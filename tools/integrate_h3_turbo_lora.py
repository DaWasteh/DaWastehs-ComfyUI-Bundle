#!/usr/bin/env python3
"""Integrate the recommended MiniMax H3 Turbo LoRA into every H3 workflow."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
H3_DIR = ROOT / "workflows" / "Reference to Video"
LORA_NAME = r"MiniMax H3\minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
LORA_SOURCE = "drbaph/MiniMax-H3-Turbo-Lora-ComfyUI"
LORA_SHA256 = "7098acf3ee75028fd9fcd948f50fcc8d995057fabb76f86bd3ca2c0ffc58e409"
VISIBLE_WORKFLOWS = (
    "MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json",
    "MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json",
    "MiniMax_H3_Spectrum_Ref2VA_Picture_and_Video_to_Video_LOCAL.json",
    "MiniMax_H3_Spectrum_RefImage_Audio_to_Video_OriginalAudio_AutoLength.json",
    "MiniMax_H3_Spectrum_RefImage_RefVideo_to_Video_Audio_AutoLength.json",
)
DIRECTOR_WORKFLOW = "MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json"


def _link_id(link: Any) -> Any:
    return link[0] if isinstance(link, list) else link.get("id")


def _origin(link: Any) -> tuple[Any, int]:
    if isinstance(link, list):
        return link[1], int(link[2])
    return link.get("origin_id"), int(link.get("origin_slot", 0))


def _set_origin(link: Any, node_id: int) -> None:
    if isinstance(link, list):
        link[1], link[2] = node_id, 0
    else:
        link["origin_id"], link["origin_slot"] = node_id, 0


def _new_link(template: Any, link_id: int, source_id: int, source_slot: int, target_id: int) -> Any:
    if isinstance(template, dict):
        return {"id": link_id, "origin_id": source_id, "origin_slot": source_slot,
                "target_id": target_id, "target_slot": 0, "type": "MODEL"}
    return [link_id, source_id, source_slot, target_id, 0, "MODEL"]


def _note(node_id: int, target_id: int, pos: list[float], order: int) -> dict[str, Any]:
    text = f"""# Erklärung · MiniMax H3 Turbo LoRA · Node {target_id}

**Zweck:** Lädt die empfohlene v4-Step-600-EMA-Turbo-LoRA für die pruned/curve-form MiniMax-H3-ComfyUI-Modelle und reduziert die Sampling-Konfiguration auf acht qualitätsorientierte Schritte.

**Einstellbare Werte**
- `lora_name` = `{LORA_NAME}` — Kompatibilitätskonvertierung aus `{LORA_SOURCE}`.
- `strength_model` = `1.0` — Empfohlener Ausgangswert des Autors; niedrigere Werte schwächen, höhere Werte verstärken den Turbo-Effekt.

**Abgestimmte Samplingwerte**
- 8 Schritte, Euler-Sampler, Beta-Scheduler
- Video-Sigma-Shift 12, Audio-Sigma-Shift 4

**Eingänge**
- `model`: MiniMax-H3-Diffusionsmodell vom UNET-Loader.

**Ausgänge**
- `MODEL`: Mit der Turbo-LoRA gepatchtes Modell für Sigma-Shift, Spectrum und Sampling.
"""
    return {
        "id": node_id, "type": "MarkdownNote", "pos": pos, "size": [560, 430],
        "flags": {}, "order": order, "mode": 0, "inputs": [], "outputs": [],
        "title": f"Erklärung · MiniMax H3 Turbo LoRA · Node {target_id}",
        "properties": {
            "Node name for S&R": "MarkdownNote", "cnr_id": "comfy-core",
            "dawasteh_note_for": target_id, "dawasteh_generated_note": True,
        },
        "widgets_values": [text], "color": "#1b2638", "bgcolor": "#101722",
    }


def _update_generated_note(workflow: dict[str, Any], target: dict[str, Any], replacements: dict[str, str]) -> None:
    note = next((
        node for node in workflow.get("nodes", [])
        if node.get("properties", {}).get("dawasteh_note_for") == target.get("id")
    ), None)
    if note is None:
        raise ValueError(f"Missing generated note for node {target.get('id')}")
    text = str((note.get("widgets_values") or [""])[0])
    for old, new in replacements.items():
        text = text.replace(old, new)
    note["widgets_values"] = [text]
    title = target.get("title") or target.get("type")
    note["title"] = f"Erklärung · {title} · Node {target['id']}"


def _marker() -> dict[str, Any]:
    return {
        "version": 1,
        "lora_name": LORA_NAME,
        "source": f"https://huggingface.co/{LORA_SOURCE}",
        "sha256": LORA_SHA256,
        "sampling": {"steps": 8, "sampler": "res_multistep", "scheduler": "simple", "shift_video": 12.0, "shift_audio": 3.0},
        "ref2va_status": "compatible graph integration; Turbo quality with full-reference conditioning remains community/experimental",
    }


def integrate_visible(workflow: dict[str, Any], label: str) -> None:
    nodes = workflow["nodes"]
    links = workflow["links"]
    unets = [node for node in nodes if node.get("type") == "UNETLoader" and "minimax_h3_" in str(node.get("widgets_values", [""])[0])]
    if len(unets) != 1:
        raise ValueError(f"{label}: expected exactly one MiniMax H3 UNETLoader, found {len(unets)}")
    unet = unets[0]

    for node in nodes:
        if node.get("type") == "MiniMaxH3SigmaShift":
            old_title = str(node.get("title") or "MiniMax H3 Sigma Shift — video 12 / audio 3")
            # v1.1.3: Audio-Sigma bleibt auf dem Hersteller-Default 3.0 (siehe tools/upgrade_v113.py).
            node["widgets_values"] = [12.0, 3.0]
            node["title"] = "MiniMax H3 Sigma Shift — video 12 / audio 3"
            _update_generated_note(workflow, node, {
                old_title: node["title"],
                # v1.1.3: Alttexte aus v1.1.2 mitheilen, damit Widget und Notiz nie auseinanderlaufen.
                "MiniMax H3 Sigma Shift — video 12 / audio 4": node["title"],
                "`shift_audio` = `4.0`": "`shift_audio` = `3.0`",
            })
        elif node.get("type") == "KSamplerSelect":
            old_title = str(node.get("title") or "SAMPLER — res_multistep")
            node["widgets_values"] = ["res_multistep"]
            node["title"] = "SAMPLER — res_multistep"
            _update_generated_note(workflow, node, {
                old_title: node["title"],
                "SAMPLER — euler": node["title"],
                "`sampler_name` = `euler`": "`sampler_name` = `res_multistep`",
            })
        elif node.get("type") == "BasicScheduler":
            old_title = str(node.get("title") or "SCHEDULER — simple / 20 steps")
            values = list(node.get("widgets_values", []))
            if len(values) < 3:
                raise ValueError(f"{label}: unexpected BasicScheduler widgets")
            old_scheduler, old_steps = str(values[0]), int(values[1])
            # v1.1.3: Scheduler zurueck auf den Hersteller-Wert; nur die Schrittzahl bleibt Turbo.
            values[0], values[1] = "simple", 8
            node["widgets_values"] = values
            node["title"] = "SCHEDULER — simple / 8 steps"
            _update_generated_note(workflow, node, {
                old_title: node["title"],
                f"`scheduler` = `{old_scheduler}`": "`scheduler` = `simple`",
                "SCHEDULER — beta / 8 steps": node["title"],
                "`scheduler` = `beta`": "`scheduler` = `simple`",
                f"`steps` = `{old_steps}`": "`steps` = `8`",
            })

    existing = [node for node in nodes if node.get("type") == "LoraLoaderModelOnly" and node.get("properties", {}).get("dawasteh_h3_turbo")]
    if existing:
        existing[0]["widgets_values"] = [LORA_NAME, 1.0]
    else:
        model_output = next((output for output in unet.get("outputs", []) if output.get("type") == "MODEL"), None)
        old_ids = list((model_output or {}).get("links") or [])
        if not old_ids:
            raise ValueError(f"{label}: UNETLoader has no connected MODEL output")
        by_id = {_link_id(link): link for link in links}
        if any(_origin(by_id[link_id])[0] != unet["id"] for link_id in old_ids):
            raise ValueError(f"{label}: unexpected UNET MODEL link origin")
        new_node_id = max(int(node["id"]) for node in nodes if isinstance(node.get("id"), int)) + 1
        new_link_id = max(int(_link_id(link)) for link in links if isinstance(_link_id(link), int)) + 1
        for link_id in old_ids:
            _set_origin(by_id[link_id], new_node_id)
        model_output["links"] = [new_link_id]
        min_x = min(float(node.get("pos", [0, 0])[0]) for node in nodes)
        min_y = min(float(node.get("pos", [0, 0])[1]) for node in nodes)
        max_order = max(int(node.get("order", 0)) for node in nodes)
        lora = {
            "id": new_node_id, "type": "LoraLoaderModelOnly", "pos": [min_x, min_y - 520.0],
            "size": [670, 140], "flags": {}, "order": max_order + 1, "mode": 0,
            "inputs": [
                {"localized_name": "model", "name": "model", "type": "MODEL", "link": new_link_id},
                {"localized_name": "lora_name", "name": "lora_name", "type": "COMBO", "widget": {"name": "lora_name"}, "link": None},
                {"localized_name": "strength_model", "name": "strength_model", "type": "FLOAT", "widget": {"name": "strength_model"}, "link": None},
            ],
            "outputs": [{"localized_name": "MODEL", "name": "MODEL", "type": "MODEL", "slot_index": 0, "links": old_ids}],
            "properties": {"Node name for S&R": "LoraLoaderModelOnly", "cnr_id": "comfy-core", "dawasteh_h3_turbo": True},
            "widgets_values": [LORA_NAME, 1.0], "title": "MiniMax H3 Turbo · v4 Step-600 EMA · 8 Steps",
            "color": "#323", "bgcolor": "#535",
        }
        note_id = new_node_id + 1
        nodes.extend([lora, _note(note_id, new_node_id, [min_x + 720.0, min_y - 520.0], max_order + 2)])
        links.append(_new_link(links[0], new_link_id, int(unet["id"]), 0, new_node_id))
        workflow["last_node_id"] = note_id
        workflow["last_link_id"] = new_link_id
        refinement = workflow.setdefault("extra", {}).setdefault("dawasteh_workflow_refinement", {})
        refinement["generated_notes"] = int(refinement.get("generated_notes", 0)) + 1
    workflow.setdefault("extra", {})["dawasteh_h3_turbo_lora"] = _marker()


def integrate_director(workflow: dict[str, Any]) -> None:
    directors = [
        node for node in workflow["nodes"]
        if node.get("type") in {"DaWH3MusicVideoDirector", "DaWH3MusicVideoDirectorDualGPU"}
    ]
    if len(directors) != 1:
        raise ValueError(f"{DIRECTOR_WORKFLOW}: expected one Director")
    values = list(directors[0]["widgets_values"])
    if len(values) < 35:
        raise ValueError(f"{DIRECTOR_WORKFLOW}: unexpected Director widget count")
    values[12] = 8
    values[31], values[32] = 12.0, 3.0
    values[33], values[34] = "res_multistep", "simple"
    director = directors[0]
    director["widgets_values"] = values
    _update_generated_note(workflow, director, {
        "`steps` = `20`": "`steps` = `8`",
        "`shift_audio` = `3.0`": "`shift_audio` = `4.0`",
        "`sampler_name` = `res_multistep`": "`sampler_name` = `euler`",
    })
    guide = next((node for node in workflow["nodes"] if node.get("id") == 2 and node.get("type") == "MarkdownNote"), None)
    if guide is not None:
        guide["widgets_values"] = [str(guide["widgets_values"][0]).replace(
            "feste Seed-Basis, 20 Steps", "feste Seed-Basis, 8 Turbo-Steps"
        )]
    workflow.setdefault("extra", {})["dawasteh_h3_turbo_lora"] = _marker()


def integrate(directory: Path = H3_DIR) -> list[Path]:
    changed: list[Path] = []
    for name in VISIBLE_WORKFLOWS:
        path = directory / name
        workflow = json.loads(path.read_text(encoding="utf-8"))
        before = json.dumps(workflow, ensure_ascii=False, sort_keys=True)
        integrate_visible(workflow, name)
        if json.dumps(workflow, ensure_ascii=False, sort_keys=True) != before:
            path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed.append(path)
    director_path = directory / DIRECTOR_WORKFLOW
    workflow = json.loads(director_path.read_text(encoding="utf-8"))
    before = json.dumps(workflow, ensure_ascii=False, sort_keys=True)
    integrate_director(workflow)
    if json.dumps(workflow, ensure_ascii=False, sort_keys=True) != before:
        director_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(director_path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=H3_DIR)
    args = parser.parse_args()
    changed = integrate(args.directory)
    print(f"Updated {len(changed)} MiniMax H3 workflows in {args.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
