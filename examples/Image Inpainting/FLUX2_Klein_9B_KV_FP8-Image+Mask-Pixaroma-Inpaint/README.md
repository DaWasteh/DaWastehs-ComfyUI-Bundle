# FLUX.2 Klein 9B · Pixaroma-Inpainting

**Workflow-Datei:** [`workflows/Image Inpainting/FLUX2_Klein_9B_KV_FP8-Image+Mask-Pixaroma-Inpaint.json`](../../../workflows/Image%20Inpainting/FLUX2_Klein_9B_KV_FP8-Image%2BMask-Pixaroma-Inpaint.json)  
**Kategorie:** Image Inpainting · **Eingabe → Ausgabe:** Bild + Maske + Text → Bild · **Quant:** FP8

Bis v1.3.0 hieß der Workflow `FLUX2_Klein_9B-Pixaroma-Inpaint.json`.

Wie das 4B-Inpainting, mit Klein 9B und Kontrollvorschau des Ausschnitts.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/flux2-klein-9b-kv-fp8-image-mask-pixaroma-inpaint>

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

### Maske: Brille ergänzen

Prompt:

```text
give her round tortoiseshell glasses
```

| Einstellung | Wert |
|---|---|
| seed | 7 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 34 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,0 GiB / 21,0 GiB |
| RAM (ComfyUI-Prozess) | 10,1 GiB |

Eingabe · Bild mit Maske (Alphakanal): ![Bild mit Maske (Alphakanal)](thumbs/input_ex_portrait_woman_mask_eyes.webp) ([Datei](input_ex_portrait_woman_mask_eyes.webp))  
Ausgabe · Ergebnis: [![Ergebnis](thumbs/glasses__n250-1.webp)](glasses__n250-1.webp) · [Volle Auflösung (1024×1024, WebP)](glasses__n250-1.webp)  
Ausgabe · Vorher: [![Vorher](thumbs/glasses__n250-2.webp)](glasses__n250-2.webp)  
Ausgabe · Generierter Ausschnitt: [![Generierter Ausschnitt](thumbs/glasses__n257.webp)](glasses__n257.webp)
