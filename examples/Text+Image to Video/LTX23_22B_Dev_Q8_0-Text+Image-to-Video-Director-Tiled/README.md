# LTX-2.3 Director (GGUF Q8_0) · Zeitleiste → Video, gekachelt

**Workflow-Datei:** [`workflows/Text+Image to Video/LTX23_22B_Dev_Q8_0-Text+Image-to-Video-Director-Tiled.json`](../../../workflows/Text%2BImage%20to%20Video/LTX23_22B_Dev_Q8_0-Text%2BImage-to-Video-Director-Tiled.json)  
**Kategorie:** Text+Image to Video · **Eingabe → Ausgabe:** Text + Bild → Video + Audio · **Quant:** GGUF Q8_0

Bis v1.3.0 hieß der Workflow `LTX23_Director_Q8_GGUF-Tiled-Video-Generation.json`.

Mehrere Szenen-Prompts auf einer Zeitleiste; zweistufig mit gekacheltem Dekodieren für lange Clips.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/ltx23-22b-dev-q8-0-text-image-to-video-director-tiled>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| LoRA | `ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors` | BF16 | 2,5 GiB |
| VAE | `LTX23_audio_vae_bf16.safetensors` | BF16 | 0,3 GiB |
| VAE | `LTX23_video_vae_bf16.safetensors` | BF16 | 1,4 GiB |
| VAE | `taeltx2_3.safetensors` | FP16 | 0,0 GiB |
| Latent-Upscaler | `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | BF16 | 0,9 GiB |
| Text-Encoder | `gemma_3_12B_it_fp4_mixed.safetensors` | FP4 mixed | 8,8 GiB |
| Text-Encoder | `ltx-2.3_text_projection_bf16.safetensors` | BF16 | 2,1 GiB |
| Diffusionsmodell | `ltx-2.3-22b-dev-Q8_0.gguf` | Q8_0 (GGUF) | 21,2 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Timeline · drei Textsegmente

| Einstellung | Wert |
|---|---|
| global prompt | Cinematic nature short film. A red fox in a snowy pine forest at golden hour, photorealistic, soft volumetric light, fine snow in the air. |
| segmente | 40 Frames: Wide aerial shot slowly descending toward the fox walking through deep snow between the pines. | 40 Frames: Close-up of the fox's face as it stops and sniffs the air, its breath visible in the cold. | 40 Frames: The fox leaps high and dives head-first into the snow to catch a mouse, snow sprays around it. |
| duration | 5 s (120 Frames) |
| seed | 42 |
| scheduler | linear_quadratic |
| sampler_name | euler |
| cfg | 1 |
| Dauer (Ausführung) | 4 min 6 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 29,3 GiB / 24,6 GiB |
| VRAM RX 9070 XT (belegt / PyTorch-Spitze) | 2,6 GiB / 0,1 GiB |
| RAM (ComfyUI-Prozess) | 33,1 GiB |

Timeline auf 5 s gekürzt (3 × 40 Frames) und mit eigenem Inhalt statt der Beispiel-Timeline gefüllt.

Ausgabe · Ausgabe: [fox-timeline.mp4](fox-timeline.mp4)  

### Timeline · Startbild + zwei Textsegmente

| Einstellung | Wert |
|---|---|
| global prompt | A friendly man in his thirties in a softly lit room, natural window light, photorealistic, 35 mm film look, calm and warm mood. |
| segmente | 8 Frames: He looks into the camera and smiles. | 56 Frames: He raises his hand and waves at the camera, smiling warmly. | 56 Frames: He laughs softly, nods and gives a thumbs up. |
| duration | 5 s (120 Frames) |
| seed | 42 |
| scheduler | linear_quadratic |
| sampler_name | euler |
| cfg | 1 |
| Dauer (Ausführung) | 4 min 58 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 28,6 GiB / 24,6 GiB |
| RAM (ComfyUI-Prozess) | 34,3 GiB |

Erstes Segment ist ein Bildsegment (Keyframe) mit dem Porträt, danach zwei reine Textsegmente.

Eingabe · ex_portrait_man.png: ![ex_portrait_man.png](thumbs/input_ex_portrait_man.webp) ([Datei](input_ex_portrait_man.webp))  
Ausgabe · Ausgabe: [man-keyframe.mp4](man-keyframe.mp4)
