# Bilder kombinieren

**Workflow-Datei:** [`workflows/Image Utilities/Image-Combiner.json`](../../../workflows/Image%20Utilities/Image-Combiner.json)  
**Kategorie:** Image Utilities · **Eingabe → Ausgabe:** Bild → Bild

Zwei Bilder übereinanderlegen und zusammenführen.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/image-combiner>

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Bilder kombinieren

| Einstellung | Wert |
|---|---|
| Dauer (Ausführung) | 2 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 7,5 GiB / 4,8 GiB |
| RAM (ComfyUI-Prozess) | 1,4 GiB |

Eingabe · ex_kitchen_table.png: ![ex_kitchen_table.png](thumbs/input_ex_kitchen_table.webp) ([Datei](input_ex_kitchen_table.webp))  
Eingabe · ex_product_teapot.png: ![ex_product_teapot.png](thumbs/input_ex_product_teapot.webp) ([Datei](input_ex_product_teapot.webp))  
Ausgabe · Ausgabe: [![Ausgabe](thumbs/teapot.webp)](teapot.webp) · [Volle Auflösung (1024×1024, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](teapot.webp)
