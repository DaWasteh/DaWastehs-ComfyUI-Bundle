# LTX-2.3 22B dev (MXFP8) · Text → Video mit Ton

**Workflow-Datei:** [`workflows/Text to Video/LTX23_22B_Dev_MXFP8-Text-to-Video.json`](../../../workflows/Text%20to%20Video/LTX23_22B_Dev_MXFP8-Text-to-Video.json)  
**Kategorie:** Text to Video · **Eingabe → Ausgabe:** Text → Video + Audio · **Quant:** MXFP8

Bis v1.3.0 hieß der Workflow `LTX23_dev_mxfp8-Text-to-Video.json`.

LTX-2.3 erzeugt Bild und Ton gemeinsam (Gemma-3-12B-Text-Encoder). 28 Schritte, CFG 3, 1280×704, Länge über „Output Duration“.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/ltx23-22b-dev-mxfp8-text-to-video>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Diffusionsmodell | `ltx-2.3-22b-dev_transformer_only_mxfp8_block32.safetensors` | MXFP8 | 22,4 GiB |
| VAE | `LTX23_video_vae_bf16.safetensors` | BF16 | 1,4 GiB |
| Text-Encoder | `gemma_3_12B_it_fp8_e4m3fn.safetensors` | FP8 | 12,3 GiB |
| Text-Encoder | `ltx-2.3_text_projection_bf16.safetensors` | BF16 | 2,1 GiB |
| Audio-VAE | `LTX23_audio_vae_bf16.safetensors` | BF16 | 0,3 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Fuchs im Schnee

Prompt:

```text
A red fox trots through fresh snow in a quiet pine forest at sunrise, its breath visible in the cold air, soft golden light between the trees, the camera tracks alongside at ground level, gentle crunching of snow and distant birdsong
```

Negativ:

```text
low quality, blurry, distorted, watermark, static, jpeg artifacts
```

| Einstellung | Wert |
|---|---|
| duration | 4 s |
| seed | 42 |
| sampler_name | euler |
| scheduler | normal |
| steps | 28 |
| denoise | 1 |
| cfg | 3 |
| Dauer (Ausführung) | 8 min 24 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,3 GiB / 26,5 GiB |
| RAM (ComfyUI-Prozess) | 35,3 GiB |

Ausgabe · Video speichern: [fox.mp4](fox.mp4)
