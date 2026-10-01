# Pixal3D MultiView (INT8) · vier Ansichten → PBR-Mesh + Kollision

**Workflow-Datei:** [`workflows/Game Development/Pixal3D_MultiView_INT8-4-Views-to-PBR-Mesh+Collision.json`](../../../workflows/Game%20Development/Pixal3D_MultiView_INT8-4-Views-to-PBR-Mesh%2BCollision.json)  
**Kategorie:** Game Development · **Eingabe → Ausgabe:** Bilder → 3D-Modell · **Quant:** INT8

Bis v1.3.0 hieß der Workflow `Pixal3D_INT8-MultiView-PBR-Collision.json`.

Vorne/links/hinten/rechts auf schwarzem Grund ergeben ein genaueres Mesh plus separates Kollisions-Mesh für Godot.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/pixal3d-multiview-int8-4-views-to-pbr-mesh-collision>

> Die vier Eingaben sind kalibrierte Blender-Renders (Kamera-Rig des Nodes: 90° Abstand, FOV 20°, gleiche Skala). Erfundene Mehransichten aus einem Bildmodell passen nicht zu diesem Rig.

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| VAE | `trellis_2_texture_vae_bf16.safetensors` | BF16 | 0,9 GiB |
| Vision-Encoder | `dino_v3_L_naf_fp32.safetensors` | FP32 | 1,1 GiB |
| VAE | `trellis_2_shape_vae_bf16.safetensors` | BF16 | 1,0 GiB |
| Diffusionsmodell | `pixal3d_multiview_int8_convrot.safetensors` | INT8 | 5,2 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Vier Blender-Ansichten → PBR-Mesh + Kollision

| Einstellung | Wert |
|---|---|
| Ansichten | vorne, links, hinten, rechts · 90° Abstand · FOV 20° · schwarzer Hintergrund |
| Quelle | Blender-Render eines prozeduralen Briefkastens (tools/examples/blender_multiview_views.py) |
| sampler_name | euler |
| denoise | 1 |
| shift | 5 |
| Dauer (Ausführung) | 10 min 57 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 12,1 GiB / 9,8 GiB |
| RAM (ComfyUI-Prozess) | 20,4 GiB |

Eingabe · ex_mv_mailbox_front.png: ![ex_mv_mailbox_front.png](thumbs/input_ex_mv_mailbox_front.webp) ([Datei](input_ex_mv_mailbox_front.webp))  
Eingabe · ex_mv_mailbox_left.png: ![ex_mv_mailbox_left.png](thumbs/input_ex_mv_mailbox_left.webp) ([Datei](input_ex_mv_mailbox_left.webp))  
Eingabe · ex_mv_mailbox_back.png: ![ex_mv_mailbox_back.png](thumbs/input_ex_mv_mailbox_back.webp) ([Datei](input_ex_mv_mailbox_back.webp))  
Eingabe · ex_mv_mailbox_right.png: ![ex_mv_mailbox_right.png](thumbs/input_ex_mv_mailbox_right.webp) ([Datei](input_ex_mv_mailbox_right.webp))  
Ausgabe · SICHTMESH · PBR-GLB: [mailbox__n322.glb](mailbox__n322.glb)  
Ausgabe · COLLISION-MESH · separat vom Sichtmesh: [mailbox__n334.glb](mailbox__n334.glb)  

GetMeshInfo:

```text
Vertices:   1,951,489 (1.95M)
Faces:      3,919,192 (3.92M)
Attributes: none
```

COLLISION REPORT · Pfad / Dreiecke / Fallback:

```text
{
  "requested_mode": "convex_hull",
  "actual_mode": "box",
  "fallback_reason": "Hull has 345 vertices; conservative box fallback for budget 128",
  "source_vertices": 6014,
  "vertices": 8,
  "triangles": 12,
  "volume": 0.29738914564247954,
  "margin_mesh_units": 0.002,
  "contains_source": true,
  "limitation": "One solid convex collider; fills holes, doors and concavities. No rig, joints or decomposition.",
  "godot_scene": "GameDev/Pixal3D/MultiView-PBR-Collision/asset_collision_eacbyw6z.tscn",
  "body_type": "StaticBody3D",
  "mass_kg": null,
  "axes_units": "Input coordinates preserved; align with the exported visual mesh and set scale before production."
}
```

FINAL GAME MESH INFO · tatsächliche Dreiecke prüfen:

```text
Vertices:   6,014
Faces:      12,000 (12.0K)
Attributes: none
```
