# Live Face Swap · Workflow 16 · v0.9.9

> **v1.0.0:** Masken, Rasur, Farbabgleich, Worker-Thread, Matting und Workflow 17 stehen in [LIVE_PERSON_SWAP_V100.md](LIVE_PERSON_SWAP_V100.md). Dieses Dokument beschreibt die DirectML-Grundlagen und die v0.9.9-Messwerte.

Workflow:

`workflows/Live Avatar/LiveAvatar-16-Live-Face-Swap-DirectML-Spout-OBS.json`

Der Workflow ersetzt die Gesichtsidentität im Webcam-Bild in Echtzeit durch ein
Quellfoto und liefert das Ergebnis als Spout-Sender `ComfyLiveFaceSwap` an OBS.
Mimik, Kopfhaltung, Hände, Kleidung und Hintergrund bleiben das echte
Kamerabild; nur das Gesicht wird getauscht. Das ist derselbe Ansatz wie
Deep-Live-Cam und FaceFusion, aber als eigener ComfyUI-Node ohne externe App,
ohne Supervisor-Gerüst und ohne CUDA.

## Warum dieser Pfad statt der bisherigen Versuche

| Pfad | Was er wirklich tut | Ergebnis auf dieser Hardware |
|---|---|---|
| Workflow 07/11 (SD1.5-LCM + OpenPose + IPAdapter) | Diffusion je Frame | 0,4–1,6 Bilder/s, Identität und Anatomie wechseln je Frame („grotesk“) |
| Workflow 03/05/12-II (LivePortrait) | Animiert ein Standbild mit der Webcam-Mimik | Nur Kopf, statischer Hintergrund, kein Körper, sichtbar „Avatar“ |
| Workflow 12-I (externe DeepFaceLive/FaceFusion-Kandidaten) | Precheck und Supervisor, keine Verarbeitung | Kein Kandidat wurde je installiert oder gemessen |
| **Workflow 16 (dieser Pfad)** | InsightFace-Erkennung + InSwapper/HyperSwap + optionaler Enhancer, alles DirectML | Echtes Kamerabild mit getauschter Identität; Latenz und Bildrate siehe Messwerte |

## Modelle

Alle Dateien wurden am 5. September 2026 heruntergeladen, per SHA-256 geprüft
und in den ComfyUI-Modellordner einsortiert. Nichts wird zur Laufzeit
nachgeladen.

| Datei | Zielordner | Quelle | Größe | SHA-256 | Lizenz |
|---|---|---|---|---|---|
| `inswapper_128.onnx` | `models/insightface/` | `facefusion/models-3.0.0` (HF) | 555.303.150 B | `a290273e…54bea7` | InsightFace nicht-kommerziell |
| `hyperswap_1a_256.onnx` | `models/insightface/` | `facefusion/models-3.3.0` (HF) | 402.742.682 B | `c0e98a8a…246add` | FaceFusion ResearchRAIL |
| `gpen_bfr_256.onnx` | `models/facerestore_models/` | `facefusion/models-3.0.0` (HF) | 75.792.988 B | `bad8bf04…ae5c25` | GPEN nicht-kommerziell |
| `gfpgan_1.4.onnx` | `models/facerestore_models/` | `facefusion/models-3.0.0` (HF) | 340.299.087 B | `accc4757…311385` | Apache-2.0 |
| `buffalo_l/` (`det_10g.onnx`, `w600k_r50.onnx`, …) | `models/insightface/models/buffalo_l/` | `deepinsight/insightface` Release v0.7 (`buffalo_l.zip`) | 288.621.354 B (ZIP) | `80ffe37d…b0ca2f` | InsightFace nicht-kommerzielle Forschung |

Vollständige Hashes stehen in `tools/upgrade_v099.py` (`MODEL_FILES`) und in
`custom_nodes/ComfyUI-DaWasteh-LiveAvatar/face_swap.py`. Beim ersten Laden legt
der Node `inswapper_128.emap.npy` neben dem Modell ab (die 512×512-Identitäts-
Projektion, ohne das `onnx`-Paket gelesen).

**Lizenzgrenze:** InSwapper, buffalo_l und GPEN sind nicht-kommerziell,
HyperSwap ist ResearchRAIL. Für private Streams/Tests geeignet; für kommerzielle
Nutzung müssen die Rechte separat geklärt werden. Nur eigene oder ausdrücklich
freigegebene Gesichter verwenden und die Synthese im Stream sichtbar kennzeichnen
(siehe `docs/LIVE_AVATAR_WORKFLOW_12_13.md`, Abschnitt Einwilligung).

## Nodes

Alle vier Nodes liegen in `ComfyUI-DaWasteh-LiveAvatar/face_swap.py` unter
`DaWasteh/Live Avatar`:

- **Face Swap Models · DirectML** lädt Detektor, Swapper und optional den
  Enhancer als ONNX-Runtime-Sitzungen auf einem DirectML-Adapter
  (`dml_device_id`). Sitzungen werden pro Einstellung gecacht.
- **Face Swap Identity from Images** mittelt die ArcFace-Einbettung des
  größten Gesichts aus einem IMAGE-Batch (mehrere Fotos = stabilere Identität)
  und gibt eine Zusammenfassung mit Kurz-ID aus.
- **Face Swap Image Preview** tauscht Gesichter in einem IMAGE-Batch offline und
  meldet Millisekunden pro Stufe (Erkennung / Swap / Enhancer). Damit werden
  Quellfoto und Einstellungen geprüft, bevor die Kamera läuft.
- **Live Face Swap Webcam → Spout** ist der blockierende Live-Node: BRIO über
  DirectShow (Index 2, 1280×720), Erkennung, Swap, optional Enhancer,
  Paste-back mit weicher Box-Maske, Spout-Sender. Beenden nur mit
  **Interrupt**, nie mit Run (Instant). Er ist im ausgelieferten Workflow
  **bypassed**, damit `Run` zuerst nur die Vorschau ausführt.

Technik: SCRFD (`det_10g`) mit fünf Landmarken bei 320 px, ArcFace-Ausrichtung,
`arcface_128`-Template für den Swapper-Crop (128 bzw. 256 px), `ffhq_512`
beziehungsweise `arcface_128` für den Enhancer, Box-Maske mit 30 % Weichzeichnung,
exponentielle Landmarken-Glättung mit Rücksetzen bei schnellen Kopfbewegungen,
Tracking des zuletzt getauschten Gesichts bei mehreren Personen. Die Logik ist
aus FaceFusion und InsightFace (MIT) portiert; das `insightface`-Paket selbst
wird nicht importiert, weil sein `onnx`-Import an dem protobuf-3.19-Pin der
installierten Audio-Packs scheitert.

## DirectML statt ROCm

Die Swapper-Modelle existieren nur als ONNX. Auf Windows-RDNA4 ist ONNX Runtime
DirectML der einzige beschleunigte Pfad (ROCm-EP gibt es nur unter Linux, Triton
gibt es nicht). Im venv lagen drei ONNX-Runtime-Distributionen übereinander
(`onnxruntime`, `onnxruntime-gpu`, `onnxruntime-directml`); die CPU/CUDA-Variante
hatte gewonnen und `DmlExecutionProvider` war nicht verfügbar. Der Updater
entfernt jetzt `onnxruntime-gpu` (auf AMD nutzlos) und installiert
`onnxruntime-directml` als letzten Schreiber neu; ein Check bricht ab, wenn der
DirectML-Provider danach fehlt.

DirectML-Adapterindizes sind nicht die HIP-Indizes. Auf diesem Rechner:

| DirectML `device_id` | GPU | Nachweis |
|---|---|---|
| 0 | AMD Radeon RX 9070 XT | Prozessspeicher auf LUID `0x16581` |
| 1 | AMD Radeon AI PRO R9700 | Prozessspeicher auf LUID `0x199af` |

Spout und OBS laufen auf der R9700, deshalb ist `dml_device_id = 1` der
Standard. Der DirectML-RVC-Begleiter belegt weiterhin die RX 9070 XT
(`Voice Design/RVC_DirectML-Live-Microphone-Voice-Swap.json`).

## Bedienung

1. Workflow laden. Im Node **Quellidentität** ein frontales, gut beleuchtetes
   Foto der freigegebenen Zielperson wählen (keine Brille, neutraler Ausdruck;
   zwei bis drei Fotos als Batch stabilisieren die Identität).
2. **Run**: Der Vorschau-Zweig tauscht das Testbild und zeigt Millisekunden pro
   Stufe. Swapper, Enhancer, `mask_blur` und `enhancer_blend` hier einstellen.
3. Den Live-Node per Rechtsklick → **Bypass** aufheben, in OBS eine
   Spout2-Quelle `ComfyLiveFaceSwap` anlegen, dann **Run**. Das Kamerabild wird
   gespiegelt ausgegeben (`mirror`).
4. Beenden mit **Interrupt**. Metriken liegen unter
   `L:/ComfyUI/logs/live-face-swap/metrics.json` (AI-Bilder/s, Präsentationen,
   Duplikate, Capture→Spout-Latenz, Swap-Millisekunden).

Empfohlene Live-Profile:

| Ziel | Swapper | Enhancer | Hinweis |
|---|---|---|---|
| Höchste Bildrate | `inswapper_128` | `none` | Weichstes Ergebnis, 128-px-Gesicht |
| Ausgewogen (Standard) | `inswapper_128` | `gpen_bfr_256` | schärfere Haut/Augen, geringe Zusatzkosten |
| Maximale Schärfe | `hyperswap_1a_256` | `gfpgan_1.4` | teuerster Pfad, `enhancer_every = 2` bei zu niedriger Bildrate |

## Stimme

Für die Stimme bleibt der gemessene DirectML-RVC-Pfad (deiteris b2332) auf der
RX 9070 XT die passende Modellklasse: kontinuierliche Sprach-zu-Sprach-
Konvertierung mit erhaltenem Timing. Voice-Cloning-TTS (OmniVoice, Qwen3-TTS)
ist dafür ungeeignet (siehe `docs/OMNIVOICE_LIVE_SWAP_EVALUATION.md`). Für eine
bestimmte Zielstimme wird ein eigenes RVC-Modell benötigt; auf AMD/Windows
trainiert Applio über ZLUDA, alternativ in der Cloud. Beatrice V2 (w-okada
VC-Client 2.2 „only_beatrice“, DirectML-Build 2.1.4) ist als latenzärmere
Alternative dokumentiert, benötigt aber Beatrice-eigene Stimmmodelle, deren
Training CUDA voraussetzt.

## Grenzen

- Ein Standbild liefert nur die Frontalidentität; starke Profile, Brillen,
  Hände vor dem Gesicht und Haare über der Stirn erzeugen sichtbare Kanten
  (kein XSeg-Occluder in v0.9.9).
- Der Swap ersetzt das Gesicht, nicht Frisur, Kopfform oder Körper. Für einen
  vollständigen Avatar bleibt Workflow 06/12-III (VRM) zuständig.
- 128-px-Swapper bei 720p wirken bei Nahaufnahmen weich; der Enhancer
  kompensiert, kann aber Zähne/Augen „glätten“. `enhancer_blend` 0,5–0,8 ist
  der natürlichere Bereich.
- DirectML-Sitzungen sind nicht threadsicher; alle Modelle laufen sequenziell im
  ComfyUI-Ausführungsthread. Kamera und Spout laufen in eigenen Threads.

## Messwerte · 5. September 2026

Offline-Pipeline (Erkennung + Swap + Paste-back, optional Enhancer) auf einem
freien System, ONNX Runtime DirectML 1.24.4, Mittel aus fünf warmen Läufen,
Zielbild 649×1280 (Flash2.jpg) beziehungsweise 1024×1024 (Workflow-13-Ansicht):

| Swapper | Enhancer | R9700 (DML 1) 649×1280 | R9700 1024×1024 | RX 9070 XT (DML 0) 649×1280 |
|---|---|---|---|---|
| inswapper_128 | none | 13,2 ms (det 2,3 / swap 10,8) | 17,4 ms | 13,6 ms |
| inswapper_128 | gpen_bfr_256 | 38,0 ms (enh 24,5) | 55,1 ms | 39,6 ms |
| inswapper_128 | gfpgan_1.4 | 65,1 ms (enh 51,5) | 81,2 ms | 67,8 ms |
| hyperswap_1a_256 | none | 9,7 ms (det 2,0 / swap 7,6) | 15,3 ms | 10,2 ms |
| hyperswap_1a_256 | gpen_bfr_256 | 35,3 ms (enh 23,8) | 47,3 ms | 37,9 ms |

Reine Modellzeit: SCRFD det_10g bei 320 px 1,0 ms (nur mit fest überschriebenen
Eingabedimensionen; die dynamische Variante scheitert unter DirectML an
`Reshape_223`), ArcFace 2,4 ms, inswapper_128 5,2–5,4 ms auf beiden Karten.
Der Rest der „swap“-Spalte ist CPU-Warp und Paste-back. Auf der CPU dauert
derselbe Pfad 0,7–2,2 s pro Bild, weshalb DirectML zwingend ist.

Damit sind 720p-Livebilder mit `inswapper_128` ohne Enhancer bei Kamerarate
(30 Bilder/s) möglich, mit GPEN-BFR-256 etwa 25 Bilder/s und mit GFPGAN 1.4
etwa 15 Bilder/s (`enhancer_every = 2` hebt das wieder auf Kamerarate). Die
Live-Kette (BRIO → Swap → Spout, headless über den API-Graphen, je 300 Bilder,
DirectML-Gerät 1 = R9700):

| Profil | KI-Bilder/s | Präsentationen/s | Duplikate | Kamera→Spout p50 / p95 |
|---|---|---|---|---|
| inswapper_128, kein Enhancer | 23,4 | 24,1 | 35 | 31 / 37 ms |
| inswapper_128 + gpen_bfr_256 (Standard) | 23,2 | 23,9 | 28 | 31 / 38 ms |
| hyperswap_1a_256 + gpen_bfr_256 | 23,4 | 24,1 | 27 | 14 / 21 ms |
| hyperswap_1a_256 + gfpgan_1.4 | 23,3 | 24,1 | 11 | 22 / 29 ms |

Alle Profile laufen mit Kamerarate: Die BRIO liefert bei 1280×720 über
DirectShow rund 24 Bilder/s, verlorene Kamerabilder gab es in keinem Lauf.
