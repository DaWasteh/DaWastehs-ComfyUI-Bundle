# TRELLIS.2 (INT8) · Bild → Form + Kollision

**Workflow-Datei:** [`workflows/Game Development/TRELLIS2_INT8-Image-to-Mesh+Collision.json`](../../../workflows/Game%20Development/TRELLIS2_INT8-Image-to-Mesh%2BCollision.json)  
**Kategorie:** Game Development · **Eingabe → Ausgabe:** Bild → 3D-Modell · **Quant:** INT8

Bis v1.3.0 hieß der Workflow `TRELLIS2_INT8-Shape-Collision.json`.

Nur die Form plus Kollisions-Mesh.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/trellis2-int8-image-to-mesh-collision>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Vision-Encoder | `dino_v3_vit_l.safetensors` | FP32 | 1,1 GiB |
| VAE | `trellis_2_shape_vae_bf16.safetensors` | BF16 | 1,0 GiB |
| Freisteller | `birefnet.safetensors` | FP16 | 0,4 GiB |
| Diffusionsmodell | `trellis_2_int8_convrot.safetensors` | INT8 | 4,9 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Objekt → Form + Kollision

| Einstellung | Wert |
|---|---|
| cfg | 7.5 |
| sampler_name | euler |
| denoise | 1 |
| shift | 5 |
| Dauer (Ausführung) | 6 min 0 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 26,0 GiB / 16,9 GiB |
| RAM (ComfyUI-Prozess) | 7,2 GiB |

Eingabe · ex_asset_chest.png: ![ex_asset_chest.png](thumbs/input_ex_asset_chest.webp) ([Datei](input_ex_asset_chest.webp))  
Ausgabe · SICHTMESH · untexturiertes GLB: [chest__n322.glb](chest__n322.glb)  
Ausgabe · COLLISION-MESH · separat vom Sichtmesh: [chest__n331.glb](chest__n331.glb)  

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
  "fallback_reason": "Hull has 170 vertices; conservative box fallback for budget 128",
  "source_vertices": 5541,
  "vertices": 8,
  "triangles": 12,
  "volume": 0.8633148419034662,
  "margin_mesh_units": 0.002,
  "contains_source": true,
  "limitation": "One solid convex collider; fills holes, doors and concavities. No rig, joints or decomposition.",
  "godot_scene": "GameDev/TRELLIS2/Shape-Collision/asset_collision_jhk_85_5.tscn",
  "body_type": "StaticBody3D",
  "mass_kg": null,
  "axes_units": "Input coordinates preserved; align with the exported visual mesh and set scale before production."
}
```
