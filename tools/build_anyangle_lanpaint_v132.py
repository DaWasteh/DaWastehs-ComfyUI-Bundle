#!/usr/bin/env python3
"""Rebuild the v1.3.2 workflows (flat RODENT graphs); no runtime/model writes.

- Qwen Image 2.1 + LanPaint 2.2 mask inpaint: the v1.2.8 crop/stitch graph with LanPaint's Langevin sampler instead
  of KSampler + noise mask (training-free, "thinks" NumSteps times per step about the masked region).
- Qwen Image 2.1 + AnyAngle LoRA + TripoSplat: one image -> background removed -> TripoSplat gaussian splat -> coarse
  renders from new camera positions (Render Splat, core) -> Qwen Image 2.1 with the AnyAngle LoRA carries the original
  over to each new angle. Four views per run, no editor, no cloud.
- Qwen Image 2.1 + AnyAngle LoRA with an own guide image (any coarse render: Blender, Mira-Scene, a splat, a sketch).
- Qwen Image 2.1 + AnyAngle Studio T8: the interactive 3D camera workbench (TripoSplat reconstruction, orbit camera,
  mannequin, pose/depth/canny guides) feeding the same Qwen chain.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

try:
    from tools.build_workflows_v118 import Graph
    from tools import build_qwen_image21_workflows as v121
    from tools import build_vision_workflows_v128 as v128
    from tools import migrate_workflows_v092 as migration
    from tools.generate_dual_gpu_workflows import install_run_timer
    from tools.refine_workflows import refine_workflow
    from tools.rodent_layout import apply_rodent_layout
    from tools.workflow_names_v131 import original_name
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import build_qwen_image21_workflows as v121
    import build_vision_workflows_v128 as v128
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout
    from workflow_names_v131 import original_name

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v132"
MARKER = "dawasteh_anyangle_lanpaint_v132"
RELEASE = "v1.3.2"
BS = "\\"
PATHS = {
    "lanpaint_inpaint": "Image Inpainting/Qwen_Image_2_1_BF16+LanPaint-Image+Mask-Inpaint.json",
    "anyangle_splat": "Image Editing/Qwen_Image_2_1_BF16+AnyAngle_LoRA+TripoSplat-Image-to-4-Camera-Angles.json",
    "anyangle_guide": "Image Editing/Qwen_Image_2_1_BF16+AnyAngle_LoRA-Image+Guide-to-Camera-Angle.json",
    "anyangle_studio": "Image Editing/Qwen_Image_2_1_BF16+AnyAngle_Studio_T8-Image-to-Camera-Angle.json",
}
QWEN_MODEL, QWEN_CLIP, QWEN_VAE = v121.MODEL, v121.CLIP, v121.VAE
ANYANGLE_LORA = "Qwen" + BS + "QI2.1_AnyAngle.safetensors"
TRIPOSPLAT = "TripoSplat" + BS + "triposplat_fp16.safetensors"
TRIPOSPLAT_DECODER = "TripoSplat" + BS + "triposplat_vae_decoder_fp16.safetensors"
FLUX2_VAE = "FLUX2" + BS + "flux2-vae.safetensors"
DINO = "dino_v3_vit_h.safetensors"
BIREFNET = "birefnet.safetensors"
INPUTS = {"lanpaint_inpaint": "portrait_model_denim.png", "anyangle_splat": "character_fox.png",
          "anyangle_guide": "character_fox.png", "anyangle_guide_2": "character_fox_guide_left.png",
          "anyangle_studio": "character_fox.png"}
ANYANGLE_PROMPT = "Change the camera angle from <image2> to <image1>."
LANPAINT_PROMPT = v128.QWEN_PROMPT
LANPAINT_NEGATIVE = ("low resolution, low quality, deformed limbs, deformed fingers, oversaturated, waxy skin, "
                     "no facial detail, over-smoothed, artificial look, blurry, distorted")
# Measured on the R9700 (see docs/ANYANGLE_LANPAINT_V132.md); the tests pin these values.
SETTINGS = {
    "inpaint_crop": dict(v128.SETTINGS["inpaint_crop"]),
    "lanpaint_sampler": {"seed": 0, "steps": 20, "cfg": 4.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
                         "LanPaint_NumSteps": 5, "LanPaint_PromptMode": "Image First",
                         "Inpainting_mode": "🖼️ Image Inpainting"},
    "lanpaint_blend": 9,
    "anyangle_sampler": {"seed": 0, "steps": 20, "cfg": 3.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
    "anyangle_resolution": 1024,
    "lora_strength": 1.0,
    "triposplat_sampler": {"seed": 0, "steps": 20, "cfg": 3.0, "sampler_name": "dpmpp_2m", "scheduler": "simple", "denoise": 1.0},
    "preprocess": {"erode_radius": 1, "size": 1024},
    "num_gaussians": 262144,
    "render": {"width": 1024, "height": 1024, "frames": 1, "splat_scale": 1.0, "sharpen": 2.0, "headlight_shading": 0.0,
               "opacity_threshold": 0.0, "render_style": "color", "background": "#848484"},
    # Render Splat's orbit camera at yaw 90 looks from the original camera (measured 2026-10-02 on a TripoSplat of the
    # fox: yaw 90 = front, 0 = the subject's right profile, 180 = its left profile); yaw grows towards the subject's left.
    "camera": {"distance": 2.3, "fov": 35.0, "front_yaw": 90.0},
    # (label, file tag, yaw offset from the original camera, pitch)
    "views": [("45° LINKS", "left45", 45.0, 10.0), ("90° LINKS · Seitenansicht", "left90", 90.0, 10.0),
              ("45° RECHTS", "right45", -45.0, 10.0), ("VOGELPERSPEKTIVE · 35° von oben", "top35", 20.0, 35.0)],
}
LICENSE = ("**Research / Evaluation, nicht kommerziell ohne separate Lizenz.**\n"
           "[Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE).")


# ---------------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------------

def _load(g: Graph, title: str, image: str) -> dict:
    load = g.add("PixaromaLoadImage", title, image=image)
    load["properties"]["loadImagePixState"] = json.dumps(v121.LOAD_CAP_STATE)
    load["size"] = [480, 620]
    return load


def _encode(g: Graph, title: str, clip: dict, vae: dict, pos, neg, resolution: int, images: list) -> dict:
    """TextEncodeQwenImage21 with image_1..n; ``pos``/``neg`` are (node, slot) or None (own widget)."""
    encode = g.add("TextEncodeQwenImage21", title, resolution=resolution)
    # Autogrow V3 is a frontend socket template, never a literal API input.
    encode["inputs"] = [slot for slot in encode["inputs"] if slot["name"] != "images"]
    encode["inputs"] += [{"name": f"images.image_{i}", "type": "IMAGE", "link": None} for i in range(1, len(images) + 1)]
    g.connect(clip, 0, encode, "clip")
    g.connect(vae, 0, encode, "vae")
    if pos is not None:
        g.connect(pos[0], pos[1], encode, "prompt")
    if neg is not None:
        g.connect(neg[0], neg[1], encode, "negative_prompt")
    for i, (node, slot) in enumerate(images, 1):
        g.connect(node, slot, encode, f"images.image_{i}")
    return encode


def _qwen(g: Graph, lora: bool) -> tuple[dict, dict, dict, dict | None]:
    """Qwen Image 2.1 loaders; returns (model for the sampler, clip, vae, lora loader or None)."""
    unet = g.add("UNETLoader", "QWEN IMAGE 2.1 · BF16 · R9700", unet_name=QWEN_MODEL)
    model, lora_node = unet, None
    if lora:
        lora_node = g.add("LoraLoaderModelOnly", "ANYANGLE LoRA · lilylilith/QI_2.1_AnyAngle · Stärke 1",
                          lora_name=ANYANGLE_LORA, strength_model=SETTINGS["lora_strength"])
        g.connect(unet, 0, lora_node, "model")
        model = lora_node
    cache = g.add("QwenImage21Cache", "EDIT KV-CACHE · auto / verlustfrei", device="auto", dtype="default")
    g.connect(model, 0, cache, "model")
    clip = g.add("CLIPLoader", "TEXTENCODER · Qwen3-VL 8B INT8 ConvRot", clip_name=QWEN_CLIP, type="qwen_image", device="default")
    vae = g.add("VAELoader", "VAE · nur Qwen Image 2.1", vae_name=QWEN_VAE)
    return cache, clip, vae, lora_node


def _sample_decode(g: Graph, model: dict, encode: dict, vae: dict, label: str, pattern: str) -> tuple[dict, dict]:
    k = SETTINGS["anyangle_sampler"]
    sample = g.add("KSampler", f"SAMPLER{label} · 20 Schritte / CFG 3 / Euler / Simple (AnyAngle-Empfehlung)", **k)
    for src, slot, field in [(model, 0, "model"), (encode, 0, "positive"), (encode, 1, "negative"), (encode, 2, "latent_image")]:
        g.connect(src, slot, sample, field)
    decode = g.add("VAEDecode", f"DECODE{label} · 2.1-VAE (RGBA)")
    g.connect(sample, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    rgb = g.add("SplitImageWithAlpha", f"RGB{label} · Alpha des Decoders verwerfen")
    g.connect(decode, 0, rgb, "image")
    save = v128._save(g, f"SPEICHERN{label} · PNG + Workflow", pattern)
    g.connect(rgb, 0, save, "images")
    return rgb, save


def _camera(g: Graph, title: str, yaw: float, pitch: float) -> dict:
    c = SETTINGS["camera"]
    cam = g.add("CreateCameraInfo", title, target_x=0.0, target_y=0.0, target_z=0.0, roll=0.0, fov=c["fov"], zoom=1.0,
                camera_type="perspective")
    # DynamicCombo "mode": the frontend saves the key followed by the sub-widgets of the chosen option, then the rest.
    cam["widgets_values"] = ["orbit", yaw, pitch, c["distance"], 0.0, 0.0, 0.0, 0.0, c["fov"], 1.0, "perspective"]
    mode = next(i for i, slot in enumerate(cam["inputs"]) if slot["name"] == "mode")
    for offset, (name, kind) in enumerate([("yaw", "FLOAT"), ("pitch", "FLOAT"), ("distance", "FLOAT")], 1):
        cam["inputs"].insert(mode + offset, {"name": name, "type": kind, "widget": {"name": name}, "link": None})
    cam["size"] = [420, 360]
    return cam


def _model_lines(keys: list[str], inputs: list[str]) -> str:
    lines = []
    manifests = [json.loads((SOURCES / "models.json").read_text(encoding="utf-8")),
                 json.loads((v121.SOURCES / "models.json").read_text(encoding="utf-8"))]
    seen = set()
    for manifest in manifests:
        for entry in manifest:
            name = Path(entry["path"]).name
            if name in keys and name not in seen:
                seen.add(name)
                url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
                lines.append(f"- [{name}]({url}) → `ComfyUI/models/{entry['path']}` ({entry['size'] / 2**30:.2f} GiB)")
    for manifest in (SOURCES / "inputs.json", v121.SOURCES / "inputs.json"):
        for entry in json.loads(manifest.read_text(encoding="utf-8")):
            if entry["file"] in inputs:
                lines.append(f"- [{entry['file']}]({entry['url']}) → `ComfyUI/input/{entry['file']}` (Beispiel)")
    return "# Benötigte Dateien\n\n" + "\n\n".join(lines)


QWEN_FILES = [Path(QWEN_MODEL).name, Path(QWEN_CLIP).name, Path(QWEN_VAE).name]
SPLAT_FILES = [Path(TRIPOSPLAT).name, Path(TRIPOSPLAT_DECODER).name, Path(FLUX2_VAE).name, DINO, BIREFNET]


def finish(g: Graph, key: str) -> dict:
    path = PATHS[key]
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v132:" + original_name(path)))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {
        "version": 1,
        "kind": key,
        "source_manifest": "tools/workflow_templates/v132/sources.json",
        "model_manifest": "tools/workflow_templates/v132/models.json",
        "validation_report": "performance/rdna4/anyangle-lanpaint-v132-validation.json",
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
# Qwen Image 2.1 + LanPaint mask inpaint
# ---------------------------------------------------------------------------------------------------------------------

def build_lanpaint_inpaint(schemas: dict) -> dict:
    g = Graph(schemas)
    model, clip, vae, _ = _qwen(g, lora=False)
    load = g.add("LoadImage", "1 · BILD LADEN · optional Maske per Rechtsklick → Open in MaskEditor", image=INPUTS["lanpaint_inpaint"])
    load["size"] = [480, 620]
    c = SETTINGS["inpaint_crop"]
    crop = g.add("PixaromaInpaintCrop", f"2 · MASKE MALEN · Editor öffnen · Ausschnitt {c['target']} px + {c['context_px']} px Umgebung", **c)
    crop["properties"]["cnr_id"] = "ComfyUI-Pixaroma"
    crop["size"] = [520, 700]
    g.connect(load, 0, crop, "image")
    g.connect(load, 1, crop, "mask")
    guard = g.add("DaWRequireMask", "MASKE PRÜFEN · stoppt sofort mit Hinweis, wenn nichts gemalt ist", min_pixels=16)
    g.connect(crop, 0, guard, "image")
    g.connect(crop, 1, guard, "mask")

    pos = g.prompt("3 · ÄNDERUNG · was im markierten Bereich entstehen soll (Englisch)", LANPAINT_PROMPT)
    neg = g.prompt("NEGATIV · wirkt bei CFG 4 (LanPaint-Empfehlung)", LANPAINT_NEGATIVE)
    encode = _encode(g, "QWEN 2.1 · Ausschnitt als Referenz + Anweisung", clip, vae, (pos, 0), (neg, 0), 0, [(guard, 0)])

    latent = g.add("LanPaint_ImageEncode", "LANPAINT ENCODE · Ausschnitt + Maske → Latent (ersetzt VAE Encode + Noise Mask)")
    g.connect(guard, 0, latent, "image")
    g.connect(vae, 0, latent, "vae")
    g.connect(guard, 1, latent, "mask")
    k = SETTINGS["lanpaint_sampler"]
    sample = g.add("LanPaint_KSampler", "LANPAINT SAMPLER · 20 Schritte / CFG 4 / Euler / Simple · 5 Denkschritte", **k)
    # The frontend adds control_after_generate to every widget called "seed", also when the node's schema does not
    # declare it (LanPaint does not): without the extra value every later widget is shifted by one and ComfyUI rejects
    # the sampler ("LanPaint_NumSteps: invalid literal 'Image First'"), found in the first v1.3.2 run.
    sample["widgets_values"].insert(1, "fixed")
    for src, slot, field in [(model, 0, "model"), (encode, 0, "positive"), (encode, 1, "negative"), (latent, 0, "latent_image")]:
        g.connect(src, slot, sample, field)
    decode = g.add("LanPaint_ImageDecode", "LANPAINT DECODE · Latent → Bild, nur Maske übernommen, 9 px Übergang",
                   blend_overlap=SETTINGS["lanpaint_blend"])
    g.connect(sample, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    g.connect(guard, 0, decode, "image")
    g.connect(guard, 1, decode, "mask")
    stitch = g.add("PixaromaInpaintStitch", "ZURÜCKSETZEN · nur der Maskenbereich ersetzt das Original", softness=-1,
                   blend_mode="from crop", color_match="off")
    stitch["properties"]["cnr_id"] = "ComfyUI-Pixaroma"
    g.connect(decode, 0, stitch, "image")
    g.connect(crop, 2, stitch, "crop_info")
    save = v128._save(g, "4 · SPEICHERN · fertiges Bild · PNG + Workflow", "Qwen_Image_2_1/LanPaint_%counter%")
    g.connect(stitch, 0, save, "images")
    v128._compare(g, "VERGLEICH · Original ↔ Ergebnis", (load, 0), (stitch, 0))
    preview = g.add("PreviewImage", "KONTROLLE · Ausschnitt nach LanPaint")
    g.connect(decode, 0, preview, "images")
    g.note(f"START HIER · Qwen Image 2.1 + LanPaint 2.2 · {RELEASE}", LANPAINT_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines(QWEN_FILES, [INPUTS["lanpaint_inpaint"]]) +
           "\n\nDieselben drei Qwen-Gewichte wie die übrigen Qwen-Image-2.1-Workflows, keine neue Modelldatei.\n"
           "Node-Pack **LanPaint** (scraed/LanPaint, GPL-3.0, ab 2.2.0) installiert der Bundle-Updater aus GitHub; "
           "Masken-Editor: Pixaroma Inpaint Crop, Wächter: ComfyUI-DaWasteh-VisionTools.\n")
    return finish(g, "lanpaint_inpaint")


LANPAINT_NOTE = f"""# Qwen Image 2.1 + LanPaint · Bild mit Maske bearbeiten

{LICENSE}

Gleiche Bedienung wie *Qwen_Image_2_1_BF16-Image+Mask-Inpaint* (v1.2.8), aber der Maskenbereich wird vom
**LanPaint-Sampler** gerechnet: ein trainingsfreies Inpainting-Verfahren (Langevin-Dynamik), das in jedem
Denoising-Schritt mehrmals „nachdenkt“, wie der neue Inhalt zur unmaskierten Umgebung passt. Vorteile laut
Autor: nahtlosere Übergänge und mehr Kontexttreue, auch bei großen Masken und ohne Inpainting-Modell.

1. **BILD LADEN** (Knoten 1): Bild hochladen oder auswählen.
2. **MASKE MALEN** (Knoten 2, Pixaroma Inpaint Crop): **Editor öffnen**, den Bereich übermalen, speichern.
   Alternativ am Bild: Rechtsklick → *Open in MaskEditor*. Eine im Crop-Editor gemalte Maske hat Vorrang.
3. **ÄNDERUNG** (Knoten 3): auf Englisch beschreiben, was im markierten Bereich entstehen soll.
4. **Queue**. Ergebnis unter **output/Qwen_Image_2_1/LanPaint_*.png**, VERGLEICH zeigt vorher/nachher.

**So arbeitet der Graph:** Der Ausschnitt um die Maske (plus Umgebung) wird auf 1024 px gebracht und dient Qwen
als Referenz. *LanPaint Encode* hängt die Maske an das Latent, der *LanPaint Sampler* rechnet nur die Maske neu
und hält alles andere in jedem Schritt am Original fest. *LanPaint Decode* übernimmt nur den Maskenbereich (9 px
weicher Übergang), Stitch setzt den Ausschnitt ins Original zurück: außerhalb der Maske bleibt alles pixelgenau.

**LanPaint-Werte:** `LanPaint_NumSteps` = Denkschritte je Sampler-Schritt (2–5 einfache, 5–10 schwere Aufgaben;
jeder Schritt kostet proportional Zeit). `Image First` = Bildqualität vor Prompt-Treue, `Prompt First` umgekehrt.
**CFG 4 mit Negativprompt** ist die LanPaint-Empfehlung für Qwen Image 2.1; mit CFG 1 (offizielle Qwen-Werte)
läuft es auch, dann wirkt der Negativprompt nicht. 20 Schritte, Euler, Simple; Seed fest auf 0.
**Keine Maske gemalt?** Der Wächter stoppt sofort mit einem Hinweis. Achtung bei PNGs mit Transparenz: Der
Alpha-Kanal wird von *Load Image* als Maske gelesen.
**Transparenz mitbearbeiten** (LanPaint-Beispiel 31: RGBA-Bild, die Silhouette darf sich ändern) geht in diesem
Graph nicht, weil Crop/Stitch mit RGB arbeiten; dafür das Original-Beispiel aus dem LanPaint-Repo verwenden.
Bedienung und Messwerte: `docs/ANYANGLE_LANPAINT_V132.md`.
"""


# ---------------------------------------------------------------------------------------------------------------------
# Qwen Image 2.1 + AnyAngle LoRA + TripoSplat: four camera angles from one image
# ---------------------------------------------------------------------------------------------------------------------

def _splat(g: Graph, image: tuple[dict, int]) -> dict:
    """Image -> BiRefNet mask -> TripoSplat -> gaussian splat (official ComfyUI chain, flat)."""
    bg_model = g.add("LoadBackgroundRemovalModel", "FREISTELLEN · BiRefNet", bg_removal_name=BIREFNET)
    mask = g.add("RemoveBackground", "MASKE · Motiv ohne Hintergrund")
    g.connect(bg_model, 0, mask, "bg_removal_model")
    g.connect(image[0], image[1], mask, "image")
    p = SETTINGS["preprocess"]
    prep = g.add("TripoSplatPreprocessImage", "TRIPOSPLAT VORBEREITEN · Quadrat 1024 px auf Schwarz", **p)
    g.connect(image[0], image[1], prep, "image")
    g.connect(mask, 0, prep, "mask")
    dino = g.add("CLIPVisionLoader", "BILDENCODER · DINOv3 ViT-H", clip_name=DINO)
    flux_vae = g.add("VAELoader", "FLUX.2 VAE · Referenz-Latent für TripoSplat", vae_name=FLUX2_VAE)
    cond = g.add("TripoSplatConditioning", "TRIPOSPLAT KONDITIONIERUNG · Bild → positiv/negativ + Latent")
    g.connect(dino, 0, cond, "clip_vision")
    g.connect(flux_vae, 0, cond, "vae")
    g.connect(prep, 0, cond, "image")
    unet = g.add("UNETLoader", "TRIPOSPLAT · fp16 · Bild → 3D-Gaussians", unet_name=TRIPOSPLAT)
    k = SETTINGS["triposplat_sampler"]
    sample = g.add("KSampler", "TRIPOSPLAT SAMPLER · 20 Schritte / CFG 3 / dpmpp_2m (offizielle Vorlage)", **k)
    for src, slot, field in [(unet, 0, "model"), (cond, 0, "positive"), (cond, 1, "negative"), (cond, 2, "latent_image")]:
        g.connect(src, slot, sample, field)
    decoder = g.add("VAELoader", "TRIPOSPLAT DECODER · fp16", vae_name=TRIPOSPLAT_DECODER)
    splat = g.add("VAEDecodeTripoSplat", f"SPLAT · {SETTINGS['num_gaussians']} Gaussians", num_gaussians=SETTINGS["num_gaussians"], seed=0)
    g.connect(sample, 0, splat, "samples")
    g.connect(decoder, 0, splat, "vae")
    return splat


def _render(g: Graph, splat: dict, label: str, yaw: float, pitch: float) -> dict:
    cam = _camera(g, f"KAMERA{label} · yaw {yaw:g}° / pitch {pitch:g}° · hier den Winkel ändern", yaw, pitch)
    r = SETTINGS["render"]
    render = g.add("RenderSplat", f"GROBES RENDER{label} · Splat aus der neuen Kamera", **r)
    g.connect(splat, 0, render, "splat")
    g.connect(cam, 0, render, "camera_info")
    return render


def build_anyangle_splat(schemas: dict) -> dict:
    g = Graph(schemas)
    model, clip, vae, _ = _qwen(g, lora=True)
    load = _load(g, "1 · BILD LADEN · Figur, Objekt oder Person (freigestellt wird automatisch)", INPUTS["anyangle_splat"])
    splat = _splat(g, (load, 0))
    pos = g.prompt("2 · PROMPT · AnyAngle-Anweisung (so lassen)", ANYANGLE_PROMPT)
    neg = g.prompt("NEGATIV · leer (CFG 3)", "")
    res = SETTINGS["anyangle_resolution"]
    for title, tag, offset, pitch in SETTINGS["views"]:
        label = f" · {title}"
        render = _render(g, splat, label, SETTINGS["camera"]["front_yaw"] + offset, pitch)
        preview = g.add("PreviewImage", f"KONTROLLE{label} · grobes Render")
        g.connect(render, 0, preview, "images")
        encode = _encode(g, f"QWEN 2.1{label} · <image1> = Original, <image2> = Render", clip, vae, (pos, 0), (neg, 0), res,
                         [(load, 0), (render, 0)])
        _sample_decode(g, model, encode, vae, label, f"AnyAngle/{tag}_%counter%")
    g.note(f"START HIER · Qwen Image 2.1 + AnyAngle + TripoSplat · {RELEASE}", SPLAT_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines(QWEN_FILES + [Path(ANYANGLE_LORA).name] + SPLAT_FILES,
                                                              [INPUTS["anyangle_splat"]]) + SPLAT_DOWNLOAD_NOTE)
    return finish(g, "anyangle_splat")


SPLAT_DOWNLOAD_NOTE = """

TripoSplat, Render Splat und BiRefNet sind ComfyUI-Core-Nodes (ab 0.38, keine Custom Nodes). Die AnyAngle-LoRA ist
Apache-2.0 (lilylilith), TripoSplat MIT (VAST-AI). `flux2-vae.safetensors` ist dieselbe Datei wie bei den FLUX.2-Workflows.
"""

SPLAT_NOTE = f"""# Qwen Image 2.1 + AnyAngle · vier Kamerawinkel aus einem Bild

{LICENSE}

**AnyAngle** ist eine LoRA für Qwen Image 2.1, die ein Bild in eine neue Kameraposition überführt. Sie braucht dafür
ein **grobes Render** der Zielansicht: Dieser Workflow erzeugt es selbst: BiRefNet stellt das Motiv frei, **TripoSplat**
rekonstruiert daraus ein 3D-Gaussian-Splat, *Render Splat* fotografiert das Splat aus vier neuen Kameras, und Qwen
Image 2.1 mit der AnyAngle-LoRA überträgt Stil, Material und Details des Originals auf jede Ansicht.
Keine Blender-Installation, kein Editor, kein Cloud-Aufruf. Gedacht als Vorbereitung für Video-Workflows, die
mehrere Ansichten derselben Figur brauchen (Referenz-zu-Video, Charakter-Konsistenz, Multi-View-3D).

1. **BILD LADEN** (Knoten 1): ein klar erkennbares Motiv vor ruhigem Hintergrund (Figur, Produkt, Person).
2. **Queue**. Vier Ergebnisse unter **output/AnyAngle/** (`left45`, `left90`, `right45`, `top35`), daneben je ein
   KONTROLLE-Bild mit dem groben Render, das Qwen gesehen hat.
3. **Winkel ändern:** an den KAMERA-Knoten `yaw` (Drehung um das Motiv: **90 = Originalkamera**, größer = Kamera
   wandert nach links um das Motiv, 180 = linkes Profil, 0 = rechtes Profil, 270 = Rückansicht), `pitch` (Höhe: positiv
   = von oben), `distance` (Abstand; kleiner = Motiv größer im Bild) und `fov`. Die Rückseite hat TripoSplat nur erraten.

**Prompt** (Knoten 2) ist die feste AnyAngle-Anweisung `Change the camera angle from <image2> to <image1>.`:
`<image1>` = Original (Identität), `<image2>` = grobes Render (Zielwinkel). Gemessen: Mit vertauschten Bildern
(wie die Modellkarte der LoRA es beschreibt) bleibt die Ansicht unverändert; diese Reihenfolge nutzt auch AnyAngle Studio.
**Sampler:** 20 Schritte, CFG 3, Euler, Simple, LoRA-Stärke 1 (Empfehlung des LoRA-Autors). Für andere Ergebnisse
den Seed auf *randomize* stellen; die vier Ansichten teilen sich alle Modelle (einmal geladen).

**Grenzen:** Das Ergebnis ist nur so gut wie das Splat. Unsichtbare Seiten (Rücken, verdeckte Hände) erfindet
TripoSplat; stark verdrehte Kameras oder sehr kleine Motive geben verschobene Details oder verformte Gesichter.
Dann `yaw` kleiner wählen, das Motiv größer ins Bild bringen oder ein eigenes Render über den Guide-Workflow
(*…+AnyAngle_LoRA-Image+Guide-to-Camera-Angle*) einspeisen. Der interaktive Weg mit 3D-Vorschau ist
*…+AnyAngle_Studio_T8-Image-to-Camera-Angle*.
Bedienung und Messwerte: `docs/ANYANGLE_LANPAINT_V132.md`.
"""


# ---------------------------------------------------------------------------------------------------------------------
# Qwen Image 2.1 + AnyAngle LoRA with an own guide image
# ---------------------------------------------------------------------------------------------------------------------

def build_anyangle_guide(schemas: dict) -> dict:
    g = Graph(schemas)
    model, clip, vae, _ = _qwen(g, lora=True)
    original = _load(g, "1 · ORIGINAL · Identität, Stil, Material (<image1>)", INPUTS["anyangle_guide"])
    guide = _load(g, "2 · GROBES RENDER der Zielansicht (<image2>) · Blender, Splat, Mira-Scene, Skizze", INPUTS["anyangle_guide_2"])
    pos = g.prompt("3 · PROMPT · AnyAngle-Anweisung (so lassen)", ANYANGLE_PROMPT)
    neg = g.prompt("NEGATIV · leer (CFG 3)", "")
    encode = _encode(g, "QWEN 2.1 · <image1> = Original, <image2> = Render", clip, vae, (pos, 0), (neg, 0),
                     SETTINGS["anyangle_resolution"], [(original, 0), (guide, 0)])
    rgb, _ = _sample_decode(g, model, encode, vae, "", "AnyAngle/Guide_%counter%")
    v128._compare(g, "VERGLEICH · grobes Render ↔ Ergebnis", (guide, 0), (rgb, 0))
    g.note(f"START HIER · Qwen Image 2.1 + AnyAngle mit eigenem Render · {RELEASE}", GUIDE_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines(QWEN_FILES + [Path(ANYANGLE_LORA).name],
                                                              [INPUTS["anyangle_guide"], INPUTS["anyangle_guide_2"]]) +
           "\n\nDie AnyAngle-LoRA ist Apache-2.0 (lilylilith). Das Beispiel-Render stammt aus dem TripoSplat-Workflow dieses Bundles.\n")
    return finish(g, "anyangle_guide")


GUIDE_NOTE = f"""# Qwen Image 2.1 + AnyAngle · eigenes Render → neue Kameraansicht

{LICENSE}

Der Grundbaustein von AnyAngle ohne Rekonstruktion: Du lieferst das **grobe Render der Zielansicht** selbst, Qwen
Image 2.1 mit der AnyAngle-LoRA überträgt Identität, Stil und Material des Originals darauf. Das Render darf grob
sein (Splat-Render, Blender-Viewport eines Mira-Scene- oder TRELLIS-Modells, Clay-Render, sogar eine Pose-Skizze);
entscheidend sind Kamerawinkel, Bildausschnitt und ungefähre Proportionen.

1. **ORIGINAL** (Knoten 1) und **GROBES RENDER** (Knoten 2) laden. Beide sollten dasselbe Motiv zeigen; das Ergebnis
   bekommt das Format des Originals, Größe und Lage des Motivs folgen dem Render.
2. **Queue**. Ergebnis unter **output/AnyAngle/Guide_*.png**, VERGLEICH zeigt Render ↔ Ergebnis.

**Prompt** (Knoten 3) ist die feste AnyAngle-Anweisung: `<image1>` = Original, `<image2>` = Render. Die Reihenfolge
nicht tauschen: mit vertauschten Bildern bleibt die Ansicht unverändert (gemessen). **Sampler:** 20 Schritte, CFG 3, Euler, Simple, LoRA-Stärke 1.
**Renders erzeugen:** *…+AnyAngle_LoRA+TripoSplat-Image-to-4-Camera-Angles* (automatisch aus einem Bild, die
KONTROLLE-Bilder sind genau solche Renders) oder *…+AnyAngle_Studio_T8* (interaktive 3D-Kamera). Für Szenen aus
*Mira_Scene+TRELLIS2* oder *Pixal3D* das GLB in Blender öffnen, Kamera setzen, Viewport-Render speichern.
Bedienung und Messwerte: `docs/ANYANGLE_LANPAINT_V132.md`.
"""


# ---------------------------------------------------------------------------------------------------------------------
# Qwen Image 2.1 + AnyAngle Studio T8
# ---------------------------------------------------------------------------------------------------------------------

def build_anyangle_studio(schemas: dict) -> dict:
    g = Graph(schemas)
    unet = g.add("UNETLoader", "QWEN IMAGE 2.1 · BF16 · R9700", unet_name=QWEN_MODEL)
    lora = g.add("AnyAngleOptionalLoRAT8", "ANYANGLE LoRA (optional) · Stärke kommt aus dem Studio (1 = LoRA, 0 = Basismodell)",
                 lora_name=ANYANGLE_LORA, strength_model=SETTINGS["lora_strength"])
    g.connect(unet, 0, lora, "model")
    cache = g.add("QwenImage21Cache", "EDIT KV-CACHE · auto / verlustfrei", device="auto", dtype="default")
    g.connect(lora, 0, cache, "model")
    clip = g.add("CLIPLoader", "TEXTENCODER · Qwen3-VL 8B INT8 ConvRot", clip_name=QWEN_CLIP, type="qwen_image", device="default")
    vae = g.add("VAELoader", "VAE · nur Qwen Image 2.1", vae_name=QWEN_VAE)
    # Core Load Image: the studio reads a directly connected Load Image by itself; behind any other loader the user
    # first has to press "read upstream image". resolution 1024 scales every reference to about 1 MP before the VAE,
    # so camera photos are safe here without the Pixaroma 4 MP cap.
    load = g.add("LoadImage", "1 · BILD LADEN · Original (<image1>)", image=INPUTS["anyangle_studio"])
    load["size"] = [480, 620]
    studio = g.add("AnyAngleStudioT8", "2 · ANYANGLE STUDIO · öffnen → 3D rekonstruieren → Kamera setzen → Apply to node", snapshot="")
    studio["size"] = [520, 420]
    g.connect(load, 0, studio, "reference_image")
    g.connect(studio, 3, lora, "strength_model")
    preview = g.add("PreviewImage", "KONTROLLE · Guide aus dem Studio (<image2>)")
    g.connect(studio, 0, preview, "images")
    encode = _encode(g, "QWEN 2.1 · <image1> = Original, <image2> = Studio-Guide · Prompt aus dem Studio", clip, vae,
                     (studio, 1), None, SETTINGS["anyangle_resolution"], [(load, 0), (studio, 0)])
    _sample_decode(g, cache, encode, vae, "", "AnyAngle/Studio_%counter%")
    g.note(f"START HIER · Qwen Image 2.1 + AnyAngle Studio T8 · {RELEASE}", STUDIO_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines(QWEN_FILES + [Path(ANYANGLE_LORA).name] + SPLAT_FILES,
                                                              [INPUTS["anyangle_studio"]]) + STUDIO_DOWNLOAD_NOTE)
    return finish(g, "anyangle_studio")


STUDIO_DOWNLOAD_NOTE = """

Node-Pack **AnyAngle Studio · T8** (T8mars/Comfyui-Qwen-Image-2.1-MultiAngle-T8, MIT) installiert der Bundle-Updater aus
GitHub; seine Python-Abhängigkeiten (onnxruntime, OpenCV, huggingface_hub) sind in der Bundle-Umgebung schon vorhanden.
Das Studio findet die TripoSplat-Dateien auch in den Unterordnern dieses Bundles; DWPose- und Depth-Anything-3-Small-
Gewichte lädt es erst beim ersten Klick auf *Extract pose* / *Estimate depth* nach (ca. 350 MB + 137 MB).
"""

STUDIO_NOTE = f"""# Qwen Image 2.1 + AnyAngle Studio T8 · interaktive 3D-Kamera

{LICENSE}

Das **AnyAngle Studio** ist eine 3D-Werkbank im Browser: Es rekonstruiert das Motiv per TripoSplat, du drehst die
Kamera frei (Orbit, Pan, Zoom, Zahlenwerte, gespeicherte Ansichten), siehst das grobe Render live und übergibst es
mit einem Klick an diesen Workflow. Alternativ eine GLB-Datei (z. B. aus *Mira_Scene+TRELLIS2* oder *Pixal3D*) oder
die eingebaute MakeHuman-Figur mit Posen-Editor.

1. **BILD LADEN** (Knoten 1).
2. **ANYANGLE STUDIO** (Knoten 2): Werkbank öffnen → *Reconstruct 3D from photo* (TripoSplat läuft auf dem
   ComfyUI-Server, ca. 10–20 s) → Kamera drehen → *Preview current camera render* prüfen → **Apply to node**.
3. **Queue**. Ergebnis unter **output/AnyAngle/Studio_*.png**; KONTROLLE zeigt den übergebenen Guide.
   **Batch views** im Studio rendert viele Winkel (z. B. 0°–330° in 30°-Schritten) und stellt je einen Lauf ein.

Das Studio liefert Guide, **Prompt** und **LoRA-Stärke** (1 = AnyAngle-LoRA, 0 = Qwen-Basismodell mit Pose-/Tiefen-/
Canny-Guide und passendem Prompt). Verdrahtung wie vom Autor vorgesehen: Original = `<image1>`, Guide = `<image2>`.
**Ohne angewandte Szene** (leeres `snapshot`) lehnt ComfyUI den Lauf ab, bis im Studio *Apply to node* geklickt wurde;
angewandte Szenen liegen unter `input/anyangle_studio/` und laufen danach auch ohne geöffneten Editor.
**Sampler:** 20 Schritte, CFG 3, Euler, Simple (Vorlage des Node-Autors). Grenzen wie beim TripoSplat-Workflow:
unsichtbare Seiten sind geraten; Pose-/Tiefen-Guides aus dem Foto bleiben in der Originalansicht.
Headless-Variante ohne Editor: *…+AnyAngle_LoRA+TripoSplat-Image-to-4-Camera-Angles*.
Bedienung und Messwerte: `docs/ANYANGLE_LANPAINT_V132.md`.
"""


BUILDERS = {
    "lanpaint_inpaint": build_lanpaint_inpaint,
    "anyangle_splat": build_anyangle_splat,
    "anyangle_guide": build_anyangle_guide,
    "anyangle_studio": build_anyangle_studio,
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
