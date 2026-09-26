# Pose & Depth · Pose und Tiefenkarten aus Bildern und Videos · v1.2.8

Neuer Ordner `workflows/Pose & Depth/` mit vier Workflows. Alle laufen mit Core-Nodes von ComfyUI (SDPose, RT-DETR,
Depth Anything 3), dazu VideoHelperSuite und das neue Paket `ComfyUI-DaWasteh-VisionTools` (Bundle-Updater).
Die Ergebnisse haben **Originalgröße** und sind deckungsgleich mit der Quelle; Videos behalten **Original-fps und Ton**.

| Workflow | Ergebnis unter `output/` |
|---|---|
| `SDPose-Pose-from-Image` | `Pose/Pose_*.png` (Skelett auf Schwarz, OpenPose-Farben) + `Pose/Pose_Keypoints_*.json` (OpenPose-JSON) |
| `SDPose-Pose-from-Video` | `Pose/Pose_Video_*.mp4` |
| `DepthAnything3-Depth-from-Image` | `Depth/Depth_*.png` (8 Bit, hell = nah) + `Depth/Depth16_*_.png` (16 Bit, voller Bereich) |
| `DepthAnything3-Depth-from-Video` | `Depth/Depth_Video_*.mp4` (hell = nah) |

## Modelle (gepinnt in `tools/workflow_templates/v128/models.json`)

| Datei | Größe | Zielordner |
|---|---:|---|
| `sdpose_wholebody_fp16.safetensors` (Comfy-Org/SDPose, MIT) | 1,79 GiB | `models/checkpoints/SDPose/` |
| `rt_detr_v4-x-hgnet_fp16.safetensors` (Personendetektor) | 0,12 GiB | `models/diffusion_models/SDPose/` |
| `depth_anything_3_mono_large.safetensors` (Comfy-Org/Depth-Anything-3) | 1,24 GiB | `models/geometry_estimation/DepthAnything3/` |

Für die R9700 (32 GB) sind die großen Varianten gewählt; gemessen belegt die ganze R9700 beim Rechnen höchstens 5,1 GiB
(Pose) bzw. 2,0 GiB (Tiefe). Die kleineren DA3-Varianten (Small/Base) lohnen sich hier nicht.

## Pose (SDPose Wholebody)

RT-DETR findet die Person, **DaW Pose Boxes** erweitert den Rahmen unverzerrt auf 3:4 plus 25 % Rand, SDPose schätzt im
Ausschnitt 133 Punkte (18 Körper, 6 Füße, 68 Gesicht, 2 × 21 Hände), SDPose Draw zeichnet sie im OpenPose-Schema.
`max_detections` = 1 nimmt die sicherste Person; für Gruppen erhöhen. Findet der Detektor niemanden, rechnet SDPose auf
dem ganzen Bild. `score_threshold` 0,5 blendet unsichere Punkte aus.

**Warum die 3:4-Rahmen:** Der Core-Extractor streckt jeden Personenrahmen ohne Seitenverhältnis auf 768×1024; eine
stehende Person (Rahmen etwa 1:3) wird dabei gut doppelt so breit gequetscht. Mit 3:4-Rahmen (wie MMPose' Top-down-Crop):

| Video | Variante | sichere Körperpunkte je Frame (von 18) | Beinpunkte (von 6) | Zittern p90 (% Körperhöhe) |
|---|---|---:|---:|---:|
| Tanzvideo, dunkle Silhouette, 480×854, 392 Frames | Core-Rahmen | 7,7 | 1,2 | 19,9 |
| | **3:4-Rahmen** | **15,6** | **5,1** | **7,2** |
| `man_in_the_rain.mp4` (Kamerafahrt, 121 Frames) | Core-Rahmen | 9,5 | 0,0 | 0,57 |
| | **3:4-Rahmen** | **10,2** | 0,5 | **0,54** |

Bei Bildern gleich oder besser (Tänzerin 18/18 Körper-, 42 Hand-, 70 Gesichtspunkte in beiden Varianten).
„Zittern“ = zweite Differenz der Punkte von Frame zu Frame; bei schnellem Tanz enthält sie auch echte Beschleunigung.

## Tiefe (Depth Anything 3 Mono Large)

Bild: 1008 px an der langen Kante (Vielfache von 14), Video: 504 px an der kurzen Kante; das Ergebnis wird auf die
Quellgröße skaliert. Normalisierung wie Comfy-Orgs Vorlage (`v2_style`: 1–99-%-Quantile je Bild, Himmel schwarz).
Das 16-Bit-PNG nutzt `min_max` mit auf den Hintergrund begrenztem Himmel (**DaW Save 16-bit Depth PNG**, 49.594
verschiedene Stufen im Testbild statt 256). Die Tiefe ist **relativ**, nicht in Metern.

Auflösung im Bild (2048², `retro_futuristic_home.png`): 504 px weicher an Kanten, 1008 px scharfe Spiegel und Grill,
1512 px kaum besser. Alle unter 2,1 s.

**Video-Flackern, gemessen statt vermutet:** mittlere Tiefenänderung zwischen zwei Frames auf Pixeln, deren Farbe
sich kaum ändert (kleiner = ruhiger):

| Variante | Raum-Schwenk mit auftauchenden Möbeln | Kamerafahrt auf einen Mann |
|---|---:|---:|
| Mono Large je Frame (ausgeliefert, wie Comfy-Org) | 0,0128 | 0,0064 |
| Mono, ein Quantil-Bereich für den ganzen Clip | 0,0121 | 0,0053 |
| Mono, jedes Frame per Skalierung/Offset aufs vorige ausgerichtet | 0,0059, aber Ausreißer 0,41 | 0,0038 |
| DA3 Base Multi-View (32 Frames je Fenster), Clip-Bereich | **0,0029** | 0,0076, Sprünge an Fenstergrenzen |

Keine Alternative ist in beiden Szenen besser und zugleich robust; Multi-View braucht außerdem `ray_pose`, weil
`cam_dec` im Core mit fp16-Gewichten abbricht (`mat1 and mat2 must have the same dtype`). Ausgeliefert ist daher der
robuste Einzelbild-Weg; DA3 Base ist nicht Teil des Pakets.

## Videos: Meta-Batches und der sichere Loader

Die Video-Workflows laufen in **VHS-Meta-Batches** zu 64 Frames: Der Prompt stellt sich nach jedem Batch selbst neu in
die Warteschlange, bis das Video fertig ist, und VHS Video Combine schreibt ein einziges MP4 mit dem Originalton. Der
RAM hängt damit nicht von der Videolänge ab. Ein flacher Graph hielte alle Frames als float32 (60 s 1080p ≈ 36 GB,
auf diesem Windows/ROCm-System ein Einfrieren statt eines OOM-Fehlers).

**DaW Load Video (Meta-Batch, safe)** ersetzt VHS Load Video, weil zwei Fehler im Test auftraten:

1. **Stumme Videos:** VHS gibt immer eine *LazyAudioMap* zurück. ComfyUI 0.37 durchläuft jeden verbundenen Ausgang
   (`PromptModelTracker.add` in `cache_update`), dabei startet die Map ffmpeg, findet keine Tonspur und der Lauf bricht
   mit „VHS failed to extract audio“ ab. Der DaW-Loader gibt bei stummen Videos kein Audio aus; das MP4 hat dann
   keinen Ton.
2. **Lauf nach Abbruch:** Scheitert oder wird ein Lauf im **ersten** Batch abgebrochen, bleibt der Batch-Manager im
   Cache (gleiche Eingaben) und hält den alten Video-Generator offen. Der nächste Lauf lieferte als erste Datei die
   restlichen 57 Frames des **vorigen** Videos. Der DaW-Loader erkennt einen neuen Lauf (`requeue` = 0) mit offenem
   Zustand und setzt ihn zurück (Log: `closed a meta batch left open by a cancelled or failed run`).

`skip_first_frames` und `frame_load_cap` am Loader verarbeiten nur einen Teil.

## Nachweis

[`vision-workflows-v128-validation.json`](../performance/rdna4/vision-workflows-v128-validation.json), abgesichert
durch `tests/test_vision_workflows_v128.py` und `tests/test_vision_tools_nodes_v128.py`. Serialisiert über das echte
Frontend, ausgeführt auf der R9700 (ComfyUI 0.37.0, Frontend 1.53.6, Profil v0.9.8 mit VRAM-Guard).

| Fall | Batches | Zeit | Ausgabe = Quelle (Frames, Größe, fps, Ton) |
|---|---:|---:|---|
| Pose, `dancer.png` 1024² | – | 6,1 s kalt / 1,3 s | – |
| Pose, Gruppenfoto 2048², 1 bzw. 5 Personen | – | 2,0 / 3,1 s | – |
| Pose-Video `man_in_the_rain.mp4` 1280×720, 121 Frames | 2 | 44,7 s | ja (AAC) |
| dasselbe ohne Tonspur | 2 | 43,7 s | ja (ohne Ton) |
| Pose-Video Tanz 480×854, 30 fps, 392 Frames | 7 | 130 s | ja (AAC) |
| Pose-Video nach Abbruch eines anderen Laufs im ersten Batch | 2 | 44,6 s | ja, nur das neue Video |
| Pose-Video 60 s 1920×1080, 1429 Frames | 23 | 631 s | ja (AAC) |
| Tiefe, 2048²-Bild (504 / 1008 / 1512 px) | – | 1,0 / 2,1 / 2,0 s | – |
| Tiefen-Video Raum 1280×720, 120 Frames | 2 | 24,4 s | ja (AAC) |
| Tiefen-Video Tanz 392 Frames / ohne Tonspur | 7 / 2 | 56,7 / 24,5 s | ja |
| Tiefen-Video 60 s 1920×1080, 1429 Frames, 23,82 fps | 23 | 445 s | ja (AAC) |

RAM bei den 60-s-1080p-Videos: Commit über die ganze Laufzeit konstant 54–56 GB (Start 40,6 GB, Grenze 97 GB); das Zittern der Pose bleibt bei 0,18 % der Körperhöhe (Median).
VRAM-Spitze Pose 5,1 GiB, Tiefe 2,0 GiB.

## Grenzen

- Pose: Jedes Frame wird einzeln geschätzt; bei Drehungen und Verdeckung fehlen einzelne Glieder für ein paar Frames.
  Mehrere Personen im Video: Bei `max_detections` = 1 kann die „sicherste“ Person wechseln.
- Tiefe: relativ und je Frame normalisiert; wenn große Objekte ins Bild kommen, verschiebt sich die Helligkeit des
  Hintergrunds. Dünne Objekte vor dem Himmel zählt DA3 teils zum Himmel (schwarz).
- Abbrechen eines Videolaufs hinterlässt kein fertiges MP4; der nächste Lauf beginnt sauber.
