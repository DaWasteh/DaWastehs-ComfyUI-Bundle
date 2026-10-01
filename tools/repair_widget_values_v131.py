#!/usr/bin/env python3
"""v1.3.1: repair widget values that the current frontend reads into the wrong widgets.

Found by tools/examples/widget_check.py, which loads every workflow into the real frontend and checks each widget
against /object_info:

* DaWastehQwen3TTSLoRAInference (Voice Design live voice, Live Avatar 04): the v0.6.9 generator wrote the values
  without the control_after_generate slot the frontend adds behind every seed, so everything after the seed moved one
  widget further (max_new_tokens = 0.8, top_p = 20, repetition_penalty = "sdpa"). The repair gives the files exactly
  what tools/generate_voice_lora_workflows.py now generates: the slot, its line in the node's parameter note and the
  RODENT topology hash over the changed values.
* AILab_Qwen3TTSCustomVoice (Voice Design CustomVoice): the node gained an optional ``instruct`` text before
  ``unload_models``; the saved values put ``True`` into instruct and ``0`` into unload_models.
* LTX23_Director-Prompt-Replay: empty ``widget_ue_connectable`` properties left behind by the Use Everywhere
  extension become non-cloneable objects after loading, and the frontend stops with "DataCloneError". The same
  save left the Video Combine node with ``[null, null, null, "image/gif", null, null]``, so the run stopped at
  filename_prefix = None.

  python tools/repair_widget_values_v131.py [--check]
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
# the line tools/refine_workflows.py writes for a seed's control widget (build_note_text / _effect)
SEED_CONTROL_NOTE = (
    "- `seed_control_after_generate` = `fixed` \u2014 Verhalten des Werts nach jedem Workflow-Lauf. "
    "`randomize` erzeugt pro Lauf eine neue Variation; `fixed` beh\u00e4lt den Wert; andere Modi \u00e4ndern ihn "
    "schrittweise."
)


def fix_tts_lora(node: dict) -> bool:
    wv = node.get("widgets_values") or []
    if node.get("type") == "DaWastehQwen3TTSLoRAInference" and len(wv) == 15 and not isinstance(wv[7], str):
        wv.insert(7, "fixed")  # text, adapter, speaker, size, language, lora_scale, seed | control_after_generate
        return True
    return False


def document_seed_control(wf: dict, node_ids: list) -> None:
    """Add the control widget to the generated parameter notes of the repaired TTS nodes (after the seed line)."""
    for note in wf.get("nodes", []):
        props = note.get("properties") or {}
        if not props.get("dawasteh_generated_note") or props.get("dawasteh_note_for") not in node_ids:
            continue
        lines = note["widgets_values"][0].split("\n")
        seed = next(i for i, line in enumerate(lines) if line.startswith("- `seed` = "))
        if not lines[seed + 1].startswith("- `seed_control_after_generate` = "):
            lines.insert(seed + 1, SEED_CONTROL_NOTE)
            note["widgets_values"][0] = "\n".join(lines)


def fix_custom_voice(node: dict) -> bool:
    wv = node.get("widgets_values") or []
    # old: text, speaker, model_size, language, unload_models, seed, <legacy>, control
    if node.get("type") == "AILab_Qwen3TTSCustomVoice" and len(wv) == 8 and isinstance(wv[4], bool):
        node["widgets_values"] = [wv[0], wv[1], wv[2], wv[3], "", wv[4], wv[5], wv[7]]
        return True
    return False


def fix_ue_property(node: dict) -> bool:
    props = node.get("properties") or {}
    if "widget_ue_connectable" in props:
        del props["widget_ue_connectable"]
        return True
    return False


VIDEO_COMBINE = {
    "frame_rate": 24, "loop_count": 0, "filename_prefix": "video/LTX_Director_Replay", "format": "video/h264-mp4",
    "pix_fmt": "yuv420p", "crf": 19, "save_metadata": True, "trim_to_audio": False, "pingpong": False,
    "save_output": True, "videopreview": {"hidden": False, "paused": False, "params": {}},
}


def fix_video_combine(node: dict) -> bool:
    wv = node.get("widgets_values")
    if node.get("type") == "VHS_VideoCombine" and isinstance(wv, list) and not any(v for v in wv if v != "image/gif"):
        node["widgets_values"] = dict(VIDEO_COMBINE)
        return True
    return False


def fix_replay(node: dict) -> bool:
    return fix_ue_property(node) | fix_video_combine(node)


REPAIRS = {
    "Voice Design/Qwen3-TTS_LoRA-Low-Latency-Live-Voice.json": fix_tts_lora,
    "Live Avatar/LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA.json": fix_tts_lora,
    "Voice Design/QwenTTS_CustomVoice-Text-to-Voice.json": fix_custom_voice,
    "Text+Image to Video/LTX23_Director-Prompt-Replay.json": fix_replay,
}


def apply(rel: str, wf: dict) -> list:
    """Repair workflow ``rel`` (v1.3.0 path) in place; returns the changed node ids."""
    repair = REPAIRS.get(rel)
    changed = [n["id"] for n in wf.get("nodes", []) if repair(n)] if repair else []
    if changed and repair is fix_tts_lora:
        document_seed_control(wf, changed)
    if changed:
        refresh_topology_hashes(wf)  # the RODENT marker pins the widget values
    return changed


def main() -> int:
    check = "--check" in sys.argv
    pending = 0
    for rel in REPAIRS:
        path = WF / rel
        if not path.exists():  # renamed in v1.3.1: look the file up through the rename map
            renames = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
            path = WF / renames.get(rel, rel)
        wf = json.loads(path.read_text(encoding="utf-8"))
        changed = apply(rel, wf)
        pending += len(changed)
        if changed and not check:
            path.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("repaired", rel, changed)
    return 1 if (check and pending) else 0


if __name__ == "__main__":
    raise SystemExit(main())
