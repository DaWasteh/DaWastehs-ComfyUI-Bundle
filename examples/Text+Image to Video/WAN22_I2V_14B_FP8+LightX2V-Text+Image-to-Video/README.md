# WAN 2.2 I2V 14B (FP8) + LightX2V · Bild + Text → Video

**Workflow-Datei:** [`workflows/Text+Image to Video/WAN22_I2V_14B_FP8+LightX2V-Text+Image-to-Video.json`](../../../workflows/Text%2BImage%20to%20Video/WAN22_I2V_14B_FP8%2BLightX2V-Text%2BImage-to-Video.json)  
**Kategorie:** Text+Image to Video · **Eingabe → Ausgabe:** Bild + Text → Video · **Quant:** FP8

Bis v1.3.0 hieß der Workflow `WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json`.

WAN 2.2 I2V in FP8 mit LightX2V-LoRAs; 4 Schritte, 1280×720, 16 fps.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/wan22-i2v-14b-fp8-lightx2v-text-image-to-video>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Diffusionsmodell | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` | FP8 | 13,3 GiB |
| LoRA | `wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors` | FP32 | 1,1 GiB |
| Diffusionsmodell | `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | FP8 | 13,3 GiB |
| LoRA | `wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors` | FP32 | 1,1 GiB |
| Text-Encoder / LLM | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | FP8 | 6,3 GiB |
| VAE | `wan_2.1_vae.safetensors` | BF16 | 0,2 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Bergsee wird lebendig

Prompt:

```text
Gentle ripples spread across the calm alpine lake, light morning mist drifts slowly over the water, a bird flies past the mountains, slow push-in camera move
```

Negativ:

```text
色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走
```

| Einstellung | Wert |
|---|---|
| duration | 5 s |
| seed | 42 |
| shift | 5 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | simple |
| Dauer (Ausführung) | 7 min 39 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,4 GiB / 21,6 GiB |
| RAM (ComfyUI-Prozess) | 29,4 GiB |

Eingabe · ex_landscape_lake.png: ![ex_landscape_lake.png](thumbs/input_ex_landscape_lake.webp) ([Datei](input_ex_landscape_lake.webp))  
Ausgabe · Video speichern: [lake.mp4](lake.mp4)  

### Tanz (Hochformat)

Prompt:

```text
The woman dances casually in place, swaying her hips and moving her arms to the rhythm, friendly smile, static camera, plain grey studio background
```

Negativ:

```text
色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走
```

| Einstellung | Wert |
|---|---|
| duration | 5 s |
| width | 480 |
| height | 832 |
| seed | 43 |
| shift | 5 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | simple |
| Dauer (Ausführung) | 2 min 38 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 22,4 GiB / 17,1 GiB |
| RAM (ComfyUI-Prozess) | 30,9 GiB |

Eingabe · ex_fullbody_woman.png: ![ex_fullbody_woman.png](thumbs/input_ex_fullbody_woman.webp) ([Datei](input_ex_fullbody_woman.webp))  
Ausgabe · Video speichern: [dance.mp4](dance.mp4)  

### Hund bellt

Prompt:

```text
The golden retriever barks twice towards the camera and wags its tail, grass moves slightly in the wind, static camera
```

Negativ:

```text
色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走
```

| Einstellung | Wert |
|---|---|
| duration | 5 s |
| width | 832 |
| height | 832 |
| seed | 44 |
| shift | 5 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | simple |
| Dauer (Ausführung) | 4 min 55 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,6 GiB / 25,1 GiB |
| RAM (ComfyUI-Prozess) | 30,1 GiB |

Eingabe · ex_dog_photo.png: ![ex_dog_photo.png](thumbs/input_ex_dog_photo.webp) ([Datei](input_ex_dog_photo.webp))  
Ausgabe · Video speichern: [dog.mp4](dog.mp4)
