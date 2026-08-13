#!/usr/bin/env python3
"""Generate curated ComfyUI dual-GPU workflows for supported model families.

The generated workflows target the Windows ROCm/HIP order used on Pandaking:

* gpu:0 = AMD Radeon AI PRO R9700 (diffusion/model work)
* gpu:1 = AMD Radeon RX 9070 XT (CLIP/text encoders and VAEs)

Only ComfyUI MODEL, CLIP, and VAE loader outputs are retargeted. Custom model
objects such as YuE, HeartMuLa, MOSS-TTS, and Qwen-TTS are intentionally out of
scope because ComfyUI's official Select * Device nodes do not accept them.
"""
from __future__ import annotations

import argparse
import copy
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from tools.refine_workflows import NOTE_PROPERTY, REFINEMENT_KEY, refine_workflow
except ModuleNotFoundError:  # Direct execution: python tools/generate_dual_gpu_workflows.py
    from refine_workflows import NOTE_PROPERTY, REFINEMENT_KEY, refine_workflow

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
DEFAULT_DESTINATION = WORKFLOWS / "Dual GPU - R9700 + RX 9070 XT"
WORKFLOW_TEMPLATES = ROOT / "tools" / "workflow_templates"

MODEL_DEVICE = "gpu:0"
HELPER_DEVICE = "gpu:1"


@dataclass(frozen=True)
class Family:
    name: str
    source: str
    output: str
    h3_director: bool = False
    template: str | None = None


FAMILIES = (
    Family("SD 1.5", "Text to Image/SD15_v1-5-pruned-emaonly-Text-to-Image.json", "SD15-DualGPU-Text-to-Image.json"),
    Family("SD 2.1", "Text to Image/SD21_wd-1-5-beta2-unclip-Text-to-Image.json", "SD21-DualGPU-Text-to-Image.json"),
    Family("SDXL", "Text to Image/SDXL_RealVisXL_V4-Text-to-Image.json", "SDXL-DualGPU-Text-to-Image.json"),
    Family("Anima", "Text to Image/Anima_base_v1-Text-to-Image.json", "Anima-DualGPU-Text-to-Image.json"),
    Family("Boogu", "Text to Image/Boogu_image_base-Text-to-Image.json", "Boogu-DualGPU-Text-to-Image.json"),
    Family("FLUX.1", "Text to Image/FLUX1_dev_fp8-Text-to-Image.json", "FLUX1-DualGPU-Text-to-Image.json"),
    Family("FLUX.2", "Text to Image/FLUX2_dev_fp8mixed-Text-to-Image.json", "FLUX2-DualGPU-Text-to-Image.json"),
    Family("FLUX.2 Klein", "Text to Image/FLUX2_Klein_4b-Text-to-Image.json", "FLUX2-Klein-DualGPU-Text-to-Image.json"),
    Family("Ideogram 4", "Text to Image/Ideogram4-Text-to-Image.json", "Ideogram4-DualGPU-Text-to-Image.json"),
    Family("Krea 2", "Text to Image/Krea2_raw-Text-to-Image.json", "Krea2-DualGPU-Text-to-Image.json"),
    Family("LongCat Image", "Text to Image/LongCat_image-Text-to-Image.json", "LongCat-Image-DualGPU-Text-to-Image.json"),
    Family("Z-Image", "Text to Image/ZImage_turbo-Text-to-Image.json", "ZImage-DualGPU-Text-to-Image.json"),
    Family("Qwen Image Edit", "Image Editing/Qwen_Image_Edit_2509-Image-Edit.json", "Qwen-Image-Edit-DualGPU.json"),
    Family("SCAIL 2", "Character Animation/SCAIL2-Character-Animation.json", "SCAIL2-DualGPU-Character-Animation.json"),
    Family("Bernini-R", "Image Editing/Bernini_R-Image-Edit.json", "Bernini-R-DualGPU-Image-Edit.json"),
    Family("WAN 2.2", "Text to Video/WAN22_14B_fp8_lightx2v-Text-to-Video.json", "WAN22-DualGPU-Text-to-Video.json"),
    Family("LTX 2.3", "Text to Video/LTX23_dev_mxfp8-Text-to-Video.json", "LTX23-DualGPU-Text-to-Video.json"),
    Family("LTX 2.5 Text to Video", "", "LTX25-DualGPU-Text-to-Video.json", template="video_ltx2_5_t2v.json"),
    Family("LTX 2.5 Image to Video", "", "LTX25-DualGPU-Image-to-Video.json", template="video_ltx2_5_i2v.json"),
    Family("LTX 2.5 FLF2V", "", "LTX25-DualGPU-FLF2V.json", template="video_ltx2_5_flf2v.json"),
    Family("Wan Animate 2 Motion Transfer", "", "Wan-Animate-2-DualGPU-Motion-Transfer.json", template="video_wan_animate2.json"),
    Family("Kandinsky 5", "Text+Image to Video/Kandinsky5_Lite-Text+Image-to-Video.json", "Kandinsky5-DualGPU-Text+Image-to-Video.json"),
    Family("ACE-Step 1.5", "Music Generation/ACE-Step1_5_Turbo_4B-Music-Generation.json", "ACE-Step1_5-DualGPU-Music-Generation.json"),
    Family("Stable Audio 3", "Music Generation/StableAudio3_Medium-Audio-Generation.json", "StableAudio3-DualGPU-Audio-Generation.json"),
    Family(
        "MiniMax H3",
        "Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json",
        "MiniMax-H3-DualGPU-Complete-Song-Music-Video-One-Click.json",
        h3_director=True,
    ),
    Family(
        "MiniMax H3 FL2VA · open inputs",
        "Reference to Video/MiniMax_H3_Spectrum_FL2VA_All_Supported_Inputs.json",
        "MiniMax-H3-FL2VA-DualGPU-All-Supported-Inputs.json",
    ),
    Family(
        "MiniMax H3 Ref2VA · open references",
        "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_All_Reference_Inputs.json",
        "MiniMax-H3-Ref2VA-DualGPU-All-Reference-Inputs.json",
    ),
)

# A selector is inserted only immediately after a known base loader. Model
# modifiers (LoRA, sampling patches, switches, reroutes) must stay downstream.
BASE_LOADER_TYPES = {
    "CheckpointLoader",
    "CheckpointLoaderSimple",
    "CLIPLoader",
    "DualCLIPLoader",
    "TripleCLIPLoader",
    "LTXAVTextEncoderLoader",
    "LTXVAudioVAELoader",
    "UNETLoader",
    "VAELoader",
}
SELECTOR = {
    "MODEL": ("SelectModelDevice", "Select Model Device", "model", MODEL_DEVICE),
    "CLIP": ("SelectCLIPDevice", "Select CLIP Device", "clip", HELPER_DEVICE),
    "VAE": ("SelectVAEDevice", "Select VAE Device", "vae", HELPER_DEVICE),
}
DEVICE_CONTROL_TYPE = "DaWMultiGPUDeviceControl"
CONTROL_ROLES = {
    "model_device": (0, "gpu:0", "SelectModelDevice"),
    "clip_device": (1, "gpu:1", "SelectCLIPDevice"),
    "vae_device": (2, "gpu:1", "SelectVAEDevice"),
}

SELECTOR_OBJECT_INFO = {
    "SelectModelDevice": {
        "display_name": "Select Model Device",
        "description": "Platziert das Diffusionsmodell auf einem bestimmten ComfyUI-GPU-Gerät.",
        "input": {"required": {"model": ["MODEL", {}], "device": [["default", "cpu", "gpu:0", "gpu:1"], {}]}},
        "input_order": {"required": ["model", "device"]},
        "output_name": ["MODEL"],
        "output": ["MODEL"],
    },
    "SelectCLIPDevice": {
        "display_name": "Select CLIP Device",
        "description": "Platziert den CLIP- oder Textencoder auf einem bestimmten ComfyUI-GPU-Gerät.",
        "input": {"required": {"clip": ["CLIP", {}], "device": [["default", "cpu", "gpu:0", "gpu:1"], {}]}},
        "input_order": {"required": ["clip", "device"]},
        "output_name": ["CLIP"],
        "output": ["CLIP"],
    },
    "SelectVAEDevice": {
        "display_name": "Select VAE Device",
        "description": "Platziert den Bild-, Video- oder Audio-VAE auf einem bestimmten ComfyUI-GPU-Gerät.",
        "input": {"required": {"vae": ["VAE", {}], "device": [["default", "gpu:0", "gpu:1"], {}]}},
        "input_order": {"required": ["vae", "device"]},
        "output_name": ["VAE"],
        "output": ["VAE"],
    },
    DEVICE_CONTROL_TYPE: {
        "display_name": "DaW Multi-GPU Device Control",
        "description": "Zentrale Dropdowns für die MODEL-, CLIP- und VAE-Geräte aller verbundenen offiziellen Selector-Nodes.",
        "input": {"required": {
            "model_device": [["default", "cpu", "gpu:0", "gpu:1"], {}],
            "clip_device": [["default", "cpu", "gpu:0", "gpu:1"], {}],
            "vae_device": [["default", "gpu:0", "gpu:1"], {}],
        }},
        "input_order": {"required": ["model_device", "clip_device", "vae_device"]},
        "output_name": ["model_device", "clip_device", "vae_device"],
        "output": ["COMBO", "COMBO", "COMBO"],
    },
}


def _graphs(workflow: dict[str, Any]):
    yield workflow
    for graph in workflow.get("definitions", {}).get("subgraphs", []):
        yield graph
        yield from _nested_graphs(graph)


def _nested_graphs(graph: dict[str, Any]):
    for child in graph.get("definitions", {}).get("subgraphs", []):
        yield child
        yield from _nested_graphs(child)


def _next_node_id(graph: dict[str, Any]) -> int:
    numeric = [node.get("id") for node in graph.get("nodes", []) if isinstance(node.get("id"), int)]
    state = graph.get("state", {})
    return max([int(state.get("lastNodeId", 0)), *numeric], default=0) + 1


def _next_link_id(graph: dict[str, Any]) -> int:
    ids: list[int] = []
    for link in graph.get("links", []):
        value = link[0] if isinstance(link, list) and link else link.get("id") if isinstance(link, dict) else None
        if isinstance(value, int):
            ids.append(value)
    state = graph.get("state", {})
    return max([int(state.get("lastLinkId", 0)), *ids], default=0) + 1


def _set_last_ids(graph: dict[str, Any], node_id: int, link_id: int) -> None:
    if "state" in graph:
        graph["state"]["lastNodeId"] = max(int(graph["state"].get("lastNodeId", 0)), node_id)
        graph["state"]["lastLinkId"] = max(int(graph["state"].get("lastLinkId", 0)), link_id)
    else:
        graph["last_node_id"] = max(int(graph.get("last_node_id", 0)), node_id)
        graph["last_link_id"] = max(int(graph.get("last_link_id", 0)), link_id)


def _redirect_origin(link: Any, node_id: int) -> None:
    if isinstance(link, list):
        link[1] = node_id
        link[2] = 0
    else:
        link["origin_id"] = node_id
        link["origin_slot"] = 0


def _new_link(template: Any, link_id: int, source_id: Any, source_slot: int, target_id: Any, link_type: str, target_slot: int = 0) -> Any:
    if isinstance(template, dict):
        return {
            "id": link_id,
            "origin_id": source_id,
            "origin_slot": source_slot,
            "target_id": target_id,
            "target_slot": target_slot,
            "type": link_type,
        }
    return [link_id, source_id, source_slot, target_id, target_slot, link_type]


def _selector_node(node_id: int, node_type: str, display_name: str, input_name: str, value: str,
                   link_id: int, output_links: list[int], pos: list[float], order: int, link_type: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "pos": pos,
        "size": [300, 82],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [{
            "localized_name": input_name,
            "name": input_name,
            "type": link_type,
            "link": link_id,
        }],
        "outputs": [{
            "localized_name": link_type,
            "name": link_type,
            "type": link_type,
            "slot_index": 0,
            "links": output_links,
        }],
        "properties": {
            "Node name for S&R": node_type,
            "cnr_id": "comfy-core",
        },
        "widgets_values": [value],
        "title": f"{display_name} · {value}",
        "color": "#16334a" if link_type == "MODEL" else "#3b2d18",
        "bgcolor": "#1d4968" if link_type == "MODEL" else "#5a4322",
    }


def insert_device_selectors(graph: dict[str, Any]) -> int:
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    if not nodes or not links:
        return 0
    by_link: dict[Any, Any] = {}
    for link in links:
        key = link[0] if isinstance(link, list) else link.get("id")
        by_link[key] = link

    candidates: list[tuple[dict[str, Any], int, dict[str, Any], list[int]]] = []
    for node in list(nodes):
        if node.get("type") not in BASE_LOADER_TYPES:
            continue
        for slot, output in enumerate(node.get("outputs", [])):
            link_type = output.get("type")
            output_links = [value for value in (output.get("links") or []) if value in by_link]
            if link_type in SELECTOR and output_links:
                candidates.append((node, slot, output, output_links))

    if not candidates:
        return 0

    min_x = min(float((node.get("pos") or [0, 0])[0]) for node in nodes)
    min_y = min(float((node.get("pos") or [0, 0, 0])[1]) for node in nodes)
    next_node = _next_node_id(graph)
    next_link = _next_link_id(graph)
    max_order = max((int(node.get("order", 0)) for node in nodes), default=0)
    template = links[0]

    for index, (source, source_slot, output, old_link_ids) in enumerate(candidates):
        link_type = output["type"]
        node_type, display_name, input_name, value = SELECTOR[link_type]
        node_id = next_node
        link_id = next_link
        next_node += 1
        next_link += 1
        for old_id in old_link_ids:
            _redirect_origin(by_link[old_id], node_id)
        output["links"] = [link_id]
        pos = [min_x + index * 330.0, min_y - 150.0]
        nodes.append(_selector_node(
            node_id, node_type, display_name, input_name, value, link_id,
            old_link_ids, pos, max_order + index + 1, link_type,
        ))
        new_link = _new_link(template, link_id, source["id"], source_slot, node_id, link_type)
        links.append(new_link)
        by_link[link_id] = new_link

    _set_last_ids(graph, next_node - 1, next_link - 1)
    return len(candidates)


def _device_role_for_selector(node_type: str) -> str | None:
    for role, (_, _, selector_type) in CONTROL_ROLES.items():
        if node_type == selector_type:
            return role
    return None


def _graph_needs_control(graph: dict[str, Any]) -> bool:
    if any(_device_role_for_selector(node.get("type", "")) for node in graph.get("nodes", [])):
        return True
    return any(_graph_needs_control(child) for child in graph.get("definitions", {}).get("subgraphs", []))


def _update_last_link(graph: dict[str, Any], link_id: int) -> None:
    if "state" in graph:
        graph["state"]["lastLinkId"] = max(int(graph["state"].get("lastLinkId", 0)), link_id)
    else:
        graph["last_link_id"] = max(int(graph.get("last_link_id", 0)), link_id)


def _append_control_link(
    graph: dict[str, Any], source_id: Any, source_slot: int, source_links: list[int],
    target: dict[str, Any], input_name: str,
) -> int:
    target_slot = len(target.setdefault("inputs", []))
    link_id = _next_link_id(graph)
    target["inputs"].append({
        "localized_name": input_name,
        "name": input_name,
        "type": "COMBO",
        "widget": {"name": input_name},
        "link": link_id,
    })
    template: Any = graph.get("links", [])[0] if graph.get("links") else ({} if "state" in graph else [])
    graph.setdefault("links", []).append(
        _new_link(template, link_id, source_id, source_slot, target["id"], "COMBO", target_slot)
    )
    source_links.append(link_id)
    _update_last_link(graph, link_id)
    return link_id


def _wire_selectors(
    graph: dict[str, Any], source_id: Any, source_slots: dict[str, int], source_link_lists: dict[str, list[int]],
) -> None:
    for node in graph.get("nodes", []):
        role = _device_role_for_selector(node.get("type", ""))
        if role is None:
            continue
        if any(item.get("name") == "device" for item in node.get("inputs", [])):
            raise ValueError(f"Selector {node.get('id')} already has a connected device input")
        _append_control_link(graph, source_id, source_slots[role], source_link_lists[role], node, "device")
        node["title"] = f"{node.get('type', 'Select Device')} · central control"


def _prepare_subgraph_control(graph: dict[str, Any], workflow_key: str) -> dict[str, int]:
    existing = {item.get("name"): index for index, item in enumerate(graph.get("inputs", []))}
    source_slots: dict[str, int] = {}
    source_link_lists: dict[str, list[int]] = {}
    input_node = graph.get("inputNode")
    if not isinstance(input_node, dict) or "id" not in input_node:
        raise ValueError(f"Subgraph {graph.get('id')} has no inputNode for central GPU control")

    base_y = float((input_node.get("bounding") or [0, 0, 0, 0])[1])
    for offset, (role, (_, default, _)) in enumerate(CONTROL_ROLES.items()):
        name = f"daw_{role}"
        if name in existing:
            index = existing[name]
            item = graph["inputs"][index]
        else:
            index = len(graph.setdefault("inputs", []))
            item = {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{workflow_key}:{graph.get('id')}:{name}")),
                "name": name,
                "type": "COMBO",
                "linkIds": [],
                "label": f"DaW {role.replace('_', ' ')}",
                "pos": [float((input_node.get("bounding") or [0, 0])[0]) + 130.0, base_y + index * 20.0],
                "default": default,
            }
            graph["inputs"].append(item)
        source_slots[role] = index
        source_link_lists[role] = item.setdefault("linkIds", [])

    bounding = input_node.get("bounding")
    if isinstance(bounding, list) and len(bounding) >= 4:
        bounding[3] = max(float(bounding[3]), 40.0 + len(graph.get("inputs", [])) * 20.0)

    _wire_selectors(graph, input_node["id"], source_slots, source_link_lists)
    for child in graph.get("definitions", {}).get("subgraphs", []):
        if not _graph_needs_control(child):
            continue
        _prepare_subgraph_control(child, workflow_key)
        for instance in [node for node in graph.get("nodes", []) if node.get("type") == child.get("id")]:
            _wire_subgraph_instance(graph, instance, input_node["id"], source_slots, source_link_lists)
    return source_slots


def _wire_subgraph_instance(
    graph: dict[str, Any], instance: dict[str, Any], source_id: Any, source_slots: dict[str, int],
    source_link_lists: dict[str, list[int]],
) -> None:
    for role, (_, default, _) in CONTROL_ROLES.items():
        _append_control_link(
            graph, source_id, source_slots[role], source_link_lists[role], instance, f"daw_{role}",
        )
        instance.setdefault("widgets_values", []).append(default)
    if isinstance(instance.get("size"), list) and len(instance["size"]) >= 2:
        instance["size"][1] = float(instance["size"][1]) + 60.0


def _timer_node(node_id: int, pos: list[float], order: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "PixaromaRunTimer",
        "pos": pos,
        "size": [226, 136],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "properties": {"Node name for S&R": "PixaromaRunTimer", "cnr_id": "ComfyUI-Pixaroma"},
        "widgets_values": [{"version": 1, "color": "#f66744", "decimals": 0, "chime": True, "sound": "", "volume": 70}],
        "color": "#1d1d1d",
        "bgcolor": "#2a2a2a",
    }


def install_run_timer(workflow: dict[str, Any]) -> None:
    if any(node.get("type") == "PixaromaRunTimer" for node in workflow.get("nodes", [])):
        return
    nodes = workflow.setdefault("nodes", [])
    node_id = _next_node_id(workflow)
    min_x = min((float((node.get("pos") or [0, 0])[0]) for node in nodes), default=0.0)
    max_y = max((float((node.get("pos") or [0, 0])[1]) + float((node.get("size") or [0, 0])[1]) for node in nodes), default=0.0)
    nodes.append(_timer_node(node_id, [min_x, max_y + 120.0], max((int(node.get("order", 0)) for node in nodes), default=0) + 1))
    _set_last_ids(workflow, node_id, int(workflow.get("last_link_id", 0)))


def _control_node(node_id: int, pos: list[float], order: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": DEVICE_CONTROL_TYPE,
        "pos": pos,
        "size": [380, 170],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [],
        "outputs": [
            {"localized_name": role, "name": role, "type": "COMBO", "slot_index": slot, "links": []}
            for role, (slot, _, _) in CONTROL_ROLES.items()
        ],
        "properties": {"Node name for S&R": DEVICE_CONTROL_TYPE},
        "widgets_values": [default for _, default, _ in CONTROL_ROLES.values()],
        "title": "Central GPU Control · MODEL / CLIP / VAE",
        "color": "#173f32",
        "bgcolor": "#205845",
    }


def install_central_device_control(workflow: dict[str, Any], workflow_key: str, h3_director: bool) -> None:
    root = workflow
    nodes = root.get("nodes", [])
    if any(node.get("type") == DEVICE_CONTROL_TYPE for node in nodes):
        raise ValueError("Workflow already contains a central GPU control node")
    node_id = _next_node_id(root)
    min_x = min((float((node.get("pos") or [0, 0])[0]) for node in nodes), default=0.0)
    min_y = min((float((node.get("pos") or [0, 0])[1]) for node in nodes), default=0.0)
    control = _control_node(node_id, [min_x - 480.0, min_y], max((int(node.get("order", 0)) for node in nodes), default=0) + 1)
    nodes.append(control)
    _set_last_ids(root, node_id, int(root.get("last_link_id", 0)))
    source_slots = {role: slot for role, (slot, _, _) in CONTROL_ROLES.items()}
    source_link_lists = {role: control["outputs"][slot]["links"] for role, slot in source_slots.items()}
    _wire_selectors(root, node_id, source_slots, source_link_lists)

    for child in root.get("definitions", {}).get("subgraphs", []):
        if not _graph_needs_control(child):
            continue
        _prepare_subgraph_control(child, workflow_key)
        for instance in [node for node in root.get("nodes", []) if node.get("type") == child.get("id")]:
            for role, (_, default, _) in CONTROL_ROLES.items():
                _append_control_link(root, node_id, source_slots[role], source_link_lists[role], instance, f"daw_{role}")
                instance.setdefault("widgets_values", []).append(default)
            if isinstance(instance.get("size"), list) and len(instance["size"]) >= 2:
                instance["size"][1] = float(instance["size"][1]) + 60.0

    if h3_director:
        director = next(node for node in root.get("nodes", []) if node.get("type") == "DaWH3MusicVideoDirectorDualGPU")
        for role, (_, default, _) in CONTROL_ROLES.items():
            _append_control_link(root, node_id, source_slots[role], source_link_lists[role], director, role)
            director.setdefault("widgets_values", []).append(default)

    if not all(source_link_lists[role] for role in CONTROL_ROLES):
        raise ValueError("Central GPU control has an unconnected device output")
    workflow.setdefault("extra", {}).setdefault("dawasteh_dual_gpu", {}).update({
        "central_control": DEVICE_CONTROL_TYPE,
        "manual_device_dropdowns": {role: default for role, (_, default, _) in CONTROL_ROLES.items()},
    })


def refresh_refinement(workflow: dict[str, Any]) -> None:
    """Rebuild generated notes/layout so copied workflows remain validator-clean."""
    for graph in _graphs(workflow):
        graph["nodes"] = [
            node for node in graph.get("nodes", [])
            if not node.get("properties", {}).get("dawasteh_generated_note")
            and node.get("properties", {}).get(NOTE_PROPERTY) is None
        ]
        graph.setdefault("extra", {}).pop(REFINEMENT_KEY, None)
    refine_workflow(workflow, SELECTOR_OBJECT_INFO)
    for graph in _graphs(workflow):
        numeric_ids = [node["id"] for node in graph.get("nodes", []) if isinstance(node.get("id"), int)]
        maximum = max(numeric_ids, default=0)
        graph["last_node_id"] = max(int(graph.get("last_node_id", 0)), maximum)
        if "state" in graph:
            graph["state"]["lastNodeId"] = max(int(graph["state"].get("lastNodeId", 0)), maximum)


def _workflow_template_path(template: str) -> Path:
    path = WORKFLOW_TEMPLATES / template
    if not path.is_file():
        raise FileNotFoundError(f"Pinned official ComfyUI workflow template is missing: {path}")
    return path


def _localize_model_paths(workflow: dict[str, Any]) -> None:
    replacements = {
        "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors": r"LTX\ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
        "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors": r"LTX\gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
        "ltx-2.5-video-vae-bf16.safetensors": r"LTX\ltx-2.5-video-vae-bf16.safetensors",
        "ltx-2.5-audio-vae-bf16.safetensors": r"LTX\ltx-2.5-audio-vae-bf16.safetensors",
        "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors": r"LTX\ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
        "gemma4_e2b_it_bf16.safetensors": r"Gemma\gemma4_e2b_it_bf16.safetensors",
        "wan_animate_2_int8_convrot.safetensors": r"WAN\wan_animate_2_int8_convrot.safetensors",
        "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors": r"WAN\lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors": r"UMT5\umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "Wan2_1_VAE_bf16.safetensors": r"WAN\Wan2_1_VAE_bf16.safetensors",
    }
    model_directories = {
        "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors": "diffusion_models/LTX",
        "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors": "text_encoders/LTX",
        "ltx-2.5-video-vae-bf16.safetensors": "vae/LTX",
        "ltx-2.5-audio-vae-bf16.safetensors": "vae/LTX",
        "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors": "latent_upscale_models/LTX",
        "gemma4_e2b_it_bf16.safetensors": "text_encoders/Gemma",
        "wan_animate_2_int8_convrot.safetensors": "diffusion_models/WAN",
        "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors": "loras/WAN",
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors": "text_encoders/UMT5",
        "Wan2_1_VAE_bf16.safetensors": "vae/WAN",
    }
    wan_animate = any(
        node.get("type") == "WanAnimate2Cache"
        for graph in _graphs(workflow)
        for node in graph.get("nodes", [])
    )
    for graph in _graphs(workflow):
        for node in graph.get("nodes", []):
            values = node.get("widgets_values")
            if isinstance(values, list):
                node["widgets_values"] = [replacements.get(value, value) for value in values]
                if wan_animate:
                    node["widgets_values"] = ["cpu" if value == "gpu" else value for value in node["widgets_values"]]
            for model in node.get("properties", {}).get("models", []) or []:
                if isinstance(model, dict) and model.get("name") in model_directories:
                    model["directory"] = model_directories[model["name"]]


def _dual_gpu_metadata(family: Family) -> dict[str, Any]:
    source = (
        f"comfyui-workflow-templates-json:{family.template}"
        if family.template else f"workflows/{family.source}"
    )
    return {
        "version": 2,
        "family": family.name,
        "source": source,
        "server": "127.0.0.1:8188",
        "backend": "ROCm/HIP",
        "default_model_device": "gpu:0 · AMD Radeon AI PRO R9700 32 GB",
        "default_clip_vae_device": "gpu:1 · AMD Radeon RX 9070 XT 16 GB",
        "execution": "device placement; ComfyUI still executes graph stages sequentially",
    }


def build_family(family: Family) -> dict[str, Any]:
    source = _workflow_template_path(family.template) if family.template else WORKFLOWS / family.source
    workflow = json.loads(source.read_text(encoding="utf-8-sig"))
    workflow = copy.deepcopy(workflow)
    if family.template:
        _localize_model_paths(workflow)
        install_run_timer(workflow)
    workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dawasteh-dual-gpu:{family.output}"))
    workflow["revision"] = 0
    extra = workflow.setdefault("extra", {})
    extra["dawasteh_dual_gpu"] = _dual_gpu_metadata(family)

    if family.h3_director:
        directors = [node for node in workflow.get("nodes", []) if node.get("type") == "DaWH3MusicVideoDirector"]
        if len(directors) != 1:
            raise ValueError(f"Expected one H3 Director in {source}, found {len(directors)}")
        director = directors[0]
        director["type"] = "DaWH3MusicVideoDirectorDualGPU"
        director["title"] = "H3 Complete-Song Director · Dual GPU · 8188"
        director.setdefault("properties", {})["Node name for S&R"] = "DaWH3MusicVideoDirectorDualGPU"
        install_central_device_control(workflow, family.output, h3_director=True)
        refresh_refinement(workflow)
        return workflow

    inserted = sum(insert_device_selectors(graph) for graph in _graphs(workflow))
    if inserted == 0:
        raise ValueError(f"No compatible MODEL/CLIP/VAE loader outputs found in {source}")
    extra["dawasteh_dual_gpu"]["selector_count"] = inserted
    install_central_device_control(workflow, family.output, h3_director=False)
    refresh_refinement(workflow)
    return workflow


def generate(destination: Path = DEFAULT_DESTINATION) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    expected = {family.output for family in FAMILIES}
    for stale in destination.glob("*.json"):
        if stale.name not in expected:
            stale.unlink()
    written: list[Path] = []
    for family in FAMILIES:
        path = destination / family.output
        path.write_text(json.dumps(build_family(family), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    paths = generate(args.destination)
    print(f"Generated {len(paths)} dual-GPU workflows in {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
