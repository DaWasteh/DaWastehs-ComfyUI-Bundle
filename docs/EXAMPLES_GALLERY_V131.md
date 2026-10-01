# Beispielgalerie, Namensschema und Korrekturen · v1.3.1

**Galerie:** <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/> · Dateien im Repo: [`examples/`](../examples/README.md)

## Was die Galerie zeigt

Zu jedem der 265 Workflows gibt es eine eigene Seite:

- einen **Screenshot aus ComfyUI** nach dem Lauf, mit Eingabe und Ergebnis direkt im Workflow. Die Erklärungstafeln sind ausgeblendet, die Gruppen auf ihren Inhalt zusammengeschoben;
- die **Ausgaben** (Bild, Video, Audio, 3D-Modell zum Drehen, Text) und die Eingabedateien;
- **Prompt und Einstellungen** zum Kopieren, den Workflow als Download und als kopierbares JSON;
- **Dauer, VRAM und RAM** der jeweiligen Generierung.

Bildmodelle zeigen vier Ideen (Porträt, Fantasy-Landschaft, Roboter, Poster mit Schrift) in drei Auflösungen mit gleichem Seed. Unter „Quant-Vergleich“ stehen Modelle mit mehreren Quantisierungen oder Varianten nebeneinander, bei Bildern mit Schiebe-Regler. Videos sind höchstens 5 Sekunden lang (das One-Click-Musikvideo 8 Sekunden mit zwei Szenen), Songs 60 Sekunden.

Das Hauptbeispiel jedes Bild-Workflows liegt als WebP in voller Auflösung vor und enthält den kompletten Workflow (Datei in ComfyUI ziehen). 3D-Modelle sind für die Web-Ansicht komprimiert (Meshopt, WebP-Texturen), die Geometrie ist unverändert.

## Wie die Beispiele entstanden

Jedes Beispiel ist ein normaler Lauf des ausgelieferten Workflows über das echte ComfyUI-Frontend (headless Edge, `app.queuePrompt`). Geändert wurden nur Prompt, Seed, Größe, Dauer und Eingabedateien; die Seeds stehen fest (`control_after_generate = fixed`). Die Eingabebilder, Stimmen und Songs wurden selbst mit Bundle-Workflows erzeugt (Z-Image Turbo, Qwen3-TTS VoiceDesign, ACE-Step); private Fotos, fremde Stimmen oder urheberrechtlich geschützte Songs kommen nicht vor. Einzige Ausnahme sind die vier Ansichten für Pixal3D MultiView: Der Workflow verlangt kalibrierte Renders (90° Abstand, FOV 20°, gleiche Skala, schwarzer Hintergrund), deshalb rendert `tools/examples/blender_multiview_views.py` einen prozeduralen Briefkasten in Blender mit genau dem Kamera-Rig des Nodes.

- Testserver: eigene ComfyUI-Instanz auf Port 8192 mit dem R9700-Profil aus `tools/start-MultiGPU.ps1` (reserve-vram 4, DaWasteh-VRAM-Wächter 3 GiB, hipBLASLt, cache-ram), eigene Ein- und Ausgabeordner.
- **Dauer** = Ausführungszeit laut ComfyUI-Verlauf (ohne Frontend-Laden); vor jedem neuen Workflow werden die Modelle entladen, die Zeit enthält also das Laden der Modelle.
- **VRAM** = Spitze der Windows-GPU-Zähler für den ComfyUI-Prozess (enthält den Treiber-Overhead von rund 4 GiB) und daneben die PyTorch-Spitze (`max_memory_reserved`); ein mitlaufender llama-server (Qwen3.8 auf der RX 9070 XT) wird getrennt ausgewiesen.
- **RAM** = Spitze des Arbeitsspeichers (RSS) des ComfyUI-Prozesses.
- Referenzrechner: Windows 11, AMD Radeon AI PRO R9700 (32 GB) und RX 9070 XT (16 GB), 47 GB RAM, ComfyUI 0.37.0, PyTorch 2.13 + ROCm.

Werkzeuge: `tools/examples/` (Katalog `catalog*.py`, `runner.py`, `reshoot.py`, `build_gallery.py`); die Seite liegt unter `examples/` und wird per GitHub Actions (`.github/workflows/pages.yml`) veröffentlicht.

## Neues Namensschema

`<Modell>[_<Variante>]_<Quant>[+<Hilfsmodell>]-<Eingabe>-to-<Ausgabe>[-<Zweck>]` – Einzelheiten und Beispiele im README-Abschnitt [Benennung](../README.md#benennung), die vollständige Liste alt → neu (207 Dateien) in [`tools/workflow_renames_v131.json`](../tools/workflow_renames_v131.json). Der Updater räumt die alten Dateien aus `user/default/workflows/DaWasteh` weg; lokal geänderte Kopien bleiben liegen und werden im Log mit dem neuen Namen genannt. Workflow-IDs und die Herkunftsfelder in `extra` behalten den alten Namen.

## Fehler, die die Beispielläufe gefunden haben

Jede Korrektur ist ein deterministisches Werkzeug; `tools/validate_workflows.py --against-head` baut alle geänderten Dateien aus dem v1.3.0-Stand nach (`tools/workflow_fixes_v131.py`).

| Workflow | Fehler | Korrektur |
|---|---|---|
| Z-Image Turbo MoodyRealMix, FLUX.1 dev UltraReal (bisher „SDXL_…“) | Die Checkpoints enthalten Z-Image- bzw. FLUX.1-Modelle, keine SDXL-Modelle; die SDXL-Graphen liefen nicht | auf der richtigen Architektur neu aufgebaut (`build_finetune_fixes_v131.py`) |
| LTX-2.3 Bild→Video, Erstes+letztes Bild mit Audio, Bernini Video-Edit, Stable Audio 3 FP32/INT8 | Die Dual-GPU-Migration hatte Geräte-Werte in Subgraph-Instanzen geschrieben; das Frontend las „gpu:0“ als Prompt | Werte entfernt, Generator korrigiert |
| Qwen3-TTS LoRA Live-Voice, Live Avatar 04 | Alle Werte nach dem Seed um eins verschoben (`top_p = 20`) | fehlender `control_after_generate`-Wert ergänzt |
| Qwen3-TTS CustomVoice | neues Feld `instruct` bekam `True` | Werte neu zugeordnet |
| LTX-2.3 Director (3 Workflows) | WhatDreamsCost 2.x: Global Prompt in der Timeline, neue Felder, Ausgang `frame_rate` verschoben | auf das 2.x-Schema migriert; Replay zusätzlich ohne defekte Use-Everywhere-Eigenschaften und mit gültigen Video-Speicher-Werten |
| WAN 2.2 TI2V 5B, WAN 2.2 Fun Control 5B | VAE-Decode brauchte schon bei 5 s 1280×704 über 18 GiB am Stück, auch Comfys Kachel-Fallback scheiterte | `VAE Decode (Tiled)` 512/64/64/8 |
| Kandinsky 5 Lite Bild→Video | VAE-Decode auf der RX 9070 XT (16 GB): ComfyUIs Kachel-Fallback dekodiert alle 121 Frames auf einmal und forderte 16,9 GiB am Stück | `VAE Decode (Tiled)` 256/64/32/8 (Blöcke à 32 Frames); das VAE läuft auf der R9700, weil der Text-Encoder (Qwen 2.5 VL 7B) auf der zweiten Karte 9,5 GiB belegt hält |
| MMAudio Video → Ton | Dauer (8 s) und Bildrate der Ausgabe (8 fps) standen fest; der Sampler verteilt aber das ganze Video auf die Dauer – bei jedem anderen Video saß der Ton nicht auf dem Bild, ein 16-fps-Video lief halb so schnell und der Ton endete nach der Hälfte | neuer Node „Video-Info“ (`VHS_VideoInfoLoaded`) gibt fps und Länge des geladenen Videos an Sampler und Video-Ausgabe |
| SDPose und Depth Anything 3 aus Video | Meta Batch Manager mit Werten als Liste gespeichert; VHS meldete bei jedem Öffnen „Failed to restore node: META-BATCH“ und färbte den Node rot | Werte im VHS-Format (`{"frames_per_batch": 64, "count": 0}`), auch im v1.2.8-Builder |
| Z-Image Turbo Tiled Upscale | lud den Text-Encoder von FLUX.2 Klein 9B (`qwen3_8b`) | `qwen_3_4b` wie Z-Image Text→Bild |
| FLUX.1 Kontext Character Keep | Negativ-Zweig ohne Eingang (Prompt wurde abgewiesen); gespeicherter Standard-Prompt verlangte, die Person auf dem Foto zu entkleiden | Verbindung ergänzt, neutrale Character-Keep-Anweisung |
| WAN 2.2 14B Text→Video | lud die Bild→Video-Modelle und -LoRAs; ohne Startbild nur Rauschen | T2V-Modelle und T2V-Lightning-LoRAs (High-Noise-Dateien siehe unten) |
| Ideogram 4 + Qwen3.5 (Idee → JSON → Bild, Idee → Felder, Idee → JSON) | optionaler Skizzen-Loader mit fehlender Platzhalterdatei ließ ComfyUI den ganzen Qwen-Zweig verwerfen; das JSON erreichte den Prompt-Builder nicht (Bild = Rauschen) | Loader stummgeschaltet (Strg+M zum Verwenden), Qwen-JSON → `import_json` des Builders |
| SDXL RealVisXL + IP-Adapter | Mit aktivem IP-Adapter brannten alle SDE-Sampler bunte Flecken ins Gesicht (auf diesem ROCm-Stack; ohne IP-Adapter sauber) | `dpmpp_2m` / `karras` für Sampler und FaceDetailer |
| LTX-2.3 22B Text→Video (4 Workflows), LTX-2.3 Bild→Video | Der gekachelte VAE-Decode forderte 2,6–3,3 GiB am Stück, während das 22B-Modell geladen blieb (ComfyUI unterschätzt den Decode und entlädt nichts) – bei 1280×704 unter dem VRAM-Wächter „out of memory“; Bild→Video dekodierte zeitlich das ganze Video auf einmal (4096 Frames) | Kacheln 384 px (Bild→Video zusätzlich Blöcke à 32 Frames); gemessen: beide laufen, keine sichtbaren Nähte |
| LTX-2.3 dev MXFP8 Text→Video | Text-Encoder auf der RX 9070 XT – Gemma 3 12B belegt geladen 25 GB, jeder Lauf endete in `CLIPTextEncode` | Text-Encoder und VAE standardmäßig auf der R9700 wie bei den anderen LTX-2.3-Workflows |
| Bernini-R Bild-Edit | lud `T5\t5xxl_fp8…` als Wan-Text-Encoder („invalid tokenizer“) | `UMT5\umt5_xxl_fp8…` wie der Video-Edit und alle WAN-Workflows |
| Bernini-R Bild-Edit (Nachtrag) | die Subgraph-Instanz reichte `clip_name` mit dem alten T5-Pfad nach innen durch und überschrieb die Korrektur im Subgraph | Wert auch an der Instanz korrigiert |
| Ideogram 4 Text → Bild, Ideogram 4 + Qwen3.5 Idee → Prompt → Bild | BasicScheduler karras mit 28 Schritten, res_2m und AuraFlow-Shift 5: dieser Zeitplan passt nicht zum Flow-Modell, jedes Bild trug ein Raster-/Krakelee-Muster, Flächen blieben unscharf, kleine Schrift unleserlich | Sampling-Kette der offiziellen ComfyUI-Vorlage: `Ideogram4Scheduler` (Preset „Default“: 20 Schritte, mu 0, std 1,75), euler, CFG-Override 3 ab 0,7, Shift 1 (nativ); bei Idee → Bild bekommt der Scheduler die Größe vom selben Auflösungs-Node wie das Latent |
| FLUX.2 Klein Base 4B Text → Bild | Das undestillierte Base-Modell lief wie das destillierte mit CFG 1 und genulltem Negativ: weiche, verwaschene Bilder, zerfahrene Schrift | CFG 5 und leerer Negativ-Prompt über denselben Text-Encoder wie in der offiziellen Klein-Base-Vorlage; 24 Schritte bleiben |
| FLUX.2 Klein 4B + Gemma 4 · Audio → Audio-React-Video | „VRAM Debug“ vor dem Decode entlud alle Modelle; ComfyUI schiebt sie dabei zurück in den Arbeitsspeicher (rund 14 GiB). Die Pixaroma-Audio-Engine legt alle Frames im RAM ab (8 s bei 1024×1024 ≈ 2,2 GB) und brach mit „above the 0.9 GB currently free“ ab – auch auf frisch gestartetem ComfyUI | `unload_all_models` aus, nur Cache leeren (wie im Audio→Bild-Workflow); die Engine rendert Frame für Frame auf der GPU und braucht kaum VRAM |
| Qwen3.5 Idee → Ideogram-4-Felder | „Save Text“ schrieb fest nach `H:\ComfyUI\ComfyUI\output\prompts\` (Laufwerk des Erstell-Rechners); überall sonst „Das System kann den angegebenen Pfad nicht finden“ | relativ `output/prompts/` (beide Starter laufen im ComfyUI-Ordner) |
| Qwen Image Edit 2511 · 8 Kamerawinkel (offizielle Vorlage) | jeder der acht Winkel lud sein eigenes 41-GB-Modell samt Text-Encoder, VAE und LoRAs; unter RAM-Druck blieb die erste Kopie geladen, während der zweite Winkel die nächste lud – 173 GB System-Commit nach zwei Winkeln | eine gemeinsame Lade-Kette für alle acht Winkel (Modell wird einmal geladen); Modell-Tafel nennt jetzt die 2511-Dateien und die INT8-ConvRot-Alternative. Gemessen, alle acht Winkel: bf16 601 s, höchstens 119 GiB Commit; INT8 ConvRot (20,5 GB) 137 s, 71 GiB |
| SDXL Illustrious V2 (NSFW) | 180 Schritte bei CFG 69 | 30 Schritte, CFG 6,5 |
| SDXL Multi-Checkpoint (NSFW) | Stufe 3 nahm das Eingangsbild statt des Ergebnisses von Stufe 2 | Kette verbunden |

## Umgebung und fremde Custom Nodes

- **Schreibgeschütztes Laden großer Modelle:** ComfyUI blendet safetensors-Dateien unter Windows „copy-on-write“ ein; Windows rechnet dabei die ganze Datei sofort auf den System-Commit an, zusätzlich zu jeder VRAM-Belegung. FLUX.2 dev FP8 mixed mit dem bf16-Mistral-Encoder (2 × 33 GiB) trieb den Commit so auf 159 GiB. `ComfyUI-DaWasteh-MultiGPU-Control` lädt safetensors ab 1 GiB jetzt schreibgeschützt (`readonly_load.py`): dieselben Tensoren in derselben Reihenfolge (an echten Dateien byte-gleich geprüft), aber ohne Commit-Anrechnung (Klein 9B KV FP8: 9,16 → 0,02 GiB). Bei Fehlern lädt ComfyUI wie bisher; abschalten mit `DAWASTEH_READONLY_SAFETENSORS=0`.
- **SAM3-Text-Encoder auf der zweiten GPU (ComfyUI-Core):** „Select CLIP Device“ lädt einen CLIP zum Verschieben neu aus dem Checkpoint. Bei SAM3/SAM 3.1 fehlen auf diesem Weg die Text-Encoder-Gewichte, der Lauf brach mit „'NoneType' object has no attribute 'keys'“ ab (SCAIL 2 Charakter-Animation, Text-Encoder auf der RX 9070 XT). `sam3_reload.py` im MultiGPU-Pack holt sie in dem Fall aus dem Checkpoint; abschalten mit `DAWASTEH_SAM3_RELOAD_FIX=0`. Upstream gemeldet: [ComfyUI #16675](https://github.com/Comfy-Org/ComfyUI/issues/16675).
- **Rechentyp nach „Select Model Device“ (ComfyUI-Core):** Der Core-Node legt nach dem Verschieben eines Modells den Rechentyp neu fest, ignoriert dabei aber, welche Typen das Modell unterstützt – FP8-Gewichte bekamen immer float16. Qwen Image Edit 2509 (FP8) lief darin über und speicherte ein schwarzes Bild. `ComfyUI-DaWasteh-MultiGPU-Control` korrigiert das beim Start (`compute_dtype.py`): Nur wenn ComfyUIs Wahl vom Modell nicht unterstützt wird, nimmt es einen unterstützten Typ (bei Qwen bfloat16) wie ComfyUIs Loader. FLUX, FLUX.2, Krea 2 und WAN unterstützen float16 und bleiben unverändert. Abschalten: `DAWASTEH_COMPUTE_DTYPE_FIX=0`. Upstream gemeldet: [ComfyUI #16682](https://github.com/Comfy-Org/ComfyUI/issues/16682).

- **insightface für IP-Adapter FaceID:** Der Updater installiert jetzt `insightface 1.0.1`, `ml_dtypes` und `protobuf 5.29.6` als letzten Schritt ohne Abhängigkeiten (so bleiben `onnxruntime-directml` und OpenCV unangetastet). `onnx` war vorher mit protobuf 3.19 gar nicht importierbar. Einzig YuE's `descript-audiotools` verlangt formal protobuf < 3.20; es nutzt protobuf nur über tensorboard, das mit 5.x läuft (YuE-Läufe bestätigt).
- **Zwei Qwen3-TTS-Packs** (`qwen3-tts-comfyui` und `ComfyUI-QwenTTS`) bringen je ein eigenes `qwen_tts` mit. Nach einem AILab-Node schlug „Save Voice“ des anderen Packs mit `PicklingError` fehl. `ComfyUI-DaWasteh-Qwen3TTS-LoRA` enthält dafür `qwen_tts_compat.py`: Der Modulname bleibt beim Pack, der ihn zuerst geladen hat.
- **YuE:** Der Node benutzte den kompletten Genre-Text als Dateinamen; lange Genre-Texte (schon der Standardtext des FP16-Workflows) scheiterten unter Windows mit `OSError 22`. Zusätzlicher Patch `tools/patches/ComfyUI_YuE-Windows-long-genre-filenames.patch`, anzuwenden nach dem bisherigen YuE-Patch.
- **WAN 2.2 14B Text→Video** braucht jetzt `wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors` und `wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors` (Links in der Modell-Notiz des Workflows).
- **SDMatte (Remove Background / Combiner mit transparenten Objekten):** Der Node lädt beim ersten Lauf rund 5 GB nach. Bricht die Verbindung zu Hugging Face ab, bleiben halb gefüllte Ordner zurück, und der Node lädt nur bei *leeren* Ordnern nach. Folge bei jedem weiteren Lauf: `TypeError: expected str, bytes or os.PathLike object, not NoneType` (beim Galerie-Lauf fehlten `tokenizer/vocab.json` und `special_tokens_map.json`). Abhilfe: den betroffenen Unterordner in `models/RMBG/SDMatte/` löschen, der nächste Lauf lädt ihn vollständig neu.

## Bekannte Grenzen

- **Arbeitsspeicher bei LTX-2.3 22B:** Auf dem Referenzrechner (47 GB RAM) trieben die LTX-Video-Workflows den System-Commit über die wachsende Auslagerungsdatei auf 130–160 GB. Nach mehreren solchen Läufen hintereinander stürzte Windows einmal ab (Bugcheck 0x101). Für die Galerie lief jeder Video-Workflow in einem frischen ComfyUI-Prozess mit einer Commit-Obergrenze. Bei eigenen Läufen: andere Programme schließen, zwischen langen LTX-Läufen ComfyUI neu starten. Seit dem schreibgeschützten Laden (siehe oben) blieb FLUX.2 dev FP8 mixed mit dem bf16-Mistral-Encoder (2 × 33 GiB Dateien) bei 104–120 GiB System-Commit statt 159 GiB und lief damit durch.
- **YuE 7B INT8:** bitsandbytes-INT8 rechnet unter Windows/ROCm sehr langsam; Stufe 2 eines 60-Sekunden-Songs war nach zwei Stunden nicht fertig (Stufe 1: 16 min, FP16 komplett: 25 min). Das Galerie-Beispiel ist deshalb ein einzelner 15-Sekunden-Abschnitt (36 min).
- **Keine Beispiele** gibt es für Echtzeit-Workflows (Webcam, Spout, Mikrofon), LoRA-Trainings, YuE2 mit privatem LoRA (Lizenz und private Daten) und die vier Pixaroma-Editoren 3D-Builder, Zuschneiden, Composer und Paint (leer ausgeliefert, ein Lauf ergibt nur eine leere Fläche); sie zeigen nur den Screenshot und einen Hinweis.
- In der **NSFW-Kategorie** sind die Beispiele jugendfrei und zeigen nur eindeutig erwachsene Personen.
