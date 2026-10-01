# Krea 2 Turbo (Low VRAM) · Text → Bild

**Workflow-Datei:** [`workflows/Text to Image/Krea2_Turbo_FP8-Text-to-Image-Low-VRAM.json`](../../../workflows/Text%20to%20Image/Krea2_Turbo_FP8-Text-to-Image-Low-VRAM.json)  
**Kategorie:** Text to Image · **Eingabe → Ausgabe:** Text → Bild · **Quant:** FP8

Bis v1.3.0 hieß der Workflow `Krea2_turbo-Low-VRAM-Text-to-Image.json`.

Krea 2 Turbo in FP8 mit FP8-Text-Encoder – die sparsamste Krea-Variante, 8 Schritte.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/krea2-turbo-fp8-text-to-image-low-vram>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Text-Encoder / LLM | `qwen3vl_4b_fp8_scaled.safetensors` | FP8 | 4,9 GiB |
| VAE | `qwen_image_vae.safetensors` | BF16 | 0,2 GiB |
| Diffusionsmodell | `krea2_turbo_fp8_scaled.safetensors` | FP8 | 12,2 GiB |

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 0 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 17,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/robot-1536x1536.webp)](robot-1536x1536.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 20 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,0 GiB / 18,5 GiB |
| RAM (ComfyUI-Prozess) | 12,9 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/robot-1024x1024.webp)](robot-1024x1024.webp) · [Volle Auflösung (768×768, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](robot-1024x1024.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 6 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 18,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/robot-768x768.webp)](robot-768x768.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 0 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 17,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/portrait-1536x1536.webp)](portrait-1536x1536.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 6 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 18,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/portrait-1024x1024.webp)](portrait-1024x1024.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 6 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 18,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/portrait-768x768.webp)](portrait-768x768.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 0 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 17,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/fantasy-1536x1536.webp)](fantasy-1536x1536.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 6 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 18,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/fantasy-1024x1024.webp)](fantasy-1024x1024.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 6 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 18,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/fantasy-768x768.webp)](fantasy-768x768.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 0 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 17,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/poster-1536x1536.webp)](poster-1536x1536.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 6 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 18,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/poster-1024x1024.webp)](poster-1024x1024.webp)  

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
| steps | 8 |
| cfg | 1 |
| sampler_name | er_sde |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 6 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,2 GiB / 18,5 GiB |
| RAM (ComfyUI-Prozess) | 1,0 GiB |

Ausgabe · Ausgabe: [![Ausgabe](thumbs/poster-768x768.webp)](poster-768x768.webp)
