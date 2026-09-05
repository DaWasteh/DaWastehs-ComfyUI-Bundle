#!/usr/bin/env python3
"""Deterministic v0.9.9 addition: Live Face Swap (DirectML) → Spout → OBS.

The template is generated here (not exported from a browser), pinned by SHA-256
under ``tools/workflow_templates`` and turned into the canonical workflow by the
regular v0.9.2 migration (central GPU control, parameter notes, RODENT layout).
Live Avatar workflows stay timer-free by user decision.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


UPGRADE_KEY = "dawasteh_v099_live_face_swap"
UPGRADE_VERSION = 1
FACE_SWAP_PATH = "Live Avatar/LiveAvatar-16-Live-Face-Swap-DirectML-Spout-OBS.json"
SOURCE_TEMPLATE = "live_face_swap_directml.json"
SOURCE_TEMPLATE_SHA256 = "b0a81c21bde4ba374c569b52135dc5db21dfd7fd7f69b7d704d7e9ae9e37bbda"

SOURCE_IMAGE = "13_smile_closeup_img00031_00001_.png"
PREVIEW_IMAGE = "13_three_quarter_left_00001_.png"
SENDER_NAME = "ComfyLiveFaceSwap"

MODEL_FILES = [
    {"repo": "facefusion/models-3.0.0", "path": "insightface/inswapper_128.onnx", "size": 555_303_150, "sha256": "a290273ed497312095dac48cdef20feec9d5208298223dd01288ab202b54bea7", "licence": "InsightFace non-commercial"},
    {"repo": "facefusion/models-3.3.0", "path": "insightface/hyperswap_1a_256.onnx", "size": 402_742_682, "sha256": "c0e98a8a03a238f461ed3d2570e426b49f46745ee400854a60dceeb70c246add", "licence": "FaceFusion ResearchRAIL"},
    {"repo": "facefusion/models-3.0.0", "path": "facerestore_models/gfpgan_1.4.onnx", "size": 340_299_087, "sha256": "accc4757b26bdb89b32b4d3500d4f79c9dff97c1dd7c7104bf9dcb95e3311385", "licence": "Apache-2.0"},
    {"repo": "facefusion/models-3.0.0", "path": "facerestore_models/gpen_bfr_256.onnx", "size": 75_792_988, "sha256": "bad8bf0426873828df2dbf4e3b3d9ababba9da7965b8b72426569486f7ae5c25", "licence": "GPEN non-commercial"},
    {"repo": "deepinsight/insightface release v0.7", "path": "insightface/models/buffalo_l (buffalo_l.zip)", "size": 288_621_354, "sha256": "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f", "licence": "InsightFace non-commercial research"},
]

V099_OBJECT_INFO: dict[str, Any] = {
    "DaWastehFaceSwapModelLoader": {
        "display_name": "Face Swap Models · DirectML (DaWasteh)",
        "description": "Lädt InsightFace-buffalo_l-Erkennung, den Swapper und optional einen Face-Enhancer als ONNX-Sitzungen auf einem DirectML-Adapter. Auf diesem Rechner ist DirectML-Gerät 1 die R9700 (Spout/OBS) und 0 die RX 9070 XT.",
        "input": {"required": {
            "swapper": [["inswapper_128", "hyperswap_1a_256"], {"default": "inswapper_128", "tooltip": "inswapper_128: schnell, stabil, 128 px. hyperswap_1a_256: 256 px, mehr Detail, ResearchRAIL-Lizenz."}],
            "enhancer": [["none", "gpen_bfr_256", "gfpgan_1.4"], {"default": "none", "tooltip": "Face-Enhancer nach dem Swap. gpen_bfr_256 ist der schnelle Live-Kandidat, gfpgan_1.4 der schärfere 512-px-Pfad."}],
            "dml_device_id": ["INT", {"default": 1, "min": 0, "max": 7, "tooltip": "DirectML-Adapterindex; 1 = R9700, 0 = RX 9070 XT."}],
            "det_size": [[320, 480, 640], {"default": 320, "tooltip": "SCRFD-Erkennungsgröße; 320 für Live, 640 für weit entfernte oder kleine Gesichter."}],
            "det_threshold": ["FLOAT", {"default": 0.5, "min": 0.1, "max": 0.95, "step": 0.05, "tooltip": "Mindest-Erkennungsscore."}],
        }},
        "input_order": {"required": ["swapper", "enhancer", "dml_device_id", "det_size", "det_threshold"]},
        "output": ["DAW_FACESWAP"],
        "output_name": ["face_swap"],
    },
    "DaWastehFaceSwapIdentity": {
        "display_name": "Face Swap Identity from Images (DaWasteh)",
        "description": "Mittelt die ArcFace-Identität des größten Gesichts aus einem oder mehreren freigegebenen Quellbildern; mehrere Ansichten stabilisieren die Identität.",
        "input": {"required": {"face_swap": ["DAW_FACESWAP"], "source_images": ["IMAGE"]}},
        "input_order": {"required": ["face_swap", "source_images"]},
        "output": ["DAW_FACE_IDENTITY", "STRING"],
        "output_name": ["identity", "summary"],
    },
    "DaWastehFaceSwapImage": {
        "display_name": "Face Swap Image Preview (DaWasteh)",
        "description": "Offline-Vorschau: tauscht das Gesicht in jedem Bild eines IMAGE-Batches und meldet die Millisekunden pro Stufe. Einstellungen hier prüfen, bevor der Live-Node startet.",
        "input": {"required": {
            "face_swap": ["DAW_FACESWAP"],
            "identity": ["DAW_FACE_IDENTITY"],
            "image": ["IMAGE"],
            "mask_blur": ["FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Weiche Kante der Einblendmaske als Anteil der Gesichtsgröße."}],
            "enhancer_blend": ["FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Anteil des Enhancer-Ergebnisses; 0 deaktiviert den Enhancer."}],
        }},
        "input_order": {"required": ["face_swap", "identity", "image", "mask_blur", "enhancer_blend"]},
        "output": ["IMAGE", "STRING"],
        "output_name": ["image", "timing"],
    },
    "DaWastehLiveFaceSwap": {
        "display_name": "Live Face Swap Webcam → Spout (DaWasteh)",
        "description": "Kontinuierlicher DirectML-Face-Swap des Webcam-Bildes in einen Spout-Sender für OBS. Einmal normal ausführen und mit Interrupt beenden; niemals Run (Instant). Blockiert andere ComfyUI-Jobs, solange er läuft.",
        "input": {"required": {
            "face_swap": ["DAW_FACESWAP"],
            "identity": ["DAW_FACE_IDENTITY"],
            "sender_name": ["STRING", {"default": SENDER_NAME, "tooltip": "Spout-Sendername in OBS."}],
            "sender_fps": ["INT", {"default": 30, "min": 1, "max": 60, "tooltip": "Präsentationsrate des Spout-Senders (wiederholt das letzte Bild)."}],
            "cam_index": ["INT", {"default": 2, "min": 0, "max": 255, "tooltip": "OpenCV-Kameraindex; BRIO über DirectShow ist auf diesem Rechner Index 2."}],
            "capture_backend": [["auto", "DirectShow", "Media Foundation"], {"default": "DirectShow"}],
            "capture_width": ["INT", {"default": 1280, "min": 320, "max": 4096}],
            "capture_height": ["INT", {"default": 720, "min": 240, "max": 4096}],
            "mirror": ["BOOLEAN", {"default": True, "tooltip": "Spiegelt das Kamerabild wie ein Spiegel."}],
            "mask_blur": ["FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05}],
            "landmark_smoothing": ["FLOAT", {"default": 0.5, "min": 0.0, "max": 0.95, "step": 0.05, "tooltip": "Zeitliche Glättung der fünf Landmarken gegen Zittern; setzt sich bei schnellen Kopfbewegungen zurück."}],
            "enhancer_blend": ["FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}],
            "enhancer_every": ["INT", {"default": 1, "min": 1, "max": 10, "tooltip": "Enhancer nur jedes n-te Bild ausführen, wenn die Bildrate sonst nicht reicht."}],
            "max_frames": ["INT", {"default": 0, "min": 0, "max": 1000000, "tooltip": "0 = bis Interrupt; sonst Testlauf mit fester Bildzahl."}],
            "metrics_json_path": ["STRING", {"default": "live-face-swap/metrics.json", "tooltip": "Metrik-JSON relativ zu L:/ComfyUI/logs."}],
        }},
        "input_order": {"required": [
            "face_swap", "identity", "sender_name", "sender_fps", "cam_index", "capture_backend", "capture_width",
            "capture_height", "mirror", "mask_blur", "landmark_smoothing", "enhancer_blend", "enhancer_every",
            "max_frames", "metrics_json_path",
        ]},
        "output": [],
        "output_name": [],
    },
}

README_HTML = (
    "<h1>Workflow 16 · Live Face Swap (DirectML) → Spout → OBS</h1>"
    "<p>Echter Echtzeit-Identitätstausch statt LivePortrait-Reenactment oder SD1.5-Diffusion: Die BRIO liefert 1280×720 über DirectShow (Index 2), "
    "InsightFace SCRFD findet das Gesicht, <code>inswapper_128</code> oder <code>hyperswap_1a_256</code> tauscht die Identität aus dem Quellfoto ein, "
    "optional glättet GPEN-BFR-256 / GFPGAN 1.4 das Ergebnis, und der Spout-Sender <code>ComfyLiveFaceSwap</code> zeigt es in OBS. "
    "Mimik, Kopfhaltung, Hände und Hintergrund bleiben dein Kamerabild; nur die Gesichtsidentität wird ersetzt.</p>"
    "<h2>Bedienung</h2>"
    "<ol><li>Quellfoto der Zielidentität laden (frontal, gut beleuchtet, keine Brille). Mehrere Fotos als Batch erhöhen die Stabilität.</li>"
    "<li>Vorschau-Zweig mit einem Testbild ausführen (<b>Run</b>); Timing-Text prüft Erkennung/Swap/Enhancer in Millisekunden.</li>"
    "<li>Den Live-Node <b>Bypass</b> aufheben, OBS-Spout-Quelle <code>ComfyLiveFaceSwap</code> anlegen, einmal <b>Run</b>. Beenden ausschließlich mit <b>Interrupt</b>; nie Run (Instant).</li></ol>"
    "<h2>Hardware</h2>"
    "<p>DirectML-Gerät 1 = R9700 (gleiche GPU wie Spout/OBS), 0 = RX 9070 XT. Die ROCm-Torch-Geräte sind hier nicht beteiligt. "
    "Für die Stimme läuft getrennt der DirectML-RVC-Begleiter (Workflow <code>Voice Design/RVC_DirectML-Live-Microphone-Voice-Swap.json</code>) auf der RX 9070 XT.</p>"
    "<h2>Lizenzen &amp; Einwilligung</h2>"
    "<p>inswapper_128 und buffalo_l: nicht-kommerzielle InsightFace-Lizenz; hyperswap_1a_256: FaceFusion ResearchRAIL; GPEN: nicht-kommerziell; GFPGAN: Apache-2.0. "
    "Nur eigene oder ausdrücklich freigegebene Gesichter verwenden und die Synthese im Stream sichtbar kennzeichnen.</p>"
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


def _link_input(name: str, kind: str, link: int) -> dict[str, Any]:
    return {"localized_name": name, "name": name, "type": kind, "link": link}


def _output(name: str, kind: str, links: list[int], slot: int) -> dict[str, Any]:
    return {"localized_name": name, "name": name, "type": kind, "slot_index": slot, "links": links}


def _node(node_id: int, node_type: str, title: str, pos: list[float], size: list[float], order: int, inputs, outputs, widgets, *, cnr: str = "ComfyUI-DaWasteh-LiveAvatar", mode: int = 0) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "pos": pos,
        "size": size,
        "flags": {},
        "order": order,
        "mode": mode,
        "inputs": inputs,
        "outputs": outputs,
        "title": title,
        "properties": {"Node name for S&R": node_type, "cnr_id": cnr},
        "widgets_values": widgets,
    }


def build_template() -> dict[str, Any]:
    """Return the deterministic Workflow-16 template graph."""
    loader = V099_OBJECT_INFO["DaWastehFaceSwapModelLoader"]
    identity = V099_OBJECT_INFO["DaWastehFaceSwapIdentity"]
    preview = V099_OBJECT_INFO["DaWastehFaceSwapImage"]
    live = V099_OBJECT_INFO["DaWastehLiveFaceSwap"]
    nodes = [
        {
            "id": 1, "type": "PixaromaNote", "pos": [40.0, 80.0], "size": [800, 900], "flags": {}, "order": 0, "mode": 0,
            "inputs": [{"localized_name": "note_json", "name": "note_json", "type": "STRING", "link": None, "widget": {"name": "note_json"}}],
            "outputs": [], "title": "Workflow 16 · Live Face Swap · Bedienung und Grenzen",
            "properties": {"Node name for S&R": "PixaromaNote", "cnr_id": "ComfyUI-Pixaroma"},
            "widgets_values": [json.dumps({"version": 1, "content": README_HTML}, ensure_ascii=False), ""],
            "color": "#1d1d1d", "bgcolor": "#2a2a2a",
        },
        _node(2, "LoadImage", "Quellidentität · freigegebenes Foto (Batch erlaubt)", [1000.0, 80.0], [430, 500], 1,
              [{"localized_name": "image", "name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}},
               {"localized_name": "upload", "name": "upload", "type": "IMAGEUPLOAD", "link": None, "widget": {"name": "upload"}}],
              [_output("IMAGE", "IMAGE", [2], 0), _output("MASK", "MASK", [], 1)],
              [SOURCE_IMAGE, "image"], cnr="comfy-core"),
        _node(3, "DaWastehFaceSwapModelLoader", "Face-Swap-Modelle · DirectML 1 = R9700", [1000.0, 640.0], [430, 200], 2,
              _widget_inputs(loader, set()),
              [_output("face_swap", "DAW_FACESWAP", [1, 4, 9], 0)],
              ["inswapper_128", "gpen_bfr_256", 1, 320, 0.5]),
        _node(4, "DaWastehFaceSwapIdentity", "Identität aus Quellfoto(s)", [1520.0, 80.0], [380, 120], 3,
              [_link_input("face_swap", "DAW_FACESWAP", 1), _link_input("source_images", "IMAGE", 2)],
              [_output("identity", "DAW_FACE_IDENTITY", [5, 10], 0), _output("summary", "STRING", [3], 1)],
              []),
        _node(5, "PreviewAny", "Identitäts-Zusammenfassung", [1520.0, 260.0], [380, 120], 4,
              [_link_input("source", "*", 3)], [], [], cnr="comfy-core"),
        _node(6, "LoadImage", "Testbild für die Offline-Vorschau", [1000.0, 900.0], [430, 500], 5,
              [{"localized_name": "image", "name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}},
               {"localized_name": "upload", "name": "upload", "type": "IMAGEUPLOAD", "link": None, "widget": {"name": "upload"}}],
              [_output("IMAGE", "IMAGE", [6], 0), _output("MASK", "MASK", [], 1)],
              [PREVIEW_IMAGE, "image"], cnr="comfy-core"),
        _node(7, "DaWastehFaceSwapImage", "Vorschau-Swap · Einstellungen prüfen", [1520.0, 460.0], [420, 180], 6,
              [_link_input("face_swap", "DAW_FACESWAP", 4), _link_input("identity", "DAW_FACE_IDENTITY", 5), _link_input("image", "IMAGE", 6),
               *_widget_inputs(preview, {"face_swap", "identity", "image"})],
              [_output("image", "IMAGE", [7], 0), _output("timing", "STRING", [8], 1)],
              [0.3, 0.8]),
        _node(8, "PreviewImage", "Vorschau · getauschtes Gesicht", [2020.0, 80.0], [500, 560], 7,
              [_link_input("images", "IMAGE", 7)], [], [], cnr="comfy-core"),
        _node(9, "PreviewAny", "Millisekunden · Erkennung / Swap / Enhancer", [2020.0, 700.0], [500, 120], 8,
              [_link_input("source", "*", 8)], [], [], cnr="comfy-core"),
        _node(10, "DaWastehLiveFaceSwap", "LIVE · BRIO → Face Swap → Spout ComfyLiveFaceSwap (Bypass aufheben)", [2600.0, 80.0], [480, 560], 9,
              [_link_input("face_swap", "DAW_FACESWAP", 9), _link_input("identity", "DAW_FACE_IDENTITY", 10),
               *_widget_inputs(live, {"face_swap", "identity"})],
              [],
              [SENDER_NAME, 30, 2, "DirectShow", 1280, 720, True, 0.3, 0.5, 0.8, 1, 0, "live-face-swap/metrics.json"],
              mode=4),
    ]
    links = [
        [1, 3, 0, 4, 0, "DAW_FACESWAP"],
        [2, 2, 0, 4, 1, "IMAGE"],
        [3, 4, 1, 5, 0, "STRING"],
        [4, 3, 0, 7, 0, "DAW_FACESWAP"],
        [5, 4, 0, 7, 1, "DAW_FACE_IDENTITY"],
        [6, 6, 0, 7, 2, "IMAGE"],
        [7, 7, 0, 8, 0, "IMAGE"],
        [8, 7, 1, 9, 0, "STRING"],
        [9, 3, 0, 10, 0, "DAW_FACESWAP"],
        [10, 4, 0, 10, 1, "DAW_FACE_IDENTITY"],
    ]
    return {
        "id": "b3e4a0f4-8c0b-4d6b-9f6a-16f1a7c1e099",
        "revision": 0,
        "last_node_id": 10,
        "last_link_id": 10,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.5, "offset": [0, 0]}, "frontendVersion": "1.51.9", UPGRADE_KEY: {"version": UPGRADE_VERSION, "release": "v0.9.9"}},
        "version": 0.4,
    }


def template_bytes() -> bytes:
    return (json.dumps(build_template(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write tools/workflow_templates/%s" % SOURCE_TEMPLATE)
    args = parser.parse_args()
    payload = template_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    target = Path(__file__).resolve().parent / "workflow_templates" / SOURCE_TEMPLATE
    if args.write:
        target.write_bytes(payload)
        print(f"wrote {target} sha256={digest}")
    else:
        print(f"sha256={digest} pinned={SOURCE_TEMPLATE_SHA256} match={digest == SOURCE_TEMPLATE_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
