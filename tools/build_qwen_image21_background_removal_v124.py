#!/usr/bin/env python3
"""Rebuild the v1.2.4 Qwen Image 2.1 background remover (flat RODENT graph); no runtime/model writes.

Base: Comfy-Org's official ``image_qwen_image_2_1_background_removal`` template (one subgraph), flattened with
the shared local model profile of v1.2.1 (BF16 DiT, INT8 ConvRot Qwen3-VL 8B, 2.1 RGBA VAE). The 2.1 VAE
decodes four channels, so the edit itself produces the transparency; the graph adds the alpha mask as a
separate PNG and a before/after compare.
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
SOURCES = ROOT / "tools/workflow_templates/v124"
PATH = "Image Editing/Qwen_Image_2_1_BF16-Background-Remover.json"
TEMPLATE = "image_qwen_image_2_1_background_removal.json"
INPUT_IMAGE = "angry_broccoli.png"
MARKER = "dawasteh_qwen_image21_background_removal"
MODEL, CLIP, VAE = v121.MODEL, v121.CLIP, v121.VAE


def _save(g: Graph, title: str, pattern: str) -> dict:
    save = g.add("PixaromaSaveImage", title)
    save["properties"]["saveImageState"] = json.dumps({
        "version": 1, "folder": "", "pattern": pattern, "format": "png", "quality": 100, "embedWorkflow": True,
        "civitaiMeta": False, "saveOnRun": True, "counterDigits": 5,
    })
    save["size"] = [500, 820]
    return save


def build(schemas: dict) -> dict:
    source = json.loads((SOURCES / TEMPLATE).read_text(encoding="utf-8"))
    official = next(n for n in source["nodes"] if n["id"] == 459)
    prompt_text = official["widgets_values"][1]
    g = Graph(schemas)
    model = g.add("UNETLoader", "QWEN IMAGE 2.1 · BF16 · R9700", unet_name=MODEL)
    clip = g.add("CLIPLoader", "TEXTENCODER · Qwen3-VL 8B INT8 ConvRot", clip_name=CLIP, type="qwen_image", device="default")
    vae = g.add("VAELoader", "VAE · nur Qwen Image 2.1 · RGBA", vae_name=VAE)
    load = g.add("PixaromaLoadImage", "BILD · Motiv, das freigestellt wird", image=INPUT_IMAGE)
    load["properties"]["loadImagePixState"] = json.dumps({"version": 1, "mode": "off", "snap": 0})
    load["size"] = [480, 620]
    pos = g.prompt("ANWEISUNG · offizieller Freistell-Prompt (Comfy-Org)", prompt_text)
    neg = g.prompt("NEGATIV · offiziell leer · CFG 1 ignoriert Negativprompt", "")
    encode = g.add("TextEncodeQwenImage21", "QWEN 2.1 · Bild + Anweisung → Latent im Bildformat", resolution=0)
    # Autogrow V3 is a frontend socket template, never a literal API input.
    encode["inputs"] = [slot for slot in encode["inputs"] if slot["name"] != "images"]
    encode["inputs"] += [{"name": f"images.image_{i}", "type": "IMAGE", "link": None} for i in (1, 2)]
    for src, slot, field in [(clip, 0, "clip"), (pos, 0, "prompt"), (neg, 0, "negative_prompt"), (vae, 0, "vae"),
                             (load, 0, "images.image_1")]:
        g.connect(src, slot, encode, field)
    cache = g.add("QwenImage21Cache", "EDIT KV-CACHE · auto / verlustfrei", device="auto", dtype="default")
    g.connect(model, 0, cache, "model")
    sample = g.add("KSampler", "SAMPLER · offiziell 25 / CFG 1 / Euler / Simple", seed=0, steps=25, cfg=1.0,
                   sampler_name="euler", scheduler="simple", denoise=1.0)
    for src, slot, field in [(cache, 0, "model"), (encode, 0, "positive"), (encode, 1, "negative"), (encode, 2, "latent_image")]:
        g.connect(src, slot, sample, field)
    decode = g.add("VAEDecode", "DECODE · 2.1-VAE · RGBA mit Transparenz")
    g.connect(sample, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    save = _save(g, "SPEICHERN · freigestellt · PNG mit Alpha", "Qwen_Image_2_1/BG_Removed_%counter%")
    g.connect(decode, 0, save, "images")
    split = g.add("SplitImageWithAlpha", "ALPHA · aus dem RGBA-Ergebnis")
    g.connect(decode, 0, split, "image")
    invert = g.add("InvertMask", "MASKE · weiß = Motiv, schwarz = entfernt")
    g.connect(split, 1, invert, "mask")
    mask_image = g.add("MaskToImage", "MASKE → Graustufenbild")
    g.connect(invert, 0, mask_image, "mask")
    save_mask = _save(g, "SPEICHERN · Alpha-Maske · PNG", "Qwen_Image_2_1/BG_Mask_%counter%")
    g.connect(mask_image, 0, save_mask, "images")
    compare = g.add("PixaromaCompare", "VERGLEICH · Original ↔ freigestellt")
    compare["size"] = [540, 640]
    g.connect(load, 0, compare, "image1")
    g.connect(decode, 0, compare, "image2")
    g.note("START HIER · Qwen Image 2.1 Background Remover · v1.2.4", START_NOTE)
    model_lines = []
    for entry in json.loads((v121.SOURCES / "models.json").read_text()):
        url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
        model_lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}`")
    for entry in json.loads((SOURCES / "inputs.json").read_text()):
        model_lines.append(f"- [{entry['file']}]({entry['url']}) → `ComfyUI/input/{entry['file']}` (Beispielbild)")
    g.note("DOWNLOADS · Modelle / Zielordner", "# Benötigte Dateien\n\n" + "\n\n".join(model_lines) + DOWNLOAD_TAIL)
    return finish(g)


def finish(g: Graph) -> dict:
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v124:" + PATH))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {
        "version": 1,
        "source_manifest": "tools/workflow_templates/v124/sources.json",
        "model_manifest": "tools/workflow_templates/v121/models.json",
        "validation_report": "performance/rdna4/qwen-image21-background-removal-v124-validation.json",
    }
    refine_workflow(g.w, g.schemas)
    before = copy.deepcopy(migration.OBJECT_INFO)
    try:
        migration.OBJECT_INFO.update(g.schemas)
        result = migration.migrate_workflow(g.w, PATH)
    finally:
        migration.OBJECT_INFO.clear()
        migration.OBJECT_INFO.update(before)
    for node in result["nodes"]:
        if node["type"] == "MarkdownNote":
            text = node.get("widgets_values", [""])[0]
            lines = sum(max(1, (len(line) + 79) // 80) for line in text.splitlines())
            node["size"] = [680, max(620, 160 + lines * 22)]
    apply_rodent_layout(result, PATH)
    return result


START_NOTE = """# Qwen Image 2.1 · Background Remover

**Research / Evaluation, nicht kommerziell ohne separate Lizenz.**
[Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE).

1. **BILD** wählen (Pixaroma Load Image, Resize **off**). Unterordner wie `input/Sheets/` werden angezeigt.
2. **Queue**. Qwen Image 2.1 bearbeitet das Bild mit der offiziellen Anweisung
   `Remove the background, and output a PNG image`; der neue 2.1-VAE liefert **RGBA**.
3. Ergebnis unter **output/Qwen_Image_2_1/**:
   - `BG_Removed_*.png`: freigestelltes Motiv mit echtem Alpha-Kanal
   - `BG_Mask_*.png`: Alpha-Maske als Graustufenbild (weiß = Motiv), z. B. für Compositing
4. **VERGLEICH** zeigt Original und Ergebnis übereinander.

**Format:** `resolution = 0` behält das Bildformat (auf 32 px gerundet). Sehr große Bilder kosten Zeit und
Speicher; `1024` begrenzt auf ca. 1 Megapixel, 2048 ist die native 2K-Obergrenze.

**Anweisung anpassen:** Was stehen bleiben soll, lässt sich benennen, z. B.
`Remove the background, keep only the person and the guitar, and output a PNG image`.
**Collagen / Charaktersheets:** Die Standardanweisung hält dort oft *alles* für Hintergrund (Ergebnis komplett
transparent). Getestet und sauber:
`Remove only the plain background. Keep every person, all clothing, accessories, text and drawn elements unchanged, and output a PNG image`

**Grenzen:** Qwen erzeugt das Motiv neu (Edit, kein reines Maskieren). Farben und feine Details bleiben
nah am Original, sind aber nicht pixelidentisch; Haare und Glas können halbtransparente Säume haben.
Offizielle Werte: **25 Schritte, CFG 1, Euler, Simple, Seed 0**. Bedienung und Testwerte: `docs/QWEN_IMAGE21_BACKGROUND_REMOVER_V124.md`.
"""

DOWNLOAD_TAIL = """

Dieselben drei Gewichte wie die beiden Qwen-Image-2.1-Workflows aus v1.2.1 (keine zusätzliche Modelldatei).
Kein Cloud-API-Aufruf, kein zusätzliches Segmentierungsmodell.
"""


def build_all() -> dict[str, dict]:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    return {PATH: build(schemas)}


def main() -> None:
    for path, workflow in build_all().items():
        target = ROOT / "workflows" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
