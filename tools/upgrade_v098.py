#!/usr/bin/env python3
"""Deterministic v0.9.8 upgrade: replace removed ``comfyui-image-saver`` helpers.

Three SDXL image-editing workflows carried two helper nodes from the third-party
``comfyui-image-saver`` pack: ``String Literal (Image Saver)`` provided a prompt
string and ``Seed Generator (Image Saver)`` provided a shared seed.  That pack is
no longer installed on the reference system, so the current ComfyUI 0.34 backend
rejects those graphs.  ComfyUI-Core ships equivalent primitives:

* ``PrimitiveStringMultiline`` → ``STRING`` output, one multiline ``value`` widget
* ``PrimitiveInt`` → ``INT`` output, ``value`` widget plus ``control_after_generate``

The upgrade keeps node ids, positions, output links and the authored values, so
the graphs stay byte-for-byte reproducible from the v0.9.7 release.
"""
from __future__ import annotations

import copy
from typing import Any


UPGRADE_KEY = "dawasteh_v098_core_primitives"
UPGRADE_VERSION = 1
REMOVED_PACK = "comfyui-image-saver"

REPLACEMENTS: dict[str, dict[str, Any]] = {
    "String Literal (Image Saver)": {"type": "PrimitiveStringMultiline", "input": ("value", "STRING")},
    "Seed Generator (Image Saver)": {"type": "PrimitiveInt", "input": ("value", "INT")},
}

TARGET_PATHS: frozenset[str] = frozenset({
    "Image Editing/SDXL_Illustrious-Super-Composite.json",
    "NSFW/SDXL_AniToReal_v1-Image-to-Image.json",
    "NSFW/SDXL_AniToReal_v2-Image-to-Image.json",
})


def _replace_node(node: dict[str, Any]) -> dict[str, Any]:
    spec = REPLACEMENTS[node["type"]]
    original_type = node["type"]
    input_name, input_type = spec["input"]
    node["type"] = spec["type"]
    node["inputs"] = [{
        "localized_name": input_name,
        "name": input_name,
        "type": input_type,
        "widget": {"name": input_name},
        "link": None,
    }]
    values = list(node.get("widgets_values") or [])
    if spec["type"] == "PrimitiveInt":
        seed = int(values[0]) if values and isinstance(values[0], (int, float)) else 0
        control = values[1] if len(values) > 1 and isinstance(values[1], str) else "randomize"
        node["widgets_values"] = [seed, control]
    else:
        node["widgets_values"] = [str(values[0]) if values else ""]
    node["properties"] = {
        "Node name for S&R": spec["type"],
        "cnr_id": "comfy-core",
        "ver": "0.34.0",
        "dawasteh_refresh_generated_note": True,
    }
    return {"id": node.get("id"), "from": original_type, "to": spec["type"]}


def upgrade_workflow(workflow: dict[str, Any], path_key: str) -> tuple[dict[str, Any], bool]:
    """Replace the removed image-saver helpers in the three affected workflows."""
    upgraded = copy.deepcopy(workflow)
    if path_key not in TARGET_PATHS:
        return upgraded, False
    marker = upgraded.get("extra", {}).get(UPGRADE_KEY, {})
    if marker.get("version") == UPGRADE_VERSION:
        return upgraded, False
    replaced = [
        _replace_node(node)
        for node in upgraded.get("nodes", [])
        if node.get("type") in REPLACEMENTS
    ]
    if not replaced:
        raise ValueError(f"{path_key}: expected at least one {REMOVED_PACK} helper node to replace")
    upgraded.setdefault("extra", {})[UPGRADE_KEY] = {
        "version": UPGRADE_VERSION,
        "release": "v0.9.8",
        "removed_pack": REMOVED_PACK,
        "replaced": replaced,
    }
    return upgraded, True
