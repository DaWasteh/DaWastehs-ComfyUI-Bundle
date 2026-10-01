# TRELLIS.2 (INT8) · Bild → PBR-Mesh + Kollision

**Workflow-Datei:** [`workflows/Game Development/TRELLIS2_INT8-Image-to-PBR-Mesh+Collision.json`](../../../workflows/Game%20Development/TRELLIS2_INT8-Image-to-PBR-Mesh%2BCollision.json)  
**Kategorie:** Game Development · **Eingabe → Ausgabe:** Bild → 3D-Modell · **Quant:** INT8

Bis v1.3.0 hieß der Workflow `TRELLIS2_INT8-PBR-Collision.json`.

TRELLIS.2 mit DINOv3: Mesh mit PBR-Texturen und separatem Kollisions-Mesh.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/trellis2-int8-image-to-pbr-mesh-collision>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| VAE | `trellis_2_texture_vae_bf16.safetensors` | BF16 | 0,9 GiB |
| Vision-Encoder | `dino_v3_vit_l.safetensors` | FP32 | 1,1 GiB |
| VAE | `trellis_2_shape_vae_bf16.safetensors` | BF16 | 1,0 GiB |
| Freisteller | `birefnet.safetensors` | FP16 | 0,4 GiB |
| Diffusionsmodell | `trellis_2_int8_convrot.safetensors` | INT8 | 4,9 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Objekt → PBR-Mesh + Kollision

| Einstellung | Wert |
|---|---|
| sampler_name | euler |
| denoise | 1 |
| shift | 5 |
| Dauer (Ausführung) | 9 min 36 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 26,2 GiB / 17,8 GiB |
| RAM (ComfyUI-Prozess) | 9,5 GiB |

Eingabe · ex_asset_chest.png: ![ex_asset_chest.png](thumbs/input_ex_asset_chest.webp) ([Datei](input_ex_asset_chest.webp))  
Ausgabe · SICHTMESH · PBR-GLB: [chest__n322.glb](chest__n322.glb)  
Ausgabe · COLLISION-MESH · separat vom Sichtmesh: [chest__n330.glb](chest__n330.glb)  

GetMeshInfo:

```text
Vertices:   20,966,869 (20.97M)
Faces:      42,319,174 (42.32M)
Attributes: none
```

COLLISION REPORT · Pfad / Dreiecke / Fallback:

```text
{
  "requested_mode": "convex_hull",
  "actual_mode": "box",
  "fallback_reason": "Hull has 147 vertices; conservative box fallback for budget 128",
  "source_vertices": 5530,
  "vertices": 8,
  "triangles": 12,
  "volume": 0.8557388140674989,
  "margin_mesh_units": 0.002,
  "contains_source": true,
  "limitation": "One solid convex collider; fills holes, doors and concavities. No rig, joints or decomposition.",
  "godot_scene": "GameDev/TRELLIS2/PBR-Collision/asset_collision_ds261ahz.tscn",
  "body_type": "StaticBody3D",
  "mass_kg": null,
  "axes_units": "Input coordinates preserved; align with the exported visual mesh and set scale before production."
}
```

FINAL GAME MESH INFO · tatsächliche Dreiecke prüfen:

```text
Vertices:   5,530
Faces:      11,888 (11.9K)
Attributes: none
```
