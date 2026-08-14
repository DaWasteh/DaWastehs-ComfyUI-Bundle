#!/usr/bin/env python3
"""Generate the Qwen3-TTS LoRA training and low-latency voice workflows."""

from __future__ import annotations

import argparse
import copy
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from tools.migrate_workflows_v092 import migrate_workflow
    from tools.refine_workflows import build_note_text, refine_workflow
except ModuleNotFoundError:
    from migrate_workflows_v092 import migrate_workflow
    from refine_workflows import build_note_text, refine_workflow

REPO_ROOT = Path(__file__).resolve().parents[1]
TIMER_VALUE = {
    "version": 1,
    "color": "#f66744",
    "decimals": 0,
    "chime": True,
    "sound": "",
    "volume": 70,
}


def load_object_info(server: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(f"{server.rstrip('/')}/object_info", timeout=30) as response:
            return json.load(response)
    except urllib.error.URLError:
        fixture = REPO_ROOT / "assets/live-avatar-v072/object-info.json"
        return json.loads(fixture.read_text(encoding="utf-8"))


def input_order(schema: dict[str, Any], section: str) -> list[str]:
    return list(schema.get("input_order", {}).get(section, schema.get("input", {}).get(section, {})))


def is_widget(schema: dict[str, Any], section: str, name: str) -> bool:
    input_type = schema["input"][section][name][0]
    return isinstance(input_type, list) or input_type in {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"}


def node(
    object_info: dict[str, Any],
    node_id: int,
    node_type: str,
    pos: list[float],
    size: list[float],
    widgets: list[Any],
    title: str,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema = object_info[node_type]
    inputs: list[dict[str, Any]] = []
    for section in ("required", "optional"):
        for name in input_order(schema, section):
            configured_type = schema["input"][section][name][0]
            item: dict[str, Any] = {
                "localized_name": name,
                "name": name,
                "type": "COMBO" if isinstance(configured_type, list) else configured_type,
                "link": None,
            }
            if is_widget(schema, section, name):
                item["widget"] = {"name": name}
            inputs.append(item)

    output_types = list(schema.get("output", []))
    output_names = list(schema.get("output_name") or output_types)
    outputs = [
        {
            "localized_name": output_names[index],
            "name": output_names[index],
            "type": output_type,
            "links": None,
        }
        for index, output_type in enumerate(output_types)
    ]
    return {
        "id": node_id,
        "type": node_type,
        "pos": pos,
        "size": size,
        "flags": {},
        "order": node_id,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "properties": properties or {"Node name for S&R": node_type},
        "widgets_values": widgets,
        "title": title,
    }


def start_note(node_id: int, title: str, html: str, size: list[float]) -> dict[str, Any]:
    payload = {
        "version": 1,
        "content": html,
        "buttonColor": "#f66744",
        "lineColor": "#f66744",
        "width": size[0],
        "height": size[1] - 40,
        "backgroundColor": "#2a2a2a",
    }
    return {
        "id": node_id,
        "type": "PixaromaNote",
        "pos": [40, 80],
        "size": size,
        "flags": {},
        "order": node_id,
        "mode": 0,
        "inputs": [
            {
                "localized_name": "note_json",
                "name": "note_json",
                "type": "STRING",
                "link": None,
                "widget": {"name": "note_json"},
            }
        ],
        "outputs": [],
        "properties": {"Node name for S&R": "PixaromaNote", "cnr_id": "ComfyUI-Pixaroma"},
        "widgets_values": [json.dumps(payload, ensure_ascii=False, separators=(",", ":")), ""],
        "title": title,
        "color": "#1d1d1d",
        "bgcolor": "#2a2a2a",
    }


def timer(node_id: int, pos: list[float]) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "PixaromaRunTimer",
        "pos": pos,
        "size": [320, 100],
        "flags": {},
        "order": node_id,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "properties": {"Node name for S&R": "PixaromaRunTimer", "cnr_id": "ComfyUI-Pixaroma"},
        "widgets_values": [TIMER_VALUE],
    }


def connect(
    nodes: list[dict[str, Any]],
    links: list[list[Any]],
    link_id: int,
    source_id: int,
    source_slot: int,
    target_id: int,
    target_input: str,
    link_type: str,
) -> None:
    source = next(item for item in nodes if item["id"] == source_id)
    target = next(item for item in nodes if item["id"] == target_id)
    target_slot = next(index for index, item in enumerate(target["inputs"]) if item["name"] == target_input)
    target["inputs"][target_slot]["link"] = link_id
    source["outputs"][source_slot]["links"] = source["outputs"][source_slot]["links"] or []
    source["outputs"][source_slot]["links"].append(link_id)
    links.append([link_id, source_id, source_slot, target_id, target_slot, link_type])


def workflow(workflow_id: str, nodes: list[dict[str, Any]], links: list[list[Any]]) -> dict[str, Any]:
    return {
        "id": workflow_id,
        "revision": 0,
        "last_node_id": max(item["id"] for item in nodes),
        "last_link_id": max((item[0] for item in links), default=0),
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {
            "workflowRendererVersion": "LG",
            "frontendVersion": "1.47.11",
            "ds": {"scale": 0.82, "offset": [100, 100]},
        },
        "version": 0.4,
    }


def training_workflow(object_info: dict[str, Any]) -> dict[str, Any]:
    html = """<h1>Qwen3-TTS · echtes Voice-LoRA-Training · Windows AMD RDNA4</h1>
<p>Dieser Workflow trainiert einen <b>echten PEFT-LoRA-Adapter</b> plus die zugehörige Sprecher-Einbettung. ACE-Step-Voice-LoRAs sind für Gesang/Musik gedacht und nicht für Live-Avatar-TTS.</p>
<h2>Datensatz</h2><div>ComfyUI/input/qwen3tts_lora/my_voice/</div><pre>001.wav + 001.txt\n002.wav + 002_Text.txt</pre>
<p>Jede TXT-Datei muss das exakte Transkript der Aufnahme enthalten. Unterstützt werden <code>&lt;name&gt;.txt</code> und <code>&lt;name&gt;_Text.txt</code>. Verwende nur Stimmen, die dir gehören oder für die du eine ausdrückliche Einwilligung hast. Saubere Einzelsprecher-Aufnahmen ohne Musik verwenden.</p>
<h2>AMD-Sicherstart</h2><ul><li><code>0.6B</code>, <code>sdpa</code>, BF16 intern</li><li>1 Epoche, Batch 1, Accumulation 4, Rank 16/Alpha 32</li><li>Lernrate <code>2e-6</code>; nicht auf 2e-5 erhöhen</li></ul>
<p>Nach einem erfolgreichen Smoke-Test Epochen schrittweise erhöhen und Hörproben vergleichen; etwa ab 10 Epochen steigt Überanpassungsgefahr. Audio wird automatisch auf 24 kHz Mono vorbereitet.</p>
<h2>Ausgabe und Nutzung</h2><div>ComfyUI/models/qwen-tts/loras/my_voice/checkpoint-epoch-N/</div>
<p>Enthält <code>adapter_model.safetensors</code>, <code>adapter_config.json</code>, <code>speaker_embedding.safetensors</code> und Metadaten. Danach ComfyUI-Nodes mit <b>R</b> aktualisieren und im LoRA-Live-Voice-Workflow den Adapter wählen.</p>
<h2>Modelle/Nodes</h2><ul><li>Qwen/Qwen3-TTS-12Hz-0.6B-Base</li><li>Qwen/Qwen3-TTS-Tokenizer-12Hz</li><li>ComfyUI-DaWasteh-Qwen3TTS-LoRA</li><li>ComfyUI-Pixaroma</li></ul>
<p><a href="https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base">Qwen 0.6B Base</a> · <a href="https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz">12Hz Tokenizer</a> · <a href="https://github.com/cheeweijie/qwen3-tts-lora-finetuning">LoRA-Referenz</a></p>"""
    nodes = [
        start_note(1, "START HIER · Qwen3-TTS Voice-LoRA", html, [920, 1180]),
        node(
            object_info,
            2,
            "DaWastehQwen3TTSLoRATrain",
            [1220, 120],
            [560, 560],
            [
                "0.6B",
                "L:\\ComfyUI\\ComfyUI\\input\\qwen3tts_lora\\my_voice",
                "L:\\ComfyUI\\ComfyUI\\models\\qwen-tts\\loras\\my_voice",
                "my_voice",
                "German",
                0.000002,
                1,
                1,
                4,
                "16",
                32,
                0.05,
                "sdpa",
            ],
            "Qwen3-TTS · PEFT-LoRA trainieren",
        ),
        timer(3, [1220, 800]),
    ]
    return workflow("qwen3-tts-voice-lora-training", nodes, [])


def inference_workflow(object_info: dict[str, Any]) -> dict[str, Any]:
    html = """<h1>Qwen3-TTS Voice-LoRA · schnelle Avatar-Sprache</h1>
<p>Schreibt Text mit einem lokal trainierten, im Dropdown wechselbaren PEFT-LoRA-Adapter als Stimme. <b>R</b> auf dem Voice-Node aktualisiert die Adapterliste nach neuem Training.</p>
<h2>Bedienung</h2><ol><li><code>adapter_name</code> und den im Training verwendeten <code>speaker_name</code> wählen/eintragen.</li><li><code>model_size</code> muss zur Trainingsbasis passen.</li><li>Text ändern und genau einmal ausführen.</li><li><code>lora_scale</code> zuerst bei 0.30 lassen; 0.20/0.30/0.35/0.50 vergleichen.</li></ol>
<p>Der Browser spielt jede geänderte Ausgabe automatisch einmal ab. Für OBS die Browser-/Anwendungs-Audioaufnahme verwenden oder den Browser über ein vorhandenes virtuelles Audiokabel routen. Zusätzlich wird eine FLAC unter <code>ComfyUI/output/audio/avatar-voice/</code> gespeichert.</p>
<p><b>Live-Grenze:</b> Dies ist schnelle, request-basierte TTS und kein kontinuierlicher Mikrofon-Voice-Changer. ComfyUI liefert den vollständigen Clip nach einem Queue-Lauf. Unveränderte Audio-Nodes bleiben gecacht, sodass ein parallel laufender LivePortrait-Auto-Queue-Zweig nicht jedes Frame neu vertont.</p>
<p><b>Sicherheit:</b> Nur eigene oder ausdrücklich freigegebene Stimmen verwenden. Adapter werden ausschließlich aus Safetensors/JSON geladen.</p>
<h2>AMD RDNA4</h2><p><code>sdpa</code>, BF16 und das 0.6B-Modell sind für geringe Latenz auf der R9700 voreingestellt. Für bessere Qualität kann ein separat mit 1.7B trainierter Adapter verwendet werden.</p>"""
    default_adapter = "my_voice/checkpoint-epoch-1"
    nodes = [
        start_note(1, "START HIER · LoRA-Stimme und OBS-Audio", html, [940, 1080]),
        node(
            object_info,
            2,
            "DaWastehQwen3TTSLoRAInference",
            [1280, 120],
            [610, 700],
            [
                "Hallo! Das ist meine lokal trainierte Avatar-Stimme.",
                default_adapter,
                "my_voice",
                "0.6B",
                "German",
                0.3,
                0,
                2048,
                0.8,
                20,
                1.0,
                1.05,
                "sdpa",
                False,
                "",
            ],
            "Text → wählbare Voice-LoRA",
        ),
        node(
            object_info,
            3,
            "PlaySoundKJ",
            [2220, 120],
            [420, 270],
            ["", "on_change", 0.8, 0.0],
            "Im Browser einmal abspielen",
            {"Node name for S&R": "PlaySoundKJ", "cnr_id": "comfyui-kjnodes"},
        ),
        node(
            object_info,
            4,
            "SaveAudio",
            [2220, 520],
            [420, 180],
            ["audio/avatar-voice/qwen3tts-lora"],
            "FLAC speichern",
            {"Node name for S&R": "SaveAudio", "cnr_id": "comfy-core"},
        ),
        timer(5, [1280, 900]),
    ]
    links: list[list[Any]] = []
    connect(nodes, links, 1, 2, 0, 3, "audio", "AUDIO")
    connect(nodes, links, 2, 2, 0, 4, "audio", "AUDIO")
    return workflow("qwen3-tts-lora-low-latency-live-voice", nodes, links)


def generated_note(
    object_info: dict[str, Any],
    node_id: int,
    target: dict[str, Any],
    pos: list[float],
) -> dict[str, Any]:
    schema = object_info[target["type"]]
    text = build_note_text(target, schema)
    line_count = text.count("\n") + 1
    return {
        "id": node_id,
        "type": "MarkdownNote",
        "pos": pos,
        "size": [390, min(540, max(230, 90 + line_count * 17))],
        "flags": {},
        "order": node_id,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "title": f"Erklärung · {target.get('title') or target['type']} · Node {target['id']}",
        "properties": {
            "Node name for S&R": "MarkdownNote",
            "cnr_id": "comfy-core",
            "dawasteh_note_for": int(target["id"]),
            "dawasteh_generated_note": True,
        },
        "widgets_values": [text],
        "color": "#1b2638",
        "bgcolor": "#101722",
    }


def live_avatar_workflow(object_info: dict[str, Any]) -> dict[str, Any]:
    source_path = REPO_ROOT / "assets" / "live-avatar-v072" / "workflow-03.base.json"
    data = copy.deepcopy(json.loads(source_path.read_text(encoding="utf-8")))
    data["id"] = "live-avatar-04-liveportrait-spout-qwen3tts-lora"
    data["revision"] = 0

    start = next(item for item in data["nodes"] if item["type"] == "PixaromaNote")
    payload = json.loads(start["widgets_values"][0])
    payload["content"] += """<h2>Voice-LoRA + OBS-Audio</h2>
<p>Der zusätzliche Qwen3-TTS-Zweig spricht Text mit einem lokal trainierten PEFT-LoRA. <code>adapter_name</code>, <code>speaker_name</code> und <code>model_size</code> müssen zum Trainings-Checkpoint passen. Den Node nach neuem Training mit <b>R</b> aktualisieren.</p>
<p><code>PlaySoundKJ</code> spielt nur bei geändertem Audio einmal im ComfyUI-Browser. OBS nimmt den Browser bzw. dessen Anwendungsaudio auf; alternativ ein bereits vorhandenes virtuelles Audiokabel verwenden. Spout überträgt ausschließlich das RGBA-Video.</p>
<p><b>Auto-Queue-Sicherheit:</b> Text, Adapter und Seed unverändert lassen. Dann bleibt der TTS-Node gecacht und <code>on_change</code> verhindert, dass bei jedem Webcam-Frame dieselbe Zeile erneut abgespielt wird. Für eine neue Zeile Text ändern und einmal ausführen.</p>
<p><b>Live-Grenze:</b> Die Stimme ist request-basierte TTS, kein kontinuierlicher Mikrofon-Voice-Changer. Nur eigene oder ausdrücklich freigegebene Stimmen verwenden.</p>"""
    payload["height"] = max(int(payload.get("height", 980)), 1320)
    start["widgets_values"][0] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    start["size"][1] = payload["height"] + 36
    start["title"] = "START HIER · LivePortrait, OBS und Voice-LoRA"

    default_adapter = "my_voice/checkpoint-epoch-1"
    voice = node(
        object_info,
        23,
        "DaWastehQwen3TTSLoRAInference",
        [2401.0, 3380.0],
        [610, 700],
        [
            "Hallo und willkommen! Mein Live-Avatar ist jetzt mit meiner lokalen Voice-LoRA verbunden.",
            default_adapter,
            "my_voice",
            "0.6B",
            "German",
            0.3,
            0,
            2048,
            0.8,
            20,
            1.0,
            1.05,
            "sdpa",
            False,
            "",
        ],
        "Voice-LoRA · neue Zeile sprechen",
    )
    player = node(
        object_info,
        24,
        "PlaySoundKJ",
        [4067.0, 3380.0],
        [420, 270],
        ["", "on_change", 0.8, 0.0],
        "Browser-Audio → OBS aufnehmen",
        {"Node name for S&R": "PlaySoundKJ", "cnr_id": "comfyui-kjnodes"},
    )
    data["nodes"].extend([voice, player])
    connect(data["nodes"], data["links"], 15, 23, 0, 24, "audio", "AUDIO")
    data["nodes"].extend(
        [
            generated_note(object_info, 25, voice, [3057.0, 3380.0]),
            generated_note(object_info, 26, player, [4533.0, 3380.0]),
        ]
    )
    data["last_node_id"] = 26
    data["last_link_id"] = 15
    marker = data.setdefault("extra", {}).setdefault("dawasteh_workflow_refinement", {})
    marker["generated_notes"] = int(marker.get("generated_notes", 10)) + 2
    return data


def write_workflow(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    args = parser.parse_args()
    object_info = load_object_info(args.server)
    required = {
        "DaWastehQwen3TTSLoRATrain",
        "DaWastehQwen3TTSLoRAInference",
        "PlaySoundKJ",
        "SaveAudio",
    }
    missing = required - object_info.keys()
    if missing:
        raise RuntimeError(f"Missing live ComfyUI nodes: {sorted(missing)}")

    generated = [
        (
            REPO_ROOT / "workflows" / "LoRA Generation" / "Qwen3-TTS_0.6B-Voice-LoRA-Training.json",
            training_workflow(object_info),
        ),
        (
            REPO_ROOT / "workflows" / "Voice Design" / "Qwen3-TTS_LoRA-Low-Latency-Live-Voice.json",
            inference_workflow(object_info),
        ),
        (
            REPO_ROOT / "workflows" / "Live Avatar" / "LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA.json",
            live_avatar_workflow(object_info),
        ),
    ]
    for path, data in generated:
        refine_workflow(data, object_info)
        key = path.relative_to(REPO_ROOT / "workflows").as_posix()
        write_workflow(path, migrate_workflow(data, key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
