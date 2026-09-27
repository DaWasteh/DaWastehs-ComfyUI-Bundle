# DaWasteh MiraScene

ComfyUI-Nodes (`comfy_api.latest`) für die v1.2.9-Workflows mit **Mira-Scene** (VAST-AI-Research): aus einem Foto
eine bearbeitbare 3D-Szene, jedes Objekt ein eigenes Modell an seiner Stelle im Raum. Die Stufen folgen Miras
`infer_scripts`; wo Mira fremde Projekte aufruft, nutzen die Workflows ComfyUIs native Modelle.

| Mira-Stufe | hier |
|---|---|
| Segmentierung (SAM3 + VLM-Objektliste) | natives **SAM 3.1** mit Text-Objektliste + `floor`, dann **DaWMiraMasks** |
| Tiefe (MoGe / Depth Anything 3) | natives **MoGe-2** |
| CCM + 64³-Voxel (Mira-CCM) | **DaWMiraLoadCCM** + **DaWMiraCCM** mit Miras Code (gepinnter Checkout) |
| Meshes (TRELLIS.2-Backend auf Miras Voxeln) | **DaWMiraTrellisObjects** (native TRELLIS.2-Knoten, je Objekt) |
| Szene (`construct_scene`, Bodenebene, Auflage) | **DaWMiraAssembleScene** mit Miras Solver und Platzierung |
| Gemini-Nachzeichnung, API-Umgebungskarte | nicht enthalten (Cloud) |

- **DaWMiraPrepareImage**: mittiges Quadrat des Fotos in 518 px (Miras Arbeitsgröße) für SAM3, MoGe und CCM, dazu
  dasselbe Quadrat bis `max_hires` für scharfe TRELLIS-Ausschnitte.
- **DaWMiraMasks**: SAM3-Treffer → überlappungsfreie Instanzmasken (Dubletten ab IoU 0,7 weg, Überlappung an das
  kleinere Objekt, Mini-Masken unter `min_area` weg, höchstens `max_objects`); der Boden behält nur Pixel ohne Objekt.
  Vorschau mit Farben je Objekt und schraffiertem Boden. Bricht mit einer klaren Meldung ab, wenn kein Objekt übrig ist.
- **DaWMiraLoadCCM**: lädt Miras CCM-Pipeline (`models/diffusers/Mira-Scene/pipeline`, diffusers-Ordner) in BF16.
- **DaWMiraCCM**: Miras CCM-Stufe für alle Objekte: pixelgenaue kanonische Koordinaten (welcher Punkt des Objekts in
  welchem Pixel zu sehen ist) und die vollständige 64³-Voxelform, auch verdeckter Teile. 30 Schritte, Guidance 3,
  Seed 42 wie Miras Inferenz. Ausgänge: Szenendaten, Voxel für TRELLIS.2 (32³), quadratische Objekt-Ausschnitte,
  Koordinaten-Vorschau.
- **DaWMiraTrellisObjects**: die native TRELLIS.2-Kette (Konditionierung, 512er-Form auf Miras Voxeln, 1024er-Detail,
  PBR-Textur, Remesh, Dezimieren, UV, Backen) **je Objekt nacheinander**. Ein Batch polstert alle Objekte auf das
  größte auf und wird dadurch überproportional langsam.
- **DaWMiraAssembleScene**: Ähnlichkeitstransformation je Objekt aus kanonischen Koordinaten und MoGe-Kamerapunkten
  (RANSAC, Miras `solve_similarity_transforms`), Bodenebene aus der Bodenmaske als Schwerkraft, aufrechte Objekte
  (bis 30° Neigung) mit Miras Schwerkraft-Solver senkrecht, dann auf Boden oder das darunterliegende Objekt gesetzt
  (Miras `GeometryPlacementBackend`, `rests_on`). Ausgabe: eine GLB im Bodensystem (Y oben, Boden bei 0, Meter) mit
  texturiertem Boden und der Fotokamera, dazu ein Bericht je Objekt. Ohne Meshes zeigt sie Miras Voxelformen.

**Mira-Scene-Code:** Die Knoten importieren Miras Module aus einem Checkout, den der Bundle-Updater auf Commit
`18f42656f3b6` unter `<ComfyUI-Wurzel>\third_party\Mira-Scene` anlegt (anderer Ort: Umgebungsvariable
`DAWASTEH_MIRA_SCENE_ROOT`). Das Repository hat noch **keine Lizenzdatei** (Upstream-Issue #4): nur privat nutzen. In
diesem Paket ist kein Mira-Code kopiert; `prepare_inference_input` und die Rückprojektion der Ausschnitte sind
nachgebaut, weil Miras Datenklassen `jaxtyping` bräuchten. Für `spconv.pytorch` und `open3d`, die Mira nur importiert,
aber auf dem genutzten Pfad nicht aufruft, setzt `mira_runtime.py` Platzhalter.
Abhängigkeiten: `requirements.txt` (`diffusers`, `trimesh`, `scikit-image`; der Bundle-Updater installiert sie ohne
Upgrade), sonst nur ComfyUI (PyTorch, transformers, einops, NumPy, Pillow).
Workflows und Messwerte: [docs/MIRA_SCENE_V129.md](../../docs/MIRA_SCENE_V129.md).
