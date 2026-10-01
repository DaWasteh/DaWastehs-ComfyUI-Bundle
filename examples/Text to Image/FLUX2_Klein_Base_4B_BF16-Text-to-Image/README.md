# FLUX.2 Klein Base 4B · Text → Bild

**Workflow-Datei:** [`workflows/Text to Image/FLUX2_Klein_Base_4B_BF16-Text-to-Image.json`](../../../workflows/Text%20to%20Image/FLUX2_Klein_Base_4B_BF16-Text-to-Image.json)  
**Kategorie:** Text to Image · **Eingabe → Ausgabe:** Text → Bild · **Quant:** BF16

Bis v1.3.0 hieß der Workflow `FLUX2_Klein_base_4b-Text-to-Image.json`.

Das nicht destillierte Basismodell von Klein 4B (24 Schritte) – gedacht als Grundlage für LoRA-Training.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/flux2-klein-base-4b-bf16-text-to-image>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Diffusionsmodell | `flux-2-klein-base-4b.safetensors` | BF16 | 7,2 GiB |
| Text-Encoder / LLM | `qwen_3_4b.safetensors` | BF16 | 7,5 GiB |
| VAE | `flux2-vae.safetensors` | FP32 | 0,3 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 59 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 25,3 GiB / 17,0 GiB |
| RAM (ComfyUI-Prozess) | 17,1 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 38 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,0 GiB / 20,1 GiB |
| RAM (ComfyUI-Prozess) | 15,8 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 12 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 21,4 GiB / 18,2 GiB |
| RAM (ComfyUI-Prozess) | 3,0 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 59 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 26,2 GiB / 17,0 GiB |
| RAM (ComfyUI-Prozess) | 16,3 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 22 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 21,5 GiB / 20,1 GiB |
| RAM (ComfyUI-Prozess) | 3,0 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 17 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 20,8 GiB / 18,2 GiB |
| RAM (ComfyUI-Prozess) | 17,1 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 59 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 21,8 GiB / 17,0 GiB |
| RAM (ComfyUI-Prozess) | 16,3 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 22 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 21,6 GiB / 20,1 GiB |
| RAM (ComfyUI-Prozess) | 3,0 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 17 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 19,3 GiB / 18,2 GiB |
| RAM (ComfyUI-Prozess) | 16,3 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 59 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 26,2 GiB / 17,0 GiB |
| RAM (ComfyUI-Prozess) | 16,3 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 22 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 21,6 GiB / 20,1 GiB |
| RAM (ComfyUI-Prozess) | 3,0 GiB |

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
| steps | 24 |
| cfg | 5.0 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 16 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 19,3 GiB / 18,2 GiB |
| RAM (ComfyUI-Prozess) | 16,3 GiB |

Ausgabe · Speichern: [![Speichern](thumbs/poster-768x768.webp)](poster-768x768.webp)
