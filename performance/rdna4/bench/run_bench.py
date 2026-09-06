"""Queue one API prompt on the benchmark instance and record a full measurement.

Records (per run):
  - client wall time (POST /prompt -> history complete)
  - server execution_start -> execution_success (from probe trace)
  - per-node durations (executing events) and sampler step timings (progress events)
  - torch peak allocated/reserved per device (probe, reset before the run)
  - OS-level dedicated GPU memory of the server pid (typeperf sampling, peak)
  - host RAM available / swap / process RSS before and after
  - output files (from history) + sha256
Appends one row to benchmark_results.csv and writes <out>/<run_id>.json.

Usage:
  python run_bench.py --prompt api/ZImage_turbo.json --url http://127.0.0.1:8190 \
      --test-id IMG-ZT --variant baseline --run-type warm --seed 1001 \
      --set "3.seed=1001" --set "5.steps=8" --results ../benchmark_results.csv --out ../raw/IMG-ZT
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path


def req(url: str, data=None, timeout=60):
    body = None if data is None else json.dumps(data).encode("utf-8")
    r = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"},
                               method="POST" if data is not None else "GET")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.load(resp)


def parse_value(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        return raw


class GpuSampler(threading.Thread):
    """Samples OS dedicated GPU memory of one pid via typeperf (PDH)."""

    def __init__(self, pid: int, interval: float = 1.0):
        super().__init__(daemon=True)
        self.pid = pid
        self.interval = interval
        self.samples: list[tuple[float, dict]] = []
        self._stop = threading.Event()
        self.error = None

    def run(self):
        counter = f"\\GPU Process Memory(pid_{self.pid}_*)\\Dedicated Usage"
        try:
            proc = subprocess.Popen(["typeperf", counter, "-si", str(int(self.interval))],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        except Exception as e:
            self.error = str(e)
            return
        header = None
        while not self._stop.is_set():
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line or line.startswith("Exiting"):
                continue
            parts = [p.strip('"') for p in line.split('","')]
            if header is None:
                if line.startswith('"(PDH-CSV'):
                    header = parts
                continue
            vals = {}
            for h, v in zip(header[1:], parts[1:]):
                try:
                    vals[h] = float(v)
                except ValueError:
                    pass
            self.samples.append((time.time(), vals))
        try:
            proc.kill()
        except Exception:
            pass

    def stop(self):
        self._stop.set()

    def peak_by_luid(self) -> dict:
        peak: dict[str, float] = {}
        for _, vals in self.samples:
            for k, v in vals.items():
                key = k.split("luid_")[-1].split(")")[0] if "luid_" in k else k
                peak[key] = max(peak.get(key, 0.0), v)
        return peak


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True, help="API prompt json ({'output':...} or bare prompt dict)")
    ap.add_argument("--url", default="http://127.0.0.1:8190")
    ap.add_argument("--test-id", required=True)
    ap.add_argument("--variant", required=True, help="baseline | <candidate name>")
    ap.add_argument("--run-type", default="warm", help="cold | warm | screening | validation")
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--seed", type=int, default=None, help="documentation only; use --set to apply")
    ap.add_argument("--set", action="append", default=[], help="node_id.input=json_value (applied to API prompt)")
    ap.add_argument("--workload", default="", help="free text: resolution/frames/steps for the csv")
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=3600)
    ap.add_argument("--sample-interval", type=float, default=1.0)
    ap.add_argument("--no-reset", action="store_true")
    a = ap.parse_args()

    data = json.loads(Path(a.prompt).read_text(encoding="utf-8"))
    prompt = data["output"] if "output" in data and "workflow" in data else data
    prompt = json.loads(json.dumps(prompt))  # deep copy
    for s in a.set:
        key, _, raw = s.partition("=")
        node, _, inp = key.rpartition(".")
        if node not in prompt:
            print(f"--set: node {node} not in prompt", file=sys.stderr)
            return 2
        prompt[node]["inputs"][inp] = parse_value(raw)

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{a.test_id}_{a.variant}_{a.run_type}_{time.strftime('%Y%m%d-%H%M%S')}"

    info = req(f"{a.url}/rdna4/info")
    mem0 = req(f"{a.url}/rdna4/mem")
    if not a.no_reset:
        req(f"{a.url}/rdna4/mem/reset", {})
        req(f"{a.url}/rdna4/trace/reset", {})
    sampler = GpuSampler(mem0["pid"], a.sample_interval)
    sampler.start()

    client_id = str(uuid.uuid4())
    t_post = time.time()
    queued = req(f"{a.url}/prompt", {"prompt": prompt, "client_id": client_id})
    pid = queued.get("prompt_id")
    if not pid:
        print(json.dumps(queued, indent=1)[:4000], file=sys.stderr)
        sampler.stop()
        return 3
    print(f"[{run_id}] queued {pid}", flush=True)
    record = None
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        h = req(f"{a.url}/history/{pid}")
        if pid in h:
            record = h[pid]
            break
        time.sleep(1.0)
    t_done = time.time()
    sampler.stop()
    if record is None:
        print("TIMEOUT: interrupting", file=sys.stderr)
        try:
            req(f"{a.url}/interrupt", {})
        except Exception:
            pass
        status = "timeout"
    else:
        status = record.get("status", {}).get("status_str")

    tr = req(f"{a.url}/rdna4/trace")["events"]
    mem1 = req(f"{a.url}/rdna4/mem")
    ev = [e for e in tr if e.get("prompt_id") in (pid, None)]
    t_start = next((e["t"] for e in ev if e["event"] == "execution_start"), None)
    t_end = next((e["t"] for e in ev if e["event"] in ("execution_success", "execution_error", "execution_interrupted")), None)
    # per-node durations
    exec_events = [e for e in ev if e["event"] == "executing"]
    node_times = []
    for i, e in enumerate(exec_events):
        if e.get("node") is None:
            continue
        nxt = exec_events[i + 1]["t"] if i + 1 < len(exec_events) else (t_end or e["t"])
        node_times.append({"node": e["node"], "display_node": e.get("display_node"), "start": e["t"], "dur": nxt - e["t"],
                           "class_type": prompt.get(str(e["node"]), {}).get("class_type")})
    # progress (sampler steps) per node
    prog: dict[str, list] = {}
    for e in ev:
        if e["event"] == "progress" and e.get("node") is not None:
            prog.setdefault(str(e["node"]), []).append((e["t"], e.get("value"), e.get("max")))
    step_stats = {}
    for node, pts in prog.items():
        pts.sort()
        if len(pts) >= 2:
            span = pts[-1][0] - pts[0][0]
            n = (pts[-1][1] or 0) - (pts[0][1] or 0)
            step_stats[node] = {"steps_observed": len(pts), "max": pts[-1][2], "span_s": span,
                                "s_per_step": (span / n) if n else None, "first_step_t": pts[0][0], "last_step_t": pts[-1][0],
                                "class_type": prompt.get(node, {}).get("class_type")}
    cached = next((e.get("nodes") for e in ev if e["event"] == "execution_cached"), None)

    outputs = []
    if record:
        for nid, o in record.get("outputs", {}).items():
            for k, v in o.items():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and "filename" in item:
                            outputs.append({"node": nid, "kind": k, **item})
    out_root = None
    try:
        out_root = Path(req(f"{a.url}/system_stats")["system"].get("argv", [])[
            req(f"{a.url}/system_stats")["system"]["argv"].index("--output-directory") + 1])
    except Exception:
        pass
    for o in outputs:
        if out_root and o.get("type") == "output":
            p = out_root / o.get("subfolder", "") / o["filename"]
            if p.exists():
                o["path"] = str(p)
                o["bytes"] = p.stat().st_size
                o["sha256"] = sha256(p)

    dev_peaks = {d["index"]: d for d in mem1["devices"]}
    result = {
        "run_id": run_id, "test_id": a.test_id, "variant": a.variant, "run_type": a.run_type,
        "hypothesis": a.hypothesis, "workload": a.workload, "seed": a.seed, "sets": a.set,
        "prompt_file": str(a.prompt), "prompt_id": pid, "status": status,
        "client_wall_s": t_done - t_post,
        "server_exec_s": (t_end - t_start) if (t_start and t_end) else None,
        "queue_delay_s": (t_start - t_post) if t_start else None,
        "cached_nodes": cached,
        "node_times": node_times,
        "step_stats": step_stats,
        "gpu0_peak_alloc": dev_peaks.get(0, {}).get("max_allocated"),
        "gpu0_peak_reserved": dev_peaks.get(0, {}).get("max_reserved"),
        "gpu1_peak_alloc": dev_peaks.get(1, {}).get("max_allocated"),
        "gpu1_peak_reserved": dev_peaks.get(1, {}).get("max_reserved"),
        "os_gpu_dedicated_peak_bytes": sampler.peak_by_luid(),
        "gpu_sampler_error": sampler.error,
        "host_before": mem0["host"], "host_after": mem1["host"],
        "outputs": outputs,
        "error": (record or {}).get("status", {}).get("messages", [])[-1] if status not in ("success",) and record else None,
        "server_argv": req(f"{a.url}/system_stats")["system"]["argv"],
        "attention_function": info.get("attention_function"),
        "profile_env": info.get("env"),
        "t_post": t_post, "t_done": t_done,
    }
    (out_dir / f"{run_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / f"{run_id}.prompt.json").write_text(json.dumps(prompt, ensure_ascii=False, indent=1), encoding="utf-8")

    # CSV row (shared builder; header fixed)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from rebuild_csv import FIELDS, row_from_record
    row = row_from_record(result, str(out_dir / f"{run_id}.json"))
    csv_path = Path(a.results)
    new = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(json.dumps({k: row[k] for k in ("run_id", "status", "client_wall_s", "server_exec_s", "loader_nodes_s",
                                            "sampler_span_s", "s_per_step", "steps", "gpu0_peak_alloc_gib",
                                            "gpu0_peak_reserved_gib", "gpu1_peak_alloc_gib", "os_gpu_peak_gib",
                                            "host_ram_avail_after_gib", "swap_used_after_gib", "outputs")}, ensure_ascii=False))
    if status != "success":
        err = result.get("error")
        print("ERROR:", json.dumps(err, ensure_ascii=False)[:3000], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
