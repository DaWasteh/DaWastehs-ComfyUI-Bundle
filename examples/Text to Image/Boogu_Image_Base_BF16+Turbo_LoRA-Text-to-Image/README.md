# Boogu + Turbo-LoRA · Text → Bild

**Workflow-Datei:** [`workflows/Text to Image/Boogu_Image_Base_BF16+Turbo_LoRA-Text-to-Image.json`](../../../workflows/Text%20to%20Image/Boogu_Image_Base_BF16%2BTurbo_LoRA-Text-to-Image.json)  
**Kategorie:** Text to Image · **Eingabe → Ausgabe:** Text → Bild · **Quant:** BF16

Bis v1.3.0 hieß der Workflow `Boogu_turbo_via_LoRA-Text-to-Image.json`.

Dasselbe Boogu-Basismodell mit Turbo-LoRA: 4 Schritte, CFG 1 – etwa zehnmal schneller als ohne LoRA.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/boogu-image-base-bf16-turbo-lora-text-to-image>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Diffusionsmodell | `boogu_image_base_bf16.safetensors` | BF16 | 19,2 GiB |
| LoRA | `boogu_image_turbo_lora_rank_128_bf16.safetensors` | BF16 | 1,3 GiB |
| Text-Encoder / LLM | `qwen3vl_8b_fp8_scaled.safetensors` | FP8 | 9,9 GiB |
| VAE | `flux1_vae_bf16.safetensors` | BF16 | 0,2 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### 3D-Render · Roboter-Barista · 1536 × 1536

Prompt:

```text
A cute small robot barista made of brushed copper and cream enamel with big round glowing eyes, carefully pouring latte art into a cappuccino cup on a wooden café counter, cozy café in the background, 3D render, soft studio lighting, pastel colors
```

| Einstellung | Wert |
|---|---|
| seed | 303 |
| width | 1536 |
| height | 1536 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 20 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,2 GiB / 24,9 GiB |
| RAM (ComfyUI-Prozess) | 31,3 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/robot-1536x1536.webp)](robot-1536x1536.webp)  

### 3D-Render · Roboter-Barista · 1024 × 1024

Prompt:

```text
A cute small robot barista made of brushed copper and cream enamel with big round glowing eyes, carefully pouring latte art into a cappuccino cup on a wooden café counter, cozy café in the background, 3D render, soft studio lighting, pastel colors
```

| Einstellung | Wert |
|---|---|
| seed | 303 |
| width | 1024 |
| height | 1024 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 54 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 29,5 GiB / 24,2 GiB |
| RAM (ComfyUI-Prozess) | 30,1 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/robot-1024x1024.webp)](robot-1024x1024.webp) · [Volle Auflösung (1024×1024, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](robot-1024x1024.webp)  

### 3D-Render · Roboter-Barista · 768 × 768

Prompt:

```text
A cute small robot barista made of brushed copper and cream enamel with big round glowing eyes, carefully pouring latte art into a cappuccino cup on a wooden café counter, cozy café in the background, 3D render, soft studio lighting, pastel colors
```

| Einstellung | Wert |
|---|---|
| seed | 303 |
| width | 768 |
| height | 768 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 27 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 28,7 GiB / 23,5 GiB |
| RAM (ComfyUI-Prozess) | 30,5 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/robot-768x768.webp)](robot-768x768.webp)  

### Porträtfoto · Leuchtturmwärter · 1536 × 1536

Prompt:

```text
Close-up portrait photograph of an elderly lighthouse keeper with a weathered, wrinkled face and a short grey beard, wearing a navy blue knit sweater and a dark wool cap, soft window light from the left, shallow depth of field, 85 mm lens, natural skin texture, calm expression
```

| Einstellung | Wert |
|---|---|
| seed | 101 |
| width | 1536 |
| height | 1536 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 31 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 25,5 GiB / 20,4 GiB |
| RAM (ComfyUI-Prozess) | 31,0 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/portrait-1536x1536.webp)](portrait-1536x1536.webp)  

### Porträtfoto · Leuchtturmwärter · 1024 × 1024

Prompt:

```text
Close-up portrait photograph of an elderly lighthouse keeper with a weathered, wrinkled face and a short grey beard, wearing a navy blue knit sweater and a dark wool cap, soft window light from the left, shallow depth of field, 85 mm lens, natural skin texture, calm expression
```

| Einstellung | Wert |
|---|---|
| seed | 101 |
| width | 1024 |
| height | 1024 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 1 min 2 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 28,5 GiB / 23,7 GiB |
| RAM (ComfyUI-Prozess) | 31,4 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/portrait-1024x1024.webp)](portrait-1024x1024.webp)  

### Porträtfoto · Leuchtturmwärter · 768 × 768

Prompt:

```text
Close-up portrait photograph of an elderly lighthouse keeper with a weathered, wrinkled face and a short grey beard, wearing a navy blue knit sweater and a dark wool cap, soft window light from the left, shallow depth of field, 85 mm lens, natural skin texture, calm expression
```

| Einstellung | Wert |
|---|---|
| seed | 101 |
| width | 768 |
| height | 768 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 13 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,0 GiB / 23,5 GiB |
| RAM (ComfyUI-Prozess) | 31,3 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/portrait-768x768.webp)](portrait-768x768.webp)  

### Fantasy-Gemälde · Stadt über den Wolken · 1536 × 1536

Prompt:

```text
A floating island city high above the clouds at golden hour, white stone towers and arched bridges, waterfalls pouring off the island edges into the clouds, two wooden airships with canvas sails, warm sunlight, highly detailed fantasy digital painting
```

| Einstellung | Wert |
|---|---|
| seed | 202 |
| width | 1536 |
| height | 1536 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 34 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 26,9 GiB / 23,1 GiB |
| RAM (ComfyUI-Prozess) | 28,7 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/fantasy-1536x1536.webp)](fantasy-1536x1536.webp)  

### Fantasy-Gemälde · Stadt über den Wolken · 1024 × 1024

Prompt:

```text
A floating island city high above the clouds at golden hour, white stone towers and arched bridges, waterfalls pouring off the island edges into the clouds, two wooden airships with canvas sails, warm sunlight, highly detailed fantasy digital painting
```

| Einstellung | Wert |
|---|---|
| seed | 202 |
| width | 1024 |
| height | 1024 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 27 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 27,4 GiB / 24,3 GiB |
| RAM (ComfyUI-Prozess) | 30,3 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/fantasy-1024x1024.webp)](fantasy-1024x1024.webp)  

### Fantasy-Gemälde · Stadt über den Wolken · 768 × 768

Prompt:

```text
A floating island city high above the clouds at golden hour, white stone towers and arched bridges, waterfalls pouring off the island edges into the clouds, two wooden airships with canvas sails, warm sunlight, highly detailed fantasy digital painting
```

| Einstellung | Wert |
|---|---|
| seed | 202 |
| width | 768 |
| height | 768 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 10 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,0 GiB / 24,6 GiB |
| RAM (ComfyUI-Prozess) | 31,3 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/fantasy-768x768.webp)](fantasy-768x768.webp)  

### Schrift · Reiseplakat „ALPENBAHN“ · 1536 × 1536

Prompt:

```text
Vintage 1920s travel poster for a mountain railway, bold art deco lettering at the top that reads "ALPENBAHN" and smaller text at the bottom that reads "SEIT 1926", a red steam train crossing a stone viaduct, snowy alpine peaks, flat colors, lithograph print texture
```

| Einstellung | Wert |
|---|---|
| seed | 404 |
| width | 1536 |
| height | 1536 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 19 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 30,2 GiB / 24,6 GiB |
| RAM (ComfyUI-Prozess) | 31,3 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/poster-1536x1536.webp)](poster-1536x1536.webp)  

### Schrift · Reiseplakat „ALPENBAHN“ · 1024 × 1024

Prompt:

```text
Vintage 1920s travel poster for a mountain railway, bold art deco lettering at the top that reads "ALPENBAHN" and smaller text at the bottom that reads "SEIT 1926", a red steam train crossing a stone viaduct, snowy alpine peaks, flat colors, lithograph print texture
```

| Einstellung | Wert |
|---|---|
| seed | 404 |
| width | 1024 |
| height | 1024 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 14 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 28,9 GiB / 24,5 GiB |
| RAM (ComfyUI-Prozess) | 31,6 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/poster-1024x1024.webp)](poster-1024x1024.webp)  

### Schrift · Reiseplakat „ALPENBAHN“ · 768 × 768

Prompt:

```text
Vintage 1920s travel poster for a mountain railway, bold art deco lettering at the top that reads "ALPENBAHN" and smaller text at the bottom that reads "SEIT 1926", a red steam train crossing a stone viaduct, snowy alpine peaks, flat colors, lithograph print texture
```

| Einstellung | Wert |
|---|---|
| seed | 404 |
| width | 768 |
| height | 768 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | sgm_uniform |
| denoise | 1 |
| Dauer (Ausführung) | 1 min 7 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 29,7 GiB / 24,6 GiB |
| RAM (ComfyUI-Prozess) | 30,4 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/poster-768x768.webp)](poster-768x768.webp)
