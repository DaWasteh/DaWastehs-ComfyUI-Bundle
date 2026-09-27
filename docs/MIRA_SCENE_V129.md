# Mira-Scene · aus einem Foto eine bearbeitbare 3D-Szene · v1.2.9

[Mira-Scene](https://github.com/VAST-AI-Research/Mira-Scene) (VAST-AI-Research, [Paper](https://arxiv.org/abs/2609.23796))
rekonstruiert aus **einem Foto** eine Szene, in der jedes Objekt ein eigenes 3D-Modell ist, an seiner Stelle, in
seiner Größe (Meter) und auf seiner Unterlage. Mira ist nicht in ComfyUI enthalten und läuft upstream als
Linux/CUDA-Kette aus fünf Umgebungen. v1.2.9 portiert die Kette auf ComfyUI: Miras eigenes CCM-Modell über den
gepinnten Mira-Code, alles andere über ComfyUIs native Modelle.

| Workflow (`Image to 3D-Mesh`) | Ergebnis unter `output/` |
|---|---|
| `Mira_Scene-Layout-Preview` | `Mira_Scene/layout_*.glb`: Miras Voxelformen platziert, Boden, Fotokamera (ca. 2 min) |
| `Mira_Scene-Image-to-3D-Scene` | `Mira_Scene/scene_*.glb`: texturierte TRELLIS.2-Modelle platziert, Boden, Fotokamera; `Mira_Scene/objects/object_*.glb` einzeln |

**Lizenz:** Das Mira-Scene-Repository hat noch **keine Lizenzdatei** (Upstream-Issue #4). Das Bundle kopiert keinen
Mira-Code und keine Gewichte; der Updater holt den Code auf einen festen Commit, die Gewichte lädt man selbst. Nur privat
nutzen, bis upstream eine Lizenz steht.

## So arbeitet die Kette

| Mira-Stufe (upstream) | in ComfyUI |
|---|---|
| Szene auf 518 px (mittiges Quadrat) | `DaWMiraPrepareImage`; zusätzlich dasselbe Quadrat bis 2048 px für scharfe Objekt-Ausschnitte |
| Segmentierung: VLM nennt Objekte, SAM3 maskiert | **SAM 3.1** nativ mit einer **Objektliste als Text** + eigener Abfrage `floor`; `DaWMiraMasks` macht daraus überlappungsfreie Instanzen |
| Tiefe: MoGe / Depth Anything 3 | **MoGe-2** nativ (metrische Punkte, Brennweite) |
| **Mira-CCM**: kanonische Koordinaten je Pixel + 64³-Voxel je Objekt | `DaWMiraLoadCCM` + `DaWMiraCCM` mit Miras Pipeline-Code (30 Schritte, Guidance 3, Seed 42 wie Miras Inferenz) |
| Meshes: TRELLIS.2-Backend auf Miras Voxeln | native **TRELLIS.2**-Knoten, je Objekt nacheinander (`DaWMiraTrellisObjects`) |
| Szene: Transformation je Objekt, Bodenebene, Schwerkraft, Auflage | `DaWMiraAssembleScene` mit Miras `solve_similarity_transforms(_gravity)`, `fit_floor_plane` und `GeometryPlacementBackend` |
| Gemini-Nachzeichnung verdeckter Objekte, Umgebungskarte per API | nicht enthalten (Cloud); verdeckte Teile ergänzt TRELLIS.2 aus Voxelform und Ausschnitt |

Die kanonischen Koordinaten sagen für jedes Pixel eines Objekts, **welcher Punkt des Objekts** dort zu sehen ist.
Zusammen mit MoGes Kamerapunkten folgt daraus je Objekt Größe, Drehung und Position (RANSAC). Die Bodenebene (RANSAC
auf den Bodenpixeln) gibt die Schwerkraft vor: Objekte mit höchstens 30° Neigung werden senkrecht gestellt (Miras
harte Schwerkraft-Bedingung), danach auf den Boden oder das Objekt darunter gesetzt. Miras VLM-Szenengraph
(„steht auf“) wird dabei aus der Geometrie abgeleitet: Unterkante höchstens 10 cm (bzw. 15 % der Objekthöhe) über dem
Boden = Boden; sonst das Objekt darunter, wenn es mindestens 30 % der Grundfläche trägt und höchstens 10 cm (25 % der
Höhe) Luft ist. Hängende Objekte (Fernseher, Bilder) behalten ihre Lage.

Das Ergebnis ist eine GLB im Bodensystem: **Y oben, Boden bei y = 0, Meter**, mit texturiertem Boden (aus den
Bodenpixeln des Fotos) und der **Fotokamera** (`photo_camera`, gleiche Brennweite): In Blender o. ä. durch diese Kamera
gesehen liegen die Objekte über dem Foto.

## Bedienung

1. **FOTO** laden. Mira nutzt das **mittige Quadrat**; Innenräume und Außenszenen mit sichtbarem Boden.
2. **OBJEKTE**: englische Begriffe, kommagetrennt. `plant:3` erlaubt bis zu drei Treffer (ohne Zahl: der sicherste).
   Nur gelistete Objekte werden rekonstruiert, höchstens 12 (`max_objects`).
3. Zuerst **Layout-Vorschau** laufen lassen: KONTROLLE zeigt die gefundenen Masken (Farben, Boden schraffiert), der
   BERICHT Größe, Neigung und Auflage je Objekt. Fehlt etwas: Begriff ändern (`couch` statt `sofa`) oder `threshold`
   am Objekt-Knoten senken.
4. Passt das Layout, dieselbe Objektliste im **Szenen-Workflow** verwenden.

Wird kein Boden gefunden (oder der Boden-Knoten umgangen), gilt die Hochachse der Kamera, und der Boden liegt unter dem
tiefsten Objektpunkt. Findet SAM3 kein einziges Objekt, bricht der Masken-Knoten mit einer klaren Meldung ab.

## Installation

Der Bundle-Updater erledigt alles außer den Modellen: Paket `ComfyUI-DaWasteh-MiraScene` (mit `diffusers`,
`trimesh`, `scikit-image`) und den Mira-Code als git-Checkout auf Commit `18f42656f3b6` unter
`<ComfyUI-Wurzel>\third_party\Mira-Scene` (ohne Updater: `git clone https://github.com/VAST-AI-Research/Mira-Scene`,
dann `git checkout 18f42656f3b6f96ef61d9b291c93d1036bdaa016`; anderer Ort über `DAWASTEH_MIRA_SCENE_ROOT`).
Die Knoten importieren daraus nur Miras CCM-Pipeline, `crop_around_mask`, den Transformations-Solver, die
Platzierung und die Bodenschätzung. `spconv` und `open3d` importiert Mira, ruft sie auf diesem Weg aber nicht auf; das
Paket setzt dafür Platzhalter.

## Modelle (gepinnt in `tools/workflow_templates/v129/mira-models.json`)

| Datei | Größe | Zielordner |
|---|---:|---|
| Mira-Scene CCM-Pipeline (`Yang-Tian/Mira-Scene`, Ordner `pipeline/`, 9 Dateien) | 5,97 GiB | `models/diffusers/Mira-Scene/pipeline/` |
| `sam3.1_multiplex_fp16.safetensors` (Comfy-Org/sam3.1) | 1,63 GiB | `models/checkpoints/SAM3/` |
| `moge_2_vitl_normal_fp16.safetensors` (Comfy-Org/MoGe) | 0,62 GiB | `models/geometry_estimation/` |
| `trellis_2_int8_convrot.safetensors` (nur Szene) | 4,89 GiB | `models/diffusion_models/` |
| `dino_v3_vit_l.safetensors` (nur Szene) | 1,13 GiB | `models/clip_vision/` |
| `trellis_2_shape_vae_bf16.safetensors`, `trellis_2_texture_vae_bf16.safetensors` (nur Szene) | 1,02 + 0,88 GiB | `models/vae/` |

TRELLIS.2, DINOv3 und die VAEs nutzen schon die TRELLIS2-/Pixal3D-Workflows des Bundles.

## Messwerte (R9700)

| Entscheidung | Grund (gemessen) |
|---|---|
| **TRELLIS.2 je Objekt nacheinander** (`DaWMiraTrellisObjects`) | Die nativen Knoten als Batch polstern alle Objekte auf das größte auf: Wohnzimmer mit 10 Objekten 2115 s (92 s pro 1024er-Detailschritt), Commit-Spitze 91 GB, VRAM 29,5 GB. Nacheinander mit derselben Knotenkette: **1053 s**, 66 GB, 21 GB. |
| TRELLIS.2 auf **Miras Voxeln** statt eigener erster Stufe | Miras 64³-Voxel beschreiben das ganze Objekt einschließlich verdeckter Teile; sie werden auf TRELLIS' 32³-Struktur halbiert. Die Form passt so zur Platzierung (gleiche kanonische Box). |
| Auflage aus der Geometrie, Toleranz **10 cm** | Miras VLM-Szenengraph fehlt lokal. Mit 8 cm Toleranz blieb im Büro ein Blumentopf 9,5 cm über dem Schrank stehen, auf dem er im Foto steht (MoGe-Tiefe bei 2–3 m Abstand); mit 10 cm steht er auf 0,751 m bei 0,752 m Schrankhöhe. |
| Schwerkraft-Solver außerhalb des Inferenzmodus | Miras Gravitations-Fit optimiert die Drehung mit Adam; ComfyUI führt Knoten unter `torch.inference_mode` aus, dort scheiterte er („does not require grad“). |

| Workflow / Szene | Zeit | Commit-Spitze | VRAM R9700 |
|---|---:|---:|---:|
| Layout, Wohnzimmer, 10 Objekte (kalt: erster Lauf nach dem Start, Modelle laden) | 197 s | 57,1 GB | 16,6 GB |
| Layout, Büro, 6 Objekte | 112 s | 56,6 GB | 12,8 GB |
| Szene, Wohnzimmer, 10 Objekte (TRELLIS.2 1024, Textur 1024², ≤ 60 000 Flächen je Objekt) | 1030 s | 67,2 GB | 21,7 GB |
| Szene, Hotellobby, 7 Objekte | 735 s | 67,4 GB | 24,2 GB |

TRELLIS.2 braucht je Objekt etwa 90 s (Form, Detail, Textur, Remesh, UV, Backen). Die Bodenebene passte in allen
drei Räumen auf wenige Millimeter (mittlere Abweichung der Bodenpixel: Büro 1,2 mm, Lobby 1,8 mm, Wohnzimmer 4 mm).
Mit umgangenem Boden-Knoten (Kamera-Hochachse statt Bodenebene) blieben im Büro fünf von sechs Objekten innerhalb von
2 cm und 1° der Werte mit Boden, der Schreibtisch wurde 10 cm kleiner geschätzt; die Kamera stand dort fast
waagerecht. Bei schräg nach unten gerichteter Kamera ist der Boden-Knoten wichtiger.

## Nachweis

Beide Workflows über das echte Frontend (headless Edge, `app.graphToPrompt`) auf der R9700 ausgeführt; Einzelwerte
in `performance/rdna4/mira-scene-v129-validation.json`, gesichert durch `tests/test_mira_scene_workflows_v129.py` und
`tests/test_mira_scene_nodes_v129.py` (u. a. Rückprojektion der Objekt-Ausschnitte gegen Miras eigenes
`crop_around_mask`, Umkehr der TRELLIS-Drehung, Auflage-Regeln).

| Fall | Ergebnis |
|---|---|
| Layout, Wohnzimmer (Standard) | 10/10 Objekte in der GLB, Boden, Fotokamera; Fernseher hängt (0,89 m), Pflanzen auf der Fensterbank (≈ 0,46 m), Sofa, Tisch und Lampen auf dem Boden |
| Layout, Büro | 6/6 Objekte; Schreibtisch, Stuhl, Regal, Schrank, Stehlampe auf dem Boden, Blumentopf auf dem Schrank |
| Layout, Büro, Boden-Knoten umgangen | 6/6 Objekte, Boden unter dem tiefsten Objektpunkt |
| Layout, Objektliste `giraffe, spaceship` | Abbruch nach 2 s mit der Meldung „Keine Objekte gefunden …“ (erwartet) |
| Szene, Wohnzimmer (Standard) | 10/10 texturierte Modelle platziert + 10 Einzel-GLBs, 35 MiB |
| Szene, Hotellobby | 7/7 (Sofa, zwei Sessel, Tisch, Hocker, Pflanze auf dem Boden; Tischlampe auf der nicht gelisteten Anrichte in 1,0 m) |

Modelle: alle 15 Dateien (9 Pipeline-Dateien, SAM 3.1, MoGe-2, TRELLIS.2, DINOv3, zwei VAEs) per SHA-256 gegen das
Manifest geprüft. Testbilder: `modern_living_room.png` aus Comfy-Orgs Workflow-Vorlagen (gepinnt in
`mira-inputs.json`); Büro und Lobby sind lokale Testbilder und nicht Teil des Bundles.

## Grenzen

- Nur Objekte aus der Liste; was SAM3 nicht findet, fehlt in der Szene. Sehr kleine Objekte (unter 0,2 % des Bildes)
  werden verworfen.
- Verdeckte Rückseiten erfindet TRELLIS.2 aus Voxelform und sichtbarem Ausschnitt; Miras Gemini-Nachzeichnung fehlt.
- Die Auflage wird aus der Geometrie geschätzt, nicht von einem VLM: Objekte auf nicht gelisteten Möbeln (z. B.
  Fensterbank) bleiben in gemessener Höhe stehen, ohne Unterlage.
- Wände, Decke und nicht gelistete Möbel sind nicht Teil der Szene; der Boden ist eine texturierte Fläche.
- Mira-Scene ohne Lizenz upstream: nur privat nutzen.
