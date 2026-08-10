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

MODEL_DEVICE = "gpu:0"
HELPER_DEVICE = "gpu:1"


@dataclass(frozen=True)
class Family:
    name: str
    source: str
    output: str
    h3_director: bool = False


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


def _new_link(template: Any, link_id: int, source_id: Any, source_slot: int, target_id: int, link_type: str) -> Any:
    if isinstance(template, dict):
        return {
            "id": link_id,
            "origin_id": source_id,
            "origin_slot": source_slot,
            "target_id": target_id,
            "target_slot": 0,
            "type": link_type,
        }
    return [link_id, source_id, source_slot, target_id, 0, link_type]


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


def _dual_gpu_metadata(family: Family) -> dict[str, Any]:
    return {
        "version": 1,
        "family": family.name,
        "source": f"workflows/{family.source}",
        "server": "127.0.0.1:8188",
        "backend": "ROCm/HIP",
        "model_device": "gpu:0 · AMD Radeon AI PRO R9700 32 GB",
        "clip_vae_device": "gpu:1 · AMD Radeon RX 9070 XT 16 GB",
        "execution": "device placement; ComfyUI still executes graph stages sequentially",
    }


def build_family(family: Family) -> dict[str, Any]:
    source = WORKFLOWS / family.source
    workflow = json.loads(source.read_text(encoding="utf-8-sig"))
    workflow = copy.deepcopy(workflow)
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
        refresh_refinement(workflow)
        return workflow

    inserted = sum(insert_device_selectors(graph) for graph in _graphs(workflow))
    if inserted == 0:
        raise ValueError(f"No compatible MODEL/CLIP/VAE loader outputs found in {source}")
    extra["dawasteh_dual_gpu"]["selector_count"] = inserted
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
