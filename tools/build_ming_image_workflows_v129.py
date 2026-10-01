#!/usr/bin/env python3
"""Rebuild the v1.2.9 Ming Image workflows (flat RODENT graphs); no runtime/model writes.

- Design text to image: official Ming Image 0.1 Design template (12 steps, CFG 1) with the official prompt rewriter
  running on the local Qwen3.8 27B GGUF (llama.cpp on the RX 9070 XT) instead of a second 17 GB text encoder.
- Transparent RGBA: the official transparency phrase in front of the (rewritten) prompt, saved as RGBA PNG.
- Image edit: reference image(s) through TextEncodeMingImageEdit at the official 1024 bucket.
- Layer decomposition: Ming Image 0.1 Design-Layer, composite + N layers as latent frames, each frame decoded on its
  own and saved as RGBA PNG; the official guided prompt turns a rough plan + the image into the layer specification.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

try:
    from tools.build_workflows_v118 import Graph
    from tools import migrate_workflows_v092 as migration
    from tools.generate_dual_gpu_workflows import install_run_timer
    from tools.refine_workflows import refine_workflow
    from tools.rodent_layout import apply_rodent_layout
    from tools.workflow_names_v131 import original_name
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout
    from workflow_names_v131 import original_name

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v129"
MARKER = "dawasteh_ming_image_v129"
RELEASE = "v1.2.9"
BS = "\\"
PATHS = {
    "t2i": "Text to Image/Ming_Image_0_1_Design_INT8-Text-to-Image.json",
    "transparent": "Text to Image/Ming_Image_0_1_Design_INT8-Text-to-Transparent-Image.json",
    "edit": "Image Editing/Ming_Image_0_1_Design_INT8-Image-Edit.json",
    "layers": "Image Utilities/Ming_Image_0_1_Design_Layer_INT8-Image-to-Layers.json",
}
UNET = "Ming" + BS + "ming_image_0.1_design_int8_convrot.safetensors"
UNET_LAYER = "Ming" + BS + "ming_image_0.1_design_layer_int8_convrot.safetensors"
CLIP = "Ming" + BS + "ming_image_0.1_ling_mini_2.0_int8_convrot.safetensors"
CLIP_LAYER = "Ming" + BS + "ming_image_0.1_ling_mini_2.0_layer_int8_convrot.safetensors"
VAE = "Ming" + BS + "ming_image_vae_bf16.safetensors"
BIREFNET = "birefnet.safetensors"
INPUTS = {"edit": "ming_card_making_input.png", "layers": "ming_card_making_input.png"}
# Measured on the R9700 (docs/MING_IMAGE_V129.md); the tests pin these values.
SETTINGS = {
    "sampler": {"seed": 0, "steps": 12, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
    "layer_sampler": {"seed": 0, "steps": 12, "cfg": 2.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
    # Official dynamic shift: mu = 1.35 from 4096 image tokens (1024 px) up -> linear shift e^1.35.
    "shift": 3.86,
    "t2i_size": 2048,
    "transparent_size": 1024,
    "bucket": "1024",
    "layers": 6,
    "writer_tokens": 4096,
    "alpha_min_share": 0.02,
}
T2I_PROMPT = ("Poster für ein Sommerfest am See: großer Titel \"SEEFEST 2026\", darunter \"Samstag, 12. Juli · ab 16 Uhr\", "
              "Live-Musik, Food-Trucks, Sonnenuntergang über dem Wasser, fröhliche flache Illustration.")
ALPHA_PROMPT = "A cute red fox mascot sitting upright and waving, flat vector sticker style with a thin white outline."
EDIT_PROMPT = "Change the date \"7TH OCTOBER\" to \"12TH JULY\" and keep everything else exactly as it is."
LAYER_PLAN = """Layer 1: all text
Layer 2: illustration at the top right
Layer 3: illustrations in the bottom corners
Layer 4: red ribbon and bow
Layer 5: dark card with gold glitter border
Layer 6: red background"""


# ---------------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------------

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


def _resolution(g: Graph, title: str, size: int) -> dict:
    resolution = g.add("PixaromaResolution", title)
    resolution["properties"]["resolutionState"] = json.dumps({
        "mode": "preset", "ratio": "1:1", "w": size, "h": size,
        "custom_w": size, "custom_h": size, "custom_ratio_w": 1, "custom_ratio_h": 1, "snap": 32,
    })
    resolution["size"] = [480, 420]
    return resolution


def _models(g: Graph, layer: bool) -> tuple[dict, dict, dict]:
    # Read-only mappings (v1.2.6 loaders): the core loaders charge the 19.5 GB text encoder file to the commit limit
    # on top of its VRAM copy; 2048x2048 then peaked at 96.6 of 97.4 GB commit, read-only at 77.3 GB (same weights).
    unet = g.add("DaWVUReadOnlyUNETLoader", "MING IMAGE 0.1 DESIGN-LAYER · INT8 ConvRot · RAM-schonend" if layer
                 else "MING IMAGE 0.1 DESIGN · INT8 ConvRot · RAM-schonend", unet_name=UNET_LAYER if layer else UNET)
    # AuraFlow = flow shift with timestep multiplier 1 (Ming/Z-Image); ModelSamplingSD3 (multiplier 1000) gave noise.
    shift = g.add("ModelSamplingAuraFlow", f"SHIFT {SETTINGS['shift']} · offizieller Zeitplan (mu 1,35 ab 1024 px)",
                  shift=SETTINGS["shift"])
    g.connect(unet, 0, shift, "model")
    clip = g.add("DaWVUReadOnlyCLIPLoader", "TEXTENCODER · Ling-mini-2.0 Layer · INT8 ConvRot · RAM-schonend" if layer
                 else "TEXTENCODER · Ling-mini-2.0 · INT8 ConvRot · RAM-schonend", clip_name=CLIP_LAYER if layer else CLIP,
                 type="qwen_image", device="default")
    vae = g.add("VAELoader", "VAE · Ming Image · RGBA", vae_name=VAE)
    return shift, clip, vae


def _writer(g: Graph, task: str, text: tuple[dict, int], **values) -> dict:
    title = {
        "design": "PROMPT-WRITER · Qwen3.8 27B schreibt das Design-JSON (RX 9070 XT) · enhance aus = Prompt direkt",
        "transparent": "PROMPT-WRITER · Qwen3.8 27B + RGBA-Präfix · enhance aus = Prompt direkt + Präfix",
        "layers": "PROMPT-WRITER · Qwen3.8 27B sieht das Bild und schreibt den Ebenenplan · enhance aus = Plan direkt",
    }[task]
    writer = g.add("DaWMingPromptWriter", title, task=task, enhance=True, layers=values.pop("layers", 4), seed=0,
                   max_tokens=SETTINGS["writer_tokens"], **values)
    g.connect(text[0], text[1], writer, "text")
    return writer


def _sample(g: Graph, model: dict, positive: tuple[dict, int], latent: dict, settings: dict, title: str) -> dict:
    negative = g.add("ConditioningZeroOut", "NEGATIV · genullt wie im Original" + (" (CFG 1 ignoriert ihn)" if settings["cfg"] == 1.0 else ""))
    g.connect(positive[0], positive[1], negative, "conditioning")
    sample = g.add("KSampler", title, **settings)
    g.connect(model, 0, sample, "model")
    g.connect(positive[0], positive[1], sample, "positive")
    g.connect(negative, 0, sample, "negative")
    g.connect(latent, 0, sample, "latent_image")
    return sample


def _model_lines(keys: list[str], extra_inputs: list[str]) -> str:
    lines = []
    for entry in json.loads((SOURCES / "models.json").read_text(encoding="utf-8")):
        if Path(entry["path"]).name not in keys:
            continue
        url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
        lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}` "
                     f"({entry['size'] / 2**30:.2f} GiB)")
    for entry in json.loads((SOURCES / "inputs.json").read_text(encoding="utf-8")):
        if entry["file"] in extra_inputs:
            lines.append(f"- [{entry['file']}]({entry['url']}) → `ComfyUI/input/{entry['file']}` (Beispiel)")
    return "# Benötigte Dateien\n\n" + "\n\n".join(lines) + DOWNLOAD_TAIL


def finish(g: Graph, key: str) -> dict:
    path = PATHS[key]
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v129:" + original_name(path)))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {
        "version": 1,
        "kind": key,
        "source_manifest": "tools/workflow_templates/v129/sources.json",
        "model_manifest": "tools/workflow_templates/v129/models.json",
        "validation_report": "performance/rdna4/ming-image-v129-validation.json",
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
# text to image (design / transparent)
# ---------------------------------------------------------------------------------------------------------------------

def _build_t2i(schemas: dict, transparent: bool) -> dict:
    g = Graph(schemas)
    model, clip, vae = _models(g, layer=False)
    text = g.prompt("1 · PROMPT · Design, Motiv, Texte in Anführungszeichen (Deutsch oder Englisch)",
                    ALPHA_PROMPT if transparent else T2I_PROMPT)
    size = SETTINGS["transparent_size"] if transparent else SETTINGS["t2i_size"]
    resolution = _resolution(g, f"2 · FORMAT · {size}² Start · 32-px-Raster" + ("" if transparent else " · 1024² schneller"), size)
    writer = _writer(g, "transparent" if transparent else "design", (text, 0))
    g.connect(resolution, 0, writer, "width")
    g.connect(resolution, 1, writer, "height")
    show = g.add("PreviewAny", "KONTROLLE · Prompt, den Ming bekommt")
    g.connect(writer, 0, show, "source")
    encode = g.add("CLIPTextEncode", "MING · Prompt kodieren")
    g.connect(clip, 0, encode, "clip")
    g.connect(writer, 0, encode, "text")
    empty = g.add("EmptyLatentImage", "LEERES LATENT · Ausgabeformat", width=size, height=size, batch_size=1)
    g.connect(resolution, 0, empty, "width")
    g.connect(resolution, 1, empty, "height")
    sample = _sample(g, model, (encode, 0), empty, SETTINGS["sampler"], "SAMPLER · offiziell 12 Schritte / CFG 1 / Euler / Simple")
    decode = g.add("VAEDecode", "DECODE · Ming-VAE · RGBA")
    g.connect(sample, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    if transparent:
        # Ming writes real alpha only in some runs (v1.2.9: 6 of 18 at 1024 px); the fallback keeps it when present and
        # otherwise uses BiRefNet's foreground mask. The mask branch is lazy: BiRefNet only loads when it is needed.
        rgb = g.add("SplitImageWithAlpha", "RGB · für die Freistellung")
        g.connect(decode, 0, rgb, "image")
        bg_model = g.add("LoadBackgroundRemovalModel", "FREISTELLER-MODELL · BiRefNet · nur bei Bedarf", bg_removal_name=BIREFNET)
        mask = g.add("RemoveBackground", "MASKE · BiRefNet, falls Ming kein Alpha geliefert hat")
        g.connect(bg_model, 0, mask, "bg_removal_model")
        g.connect(rgb, 0, mask, "image")
        alpha = g.add("DaWMingAlphaFallback", "ALPHA · Mings eigenes, sonst BiRefNet-Maske", min_share=SETTINGS["alpha_min_share"])
        g.connect(decode, 0, alpha, "images")
        g.connect(mask, 0, alpha, "mask")
        source = g.add("PreviewAny", "KONTROLLE · Alpha-Quelle (ming = vom Modell, mask = BiRefNet)")
        g.connect(alpha, 1, source, "source")
        save = _save(g, "3 · SPEICHERN · RGBA-PNG mit Transparenz + Workflow", "Ming_Image/Transparent_%counter%")
        g.connect(alpha, 0, save, "images")
        board = g.add("DaWMingCheckerboard", "KONTROLLE · Transparenz auf Schachbrett")
        g.connect(alpha, 0, board, "images")
        preview = g.add("PreviewImage", "KONTROLLE · Freisteller auf Schachbrett (Datei behält Alpha)")
        g.connect(board, 0, preview, "images")
        g.note(f"START HIER · Ming Image · Freisteller RGBA · {RELEASE}", TRANSPARENT_NOTE)
        g.note("DOWNLOADS · Modelle / Zielordner", _model_lines([Path(p).name for p in (UNET, CLIP, VAE, BIREFNET)], []))
        return finish(g, "transparent")
    rgb = g.add("SplitImageWithAlpha", "RGB · Alpha des Decoders verwerfen")
    g.connect(decode, 0, rgb, "image")
    save = _save(g, "3 · SPEICHERN · PNG + Workflow", "Ming_Image/Design_%counter%")
    g.connect(rgb, 0, save, "images")
    g.note(f"START HIER · Ming Image 0.1 Design · Text → Bild · {RELEASE}", T2I_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines([Path(p).name for p in (UNET, CLIP, VAE)], []))
    return finish(g, "t2i")


def build_t2i(schemas: dict) -> dict:
    return _build_t2i(schemas, transparent=False)


def build_transparent(schemas: dict) -> dict:
    return _build_t2i(schemas, transparent=True)


# ---------------------------------------------------------------------------------------------------------------------
# image edit
# ---------------------------------------------------------------------------------------------------------------------

def build_edit(schemas: dict) -> dict:
    g = Graph(schemas)
    model, clip, vae = _models(g, layer=False)
    load = _pixaroma_load(g, "1 · BILD · wird bearbeitet (bestimmt das Ausgabeformat)", INPUTS["edit"])
    size = g.add("DaWMingReferenceSize", f"ARBEITSGRÖSSE · offizieller {SETTINGS['bucket']}er-Bucket (Seitenverhältnis bleibt)",
                 bucket=SETTINGS["bucket"])
    g.connect(load, 0, size, "image")
    text = g.prompt("2 · ÄNDERUNG · was sich ändern soll (Englisch am zuverlässigsten)", EDIT_PROMPT)
    encode = g.add("TextEncodeMingImageEdit", "MING EDIT · Bild + Anweisung (offiziell: ein Eingabebild)")
    # Autogrow V3 is a frontend socket template, never a literal API input. One reference like the official
    # pipeline: with two images the v1.2.9 tests returned image 2 unchanged (3 of 3 photo cases).
    encode["inputs"] = [slot for slot in encode["inputs"] if slot["name"] != "images"]
    encode["inputs"] += [{"name": "images.image_1", "type": "IMAGE", "link": None, "shape": 7}]
    for src, slot, field in [(clip, 0, "clip"), (vae, 0, "vae"), (text, 0, "prompt"), (size, 0, "images.image_1")]:
        g.connect(src, slot, encode, field)
    empty = g.add("EmptyLatentImage", "LEERES LATENT · Format von Bild 1", width=1024, height=1024, batch_size=1)
    g.connect(size, 1, empty, "width")
    g.connect(size, 2, empty, "height")
    sample = _sample(g, model, (encode, 0), empty, SETTINGS["sampler"], "SAMPLER · offiziell 12 Schritte / CFG 1 / Euler / Simple")
    decode = g.add("VAEDecode", "DECODE · Ming-VAE · RGBA")
    g.connect(sample, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    rgb = g.add("SplitImageWithAlpha", "RGB · Alpha des Decoders verwerfen")
    g.connect(decode, 0, rgb, "image")
    save = _save(g, "3 · SPEICHERN · PNG + Workflow", "Ming_Image/Edit_%counter%")
    g.connect(rgb, 0, save, "images")
    _compare(g, "VERGLEICH · Bild 1 ↔ Ergebnis", (size, 0), (rgb, 0))
    g.note(f"START HIER · Ming Image 0.1 Design · Bild bearbeiten · {RELEASE}", EDIT_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner", _model_lines([Path(p).name for p in (UNET, CLIP, VAE)], [INPUTS["edit"]]))
    return finish(g, "edit")


# ---------------------------------------------------------------------------------------------------------------------
# layer decomposition
# ---------------------------------------------------------------------------------------------------------------------

def build_layers(schemas: dict) -> dict:
    g = Graph(schemas)
    model, clip, vae = _models(g, layer=True)
    load = _pixaroma_load(g, "1 · BILD · fertiges Design (Poster, Karte, Folie, UI)", INPUTS["layers"])
    size = g.add("DaWMingReferenceSize", f"ARBEITSGRÖSSE · offizieller {SETTINGS['bucket']}er-Bucket · 512 nur Vorschau",
                 bucket=SETTINGS["bucket"])
    g.connect(load, 0, size, "image")
    plan = g.prompt("2 · EBENENPLAN · grob, eine Zeile je Ebene, vorne zuerst, Hintergrund zuletzt (optional)", LAYER_PLAN)
    writer = _writer(g, "layers", (plan, 0), layers=SETTINGS["layers"])
    g.connect(size, 0, writer, "image")
    show = g.add("PreviewAny", "KONTROLLE · Ebenen-Spezifikation, die Ming bekommt")
    g.connect(writer, 0, show, "source")
    encode = g.add("TextEncodeMingImageEdit", "MING LAYER · Bild + Ebenen-Spezifikation")
    encode["inputs"] = [slot for slot in encode["inputs"] if slot["name"] != "images"]
    encode["inputs"] += [{"name": "images.image_1", "type": "IMAGE", "link": None, "shape": 7}]
    for src, slot, field in [(clip, 0, "clip"), (vae, 0, "vae"), (writer, 0, "prompt"), (size, 0, "images.image_1")]:
        g.connect(src, slot, encode, field)
    empty = g.add("EmptyQwenImageLayeredLatentImage", "LEERES LATENT · Komposit + N Ebenen als Frames",
                  width=1024, height=1024, layers=SETTINGS["layers"], batch_size=1)
    g.connect(size, 1, empty, "width")
    g.connect(size, 2, empty, "height")
    g.connect(writer, 1, empty, "layers")
    sample = _sample(g, model, (encode, 0), empty, SETTINGS["layer_sampler"], "SAMPLER · offiziell 12 Schritte / CFG 2 / Euler / Simple")
    cut = g.add("LatentCutToBatch", "FRAMES EINZELN · jede Ebene als eigenes Bild dekodieren", dim="t", slice_size=1)
    g.connect(sample, 0, cut, "samples")
    decode = g.add("VAEDecode", "DECODE · Ming-VAE · RGBA je Ebene")
    g.connect(cut, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    split = g.add("DaWMingLayerSplit", "EBENEN · 1 = vorne … letzte = Hintergrund")
    g.connect(decode, 0, split, "frames")
    save = _save(g, "3 · SPEICHERN · jede Ebene als RGBA-PNG", "Ming_Image/Layers/Layer_%counter%")
    g.connect(split, 0, save, "images")
    sheet = g.add("PreviewImage", "KONTROLLE · alle Ebenen auf Schachbrett")
    g.connect(split, 3, sheet, "images")
    _compare(g, "VERGLEICH · Original ↔ Ebenen wieder übereinander", (size, 0), (split, 2))
    g.note(f"START HIER · Ming Image 0.1 Design-Layer · Design in Ebenen zerlegen · {RELEASE}", LAYER_NOTE)
    g.note("DOWNLOADS · Modelle / Zielordner",
           _model_lines([Path(p).name for p in (UNET_LAYER, CLIP_LAYER, VAE)], [INPUTS["layers"]]))
    return finish(g, "layers")


# ---------------------------------------------------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------------------------------------------------

DOWNLOAD_TAIL = """

Comfy-Orgs Umpackungen von inclusionAIs Ming-Image-0.1-Design(-Layer) (MIT). DiT und Text-Encoder INT8 ConvRot wie im
offiziellen Template; der Prompt-Writer nutzt das Qwen3.8-27B-GGUF aus dem Startprofil (`models/LLM/Qwen3.8`, schon für
den Musikvideo-Prompt-Writer da), kein zweiter 17-GB-Text-Encoder. Knoten: ComfyUI-DaWasteh-MingImage (Bundle-Updater).
"""

WRITER_TEXT = """**PROMPT-WRITER** (an = offizielle Pipeline): Qwen3.8 27B läuft per llama.cpp auf der RX 9070 XT, nur solange er
schreibt, danach sind VRAM und RAM wieder frei. Ohne GGUF im Startprofil oder mit `enhance` **aus** geht der Text direkt
an Ming. Der geschriebene Prompt steht in **KONTROLLE**; ändert sich nur der Seed, schreibt er nicht neu."""

T2I_NOTE = """# Ming Image 0.1 Design · Text → Bild

Ming Image 0.1 Design (inclusionAI, MIT) ist auf **Designs mit Text** trainiert: Poster, UI-Screens, Infografiken,
Karten, Folien. Texte in Anführungszeichen setzt es buchstabengetreu.

1. **PROMPT** (Knoten 1): beschreiben, was entstehen soll; sichtbare Texte in "Anführungszeichen".
2. **FORMAT** (Knoten 2): offiziell 2048×2048; 1024×1024 ist etwa viermal schneller.
3. **Queue**. Ergebnis unter **output/Ming_Image/Design_*.png**.

**Dauer (R9700):** 2048² ca. 40–50 s, 1024² ca. 10 s, dazu beim ersten Lauf Laden der Modelle und der Writer
(kurze Anfrage ca. 30 s, sehr lange bis 2 min).

""" + WRITER_TEXT + """ Der Writer macht aus der kurzen Beschreibung das Figma-artige JSON
(Ebenen, Koordinaten, Farben, exakte Texte), mit dem Ming trainiert wurde, und bekommt das echte Format mitgeteilt.

**Sampler:** offiziell 12 Schritte, CFG 1, Euler, Simple; **ModelSamplingAuraFlow 3,86** = der Zeitplan der
Referenz-Implementierung (mu 1,35). Seed fest auf 0, für Varianten auf *randomize*.
**Speicher:** Die RAM-schonenden Loader mappen die 19,5-GB-Text-Encoder-Datei schreibgeschützt (Commit bei 2048²:
77 statt 97 von 97 GB mit den Core-Loadern, gleiche Gewichte). Bedienung und Messwerte: `docs/MING_IMAGE_V129.md`.
"""

TRANSPARENT_NOTE = """# Ming Image 0.1 Design · Freisteller mit echtem Alpha-Kanal

Ming kann **echte Transparenz** schreiben (RGBA-VAE). Der Workflow setzt dafür einen der offiziellen Präfixe an den
Anfang des Prompts: `transparent canvas, not white, not checkerboard` (im Test am häufigsten erfolgreich).

1. **PROMPT** (Knoten 1): nur das Motiv beschreiben (Figur, Produkt, Logo), keinen Hintergrund.
2. **FORMAT** (Knoten 2): Start 1024×1024.
3. **Queue**. Ergebnis: **output/Ming_Image/Transparent_*.png** mit Alpha; die KONTROLLE zeigt es auf Schachbrett.

**Alpha-Absicherung:** Ming liefert den Alpha-Kanal nur in einem Teil der Läufe (Test: 6 von 18), sonst malt es Weiß
oder ein Schein-Schachbrett. Ist weniger als 2 % des Bildes transparent, stellt **BiRefNet** das Motiv frei; nur dann
wird es geladen. *Alpha-Quelle* zeigt `ming` (vom Modell, mit weichen Schatten) oder `mask` (BiRefNet).
Sticker mit weißem Rand bleiben meist deckend weiß umrandet: den Rand dann im Prompt weglassen.

""" + WRITER_TEXT + """ Im Freisteller-Modus bekommt er den Hinweis, keinen Hintergrund zu beschreiben.

Als JPG geht die Transparenz verloren. Bedienung und Messwerte: `docs/MING_IMAGE_V129.md`.
"""

EDIT_NOTE = """# Ming Image 0.1 Design · Bild bearbeiten

1. **BILD** (Knoten 1) wählen. Es wird auf die offizielle Arbeitsgröße gebracht (1024er-Bucket, Seitenverhältnis bleibt,
   z. B. 1920×1080 → 1280×720); diese Größe hat auch das Ergebnis.
2. **ÄNDERUNG** (Knoten 2): kurz sagen, was sich ändern soll, z. B. `Change the title to "SUMMER SALE".`,
   `Replace the ribbon with a blue one.` Texte in Anführungszeichen.
3. **Queue**. Ergebnis unter **output/Ming_Image/Edit_*.png**, VERGLEICH zeigt vorher/nachher.
   Dauer (R9700): ca. 22 s, erster Lauf ca. 60 s.

**Stärken:** Texte, Daten, Farben und Elemente in Designs gezielt ändern; der Rest bleibt stehen. Fotos gehen auch
(Kleidung, Farben), Mings Schwerpunkt sind aber Designs.
**Nur ein Bild:** wie in der offiziellen Pipeline. Mit einem zweiten Referenzbild (der Core-Knoten erlaubt bis zu 8)
kam im Test bei Fotos nur Bild 2 unverändert heraus; für Kombinationen aus mehreren Bildern Qwen Image 2.1 Edit nutzen.
**Sampler:** offiziell 12 Schritte, CFG 1. Bedienung und Messwerte: `docs/MING_IMAGE_V129.md`.
"""

LAYER_NOTE = """# Ming Image 0.1 Design-Layer · fertiges Design in Ebenen zerlegen

Aus einem flachen Bild (Poster, Karte, Folie, UI-Screen) werden **N transparente RGBA-Ebenen**: Texte, Motive,
Karten/Flächen und Hintergrund getrennt, verdeckte Stellen ergänzt. Übereinander gelegt ergeben sie wieder das Bild.

1. **BILD** (Knoten 1) wählen. Arbeitsgröße: offizieller 1024er-Bucket (Seitenverhältnis bleibt).
2. **EBENENPLAN** (Knoten 2): grob, eine Zeile je Ebene, **vorderste zuerst, Hintergrund zuletzt**. Leer lassen geht
   auch: dann zählt nur `layers` am Writer.
3. **Queue**. Ergebnis: **output/Ming_Image/Layers/Layer_*.png** (Layer 1 = vorne … letzte = Hintergrund).
   KONTROLLE zeigt alle Ebenen auf Schachbrett, VERGLEICH das Original gegen die wieder übereinander gelegten Ebenen.

""" + WRITER_TEXT + """ Er sieht das Bild und schreibt aus dem groben Plan die genaue Spezifikation
(Farben, Positionen, Texte wörtlich, Karte hinter dem Text als eigene Ebene, Hintergrund zuletzt); die Ebenenzahl
kommt aus seiner Antwort. Ohne Writer: `layers` am Writer = Zahl der Planzeilen.

**Dauer (R9700):** 6 Ebenen bei 1024 px ca. 4 min (7 Bilder mit CFG 2), erster Lauf ca. 5 min. Der 512er-Bucket
(ca. 50 s) verschmolz im Test Karte und Hintergrund zu einer Ebene: nur als schnelle Vorschau.
**Tipps (Hersteller):** Text nach vorne, die Karte/das Banner hinter dem Text als eigene Ebene, das Hauptmotiv als eigene
Ebene, Tische/Böden/Schatten gehören zum Hintergrund. Fehlt etwas in den Ebenen (VERGLEICH zeigt Lücken), einen anderen
Seed probieren. **Sampler:** offiziell 12 Schritte, **CFG 2**. Bedienung und Messwerte: `docs/MING_IMAGE_V129.md`.
"""


BUILDERS = {
    "t2i": build_t2i,
    "transparent": build_transparent,
    "edit": build_edit,
    "layers": build_layers,
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
