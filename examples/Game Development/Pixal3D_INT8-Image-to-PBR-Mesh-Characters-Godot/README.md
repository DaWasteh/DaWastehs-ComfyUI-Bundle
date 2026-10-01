# Pixal3D (INT8) · Figur/Tier → PBR-Mesh für Godot

**Workflow-Datei:** [`workflows/Game Development/Pixal3D_INT8-Image-to-PBR-Mesh-Characters-Godot.json`](../../../workflows/Game%20Development/Pixal3D_INT8-Image-to-PBR-Mesh-Characters-Godot.json)  
**Kategorie:** Game Development · **Eingabe → Ausgabe:** Bild → 3D-Modell · **Quant:** INT8

Bis v1.3.0 hieß der Workflow `Pixal3D_INT8-Humanoids-and-Animals-PBR-for-Godot.json`.

Wie die Gebäude-Variante, mit 2048-px-Texturen und 24.000 Dreiecken für Figuren.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/pixal3d-int8-image-to-pbr-mesh-characters-godot>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| VAE | `trellis_2_texture_vae_bf16.safetensors` | BF16 | 0,9 GiB |
| Vision-Encoder | `dino_v3_L_naf_fp32.safetensors` | FP32 | 1,1 GiB |
| VAE | `trellis_2_shape_vae_bf16.safetensors` | BF16 | 1,0 GiB |
| Tiefenschätzung | `moge_2_vitl_normal_fp16.safetensors` | FP16 | 0,6 GiB |
| Freisteller | `birefnet.safetensors` | FP16 | 0,4 GiB |
| Diffusionsmodell | `pixal3d_int8_convrot.safetensors` | INT8 | 5,2 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Figur → PBR-Mesh

| Einstellung | Wert |
|---|---|
| sampler_name | euler |
| denoise | 1 |
| shift | 5 |
| Dauer (Ausführung) | 4 min 18 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 14,1 GiB / 11,1 GiB |
| RAM (ComfyUI-Prozess) | 13,8 GiB |

Eingabe · ex_character_fox.png: ![ex_character_fox.png](thumbs/input_ex_character_fox.webp) ([Datei](input_ex_character_fox.webp))  
Ausgabe · GODOT · PBR-GLB speichern: [fox.glb](fox.glb)  

GetMeshInfo:

```text
Vertices:   2,597,543 (2.60M)
Faces:      5,658,418 (5.66M)
Attributes: none
```

FINAL GAME MESH INFO · tatsächliche Dreiecke prüfen:

```text
Vertices:   12,075 (12.1K)
Faces:      23,920 (23.9K)
Attributes: none
```
