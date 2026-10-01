# MiniMax FastH3 (INT8) · Video Ultimate Upscale

**Workflow-Datei:** [`workflows/Video Upscaling/MiniMax_FastH3_INT8-Video-Ultimate-Upscale.json`](../../../workflows/Video%20Upscaling/MiniMax_FastH3_INT8-Video-Ultimate-Upscale.json)  
**Kategorie:** Video Upscaling · **Eingabe → Ausgabe:** Video → Video · **Quant:** INT8

Bis v1.3.0 hieß der Workflow `MiniMax_H3-Ultimate-Upscale-FastH3.json`.

Wie der Latent-Upscaler, mit zweitem FastH3-Durchgang in voller Zielgröße (4 Schritte).

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/minimax-fasth3-int8-video-ultimate-upscale>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Diffusionsmodell | `fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors` | INT8 | 20,6 GiB |
| VAE | `minimax_h3_video_vae_fp16.safetensors` | FP16 | 4,8 GiB |
| VAE | `minimax_h3_audio_vae_fp32.safetensors` | FP32 | 0,6 GiB |
| Text-Encoder | `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | INT8 | 25,3 GiB |
| Latent-Upscaler | `minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors` | BF16 | 0,6 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### 480×832 → ×1,5

| Einstellung | Wert |
|---|---|
| Dauer (Ausführung) | 3 min 41 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,2 GiB / 26,0 GiB |
| RAM (ComfyUI-Prozess) | 33,1 GiB |

Block 1 wird am Pause-Knoten geprüft, dann „Continue“ für den Rest (wie im Workflow vorgesehen).

Eingabe · ex_dance_woman.mp4: [input_ex_dance_woman.mp4](input_ex_dance_woman.mp4)  
Ausgabe · BLOCK 1 · Block speichern + Vorschau mit Originalton: [dance__n21.mp4](dance__n21.mp4)  
Ausgabe · VU 4 · HOCHSKALIERTES VIDEO · Originalton unverändert: [dance__n31.mp4](dance__n31.mp4)  

BLOCKPLAN · Blöcke, Schnitte, Zielgröße:

```text
ex_dance_woman.mp4: 480x832 -> 704x1248 (x1.50), 122 Frames (5.08 s), 1 Blöcke, 0 harte Schnitte erkannt

  1. Frames 0–121 (5.08 s)
```
