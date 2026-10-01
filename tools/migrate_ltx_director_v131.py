#!/usr/bin/env python3
"""v1.3.1: migrate the three LTX Director workflows to the WhatDreamsCost 2.x node schema.

WhatDreamsCost-ComfyUI 2.0 rebuilt ``LTXDirector`` and ``LTXDirectorGuide``:

* LTXDirector: 17 widgets became 23 (start/end in seconds and frames, motion track, audio inpaint, override_audio).
  ``global_prompt`` is no longer a widget; the editor keeps it inside ``timeline_data`` and the node reads it from
  there. The JS restores widgets from ``properties`` when ``has_serialized_properties`` is set; old 17-value lists
  fall into its 19-value fallback and land one to three widgets off (frame_rate = "seconds", resize_method = 18).
  A new output ``motion_guide_data`` sits at slot 5, so ``frame_rate`` moved from slot 5 to 6 and
  ``combined_audio`` from 6 to 7; old links on slot 5 would feed a MOTION_GUIDE_DATA into a FLOAT input.
* LTXDirectorGuide: IC-LoRA, attention, crop and tiled-encode widgets were added in front of and behind
  ``scale_by``/``upscale_method``; the old two-value list turns into ic_lora_name = 0.5.

The script rewrites both node types in place, keeps every prompt, segment and link and leaves the rest of the
graph untouched. ``--check`` exits 1 while an old-format node is left.

  python tools/migrate_ltx_director_v131.py [--check]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from tools.rodent_layout import refresh_topology_hashes
except ModuleNotFoundError:  # run from inside tools/
    from rodent_layout import refresh_topology_hashes

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / "workflows"
NODE_VERSION = "2.0.5"

WORKFLOWS = [
    "Text+Image to Video/LTX23_Director-Prompt-Replay.json",
    "Text+Image to Video/LTX23_Director_Q8_GGUF-Tiled-Video-Generation.json",
    "Text+Image to Video/LTX23_Director_fp8-2-Stage.json",
]

# widgets_values order written by WhatDreamsCost 2.x (object_info input order + the editor DOM widget)
DIRECTOR_WIDGETS = [
    "start_second", "end_second", "duration_seconds", "start_frame", "end_frame", "duration_frames",
    "timeline_data", "local_prompts", "segment_lengths", "epsilon", "guide_strength",
    "use_custom_audio", "use_custom_motion", "inpaint_audio", "frame_rate", "display_mode",
    "custom_width", "custom_height", "resize_method", "divisible_by", "img_compression", "override_audio",
    "timeline_ui",
]
# saved by WhatDreamsCost 1.x (bundle v1.0 - v1.3.0)
DIRECTOR_WIDGETS_V1 = [
    "global_prompt", "duration_frames", "duration_seconds", "timeline_data", "local_prompts", "segment_lengths",
    "epsilon", "guide_strength", "use_custom_audio", "frame_rate", "display_mode", "custom_width", "custom_height",
    "resize_method", "divisible_by", "img_compression", "timeline_ui",
]
DIRECTOR_INPUTS = [
    ("model", "MODEL", False), ("clip", "CLIP", False), ("audio_vae", "VAE", True),
    ("optional_latent", "LATENT", True), ("global_prompt", "STRING", True),
]
DIRECTOR_OUTPUTS = [
    ("model", "MODEL"), ("positive", "CONDITIONING"), ("video_latent", "LATENT"), ("audio_latent", "LATENT"),
    ("guide_data", "GUIDE_DATA"), ("motion_guide_data", "MOTION_GUIDE_DATA"), ("frame_rate", "FLOAT"),
    ("combined_audio", "AUDIO"),
]
GUIDE_INPUTS = [
    ("positive", "CONDITIONING", False), ("negative", "CONDITIONING", False), ("vae", "VAE", False),
    ("latent", "LATENT", False), ("guide_data", "GUIDE_DATA", False),
    ("motion_guide_data", "MOTION_GUIDE_DATA", True), ("model", "MODEL", True),
]
GUIDE_OUTPUTS = [
    ("positive", "CONDITIONING"), ("negative", "CONDITIONING"), ("latent", "LATENT"), ("model", "MODEL"),
    ("latent_downscale_factor", "FLOAT"),
]
TIMELINE_DEFAULTS = {
    "mainTrackEnabled": True, "audioTrackEnabled": True, "motionTrackEnabled": True, "propHeight": 90,
    "globalPropHeight": 60, "showFilenames": True, "overrideAudio": False, "inpaint_audio": True,
    "global_prompt": "", "retake_global_prompt": "", "retakeMode": False, "retakeStart": 24, "retakeLength": 48,
    "retakePrompt": "", "retakeStrength": 1, "retakeVideo": None, "normalStartFrame": 0,
    "normalDurationFrames": 120, "segments": [], "motionSegments": [], "audioSegments": [],
}


def _num(value):
    """Timeline positions were saved as strings by the 1.x editor."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    return int(f) if f.is_integer() else f


def _io(entries, old, key):
    """Rebuild an input/output list in schema order, keeping links by name."""
    by_name = {item.get("name"): item for item in old or []}
    rebuilt = []
    for name, typ, *optional in entries:
        item = {"name": name, "type": typ}
        if optional and optional[0]:
            item["shape"] = 7
        prev = by_name.get(name) or {}
        if key == "link":
            item["link"] = prev.get("link")
        else:
            item["links"] = prev.get("links") or None
        for extra in ("label", "localized_name"):
            if extra in prev:
                item[extra] = prev[extra]
        rebuilt.append(item)
    return rebuilt


def migrate_director(node: dict) -> dict | None:
    wv = node.get("widgets_values")
    if not isinstance(wv, list) or len(wv) != len(DIRECTOR_WIDGETS_V1):
        return None
    old = dict(zip(DIRECTOR_WIDGETS_V1, wv))
    frames = int(old["duration_frames"])
    seconds = round(float(old["duration_seconds"]), 3)
    timeline = dict(TIMELINE_DEFAULTS)
    saved = json.loads(old["timeline_data"] or "{}")
    for key, value in saved.items():
        timeline[key] = value
    timeline["segments"] = [
        {**seg, "start": _num(seg.get("start")), "length": _num(seg.get("length"))} for seg in saved.get("segments", [])
    ]
    timeline["global_prompt"] = old["global_prompt"] or ""
    timeline["normalDurationFrames"] = frames
    values = {
        "start_second": 0.0, "end_second": seconds, "duration_seconds": seconds,
        "start_frame": 0, "end_frame": frames, "duration_frames": frames,
        "timeline_data": json.dumps(timeline, ensure_ascii=False, separators=(",", ":")),
        "local_prompts": old["local_prompts"], "segment_lengths": old["segment_lengths"], "epsilon": old["epsilon"],
        "guide_strength": old["guide_strength"], "use_custom_audio": bool(old["use_custom_audio"]),
        "use_custom_motion": True, "inpaint_audio": True, "frame_rate": old["frame_rate"],
        "display_mode": old["display_mode"], "custom_width": old["custom_width"],
        "custom_height": old["custom_height"], "resize_method": old["resize_method"],
        "divisible_by": old["divisible_by"], "img_compression": old["img_compression"], "override_audio": False,
        "timeline_ui": "",
    }
    node["widgets_values"] = [values[name] for name in DIRECTOR_WIDGETS]
    props = {k: v for k, v in (node.get("properties") or {}).items() if k != "widget_ue_connectable"}
    props.update(values)
    props.update({
        "ver": NODE_VERSION, "global_prompt": timeline["global_prompt"], "mainTrackEnabled": True,
        "audioTrackEnabled": True, "motionTrackEnabled": True, "audioTrackWasEnabledBeforeOverride": False,
        "overrideAudio": False, "showFilenames": True, "propHeight": 90, "globalPropHeight": 60,
        "retakeMode": False, "has_serialized_properties": True,
    })
    props.pop("aux_id", None)
    node["properties"] = props
    node["inputs"] = _io(DIRECTOR_INPUTS, node.get("inputs"), "link")
    old_outputs = [o.get("name") for o in node.get("outputs") or []]
    node["outputs"] = _io(DIRECTOR_OUTPUTS, node.get("outputs"), "links")
    new_slots = [name for name, _ in DIRECTOR_OUTPUTS]
    return {old_outputs.index(n): new_slots.index(n) for n in old_outputs if n in new_slots}


def migrate_guide(node: dict) -> dict | None:
    wv = node.get("widgets_values")
    if not isinstance(wv, list) or len(wv) != 2:
        return None
    scale_by, upscale_method = wv
    node["widgets_values"] = ["None", 1, scale_by, upscale_method, 1, "center", True, False, 256, 64, False]
    props = {k: v for k, v in (node.get("properties") or {}).items() if k != "widget_ue_connectable"}
    props["ver"] = NODE_VERSION
    props.pop("aux_id", None)
    node["properties"] = props
    node["inputs"] = _io(GUIDE_INPUTS, node.get("inputs"), "link")
    node["outputs"] = _io(GUIDE_OUTPUTS, node.get("outputs"), "links")
    return {0: 0, 1: 1, 2: 2}


def migrate(wf: dict) -> list[int]:
    changed = []
    remaps: dict[int, dict] = {}
    for node in wf.get("nodes", []):
        fn = {"LTXDirector": migrate_director, "LTXDirectorGuide": migrate_guide}.get(node.get("type"))
        remap = fn(node) if fn else None
        if remap is not None:
            changed.append(node["id"])
            remaps[node["id"]] = remap
    for link in wf.get("links", []):
        if link[1] in remaps:
            link[2] = remaps[link[1]].get(link[2], link[2])
    if changed:
        refresh_topology_hashes(wf)  # the RODENT marker pins inputs, outputs, links and widget values
    return changed


def main() -> int:
    check = "--check" in sys.argv
    pending = 0
    renames = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
    for rel in WORKFLOWS:
        path = WF / rel
        if not path.exists():  # renamed in v1.3.1
            path = WF / renames.get(rel, rel)
        wf = json.loads(path.read_text(encoding="utf-8"))
        changed = migrate(wf)
        pending += len(changed)
        if changed and not check:
            path.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("migrated", path.relative_to(WF).as_posix(), changed)
    return 1 if (check and pending) else 0


if __name__ == "__main__":
    raise SystemExit(main())
