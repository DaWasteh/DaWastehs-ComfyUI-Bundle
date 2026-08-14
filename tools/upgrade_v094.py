#!/usr/bin/env python3
"""Deterministic v0.9.4 upgrades for adaptive media and Wan Animate 2."""
from __future__ import annotations

import copy
from typing import Any


UPGRADE_KEY = "dawasteh_v094_adaptive_media"
UPGRADE_VERSION = 4
WAN_PATH = "Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json"
AUTO_PROFILE = "Auto (connected model)"
WAN_PROFILE = "Wan 2.x / Animate 2 (480p)"
NATIVE_QUALITY = "Model native (100%)"
ADAPTIVE_OBJECT_INFO = {
    "DaWAdaptiveLoadImage": {
        "display_name": "Adaptive Load Image · Model Resolution",
        "description": "Loads and scales a complete image to a model-valid resolution without cropping.",
        "input": {"required": {
            "image": ["COMBO", {"image_upload": True}],
            "model_profile": ["COMBO", {"default": AUTO_PROFILE}],
            "quality": ["COMBO", {"default": NATIVE_QUALITY}],
            "detected_profile": ["COMBO", {"default": "Not detected"}],
        }},
        "input_order": {"required": ["image", "model_profile", "quality", "detected_profile"]},
        "output": ["IMAGE", "MASK", "INT", "INT", "STRING", "STRING"],
        "output_name": ["image", "mask", "width", "height", "model_profile", "info"],
    },
    "DaWAdaptiveLoadVideo": {
        "display_name": "Adaptive Load Video · Model Resolution",
        "description": "Loads video lazily and scales complete frames to a model-valid resolution without cropping.",
        "input": {"required": {
            "file": ["COMBO", {"video_upload": True}],
            "model_profile": ["COMBO", {"default": AUTO_PROFILE}],
            "quality": ["COMBO", {"default": NATIVE_QUALITY}],
            "detected_profile": ["COMBO", {"default": "Not detected"}],
        }},
        "input_order": {"required": ["file", "model_profile", "quality", "detected_profile"]},
        "output": ["VIDEO", "INT", "INT", "FLOAT", "FLOAT", "STRING", "STRING"],
        "output_name": ["video", "width", "height", "fps", "duration", "model_profile", "info"],
    },
}


def _next_node_id(graph: dict[str, Any]) -> int:
    ids = [node.get("id") for node in graph.get("nodes", []) if isinstance(node.get("id"), int)]
    return max([int(graph.get("last_node_id", 0)), *ids], default=0) + 1


def _next_link_id(graph: dict[str, Any]) -> int:
    ids = [link[0] for link in graph.get("links", []) if isinstance(link, list) and link]
    return max([int(graph.get("last_link_id", 0)), *ids], default=0) + 1


def _link(graph: dict[str, Any], source: int, source_slot: int, target: int, target_slot: int, kind: str) -> int:
    link_id = _next_link_id(graph)
    graph.setdefault("links", []).append([link_id, source, source_slot, target, target_slot, kind])
    graph["last_link_id"] = link_id
    return link_id


def _seconds_node(node_id: int) -> dict[str, Any]:
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
        "widgets_values": [3.0],
        "color": "#4b3475",
        "bgcolor": "#6b4aa0",
    }


def _math_node(node_id: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "ComfyMathExpression",
        "pos": [0, 0],
        "size": [390, 190],
        "flags": {"collapsed": False},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"label": "seconds", "localized_name": "values.a", "name": "values.a", "type": "FLOAT,INT,BOOLEAN", "link": None},
            {"label": "source fps", "localized_name": "values.b", "name": "values.b", "type": "FLOAT,INT,BOOLEAN", "link": None},
            {"localized_name": "expression", "name": "expression", "type": "STRING", "widget": {"name": "expression"}, "link": None},
        ],
        "outputs": [
            {"localized_name": "FLOAT", "name": "FLOAT", "type": "FLOAT", "links": None},
            {"localized_name": "INT", "name": "INT", "type": "INT", "slot_index": 1, "links": []},
            {"localized_name": "BOOL", "name": "BOOL", "type": "BOOLEAN", "links": None},
        ],
        "title": "SECONDS + SOURCE FPS → WAN 4n+1 FRAMES",
        "properties": {
            "Node name for S&R": "ComfyMathExpression",
            "cnr_id": "comfy-core",
            "dawasteh_duration_control": True,
        },
        "widgets_values": ["max(5, round((a * b - 1) / 4) * 4 + 1)"],
        "color": "#704c1c",
        "bgcolor": "#956827",
    }


def _adaptive_image(node: dict[str, Any]) -> None:
    filename = node.get("widgets_values", [""])[0]
    old_links = list(node.get("outputs", [{}])[0].get("links") or [])
    node.update({
        "type": "DaWAdaptiveLoadImage",
        "title": "Adaptive Load Image · Wan Animate 2 · auto",
        "outputs": [
            {"name": "image", "type": "IMAGE", "links": old_links},
            {"name": "mask", "type": "MASK", "links": None},
            {"name": "width", "type": "INT", "links": []},
            {"name": "height", "type": "INT", "links": []},
            {"name": "model_profile", "type": "STRING", "links": None},
            {"name": "info", "type": "STRING", "links": None},
        ],
        "widgets_values": [filename, AUTO_PROFILE, NATIVE_QUALITY, WAN_PROFILE],
    })
    node.setdefault("properties", {})["Node name for S&R"] = "DaWAdaptiveLoadImage"


def _adaptive_video(node: dict[str, Any]) -> None:
    filename = node.get("widgets_values", [""])[0]
    old_links = list(node.get("outputs", [{}])[0].get("links") or [])
    node.update({
        "type": "DaWAdaptiveLoadVideo",
        "title": "Adaptive Load Video · Wan Animate 2 · auto",
        "outputs": [
            {"name": "video", "type": "VIDEO", "links": old_links},
            {"name": "width", "type": "INT", "links": None},
            {"name": "height", "type": "INT", "links": None},
            {"name": "fps", "type": "FLOAT", "links": None},
            {"name": "duration", "type": "FLOAT", "links": None},
            {"name": "model_profile", "type": "STRING", "links": None},
            {"name": "info", "type": "STRING", "links": None},
        ],
        "widgets_values": [filename, AUTO_PROFILE, NATIVE_QUALITY, WAN_PROFILE],
    })
    node.setdefault("properties", {})["Node name for S&R"] = "DaWAdaptiveLoadVideo"


def _update_wan_note(node: dict[str, Any]) -> None:
    values = node.get("widgets_values")
    if not isinstance(values, list) or not values or not isinstance(values[0], str):
        return
    text = values[0]
    text = text.replace(
        "1. **LoadImage** — your character image (background doesn't matter; the output background follows the prompt).\n"
        "2. **LoadVideo** — the driving video (any resolution; keep the character framing similar to the reference image, e.g. full-body to full-body).",
        "1. **Adaptive Load Image** — choose the character image. Auto detects Wan Animate 2; the manual model dropdown remains available.\n"
        "2. **Adaptive Load Video** — choose the driving video. Both loaders scale to a Wan-valid resolution without cropping; use lower quality levels for drafts.",
    )
    start = text.find("## Making longer videos (extending)")
    end = text.find("## Tips", start)
    if start >= 0 and end > start:
        replacement = (
            "## Direct duration in seconds\n\n"
            "Set **OUTPUT DURATION · SECONDS**. The workflow combines that value with the loaded pose video's real FPS and snaps it to Wan's valid `4n+1` frame grid. Context windows are enabled on the active Motion Transfer subgraph, so durations are no longer limited to the old fixed 81-frame widget.\n\n"
            "The second bypassed Motion Transfer subgraph remains available as an expert/manual extension alternative. Enable and chain it only when you deliberately want separate segments.\n\n"
        )
        text = text[:start] + replacement + text[end:]
    text = text.replace(
        "- Frames are taken 1:1 from the video (no fps resampling) — resample to ~16-24 fps if the motion looks too slow.\n",
        "- Duration uses the loaded video's FPS; frames are not temporally resampled. Change the source FPS first if the motion speed itself is wrong.\n"
        "- The adaptive loaders never crop. Matching character framing in reference and pose media still gives the best transfer.\n",
    )
    values[0] = text


def _update_manual_extension_note(node: dict[str, Any]) -> None:
    values = node.get("widgets_values")
    if not isinstance(values, list) or not values or not isinstance(values[0], str):
        return
    values[0] = (
        "Use OUTPUT DURATION · SECONDS for the normal longer-video path; the active Motion Transfer "
        "subgraph uses context windows automatically. The bypassed second subgraph and manual "
        "copy/paste chaining remain optional expert tools when you deliberately want separate segments."
    )


def _mark_note_refresh(by_id: dict[Any, dict[str, Any]]) -> None:
    for node_id in (189, 240, 261, 288, 477):
        node = by_id.get(node_id)
        if node is not None:
            node.setdefault("properties", {})["dawasteh_refresh_generated_note"] = True


def upgrade_workflow(workflow: dict[str, Any], path_key: str) -> tuple[dict[str, Any], bool]:
    upgraded = copy.deepcopy(workflow)
    if path_key != WAN_PATH:
        return upgraded, False
    marker = upgraded.setdefault("extra", {}).get(UPGRADE_KEY, {})
    if marker.get("version") == UPGRADE_VERSION:
        return upgraded, False

    nodes = upgraded.setdefault("nodes", [])
    by_id = {node.get("id"): node for node in nodes}
    if marker.get("version") in (1, 2, 3):
        note = by_id.get(574)
        if note is not None:
            _update_wan_note(note)
        extension_note = by_id.get(539)
        if extension_note is not None:
            _update_manual_extension_note(extension_note)
        _mark_note_refresh(by_id)
        upgraded["extra"][UPGRADE_KEY]["version"] = UPGRADE_VERSION
        return upgraded, True

    image = by_id.get(189)
    video = by_id.get(240)
    first = by_id.get(261)
    second = by_id.get(477)
    components = by_id.get(288)
    if not all((image, video, first, second, components)):
        raise ValueError(f"{path_key}: expected official Wan Animate 2 root nodes are missing")

    note = by_id.get(574)
    if note is not None:
        _update_wan_note(note)
    extension_note = by_id.get(539)
    if extension_note is not None:
        _update_manual_extension_note(extension_note)
    _adaptive_image(image)
    _adaptive_video(video)

    # Drive both subgraphs from the adaptive reference dimensions. This keeps the
    # model's internal resize at exactly the already prepared size and avoids a
    # second crop/resize pass for the normal matching-framing use case.
    for target in (first, second):
        for slot, source_slot, kind in ((14, 2, "INT"), (15, 3, "INT")):
            if target["inputs"][slot].get("link") is not None:
                raise ValueError(f"{path_key}: adaptive size target {target['id']}:{slot} is already linked")
            link_id = _link(upgraded, image["id"], source_slot, target["id"], slot, kind)
            image["outputs"][source_slot]["links"].append(link_id)
            target["inputs"][slot]["link"] = link_id

    seconds_id = _next_node_id(upgraded)
    math_id = seconds_id + 1
    seconds = _seconds_node(seconds_id)
    math_node = _math_node(math_id)
    max_order = max((int(node.get("order", 0)) for node in nodes), default=0)
    seconds["order"] = max_order + 1
    math_node["order"] = max_order + 2

    link_id = _link(upgraded, seconds_id, 0, math_id, 0, "FLOAT")
    seconds["outputs"][0]["links"].append(link_id)
    math_node["inputs"][0]["link"] = link_id

    fps_output = components["outputs"][2]
    link_id = _link(upgraded, components["id"], 2, math_id, 1, "FLOAT")
    fps_output.setdefault("links", []).append(link_id)
    math_node["inputs"][1]["link"] = link_id

    length_slot = len(first.setdefault("inputs", []))
    first["inputs"].append({
        "label": "length · seconds controlled",
        "localized_name": "length",
        "name": "length",
        "type": "INT",
        "widget": {"name": "length"},
        "link": None,
    })
    link_id = _link(upgraded, math_id, 1, first["id"], length_slot, "INT")
    math_node["outputs"][1]["links"].append(link_id)
    first["inputs"][length_slot]["link"] = link_id

    # The official subgraph already contains the context-window implementation.
    # Enable it so durations longer than the old 81-frame default remain bounded.
    if len(first.get("widgets_values", [])) <= 7:
        raise ValueError(f"{path_key}: Wan subgraph widget layout changed")
    first["widgets_values"][7] = True
    _mark_note_refresh(by_id)

    nodes.extend((seconds, math_node))
    upgraded["last_node_id"] = math_id
    upgraded["extra"]["dawasteh_duration_seconds"] = {
        "version": 1,
        "unit": "seconds",
        "mode": "explicit-seconds-dynamic-source-fps",
        "fps": "loaded pose video",
        "frame_alignment": "4n+1",
        "target": f"{first['id']}.length",
        "default_seconds": 3.0,
    }
    upgraded["extra"][UPGRADE_KEY] = {
        "version": UPGRADE_VERSION,
        "release": "v0.9.4",
        "adaptive_loaders": ["DaWAdaptiveLoadImage", "DaWAdaptiveLoadVideo"],
        "no_crop": True,
        "wan_seconds_control": True,
        "context_windows_enabled": True,
    }
    return upgraded, True
