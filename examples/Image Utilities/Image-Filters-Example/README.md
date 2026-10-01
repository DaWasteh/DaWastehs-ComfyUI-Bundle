# Filter + Overlay

**Workflow-Datei:** [`workflows/Image Utilities/Image-Filters-Example.json`](../../../workflows/Image%20Utilities/Image-Filters-Example.json)  
**Kategorie:** Image Utilities · **Eingabe → Ausgabe:** Bild → Bild

Filterkette mit Überlagerungs-Textur.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/image-filters-example>

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Filter + Overlay-Textur

| Einstellung | Wert |
|---|---|
| Dauer (Ausführung) | 1 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 12,8 GiB / 0,1 GiB |
| RAM (ComfyUI-Prozess) | 1,4 GiB |

Eingabe · ex_portrait_woman.png: ![ex_portrait_woman.png](thumbs/input_ex_portrait_woman.webp) ([Datei](input_ex_portrait_woman.webp))  
Eingabe · ex_kitchen_table.png: ![ex_kitchen_table.png](thumbs/input_ex_kitchen_table.webp) ([Datei](input_ex_kitchen_table.webp))  
Ausgabe · Bild 1: [![Bild 1](thumbs/portrait__n5.webp)](portrait__n5.webp) · [Volle Auflösung (1024×1024, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](portrait__n5.webp)  
Ausgabe · Bild 2: [![Bild 2](thumbs/portrait__n4-1.webp)](portrait__n4-1.webp)  
Ausgabe · Bild 3: [![Bild 3](thumbs/portrait__n4-2.webp)](portrait__n4-2.webp)
