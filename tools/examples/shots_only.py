"""Screenshot workflows that get no example run (realtime, training, license-restricted): load, hide notes, capture.

  L:/ComfyUI/tmp/minimax-test-venv/Scripts/python.exe tools/examples/shots_only.py [--all-missing] [rel.json ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import CATALOG, wf_path  # noqa: E402
from comfy_driver import ComfyDriver, load_workflow  # noqa: E402
from runner import WORK, slug  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--all-missing" in sys.argv:  # screenshots are named after the v1.3.0 path, like the run folders
        covered = {e.workflow for e in CATALOG}
        renames = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
        previous = {new: old for old, new in renames.items()}
        current = (p.relative_to(ROOT / "workflows").as_posix() for p in (ROOT / "workflows").rglob("*.json"))
        args += sorted(old for old in (previous.get(rel, rel) for rel in current) if old not in covered)
    out_dir = WORK / "shots"
    out_dir.mkdir(parents=True, exist_ok=True)
    d = ComfyDriver()
    try:
        d.open()
        for rel in args:
            target = out_dir / (slug(rel.removesuffix(".json")) + ".png")
            try:
                d.load(load_workflow(wf_path(rel)))
                info = d.screenshot(target)
                print("shot", rel, info["size"], flush=True)
            except Exception as exc:
                print("FAILED", rel, exc, flush=True)
    finally:
        d.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
