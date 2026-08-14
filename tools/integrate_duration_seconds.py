#!/usr/bin/env python3
"""Expose output duration in seconds across music/video generation workflows."""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DURATION_KEY = "dawasteh_duration_seconds"
DURATION_VERSION = 1
GENERATION_FOLDERS = {
    "Music Generation",
    "Audio to Video",
    "Character Animation",
    "Controlled Video",
    "Reference to Video",
    "Talking Video",
    "Text to Video",
    "Text+Image to Video",
    "Video Editing",
}
SECONDS_RE = re.compile(r"duration|seconds|sekunden|dauer", re.IGNORECASE)


@dataclass(frozen=True)
class DurationSpec:
    fps: float
    alignment: int
    minimum: int
    targets: tuple[tuple[int, str], ...]
    default_seconds: float


SPECS: dict[str, DurationSpec] = {
    "Text to Video/LTX23_dev_mxfp8-Text-to-Video.json": DurationSpec(25, 8, 9, ((4, "length"), (19, "frames_number")), 4.0),
    "Text to Video/LTX23_dev_Q8_GGUF-Text-to-Video.json": DurationSpec(25, 8, 9, ((4, "length"), (19, "frames_number")), 4.0),
    "Text to Video/LTX23_distilled_fp8-Text-to-Video.json": DurationSpec(25, 8, 9, ((5, "length"), (20, "frames_number")), 4.0),
    "Text to Video/LTX23_distilled_mxfp8-Text-to-Video.json": DurationSpec(25, 8, 9, ((5, "length"), (20, "frames_number")), 4.0),
    "Controlled Video/WAN22_5B_Fun-Control-to-Video.json": DurationSpec(24, 4, 5, ((60, "length"),), 5.0),
    "Text+Image to Video/Kandinsky5_Lite-Text+Image-to-Video.json": DurationSpec(24, 4, 5, ((78, "length"),), 5.0),
    "Text+Image to Video/WAN22_5B-Text+Image-to-Video.json": DurationSpec(24, 4, 5, ((55, "length"),), 10.0),
    "Text+Image to Video/WAN22_bernini_i2v-Text+Image-to-Video.json": DurationSpec(16, 4, 5, ((10, "length"),), 5.0),
    "Text+Image to Video/WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json": DurationSpec(16, 4, 5, ((12, "length"),), 5.0),
    "Text+Image to Video/WAN22_i2v_14B_Q8_GGUF_lightx2v-Text+Image-to-Video.json": DurationSpec(16, 4, 5, ((10, "length"),), 5.0),
    "Character Animation/SCAIL2-Character-Animation.json": DurationSpec(16, 4, 5, ((101, "length"), (113, "frame_load_cap")), 5.0),
    "Character Animation/SCAIL2-Character-Replacement.json": DurationSpec(16, 4, 5, ((101, "length"), (113, "frame_load_cap")), 5.0),
}

SOURCE_DURATION_PATHS = {
    "Audio to Video/FLUX2_Klein_4B_Gemma4-Audio-Context-to-AudioReact-Video.json",
    "Audio to Video/LTX23-Image+Audio-to-Generative-Matching-Length-Video.json",
    "Audio to Video/Pixaroma-Image+Audio-to-AudioReact-Video.json",
    "Character Animation/WAN21_SCAIL2-Character-Replacement.json",
    "Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json",
    "Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json",
    "Reference to Video/MiniMax_H3_Spectrum_RefImage_Audio_to_Video_OriginalAudio_AutoLength.json",
    "Reference to Video/MiniMax_H3_Spectrum_RefImage_RefVideo_to_Video_Audio_AutoLength.json",
    "Talking Video/WAN21_InfiniteTalk-Multi-Speaker.json",
    "Video Editing/Bernini_R-Video-Editing.json",
}


def _next_node_id(graph: dict[str, Any]) -> int:
    values = [node.get("id") for node in graph.get("nodes", []) if isinstance(node.get("id"), int)]
    return max([int(graph.get("last_node_id", 0)), *values], default=0) + 1


def _next_link_id(graph: dict[str, Any]) -> int:
    values = []
    for link in graph.get("links", []) or []:
        value = link[0] if isinstance(link, list) and link else link.get("id") if isinstance(link, dict) else None
        if isinstance(value, int):
            values.append(value)
    return max([int(graph.get("last_link_id", 0)), *values], default=0) + 1


def _new_link(template: Any, link_id: int, source: int, source_slot: int, target: int, target_slot: int, link_type: str) -> Any:
    if isinstance(template, dict):
        return {
            "id": link_id,
            "origin_id": source,
            "origin_slot": source_slot,
            "target_id": target,
            "target_slot": target_slot,
            "type": link_type,
        }
    return [link_id, source, source_slot, target, target_slot, link_type]


def _primitive(node_id: int, value: float) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "PrimitiveFloat",
        "pos": [0, 0],
        "size": [300, 110],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [{
            "localized_name": "value",
            "name": "value",
            "type": "FLOAT",
            "widget": {"name": "value"},
            "link": None,
        }],
        "outputs": [{
            "localized_name": "FLOAT",
            "name": "FLOAT",
            "type": "FLOAT",
            "slot_index": 0,
            "links": [],
        }],
        "title": "OUTPUT DURATION · SECONDS",
        "properties": {
            "Node name for S&R": "PrimitiveFloat",
            "cnr_id": "comfy-core",
            "dawasteh_duration_control": True,
        },
        "widgets_values": [value],
        "color": "#4b3475",
        "bgcolor": "#6b4aa0",
    }


def _math(node_id: int, expression: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "ComfyMathExpression",
        "pos": [0, 0],
        "size": [360, 190],
        "flags": {"collapsed": False},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"label": "seconds", "localized_name": "values.a", "name": "values.a", "type": "FLOAT,INT,BOOLEAN", "link": None},
            {"localized_name": "expression", "name": "expression", "type": "STRING", "widget": {"name": "expression"}, "link": None},
        ],
        "outputs": [
            {"localized_name": "FLOAT", "name": "FLOAT", "type": "FLOAT", "links": None},
            {"localized_name": "INT", "name": "INT", "type": "INT", "slot_index": 1, "links": []},
            {"localized_name": "BOOL", "name": "BOOL", "type": "BOOLEAN", "links": None},
        ],
        "title": "SECONDS → VALID MODEL FRAME COUNT",
        "properties": {
            "Node name for S&R": "ComfyMathExpression",
            "cnr_id": "comfy-core",
            "dawasteh_duration_control": True,
        },
        "widgets_values": [expression],
        "color": "#704c1c",
        "bgcolor": "#956827",
    }


def _contains_native_seconds(workflow: dict[str, Any]) -> bool:
    def walk(graph: dict[str, Any]) -> bool:
        for item in graph.get("inputs", []) or []:
            if SECONDS_RE.search(str(item.get("name", ""))) or SECONDS_RE.search(str(item.get("label", ""))):
                return True
        for node in graph.get("nodes", []):
            if node.get("properties", {}).get("dawasteh_generated_note"):
                continue
            if SECONDS_RE.search(str(node.get("title", ""))):
                return True
            for item in node.get("inputs", []) or []:
                if SECONDS_RE.search(str(item.get("name", ""))) or SECONDS_RE.search(str(item.get("label", ""))):
                    return True
        return any(walk(child) for child in graph.get("definitions", {}).get("subgraphs", []) or [])
    return walk(workflow)


def is_generation_path(path_key: str) -> bool:
    return Path(path_key).parts[0] in GENERATION_FOLDERS


def model_frame_count(seconds: float, spec: DurationSpec) -> int:
    """Return the nearest model-valid frame count for a duration request."""
    return max(spec.minimum, round((float(seconds) * spec.fps - 1) / spec.alignment) * spec.alignment + 1)


def _install_explicit_control(workflow: dict[str, Any], path_key: str, spec: DurationSpec) -> None:
    nodes = workflow.setdefault("nodes", [])
    by_id = {node.get("id"): node for node in nodes}
    primitive_id = _next_node_id(workflow)
    math_id = primitive_id + 1
    primitive = _primitive(primitive_id, spec.default_seconds)
    expression = (
        f"max({spec.minimum}, round((a * {spec.fps:g} - 1) / {spec.alignment}) * "
        f"{spec.alignment} + 1)"
    )
    math_node = _math(math_id, expression)
    max_order = max((int(node.get("order", 0)) for node in nodes), default=0)
    primitive["order"] = max_order + 1
    math_node["order"] = max_order + 2
    link_id = _next_link_id(workflow)
    template = workflow.get("links", [])[0] if workflow.get("links") else []
    workflow.setdefault("links", []).append(_new_link(template, link_id, primitive_id, 0, math_id, 0, "FLOAT"))
    primitive["outputs"][0]["links"].append(link_id)
    math_node["inputs"][0]["link"] = link_id
    link_id += 1

    for node_id, input_name in spec.targets:
        target = by_id.get(node_id)
        if target is None:
            raise ValueError(f"{path_key}: duration target node {node_id} is missing")
        target_slot = next((index for index, item in enumerate(target.get("inputs", [])) if item.get("name") == input_name), None)
        if target_slot is None:
            raise ValueError(f"{path_key}: duration target {node_id}.{input_name} is missing")
        target_input = target["inputs"][target_slot]
        if target_input.get("link") is not None:
            raise ValueError(f"{path_key}: duration target {node_id}.{input_name} is already linked")
        workflow["links"].append(_new_link(template, link_id, math_id, 1, node_id, target_slot, "INT"))
        math_node["outputs"][1]["links"].append(link_id)
        target_input["link"] = link_id
        link_id += 1

    nodes.extend((primitive, math_node))
    workflow["last_node_id"] = max(int(workflow.get("last_node_id", 0)), math_id)
    workflow["last_link_id"] = max(int(workflow.get("last_link_id", 0)), link_id - 1)


def integrate_duration_seconds(workflow: dict[str, Any], path_key: str) -> tuple[dict[str, Any], bool]:
    """Return (workflow, changed) with a versioned seconds-duration contract."""
    migrated = copy.deepcopy(workflow)
    if not is_generation_path(path_key):
        return migrated, False
    marker = migrated.setdefault("extra", {}).get(DURATION_KEY, {})
    if marker.get("version") == DURATION_VERSION:
        return migrated, False

    spec = SPECS.get(path_key)
    if spec is not None:
        _install_explicit_control(migrated, path_key, spec)
        mode = "explicit-seconds-to-model-valid-frames"
        details = {
            "fps": spec.fps,
            "frame_alignment": f"{spec.alignment}n+1",
            "targets": [f"{node_id}.{name}" for node_id, name in spec.targets],
        }
    elif path_key in SOURCE_DURATION_PATHS:
        mode = "source-media-duration"
        details = {"behavior": "output duration follows or is trimmed from the loaded audio/video duration"}
    elif _contains_native_seconds(migrated):
        mode = "native-seconds"
        details = {}
    else:
        raise ValueError(f"{path_key}: generation workflow has no seconds-duration contract")

    migrated["extra"][DURATION_KEY] = {
        "version": DURATION_VERSION,
        "unit": "seconds",
        "mode": mode,
        **details,
    }
    return migrated, True
