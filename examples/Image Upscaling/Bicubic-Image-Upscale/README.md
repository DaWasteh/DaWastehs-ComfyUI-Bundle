# Bikubisch · Bild hochskalieren

**Workflow-Datei:** [`workflows/Image Upscaling/Bicubic-Image-Upscale.json`](../../../workflows/Image%20Upscaling/Bicubic-Image-Upscale.json)  
**Kategorie:** Image Upscaling · **Eingabe → Ausgabe:** Bild → Bild

Bis v1.3.0 hieß der Workflow `Image-Simple-Bicubic-Upscale.json`.

Reine Interpolation (4×) als Vergleichsbasis – keine neuen Details.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/bicubic-image-upscale>

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### 256 px → 1024 px

| Einstellung | Wert |
|---|---|
| Dauer (Ausführung) | 0 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 5,1 GiB / 0,1 GiB |
| RAM (ComfyUI-Prozess) | 0,8 GiB |

Eingabe · ex_portrait_woman_256.png: ![ex_portrait_woman_256.png](thumbs/input_ex_portrait_woman_256.webp) ([Datei](input_ex_portrait_woman_256.webp))  
Ausgabe · Ausgabe: [![Ausgabe](thumbs/portrait.webp)](portrait.webp) · [Volle Auflösung (1024×1024, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](portrait.webp)
