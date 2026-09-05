#!/usr/bin/env python3
"""Deterministic v1.0.0 additions: Workflow 16 (rebuilt) and Workflow 17.

v1.0.0 turns the v0.9.9 face swap into a realistic live pipeline (measured on
the captured BRIO frames of this host): ``hyperswap_1c_256`` on a 0.8× crop,
xseg_3 occlusion (hands/objects stay visible), bisenet region mask with the
real mouth interior kept, a "digital shave" of the beard zone, LAB colour
transfer and GPEN-BFR-256. Workflow 17 adds MODNet person matting onto a clean
background plate (nobody in the picture once you leave) and the DirectML RVC
voice launcher. Both templates are generated here, pinned by SHA-256 under
``tools/workflow_templates`` and turned into canonical workflows by the regular
v0.9.2 migration. Live Avatar workflows stay timer-free by user decision.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from tools.upgrade_v099 import MODEL_FILES as V099_MODEL_FILES, PREVIEW_IMAGE, SENDER_NAME, SOURCE_IMAGE, _link_input, _node, _output
except ImportError:  # executed as a script from tools/
    from upgrade_v099 import MODEL_FILES as V099_MODEL_FILES, PREVIEW_IMAGE, SENDER_NAME, SOURCE_IMAGE, _link_input, _node, _output


UPGRADE_KEY = "dawasteh_v100_live_person_swap"
UPGRADE_VERSION = 1
FACE_SWAP_PATH = "Live Avatar/LiveAvatar-16-Live-Face-Swap-DirectML-Spout-OBS.json"
FACE_SWAP_TEMPLATE = "live_face_swap_directml_v100.json"
FACE_SWAP_TEMPLATE_SHA256 = "15775ccce5c264100dfbefe6ee8a130c50fae4979e3c71679f2062a489362c54"
PERSON_SWAP_PATH = "Live Avatar/LiveAvatar-17-Live-Person-Swap-Matting-Voice-DirectML-Spout-OBS.json"
PERSON_SWAP_TEMPLATE = "live_person_swap_directml_v100.json"
PERSON_SWAP_TEMPLATE_SHA256 = "0768c62731dd39fa18b8221ae44db86ee4eaed70f3adac1581572aaf5848beb3"

SOURCE_IMAGES = [SOURCE_IMAGE, PREVIEW_IMAGE, "13_three_quarter_right_00001_.png"]
PERSON_SENDER_NAME = "ComfyLivePersonSwap"
VOICE_INSTALL_PATH = "L:/ComfyUI/voice-changer-dml-b2332"

MODEL_FILES = [
    *V099_MODEL_FILES,
    {"repo": "facefusion/models-3.3.0", "path": "insightface/hyperswap_1c_256.onnx", "size": 402_742_682, "sha256": "5528c2d76fe9986c99d829278987ef9f3a630cb606db7628d02b57b330f406a5", "licence": "FaceFusion ResearchRAIL"},
    {"repo": "facefusion/models-3.9.0", "path": "insightface/alphaface_256.onnx", "size": 555_624_110, "sha256": "efcca3ffa1c28b75a007f689b39f7d4716c02810e7fa72d892e175f0b058a2e2", "licence": "AlphaFace non-commercial"},
    {"repo": "facefusion/models-3.0.0", "path": "insightface/uniface_256.onnx", "size": 406_964_143, "sha256": "eb5ce2af024cddf88ecb93b24e29a6eb44e354aba7d3319e84d29dcd868820f3", "licence": "UniFace, licence unknown"},
    {"repo": "facefusion/models-3.2.0", "path": "face_parsing/xseg_3.onnx", "size": 70_327_709, "sha256": "48ccd7e8541e159a5a754ec9e62df2f12065f7df8f9af842c1750342c6533559", "licence": "DeepFaceLab GPL-3.0"},
    {"repo": "facefusion/models-3.1.0", "path": "face_parsing/xseg_2.onnx", "size": 70_324_286, "sha256": "cd9a0879eaf43841d765472cf1f8c330dbf9dcb03da0eace93e95f3bcc399042", "licence": "DeepFaceLab GPL-3.0"},
    {"repo": "facefusion/models-3.1.0", "path": "face_parsing/xseg_1.onnx", "size": 70_324_286, "sha256": "c4d1498b8a03b5fe2a3a5d2ef2a0402ab03bd51edaf5b2d8d5fb764702a97dd3", "licence": "DeepFaceLab GPL-3.0"},
    {"repo": "facefusion/models-3.0.0", "path": "face_parsing/bisenet_resnet_34.onnx", "size": 93_632_546, "sha256": "4a0b8c958a3c938913bd06a8365dbb3c8761afba6ecbf0d14b3b1f77eb230c96", "licence": "yakhyo MIT"},
    {"repo": "facefusion/models-3.5.0", "path": "background_removal/modnet.onnx", "size": 25_901_946, "sha256": "a9edce4b47653992aacd1bee48126e65a415ed54e2ecbe51bdca25a8cab0c0d3", "licence": "MODNet Apache-2.0"},
    {"repo": "facefusion/models-3.0.0", "path": "facerestore_models/gpen_bfr_512.onnx", "size": 284_340_240, "sha256": "d5f066b9068a8b74217f9712e28e875a6144629b108a6f7355acbdb3a2832c54", "licence": "GPEN non-commercial"},
]

SWAPPER_CHOICES = ["inswapper_128", "hyperswap_1a_256", "hyperswap_1c_256", "alphaface_256", "uniface_256"]
ENHANCER_CHOICES = ["none", "gpen_bfr_256", "gfpgan_1.4", "gpen_bfr_512"]
OCCLUDER_CHOICES = ["none", "xseg_3", "xseg_2", "xseg_1"]
PARSER_CHOICES = ["none", "bisenet_resnet_34"]
MATTING_CHOICES = ["none", "modnet"]
SHAVE_CHOICES = ["none", "skin", "inpaint"]
BACKGROUND_CHOICES = ["off", "image", "green", "blur"]
CAPTURE_BACKENDS = ["auto", "DirectShow", "Media Foundation"]
VOICE_ACTIONS = ["start / open UI", "status / open UI", "stop verified service"]

_TUNING_INPUTS: dict[str, Any] = {
    "mask_blur": ["FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Weiche Kante der Box-Maske; mit Parser wirkt nur die Hälfte davon am Crop-Rand."}],
    "crop_scale": ["FLOAT", {"default": 0.8, "min": 0.6, "max": 1.2, "step": 0.05, "tooltip": "<1 weitet den ausgerichteten Crop, damit Kinn, Bart und Kiefer mit neu gerendert werden. 0.8 gemessen am besten; 0.7 wird weicher."}],
    "color_match": ["FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "LAB-Farbabgleich des getauschten Gesichts an das Kamerabild (Hautton, Licht)."}],
    "keep_mouth": ["BOOLEAN", {"default": True, "tooltip": "Echtes Mundinneres (Zähne, Zunge) behalten; Swapper öffnen den Mund sonst nur halb."}],
    "shave": [SHAVE_CHOICES, {"default": "skin", "tooltip": "Bartzone vor dem Swap glätten (skin ≈ 1 ms), damit der Swapper nackte Haut rendert; none für Bartträger als Ziel."}],
    "shave_extent": ["FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "1 = Schnurrbart und Kinn, 0.6 = nur Kinn."}],
    "enhancer_blend": ["FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Anteil des Enhancer-Ergebnisses; 0 deaktiviert den Enhancer."}],
}
_TUNING_ORDER = list(_TUNING_INPUTS)
_TUNING_DEFAULTS = [0.3, 0.8, 0.5, True, "skin", 1.0, 0.8]

_CAMERA_INPUTS: dict[str, Any] = {
    "cam_index": ["INT", {"default": 2, "min": 0, "max": 255, "tooltip": "OpenCV-Kameraindex; BRIO über DirectShow ist auf diesem Rechner Index 2."}],
    "capture_backend": [CAPTURE_BACKENDS, {"default": "DirectShow"}],
    "capture_width": ["INT", {"default": 1280, "min": 320, "max": 4096}],
    "capture_height": ["INT", {"default": 720, "min": 240, "max": 4096}],
    "mirror": ["BOOLEAN", {"default": True, "tooltip": "Spiegelt das Kamerabild wie ein Spiegel."}],
}

V100_OBJECT_INFO: dict[str, Any] = {
    "DaWastehFaceSwapModelLoader": {
        "display_name": "Face Swap Models · DirectML (DaWasteh)",
        "description": "Lädt SCRFD-Erkennung, ArcFace, Swapper, Enhancer, Occluder (xseg), Face-Parser (bisenet) und optional MODNet-Matting als ONNX-Runtime-DirectML-Sitzungen. Swapper und Enhancer laufen auf dml_device_id, Occluder/Parser/Matting parallel im Worker-Thread auf mask_device_id (Standard: die jeweils andere GPU).",
        "input": {"required": {
            "swapper": [SWAPPER_CHOICES, {"default": "hyperswap_1c_256", "tooltip": "hyperswap_1c_256: 4 ms, folgt der Mimik am besten (Standard). inswapper_128: schnell, 128 px. alphaface_256: sehr gut, aber 47 ms. uniface_256: ffhq-Crop, bildkonditioniert."}],
            "enhancer": [ENHANCER_CHOICES, {"default": "gpen_bfr_256", "tooltip": "gpen_bfr_256 (2,5 ms) ist der Live-Standard; gfpgan_1.4 (18 ms) und gpen_bfr_512 (30 ms) sind schärfer, aber langsamer."}],
            "occluder": [OCCLUDER_CHOICES, {"default": "xseg_3", "tooltip": "Hände und Gegenstände vor dem Gesicht bleiben sichtbar. xseg_3 behält Bart, Mundinneres und Brillengläser als Gesicht; xseg_1 schneidet sie aus."}],
            "parser": [PARSER_CHOICES, {"default": "bisenet_resnet_34", "tooltip": "Gesichtsregionen für Einblendmaske, Mundmaske und Rasur (8 ms)."}],
            "matting": [MATTING_CHOICES, {"default": "none", "tooltip": "Personen-Matting für Workflow 17 (Hintergrund ersetzen); modnet 512 px, ca. 6 ms."}],
            "dml_device_id": ["INT", {"default": 1, "min": 0, "max": 7, "tooltip": "DirectML-Adapter für Erkennung, Swapper und Enhancer; 1 = R9700, 0 = RX 9070 XT."}],
            "mask_device_id": ["INT", {"default": 0, "min": 0, "max": 7, "tooltip": "DirectML-Adapter für Occluder, Parser und Matting (Worker-Thread); die andere GPU ist am schnellsten."}],
            "det_size": [[320, 480, 640], {"default": 320, "tooltip": "SCRFD-Erkennungsgröße; 320 für Live, 640 für weit entfernte oder kleine Gesichter."}],
            "det_threshold": ["FLOAT", {"default": 0.5, "min": 0.1, "max": 0.95, "step": 0.05, "tooltip": "Mindest-Erkennungsscore."}],
        }},
        "input_order": {"required": ["swapper", "enhancer", "occluder", "parser", "matting", "dml_device_id", "mask_device_id", "det_size", "det_threshold"]},
        "output": ["DAW_FACESWAP"],
        "output_name": ["face_swap"],
    },
    "DaWastehFaceSwapIdentity": {
        "display_name": "Face Swap Identity from Images (DaWasteh)",
        "description": "Mittelt die ArcFace-Identität des größten Gesichts aus einem oder mehreren freigegebenen Zielfotos. Bis zu vier IMAGE-Eingänge (jeder darf ein Batch sein); mehrere Ansichten (frontal, Dreiviertel, lächelnd, Mund offen) stabilisieren die Identität.",
        "input": {
            "required": {"face_swap": ["DAW_FACESWAP"], "source_images": ["IMAGE"]},
            "optional": {"more_images": ["IMAGE"], "more_images_2": ["IMAGE"], "more_images_3": ["IMAGE"]},
        },
        "input_order": {"required": ["face_swap", "source_images"], "optional": ["more_images", "more_images_2", "more_images_3"]},
        "output": ["DAW_FACE_IDENTITY", "STRING"],
        "output_name": ["identity", "summary"],
    },
    "DaWastehFaceSwapIdentityFromFolder": {
        "display_name": "Face Swap Identity from Folder (DaWasteh)",
        "description": "Mittelt die Identität über alle Fotos eines Unterordners von ComfyUI/input (z. B. input/face-swap-identity mit 5–20 Fotos der Zielperson).",
        "input": {"required": {
            "face_swap": ["DAW_FACESWAP"],
            "folder": [["face-swap-identity"], {"default": "face-swap-identity", "tooltip": "Unterordner von ComfyUI/input mit Fotos der Zielperson."}],
        }},
        "input_order": {"required": ["face_swap", "folder"]},
        "output": ["DAW_FACE_IDENTITY", "STRING"],
        "output_name": ["identity", "summary"],
    },
    "DaWastehWebcamSnapshot": {
        "display_name": "Webcam Snapshot / Clean Plate (DaWasteh)",
        "description": "Nimmt nach einer Wartezeit Bilder von der Webcam auf: als Testbild von dir selbst für die Vorschau oder als leere Hintergrundplatte (aus dem Bild gehen) für Workflow 17. Das Ergebnis wird gecacht; retake erhöhen, um neu aufzunehmen.",
        "input": {"required": {
            **_CAMERA_INPUTS,
            "delay_seconds": ["FLOAT", {"default": 3.0, "min": 0.0, "max": 30.0, "step": 0.5, "tooltip": "Zeit, um aus dem Bild zu gehen (Clean Plate) oder sich zu positionieren."}],
            "frames": ["INT", {"default": 1, "min": 1, "max": 16}],
            "frame_interval_seconds": ["FLOAT", {"default": 1.0, "min": 0.1, "max": 10.0, "step": 0.1}],
            "retake": ["INT", {"default": 0, "min": 0, "max": 1000000, "tooltip": "Wert ändern, um neu aufzunehmen; sonst bleibt die letzte Aufnahme gecacht."}],
        }},
        "input_order": {"required": [*_CAMERA_INPUTS, "delay_seconds", "frames", "frame_interval_seconds", "retake"]},
        "output": ["IMAGE"],
        "output_name": ["image"],
    },
    "DaWastehFaceSwapImage": {
        "display_name": "Face Swap Image Preview (DaWasteh)",
        "description": "Offline-Vorschau: tauscht das Gesicht in jedem Bild eines IMAGE-Batches (optional mit Matting auf eine Hintergrundplatte) und meldet die Millisekunden pro Stufe. Einstellungen hier prüfen, bevor der Live-Node startet.",
        "input": {
            "required": {
                "face_swap": ["DAW_FACESWAP"],
                "identity": ["DAW_FACE_IDENTITY"],
                "image": ["IMAGE"],
                **_TUNING_INPUTS,
                "background_mode": [BACKGROUND_CHOICES, {"default": "off", "tooltip": "image = auf die Hintergrundplatte legen (Matting im Loader nötig); green = Greenscreen; blur = unscharfer Kamerahintergrund."}],
            },
            "optional": {"background": ["IMAGE"]},
        },
        "input_order": {"required": ["face_swap", "identity", "image", *_TUNING_ORDER, "background_mode"], "optional": ["background"]},
        "output": ["IMAGE", "STRING"],
        "output_name": ["image", "timing"],
    },
    "DaWastehLiveFaceSwap": {
        "display_name": "Live Face Swap Webcam → Spout (DaWasteh)",
        "description": "Kontinuierlicher DirectML-Face-Swap des Webcam-Bildes (optional mit Personen-Matting auf eine Hintergrundplatte) in einen Spout-Sender für OBS. Einmal normal ausführen und mit Interrupt beenden; niemals Run (Instant). Blockiert andere ComfyUI-Jobs, solange er läuft.",
        "input": {
            "required": {
                "face_swap": ["DAW_FACESWAP"],
                "identity": ["DAW_FACE_IDENTITY"],
                "sender_name": ["STRING", {"default": SENDER_NAME, "tooltip": "Spout-Sendername in OBS."}],
                "sender_fps": ["INT", {"default": 30, "min": 1, "max": 60, "tooltip": "Präsentationsrate des Spout-Senders (wiederholt das letzte Bild)."}],
                **_CAMERA_INPUTS,
                **_TUNING_INPUTS,
                "landmark_smoothing": ["FLOAT", {"default": 0.5, "min": 0.0, "max": 0.95, "step": 0.05, "tooltip": "Zeitliche Glättung der fünf Landmarken gegen Zittern; setzt sich bei schnellen Kopfbewegungen zurück."}],
                "enhancer_every": ["INT", {"default": 1, "min": 1, "max": 10, "tooltip": "Enhancer nur jedes n-te Bild ausführen, wenn die Bildrate sonst nicht reicht."}],
                "parser_every": ["INT", {"default": 1, "min": 1, "max": 4, "tooltip": "Gesichtsregionen nur jedes n-te Bild neu parsen (2 hebt die Bildrate, wenn Matting oder der RVC-Dienst die Masken-GPU teilen)."}],
                "background_mode": [BACKGROUND_CHOICES, {"default": "off", "tooltip": "image = auf die Hintergrundplatte legen (Matting im Loader nötig); wer aus dem Bild geht, verschwindet."}],
                "max_frames": ["INT", {"default": 0, "min": 0, "max": 1000000, "tooltip": "0 = bis Interrupt; sonst Testlauf mit fester Bildzahl."}],
                "metrics_json_path": ["STRING", {"default": "live-face-swap/metrics.json", "tooltip": "Metrik-JSON relativ zu L:/ComfyUI/logs."}],
            },
            "optional": {"background": ["IMAGE"]},
        },
        "input_order": {"required": [
            "face_swap", "identity", "sender_name", "sender_fps", *_CAMERA_INPUTS, *_TUNING_ORDER,
            "landmark_smoothing", "enhancer_every", "parser_every", "background_mode", "max_frames", "metrics_json_path",
        ], "optional": ["background"]},
        "output": [],
        "output_name": [],
    },
}

# Kept out of V100_OBJECT_INFO on purpose: the v0.9.5 RVC control workflow is
# committed without generated notes for this node and must reconstruct exactly.
VOICE_LAUNCHER_SCHEMA: dict[str, Any] = {
    "display_name": "DirectML RVC Live Voice Swap Launcher (DaWasteh)",
    "description": "Startet, prüft oder stoppt ausschließlich den hash-verifizierten lokalen DirectML-RVC-Dienst (MMVCServerSIO b2332) für die Live-Stimme; die Stimme läuft neben dem Bild-Swap auf der RX 9070 XT.",
    "input": {"required": {
        "action": [VOICE_ACTIONS, {}],
        "install_path": ["STRING", {"default": VOICE_INSTALL_PATH}],
        "open_browser": ["BOOLEAN", {"default": True}],
    }},
    "input_order": {"required": ["action", "install_path", "open_browser"]},
    "output": ["STRING", "STRING", "INT"],
    "output_name": ["status", "ui_url", "process_id"],
}


README_16_HTML = (
    "<h1>Workflow 16 · Live Face Swap (DirectML) → Spout → OBS · v1.0.0</h1>"
    "<p>Behält das echte Kamerabild und tauscht nur die Gesichtsidentität: BRIO 1280×720 (DirectShow-Index 2) → SCRFD → <code>hyperswap_1c_256</code> auf einem 0,8×-Crop → "
    "xseg_3-Occluder (Hände bleiben sichtbar) ∧ bisenet-Regionsmaske (echtes Mundinneres bleibt) → LAB-Farbabgleich → GPEN-BFR-256 → Spout <code>ComfyLiveFaceSwap</code>. "
    "Die Bartzone wird vor dem Swap digital rasiert, damit der Swapper nackte Haut rendert. Occluder, Parser und Matting laufen im Worker-Thread auf der anderen GPU. "
    "Gemessen auf 150 BRIO-Frames dieses Rechners: 26 KI-Bilder/s ohne, rund 22 mit Matting.</p>"
    "<h2>Zielidentität · mehrere Fotos</h2>"
    "<p>Der Node <b>Face Swap Identity from Images</b> hat vier IMAGE-Eingänge (<code>source_images</code>, <code>more_images</code>, <code>more_images_2</code>, <code>more_images_3</code>); jeder darf ein Batch sein. "
    "Drei LoadImage-Nodes mit frontal, Dreiviertel links und rechts sind vorverdrahtet. Für 5–20 Fotos den Node <b>Face Swap Identity from Folder</b> nehmen: Fotos nach <code>ComfyUI/input/face-swap-identity/</code> legen und den Ordner wählen.</p>"
    "<h2>Testbild</h2>"
    "<p>Das Testbild ist ein Bild <b>von dir</b>, so wie die Kamera dich sieht: Der Node <b>Webcam Snapshot</b> nimmt es nach 3 s auf (einmal Run, danach gecacht; <code>retake</code> ändern für ein neues). "
    "Die Vorschau zeigt darauf den Swap mit allen Einstellungen und die Millisekunden je Stufe.</p>"
    "<h2>Live</h2>"
    "<ol><li>Vorschau prüfen (<b>Run</b>), Regler anpassen: <code>crop_scale</code> 0,8, <code>color_match</code> 0,5, <code>keep_mouth</code> an, <code>shave</code> skin.</li>"
    "<li>Live-Node <b>Bypass</b> aufheben, OBS-Spout-Quelle <code>ComfyLiveFaceSwap</code> anlegen, einmal <b>Run</b>. Beenden nur mit <b>Interrupt</b>; nie Run (Instant).</li></ol>"
    "<h2>Grenzen</h2>"
    "<p>Körper, Kleidung, Haare und Statur bleiben deine; nur das Gesicht wird ersetzt (Workflow 17 ersetzt zusätzlich den Hintergrund). "
    "Lizenzen: hyperswap ResearchRAIL, inswapper/GPEN/buffalo_l nicht-kommerziell, xseg GPL-3.0, bisenet MIT, GFPGAN Apache-2.0. Nur eigene oder ausdrücklich freigegebene Gesichter verwenden und die Synthese im Stream kennzeichnen.</p>"
)

README_17_HTML = (
    "<h1>Workflow 17 · Live Person Swap · Gesicht + Hintergrund + Stimme · v1.0.0</h1>"
    "<p>Erweitert Workflow 16 um MODNet-Personen-Matting: Das getauschte Gesicht samt deinem Körper wird auf eine <b>leere Hintergrundplatte</b> gelegt. Gehst du aus dem Bild, ist niemand mehr da. "
    "Der DirectML-RVC-Launcher startet parallel die Live-Stimme (eigenes RVC-Modell nötig, siehe Voice-Design-Workflows). Spout-Sender: <code>ComfyLivePersonSwap</code>.</p>"
    "<h2>Ablauf</h2>"
    "<ol><li><b>Clean Plate</b>: Beim ersten Run wartet der obere Snapshot-Node 8 s, in denen du aus dem Bild gehst; die Platte bleibt gecacht (<code>retake</code> ändern für eine neue).</li>"
    "<li><b>Testbild</b>: Der zweite Snapshot-Node nimmt dich nach weiteren 3 s auf; die Vorschau zeigt Swap + Matting auf der Platte.</li>"
    "<li>Live-Node <b>Bypass</b> aufheben, OBS-Spout-Quelle <code>ComfyLivePersonSwap</code>, einmal <b>Run</b>, Ende mit <b>Interrupt</b>.</li></ol>"
    "<h2>Was auf dieser Hardware nicht geht</h2>"
    "<p>Ein Ganzkörpertausch (andere Statur, andere Kleidung, andere Frisur) in Echtzeit ist auf RDNA4 ohne Flimmern nicht möglich: Diffusions-Bildspiegel liefern 0,4–1,6 Bilder/s ohne zeitliche Konsistenz (Workflow 07/11), Reenactment (LivePortrait) animiert nur ein Standbild. "
    "Realistisch bleibt deshalb: echtes Kamerabild, getauschtes Gesicht, ersetzter Hintergrund. Für einen anderen Körper braucht es einen 3D-Avatar (Workflow 06/12-III) mit stilisiertem Look.</p>"
    "<h2>Hardware</h2>"
    "<p>Swapper/Enhancer auf DirectML-Gerät 1 (R9700, wie Spout/OBS), Occluder/Parser/Matting auf Gerät 0 (RX 9070 XT) im Worker-Thread. Die Stimme läuft im RVC-Dienst auf der RX 9070 XT. "
    "MODNet (Apache-2.0) ist ein Porträt-Matting; Haare und Hände sind gut, feine Gegenstände in der Hand können weich werden.</p>"
)


def _widget_inputs(schema: dict[str, Any], skip: set[str]) -> list[dict[str, Any]]:
    inputs = []
    for name in schema["input_order"]["required"]:
        if name in skip:
            continue
        kind = schema["input"]["required"][name][0]
        widget_type = "COMBO" if isinstance(kind, list) else kind
        inputs.append({"localized_name": name, "name": name, "type": widget_type, "widget": {"name": name}, "link": None})
    return inputs


def _load_image_node(node_id: int, title: str, pos: list[float], order: int, image: str, links: list[int]) -> dict[str, Any]:
    return _node(node_id, "LoadImage", title, pos, [430, 500], order,
                 [{"localized_name": "image", "name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}},
                  {"localized_name": "upload", "name": "upload", "type": "IMAGEUPLOAD", "link": None, "widget": {"name": "upload"}}],
                 [_output("IMAGE", "IMAGE", links, 0), _output("MASK", "MASK", [], 1)],
                 [image, "image"], cnr="comfy-core")


def _note_node(title: str, html: str, size: list[float]) -> dict[str, Any]:
    return {
        "id": 1, "type": "PixaromaNote", "pos": [40.0, 80.0], "size": size, "flags": {}, "order": 0, "mode": 0,
        "inputs": [{"localized_name": "note_json", "name": "note_json", "type": "STRING", "link": None, "widget": {"name": "note_json"}}],
        "outputs": [], "title": title,
        "properties": {"Node name for S&R": "PixaromaNote", "cnr_id": "ComfyUI-Pixaroma"},
        "widgets_values": [json.dumps({"version": 1, "content": html}, ensure_ascii=False), ""],
        "color": "#1d1d1d", "bgcolor": "#2a2a2a",
    }


def _snapshot_widgets(delay: float) -> list[Any]:
    return [2, "DirectShow", 1280, 720, True, delay, 1, 1.0, 0]


def _live_widgets(sender: str, background_mode: str, parser_every: int = 1) -> list[Any]:
    return [sender, 30, 2, "DirectShow", 1280, 720, True, *_TUNING_DEFAULTS, 0.5, 1, parser_every, background_mode, 0, "live-face-swap/metrics.json"]


def build_face_swap_template() -> dict[str, Any]:
    """Workflow 16 (v1.0.0): three identity photos, webcam test shot, tuned live node."""
    loader = V100_OBJECT_INFO["DaWastehFaceSwapModelLoader"]
    preview = V100_OBJECT_INFO["DaWastehFaceSwapImage"]
    live = V100_OBJECT_INFO["DaWastehLiveFaceSwap"]
    snapshot = V100_OBJECT_INFO["DaWastehWebcamSnapshot"]
    nodes = [
        _note_node("Workflow 16 · Live Face Swap v1.0.0 · Bedienung, mehrere Fotos, Testbild, Grenzen", README_16_HTML, [820, 1000]),
        _load_image_node(2, "Zielidentität 1 · frontal", [1000.0, 80.0], 1, SOURCE_IMAGES[0], [2]),
        _load_image_node(3, "Zielidentität 2 · Dreiviertel links", [1000.0, 640.0], 2, SOURCE_IMAGES[1], [3]),
        _load_image_node(4, "Zielidentität 3 · Dreiviertel rechts", [1000.0, 1200.0], 3, SOURCE_IMAGES[2], [4]),
        _node(5, "DaWastehFaceSwapModelLoader", "Face-Swap-Modelle · Swapper auf DML 1 (R9700), Masken auf DML 0 (RX 9070 XT)", [1520.0, 80.0], [460, 300], 4,
              _widget_inputs(loader, set()),
              [_output("face_swap", "DAW_FACESWAP", [1, 6, 10], 0)],
              ["hyperswap_1c_256", "gpen_bfr_256", "xseg_3", "bisenet_resnet_34", "none", 1, 0, 320, 0.5]),
        _node(6, "DaWastehFaceSwapIdentity", "Identität aus 3 Zielfotos (bis zu 4 Eingänge, je Batch)", [1520.0, 460.0], [420, 180], 5,
              [_link_input("face_swap", "DAW_FACESWAP", 1), _link_input("source_images", "IMAGE", 2),
               _link_input("more_images", "IMAGE", 3), _link_input("more_images_2", "IMAGE", 4), _link_input("more_images_3", "IMAGE", None)],
              [_output("identity", "DAW_FACE_IDENTITY", [7, 11], 0), _output("summary", "STRING", [5], 1)],
              []),
        _node(7, "PreviewAny", "Identitäts-Zusammenfassung", [1520.0, 700.0], [420, 120], 6,
              [_link_input("source", "*", 5)], [], [], cnr="comfy-core"),
        _node(8, "DaWastehWebcamSnapshot", "Testbild von dir · BRIO nach 3 s (gecacht, retake ändern)", [1520.0, 880.0], [420, 300], 7,
              _widget_inputs(snapshot, set()),
              [_output("image", "IMAGE", [8], 0)],
              _snapshot_widgets(3.0)),
        _node(9, "DaWastehFaceSwapImage", "Vorschau-Swap · Regler hier prüfen", [2040.0, 80.0], [460, 360], 8,
              [_link_input("face_swap", "DAW_FACESWAP", 6), _link_input("identity", "DAW_FACE_IDENTITY", 7), _link_input("image", "IMAGE", 8),
               *_widget_inputs(preview, {"face_swap", "identity", "image"}), _link_input("background", "IMAGE", None)],
              [_output("image", "IMAGE", [9], 0), _output("timing", "STRING", [12], 1)],
              [*_TUNING_DEFAULTS, "off"]),
        _node(10, "PreviewImage", "Vorschau · getauschtes Gesicht", [2560.0, 80.0], [520, 560], 9,
              [_link_input("images", "IMAGE", 9)], [], [], cnr="comfy-core"),
        _node(11, "PreviewAny", "Millisekunden · Erkennung / Swap / Maske / Enhancer", [2560.0, 700.0], [520, 120], 10,
              [_link_input("source", "*", 12)], [], [], cnr="comfy-core"),
        _node(12, "DaWastehLiveFaceSwap", "LIVE · BRIO → Face Swap → Spout ComfyLiveFaceSwap (Bypass aufheben)", [3140.0, 80.0], [500, 760], 11,
              [_link_input("face_swap", "DAW_FACESWAP", 10), _link_input("identity", "DAW_FACE_IDENTITY", 11),
               *_widget_inputs(live, {"face_swap", "identity"}), _link_input("background", "IMAGE", None)],
              [],
              _live_widgets(SENDER_NAME, "off"),
              mode=4),
    ]
    links = [
        [1, 5, 0, 6, 0, "DAW_FACESWAP"],
        [2, 2, 0, 6, 1, "IMAGE"],
        [3, 3, 0, 6, 2, "IMAGE"],
        [4, 4, 0, 6, 3, "IMAGE"],
        [5, 6, 1, 7, 0, "STRING"],
        [6, 5, 0, 9, 0, "DAW_FACESWAP"],
        [7, 6, 0, 9, 1, "DAW_FACE_IDENTITY"],
        [8, 8, 0, 9, 2, "IMAGE"],
        [9, 9, 0, 10, 0, "IMAGE"],
        [10, 5, 0, 12, 0, "DAW_FACESWAP"],
        [11, 6, 0, 12, 1, "DAW_FACE_IDENTITY"],
        [12, 9, 1, 11, 0, "STRING"],
    ]
    return _graph("c7f1d2a0-4b6e-4c0a-9d3e-16f1a7c1e100", nodes, links, 12, 12)


def build_person_swap_template() -> dict[str, Any]:
    """Workflow 17: face swap + MODNet matting onto a clean plate + RVC voice launcher."""
    loader = V100_OBJECT_INFO["DaWastehFaceSwapModelLoader"]
    preview = V100_OBJECT_INFO["DaWastehFaceSwapImage"]
    live = V100_OBJECT_INFO["DaWastehLiveFaceSwap"]
    snapshot = V100_OBJECT_INFO["DaWastehWebcamSnapshot"]
    voice = VOICE_LAUNCHER_SCHEMA
    nodes = [
        _note_node("Workflow 17 · Live Person Swap v1.0.0 · Gesicht + Hintergrund + Stimme", README_17_HTML, [820, 1000]),
        _load_image_node(2, "Zielidentität 1 · frontal", [1000.0, 80.0], 1, SOURCE_IMAGES[0], [2]),
        _load_image_node(3, "Zielidentität 2 · Dreiviertel links", [1000.0, 640.0], 2, SOURCE_IMAGES[1], [3]),
        _load_image_node(4, "Zielidentität 3 · Dreiviertel rechts", [1000.0, 1200.0], 3, SOURCE_IMAGES[2], [4]),
        _node(5, "DaWastehFaceSwapModelLoader", "Face-Swap-Modelle + MODNet-Matting · Swapper DML 1, Masken DML 0", [1520.0, 80.0], [460, 300], 4,
              _widget_inputs(loader, set()),
              [_output("face_swap", "DAW_FACESWAP", [1, 6, 10], 0)],
              ["hyperswap_1c_256", "gpen_bfr_256", "xseg_3", "bisenet_resnet_34", "modnet", 1, 0, 320, 0.5]),
        _node(6, "DaWastehFaceSwapIdentity", "Identität aus 3 Zielfotos (bis zu 4 Eingänge, je Batch)", [1520.0, 460.0], [420, 180], 5,
              [_link_input("face_swap", "DAW_FACESWAP", 1), _link_input("source_images", "IMAGE", 2),
               _link_input("more_images", "IMAGE", 3), _link_input("more_images_2", "IMAGE", 4), _link_input("more_images_3", "IMAGE", None)],
              [_output("identity", "DAW_FACE_IDENTITY", [7, 11], 0), _output("summary", "STRING", [5], 1)],
              []),
        _node(7, "PreviewAny", "Identitäts-Zusammenfassung", [1520.0, 700.0], [420, 120], 6,
              [_link_input("source", "*", 5)], [], [], cnr="comfy-core"),
        _node(8, "DaWastehWebcamSnapshot", "CLEAN PLATE · leerer Raum · 8 s aus dem Bild gehen (gecacht, retake ändern)", [1520.0, 880.0], [420, 300], 7,
              _widget_inputs(snapshot, set()),
              [_output("image", "IMAGE", [13, 14], 0)],
              _snapshot_widgets(8.0)),
        _node(9, "DaWastehWebcamSnapshot", "Testbild von dir · BRIO nach 3 s (gecacht, retake ändern)", [1520.0, 1240.0], [420, 300], 8,
              _widget_inputs(snapshot, set()),
              [_output("image", "IMAGE", [8], 0)],
              _snapshot_widgets(3.0)),
        _node(10, "DaWastehFaceSwapImage", "Vorschau · Swap + Matting auf Clean Plate", [2040.0, 80.0], [460, 360], 9,
              [_link_input("face_swap", "DAW_FACESWAP", 6), _link_input("identity", "DAW_FACE_IDENTITY", 7), _link_input("image", "IMAGE", 8),
               *_widget_inputs(preview, {"face_swap", "identity", "image"}), _link_input("background", "IMAGE", 13)],
              [_output("image", "IMAGE", [9], 0), _output("timing", "STRING", [12], 1)],
              [*_TUNING_DEFAULTS, "image"]),
        _node(11, "PreviewImage", "Vorschau · Person auf leerem Raum", [2560.0, 80.0], [520, 560], 10,
              [_link_input("images", "IMAGE", 9)], [], [], cnr="comfy-core"),
        _node(12, "PreviewAny", "Millisekunden · Erkennung / Swap / Maske / Enhancer / Matting", [2560.0, 700.0], [520, 120], 11,
              [_link_input("source", "*", 12)], [], [], cnr="comfy-core"),
        _node(13, "DaWastehLiveVoiceSwapLauncher", "STIMME · DirectML-RVC-Dienst starten (RX 9070 XT)", [2560.0, 880.0], [520, 200], 12,
              _widget_inputs(voice, set()),
              [_output("status", "STRING", [], 0), _output("ui_url", "STRING", [], 1), _output("process_id", "INT", [], 2)],
              ["start / open UI", VOICE_INSTALL_PATH, False]),
        _node(14, "DaWastehLiveFaceSwap", "LIVE · BRIO → Face Swap + Matting → Spout ComfyLivePersonSwap (Bypass aufheben)", [3140.0, 80.0], [500, 800], 13,
              [_link_input("face_swap", "DAW_FACESWAP", 10), _link_input("identity", "DAW_FACE_IDENTITY", 11),
               *_widget_inputs(live, {"face_swap", "identity"}), _link_input("background", "IMAGE", 14)],
              [],
              _live_widgets(PERSON_SENDER_NAME, "image", parser_every=2),
              mode=4),
    ]
    links = [
        [1, 5, 0, 6, 0, "DAW_FACESWAP"],
        [2, 2, 0, 6, 1, "IMAGE"],
        [3, 3, 0, 6, 2, "IMAGE"],
        [4, 4, 0, 6, 3, "IMAGE"],
        [5, 6, 1, 7, 0, "STRING"],
        [6, 5, 0, 10, 0, "DAW_FACESWAP"],
        [7, 6, 0, 10, 1, "DAW_FACE_IDENTITY"],
        [8, 9, 0, 10, 2, "IMAGE"],
        [9, 10, 0, 11, 0, "IMAGE"],
        [10, 5, 0, 14, 0, "DAW_FACESWAP"],
        [11, 6, 0, 14, 1, "DAW_FACE_IDENTITY"],
        [12, 10, 1, 12, 0, "STRING"],
        [13, 8, 0, 10, 3 + len(_TUNING_ORDER) + 1, "IMAGE"],  # background sits after the widget inputs
        [14, 8, 0, 14, 2 + len(_CAMERA_INPUTS) + 2 + len(_TUNING_ORDER) + 6, "IMAGE"],
    ]
    return _graph("d8a2e3b1-5c7f-4d1b-8e4f-27a2b8d2f117", nodes, links, 14, 14)


def _graph(graph_id: str, nodes: list[dict[str, Any]], links: list[list[Any]], last_node: int, last_link: int) -> dict[str, Any]:
    return {
        "id": graph_id,
        "revision": 0,
        "last_node_id": last_node,
        "last_link_id": last_link,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.5, "offset": [0, 0]}, "frontendVersion": "1.51.9", UPGRADE_KEY: {"version": UPGRADE_VERSION, "release": "v1.0.0"}},
        "version": 0.4,
    }


TEMPLATES = {
    FACE_SWAP_TEMPLATE: (build_face_swap_template, FACE_SWAP_TEMPLATE_SHA256),
    PERSON_SWAP_TEMPLATE: (build_person_swap_template, PERSON_SWAP_TEMPLATE_SHA256),
}


def template_bytes(name: str) -> bytes:
    builder, _ = TEMPLATES[name]
    return (json.dumps(builder(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write both templates under tools/workflow_templates")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent / "workflow_templates"
    for name, (_, pinned) in TEMPLATES.items():
        payload = template_bytes(name)
        digest = hashlib.sha256(payload).hexdigest()
        if args.write:
            (folder / name).write_bytes(payload)
            print(f"wrote {folder / name} sha256={digest}")
        else:
            print(f"{name}: sha256={digest} pinned={pinned} match={digest == pinned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
