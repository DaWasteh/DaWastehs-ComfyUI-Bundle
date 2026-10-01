# FLUX.2 Klein 9B · Objekt in Hintergrund einfügen

**Workflow-Datei:** [`workflows/Image Editing/FLUX2_Klein_9B_KV_FP8-Two-Images-to-Image-Blend.json`](../../../workflows/Image%20Editing/FLUX2_Klein_9B_KV_FP8-Two-Images-to-Image-Blend.json)  
**Kategorie:** Image Editing · **Eingabe → Ausgabe:** Bild + Text → Bild · **Quant:** FP8

Bis v1.3.0 hieß der Workflow `FLUX2_Klein_9B_KV-Image-Blend.json`.

Vordergrund automatisch freistellen, auf den Hintergrund setzen und von Klein 9B an Licht, Perspektive und Schatten anpassen lassen.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/flux2-klein-9b-kv-fp8-two-images-to-image-blend>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Text-Encoder / LLM | `qwen_3_8b_fp8mixed.safetensors` | FP8 mixed | 8,1 GiB |
| VAE | `flux2-vae.safetensors` | FP32 | 0,3 GiB |
| Diffusionsmodell | `flux-2-klein-9b-kv-fp8.safetensors` | FP8 | 9,1 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Objekt in Hintergrund einfügen

Prompt:

```text
Place the teapot naturally on the kitchen table, matching the light, perspective and shadows
```

| Einstellung | Wert |
|---|---|
| seed | 7 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 32 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 24,4 GiB / 22,0 GiB |
| RAM (ComfyUI-Prozess) | 9,3 GiB |

Eingabe · ex_kitchen_table.png: ![ex_kitchen_table.png](thumbs/input_ex_kitchen_table.webp) ([Datei](input_ex_kitchen_table.webp))  
Eingabe · ex_product_teapot.png: ![ex_product_teapot.png](thumbs/input_ex_product_teapot.webp) ([Datei](input_ex_product_teapot.webp))  
Ausgabe · Ausgabe: [![Ausgabe](thumbs/teapot-table.webp)](teapot-table.webp) · [Volle Auflösung (1024×1024, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](teapot-table.webp)
