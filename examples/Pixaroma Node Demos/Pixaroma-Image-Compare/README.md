# Pixaroma · Bildvergleich

**Workflow-Datei:** [`workflows/Pixaroma Node Demos/Pixaroma-Image-Compare.json`](../../../workflows/Pixaroma%20Node%20Demos/Pixaroma-Image-Compare.json)  
**Kategorie:** Pixaroma Node Demos · **Eingabe → Ausgabe:** Bild → Vergleich

Zwei Bilder mit Regler vergleichen.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/pixaroma-image-compare>

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Zwei Bilder vergleichen

| Einstellung | Wert |
|---|---|
| Dauer (Ausführung) | 0 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 4,7 GiB / 0,1 GiB |
| RAM (ComfyUI-Prozess) | 0,9 GiB |

Eingabe · ex_landscape_lake.png: ![ex_landscape_lake.png](thumbs/input_ex_landscape_lake.webp) ([Datei](input_ex_landscape_lake.webp))  
Eingabe · ex_landscape_lake_winter.png: ![ex_landscape_lake_winter.png](thumbs/input_ex_landscape_lake_winter.webp) ([Datei](input_ex_landscape_lake_winter.webp))  
Ausgabe · Bild 1: [![Bild 1](thumbs/winter__n1-1.webp)](winter__n1-1.webp) · [Volle Auflösung (1344×768, WebP)](winter__n1-1.webp)  
Ausgabe · Bild 2: [![Bild 2](thumbs/winter__n1-2.webp)](winter__n1-2.webp)
