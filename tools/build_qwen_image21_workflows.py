#!/usr/bin/env python3
"""Rebuild the two flat Qwen Image 2.1 bundle graphs; no runtime/model writes."""
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
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v121"
PATHS = {
    "t2i": "Text to Image/Qwen_Image_2_1_BF16-Text-to-Image.json",
    "image_edit": "Image Editing/Qwen_Image_2_1_BF16-Multi-Image-Edit.json",
}
MODEL = "Qwen\\qwen_image_2.1_bf16.safetensors"
CLIP = "Qwen\\qwen3vl_8b_int8_convrot.safetensors"
VAE = "qwen-image\\qwen_image_2.1_vae_bf16.safetensors"
MARKER = "dawasteh_qwen_image21"


def finish(g: Graph, path: str, mode: str) -> dict:
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v121:" + path))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {
        "version": 1,
        "mode": mode,
        "source_manifest": "tools/workflow_templates/v121/sources.json",
        "model_manifest": "tools/workflow_templates/v121/models.json",
        "validation_report": "performance/rdna4/qwen-image21-v121-validation.json",
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


def build(mode: str, schemas: dict) -> dict:
    edit = mode == "image_edit"
    source = json.loads((SOURCES / f"image_qwen_image_2_1_{mode}.json").read_text(encoding="utf-8"))
    original = next(n for n in source["nodes"] if n["id"] == 459)
    prompt_text = original["widgets_values"][1 if edit else 0]
    g = Graph(schemas)
    model = g.add("UNETLoader", "QWEN IMAGE 2.1 · BF16 · R9700", unet_name=MODEL)
    clip = g.add("CLIPLoader", "TEXTENCODER · Qwen3-VL 8B INT8 ConvRot", clip_name=CLIP, type="qwen_image", device="default")
    vae = g.add("VAELoader", "VAE · nur Qwen Image 2.1 · RGBA", vae_name=VAE)
    pos = g.prompt("EDIT · <image1> = Basis · <image2> = Referenz" if edit else "PROMPT · Bildbeschreibung / gewünschter Text", prompt_text)
    neg = g.prompt("NEGATIV · offiziell leer · CFG 1 ignoriert Negativprompt", "")
    encode = g.add("TextEncodeQwenImage21", "QWEN 2.1 · Referenzen + Positiv/Negativ + passendes Latent", resolution=0 if edit else 1024)
    # Autogrow V3 is a frontend socket template, never a literal API input.
    encode["inputs"] = [slot for slot in encode["inputs"] if slot["name"] != "images"]
    if edit:
        for i in range(1, 4):
            encode["inputs"].append({"name": f"images.image_{i}", "type": "IMAGE", "link": None})
    g.connect(clip, 0, encode, "clip")
    g.connect(pos, 0, encode, "prompt")
    g.connect(neg, 0, encode, "negative_prompt")
    resolution = g.add("PixaromaResolution", "FORMAT · nur bei FREIE GRÖSSE an" if edit else "FORMAT · 1024² Start · 32px-Raster · 2048² optional")
    resolution["properties"]["resolutionState"] = json.dumps({
        "mode": "preset", "ratio": "1:1", "w": 1024, "h": 1024,
        "custom_w": 1024, "custom_h": 1024, "custom_ratio_w": 1,
        "custom_ratio_h": 1, "snap": 32,
    })
    resolution["size"] = [480, 420]
    empty = g.add("EmptyLatentImage", "LEERES LATENT · Ausgabeformat", width=1024, height=1024, batch_size=1)
    g.connect(resolution, 0, empty, "width")
    g.connect(resolution, 1, empty, "height")
    latent = empty
    if edit:
        loads = []
        for i, image in enumerate(("portrait_model_denim.png", "clothing_light_blue_denim_shirt.png"), 1):
            load = g.add("PixaromaLoadImage", f"BILD {i} · " + ("Basis / Ausgabeformat" if i == 1 else "Kleidung / zusätzliche Referenz"), image=image)
            load["properties"]["loadImagePixState"] = json.dumps({"version": 1, "mode": "off", "snap": 0})
            load["size"] = [480, 620]
            loads.append(load)
            g.connect(load, 0, encode, f"images.image_{i}")
        g.connect(vae, 0, encode, "vae")
        latent = g.add("ComfySwitchNode", "FREIE GRÖSSE · aus = Format von Bild 1 (empfohlen)", switch=False)
        # MatchType V3 resolves to LATENT in this graph, as in the official UI file.
        for slot in latent["inputs"]:
            if slot["name"] in ("on_false", "on_true"):
                slot["type"] = "LATENT"
        latent["outputs"][0]["type"] = "LATENT"
        g.connect(encode, 2, latent, "on_false")
        g.connect(empty, 0, latent, "on_true")
        cache = g.add("QwenImage21Cache", "EDIT KV-CACHE · auto / verlustfrei", device="auto", dtype="default")
        g.connect(model, 0, cache, "model")
        model = cache
    sample = g.add("KSampler", "SAMPLER · offiziell 25 / CFG 1 / Euler / Simple", seed=0, steps=25, cfg=1.0, sampler_name="euler", scheduler="simple", denoise=1.0)
    for src, slot, field in [(model, 0, "model"), (encode, 0, "positive"), (encode, 1, "negative"), (latent, 0, "latent_image")]:
        g.connect(src, slot, sample, field)
    decode = g.add("VAEDecode", "DECODE · neuer 2.1-VAE · RGBA-Ausgabe")
    g.connect(sample, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    save = g.add("PixaromaSaveImage", "SPEICHERN · PNG + Workflow + Alpha")
    save["properties"]["saveImageState"] = json.dumps({
        "version": 1, "folder": "", "pattern": f"Qwen_Image_2_1/{'Edit' if edit else 'T2I'}_%counter%",
        "format": "png", "quality": 100, "embedWorkflow": True,
        "civitaiMeta": False, "saveOnRun": True, "counterDigits": 5,
    })
    save["size"] = [500, 820]
    g.connect(decode, 0, save, "images")
    if edit:
        compare = g.add("PixaromaCompare", "VERGLEICH · Bild 1 ↔ Ergebnis")
        compare["size"] = [540, 640]
        g.connect(loads[0], 0, compare, "image1")
        g.connect(decode, 0, compare, "image2")
    g.note("START HIER · Qwen Image 2.1 · v1.2.1", f"""# Qwen Image 2.1 · {'Multi-Image Edit' if edit else 'Text to Image'}

**Research / Evaluation, nicht kommerziell ohne separate Lizenz.**
[Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE).

1. Modellnamen prüfen, Pixaroma-Prompt bearbeiten, dann Queue starten.
2. Offizielle Startwerte: **25 Schritte, CFG 1, Euler, Simple, Denoise 1**.
   Seed 0 ist fest für reproduzierbare Ergebnisse; im Sampler auf randomize stellen für Variation.
   CFG 1 ignoriert den Negativprompt. Höhere CFG verändert Verhalten und Rechenaufwand.
3. Genau eine zentrale DaW GPU-Steuerung; MODEL/CLIP/VAE sind wirklich verbunden.
   Standard: alles R9700 (gpu:0), kein ungeprüfter Split. gpu:1 ist optional, keine Parallelberechnung.
4. Pixaroma Timer misst den Lauf; PNG landet unter **output/Qwen_Image_2_1/**.
   PNG erhält Alpha und Workflow-Metadaten; JPG verliert beides/Transparenz.

{'## Bilder und Format' if edit else '## Format und Transparenz'}
""" + ("""Pixaroma Load Image startet mit Resize **off**. Keine doppelte Skalierung.
**resolution = 0** am Textencoder übernimmt jede Referenzgröße, auf Vielfache von 32 gerundet.
**1024** bedeutet ca. 1 Megapixel je Referenz, nicht eine feste Breite. Das Seitenverhältnis bleibt erhalten.
Das LATENT von TextEncodeQwenImage21 bestimmt korrekt das Ausgabeformat von Bild 1.
FREIE GRÖSSE **aus** ist die Herstellerempfehlung; **an** nutzt Pixaroma Resolution,
kann aber bei abweichendem Format Motiv/Position verschieben. Der Schalter erzeugt keine Maske.

<image1> = Basis, <image2> = Kleidung/Referenz. Für nur ein Bild den zweiten Loader
mit Strg+M stummschalten UND den Prompt anpassen. Weitere Bilder am Autogrow-Eingang
verbinden (Core unterstützt bis zu 16); zusätzliche Referenzen kosten VRAM/RAM.
Die zwei Startbilder kommen aus Comfy-Orgs offiziellen Beispielen; Links im Download-Hinweis.
Die RGB-Loader geben Eingabe-Alpha getrennt als MASK aus; diese ist hier nicht verbunden.
Dies ist kein Masken-Inpainting-Workflow. Der Decoder kann dennoch RGBA ausgeben.

KV-Cache auto/default bleibt verlustfrei. cpu kann VRAM sparen; off rechnet Referenzen
in jedem Schritt neu. int8/int4 sind qualitätsverändernde Optionen, nicht Standard.
""" if edit else """Pixaroma Resolution steuert Breite/Höhe direkt, Standard 1024×1024 mit 32px-Raster.
2K: 1:1 und 2048×2048 wählen. Mehr Pixel brauchen deutlich mehr Zeit und Speicher.
Transparenz per Prompt anfordern:
`This is an RGBA format image with transparency. [Motiv]. The image has an alpha channel and a transparent background.`
Der neue VAE liefert RGBA; ein Alpha-Kanal garantiert allein noch keine saubere Freistellung.
""") + "\nBedienung und genaue Testgrenzen: docs/QWEN_IMAGE21_V121.md. Kein Cloud-API-Aufruf.\n")
    model_lines = []
    for entry in json.loads((SOURCES / "models.json").read_text()):
        url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
        model_lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}`")
    if edit:
        for entry in json.loads((SOURCES / "inputs.json").read_text()):
            model_lines.append(f"- [{entry['file']}]({entry['url']}) → `ComfyUI/input/{entry['file']}`")
    g.note("DOWNLOADS · Modelle / Zielordner / keine alten Qwen-VAEs", "# Benötigte Dateien\n\n" + "\n\n".join(model_lines) + "\n\nAlle drei Gewichte werden von beiden Workflows gemeinsam verwendet.\nBF16-DiT + INT8-ConvRot-Textencoder ist bewusst das vorhandene lokale Profil.\nDie alten Qwen-Image/Edit-VAEs und Qwen2.5-VL sind NICHT austauschbar.\nSeparate Qwen3.5-Prompt-Enhancer sind optional und werden hier nicht geladen.\n")
    return finish(g, PATHS[mode], mode)


def build_all() -> dict[str, dict]:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    return {path: build(mode, schemas) for mode, path in PATHS.items()}


def main() -> None:
    for path, workflow in build_all().items():
        target = ROOT / "workflows" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
