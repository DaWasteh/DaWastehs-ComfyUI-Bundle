#!/usr/bin/env python3
"""v1.3.1: remove the device values that the dual-GPU migration wrote into proxy-promoted subgraph instances.

Such an instance keeps its promoted values (prompt, size, duration ...) in the inner nodes and has no own
``widgets_values``. The migration appended ["gpu:0", "gpu:0", "gpu:0"] there, and the frontend assigns those
positionally to the first three promoted widgets, so the prompt read "gpu:0". Affected: LTX23 Image-to-Video,
LTX23 First+Last-Frame, Bernini-R Video Edit, Stable Audio 3 Medium (FP32 and INT8).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    from tools.rodent_layout import refresh_topology_hashes
except ModuleNotFoundError:  # run from inside tools/
    from rodent_layout import refresh_topology_hashes

ROOT = Path(__file__).resolve().parents[1]
DEVICE = re.compile(r"^(gpu:\d+|cpu)$")


def broken_instances(wf: dict) -> list[dict]:
    subgraphs = {sg["id"] for sg in (wf.get("definitions") or {}).get("subgraphs") or []}
    out = []
    for node in wf.get("nodes", []):
        if node.get("type") not in subgraphs:
            continue
        wv = node.get("widgets_values")
        if (node.get("properties") or {}).get("proxyWidgets") and wv and all(
                isinstance(v, str) and DEVICE.match(v) for v in wv):
            out.append(node)
    return out


def repair(wf: dict) -> list:
    """Clear the device-only values in place; returns the repaired instance ids."""
    nodes = broken_instances(wf)
    for node in nodes:
        node["widgets_values"] = []
    if nodes:
        refresh_topology_hashes(wf)  # the RODENT marker pins the widget values
    return [n["id"] for n in nodes]


def main() -> int:
    check = "--check" in sys.argv
    found = 0
    for path in sorted((ROOT / "workflows").rglob("*.json")):
        wf = json.loads(path.read_text(encoding="utf-8"))
        ids = [n["id"] for n in broken_instances(wf)]
        if not ids:
            continue
        found += len(ids)
        print(f"{path.relative_to(ROOT)}: {ids}")
        if not check:
            repair(wf)
            path.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if (check and found) else 0


if __name__ == "__main__":
    raise SystemExit(main())
