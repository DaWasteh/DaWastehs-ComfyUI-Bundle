"""Run gallery examples through the real ComfyUI frontend and record outputs, timings and memory.

Every example is one queued run of a bundle workflow with a few widgets changed (prompt, seed, size, inputs). Results
land in a staging folder (default ``L:/ComfyUI/tmp/examples-v131/runs``); ``build_gallery.py`` turns them into the
``examples/`` folder and the GitHub Pages site. Finished examples are skipped, so a run can be resumed at any time.

  L:/ComfyUI/tmp/minimax-test-venv/Scripts/python.exe tools/examples/runner.py --only "Text to Image/" [--force]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import CATALOG, Example  # noqa: E402
from comfy_driver import ComfyDriver, history_error, history_files, history_texts  # noqa: E402
from gpu_mem import TreeSampler, system_commit_gib  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORK = Path("L:/ComfyUI/tmp/examples-v131")
SERVER_DIR = WORK / "server"
RUNS = WORK / "runs"
INPUT_DIR = WORK / "input"
BENCH = ROOT / "performance" / "rdna4" / "bench"
PROFILE = ROOT / "performance" / "rdna4" / "profiles" / "v131_examples.json"
VENV_PY = Path("L:/ComfyUI/.venv/Scripts/python.exe")
FFMPEG = "L:/ComfyUI/.venv/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"
URL = "http://127.0.0.1:8192"
GIB = 2**30
# 47 GB RAM: above this system commit the example is interrupted (bug check 0x101 after 140-162 GiB, 2026-09-30)
MAX_COMMIT_GIB = 135
# memory piles up across examples in one server process (FLUX.2 dev: 118 GiB fresh, 187 GiB after three runs):
# restart the server before an example when the idle commit is already above this
RESTART_ABOVE_COMMIT_GIB = 75
# heavy video workflows start from a fresh server process, so memory does not pile up across examples
FRESH_SERVER_CATEGORIES = ("Text to Video/", "Text+Image to Video/", "Audio to Video/", "Controlled Video/",
                           "Character Animation/", "Talking Video/", "Reference to Video/", "Video Upscaling/",
                           "Video Editing/", "Live Avatar/")


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.+-]+", "_", text).strip("_")


def run_dir(ex: Example) -> Path:
    return RUNS / slug(ex.workflow.removesuffix(".json")) / slug(ex.key)


def log(msg: str) -> None:
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    with open(WORK / "runner.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# -- server ---------------------------------------------------------------------------------------------------------
def server_alive(driver: ComfyDriver | None = None) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(URL + "/system_stats", timeout=5):
            return True
    except Exception:
        return False


def restart_server() -> None:
    log("restarting test server")
    subprocess.run([str(VENV_PY), str(BENCH / "comfy_server.py"), "stop", "--run-dir", str(SERVER_DIR)],
                   capture_output=True, text=True, timeout=120)
    time.sleep(5)
    res = subprocess.run([str(VENV_PY), str(BENCH / "comfy_server.py"), "start", "--profile", str(PROFILE),
                          "--run-dir", str(SERVER_DIR), "--port", "8192", "--startup-timeout", "600"],
                         capture_output=True, text=True, timeout=700)
    log("server: " + (res.stdout + res.stderr).strip()[-300:])


# -- one example ----------------------------------------------------------------------------------------------------
def node_titles(workflow: dict) -> dict:
    titles = {}
    for node in workflow.get("nodes", []):
        titles[str(node["id"])] = {"type": node["type"], "title": node.get("title") or ""}
    for sg in (workflow.get("definitions") or {}).get("subgraphs") or []:
        for node in sg.get("nodes", []):
            titles.setdefault(str(node["id"]), {"type": node["type"], "title": node.get("title") or ""})
    return titles


def exec_seconds(entry: dict) -> float | None:
    start = end = None
    for name, data in entry.get("status", {}).get("messages", []):
        if name == "execution_start":
            start = data.get("timestamp")
        if name in ("execution_success", "execution_error", "execution_interrupted"):
            end = data.get("timestamp")
    if start and end:
        return round((end - start) / 1000.0, 1)
    return None


def run_example(driver: ComfyDriver, ex: Example, force: bool = False) -> dict:
    out_dir = run_dir(ex)
    result_path = out_dir / "result.json"
    if result_path.exists() and not force:
        old = json.loads(result_path.read_text(encoding="utf-8"))
        if old.get("status") == "success":
            return old
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    wf_path = ROOT / "workflows" / ex.workflow
    if not wf_path.exists():  # renamed in v1.3.1; the catalog and the run folders keep the v1.3.0 names
        renames = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
        wf_path = ROOT / "workflows" / renames.get(ex.workflow, ex.workflow)
    workflow = json.loads(wf_path.read_text(encoding="utf-8"))
    for local, name in ex.uploads.items():
        src = Path(local)
        if not src.is_absolute():
            src = WORK / "assets" / local
        target = INPUT_DIR / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    if ex.prepare:
        workflow = ex.prepare(workflow)

    result = {"workflow": ex.workflow, "key": ex.key, "title": ex.title, "group": ex.group, "params": ex.params,
              "patches": ex.patches, "uploads": {Path(k).name: v for k, v in ex.uploads.items()},
              "started": time.strftime("%Y-%m-%d %H:%M:%S"), "status": "error"}
    t0 = time.time()
    sampler = None
    try:
        loaded = driver.load(workflow)
        if loaded.get("dialogs"):
            result["load_dialogs"] = loaded["dialogs"]  # e.g. "Failed to restore node" of a node extension
        driver.patch(ex.patches)
        driver.post_json("/rdna4/mem/reset")
        server_pid = driver.get_json("/rdna4/mem")["pid"]
        sampler = TreeSampler(server_pid, interval=1.0, on_danger=lambda: driver.post_json("/interrupt"),
                              max_commit_gib=MAX_COMMIT_GIB).start()
        prompt_id = driver.queue()
        result["prompt_id"] = prompt_id
        entry = driver.wait(prompt_id, timeout=ex.timeout)
        gates = ex.gates if isinstance(ex.gates, list) else [None] * int(ex.gates or 0)
        result["gate_runs"] = []
        for gate in gates:
            # Pixaroma pause gate: the first run stops at the gate, Continue runs the rest from the snapshot.
            err = history_error(entry)
            if err:
                break
            result["gate_runs"].append({"prompt_id": prompt_id, "exec_seconds": exec_seconds(entry),
                                        "files": history_files(entry), "texts": history_texts(entry)})
            prompt_id = driver.continue_gate(gate)
            entry = driver.wait(prompt_id, timeout=ex.timeout)
        # Some nodes queue further prompts from the frontend: the VHS Meta Batch Manager every next batch (just after
        # the previous one finished; the video is written by the last batch), Pixaroma's XY plot one prompt per cell
        # (the grid comes with the last), Pixaroma's multi-prompt and queue nodes one per entry. Collect them all.
        while not history_error(entry):
            time.sleep(3)
            q = driver.get_json("/queue")
            follow = [item[1] for item in (q.get("queue_running") or []) + (q.get("queue_pending") or [])]
            if not follow:
                break
            result["gate_runs"].append({"prompt_id": prompt_id, "exec_seconds": exec_seconds(entry),
                                        "files": history_files(entry), "texts": history_texts(entry)})
            prompt_id = follow[0]
            entry = driver.wait(prompt_id, timeout=ex.timeout)
        mem = driver.get_json("/rdna4/mem")
        result["memory"] = sampler.stop()
        sampler = None
        result["memory"]["torch"] = [{"name": d["name"], "max_allocated_gib": round(d["max_allocated"] / GIB, 2),
                                      "max_reserved_gib": round(d["max_reserved"] / GIB, 2)} for d in mem["devices"]]
        secs = [g["exec_seconds"] for g in result["gate_runs"]] + [exec_seconds(entry)]
        result["exec_seconds"] = round(sum(s for s in secs if s), 1) if any(secs) else None
        err = history_error(entry)
        if not err and result["memory"].get("commit_guard_tripped"):
            err = "commit guard: " + result["memory"].get("commit_guard_reason", "")
        titles = node_titles(workflow)
        files = []
        all_files = [f for g in result["gate_runs"] for f in g["files"]] + history_files(entry)
        seen_files = set()
        for f in all_files:
            if (f["type"], f["subfolder"], f["filename"]) in seen_files:
                continue
            seen_files.add((f["type"], f["subfolder"], f["filename"]))
            # ComfyUI appends "temp" to --temp-directory (folder_paths.set_temp_directory)
            base = SERVER_DIR / "output" if f["type"] == "output" else SERVER_DIR / "temp" / "temp"
            src = base / f["subfolder"] / f["filename"]
            if not src.exists():
                result.setdefault("missing_files", []).append(str(src))
                continue
            dst_name = f"{f['node'].replace(':', '_')}_{f['kind']}_{f['filename']}"
            shutil.copy2(src, out_dir / dst_name)
            info = titles.get(f["node"].split(":")[-1], {})
            files.append({**f, "file": dst_name, "node_type": info.get("type"), "node_title": info.get("title")})
        result["outputs"] = files
        texts = {}
        for g in result["gate_runs"]:
            texts.update(g["texts"])
        texts.update(history_texts(entry))
        result["texts"] = {k: {"text": v, **titles.get(k.split(":")[-1], {})} for k, v in texts.items()}
        if err:
            result["error"] = err
        else:
            result["status"] = "success"
        if ex.asset and result["status"] == "success" and files:
            # This output feeds other examples as an input file.
            pick = next((f for f in files if not ex.asset_node or f["node"] == ex.asset_node), files[0])
            asset = WORK / "assets" / ex.asset
            asset.parent.mkdir(parents=True, exist_ok=True)
            src = out_dir / pick["file"]
            if src.suffix.lower() == asset.suffix.lower():
                shutil.copy2(src, asset)
            else:  # e.g. FLAC from SaveAudio -> MP3 input asset, WEBM -> MP4
                subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), str(asset)], check=True)
            result["asset"] = ex.asset
        if ex.shot and result["status"] == "success":
            result["shot"] = driver.screenshot(out_dir / "workflow.png", **ex.shot_opts)
            result["shot_compact"] = True
    except Exception as exc:  # keep going with the next example
        result["error"] = f"{type(exc).__name__}: {exc}"[:4000]
        result["traceback"] = traceback.format_exc()[-4000:]
        if sampler:
            result["memory"] = sampler.stop()
    result["seconds"] = round(time.time() - t0, 1)
    result["frontend"] = driver.frontend
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def system_info(driver: ComfyDriver) -> dict:
    stats = driver.get_json("/system_stats")
    sysd = stats.get("system", {})
    # device names look like "cuda:0 AMD Radeon AI PRO R9700 : native" (allocator backend after the colon)
    gpus = [f"{d['name'].split(':')[1].split(' ', 1)[-1].strip() if d['name'].count(':') >= 2 else d['name']} "
            f"({d['vram_total'] / GIB:.0f} GB)" for d in stats.get("devices", [])]
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    return {
        "Betriebssystem": "Windows 11 Pro",
        "GPUs": " + ".join(gpus),
        "Arbeitsspeicher": f"{sysd.get('ram_total', 0) / GIB:.0f} GB",
        "ComfyUI": sysd.get("comfyui_version", ""),
        "PyTorch": sysd.get("pytorch_version", ""),
        "Python": (sysd.get("python_version", "") or "").split(" ")[0],
        "Frontend": driver.frontend or "",
        "Startparameter": " ".join(a for a in profile["args"] if not a.startswith("L:/")).replace("--input-directory", "").strip(),
        "VRAM-Guard": "DaWasteh VRAM guard, 3 GiB Reserve je GPU",
        "profile": profile["description"],
    }


def skip_file() -> list[str]:
    """Workflows to leave out of every further pass (one substring per line), e.g. runs that exceed the commit guard."""
    path = WORK / "skip_workflows.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[], help="substring filter on workflow path (repeatable)")
    ap.add_argument("--key", action="append", default=[], help="substring filter on example key")
    ap.add_argument("--skip", action="append", default=[], help="skip workflows whose path contains this (repeatable)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-free", action="store_true")
    ap.add_argument("--restart", action="store_true",
                    help="start from a fresh server process (node packs that patch sys.modules at run time)")
    args = ap.parse_args()

    todo = [ex for ex in CATALOG
            if (not args.only or any(o in ex.workflow for o in args.only))
            and (not args.key or any(k in ex.key for k in args.key))
            and not any(s in ex.workflow for s in args.skip + skip_file())]
    if args.list:
        for ex in todo:
            done = (run_dir(ex) / "result.json").exists()
            print(("x " if done else "  ") + ex.workflow + " :: " + ex.key)
        print(len(todo), "examples")
        return 0
    WORK.mkdir(parents=True, exist_ok=True)
    import urllib.request
    pending = [ex for ex in todo if args.force or not (run_dir(ex) / "result.json").exists()
               or json.loads((run_dir(ex) / "result.json").read_text(encoding="utf-8")).get("status") != "success"]
    if not server_alive() or (args.restart and pending):
        while server_alive():  # let a previous runner finish its prompt before restarting
            with urllib.request.urlopen(URL + "/queue", timeout=10) as r:
                q = json.load(r)
            if not q["queue_running"] and not q["queue_pending"]:
                break
            time.sleep(5)
        restart_server()
    while True:  # a previous runner may have left a prompt running
        with urllib.request.urlopen(URL + "/queue", timeout=10) as r:
            q = json.load(r)
        if not q["queue_running"] and not q["queue_pending"]:
            break
        time.sleep(5)
    driver = ComfyDriver(URL)
    driver.open()
    try:
        (WORK / "system.json").write_text(json.dumps(system_info(driver), ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as exc:
        log(f"system info failed: {exc}")
    last_workflow = None
    failures = 0
    for i, ex in enumerate(todo, 1):
        res_path = run_dir(ex) / "result.json"
        if res_path.exists() and not args.force:
            try:
                if json.loads(res_path.read_text(encoding="utf-8")).get("status") == "success":
                    continue
            except Exception:
                pass
        fresh = ex.workflow != last_workflow and ex.workflow.startswith(FRESH_SERVER_CATEGORIES)
        if fresh or system_commit_gib() > RESTART_ABOVE_COMMIT_GIB:
            driver.close()
            restart_server()
            driver = ComfyDriver(URL)
            driver.open()
        elif ex.workflow != last_workflow and not args.no_free:
            try:
                driver.free()
                time.sleep(3)
            except Exception:
                pass
        last_workflow = ex.workflow
        log(f"[{i}/{len(todo)}] {ex.workflow} :: {ex.key}")
        try:
            res = run_example(driver, ex, force=args.force)
        except Exception as exc:  # e.g. a missing derived input asset: record it, keep the pass going
            res = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        mem = res.get("memory") or {}
        torch_peaks = ", ".join(f"{d['name'].split()[-1]} {d['max_reserved_gib']}" for d in mem.get("torch", []))
        log(f"    -> {res['status']} {res.get('seconds')} s (exec {res.get('exec_seconds')}) torch[{torch_peaks}] "
            f"proc {mem.get('peak_process_private_gib')} GiB commit {mem.get('peak_system_commit_gib')} "
            f"{res.get('error', '')[:300]}")
        if res["status"] != "success":
            failures += 1
            if not server_alive():
                restart_server()
                driver.close()
                driver = ComfyDriver(URL)
                driver.open()
        else:
            failures = 0
    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
