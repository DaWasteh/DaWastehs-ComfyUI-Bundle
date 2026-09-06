#!/usr/bin/env python3
"""v1.1.2 deterministic workflow migration (LoRA trainer memory fix, performance/rdna4/REPORT.md §9).

Applies, idempotently, on top of the v1.1.1 collection:

  T1  TrainLoraNode graphs (5): ``checkpoint_depth`` 1 -> 2.
      ``checkpoint_depth=1`` wraps the whole diffusion model in ONE ``torch.utils.checkpoint`` block
      (ComfyUI logs "patching 1 modules at depth 1"), so the backward pass recomputes and holds every
      activation at once — no memory saving at all. Depth 2 checkpoints each transformer/UNet block.
      Measured 2026-09-06 on the R9700 (3 images 1024², rank 16, 8 fwd/bwd): SDXL peak 22.9 -> 7.9 GiB
      at the same step time; Z-Image Base did not fit into 32 GB at depth 1 (the 2026-09-05 freezes)
      and trains at depth 2.

  E2c Measured device placement (REPORT.md §9.4): ``DaWMultiGPUDeviceControl`` CLIP/VAE gpu:1 -> gpu:0 for the
      workflows listed in ``E2_REMAINING`` (ACE-Step 1.5 Turbo 4B: 60-s short form warm 218.6 -> 10.1 s, cold
      249.6 -> 24.6 s, because the Qwen-4B LM ran partially loaded on the 16-GB card at 0.68 s/token;
      WAN 2.2 T2V 14B short form: cold 124.8 -> 106.9 s, warm 159.2 -> 69.4 s).

Every migrated file carries ``extra[MARKER_KEY] = {"version": MARKER_VERSION}`` so that
``tools/validate_workflows.py --against-head`` can rebuild it from the previous release
(v1.1.1 form -> v1.1.2 form).

  python tools/upgrade_v112.py --check     # verify workflows/ == apply(HEAD files)
  python tools/upgrade_v112.py --apply     # rewrite workflows/ in place
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / "workflows"
MARKER_KEY = "dawasteh_rdna4_v112"
MARKER_VERSION = 1

TRAIN_DEPTH2 = {
    "LoRA Generation/Boogu_Image_Base-LoRA-Training.json",
    "LoRA Generation/FLUX1_Dev-LoRA-Training.json",
    "LoRA Generation/FLUX2_Klein_4B_Base-LoRA-Training.json",
    "LoRA Generation/SDXL-LoRA-Training.json",
    "LoRA Generation/ZImage_Base-LoRA-Training.json",
}
CHECKPOINT_DEPTH = 2
E2_REMAINING = {
    "Music Generation/ACE-Step1_5_Turbo_4B-Music-Generation.json",
    "Text to Video/WAN22_14B_fp8_lightx2v-Text-to-Video.json",
}
ALL_GPU0 = ["gpu:0", "gpu:0", "gpu:0"]


def train_widget_index(node: dict, name: str) -> int | None:
    """Index of widget *name* in ``widgets_values`` of a TrainLoraNode (v1.1.1 form carries the
    ``control_after_generate`` value right after ``seed``)."""
    names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
    if name not in names:
        return None
    idx = names.index(name)
    wv = node.get("widgets_values") or []
    if len(wv) == len(names) + 1 and "seed" in names and idx > names.index("seed"):
        idx += 1
    return idx if idx < len(wv) else None


def set_checkpoint_depth(wf: dict, depth: int = CHECKPOINT_DEPTH) -> bool:
    changed = False
    for n in wf.get("nodes", []):
        if n.get("type") != "TrainLoraNode":
            continue
        idx = train_widget_index(n, "checkpoint_depth")
        if idx is None:
            continue
        if n["widgets_values"][idx] != depth:
            n["widgets_values"][idx] = depth
            changed = True
    return changed


def set_control(wf: dict, values: list[str]) -> bool:
    """Same rule as upgrade_v111.set_control: widgets + ``extra.dawasteh_dual_gpu.defaults``."""
    changed = False
    for node in wf.get("nodes", []):
        if node.get("type") == "DaWMultiGPUDeviceControl":
            wv = node.get("widgets_values") or []
            if len(wv) != 3:
                continue
            new = list(values)
            if list(wv) != new:
                node["widgets_values"] = new
                changed = True
            defaults = wf.get("extra", {}).get("dawasteh_dual_gpu", {}).get("defaults")
            if isinstance(defaults, dict):
                expected = {"MODEL": new[0], "CLIP": new[1], "VAE": new[2]}
                if defaults != expected:
                    defaults.update(expected)
                    changed = True
    return changed


def apply(wf: dict, rel: str) -> dict:
    """Return the v1.1.2 form of *wf* (already-migrated input is returned unchanged)."""
    wf = copy.deepcopy(wf)
    rel = rel.replace("\\", "/")
    if rel not in TRAIN_DEPTH2 and rel not in E2_REMAINING:
        return wf
    if rel in TRAIN_DEPTH2:
        set_checkpoint_depth(wf)
    if rel in E2_REMAINING:
        set_control(wf, ALL_GPU0)
    wf.setdefault("extra", {})[MARKER_KEY] = {"version": MARKER_VERSION}
    # keep the RODENT layout marker consistent with the changed widget (same rule as upgrade_v111)
    try:
        from tools.rodent_layout import RODENT_KEY, _topology_hash
    except ModuleNotFoundError:  # direct execution from tools/
        from rodent_layout import RODENT_KEY, _topology_hash
    marker = wf.get("extra", {}).get(RODENT_KEY)
    if marker and marker.get("topology_sha256") != _topology_hash(wf):
        marker["topology_sha256"] = _topology_hash(wf)
    return wf


def targets() -> set[str]:
    return set(TRAIN_DEPTH2) | set(E2_REMAINING)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    diffs = 0
    for rel in sorted(targets()):
        p = WORKFLOWS / rel
        raw = p.read_text(encoding="utf-8")
        wf = json.loads(raw)
        new = apply(wf, rel)
        if new != wf:
            diffs += 1
            if a.apply:
                p.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"rewrote {rel}")
            else:
                print(f"differs {rel}")
    print(f"{'applied' if a.apply else 'check'}: {diffs} file(s) {'rewritten' if a.apply else 'differ'}")
    return 0 if a.apply or diffs == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
