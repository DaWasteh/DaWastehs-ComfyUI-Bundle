# FLUX.2 Klein 9B · Collage → Bild

**Workflow-Datei:** [`workflows/Image Editing/FLUX2_Klein_9B_KV_FP8-Pixaroma-Composition-to-Image.json`](../../../workflows/Image%20Editing/FLUX2_Klein_9B_KV_FP8-Pixaroma-Composition-to-Image.json)  
**Kategorie:** Image Editing · **Eingabe → Ausgabe:** Collage + Text → Bild · **Quant:** FP8

Bis v1.3.0 hieß der Workflow `FLUX2_Klein_9B-Pixaroma-Composer-Edit.json`.

Bilder im Pixaroma-Composer zusammenschieben, Klein 9B verschmilzt die Collage zu einem stimmigen Bild.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/flux2-klein-9b-kv-fp8-pixaroma-composition-to-image>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| VAE | `flux2-vae.safetensors` | FP32 | 0,3 GiB |
| Text-Encoder / LLM | `qwen_3_8b_fp8mixed.safetensors` | FP8 mixed | 8,1 GiB |
| Diffusionsmodell | `flux-2-klein-9b-kv-fp8.safetensors` | FP8 | 9,1 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Mitgelieferte Szene

| Einstellung | Wert |
|---|---|
| seed | 7 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 32 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 28,3 GiB / 20,9 GiB |
| RAM (ComfyUI-Prozess) | 9,5 GiB |

Unverändert mit der im Workflow gespeicherten Pixaroma-Szene; eigene Szenen baust du im Editor-Knoten.

Ausgabe · Ausgabe: [![Ausgabe](thumbs/default.webp)](default.webp) · [Volle Auflösung (1024×1024, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](default.webp)
