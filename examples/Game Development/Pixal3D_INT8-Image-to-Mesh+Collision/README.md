# Pixal3D (INT8) · Bild → Form + Kollision

**Workflow-Datei:** [`workflows/Game Development/Pixal3D_INT8-Image-to-Mesh+Collision.json`](../../../workflows/Game%20Development/Pixal3D_INT8-Image-to-Mesh%2BCollision.json)  
**Kategorie:** Game Development · **Eingabe → Ausgabe:** Bild → 3D-Modell · **Quant:** INT8

Bis v1.3.0 hieß der Workflow `Pixal3D_INT8-Shape-Collision.json`.

Nur die Form (ohne Textur) plus Kollisions-Mesh – schneller für Blockouts.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/pixal3d-int8-image-to-mesh-collision>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Vision-Encoder | `dino_v3_L_naf_fp32.safetensors` | FP32 | 1,1 GiB |
| VAE | `trellis_2_shape_vae_bf16.safetensors` | BF16 | 1,0 GiB |
| Tiefenschätzung | `moge_2_vitl_normal_fp16.safetensors` | FP16 | 0,6 GiB |
| Freisteller | `birefnet.safetensors` | FP16 | 0,4 GiB |
| Diffusionsmodell | `pixal3d_int8_convrot.safetensors` | INT8 | 5,2 GiB |

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
| Dauer (Ausführung) | 3 min 7 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 12,1 GiB / 10,3 GiB |
| RAM (ComfyUI-Prozess) | 11,7 GiB |

Eingabe · ex_product_teapot.png: ![ex_product_teapot.png](thumbs/input_ex_product_teapot.webp) ([Datei](input_ex_product_teapot.webp))  
Ausgabe · SICHTMESH · untexturiertes GLB: [teapot__n322.glb](teapot__n322.glb)  
Ausgabe · COLLISION-MESH · separat vom Sichtmesh: [teapot__n330.glb](teapot__n330.glb)  

GetMeshInfo:

```text
Vertices:   2,718,540 (2.72M)
Faces:      5,525,234 (5.53M)
Attributes: none
```

COLLISION REPORT · Pfad / Dreiecke / Fallback:

```text
{
  "requested_mode": "convex_hull",
  "actual_mode": "box",
  "fallback_reason": "Hull has 714 vertices; conservative box fallback for budget 128",
  "source_vertices": 5985,
  "vertices": 8,
  "triangles": 12,
  "volume": 0.5085831963005267,
  "margin_mesh_units": 0.002,
  "contains_source": true,
  "limitation": "One solid convex collider; fills holes, doors and concavities. No rig, joints or decomposition.",
  "godot_scene": "GameDev/Pixal3D/Shape-Collision/asset_collision_meho3l1q.tscn",
  "body_type": "StaticBody3D",
  "mass_kg": null,
  "axes_units": "Input coordinates preserved; align with the exported visual mesh and set scale before production."
}
```
