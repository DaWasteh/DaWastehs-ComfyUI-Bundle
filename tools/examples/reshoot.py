"""Retake the workflow screenshot of finished examples without running them again (no GPU work).

Loads the example's workflow with its patches, hands the recorded outputs to the frontend's node-output store (the
same data ComfyUI shows after a run: images, videos, audio, text) and takes the compact screenshot. Used after the
screenshot layout changed (v1.3.1: groups shrink to their content once the explanation notes are hidden).

  L:/ComfyUI/tmp/minimax-test-venv/Scripts/python.exe tools/examples/reshoot.py [--only substring] [--force]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import CATALOG, wf_path  # noqa: E402
from comfy_driver import ComfyDriver  # noqa: E402
from runner import INPUT_DIR, URL, WORK, log, run_dir, server_alive  # noqa: E402

JS_OUTPUTS = r"""
const outputs = arguments[0];
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  await new Promise(r => setTimeout(r, 1500));   // input previews (Load Image) land in the same store first
  app.nodeOutputs = {...(app.nodeOutputs || {}), ...outputs};   // legacy setter, synced into the node-output store
  for (const [id, out] of Object.entries(outputs)) {
    const node = app.graph.getNodeById(Number(id.split(':').pop())) || app.graph.getNodeById(id);
    if (node && node.onExecuted) { try { node.onExecuted(out); } catch (e) {} }
  }
  app.graph.setDirtyCanvas(true, true);
  await new Promise(r => setTimeout(r, 2500));   // let previews load before the layout pass measures sizes
  done({ok: true, nodes: Object.keys(outputs).length});
})().catch(e => done({ok: false, error: String(e)}));
"""

MEDIA_KINDS = {"images", "gifs", "audio", "video", "animated", "3d", "result"}


def recorded_outputs(result: dict) -> dict:
    """{node id: {kind: [file items]}} for the server's /view, plus preview texts."""
    out: dict[str, dict] = {}
    files = list(result.get("outputs") or [])
    for g in result.get("gate_runs") or []:
        files += g.get("files", [])
    for f in files:
        item = {"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")}
        out.setdefault(str(f["node"]), {}).setdefault(f["kind"], [])
        if item not in out[str(f["node"])][f["kind"]]:
            out[str(f["node"])][f["kind"]].append(item)
    for node_id, text in (result.get("texts") or {}).items():
        out.setdefault(str(node_id), {})["text"] = [text["text"] if isinstance(text, dict) else text]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    todo = [ex for ex in CATALOG if ex.shot and (not args.only or any(o in ex.workflow for o in args.only))]
    driver = ComfyDriver(URL)
    driver.open()
    done = skipped = failed = 0
    try:
        for ex in todo:
            path = run_dir(ex) / "result.json"
            if not path.exists():
                continue
            result = json.loads(path.read_text(encoding="utf-8"))
            if result.get("status") != "success" or (result.get("shot_compact") and not args.force):
                skipped += 1
                continue
            while not server_alive():  # the runner restarts the server before heavy video workflows
                time.sleep(10)
            try:
                workflow = json.loads(wf_path(ex.workflow).read_text(encoding="utf-8"))
                for local, name in ex.uploads.items():
                    src = Path(local) if Path(local).is_absolute() else WORK / "assets" / local
                    target = INPUT_DIR / name
                    if src.exists() and not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, target)
                if ex.prepare:
                    workflow = ex.prepare(workflow)
                driver.load(workflow)
                driver.patch(ex.patches)
                res = driver.driver.execute_async_script(JS_OUTPUTS, recorded_outputs(result))
                if not res.get("ok"):
                    raise RuntimeError(json.dumps(res))
                result["shot"] = driver.screenshot(run_dir(ex) / "workflow.png", **ex.shot_opts)
                result["shot_compact"] = True
                path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
                done += 1
                log(f"reshoot {ex.workflow} :: {ex.key}")
            except Exception as exc:  # keep going; the old screenshot stays
                failed += 1
                log(f"reshoot FAILED {ex.workflow} :: {ex.key}: {exc}"[:400])
    finally:
        driver.close()
    print(f"reshot {done}, skipped {skipped}, failed {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
