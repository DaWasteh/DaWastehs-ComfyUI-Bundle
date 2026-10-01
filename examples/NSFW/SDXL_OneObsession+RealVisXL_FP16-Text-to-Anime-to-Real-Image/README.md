# SDXL One Obsession + RealVisXL · Text → Anime → realistisch

**Workflow-Datei:** [`workflows/NSFW/SDXL_OneObsession+RealVisXL_FP16-Text-to-Anime-to-Real-Image.json`](../../../workflows/NSFW/SDXL_OneObsession%2BRealVisXL_FP16-Text-to-Anime-to-Real-Image.json)  
**Kategorie:** NSFW · **Eingabe → Ausgabe:** Text → Bild · **Quant:** FP16

Bis v1.3.0 hieß der Workflow `SDXL_AniToReal_v2-Image-to-Image.json`.

Variante mit RealVisXL im zweiten Durchgang.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/sdxl-oneobsession-realvisxl-fp16-text-to-anime-to-real-image>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Modell | `oneObsession_v20Bold.safetensors` | FP16 | 6,5 GiB |
| Modell | `RealVisXL_V4.0.safetensors` | FP16 | 6,5 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Anime-Bild → realistische Version

Prompt:

```text
masterpiece, best quality, good quality, detailed face, 1woman, solo, adult woman, mature female, 35 years old, tall, shoulder-length auburn hair, green eyes, dark green bikini, sandy beach, ocean, sunny day, daylight, smile, standing, cowboy shot, looking at viewer
```

| Einstellung | Wert |
|---|---|
| seed | 66 |
| Dauer (Ausführung) | 37 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 23,8 GiB / 18,7 GiB |
| RAM (ComfyUI-Prozess) | 12,3 GiB |

Entschärftes Beispiel: generierte, eindeutig erwachsene Person, Bademode statt Nacktheit; der Workflow selbst ist für die NSFW-Kategorie gedacht.

Ausgabe · Final: [![Final](thumbs/beach__n141.webp)](beach__n141.webp) · [Volle Auflösung (3328×4864, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](beach__n141.webp)  
Ausgabe · Final: [![Final](thumbs/beach__n142.webp)](beach__n142.webp)  
Ausgabe · Pass 1: [![Pass 1](thumbs/beach__n140.webp)](beach__n140.webp)  
Ausgabe · Pass 1: [![Pass 1](thumbs/beach__n143.webp)](beach__n143.webp)
