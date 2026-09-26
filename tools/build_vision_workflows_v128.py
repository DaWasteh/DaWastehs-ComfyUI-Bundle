#!/usr/bin/env python3
"""Rebuild the v1.2.8 workflows (flat RODENT graphs); no runtime/model writes.

- Qwen Image 2.1 mask edit: load image -> paint mask (Pixaroma Inpaint Crop editor or the core MaskEditor) -> prompt.
  Crop around the mask, Qwen 2.1 edit of the crop with the crop as reference and a latent noise mask, stitch back:
  pixels outside the mask stay bit-identical to the input.
- Pose from image / video: RT-DETR person boxes -> SDPose Wholebody (133 keypoints) -> OpenPose-style pose map.
- Depth from image / video: Depth Anything 3 Mono Large -> normalised depth map (8-bit, 16-bit PNG for images).

Videos run through VideoHelperSuite meta batches: the prompt re-queues itself per batch, so RAM stays bounded for any
length and the output is one video with the original frame rate and audio.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

try:
    from tools.build_workflows_v118 import Graph
    from tools import build_qwen_image21_workflows as v121
    from tools import migrate_workflows_v092 as migration
    from tools.generate_dual_gpu_workflows import install_run_timer
    from tools.refine_workflows import refine_workflow
    from tools.rodent_layout import apply_rodent_layout
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import build_qwen_image21_workflows as v121
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v128"
MARKER = "dawasteh_vision_v128"
RELEASE = "v1.2.8"
BS = "\\"
PATHS = {
    "qwen_inpaint": "Image Inpainting/Qwen_Image_2_1_BF16-Mask-Inpaint.json",
    "pose_image": "Pose & Depth/SDPose-Pose-from-Image.json",
    "pose_video": "Pose & Depth/SDPose-Pose-from-Video.json",
    "depth_image": "Pose & Depth/DepthAnything3-Depth-from-Image.json",
    "depth_video": "Pose & Depth/DepthAnything3-Depth-from-Video.json",
}
QWEN_MODEL, QWEN_CLIP, QWEN_VAE = v121.MODEL, v121.CLIP, v121.VAE
SDPOSE = "SDPose" + BS + "sdpose_wholebody_fp16.safetensors"
DETECTOR = "SDPose" + BS + "rt_detr_v4-x-hgnet_fp16.safetensors"
DA3 = "DepthAnything3" + BS + "depth_anything_3_mono_large.safetensors"
INPUTS = {"qwen_inpaint": "portrait_model_denim.png", "pose_image": "dancer.png", "pose_video": "man_in_the_rain.mp4",
          "depth_image": "retro_futuristic_home.png", "depth_video": "empty_room_assembly.mp4"}
# Measured on the R9700 (see docs/POSE_DEPTH_V128.md and docs/QWEN_IMAGE21_INPAINT_V128.md); the tests pin these values.
SETTINGS = {
    "inpaint_crop": {"size_mode": "keep shape (long side)", "target": 1024, "multiple": 32, "context_px": 64, "mask_grow": 8,
                     "mask_blur": 8, "softness": 16, "blend_mode": "mask", "invert_mask": False},
    "qwen_sampler": {"seed": 0, "steps": 25, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
    "detector": {"threshold": 0.5, "class_name": "person", "max_detections": 1},
    "draw": {"draw_body": True, "draw_hands": True, "draw_face": True, "draw_feet": True, "stick_width": 4,
             "face_point_size": 2, "score_threshold": 0.5, "draw_head": True},
    "depth_image": {"resolution": 1008, "resize_method": "upper_bound_resize"},
    "depth_video": {"resolution": 504, "resize_method": "lower_bound_resize"},
    "frames_per_batch": 64,
    "crf": 17,
}
QWEN_PROMPT = "Change the green sweater into a red leather jacket with a silver zipper."


# ---------------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------------

def _values(node: dict, values: list) -> dict:
    """Set the persisted widget values exactly as the frontend saves them (dynamic combos: key, then sub-widgets)."""
    node["widgets_values"] = list(values)
    return node


def _sub_widgets(node: dict, names: list[tuple[str, str]]) -> None:
    """Dynamic-combo sub-widgets are separate input slots in the saved UI file (official template layout)."""
    for name, kind in names:
        if not any(slot["name"] == name for slot in node["inputs"]):
            node["inputs"].append({"name": name, "type": kind, "widget": {"name": name}, "link": None})


def _pixaroma_load(g: Graph, title: str, image: str) -> dict:
    load = g.add("PixaromaLoadImage", title, image=image)
    load["properties"]["loadImagePixState"] = json.dumps({"version": 1, "mode": "off", "snap": 0})
    load["size"] = [480, 620]
    return load


def _save(g: Graph, title: str, pattern: str) -> dict:
    save = g.add("PixaromaSaveImage", title)
    save["properties"]["saveImageState"] = json.dumps({
        "version": 1, "folder": "", "pattern": pattern, "format": "png", "quality": 100, "embedWorkflow": True,
        "civitaiMeta": False, "saveOnRun": True, "counterDigits": 5,
    })
    save["size"] = [500, 820]
    return save


def _compare(g: Graph, title: str, before: tuple[dict, int], after: tuple[dict, int]) -> dict:
    compare = g.add("PixaromaCompare", title)
    compare["size"] = [540, 640]
    g.connect(before[0], before[1], compare, "image1")
    g.connect(after[0], after[1], compare, "image2")
    return compare


def _load_video(g: Graph, title: str, video: str, batch: dict) -> dict:
    # DaW loader = VHS_LoadVideo + meta batch, but silent videos give no audio and a run after a cancelled/failed one
    # never continues the old video (both broke the plain VHS loader in the v1.2.8 tests).
    load = g.add("DaWLoadVideoBatches", title, video=video, skip_first_frames=0, frame_load_cap=0)
    load["size"] = [480, 700]
    g.connect(batch, 0, load, "meta_batch")
    return load


def _combine(g: Graph, title: str, images: tuple[dict, int], fps: dict, audio: dict, batch: dict, prefix: str, save: bool) -> dict:
    combine = g.add("VHS_VideoCombine", title)
    combine["inputs"] += [
        {"name": "pix_fmt", "type": ["yuv420p", "yuv420p10le"], "widget": {"name": "pix_fmt"}, "link": None},
        {"name": "crf", "type": "INT", "widget": {"name": "crf"}, "link": None},
        {"name": "save_metadata", "type": "BOOLEAN", "widget": {"name": "save_metadata"}, "link": None},
        {"name": "trim_to_audio", "type": "BOOLEAN", "widget": {"name": "trim_to_audio"}, "link": None},
    ]
    combine["widgets_values"] = {
        "frame_rate": 24, "loop_count": 0, "filename_prefix": prefix, "format": "video/h264-mp4", "pix_fmt": "yuv420p",
        "crf": SETTINGS["crf"], "save_metadata": True, "trim_to_audio": False, "pingpong": False, "save_output": save,
        "videopreview": {"hidden": False, "paused": False, "params": {}},
    }
    combine["properties"]["cnr_id"] = "comfyui-videohelpersuite"
    combine["size"] = [520, 760]
    g.connect(images[0], images[1], combine, "images")
    g.connect(fps, 3, combine, "frame_rate")
    g.connect(audio, 2, combine, "audio")
    g.connect(batch, 0, combine, "meta_batch")
    return combine


def _video_frame(g: Graph, label: str, video: str) -> tuple[dict, dict]:
    batch = g.add("VHS_BatchManager", f"META-BATCH · {SETTINGS['frames_per_batch']} Frames je Durchgang · beliebige Videolänge",
                  frames_per_batch=SETTINGS["frames_per_batch"])
    load = _load_video(g, f"VIDEO · {label} · Originalgröße und -fps", video, batch)
    return batch, load


def _model_lines(keys: list[str], extra_inputs: list[str]) -> str:
    lines = []
    entries = [e for e in json.loads((SOURCES / "models.json").read_text(encoding="utf-8")) if Path(e["path"]).name in keys]
    for entry in entries:
        url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
        lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}` "
                     f"({entry['size'] / 2**30:.2f} GiB)")
    for entry in json.loads((SOURCES / "inputs.json").read_text(encoding="utf-8")):
        if entry["file"] in extra_inputs:
            lines.append(f"- [{entry['file']}]({entry['url']}) → `ComfyUI/input/{entry['file']}` (Beispiel)")
    return "# Benötigte Dateien\n\n" + "\n\n".join(lines)


def finish(g: Graph, key: str) -> dict:
    path = PATHS[key]
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v128:" + path))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {
        "version": 1,
        "kind": key,
        "source_manifest": "tools/workflow_templates/v128/sources.json",
        "model_manifest": "tools/workflow_templates/v121/models.json" if key == "qwen_inpaint" else "tools/workflow_templates/v128/models.json",
        "validation_report": "performance/rdna4/vision-workflows-v128-validation.json",
    }
    refine_workflow(g.w, g.schemas)
    before = copy.deepcopy(migration.OBJECT_INFO)
    try:
        migration.OBJECT_INFO.update(g.schemas)
        result = migration.migrate_workflow(g.w, path)
    finally:
        migration.OBJECT_INFO.clear()
        migration.OBJECT_INFO.update(before)
    for node in result["nodes"]:
        if node["type"] == "MarkdownNote":
            text = node.get("widgets_values", [""])[0]
            lines = sum(max(1, (len(line) + 79) // 80) for line in text.splitlines())
            node["size"] = [680, max(620, 160 + lines * 22)]
    apply_rodent_layout(result, path)
    return result


# ---------------------------------------------------------------------------------------------------------------------
# Qwen Image 2.1 mask edit
# ---------------------------------------------------------------------------------------------------------------------

def build_qwen_inpaint(schemas: dict) -> dict:
    g = Graph(schemas)
    unet = g.add("UNETLoader", "QWEN IMAGE 2.1 · BF16 · R9700", unet_name=QWEN_MODEL)
    soft = g.add("DifferentialDiffusion", "WEICHE MASKENKANTE · Differential Diffusion", strength=1.0)
    g.connect(unet, 0, soft, "model")
    cache = g.add("QwenImage21Cache", "EDIT KV-CACHE · auto / verlustfrei", device="auto", dtype="default")
    g.connect(soft, 0, cache, "model")
    clip = g.add("CLIPLoader", "TEXTENCODER · Qwen3-VL 8B INT8 ConvRot", clip_name=QWEN_CLIP, type="qwen_image", device="default")
    vae = g.add("VAELoader", "VAE · nur Qwen Image 2.1", vae_name=QWEN_VAE)

    load = g.add("LoadImage", "1 · BILD LADEN · optional Maske per Rechtsklick → Open in MaskEditor", image=INPUTS["qwen_inpaint"])
    load["size"] = [480, 620]
    c = SETTINGS["inpaint_crop"]
    crop = g.add("PixaromaInpaintCrop", f"2 · MASKE MALEN · Editor öffnen · Ausschnitt {c['target']} px + {c['context_px']} px Umgebung", **c)
    crop["properties"]["cnr_id"] = "ComfyUI-Pixaroma"
    crop["size"] = [520, 700]
    g.connect(load, 0, crop, "image")
    g.connect(load, 1, crop, "mask")
    # The crop also runs through the guard: encoders and VAE start only after the check (fails in seconds, not after
    # loading the 8B text encoder).
    guard = g.add("DaWRequireMask", "MASKE PRÜFEN · stoppt sofort mit Hinweis, wenn nichts gemalt ist", min_pixels=16)
    g.connect(crop, 0, guard, "image")
    g.connect(crop, 1, guard, "mask")

    pos = g.prompt("3 · ÄNDERUNG · was im markierten Bereich entstehen soll (Englisch)", QWEN_PROMPT)
    neg = g.prompt("NEGATIV · offiziell leer · CFG 1 ignoriert Negativprompt", "")
    encode = g.add("TextEncodeQwenImage21", "QWEN 2.1 · Ausschnitt als Referenz + Anweisung", resolution=0)
    # Autogrow V3 is a frontend socket template, never a literal API input.
    encode["inputs"] = [slot for slot in encode["inputs"] if slot["name"] != "images"]
    encode["inputs"] += [{"name": f"images.image_{i}", "type": "IMAGE", "link": None} for i in (1, 2)]
    for src, slot, field in [(clip, 0, "clip"), (pos, 0, "prompt"), (neg, 0, "negative_prompt"), (vae, 0, "vae"), (guard, 0, "images.image_1")]:
        g.connect(src, slot, encode, field)

    latent = g.add("VAEEncode", "AUSSCHNITT → Latent (gleiches 32-px-Format wie die Referenz)")
    g.connect(guard, 0, latent, "pixels")
    g.connect(vae, 0, latent, "vae")
    masked = g.add("SetLatentNoiseMask", "NUR MASKE NEU RECHNEN · Rest bleibt Original")
    g.connect(latent, 0, masked, "samples")
    g.connect(guard, 1, masked, "mask")
    k = SETTINGS["qwen_sampler"]
    sample = g.add("KSampler", "SAMPLER · offiziell 25 / CFG 1 / Euler / Simple · Denoise 1", **k)
    for src, slot, field in [(cache, 0, "model"), (encode, 0, "positive"), (encode, 1, "negative"), (masked, 0, "latent_image")]:
        g.connect(src, slot, sample, field)
    decode = g.add("VAEDecode", "DECODE · 2.1-VAE (RGBA)")
    g.connect(sample, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    rgb = g.add("SplitImageWithAlpha", "RGB · Alpha des Decoders verwerfen")
    g.connect(decode, 0, rgb, "image")
    stitch = g.add("PixaromaInpaintStitch", "ZURÜCKSETZEN · nur der Maskenbereich ersetzt das Original", softness=-1,
                   blend_mode="from crop", color_match="off")
    stitch["properties"]["cnr_id"] = "ComfyUI-Pixaroma"
    g.connect(rgb, 0, stitch, "image")
    g.connect(crop, 2, stitch, "crop_info")
    save = _save(g, "4 · SPEICHERN · fertiges Bild · PNG + Workflow", "Qwen_Image_2_1/Inpaint_%counter%")
    g.connect(stitch, 0, save, "images")
    _compare(g, "VERGLEICH · Original ↔ Ergebnis", (load, 0), (stitch, 0))
    preview = g.add("PreviewImage", "KONTROLLE · Ausschnitt, den Qwen bearbeitet hat")
    g.connect(rgb, 0, preview, "images")

    g.note(f"START HIER · Qwen Image 2.1 Mask Inpaint · {RELEASE}", QWEN_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _qwen_downloads())
    return finish(g, "qwen_inpaint")


def _qwen_downloads() -> str:
    lines = []
    for entry in json.loads((v121.SOURCES / "models.json").read_text(encoding="utf-8")):
        url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
        lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}`")
    for entry in json.loads((v121.SOURCES / "inputs.json").read_text(encoding="utf-8")):
        if entry["file"] == INPUTS["qwen_inpaint"]:
            lines.append(f"- [{entry['file']}]({entry['url']}) → `ComfyUI/input/{entry['file']}` (Beispiel)")
    return ("# Benötigte Dateien\n\n" + "\n\n".join(lines) +
            "\n\nDieselben drei Gewichte wie die übrigen Qwen-Image-2.1-Workflows (v1.2.1/v1.2.4), keine neue Modelldatei.\n"
            "Masken-Editor: Pixaroma Inpaint Crop (ComfyUI-Pixaroma), Wächter: ComfyUI-DaWasteh-VisionTools (Bundle-Updater).\n")


QWEN_NOTE = """# Qwen Image 2.1 · Bild mit Maske bearbeiten

**Research / Evaluation, nicht kommerziell ohne separate Lizenz.**
[Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE).

1. **BILD LADEN** (Knoten 1): Bild hochladen oder auswählen.
2. **MASKE MALEN** (Knoten 2, Pixaroma Inpaint Crop): **Editor öffnen**, den Bereich übermalen, der sich ändern soll,
   speichern. Alternativ am Bild: Rechtsklick → *Open in MaskEditor*. Eine im Crop-Editor gemalte Maske hat Vorrang.
3. **ÄNDERUNG** (Knoten 3): auf Englisch beschreiben, was im markierten Bereich entstehen soll, z. B.
   `Replace the cup with a small potted cactus.` oder `Remove the person.`
4. **Queue**. Ergebnis unter **output/Qwen_Image_2_1/Inpaint_*.png**, VERGLEICH zeigt vorher/nachher.

**So arbeitet der Graph:** Der Ausschnitt um die Maske (plus Umgebung) wird auf 1024 px Kantenlänge gebracht und
dient Qwen als Referenz. Nur die maskierten Latents werden neu gerechnet (Noise-Maske + Differential Diffusion),
danach setzt Stitch **nur den Maskenbereich** mit weicher Kante ins Original zurück. Alles außerhalb der Maske
bleibt pixelgenau das Originalbild, auch bei großen Fotos.

**Etwas entfernen:** großzügig malen, das ganze Objekt samt Schatten, Rädern, Griffen usw. Was außerhalb der
Maske bleibt, bleibt im Bild (ein nicht übermalter Stoßfänger steht danach allein da).
**Keine Maske gemalt?** Der Wächter *MASKE PRÜFEN* stoppt sofort mit einem Hinweis, statt das Bild unverändert
zurückzugeben. Achtung bei PNGs mit Transparenz: Der Alpha-Kanal wird von *Load Image* als Maske gelesen.
**Dauer (R9700):** ca. 21–24 s je Bild bei 1024 px, erster Lauf ca. 60 s (Modelle laden).

**Einstellungen am Crop-Knoten:** `target` 1024 (für große Masken auf großen Bildern 1536 oder 2048, kostet Zeit),
`context_px` = wie viel Umgebung Qwen sieht, `mask_grow`/`mask_blur` = Maskenrand, `softness` = Übergang beim
Zurücksetzen. `invert_mask` bearbeitet alles **außer** der Maske (z. B. neuer Hintergrund).
Offizielle Samplerwerte: **25 Schritte, CFG 1, Euler, Simple**; Seed fest auf 0, für Varianten auf *randomize*.
Bedienung und Testwerte: `docs/QWEN_IMAGE21_INPAINT_V128.md`.
"""


# ---------------------------------------------------------------------------------------------------------------------
# Pose (SDPose Wholebody + RT-DETR)
# ---------------------------------------------------------------------------------------------------------------------

def _pose_models(g: Graph) -> tuple[dict, dict]:
    sdpose = g.add("CheckpointLoaderSimple", "SDPOSE · Wholebody fp16 · 133 Punkte", ckpt_name=SDPOSE)
    detector = g.add("UNETLoader", "PERSONEN-DETEKTOR · RT-DETR v4-x fp16", unet_name=DETECTOR)
    return sdpose, detector


def _pose_chain(g: Graph, image: tuple[dict, int], sdpose: dict, detector: dict) -> tuple[dict, dict, dict]:
    d = SETTINGS["detector"]
    detect = g.add("RTDETR_detect", f"PERSONEN FINDEN · max. {d['max_detections']} (für Gruppen erhöhen)", **d)
    g.connect(detector, 0, detect, "model")
    g.connect(image[0], image[1], detect, "image")
    # SDPose stretches each box to 768x1024 without keeping the aspect ratio; 3:4 boxes around the person (MMPose
    # top-down crop) doubled the confident body points on a dark dance video (7.7 -> 15.6 of 18, v1.2.8 test).
    boxes = g.add("DaWPoseBoxes", "PERSONENRAHMEN · auf 3:4 + 25 % Rand (unverzerrter SDPose-Ausschnitt)", scale=1.25)
    g.connect(detect, 0, boxes, "bboxes")
    g.connect(image[0], image[1], boxes, "image")
    extract = g.add("SDPoseKeypointExtractor", "SDPOSE · Keypoints je Person (Ausschnitt 768×1024)", batch_size=16)
    g.connect(sdpose, 0, extract, "model")
    g.connect(sdpose, 2, extract, "vae")
    g.connect(image[0], image[1], extract, "image")
    g.connect(boxes, 0, extract, "bboxes")
    draw = g.add("SDPoseDrawKeypoints", "POSE-KARTE · Körper, Hände, Gesicht, Füße (OpenPose-Farben)", **SETTINGS["draw"])
    g.connect(extract, 0, draw, "keypoints")
    return boxes, extract, draw


def _overlay(g: Graph, image: tuple[dict, int], detect: dict, draw: dict) -> dict:
    boxes = g.add("DrawBBoxes", "KONTROLLE · Personenrahmen (3:4) ins Bild")
    g.connect(detect, 0, boxes, "bboxes")
    g.connect(image[0], image[1], boxes, "image")
    blend = g.add("ImageBlend", "KONTROLLE · Pose über das Bild legen (screen)", blend_factor=1.0, blend_mode="screen")
    g.connect(boxes, 0, blend, "image1")
    g.connect(draw, 0, blend, "image2")
    return blend


def build_pose_image(schemas: dict) -> dict:
    g = Graph(schemas)
    sdpose, detector = _pose_models(g)
    load = _pixaroma_load(g, "BILD · Person, deren Pose extrahiert wird", INPUTS["pose_image"])
    detect, extract, draw = _pose_chain(g, (load, 0), sdpose, detector)
    save = _save(g, "SPEICHERN · Pose-Karte · PNG (für ControlNet / Pose-Video)", "Pose/Pose_%counter%")
    g.connect(draw, 0, save, "images")
    keypoints = g.add("SavePoseKpsAsJsonFile", "SPEICHERN · Keypoints als OpenPose-JSON", filename_prefix="Pose/Pose_Keypoints")
    g.connect(extract, 0, keypoints, "pose_kps")
    blend = _overlay(g, (load, 0), detect, draw)
    preview = g.add("PreviewImage", "KONTROLLE · Pose + Rahmen über dem Bild")
    g.connect(blend, 0, preview, "images")
    _compare(g, "VERGLEICH · Bild ↔ Pose-Karte", (load, 0), (draw, 0))
    g.note(f"START HIER · Pose aus Bild · SDPose · {RELEASE}", POSE_IMAGE_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines([SDPOSE.split(BS)[-1], DETECTOR.split(BS)[-1]], [INPUTS["pose_image"]]) + POSE_TAIL)
    return finish(g, "pose_image")


def build_pose_video(schemas: dict) -> dict:
    g = Graph(schemas)
    sdpose, detector = _pose_models(g)
    batch, load = _video_frame(g, "Person, deren Bewegung extrahiert wird", INPUTS["pose_video"])
    detect, _, draw = _pose_chain(g, (load, 0), sdpose, detector)
    _combine(g, "SPEICHERN · Pose-Video · MP4 mit Originalton und -fps", (draw, 0), load, load, batch, "Pose/Pose_Video", True)
    blend = _overlay(g, (load, 0), detect, draw)
    _combine(g, "KONTROLLE · Pose über dem Video (nur Vorschau)", (blend, 0), load, load, batch, "Pose/Pose_Overlay", False)
    g.note(f"START HIER · Pose aus Video · SDPose · {RELEASE}", POSE_VIDEO_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines([SDPOSE.split(BS)[-1], DETECTOR.split(BS)[-1]], [INPUTS["pose_video"]]) + POSE_TAIL)
    return finish(g, "pose_video")


POSE_TAIL = """

SDPose (MIT) und RT-DETR sind Comfy-Orgs Umpackungen, beide laufen mit Core-Nodes von ComfyUI.
Kein Cloud-API-Aufruf, keine zusätzliche Node-Installation.
"""

POSE_COMMON = """**So arbeitet der Graph:** RT-DETR findet die Person, der Rahmen wird unverzerrt auf 3:4 plus 25 % Rand
erweitert, SDPose Wholebody schätzt im Personenausschnitt 133 Punkte (Körper, Füße, 68 Gesichtspunkte, beide Hände). Die Pose-Karte ist im OpenPose-Farbschema auf Schwarz,
in **Originalauflösung**, deckungsgleich mit dem Quellbild, direkt nutzbar für OpenPose-ControlNets und Pose-gesteuerte
Video-Workflows.

**Eine Person:** `max_detections` = 1 nimmt die sicherste Person. Für Gruppen erhöhen (z. B. 5). Findet der Detektor
niemanden (z. B. stark stilisierte Figuren), rechnet SDPose auf dem ganzen Bild.
**Zeichnen:** Hände/Gesicht/Füße einzeln abschaltbar; `score_threshold` 0,5 blendet unsichere Punkte aus.
"""

POSE_IMAGE_NOTE = """# Pose aus einem Bild · SDPose Wholebody

1. **BILD** wählen (Pixaroma Load Image, Resize **off**).
2. **Queue**. Ergebnisse unter **output/Pose/**:
   - `Pose_*.png`: Pose-Karte (Skelett auf Schwarz, gleiche Größe wie das Bild)
   - `Pose_Keypoints_*.json`: alle Punkte im OpenPose-JSON-Format (Pixelkoordinaten + Konfidenz)
3. **KONTROLLE** legt Pose und Personenrahmen über das Bild, **VERGLEICH** zeigt Bild ↔ Pose-Karte.

""" + POSE_COMMON + """
Bedienung und Messwerte: `docs/POSE_DEPTH_V128.md`.
"""

POSE_VIDEO_NOTE = """# Pose aus einem Video · SDPose Wholebody

1. **VIDEO** wählen (VHS Load Video; Originalgröße und Original-fps bleiben).
2. **Queue**. Der Workflow läuft in **Meta-Batches** zu je 64 Frames und stellt sich selbst neu in die Warteschlange,
   bis das Video fertig ist (Fortschritt in der Queue). Dadurch bleibt der RAM bei jeder Videolänge klein.
3. Ergebnis: **output/Pose/Pose_Video_*.mp4** mit Originalton und Original-fps. Die KONTROLLE zeigt die Pose über
   dem Video nur als Vorschau (temp).

**Nur einen Teil verarbeiten:** am Video-Knoten `skip_first_frames` und `frame_load_cap` setzen.
**Abbrechen:** in der Queue abbrechen; bereits fertige Batches bleiben unvollständig (kein fertiges MP4).

""" + POSE_COMMON + """
Jedes Frame wird einzeln geschätzt; bei schnellen Bewegungen oder verdeckten Händen können einzelne Punkte
von Frame zu Frame springen. Bedienung und Messwerte: `docs/POSE_DEPTH_V128.md`.
"""


# ---------------------------------------------------------------------------------------------------------------------
# Depth (Depth Anything 3 Mono Large)
# ---------------------------------------------------------------------------------------------------------------------

def _depth_model(g: Graph) -> dict:
    return g.add("LoadDA3Model", "DEPTH ANYTHING 3 · Mono Large", model_name=DA3, weight_dtype="default")


def _depth_inference(g: Graph, model: dict, image: tuple[dict, int], settings: dict, label: str) -> dict:
    infer = _values(g.add("DA3Inference", label), [settings["resolution"], settings["resize_method"], "mono"])
    g.connect(model, 0, infer, "da3_model")
    g.connect(image[0], image[1], infer, "image")
    return infer


def _render(g: Graph, geometry: dict, title: str, output: str, normalization: str, sky_clip: bool) -> dict:
    render = _values(g.add("DA3Render", title), [output, normalization, sky_clip])
    _sub_widgets(render, [("output.normalization", "COMBO"), ("output.apply_sky_clip", "BOOLEAN")])
    g.connect(geometry, 0, render, "da3_geometry")
    return render


def build_depth_image(schemas: dict) -> dict:
    g = Graph(schemas)
    model = _depth_model(g)
    load = _pixaroma_load(g, "BILD · Szene, deren Tiefe geschätzt wird", INPUTS["depth_image"])
    s = SETTINGS["depth_image"]
    infer = _depth_inference(g, model, (load, 0), s, f"DA3 · Tiefe schätzen · {s['resolution']} px (lange Kante)")
    gray = _render(g, infer, "TIEFENKARTE · Graustufen · hell = nah (ControlNet)", "depth", "v2_style", False)
    save = _save(g, "SPEICHERN · Tiefenkarte 8 Bit · PNG", "Depth/Depth_%counter%")
    g.connect(gray, 0, save, "images")
    full = _render(g, infer, "TIEFENKARTE · voller Bereich · Himmel begrenzt (für 16 Bit)", "depth", "min_max", True)
    save16 = g.add("DaWSaveDepth16", "SPEICHERN · Tiefenkarte 16 Bit · PNG (3D / Displacement)", filename_prefix="Depth/Depth16")
    g.connect(full, 0, save16, "images")
    color = _render(g, infer, "KONTROLLE · Tiefe eingefärbt (Turbo)", "depth_colored", "v2_style", False)
    preview = g.add("PreviewImage", "KONTROLLE · Tiefe eingefärbt")
    g.connect(color, 0, preview, "images")
    _compare(g, "VERGLEICH · Bild ↔ Tiefenkarte", (load, 0), (gray, 0))
    g.note(f"START HIER · Tiefe aus Bild · Depth Anything 3 · {RELEASE}", DEPTH_IMAGE_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines([DA3.split(BS)[-1]], [INPUTS["depth_image"]]) + DEPTH_TAIL)
    return finish(g, "depth_image")


def build_depth_video(schemas: dict) -> dict:
    g = Graph(schemas)
    model = _depth_model(g)
    batch, load = _video_frame(g, "Szene, deren Tiefe geschätzt wird", INPUTS["depth_video"])
    s = SETTINGS["depth_video"]
    infer = _depth_inference(g, model, (load, 0), s, f"DA3 · Tiefe je Frame · kurze Kante {s['resolution']} px")
    gray = _render(g, infer, "TIEFENKARTE · Graustufen · hell = nah", "depth", "v2_style", False)
    _combine(g, "SPEICHERN · Tiefen-Video · MP4 mit Originalton und -fps", (gray, 0), load, load, batch, "Depth/Depth_Video", True)
    color = _render(g, infer, "KONTROLLE · Tiefe eingefärbt (Turbo)", "depth_colored", "v2_style", False)
    _combine(g, "KONTROLLE · Tiefe eingefärbt (nur Vorschau)", (color, 0), load, load, batch, "Depth/Depth_Color", False)
    g.note(f"START HIER · Tiefe aus Video · Depth Anything 3 · {RELEASE}", DEPTH_VIDEO_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines([DA3.split(BS)[-1]], [INPUTS["depth_video"]]) + DEPTH_TAIL)
    return finish(g, "depth_video")


DEPTH_TAIL = """

Depth Anything 3 (ByteDance Seed) als Comfy-Org-Umpackung, läuft mit den Core-Nodes von ComfyUI.
Kein Cloud-API-Aufruf.
"""

DEPTH_IMAGE_NOTE = """# Tiefe aus einem Bild · Depth Anything 3 Mono Large

1. **BILD** wählen (Pixaroma Load Image, Resize **off**).
2. **Queue**. Ergebnisse unter **output/Depth/** in Originalgröße:
   - `Depth_*.png`: Tiefenkarte 8 Bit, hell = nah, Himmel schwarz (für Depth-ControlNets)
   - `Depth16_*.png`: 16-Bit-Graustufen (65.536 Stufen, voller Tiefenbereich, Himmel auf die Hintergrundtiefe
     begrenzt) für 3D-Displacement, Parallax und Compositing ohne Treppenstufen
3. **KONTROLLE** zeigt die Tiefe eingefärbt, **VERGLEICH** Bild ↔ Tiefenkarte.

**Auflösung:** DA3 rechnet mit 1008 px an der langen Kante (Vielfache von 14) und skaliert das Ergebnis auf die
Bildgröße. 504 ist schneller und weicher an Kanten, 1512 bringt kaum mehr. Dauer: 1–2 s für ein 2048²-Bild.
Die Tiefe ist **relativ** (nah/fern), nicht in Metern. Der Himmel wird schwarz; dünne Objekte vor dem Himmel
(Palmwedel, Leitungen) zählt DA3 manchmal zum Himmel.
Bedienung und Messwerte: `docs/POSE_DEPTH_V128.md`.
"""

DEPTH_VIDEO_NOTE = """# Tiefe aus einem Video · Depth Anything 3 Mono Large

1. **VIDEO** wählen (VHS Load Video; Originalgröße und Original-fps bleiben).
2. **Queue**. Der Workflow läuft in **Meta-Batches** zu je 64 Frames und stellt sich selbst neu in die Warteschlange,
   bis das Video fertig ist. Dadurch bleibt der RAM bei jeder Videolänge klein.
3. Ergebnis: **output/Depth/Depth_Video_*.mp4** (hell = nah) mit Originalton und Original-fps.
   Die eingefärbte KONTROLLE ist nur eine Vorschau (temp).

**Auflösung:** kurze Kante 504 px (Vielfache von 14), das Ergebnis wird auf die Videogröße skaliert.
**Dauer (R9700):** 5-s-Clip 720p ca. 25 s, 60 s 1080p ca. 7,5 min; der RAM bleibt dabei konstant.
**Nur einen Teil verarbeiten:** am Video-Knoten `skip_first_frames` und `frame_load_cap` setzen.
Die Tiefe ist **relativ** und wird je Frame normalisiert. Bedienung und Messwerte: `docs/POSE_DEPTH_V128.md`.
"""


BUILDERS = {
    "qwen_inpaint": build_qwen_inpaint,
    "pose_image": build_pose_image,
    "pose_video": build_pose_video,
    "depth_image": build_depth_image,
    "depth_video": build_depth_video,
}


def build_all() -> dict[str, dict]:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    return {PATHS[key]: builder(schemas) for key, builder in BUILDERS.items()}


def main() -> None:
    for path, workflow in build_all().items():
        target = ROOT / "workflows" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
