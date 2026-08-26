#!/usr/bin/env python3
"""Deterministic v0.9.5 game-development workflow additions.

The two Gemini LAB graphs are treated as requirements sketches, not trusted
workflow sources.  Their maintained successors are derived from workflows that
were already validated in v0.9.4 and use only models/nodes present in the local
ComfyUI installation.
"""
from __future__ import annotations

import copy
import json
import uuid
from typing import Any


UPGRADE_KEY = "dawasteh_v095_game_dev"
UPGRADE_VERSION = 1
TEXTURE_PATH = "Game Development/FLUX2_Klein_4B-PS1-Texture-Concept.json"
TEXTURE_SOURCE = "Text to Image/FLUX2_Klein_4b-Text-to-Image.json"
HUNYUAN_PATH = "Game Development/Hunyuan3D_v2_1-Low-Poly-Static-Mesh-for-Godot.json"
HUNYUAN_SOURCE = "Image to 3D-Mesh/Hunyuan3D_v2_1-Image-to-3D-Mesh.json"
VOICE_PATH = "Voice Design/RVC_DirectML-Live-Microphone-Voice-Swap.json"
VOICE_SOURCE = "Live Avatar/LiveAvatar-06-VRM-Full-Body-Hand-Face+Live-Mic.json"
VOICE_UPGRADE_KEY = "dawasteh_v095_live_voice"
ADDITION_SOURCES = {
    TEXTURE_PATH: TEXTURE_SOURCE,
    HUNYUAN_PATH: HUNYUAN_SOURCE,
    VOICE_PATH: VOICE_SOURCE,
}

# The v0.9.2 refinement snapshot predates ComfyUI 0.34's core mesh decimator.
# Supplying the current schema keeps generated notes deterministic without
# replacing the historical object-info asset used by the older collection.
V095_OBJECT_INFO: dict[str, Any] = {
    "DaWastehLiveVoiceSwapLauncher": {
        "display_name": "DirectML RVC Live Voice Swap Launcher (DaWasteh)",
        "description": (
            "Starts, inspects, or stops only the hash-verified local DirectML RVC b2332 service. "
            "Voice models and audio routing remain explicit user-controlled resources."
        ),
        "input": {
            "required": {
                "action": [["start / open UI", "status / open UI", "stop verified service"]],
                "install_path": ["STRING", {"default": "L:/ComfyUI/voice-changer-dml-b2332"}],
                "open_browser": ["BOOLEAN", {"default": True}],
            }
        },
        "input_order": {"required": ["action", "install_path", "open_browser"]},
        "output": ["STRING", "STRING", "INT"],
        "output_name": ["status", "ui_url", "process_id"],
    },
    "DecimateMesh": {
        "display_name": "Decimate Mesh",
        "description": (
            "Simplifies a mesh to a target face count using QEM. The midpoint "
            "preset preserves thin features and returns a welded mesh."
        ),
        "input": {
            "required": {
                "mesh": ["MESH", {}],
                "target_face_count": [
                    "INT",
                    {
                        "default": 200000,
                        "min": 0,
                        "max": 50000000,
                        "tooltip": "Target max faces. 0 disables.",
                    },
                ],
                "placement_mode": [
                    "COMFY_DYNAMICCOMBO_V3",
                    {
                        "display_name": "placement_mode",
                        "options": [
                            {"key": "midpoint", "inputs": {"required": {}}},
                            {
                                "key": "qem",
                                "inputs": {
                                    "required": {
                                        "line_quadric_weight": ["FLOAT", {"default": 0.0}],
                                        "feature_edge_quadric_weight": ["FLOAT", {"default": 0.0}],
                                        "feature_edge_min_dihedral_deg": ["FLOAT", {"default": 30.0}],
                                        "clamp_v_to_edge": ["BOOLEAN", {"default": True}],
                                    }
                                },
                            },
                        ],
                    },
                ],
            }
        },
        "input_order": {"required": ["mesh", "target_face_count", "placement_mode"]},
        "output": ["MESH"],
        "output_name": ["mesh"],
    }
}


def addition_sources() -> dict[str, str]:
    """Return target -> existing canonical source for collection reconstruction."""
    return dict(ADDITION_SOURCES)


def _next_node_id(workflow: dict[str, Any]) -> int:
    ids = [node.get("id") for node in workflow.get("nodes", []) if isinstance(node.get("id"), int)]
    return max([int(workflow.get("last_node_id", 0)), *ids], default=0) + 1


def _next_link_id(workflow: dict[str, Any]) -> int:
    ids = [link[0] for link in workflow.get("links", []) if isinstance(link, list) and link]
    return max([int(workflow.get("last_link_id", 0)), *ids], default=0) + 1


def _mark_refresh(*nodes: dict[str, Any]) -> None:
    for node in nodes:
        node.setdefault("properties", {})["dawasteh_refresh_generated_note"] = True


def _set_identity(workflow: dict[str, Any], path_key: str, family: str) -> None:
    workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dawasteh-v095:{path_key}"))
    workflow["revision"] = 0
    for node in workflow.get("nodes", []):
        if node.get("type") == "DaWMultiGPUDeviceControl":
            node["widgets_values"] = ["gpu:0", "gpu:0", "gpu:0"]
            node.setdefault("properties", {})["dawasteh_refresh_generated_note"] = True
        elif node.get("type") in {"SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"}:
            node["widgets_values"] = ["gpu:0"]
            node.setdefault("properties", {})["dawasteh_refresh_generated_note"] = True
    gpu = workflow.setdefault("extra", {}).setdefault("dawasteh_dual_gpu", {})
    gpu.update({
        "family": family,
        "source": f"workflows/{path_key}",
        "curated_split_default": False,
        "defaults": {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"},
    })


def _image_scale(node_id: int, title: str, method: str, width: int, height: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "ImageScale",
        "pos": [0, 0],
        "size": [315, 170],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "image", "name": "image", "type": "IMAGE", "link": None},
            {
                "localized_name": "upscale_method",
                "name": "upscale_method",
                "type": "COMBO",
                "widget": {"name": "upscale_method"},
                "link": None,
            },
            {"localized_name": "width", "name": "width", "type": "INT", "widget": {"name": "width"}, "link": None},
            {"localized_name": "height", "name": "height", "type": "INT", "widget": {"name": "height"}, "link": None},
            {"localized_name": "crop", "name": "crop", "type": "COMBO", "widget": {"name": "crop"}, "link": None},
        ],
        "outputs": [{"localized_name": "IMAGE", "name": "IMAGE", "type": "IMAGE", "slot_index": 0, "links": []}],
        "title": title,
        "properties": {"Node name for S&R": "ImageScale", "cnr_id": "comfy-core", "ver": "0.34.0"},
        "widgets_values": [method, width, height, "disabled"],
    }


def _image_quantize(node_id: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "ImageQuantize",
        "pos": [0, 0],
        "size": [315, 130],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "image", "name": "image", "type": "IMAGE", "link": None},
            {"localized_name": "colors", "name": "colors", "type": "INT", "widget": {"name": "colors"}, "link": None},
            {"localized_name": "dither", "name": "dither", "type": "COMBO", "widget": {"name": "dither"}, "link": None},
        ],
        "outputs": [{"localized_name": "IMAGE", "name": "IMAGE", "type": "IMAGE", "slot_index": 0, "links": []}],
        "title": "PS1-Palette · 32 Farben · Bayer-4",
        "properties": {"Node name for S&R": "ImageQuantize", "cnr_id": "comfy-core", "ver": "0.34.0"},
        "widgets_values": [32, "bayer-4"],
    }


def _save_image(node_id: int, title: str, prefix: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "SaveImage",
        "pos": [0, 0],
        "size": [315, 270],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "images", "name": "images", "type": "IMAGE", "link": None},
            {
                "localized_name": "filename_prefix",
                "name": "filename_prefix",
                "type": "STRING",
                "widget": {"name": "filename_prefix"},
                "link": None,
            },
        ],
        "outputs": [{"localized_name": "images", "name": "images", "type": "IMAGE", "links": None}],
        "title": title,
        "properties": {"Node name for S&R": "SaveImage", "cnr_id": "comfy-core", "ver": "0.34.0"},
        "widgets_values": [prefix],
    }


def _connect(
    workflow: dict[str, Any],
    source: dict[str, Any],
    source_slot: int,
    target: dict[str, Any],
    target_slot: int,
    kind: str,
) -> int:
    link_id = _next_link_id(workflow)
    workflow.setdefault("links", []).append([link_id, source["id"], source_slot, target["id"], target_slot, kind])
    source["outputs"][source_slot].setdefault("links", [])
    if source["outputs"][source_slot]["links"] is None:
        source["outputs"][source_slot]["links"] = []
    source["outputs"][source_slot]["links"].append(link_id)
    target["inputs"][target_slot]["link"] = link_id
    workflow["last_link_id"] = link_id
    return link_id


def _upgrade_texture(workflow: dict[str, Any]) -> None:
    by_id = {node.get("id"): node for node in workflow.get("nodes", [])}
    expected = {
        1: "UNETLoader",
        2: "CLIPLoader",
        8: "VAEDecode",
        9: "SaveImage",
        10: "Note",
        22: "PixaromaPrompt",
        24: "VRAM_Debug",
    }
    for node_id, node_type in expected.items():
        if by_id.get(node_id, {}).get("type") != node_type:
            raise ValueError(f"{TEXTURE_PATH}: expected node {node_id} to be {node_type}")

    positive = (
        "single square retro PS1 game texture concept sheet, exactly nine equal square material swatches "
        "in a strict 3 by 3 grid: rusted steel, weathered wood, worn leather, cracked sandstone, "
        "cobblestone, concrete, sci-fi panel, painted metal and rough cloth; orthographic flat front view, "
        "each tile isolated by a clean narrow white gutter, hard pixel clusters, limited 32-color palette, "
        "unlit flat diffuse albedo, seamless-looking game materials, no perspective, no labels, no text, "
        "no characters, no objects, no dramatic shadows, no watermark"
    )
    by_id[22]["widgets_values"] = [positive]
    by_id[9]["title"] = "SOURCE · 1024px Konzept speichern"
    by_id[9]["widgets_values"] = ["GameDev/PS1_Texture_Concept/source_1024"]
    by_id[10]["title"] = "START HIER · PS1-Texturkonzept für Godot"
    by_id[10]["widgets_values"] = [
        "=== FLUX.2 KLEIN 4B -> PS1-TEXTURKONZEPT -> GODOT ===\n\n"
        "1) Prompt Pixaroma beschreibt Materialthema und gewünschte Kacheln.\n"
        "2) FLUX.2 Klein 4B erzeugt eine 1024x1024-Konzeptquelle mit den bereits installierten "
        "Diffusions-, Qwen-Textencoder- und VAE-Gewichten.\n"
        "3) Area-Downscale erzeugt echte 128x128 Pixel, danach begrenzt ImageQuantize auf 32 Farben.\n"
        "4) Gespeichert werden Quelle, game_128 und eine 1024er Nearest-Preview.\n\n"
        "WICHTIG: Das ist ein Textur-KONZEPTBLATT, kein automatisch passendes UV-Atlas. Für ein echtes "
        "Mesh dessen UV-Layout als Vorlage verwenden und die finalen Inseln in Blender/Krita ausarbeiten.\n\n"
        "Godot: game_128 importieren, Filter AUS. Mipmaps für UI/Sprites AUS; bei 3D-Flächen gegen Flimmern "
        "meist AN lassen. Lossless-Kompression verwenden. 32 Farben/Bayer-4 sind Startwerte und frei änderbar."
    ]
    _mark_refresh(by_id[9])

    first = _next_node_id(workflow)
    scale_small = _image_scale(first, "GAME TEXTURE · Area-Downscale auf 128px", "area", 128, 128)
    quantize = _image_quantize(first + 1)
    save_small = _save_image(first + 2, "GAME TEXTURE · 128px PNG speichern", "GameDev/PS1_Texture_Concept/game_128")
    scale_preview = _image_scale(first + 3, "NEAREST PREVIEW · 1024px", "nearest-exact", 1024, 1024)
    save_preview = _save_image(first + 4, "PREVIEW · 1024px PNG speichern", "GameDev/PS1_Texture_Concept/nearest_preview_1024")
    max_order = max((int(node.get("order", 0)) for node in workflow.get("nodes", [])), default=0)
    for offset, node in enumerate((scale_small, quantize, save_small, scale_preview, save_preview), start=1):
        node["order"] = max_order + offset
        workflow["nodes"].append(node)

    _connect(workflow, by_id[24], 0, scale_small, 0, "IMAGE")
    _connect(workflow, scale_small, 0, quantize, 0, "IMAGE")
    _connect(workflow, quantize, 0, save_small, 0, "IMAGE")
    _connect(workflow, quantize, 0, scale_preview, 0, "IMAGE")
    _connect(workflow, scale_preview, 0, save_preview, 0, "IMAGE")
    workflow["last_node_id"] = save_preview["id"]
    _set_identity(workflow, TEXTURE_PATH, "FLUX.2 Klein 4B PS1 Texture Concept for Godot")
    workflow.setdefault("extra", {})[UPGRADE_KEY] = {
        "version": UPGRADE_VERSION,
        "release": "v0.9.5",
        "source_requirement": "FLUX-SDXL PS1 Texture Sheet Generator.json",
        "model_downloads": 0,
        "installed_models": [
            "diffusion_models/FLUX/flux-2-klein-4b.safetensors",
            "text_encoders/Qwen/qwen_3_4b.safetensors",
            "vae/FLUX2/flux2-vae.safetensors",
        ],
        "truthful_output": "texture concept sheet; not a mesh-aligned UV atlas",
        "outputs": ["source_1024", "game_128", "nearest_preview_1024"],
    }


def _decimate_mesh(node_id: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "DecimateMesh",
        "pos": [0, 0],
        "size": [360, 150],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "mesh", "name": "mesh", "type": "MESH", "link": None},
            {
                "localized_name": "target_face_count",
                "name": "target_face_count",
                "type": "INT",
                "widget": {"name": "target_face_count"},
                "link": None,
            },
            {
                "localized_name": "placement_mode",
                "name": "placement_mode",
                "type": "COMFY_DYNAMICCOMBO_V3",
                "widget": {"name": "placement_mode"},
                "link": None,
            },
        ],
        "outputs": [{"localized_name": "mesh", "name": "mesh", "type": "MESH", "slot_index": 0, "links": []}],
        "title": "LOW-POLY · Ziel maximal 5.000 Faces",
        "properties": {"Node name for S&R": "DecimateMesh", "cnr_id": "comfy-core", "ver": "0.34.0"},
        "widgets_values": [5000, "midpoint"],
    }


def _upgrade_hunyuan(workflow: dict[str, Any]) -> None:
    by_id = {node.get("id"): node for node in workflow.get("nodes", [])}
    expected = {9: "VoxelToMesh", 10: "SaveGLB", 11: "Note", 12: "MarkdownNote", 25: "VRAM_Debug"}
    for node_id, node_type in expected.items():
        if by_id.get(node_id, {}).get("type") != node_type:
            raise ValueError(f"{HUNYUAN_PATH}: expected node {node_id} to be {node_type}")

    old_link = by_id[10]["inputs"][0].get("link")
    if not isinstance(old_link, int):
        raise ValueError(f"{HUNYUAN_PATH}: SaveGLB mesh input is not linked")
    serialized = next((link for link in workflow.get("links", []) if link[0] == old_link), None)
    if serialized is None or serialized[1:5] != [25, 0, 10, 0]:
        raise ValueError(f"{HUNYUAN_PATH}: canonical mesh cleanup link changed")

    decimate = _decimate_mesh(_next_node_id(workflow))
    decimate["order"] = max((int(node.get("order", 0)) for node in workflow.get("nodes", [])), default=0) + 1
    workflow["nodes"].append(decimate)
    serialized[3] = decimate["id"]
    serialized[4] = 0
    decimate["inputs"][0]["link"] = old_link
    by_id[10]["inputs"][0]["link"] = None
    _connect(workflow, decimate, 0, by_id[10], 0, "MESH")
    workflow["last_node_id"] = decimate["id"]

    by_id[10]["title"] = "GODOT · Low-Poly-GLB speichern (statisch)"
    by_id[10]["widgets_values"] = ["GameDev/Hunyuan3D_LowPoly/hunyuan3d_lowpoly_static", ""]
    by_id[11]["title"] = "START HIER · Bild → Low-Poly-GLB für Godot"
    by_id[11]["widgets_values"] = [
        "=== HUNYUAN3D 2.1 -> LOW-POLY-GLB -> GODOT ===\n\n"
        "1) Ein einzelnes, zentriertes Objektbild mit sauberem oder transparentem Hintergrund wählen.\n"
        "2) Der bewährte Core-Pfad nutzt ModelSamplingAuraFlow shift 1, 40 Schritte und den bereits "
        "installierten Hunyuan3D-2.1-Checkpoint.\n"
        "3) Decimate Mesh reduziert auf maximal 5.000 Faces. 'midpoint' schützt dünne Details besser. "
        "800 Faces nur als aggressives fernes LOD testen.\n"
        "4) SaveGLB schreibt nach output/GameDev/Hunyuan3D_LowPoly/.\n\n"
        "WICHTIG: Ergebnis ist ein STATISCHES, UNTEXTURIERTES und UNGERIGGTES Zwischenmesh. Vor einem "
        "Character-Einsatz in Blender Maßstab/Achsen, Normalen, Silhouette, UVs, Material, Rig, Skinning, "
        "Animationen und LODs prüfen. In Godot eignet es sich direkt nur als MeshInstance3D/Prop; Collision "
        "bewusst separat erzeugen."
    ]
    by_id[12]["widgets_values"] = [
        "**Vorhandene lokale Ressourcen**\n\n"
        "- `models/checkpoints/Hunyuan3D/hunyuan_3d_v2.1.safetensors`\n"
        "- ComfyUI 0.34 Core: `DecimateMesh` / `SaveGLB`\n\n"
        "Keine neuen Modellgewichte und kein zusätzlicher Mesh-Custom-Node nötig. Der 5.000-Face-Wert ist "
        "ein sicherer Startpunkt, kein universelles Budget. Silhouette und dünne Teile immer visuell prüfen."
    ]
    _mark_refresh(by_id[10])
    _set_identity(workflow, HUNYUAN_PATH, "Hunyuan3D 2.1 Low-Poly Static Mesh for Godot")
    workflow.setdefault("extra", {})[UPGRADE_KEY] = {
        "version": UPGRADE_VERSION,
        "release": "v0.9.5",
        "source_requirement": "Hunyuan3D + Mesh Decimator Pipeline.json",
        "model_downloads": 0,
        "installed_checkpoint": "Hunyuan3D/hunyuan_3d_v2.1.safetensors",
        "decimator": "ComfyUI 0.34 core DecimateMesh",
        "target_face_count": 5000,
        "truthful_output": "static, untextured, unrigged GLB intermediate",
    }


def _run_timer(node_id: int, order: int) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "PixaromaRunTimer",
        "pos": [0, 0],
        "size": [320, 100],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "properties": {"Node name for S&R": "PixaromaRunTimer", "cnr_id": "ComfyUI-Pixaroma"},
        "widgets_values": [{
            "version": 1,
            "color": "#f66744",
            "decimals": 0,
            "chime": True,
            "sound": "",
            "volume": 70,
        }],
    }


def _upgrade_voice(workflow: dict[str, Any]) -> None:
    by_id = {node.get("id"): node for node in workflow.get("nodes", [])}
    expected = {
        1: "PixaromaNote",
        2: "DaWastehVRMLiveAvatarLauncher",
        4: "MarkdownNote",
        5: "DaWMultiGPUDeviceControl",
    }
    for node_id, node_type in expected.items():
        if by_id.get(node_id, {}).get("type") != node_type:
            raise ValueError(f"{VOICE_PATH}: expected node {node_id} to be {node_type}")

    launcher = by_id[2]
    launcher.update({
        "type": "DaWastehLiveVoiceSwapLauncher",
        "size": [610, 230],
        "inputs": [
            {
                "localized_name": "action",
                "name": "action",
                "type": "COMBO",
                "widget": {"name": "action"},
                "link": None,
            },
            {
                "localized_name": "install_path",
                "name": "install_path",
                "type": "STRING",
                "widget": {"name": "install_path"},
                "link": None,
            },
            {
                "localized_name": "open_browser",
                "name": "open_browser",
                "type": "BOOLEAN",
                "widget": {"name": "open_browser"},
                "link": None,
            },
        ],
        "outputs": [
            {"localized_name": "status", "name": "status", "type": "STRING", "slot_index": 0, "links": []},
            {"localized_name": "ui_url", "name": "ui_url", "type": "STRING", "slot_index": 1, "links": []},
            {"localized_name": "process_id", "name": "process_id", "type": "INT", "slot_index": 2, "links": []},
        ],
        "title": "LIVE VOICE · DirectML RVC starten / prüfen / stoppen",
        "properties": {"Node name for S&R": "DaWastehLiveVoiceSwapLauncher"},
        "widgets_values": ["start / open UI", "L:/ComfyUI/voice-changer-dml-b2332", True],
    })
    _mark_refresh(launcher)

    note_content = (
        "<h1>Live-Mikrofon-Voice-Swap · DirectML RVC</h1>"
        "<p><b>Ein normaler Run</b> verifiziert den gepinnten b2332-Runtime vollständig, startet nur dessen "
        "exakte EXE und öffnet die lokale UI auf <code>127.0.0.1:18888</code>. Live-Audio läuft danach "
        "außerhalb der ComfyUI-Queue weiter.</p>"
        "<ol><li><code>start / open UI</code> wählen und einmal Run drücken.</li>"
        "<li>In der RVC-UI ausschließlich ein eigenes oder ausdrücklich lizenziertes Modell importieren. "
        "Kein Stimmenmodell wird im Git-Bundle verteilt.</li>"
        "<li>RX 9070 XT DirectML, <code>rmvpe_onnx</code>, 48 kHz und zunächst 100-ms-Chunks wählen.</li>"
        "<li>Physisches Mikrofon als Eingang, virtuelles Audiokabel als Ausgang wählen. In OBS nur das Kabel "
        "aufnehmen und das Originalmikrofon stummschalten. Auf diesem Rechner ist derzeit kein virtuelles Kabel "
        "vorinstalliert; für die lokale Vorführung Kopfhörer als Ausgang nutzen und Lautsprecher-Feedback vermeiden.</li>"
        "<li>Zum Beenden <code>stop verified service</code> wählen und erneut Run drücken.</li></ol>"
        "<p><b>Demo-Modell:</b> Die offizielle Seite <a href='https://amitaro.net/synth/rvc/'>Amitaro's Voice "
        "Material Studio</a> bietet klar lizenzierte RVC-Modelle. Nutzung erfordert Credit "
        "<code>RVC Model: Amitaro's Voice Material Studio (https://amitaro.net/)</code>; keine "
        "Weiterverteilung, kein Vortäuschen der echten Stimme und weitere dortige Inhaltsgrenzen beachten.</p>"
        "<p><b>OmniVoice wurde bewusst nicht verwendet:</b> Es ist Zero-shot-TTS aus Text und 3–10 s "
        "Referenzaudio, kein echtes inkrementelles Speech-to-Speech-Streaming; die offiziellen Gewichte sind "
        "zudem CC-BY-NC. Details: <code>docs/OMNIVOICE_LIVE_SWAP_EVALUATION.md</code>.</p>"
        "<p><b>Verantwortung:</b> Nur Stimmen mit nachweisbarer Einwilligung/Lizenz nutzen. Keine Täuschung, "
        "Belästigung, Betrugsanrufe oder Identitätsvortäuschung.</p>"
    )
    by_id[1]["title"] = "START HIER · Live Voice Swap + Audio-Routing"
    by_id[1]["widgets_values"] = [json.dumps({
        "version": 1,
        "content": note_content,
        "buttonColor": "#32c48d",
        "lineColor": "#32c48d",
        "width": 940,
        "height": 980,
        "backgroundColor": "#2a2a2a",
    }, ensure_ascii=False, separators=(",", ":")), ""]

    timer_id = _next_node_id(workflow)
    timer = _run_timer(
        timer_id,
        max((int(node.get("order", 0)) for node in workflow.get("nodes", [])), default=0) + 1,
    )
    workflow["nodes"].append(timer)
    workflow["last_node_id"] = timer_id
    _set_identity(workflow, VOICE_PATH, "DirectML RVC Live Microphone Voice Swap")
    workflow.setdefault("extra", {})[VOICE_UPGRADE_KEY] = {
        "version": UPGRADE_VERSION,
        "release": "v0.9.5",
        "runtime": "deiteris/voice-changer b2332 DirectML",
        "runtime_downloads": 0,
        "voice_model_bundled": False,
        "live_audio_outside_comfy_queue": True,
        "fixed_loopback_url": "http://127.0.0.1:18888/",
        "omnivoice_decision": "not suitable for true live speech-to-speech swapping",
    }


def upgrade_workflow(workflow: dict[str, Any], path_key: str) -> tuple[dict[str, Any], bool]:
    """Upgrade one v0.9.5 target; return a deep copy and a changed flag."""
    upgraded = copy.deepcopy(workflow)
    if path_key not in ADDITION_SOURCES:
        return upgraded, False
    marker_key = VOICE_UPGRADE_KEY if path_key == VOICE_PATH else UPGRADE_KEY
    marker = upgraded.get("extra", {}).get(marker_key, {})
    if marker.get("version") == UPGRADE_VERSION:
        return upgraded, False
    if path_key == TEXTURE_PATH:
        _upgrade_texture(upgraded)
    elif path_key == HUNYUAN_PATH:
        _upgrade_hunyuan(upgraded)
    elif path_key == VOICE_PATH:
        _upgrade_voice(upgraded)
    return upgraded, True
