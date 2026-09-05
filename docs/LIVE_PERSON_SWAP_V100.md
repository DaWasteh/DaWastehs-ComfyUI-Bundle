# Live Face Swap und Live Person Swap · Workflow 16 und 17 · v1.0.0

Workflows:

- `workflows/Live Avatar/LiveAvatar-16-Live-Face-Swap-DirectML-Spout-OBS.json` (Gesicht)
- `workflows/Live Avatar/LiveAvatar-17-Live-Person-Swap-Matting-Voice-DirectML-Spout-OBS.json` (Gesicht + Hintergrund + Stimme)

v1.0.0 macht aus dem v0.9.9-Face-Swap eine Kette, die auf diesem Rechner als
realistisch durchgeht. Alle Entscheidungen wurden mit 150 echten BRIO-Frames
(1280×720, 25 Sekunden: Lächeln, Mund weit auf, Kopf drehen, Hände vor dem
Gesicht, aus dem Bild gehen) offline verglichen und danach live gegen OBS
gemessen. Die v0.9.9-Grundlagen (DirectML statt ROCm, native SCRFD/ArcFace-
Portierung, Protobuf-Reader) stehen weiter in
[LIVE_FACE_SWAP_V099.md](LIVE_FACE_SWAP_V099.md).

## Was v0.9.9 noch falsch machte und warum

| Beobachtung im Stream | Ursache | Lösung in v1.0.0 |
|---|---|---|
| Bart bleibt im Gesicht | Der arcface_128-Crop endet am Kinn, der Swapper reproduziert Bartstruktur, die Box-Maske blendet die Crop-Unterkante aus | `crop_scale` 0,8 (weiterer Crop), „digitale Rasur“ der Bartzone vor dem Swap, Occluder-Maske in der Bartzone nach unten erweitert |
| Doppeltes Kinn bei offenem Mund | Swapper öffnen den Mund nur halb; das echte Mundinnere schaut daneben hervor | Region-Maske aus bisenet, Mundinneres (`keep_mouth`) bleibt echt: Zähne und Zunge stammen aus der Kamera |
| Hände vor dem Gesicht werden übermalt | Keine Occlusion-Maske | xseg_3-Occluder (Hände/Gegenstände bleiben sichtbar) |
| Brille sitzt „aufgemalt“ | Der Swapper rendert Brillengestelle unsauber | xseg_3 schneidet nur das Gestell aus: echtes Gestell, getauschte Augen dahinter |
| Hautton springt zum Hals | Kein Farbabgleich | LAB-Farbtransfer vom Kamera-Crop (`color_match` 0,5) |
| Körper bleibt, Raum bleibt | Nur das Gesicht wird ersetzt | Workflow 17: MODNet-Matting auf eine leere Hintergrundplatte; wer aus dem Bild geht, ist weg |

## Kette

```
BRIO 1280×720 (DirectShow 2)
  → SCRFD det_10g (2 ms, DML 1)
  → Crop arcface_128 × 0,8
  → [Worker-Thread, DML 0] bisenet_resnet_34 Regionen (7–12 ms) · MODNet-Alpha (8 ms, nur Workflow 17)
  → Rasur der Bartzone mit Wangenfarbe (1 ms)
  → hyperswap_1c_256 (5 ms, DML 1)
  → xseg_3 Occluder (5 ms, DML 1), in der Bartzone nach unten erweitert
  → Maske = Box ∧ Occluder ∧ Regionen(ohne Mundinneres) ∪ Bartzone
  → LAB-Farbabgleich → Einblenden
  → GPEN-BFR-256 (5 ms)
  → [17] Composite auf Clean Plate mit MODNet-Alpha (2 ms)
  → Spout ComfyLiveFaceSwap / ComfyLivePersonSwap
```

Der Worker-Thread existiert nur, wenn `mask_device_id` ≠ `dml_device_id`:
zwei Threads auf demselben DirectML-Adapter lösen in ONNX Runtime opake
Gerätefehler aus (reproduziert), deshalb schaltet die Engine dann auf seriell.

## Gemessene Varianten

Offline auf den 150 Frames, Standardwerte fett:

| Frage | Kandidaten | Ergebnis |
|---|---|---|
| Swapper | inswapper_128, hyperswap_1a, **hyperswap_1c**, alphaface_256, uniface_256 | 1c folgt Mund und Profil am besten bei 5 ms; alphaface ähnlich gut, aber 47 ms; inswapper öffnet den Mund, verliert Identität |
| Occluder | xseg_1, xseg_2, **xseg_3** | xseg_1 schneidet Bart, Mund und Brillengläser als „Occlusion“ heraus (Bart bleibt sichtbar); xseg_3 behält sie als Gesicht und findet Hände am sichersten |
| Crop | 1,0, **0,8**, 0,7 | 0,8 nimmt Kinn und Kiefer mit; 0,7 wird sichtbar weicher; ein vertikaler Versatz des Templates (Gesicht höher im Crop) lässt die Identität sofort kippen und wurde verworfen |
| Rasur | keine, Textur-Filter, **ganze Zone**, Telea-Inpainting | bisenet klassifiziert Bart als *Haut*, deshalb ist die Zone geometrisch (unter Nasenspitze bis Hals); ganze Zone ist zeitlich stabil, Inpainting fleckig |
| Mundinneres | Swapper, **Kamera** | Kamera: echte Zähne/Zunge, Mundöffnung stimmt |
| Farbabgleich | 0, **0,5** | 0,5 gleicht Hautton an, ohne bei Lichtwechsel zu driften |
| Parser | bisenet_resnet_18, **bisenet_resnet_34** | 18 spart nur 1 ms |
| Matting-Größe | **512**, 416, 384, 320 | 512 ist der kompilierte Pfad (5 ms); kleinere Größen sind unter DirectML langsamer |
| Enhancer | **gpen_bfr_256**, gfpgan_1.4, gpen_bfr_512 | 2,5 / 18 / 30 ms |

## Bildraten

Engine allein (150 gespeicherte Frames, ohne Kamera/Spout):

| Konfiguration | Mittel | p95 | Bilder/s |
|---|---|---|---|
| Workflow 16 (Masken auf DML 0 parallel) | 23 ms | 31 ms | 42 |
| Workflow 16, Masken seriell auf DML 1 | 43 ms | 55 ms | 23 |
| Workflow 17 mit Matting, `parser_every` 1 | 33 ms | 41 ms | 27 |
| Workflow 17 mit Matting, `parser_every` 2 | 30 ms | 43 ms | 29 |

Live über den API-Graphen mit echter BRIO und Spout (5. September 2026):

| Workflow | KI-Bilder/s | Verarbeitung Mittel / p95 | Kamera→Spout p50 | Verlorene Kamerabilder |
|---|---|---|---|---|
| 16, 300 Bilder | 22,9 (Kamerarate) | 28 / 31 ms | 55 ms | 5 |
| 17, 500 Bilder, RVC-Dienst gleichzeitig auf der RX 9070 XT, `parser_every` 1 | 18,7 | 45 / 49 ms | 74 ms | 214 |
| 17, 500 Bilder, RVC-Dienst läuft, `parser_every` 2 (Standard) | 24,0 (Kamerarate) | 26 / 43 ms | 34 ms | 38 |

Die BRIO liefert bei 720p rund 24–30 Bilder/s. Workflow 17 teilt sich die
RX 9070 XT mit dem RVC-Stimmdienst; `parser_every` 2 (Standard in Workflow 17)
halbiert die Parser-Last, weil die Regionen im gesichtsausgerichteten Crop
zwischen zwei Bildern kaum wandern.

## Modelle (neu in v1.0.0)

| Datei | Zielordner | Quelle | Größe | SHA-256 | Lizenz |
|---|---|---|---|---|---|
| hyperswap_1c_256.onnx | models/insightface | facefusion/models-3.3.0 | 402.742.682 | 5528c2d76fe9986c99d829278987ef9f3a630cb606db7628d02b57b330f406a5 | FaceFusion ResearchRAIL |
| alphaface_256.onnx | models/insightface | facefusion/models-3.9.0 | 555.624.110 | efcca3ffa1c28b75a007f689b39f7d4716c02810e7fa72d892e175f0b058a2e2 | AlphaFace non-commercial |
| uniface_256.onnx | models/insightface | facefusion/models-3.0.0 | 406.964.143 | eb5ce2af024cddf88ecb93b24e29a6eb44e354aba7d3319e84d29dcd868820f3 | unbekannt (xc-csc101) |
| xseg_3.onnx | models/face_parsing | facefusion/models-3.2.0 | 70.327.709 | 48ccd7e8541e159a5a754ec9e62df2f12065f7df8f9af842c1750342c6533559 | DeepFaceLab GPL-3.0 |
| xseg_2.onnx | models/face_parsing | facefusion/models-3.1.0 | 70.324.286 | cd9a0879eaf43841d765472cf1f8c330dbf9dcb03da0eace93e95f3bcc399042 | DeepFaceLab GPL-3.0 |
| xseg_1.onnx | models/face_parsing | facefusion/models-3.1.0 | 70.324.286 | c4d1498b8a03b5fe2a3a5d2ef2a0402ab03bd51edaf5b2d8d5fb764702a97dd3 | DeepFaceLab GPL-3.0 |
| bisenet_resnet_34.onnx | models/face_parsing | facefusion/models-3.0.0 | 93.632.546 | 4a0b8c958a3c938913bd06a8365dbb3c8761afba6ecbf0d14b3b1f77eb230c96 | yakhyo MIT |
| modnet.onnx | models/background_removal | facefusion/models-3.5.0 | 25.901.946 | a9edce4b47653992aacd1bee48126e65a415ed54e2ecbe51bdca25a8cab0c0d3 | MODNet Apache-2.0 |
| gpen_bfr_512.onnx | models/facerestore_models | facefusion/models-3.0.0 | 284.340.240 | d5f066b9068a8b74217f9712e28e875a6144629b108a6f7355acbdb3a2832c54 | GPEN non-commercial |

Die Vorverarbeitung folgt dem FaceFusion-Quelltext (Stand 3. September 2026):
xseg NHWC 0..1, bisenet NCHW ImageNet-normalisiert mit argmax über 19
CelebAMask-HQ-Klassen, MODNet NCHW −1..1, alphaface mit rohem ArcFace-Vektor,
uniface mit ffhq_512-Quellcrop statt Embedding. Nichts wird zur Laufzeit
nachgeladen; die Liste steht in `tools/upgrade_v100.py`.

## Nodes

| Node | Zweck |
|---|---|
| Face Swap Models · DirectML | Swapper/Enhancer auf `dml_device_id` (1 = R9700), Occluder/Parser/Matting auf `mask_device_id` (0 = RX 9070 XT) |
| Face Swap Identity from Images | bis zu vier IMAGE-Eingänge (je Batch), gemittelte ArcFace-Identität |
| Face Swap Identity from Folder | alle Fotos aus `ComfyUI/input/<ordner>/` (z. B. `face-swap-identity`), Cache bis sich eine Datei ändert |
| Webcam Snapshot / Clean Plate | Testbild von dir nach `delay_seconds`, oder die leere Platte (aus dem Bild gehen); gecacht bis `retake` sich ändert |
| Face Swap Image Preview | Offline-Vorschau mit allen Reglern, optional Matting auf `background`; meldet ms je Stufe |
| Live Face Swap Webcam → Spout | blockierender Live-Node, `background_mode` off/image/green/blur, `parser_every`; Ende nur mit Interrupt |

## Bedienung

**Zielidentität, mehrere Fotos.** Drei LoadImage-Nodes (frontal, Dreiviertel
links, Dreiviertel rechts) hängen an `source_images`, `more_images` und
`more_images_2`. Für 5–20 Fotos den Ordner-Node nehmen: Fotos nach
`L:/ComfyUI/ComfyUI/input/face-swap-identity/` legen und den Ordner wählen.
Frontal, lächelnd, Mund offen und Dreiviertelansichten stabilisieren die
Identität; das Ziel sollte keine Brille tragen (die kommt von dir).

**Testbild.** Ein Bild von dir, so wie die Kamera dich sieht. Der
Snapshot-Node nimmt es beim ersten Run nach 3 Sekunden auf und behält es
(`retake` ändern für ein neues). Die Vorschau zeigt darauf den Swap mit allen
Reglern; der Timing-Text nennt die Millisekunden je Stufe.

**Workflow 17, Clean Plate.** Beim ersten Run wartet der obere Snapshot-Node
8 Sekunden, in denen du das Bild verlässt. Kamera nicht mehr bewegen; bei
Lichtwechsel `retake` erhöhen. Der RVC-Launcher startet den Stimmdienst
(eigenes RVC-Modell nötig, siehe Voice-Design-Workflows und
`docs/LIVE_FACE_SWAP_V099.md`, Abschnitt Stimme).

**Live.** Bypass des Live-Nodes aufheben, OBS-Spout-Quelle
`ComfyLiveFaceSwap` bzw. `ComfyLivePersonSwap`, einmal **Run**, Ende nur mit
**Interrupt**. Metriken: `L:/ComfyUI/logs/live-face-swap/metrics.json`.

Regler, wenn etwas nicht passt:

| Symptom | Regler |
|---|---|
| Bart schimmert am Kinn | `crop_scale` 0,7, `shave_extent` 1,0, `mask_blur` 0,2 |
| Ziel hat selbst einen Bart | `shave` none |
| Mund wirkt fremd | `keep_mouth` aus (Swapper-Mund) |
| Hautton zu blass/zu warm | `color_match` 0,3–0,8 |
| Bildrate unter Kamerarate | `parser_every` 2, `enhancer_every` 2, Enhancer `none` |
| Gesicht flackert bei Bewegung | `landmark_smoothing` 0,6–0,7 |

## Was auf dieser Hardware nicht geht

Ein Ganzkörpertausch in Echtzeit (andere Statur, Brust, Kleidung, Frisur)
ist auf RDNA4 ohne Flimmern nicht möglich: Diffusions-Bildspiegel schaffen
0,4–1,6 Bilder/s ohne zeitliche Konsistenz (Workflow 07/11), Reenactment
(LivePortrait) animiert nur ein Standbild, und ein Video-Diffusionsmodell mit
Körperkontrolle läuft hier bei rund 120 s je Schritt. Realistisch bleibt: echtes
Kamerabild, getauschtes Gesicht, ersetzter Hintergrund (Workflow 17). Für einen
anderen Körper bleibt der 3D-Avatar-Pfad (Workflow 06/12-III) mit stilisiertem
Look. Die Stimme läuft weiter über den DirectML-RVC-Dienst; eine bestimmte
Zielstimme braucht ein eigenes RVC-Modell.

## Grenzen

- Sehr starkes Profil (Ohr zur Kamera) verliert kurz das Gesicht; SCRFD findet es beim Zurückdrehen sofort wieder.
- MODNet ist ein Porträt-Matting: Haare und Hände sind gut, dünne Gegenstände in der Hand werden weich; die Clean Plate muss zur unveränderten Kameraposition passen.
- Hände direkt unter dem Kinn können in der nach unten erweiterten Bartzone teilweise übermalt werden (bis 15 % der Crop-Höhe).
- Lizenzen: hyperswap ResearchRAIL, inswapper/GPEN/alphaface/buffalo_l nicht-kommerziell, xseg GPL-3.0, bisenet MIT, MODNet Apache-2.0, GFPGAN Apache-2.0. Nur eigene oder ausdrücklich freigegebene Gesichter verwenden und die Synthese im Stream sichtbar kennzeichnen.
