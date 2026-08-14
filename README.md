# DaWasteh – konsolidierte ComfyUI-Workflows · v0.9.2

Dieser Ordner ist jetzt der **kuratierte Hauptordner** für die lokalen Workflows auf Windows 11 mit:

- AMD Radeon AI Pro R9700 (32 GB, RDNA4)
- AMD Radeon RX 9070 XT (16 GB, RDNA4)
- PyTorch/ROCm unter Windows
- ComfyUI aus `L:/ComfyUI`

Die Quellordner `DaWasteh`, `Pixaroma` und `WhatDreamsCost` wurden **nicht verändert**. Vor der Konsolidierung wurde zusätzlich ein Backup der ursprünglichen 59 Workflows erstellt:

`L:/ComfyUI/_workflow_backups/DaWasteh-Neu-before-consolidation-20260725-215010.zip`

Der maschinenlesbare Abschluss-Audit liegt hier:

`L:/ComfyUI/_workflow_backups/DaWasteh-Neu-final-audit-20260725.json`

## Ergebnis

- **239 kuratierte Workflow-Dateien** in 30 Kategorien
- **v0.9.2: Sammlung konsolidiert und nach der „RODENT Method“ organisiert**: Die von YouTuber **Nerdy Rodent** popularisierte Methode gliedert die Graphen in klar beschriftete Funktionszonen, nutzt eine einheitliche Stufen-Farbkodierung und ordnet den Datenfluss kompakt von links nach rechts. Automatisch erzeugte Parameterhinweise liegen gesammelt in `R9 · PARAMETER REFERENCE`, statt den eigentlichen Graphen mit riesigen Abständen auseinanderzuziehen. Sieben rgthree-Workflows behalten aus Funktionsgründen ihre bereits referenzierten Gruppen-IDs/-Titel; die Pixaroma-Group-Demo behält ihre gekoppelte native/Pixaroma-Geometrie. Beide Ausnahmen werden dennoch kompakt beziehungsweise kollisionsfrei ergänzt und ausdrücklich in den Workflow-Metadaten markiert.
- **Optionale GPU-Platzierung direkt in allen 239 Workflows**: Der frühere Ordner `Dual GPU - R9700 + RX 9070 XT` wurde aufgelöst. Jeder kanonische Workflow enthält jetzt genau einen zentralen `DaW Multi-GPU Device Control`-Node. 28 bereits kuratierte Profile behalten ihre bewährte Verteilung; die übrigen 211 starten vollständig auf der R9700 (`gpu:0`). Wo standardisierte ComfyUI-Objekte vom Typ MODEL, CLIP oder VAE vorhanden sind, steuern verbundene offizielle Selector-Nodes die Platzierung. Bei proprietären Custom-Modellobjekten bleibt der Control-Node bewusst passiv, statt eine wirkungslose Umplatzierung vorzutäuschen.
- **Sekunden statt Frame-Rechnen**: Alle 66 Musik-/Video-Generierungsworkflows besitzen jetzt einen dokumentierten Sekundenvertrag. 44 verwenden native Sekundenparameter, zehn folgen der geladenen Audio-/Videodauer und zwölf bisher framebasierte LTX-/WAN-/Kandinsky-/SCAIL-Graphen rechnen eine sichtbare Sekundenangabe über `ComfyMathExpression` in modellgültige Framezahlen um. Die zwölf neuen Umrechnungen sind statisch bis zum jeweiligen Frame-Eingang und zur passenden Ausgabe-FPS geprüft; ein neuer vollständiger GPU-Qualitätslauf aller zwölf Profile ist nicht Teil dieser Layout-/Steuerungsrelease.
- **v0.9.1: MiniMax Music 3 lokal und live geprüft**: Der offizielle Template-basierte FP32-DiT/BF16-Text-to-Music-Workflow enthält nun dieselbe optionale GPU-Steuerung wie die restliche Sammlung; der separate Dual-GPU-Klon entfällt. Single-GPU- und verteilte Belegung wurden mit vier Sekunden Maximaldauer, allen 30 Euler-/Simple-Schritten und tiled DAV decode bis zu nichtleeren 7,988-Sekunden-Stereo-FLACs ausgeführt; der Enhancer lieferte live exakt seine drei Pflichtabschnitte. Ein LoRA-Trainingsworkflow wird bewusst nicht als funktionsfähig ausgeliefert, weil MiniMax keine Trainingsrecipe veröffentlicht hat und ComfyUIs Music-3-DAV decoder-only ist. Details: [docs/MINIMAX_MUSIC3.md](docs/MINIMAX_MUSIC3.md)
- **v0.9.0: vier neue offizielle Template-basierte Video-Workflows**: LTX-2.5 Text-to-Video, Image-to-Video und First/Last-Frame-to-Video verwenden die offiziellen INT8-ConvRot-DiT-/Textencoder; Wan Animate 2 Motion Transfer verwendet den offiziellen INT8-ConvRot-DiT, den vorhandenen FP8-UMT5 und die LightX2V-LoRA. Die vier gepinnten Quelltemplates liegen reproduzierbar unter `tools/workflow_templates/`.
- **v0.8.9: inkrementeller Windows-Updater** unter `tools/update-comfyui-rdna4.ps1`: Er verwendet ausschließlich den echten Klon `L:/GitHub/DaWastehs-ComfyUI-Bundle`, kopiert eigene Workflows und Nodes nur bei geändertem SHA-256-Inhalt, entfernt nur zuvor manifestierte Dateien und erzeugt keine zweite Repository-Kopie mehr
- **alle 7 verbleibenden MiniMax-H3-Workflows** verwenden die empfohlene pruned-ComfyUI-Turbo-LoRA `v4 step-600 EMA` mit dem qualitätsorientierten Profil aus 8 Schritten, Euler, Beta, Video-Sigma 12 und Audio-Sigma 4; zwei redundante FL2VA-All-Inputs-Varianten wurden entfernt, weil `MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json` ihren Funktionsumfang bereits abdeckt
- **2 MiniMax-Guide-basierte H3-Prompt-Enhancer** setzen die vom Nutzer als MiniMax-Ausgabe bereitgestellten Regeln getrennt für Base/FL2VA und Ref2VA um; ein deterministischer Regex-Abschluss entfernt regelwidrige Shot-1-Zeitstempel auch dann, wenn das lokale 4B-LLM sie erzeugt
- **146 Pixaroma Prompt**-Eingaben in 117 gezielt ausgewählten Workflows sowie **9 Pause Text**-Freigaben; insgesamt wurden 120 Workflows sinnvoll erweitert
- 222 Nicht-Live-Workflows enthalten exakt einen `PixaromaRunTimer`; die 17 Live-Avatar-Workflows bleiben auf ausdrücklichen Nutzerwunsch timerfrei
- alle vorhandenen Workflows wurden mit kompakten, kollisionsfreien Abständen angeordnet; acht markierte Group-Control-/Demo-Ausnahmen bewahren absichtlich ihre funktionsrelevanten Gruppentitel oder gekoppelte Geometrie
- **4.910 automatisch zugeordnete Parameter-Notes** erklären jeden Nicht-Pixaroma-/Nicht-Dokumentations-Node einschließlich aktueller Werte, Schalterwirkung, Ein-/Ausgänge und höher-/niedriger-Auswirkung
- 59 vorhandene Workflows beibehalten
- 114 funktional ergänzende Workflows übernommen:
  - 33 aus `DaWasteh`
  - 78 aus `Pixaroma`
  - 3 aus `WhatDreamsCost`
- 2 neue Audio-zu-Video-Workflows aufgebaut: ein klar als AudioReact gekennzeichneter Gemma-/FLUX2-/Pixaroma-Workflow und ein echtes generatives LTX-2.3-Video mit Custom Audio
- 1 neuer Audio-zu-Bild-Workflow: Gemma 4 analysiert das Audio, FLUX.2 Klein 4B erzeugt das Kontextbild, `PixaromaResolution` bietet frei wählbare Formate und `PixaromaNote` dokumentiert Bedienung und Downloads
- 3 grundlegende Live-Avatar-Workflows: SDXL-Quellbild, RMBG-2.0-Freistellung und eine AMD-RDNA4-optimierte Webcam→LivePortrait→RGBA-Spout-Pipeline für OBS
- 1 erweiterter LivePortrait-Webcam→Spout→OBS-Workflow mit gecachter, adapterwechselbarer Qwen3-TTS-Voice-LoRA und Browser-Audio für OBS
- 1 experimenteller Continuous-LivePortrait-Workflow mit Latest-Frame-Capture, persistentem GPU-Composite und kontrolliertem Spout-Dauerbetrieb
- **17 Live-Avatar-Workflows**: die bisherigen Pfade 01–11 plus Workflow 12-I als fail-closed DirectML-Bake-off, 12-II als gemessener LivePortrait-Gesichtsmodus, 12-III als zuverlässiger Browser-VRM-Modus, Workflow 13 als Character-Sheet, Workflow 14 als experimentelle Multiview-Geometrie und Workflow 15 als geprüfter Single-View-High-Realism-Hunyuan3D-GLB-Pfad. Workflow 15 erzeugt ein statisches, untexturiertes und ungeriggtes GLB; die lokale Blender-Postpipeline ist für Rig, Textur und VRM nötig.
- 1 echtes Qwen3-TTS-PEFT-LoRA-Training sowie 1 eigenständiger Low-Latency-Voice-Workflow; ACE-Step bleibt korrekt auf Gesang/Musik beschränkt
- die ausgelieferten YuE-/HeartMuLa-Startwerte wieder mit ihren bestehenden Tests und Bedienhinweisen synchronisiert: YuE CoT nutzt 20 Sektionen für 540 Sekunden, HeartMuLa startet wieder mit 300 Sekunden Obergrenze
- der manifestgesteuerte Pixaroma-Integrator akzeptiert nach der Refinement-Pipeline ausschließlich zusätzliche lokalisierte UI-Labels, Topologie-Reihenfolge und vorhandene Darstellungsfarben, prüft semantische Node-/Link-Zustände aber weiterhin strikt
- 2 neue MOSS-TTS-Local-v1.5-Workflows: Audio + exaktes Transkript + neuer Text als Continuation sowie Text + Audio-Stimmenvorlage als Zero-shot Voice Clone; beide enthalten direkte Downloads und Zielordner
- 3 lokale YuE-/HeartMuLa-Musikworkflows: YuE CoT mit exakter 5–600-Sekunden-Planung, YuE ICL mit optionaler Vocal-/Songreferenz und HeartMuLa mit promptabhängig abgesicherter Dauer bis 600 Sekunden
- 3 zusätzliche INT8-Musikworkflows: YuE 7B bitsandbytes INT8, ACE-Step 1.5 XL SFT INT8 ConvRot und ein lokal aus dem offiziellen Checkpoint erzeugtes Stable Audio 3 Medium INT8 ConvRot
- 4 neue Idee-zu-Songtext-zu-Musik-Workflows: Qwen 3.5 4B und Gemma 4 e4B schreiben aus einer groben Idee strukturierte Lyrics und reichen sie direkt an ACE-Step 1.5 XL oder HeartMuLa weiter
- 7 lokale MiniMax-H3-Workflows: FL2VA, Ref2VA, automatische Audio-/Videolänge sowie ein Complete-Song-Director, der lange Songs seriell in höchstens 15 Sekunden lange H3-Szenen zerlegt. v0.8.4 ergänzte Identity-Lock und unverändertes Originalaudio; v0.8.6 ergänzte Turbo-LoRA und Prompt-Enhancer; v0.8.8 verband die Selector-Pfade mit einer zentralen manuellen GPU-Steuerung. Seit v0.9.2 sitzt diese Steuerung direkt in den kanonischen Graphen; die zwei redundanten FL2VA-All-Inputs-Dateien und die getrennten Dual-GPU-Klone entfallen. Einrichtung und Prüfnachweise: [docs/MINIMAX_H3_TURBO_AND_PROMPTS.md](docs/MINIMAX_H3_TURBO_AND_PROMPTS.md)
- 5 neue lokale Bild-LoRA-Trainingsworkflows mit offiziellen ComfyUI-Core-Trainingsnodes: Z-Image Base, Boogu Image Base, FLUX.1 Dev, FLUX.2 Klein 4B Base und SDXL
- der ACE-Step-1.5-Workflow enthält zusätzlich einen ausführlichen Rank-Guide für Rank 16/32/64/128
- exakte und funktionale Tutorial-Duplikate nicht erneut übernommen
- NVIDIA-/CUDA-exklusive Varianten durch lokale AMD-taugliche Varianten ersetzt oder ausgelassen
- vorhandene Modell- und Input-Referenzen auf die lokale Installation angepasst

## Inkrementelles Update · v0.8.9

Die versionierten Startdateien `tools/update-comfyui-rdna4.ps1` und `tools/update-comfyui-rdna4.bat` gehören nach `L:/ComfyUI/`. Der Batch-Aufruf bleibt unverändert; vor dem Update müssen die ComfyUI-Server auf Port 8188 und 8189 beendet sein.

Der Updater verwendet jetzt den vorhandenen Hauptklon `L:/GitHub/DaWastehs-ComfyUI-Bundle` direkt. Dieser Klon muss vor und nach dem Fast-Forward-Pull sauber sein, damit ausschließlich der eindeutig zu `HEAD` gehörende Inhalt verteilt wird. Der frühere Nebenklon `L:/GitHub/DaWasteh ComfyUI Nodes` wird nicht mehr erzeugt; ein vorhandener alter Klon wird nur dann automatisch entfernt, wenn sein Remote eindeutig dem früheren Repository entspricht und sein Arbeitsbaum einschließlich ungetrackter und ignorierter Dateien vollständig leer ist.

Eigene Inhalte werden inkrementell nach `L:/ComfyUI/ComfyUI/user/default/workflows/DaWasteh` und `L:/ComfyUI/ComfyUI/custom_nodes/` synchronisiert:

- SHA-256-Vergleiche überspringen byte-identische Dateien.
- Nur ersetzte oder entfernte Dateien werden unter `L:/ComfyUI/_update_backups/<Zeitstempel>/` gesichert.
- `L:/ComfyUI/config/dawasteh-bundle-sync-manifest.json` merkt sich ausschließlich die zuletzt aus Git ausgelieferten Dateien. Nur dadurch bekannte, später aus Git entfernte Dateien dürfen im Ziel gelöscht werden; fremde lokale Dateien bleiben unangetastet.
- Requirements eigener Node-Packs werden nur erneut installiert, wenn sich Dateien dieses Packs tatsächlich geändert haben.
- Die Synchronisierung liest jede Datei binär direkt aus den Git-Blobs eines einmal festgehaltenen Commit-Hashes statt aus veränderlichen Arbeitsbaumdateien. Die Validierung vergleicht das Manifest mit genau diesem Commit-Baum, prüft jede ausgelieferte Datei nochmals per SHA-256, liest Workflow-JSON und parst Python-Quelltext ohne `__pycache__` oder `.pyc` zu erzeugen. Kurzlebige Blob-/Validierungsdateien liegen ausschließlich in `%TEMP%` und werden in `finally`-Blöcken entfernt.
- Lexische Pfadgrenzen sowie ein Symlink-/Junction-Verbot in den verwalteten Zielpfaden verhindern, dass Kopier- oder Löschoperationen das vorgesehene Ziel verlassen.
- `ComfyUI-DaWasteh-MultiGPU-Control` ist jetzt Teil des regulären Updates. Nach einem erfolgreichen Pull aktualisiert die versionierte `.ps1`-Datei außerdem ihre installierte PowerShell-Kopie für den nächsten Lauf; der gerade aktive Batch-Launcher wird aus Sicherheitsgründen nicht während seiner eigenen Ausführung überschrieben.

## Ordnerübersicht

| Ordner | Anzahl | Zweck |
|---|---:|---|
| `Text to Image` | 42 | FLUX, Krea2, Z-Image, SDXL, Anima, Boogu, LongCat, Ideogram usw. |
| `LoRA Generation` | 7 | ACE-Step 1.5, echtes Qwen3-TTS-Voice-LoRA sowie lokale Core-Trainer für Z-Image, Boogu, FLUX.1, FLUX.2 Klein und SDXL |
| `Image Editing` | 21 | FLUX2-Klein-Edits, Qwen Image Edit, SDXL-Composites, Bernini |
| `Prompt Tools` | 15 | Prompt Stack/Pack/Multi, Builder, Text-Tools, XY-Plot |
| `Pixaroma Node Demos` | 12 | aktuelle, deduplizierte Pixaroma-Node-Beispiele |
| `Image Utilities` | 12 | Hintergrundentfernung, Combine, Blend, Compare, Filter, Scale, Lama |
| `Text+Image to Video` | 12 | WAN, LTX Director, LTX-2.5 Image-/First+Last-Frame, Custom Audio und Kandinsky |
| `Reference to Video` | 7 | MiniMax H3 FL2VA, Ref2VA, AutoLength und Complete-Song-Director; alle mit v4-Step-600-EMA-Turbo-LoRA |
| `Prompt Enhancer` | 14 | Gemma/Qwen Prompt-, Bild-, Audio- und Videoverständnis, MiniMax Music 3 Official-Skill-Caption-Enhancer sowie getrennte H3-Base-/Ref2VA-Enhancer |
| `Music Generation` | 31 | MiniMax Music 3, ACE-Step, Stable Audio 3, YuE CoT/ICL, HeartMuLa, drei INT8-Varianten sowie Qwen-/Gemma-Idee-zu-Lyrics und AutoSongwriter-Presets |
| `Voice Design` | 11 | Qwen3-TTS einschließlich wechselbarer PEFT-LoRA-Stimmen sowie MOSS-TTS Local v1.5: Custom Voice, Continuation, Clone und Dialog |
| `Text to Video` | 6 | LTX 2.3, LTX 2.5 INT8 ConvRot und WAN 2.2 |
| `Audio to Video` | 3 | zwei AudioReact-Varianten sowie echtes generatives LTX-2.3-Bild+Audio→Video in Soundlänge |
| `Audio to Image` | 1 | Gemma-4-Audioverständnis → visueller Prompt → FLUX.2-Klein-4B-Kontextbild |
| `NSFW` | 4 | getrennte SDXL-NSFW-/AniToReal-Workflows |
| `Character & Consistency` | 3 | FLUX Kontext und SDXL/IPAdapter Character Keep |
| `Character Animation` | 4 | SCAIL-2 Animation/Replacement sowie Wan Animate 2 Motion Transfer |
| `Live Avatar` | 17 | 2D-Quellbilder, LivePortrait-/Spout-Pfade, Browser-VRM, DirectML-Bake-off, Character-Sheets sowie lokale Hunyuan3D-GLB-Geometrie mit geprüftem Single-View-High-Realism-Pfad |
| `Image Inpainting` | 3 | FLUX2 Klein 4B/9B Inpainting |
| `Image Upscaling` | 3 | einfache, Modell- und Z-Image-Upscaler |
| `Batch Processing` | 2 | Ordner-Batches und Batch-Image-Edit |
| `weitere 9 Einzelordner` | 9 | jeweils 1 Workflow: Controlled Video, Image Fusion, 3D, Outpainting, Talking Video, Tests, Video Editing, Video-to-Audio, Vocal Separation |

## Live Avatar · v0.8.5

**Ausführliche Einrichtung, Drei-Bilder-Avatar-Erstellung, Workflow-12-Benchmark, OBS-Schritte und Fehlerbehebung:** [LIVE_AVATAR_ANLEITUNG.md](LIVE_AVATAR_ANLEITUNG.md)

v0.8.5 optimiert beide vom Nutzer gewählten Modi, ohne ihre Fähigkeiten gleichzusetzen. Der produktive 24+-FPS-Pfad bleibt das lokal gerenderte High-Realism-VRM: MediaPipe verarbeitet nur neue Kameraframes, der Renderer zeigt getrennte Tracking-/Render-FPS an, und der neue adaptive Bildausschnitt richtet den Avatar an sichtbaren Schulter-/Hüft-/Beinankern aus. Wenn Kopf oder Beine die Webcam verlassen, werden sie dadurch auch aus dem Avatarbild geschoben; verlorene Gesichts-, Körper-, Blick- und Ausdrucksziele laufen statt einzufrieren kontrolliert zur Modellruhe zurück. Der Buffered AI Mirror 07/11 bleibt fotonäher, aber langsam. Er vermeidet jetzt ungefragtes OpenPose-Diagnose-JSON, überträgt RGBA in einem GPU→CPU-Schritt und schreibt echte Produktions-, Präsentations- und Duplikatmetriken. Zwei ComfyUI-Server poolen keinen VRAM und beschleunigen diesen seriellen Graphen nicht; Workflow 06 benötigt nur 8188.

Der sichtbare v0.8.5-Browser-Test verwendete einen 30-FPS-Full-Body-Tanzclip und danach einen echten Torso-/Teilbild-Crop als lokale Fake-Webcam. Das damalige High-Realism-v2-Modell erreichte 30,1/29,8 Tracking-FPS und 64,3/73,6 Render-FPS bei 1264×625 Backing-Auflösung; der zweite Screenshot zeigt den Avatar passend vergrößert und am Bildrand abgeschnitten statt weiterhin als fixes Ganzkörperportrait. Nach der sichtbaren Nutzerabnahme wurde v5 ergänzt: Es behält das stabile v2-Körperrig, bindet aber ein alpha-gefedertes Gesichtsdetail aus dem Original `L:/ComfyUI/ComfyUI/input/liveavatar-img-00031.png` an den Kopfknochen und versieht es mit eigenen Blink-/Vokal-Morphs. Im Browser blieb der Durchsatz mit 30,0 Tracking-FPS und ungefähr 59–75 Render-FPS klar über dem 24-FPS-Ziel. Das ist frontal deutlich quelltreuer, bleibt aber ehrlich ein hybrides VRM0 und keine vollständige volumetrische Portraitrekonstruktion; extreme Profile sind weniger exakt. Anatomische Gelenklimits, begrenzte Rotationsgeschwindigkeit und eine ruhigere Standardglättung reduzieren zugleich ruckartige Extrembewegungen.

Workflow 11 lief nach 22,5–29,0 s Kaltstart überwiegend in 0,61–0,68 s warm; ein einzelner Abnahmelauf lag bei 0,87 s. Ein unabhängiger Spout-Empfänger bestätigte 384×384 RGBA, Alpha 255, nichtleere Pixel und wechselnde Pixelhashes. Zusätzlich wurde eine isolierte OBS-Testszene wirklich aufgenommen: 20,03 Sekunden MKV, 1280×720 bei 30 FPS; währenddessen liefen vier neue Workflow-07-Frames, und 40 bei 2 Hz dekodierte Videostichproben ergaben 18 unterschiedliche Hashes. Die temporäre OBS-Szene, das Testprofil und die vorübergehende WebSocket-Freigabe wurden danach entfernt beziehungsweise auf die vorherige Konfiguration zurückgesetzt.

Siebzehn aufeinander aufbauende Workflows unter `workflows/Live Avatar/` bilden die lokale Teststrecke. Die Capability-Tiers bleiben getrennt: **2D-Referenzgenerierung** (01/10), **Buffered AI Mirror** (07/11) und **tatsächlich geriggtes Browser-VRM** (06); ein PNG ist niemals automatisch ein VRM:

1. `LiveAvatar-01-SDXL-Avatar-Generation.json` erzeugt mit dem bereits vorhandenen RealVisXL V4 ein frontales 1024×1024-Quellbild.
2. `LiveAvatar-02-RMBG-Transparency.json` entfernt mit RMBG-2.0 den Hintergrund und speichert ein PNG mit Alphakanal.
3. `LiveAvatar-03-LivePortrait-Webcam-Spout-OBS.json` übernimmt Mimik und Kopfbewegung aus `WebcamCaptureCV2`, setzt nur den animierten Gesichtsbereich in das statische Quellbild ein, stellt dessen ursprünglichen Alphakanal wieder her und sendet RGBA als `ComfyLiveAvatar` über Spout. Es bleibt der stabile Queue-basierte Fallback.
4. `LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA.json` ergänzt den stabilen Queue-Pfad um die lokale Qwen3-TTS-Voice-LoRA-Ausgabe.
5. `LiveAvatar-05-LivePortrait-Continuous-Spout-OBS.json` ist ein separates Experiment mit `ComfyUI-DaWasteh-LiveAvatar`: Capture und Spout laufen als Latest-Frame-Worker, während alle Torch-/ROCm-Schritte im Comfy-Ausführungsthread bleiben. Einmal normal **Run** starten, mit **Interrupt** stoppen und ausdrücklich nie **Run (Instant)** verwenden. Der Sender heißt `ComfyLiveAvatarFast`; OBS verwendet Composite Mode `Default`. Der Node animiert ausschließlich das Gesicht und blockiert während seiner Laufzeit andere ComfyUI-Jobs. Auf der R9700 stieg der warme Durchsatz gegenüber dem Queue-Fallback von rund 1,29 auf 7,3–7,9 neue Frames/s; ein separater SpoutGL-Empfänger erhielt 1024×1024-RGBA mit Alphaextrema `(0,255)` und wechselnden nichtleeren Frames.

6. `LiveAvatar-06-VRM-Full-Body-Hand-Face+Live-Mic.json` startet einen lokalen Browser-Renderer mit MediaPipe-Holistic-Tracking und VRM. Der Launcher wählt lokal standardmäßig `dawasteh-img00031-highrealism-local-v5.vrm`, aktiviert den adaptiven Webcam-Bildausschnitt und kann Modell, Chroma und Präsentationsmodus direkt im einen ComfyUI-Workflow festlegen. MediaPipe wird über `requestVideoFrameCallback` nur für neue Webcamframes aufgerufen; eine FPS-Zeile trennt Trackingupdates von WebGL-Renderframes und nennt die echte Backing-Auflösung. Full-HD wird nicht unnötig über die OBS-Ausgabe hinaus supersampelt. Wenn Landmarks verschwinden, fallen Gesicht, Blick, Mund, Torso, Arme, Beine und Hände kontrolliert zur Ruhe zurück. Die Presets werden per `python tools/install_live_avatar_vrm_models.py --comfy-root L:/ComfyUI/ComfyUI` installiert. Der separate DirectML-RVC-Begleiter funktionierte auf der RX 9070 XT mit einem vertrauenswürdig gepinnten Testmodell und anschließendem app-eigenem ONNX-Export warm mit etwa 36–41 ms Rechenzeit pro 100-ms-Chunk; er ist ausdrücklich nicht Qwen-TTS/Voice-LoRA.
7. `LiveAvatar-07-AI-Webcam-Character-Swap-Experimental.json` ist auf diesem Rechner ein **Buffered AI Mirror**, kein Livepfad: Webcam → OpenPose → SD1.5-LCM Img2Img + IPAdapter-Referenz. Auf 8188/R9700 ergaben wiederholte warme Serien etwa 2,0–2,8 Sekunden pro Frame (rund 0,36–0,50 FPS); 8189/RX 9070 XT erreichte nur rund 0,125 FPS. v0.8.5 hält die Bildqualität unverändert, überträgt vorhandene RGBA-Ausgaben aber in einem statt zwei GPU→CPU-Schritten. Echte AI-Produktion und wiederholte 30-Hz-Spout-Präsentationen werden getrennt über den portablen relativen Pfad `live-avatar-07/metrics.json` im lokalen ComfyUI-Log-Root gezählt. Der reparierte Webcam-Node verwendet die Logitech BRIO ausdrücklich über DirectShow-Index 2. `tools/install_live_avatar_ai_assets.py` installiert nur gepinnte Safetensors nach Stoppen von Run (Instant) und bei leerer Queue. Für Audio bleibt DirectML-RVC auf der RX 9070 XT getrennt; 8189 währenddessen nicht mit schweren Jobs belasten.

11. `LiveAvatar-11-AI-Webcam-Character-Swap-Cached-OpenPose.json` ist die separate Geschwindigkeitsvariante und verändert Workflow 07 nicht. `DaWastehCachedOpenPose` hält die OpenPose-Gewichte nach dem Kaltstart auf der R9700. Das Standard-Speed-Preset nutzt 384×384, Körper+Gesicht und deaktivierte Handerkennung; vier LCM-Schritte sowie ControlNet-/IPAdapter-Stärken bleiben erhalten. Unverknüpftes, eingerücktes OpenPose-Diagnose-JSON ist in v0.8.5 standardmäßig deaktiviert und nur noch explizit zuschaltbar. Die ehrlichen Laufzeitmetriken liegen portabel unter `live-avatar-11/metrics.json` relativ zum lokalen ComfyUI-Log-Root. Die bisherige Messung bleibt 0,62–0,68 Sekunden warm, Median 0,645 Sekunden beziehungsweise rund 1,55 neue Bilder/s; der neue Live-Test muss davon getrennt dokumentiert werden. Das ist weiterhin ein gepufferter AI Mirror, kein flüssiges Mocap; Handerkennung kann für mehr Pose-Detail auf Kosten von ungefähr einer halben Sekunde wieder aktiviert werden.

`LiveAvatar-08-Local-VRM-Texture-Creator-Realistic+Stylized.json` ist der lokale, creditfreie Template-Weg: drei lizenzierte/einvernehmlich bereitgestellte Bilder derselben klar erwachsenen Person – empfohlen frontal, Dreiviertelansicht und Profil – werden als gleich gewichteter IPAdapter-Referenz-Batch mit einem Prompt kombiniert. Ein bestehendes lizenziertes VRM0 mit genau einer eingebetteten Basisfarbtextur liefert Rig, Finger und Morphs; Mehrtextur-Basen werden sicher abgelehnt und vorhandenes Textur-Alpha bleibt erhalten. Ausschließlich die UV-Basistextur wird lokal per SD1.5/LCM/IPAdapter umgestaltet. Der Speichern-Node bleibt zunächst stumm: erst die flache UV-Vorschau prüfen, danach bewusst aktivieren und die neue, in Workflow 06 auswählbare VRM0-Variante zusätzlich am gerenderten 3D-Modell kontrollieren. Das ist eine erscheinungs-/ähnlichkeitsgeführte Texturvariante, keine Identitätsrekonstruktion: Körpergeometrie, Körperform, Rig und UV-Inseln bleiben vom Basismodell begrenzt. `LiveAvatar-09-Meshy-AutoRig-to-VRM-Candidate-Optional-Cloud.json` ist ein ungetesteter, kostenpflichtiger Meshy-Kandidat: Referenz und Modell verlassen dabei den Rechner; der strikte Konverter akzeptiert nur ein tatsächlich vollständiges Rig inklusive Fingerketten und Gesichtsmorphs und verspricht keine direkte VRM-Erzeugung durch Meshy. `LiveAvatar-10-Realistic-Adult-Character-Reference-Prompt+Image.json` erzeugt lokal mit dem tatsächlich installierten RealVisXL V4 drei wählbare bekleidete erwachsene 2D-Presets und einen strikt prompt-only, klar erwachsenen, neutralen nicht-expliziten Akt. Ein lizenziertes/einvernehmliches Portrait kann ausschließlich den bekleideten IPAdapter-Zweig beeinflussen; der separate Akt-Sampler ist direkt mit dem Checkpoint verbunden. Workflow 10 erzeugt Referenz-PNGs, kein Mesh, Rig oder VRM.

Für die Radeon AI Pro R9700 sind LivePortrait `fp16` und FaceAlignment mit `landmarkrunner_device = torch_gpu` voreingestellt. BlazeFace erkennt das Gesicht kompatibel auf der CPU; das Landmark-TorchScript und LivePortrait selbst laufen auf der R9700. Der MediaPipe-Pfad bleibt bewusst ungenutzt, weil die installierte Python-3.13-Ausgabe nicht mehr das von diesem älteren Node erwartete `mediapipe.framework` bereitstellt. Der aktuelle LivePortraitKJ-Node nennt den früher oft als `crop_factor` beschriebenen Regler `scale`; `2.30` fokussiert den Kopf, während `LivePortraitComposite` Kleidung und Hände stabil aus dem Quellbild übernimmt. Ein normaler ComfyUI-Graph verarbeitet nur ein Webcam-Frame pro Queue-Ausführung: Für fortlaufende Bewegung muss beim Fallback-Workflow 03 **Run (Instant)** verwendet werden – das ist der aktuelle Name der in den älteren Workflow-Notizen als „Auto Queue“ bezeichneten Funktion; der Spout-Writer sendet das jeweils letzte fertige RGBA-Frame mit 30 FPS weiter. Workflow 05 benötigt dagegen genau einen normalen Run und läuft bis zum Interrupt.

Installiert wurden `ComfyUI-LivePortraitKJ` und `Jovi_Spout`. Die sechs Human-LivePortrait-Dateien liegen unter `L:/ComfyUI/ComfyUI/models/liveportrait/`, RMBG-2.0 unter `models/RMBG/RMBG-2.0/`. Der Webcam-Node war bereits in ComfyUI-KJNodes vorhanden und wurde um eine explizite Windows-Backend-Auswahl ergänzt. Die Indizes sind backendabhängig: Unter DirectShow sind Elgato Virtual Camera/Facecam Pro/Logitech BRIO/OBS Virtual Camera derzeit 0/1/2/3; unter MSMF ist die BRIO Index 0 und Elgato Virtual Camera Index 1. Workflows 07 und 11 wählen deshalb stabil `DirectShow` + Index 2 für die BRIO. Das Windows-[Spout2-Plugin 1.12.0](https://github.com/Off-World-Live/obs-spout2-plugin/releases/tag/1.12.0) liegt auf dieser OBS-Installation unter `C:/ProgramData/obs-studio/plugins/win-spout/`. Ein separater SpoutGL-Empfänger hat nach dem vollständigen LivePortrait-Lauf das nichtleere 1024×1024-RGBA-Frame des Senders `ComfyLiveAvatar` empfangen; in OBS muss nach einem Neustart nur noch die Spout2-Quelle mit diesem Namen gewählt und Alpha aktiviert werden.

PyTorch 2.6+ lädt den von Kijai bereitgestellten `landmark_model.pth` standardmäßig nicht mehr als serialisiertes `torch.fx`-Modul. `tools/convert_liveportrait_landmark.py` prüft deshalb vor dem einmaligen vollständigen Laden zuerst die bekannte Upstream-SHA-256-Prüfsumme `48ba55140fda4c292d3faf3e3ed9106784c7c32aebf170d4983fb67cd0a3c9c8` und erzeugt daraus das eigenständige `landmark_model_torchscript.pt`. Die Konvertierung ist bytegenau auf Torch `2.12.0+rocm7.15.0a20260727`, onnx2torch `1.5.15`, ONNX `1.22.0` und Protobuf `5.29.6` festgelegt und vergleicht zwei deterministische Testeingaben numerisch mit dem Quellmodell. Diese einmaligen Konvertierungsabhängigkeiten gehören in eine Wegwerf-Umgebung, nicht in das produktive ComfyUI. Der Runtime-Patch lädt nur das fertige TorchScript nach Prüfung seiner SHA-256-Prüfsumme `9064565b92b3595786096b36acd24709c7bd290631510517bd3a9d5ca8f28a43`; dadurch werden weder `onnx2torch` noch eine Änderung der vorhandenen Protobuf-Version im laufenden ComfyUI benötigt. Der reproduzierbare Diff liegt unter `tools/patches/ComfyUI-LivePortraitKJ-PyTorch-2.6-verified-landmark-load.patch`; ein Update des Custom Nodes kann den lokalen Fix überschreiben. Der erfolgreiche FaceAlignment-Erstlauf legte zusätzlich `2DFAN4-cd938726ad.zip` (`cd938726…`), `blazefaceback.pth` (`e2c03bb3…`) und `anchorsback.npy` (`a10bb2fb…`) im Torch-Checkpoint-Cache ab.

Der reproduzierbare KJNodes-Kompatibilitätspatch `tools/patches/ComfyUI-KJNodes-WebcamCaptureCV2-Windows-Backend.patch` erhält den Queue-sicheren `IS_CHANGED`-Hook, ergänzt `auto`/`DirectShow`/`Media Foundation`, gibt fehlgeschlagene Captures zur Wiederöffnung frei, verbessert die Diagnose um Index und Backend und normalisiert die Ausgabe auf die angeforderte Bildgröße. Ein Custom-Node-Update kann diesen lokalen Patch überschreiben.

Die Upstream-`requirements.txt` von LivePortraitKJ und Jovi_Spout dürfen in dieser Python-3.13-/ROCm-Installation **nicht blind vollständig installiert** werden: sie würden NumPy auf `<2` absenken und LivePortrait zusätzlich einen nicht benötigten GPU-ONNX-Pfad einziehen. Installiert wurden nur die tatsächlich benötigten, Python-3.13-kompatiblen Pakete; `cozy_comfyui` ist lokal auf Commit `6f37572d41a4124f406c1d1f33b61f0fd56b4d99` festgelegt. `pip check` bleibt wegen der bereits zuvor vorhandenen Protobuf-3.19.6-Konflikte anderer ComfyUI-Nodes nicht global sauber; die hier ausgelieferte TorchScript-/FaceAlignment-Pipeline verwendet diesen Konfliktpfad nicht.

## Qwen3-TTS Voice-LoRA · v0.7.0

v0.7.0 korrigiert die ComfyUI-Validierung des numerisch aussehenden `lora_rank`-Dropdowns: Rank 8/16/32/64 werden als stabile String-Auswahl gespeichert und vor PEFT kontrolliert in Integer umgewandelt. Zusätzlich erkennt der Trainer neben `<audio-stem>.txt` jetzt auch das verbreitete Schema `<audio-stem>_Text.txt` und liest UTF-8-Dateien BOM-tolerant.

ACE-Step-Voice-LoRAs konditionieren eine **Gesangs-/Musikgenerierung** und sind deshalb nicht die richtige Technik für eine sprechende Live-Avatar-Stimme. v0.6.9 ergänzte stattdessen `custom_nodes/ComfyUI-DaWasteh-Qwen3TTS-LoRA/` mit zwei lokal installierten Nodes:

- `DaWastehQwen3TTSLoRATrain` trainiert einen echten PEFT-LoRA-Adapter plus die benötigte Sprecher-Einbettung.
- `DaWastehQwen3TTSLoRAInference` listet vollständige Adapter unter `models/qwen-tts/loras/` im Dropdown auf, lädt sie ausschließlich aus Safetensors/JSON und erlaubt einen skalierbaren Wechsel zwischen lokalen Stimmen.

`Qwen3-TTS_0.6B-Voice-LoRA-Training.json` erwartet Audio-/UTF-8-Transkriptpaare nach dem Schema `<name>.wav` + `<name>.txt` oder `<name>.wav` + `<name>_Text.txt` unter `ComfyUI/input/qwen3tts_lora/my_voice/`. Der AMD-Sicherstart ist 0.6B, BF16, SDPA, Batch 1, Gradient Accumulation 4, Rank 16/Alpha 32, Lernrate `2e-6` und zunächst genau eine Epoche. Eingangsaudio wird vor dem Training auf 24 kHz Mono normalisiert. Checkpoints landen als `adapter_model.safetensors`, `adapter_config.json`, `speaker_embedding.safetensors` und Metadaten unter `ComfyUI/models/qwen-tts/loras/<stimme>/checkpoint-epoch-N/`. Der ebenfalls unterstützte 1.7B-Pfad ist qualitativ stärker, aber langsamer.

`Qwen3-TTS_LoRA-Low-Latency-Live-Voice.json` erzeugt aus Text eine vollständige 24-kHz-Sprachdatei, spielt geänderte Ausgaben mit `PlaySoundKJ` einmal im Browser und speichert zusätzlich FLAC. `LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA.json` fügt denselben Voice-Zweig zur bewährten FaceAlignment→LivePortrait→RGBA-Spout-Pipeline hinzu. Für OBS wird das ComfyUI-Browser-/Anwendungsaudio aufgenommen oder über ein bereits vorhandenes virtuelles Audiokabel geroutet; Spout selbst transportiert nur Video. Unveränderte TTS-Eingaben bleiben im Auto-Queue-Betrieb gecacht und `on_change` verhindert eine Wiederholung pro Webcam-Frame.

Die ComfyUI-Integration ist bewusst als **Low-Latency/request-basierte TTS** bezeichnet: Der Node liefert einen vollständigen Clip nach einem Queue-Lauf, aber keinen kontinuierlichen Mikrofon-Voice-Changer. Nach neuem Training den Inference-Node mit `R` aktualisieren, Adapter, `speaker_name` und passende 0.6B-/1.7B-Basis wählen und LoRA-Skalen 0.20/0.30/0.35/0.50 vergleichen. Stimmen dürfen nur mit Eigentum oder ausdrücklicher Einwilligung geklont werden.

Das fehlende 0.6B-Base-Modell wurde nach `L:/ComfyUI/ComfyUI/models/qwen-tts/Qwen3-TTS-12Hz-0.6B-Base/` geladen; der 12-Hz-Tokenizer war bereits vorhanden. Als Laufzeit-Voraussetzung muss `qwen3-tts-comfyui` oder `ComfyUI-Qwen-TTS` installiert sein. `tools/install_qwen3_tts_lora_node.py` prüft diese Laufzeit, installiert die begrenzten PEFT-/Audio-Abhängigkeiten mit dem Ziel-ComfyUI-Python und kopiert den Node-Pack nur nach Run (Instant) stoppen und bei leerer Queue. Die Implementierung übernimmt die korrigierte Label-Verschiebung, Textprojektion, PEFT-Zielmodule und Scale-Empfehlungen aus dem Apache-2.0-Projekt [cheeweijie/qwen3-tts-lora-finetuning](https://github.com/cheeweijie/qwen3-tts-lora-finetuning); die offizielle Qwen-Implementierung bietet ansonsten nur Full-SFT.

## Pixaroma Prompt-Bibliothek · v0.6.4

`prompt-libraries/DaWasteh-Pixaroma-Prompt-Library.json` ist eine persönliche, importierbare Bibliothek für **Prompt Pixaroma**. Im Node `Tags` öffnen und die Datei importieren. `@tag` fügt einen gespeicherten Textbaustein ein, `*Kategorie` zieht bei jedem Lauf einen Baustein aus einer Kategorie und `#liste` zieht eine Zeile aus einer Listenkarte. Die Wahlmodi Shuffle, Random und In order stehen im Tags-Editor bereit; **Show expanded** zeigt den tatsächlich gesendeten Prompt.

Die Bibliothek trennt Bild/Video, Musik, Voice-Direction, Branding (DaWasteh, Pandaking, Draygh, Stella), explizit erwachsene einvernehmliche Inhalte und Negativ-Tags. Zufallslisten enthalten keine Adult- oder Negative-Tags. Der queue-sichere Installer `python tools/install_pixaroma_prompt_library.py` installiert nur in eine leere lokale Bibliothek; eine bestehende Library wird ohne `--replace` nie überschrieben. Er wird absichtlich nicht automatisch ausgeführt.

**Pause Text** liegt nur hinter ausgewählten `TextGenerate`-Ausgaben, die anschließend Bild-, Video- oder Audiogenerierung konditionieren: Pause zeigt und stoppt, Continue nutzt den korrigierten Text ohne das LLM erneut auszuführen, Pass läuft ohne Stopp durch und Keep wiederholt mit dem freigegebenen Text. Negative Prompts, Systemformeln, Lyrics, TTS-Sprechtexte, Referenztranskripte, Utilities, Demos und Training bleiben bewusst unverändert.

Prompt-Tag-Expansion und Pause/Continue/Keep sind Browser-Funktionen von ComfyUI-Pixaroma. Reine API-/Headless-Läufe expandieren keine private `@`/`*`/`#`-Library und können keine interaktive Pause bedienen; dafür einen normalen String-Eingang verwenden.

## Benennung

Die bestehende englische Ordnerstruktur wurde beibehalten und logisch erweitert. Neue Dateien folgen möglichst diesem Schema:

`MODEL_VARIANTE-Funktion.json`

Korrigierte vorhandene Namen:

- `LLM_Gemma3_12B_abliterated_...` → `LLM_Gemma4_e4b_abliterated_...`  
  Der Workflow lädt tatsächlich Gemma 4 e4b.
- `FLUX2_dev_fp8mixed_NEW-...` → `FLUX2_dev_fp8mixed_v2-...`

## Lokales LoRA-Training auf RDNA4

Die fünf neuen Bildtrainer verwenden ausschließlich die **offiziellen experimentellen ComfyUI-Core-Nodes** `LoadImageTextDataSetFromFolder`, `MakeTrainingDataset`, `ResolutionBucket`, `TrainLoraNode`, `LossGraphNode` und `SaveLoRA`. Es wird keine zusätzliche CUDA-Trainer-Extension benötigt.

- Trainingsdaten liegen unter `ComfyUI/input/lora_training/<modell>/`; jedes Bild erhält eine gleichnamige `.txt`-Caption.
- Alle neuen Trainer starten absichtlich mit **2 Schritten** und einem `_smoke`-Dateiprefix. Erst nach erfolgreichem Loss-/Datei-Test auf den gewünschten Schrittwert erhöhen und `_smoke` entfernen.
- Standard ist Rank 16, BF16, Batch 1, Gradient Accumulation 4, Gradient Checkpointing und Resolution Buckets.
- `SaveLoRA` schreibt nach `ComfyUI/output/loras/DaWasteh/`. Fertige Adapter anschließend nach `ComfyUI/models/loras/DaWasteh/` kopieren.
- FLUX.1 Dev nutzt wegen des vorhandenen FP8-Modells den quantisierten Bypass-Rückwärtsweg und ist im Workflow ausdrücklich als experimentell markiert.
- Alle für diese fünf Workflows benötigten Basismodelle, Textencoder und VAEs waren bereits in `L:/ComfyUI/ComfyUI/models` vorhanden; es mussten keine zusätzlichen Gewichte heruntergeladen werden.

**Krea 2 RAW wurde nach einem reproduzierbaren OOM auf der R9700 trotz aktiviertem Offloading wieder entfernt.** Das 24,5-GB-BF16-Modell zusammen mit Textencoder und Trainingszustand überschreitet die sichere 32-GB-VRAM-/48-GB-RAM-Grenze dieses Systems. Entsprechend der Stabilitätsregel wird kein Workflow ausgeliefert, der auf der Zielhardware nicht sicher nutzbar ist.

Für Qwen3-TTS steht ab v0.6.9 zusätzlich zum vorhandenen experimentellen Full-Finetuning der separate, lokal smoke-getestete PEFT-LoRA-Pfad zur Verfügung. Bewusst nicht als lokale RDNA4-LoRA-Trainer aufgenommen wurden weiterhin LTX-2 (offizieller Trainer verlangt CUDA/Triton), WAN 2.x (kein offizieller Herstellertrainer), HunyuanVideo/CogVideoX (kein bestätigter gfx1201-Pfad), Stable Audio 3 (kein passender ComfyUI-Core-Datasetpfad) sowie MOSS-TTS Local v1.5. OpenMOSS dokumentiert für Local v1.5 Full-SFT, aber keinen allgemeinen v1.5-LoRA-Pfad; das vorhandene Community-LoRA-Beispiel zielt auf das ältere 8B-Modell, und der verwendete ComfyUI-v1.5-Node kann keine LoRAs trainieren oder laden.

## Idee → Songtext → Musik · v0.6.6

Vier neue Workflows unter `workflows/Music Generation/` kombinieren die native ComfyUI-`TextGenerate`-Node mit den vorhandenen Musikmodellen:

- `ACE-Step1_5_XL_SFT_Qwen3_5_4B-Idea-to-Lyrics-to-Music.json`
- `ACE-Step1_5_XL_SFT_Gemma4_e4B-Idea-to-Lyrics-to-Music.json`
- `HeartMuLa_HappyNewYear_3B_Qwen3_5_4B-Idea-to-Lyrics-to-Music.json`
- `HeartMuLa_HappyNewYear_3B_Gemma4_e4B-Idea-to-Lyrics-to-Music.json`

Im ersten grünen Node wird nur die grobe Songidee eingetragen; Sprache, Handlung, Stimmung und Perspektive dürfen frei formuliert werden. Ein getrennter grüner Tags-Node steuert Genre, Stimme, Instrumentierung und Produktion. Qwen 3.5 4B beziehungsweise Gemma 4 e4B erzeugen singbare Lyrics mit Markern wie `[Verse 1]`, `[Chorus]` und `[Bridge]`. Ein Core-`RegexReplace` entfernt bei Bedarf internen Denktext oder eine Präambel; `PixaromaShowText` zeigt nur den bereinigten Songtext an und reicht ihn ohne Copy-and-paste direkt an ACE-Step oder HeartMuLa weiter.

Beide LLM-Varianten verwenden lokal vorhandene Textencoder aus `ComfyUI/models/text_encoders/Qwen/` beziehungsweise `ComfyUI/models/text_encoders/Gemma/`. Die Workflows enthalten die direkten Hugging-Face-Downloads und Zielordner in ihrer Bedienungs-Note. ACE-Step startet mit 210 Sekunden; HeartMuLa nutzt 210 Sekunden als Obergrenze und kann bei Audio-EOS früher enden.

## INT8-Musikvarianten

Drei zusätzliche Workflows unter `workflows/Music Generation/` verwenden echte 8-Bit-Gewichte:

- `YuE_7B-INT8_R9700-Music-Generation.json`: Community-bitsandbytes-INT8 für Stage 1 und Stage 2; XCodec und Upsampler bleiben in Originalpräzision.
- `ACE-Step1_5_XL_SFT_INT8_ConvRot-Music-Generation.json`: nativer Comfy-INT8-ConvRot-Checkpoint von `hrktxz`; `weight_dtype=default` liest die eingebetteten Quantisierungsmetadaten.
- `StableAudio3_Medium_INT8_ConvRot-Audio-Generation.json`: lokal mit `Comfy-Org/comfy-model-tools` aus dem offiziellen Medium-Checkpoint erzeugt; 192 DiT-Linear-Layer sind INT8 ConvRot, der Audio-VAE bleibt BF16.

Die Modelle liegen lokal unter `L:/ComfyUI/ComfyUI/models/yue/`, `models/diffusion_models/ACE/` und `models/checkpoints/StableAudio/`. Die Workflow-Notes enthalten Quellen, Zielpfade und SHA-256-Prüfsummen. Auf dieser Windows-ROCm-Installation läuft Comfy INT8 ohne Triton über den Eager-Fallback; dadurch sinkt der Modell-/VRAM-Bedarf, ein Geschwindigkeitsgewinn ist aber nicht garantiert. YuE verwendet separat bitsandbytes; dessen ROCm-7.14-Wheel-Fallback wurde auf gfx1201 mit einer INT8-Matrixmultiplikation geprüft.

## YuE und HeartMuLa · v0.6.3

Die Musikworkflows benötigen zwei lokale Custom-Node-Patches aus `tools/patches/`:

- `ComfyUI_YuE-Windows-RDNA4-longform-ICL.patch`: SDPA statt Flash-Attention, kein TorchInductor auf Windows-ROCm, robuste MMGP-Profilvalidierung, verlustfreie WAV-Zwischenstufen, exakte 5–600-Sekunden-Tokenplanung und ein optionaler ComfyUI-`AUDIO`-Eingang für ICL-Referenzen.
- `ComfyUI-HeartMuLa-600s-context.patch`: erweitert `duration_seconds` auf 600 und prüft vor dem GPU-Lauf, wie viel Audio neben den aktuellen Lyrics/Tags in den 8192-Positionen-Kontext passt.

Die Patches werden jeweils im Root des passenden Custom-Node-Repositories angewendet; vorher mit `git apply --check` prüfen. Beispiel:

```powershell
git -C "L:/ComfyUI/ComfyUI/custom_nodes/ComfyUI_YuE" apply --check "<dieser-clone>/tools/patches/ComfyUI_YuE-Windows-RDNA4-longform-ICL.patch"
git -C "L:/ComfyUI/ComfyUI/custom_nodes/ComfyUI_YuE" apply "<dieser-clone>/tools/patches/ComfyUI_YuE-Windows-RDNA4-longform-ICL.patch"
git -C "L:/ComfyUI/ComfyUI/custom_nodes/ComfyUI-HeartMuLa" apply --check "<dieser-clone>/tools/patches/ComfyUI-HeartMuLa-600s-context.patch"
git -C "L:/ComfyUI/ComfyUI/custom_nodes/ComfyUI-HeartMuLa" apply "<dieser-clone>/tools/patches/ComfyUI-HeartMuLa-600s-context.patch"
```

Der separate Referenzstimmen-Workflow verwendet den zusätzlichen ICL-Checkpoint:

```powershell
hf download m-a-p/YuE-s1-7B-anneal-en-icl --local-dir "L:/ComfyUI/ComfyUI/models/yue/YuE-s1-7B-anneal-en-icl"
```

Lokaler Zielordner: `L:/ComfyUI/ComfyUI/models/yue/YuE-s1-7B-anneal-en-icl`

**YuE-Einstellungen unterscheiden sich bewusst:** Ohne Referenz den CoT-Workflow mit `...en-cot` und beiden Audio-Prompt-Schaltern AUS verwenden. Mit Referenz den ICL-Workflow mit `...en-icl`, verbundenem `reference_audio`, `use_audio_prompt=True` und vorzugsweise etwa 30 Sekunden isoliertem Gesang/Chorus verwenden. Ein kompletter Mix überträgt zusätzlich Arrangement und Instrumentierung; ICL ist Stil-/Audio-Conditioning, keine garantierte identische Voice-Clone-Engine.

HeartMuLa OSS 3B besitzt derzeit keinen Referenz-Audio-Eingang; dieser Punkt steht im offiziellen HeartLib noch auf der TODO-Liste. Deshalb enthält der HeartMuLa-Workflow keinen wirkungslosen Pseudo-Port. Mehr als 300 Sekunden sind möglich, aber `duration_seconds` bleibt eine Obergrenze: Audio-EOS kann früher eintreten und lange Lyrics verkleinern das promptabhängige Maximum.

## RDNA4-Anpassungen

Folgende Regeln wurden auf die konsolidierte Sammlung angewendet:

- keine Nunchaku-/SVDQ-/FP4-Workflows
- kein `CUDAExecutionProvider`
- keine TensorRT-, xformers-, Triton- oder Flash-Attention-Pflicht
- keine `nvfp4`-Modelle
- keine SeedVR2-Workflows mit festem `cuda:0`
- FLUX2-Klein-9B-Imports verwenden das installierte KV-FP8-Modell
- FLUX2-Klein-4B-Imports verwenden das installierte lokale 4B-Modell
- Z-Image-Imports verwenden das installierte BF16-Modell
- verdächtige Krea2-INT8-ConvRot-Referenzen wurden auf das installierte FP8-Modell umgestellt
- Qwen3-TTS verwendet `device=auto` beziehungsweise den Windows-ROCm-`cuda`/HIP-Alias und `attention=sdpa`; der Voice-LoRA-Pfad lädt keine Flash-Attention-/Triton-Pflicht
- ONNX-CUDA-Beispiele aus den Pixaroma-WAN-Wrapper-Workflows wurden nicht übernommen; stattdessen bleiben die nativen lokalen WAN/SCAIL-Workflows erhalten

## Bewusst nicht übernommen

Diese Dateien bleiben in ihren Quellordnern als Referenz, gehören aber nicht in die produktive RDNA4-Sammlung:

- Nunchaku-Workflows: NVIDIA/CUDA-spezifisch
- SeedVR2-Custom-Workflows: fehlende Nodes und festes `cuda:0`
- WAN-Video-Wrapper-Beispiele mit `CUDAExecutionProvider`
- Lens-Workflow mit NVIDIA-`nvfp4`-Textencoder
- Fish Audio S2: benötigter Node-Pack ist nicht installiert; Qwen3-TTS deckt TTS/Clone/Dialog lokal ab
- kostenpflichtige Cloud-Upscaler
- alte Tutorial-T2I-Duplikate, deren Modelle bereits sauber unter `Text to Image` vorhanden sind
- `Ill_modular_wf.json` und `Illus_v2_6.13.25.json`: große Legacy-Pipelines mit zahlreichen nicht mehr installierten Nodes/Modellen; die lauffähigen vereinfachten SDXL-Nachfolger wurden übernommen
- redundante WhatDreamsCost-Director-/2-Stage-Varianten; behalten wurden die expandierte Director-, Custom-Audio- und Prompt-Replay-Version
- der WhatDreamsCost-3-Stage-Workflow wurde nach rekursiver Prüfung ausgeschlossen, weil sein Quell-Subgraph `Stage #2` 20 Links zu nicht vorhandenen Nodes enthält; die Originaldatei bleibt im Quellordner und eine Sicherung liegt unter `_workflow_backups/excluded-LTX23_First+Last-Frame-3-Stage-source-broken.json`

## Validierung

Automatisch geprüft wurden alle 239 Workflows. Vor dem Release rekonstruiert `--against-head` die komplette v0.9.2-Migration deterministisch aus dem noch auf v0.9.1 stehenden `HEAD`; nach dem Release bewahrt `--baseline-ref v0.9.1` denselben Vergleich. Der Validator prüft zusätzlich die exakte Dateimenge und akzeptiert GPU-, Sekunden- und RODENT-Anpassungen sowie die vier gepinnten Template-Neuzugänge nur, wenn sie exakt reproduzierbar sind:

- 239/239 gültige JSON-Dateien
- 222 Nicht-Live-Workflows mit genau einem `PixaromaRunTimer`; 17/17 Live-Avatar-Workflows ohne Run-Timer
- 292 Haupt- und Untergraphen rekursiv geprüft
- 10.798 Nodes und 4.910 Dokumentations-/Parameter-Notes; die vorhandenen `PixaromaPrompt`-/`PixaromaPauseText`-Integrationen bleiben erhalten
- 7.411 Graph-Links einschließlich Slotgrenzen, Typkompatibilität, zentraler Device-Control-Verbindungen, Sekunden→Frame-Umrechnungen und wechselseitiger Input-/Output-Zuordnung erfasst
- keine neuen doppelten IDs, fehlenden oder einseitigen Endpunkte, Note-Zuordnungs-, Gruppen- oder Layoutfehler in den v0.9.2-Dateien
- die vier ursprünglich als v0.9.0-Dual-GPU-Workflows eingeführten Graphen wurden über den echten ComfyUI-Browsergraphen in API-Prompts expandiert und auf Windows-ROCm real ausgeführt: LTX-2.5 T2V, I2V und FLF2V jeweils mit 2 Sekunden bei 320×320 sowie Wan Animate 2 Motion Transfer mit 9 Frames bei 256×256. Alle vier Läufe endeten mit `execution_success` und speicherten nichtleere MP4-Dateien; seit v0.9.2 liegen sie in ihren funktionalen Ordnern.
- der MiniMax-Music-3-Workflow wurde mit Single-GPU- und verteilter Belegung über den echten Browsergraphen und die vollständigen lokalen Gewichte ausgeführt. Beide verwendeten vier Sekunden Maximaldauer, alle 30 Euler-/Simple-Schritte und tiled DAV decode und speicherten endliche, nichtleere 44,1-kHz-Stereo-FLACs mit 7,988 Sekunden Laufzeit. Das verteilte Log bestätigte den Textstack auf `cuda:0` (R9700) und MODEL/DAV auf `cuda:1` (RX 9070 XT). Der Qwen-3.5-4B-Enhancer endete ebenfalls mit `execution_success` und lieferte exakt `Global Metadata`, `Vocal Details` und `Arrangement`.
- vorhandene `PixaromaNote`-Dictionaries einschließlich Position und Größe unverändert; ausschließlich die Qwen3-TTS-Trainingsnote dokumentiert zusätzlich das neue `_Text.txt`-Transkriptschema
- Die automatisierte Testsuite prüft insgesamt die Workflow-Werkzeuge, den Continuous-LiveAvatar-Lebenszyklus und den Voice-LoRA-Adapterlebenszyklus; davon sichern die Integrationstests Manifest-Hashes gegen HEAD, exakte Prompttext-Migration, Formula+Idea-Trennung, Pause-Ancestry, wechselseitige Links, Kollisionsfreiheit, Korruptionserkennung, die drei INT8-Modellpfade, den AMD-sicheren Live-Avatar-Stack, echte PEFT-/Safetensors-Voice-LoRAs und wiederholte byteidentische Anwendung ab
- alle fünf neuen Trainer verwenden installierte Core-Nodes und vorhandene lokale Modelle
- alle fünf Trainer erfolgreich mit einem vollständigen einmaligen 1-Step-Train-und-Save-Smoke-Test auf der Radeon AI Pro R9700 / ROCm 7.15 ausgeführt; die ausgelieferten Workflows starten bewusst mit 2 Schritten für den ersten eigenen Smoke-Test, und die erzeugten Test-Safetensors enthielten nichtleere Adaptergewichte
- Boogu erst nach aktiviertem `offloading=true` OOM-frei validiert; diese sichere Einstellung ist im Workflow fest voreingestellt
- MOSS-TTS Local v1.5 verwendet `dtype=auto` und `attention=sdpa`; die Gewichte belegen zusammen rund 17,6 GB (9,1 GB Modell plus 8,5 GB Codec). Voice Clone und Continuation wurden auf der R9700 erfolgreich bis zu nichtleeren 48-kHz-Stereo-FLACs ausgeführt; für statisches ComfyUI-Offloading war ein lokaler Comfy-Cast-Fix für `MossQwen3RMSNorm` nötig
- Qwen3-TTS 0.6B trainierte auf der R9700 mit den ausgelieferten Rank-16-/Alpha-32-/Accumulation-4-Startwerten in einem vollständigen 1-Sample-/1-Epoch-Smoke-Test 462 nichtleere LoRA-Tensoren (47,6 MB) plus Sprecher-Einbettung. Für v0.7.0 wurde dieser Lauf zusätzlich mit dem String-COMBO-Wert `"16"` und einem realen MP3-/`_Text.txt`-Paar erfolgreich wiederholt; die Metadaten enthielten weiterhin den Integer-Rank `16`. Der anschließende Adapter-Inference- und Cache-Invalidierungs-Test erzeugte zweimal 3,82 Sekunden identisches, endliches 24-kHz-Mono-FLAC mit Peak 0,0615 und RMS 0,00569, ohne den nach Timestamp-Wechsel veralteten Backend-Cache wiederzuverwenden. Der kombinierte LiveAvatar-04-Lauf lieferte gleichzeitig ein nichtleeres 1024×1024-RGBA-Frame mit Alpha `(0,255)` und 5,58 Sekunden endliches Voice-LoRA-Audio.
- keine NVIDIA-/CUDA-only-Risiko-Widgets und keine eingebetteten `Rh-Comfy-Auth`-Tokens/JWTs
- Generator, Refinement und Validator sind reproduzierbar und idempotent; die fokussierte Unit-Test-Suite prüft dynamische Widgets, Seed-Kontrollen, VHS-Dictionary-Werte, Subgraphs und TrainLora-Widgetreihenfolge

Die Prüfung bestätigt Struktur, lokale Abhängigkeiten und RDNA4-Kompatibilität. Die Testsuite umfasst 160 erfolgreiche Tests und 20 bewusst übersprungene optionale/integrationsabhängige Fälle. Alle sieben verbleibenden MiniMax-H3-Workflows wurden einzeln mit echter R9700-Inferenz bis zur Videoausgabe ausgeführt. Für v0.8.6 liefen zusätzlich FL2VA und Ref2VA mit der neuen v4-Step-600-EMA-Turbo-LoRA, acht Euler-/Beta-Schritten und echter Dual-GPU-Platzierung jeweils bis zu fünf dekodierten 320×320-Frames; beide eigenständigen Guide-Enhancer wurden live mit Qwen 3.5 4B ausgeführt und lieferten ihre drei beziehungsweise sechs Pflichtabschnitte, wobei der Ref2VA-Abschluss den verbotenen Shot-1-Zeitstempel deterministisch entfernte. Für v0.8.7 wurden die beiden neuen offenen Multi-GPU-Graphen separat geprüft: FL2VA verarbeitete echte First-/Last-Frame-Anker und Ref2VA eine echte Bildreferenz; beide erzeugten mit acht Turbo-Schritten jeweils fünf dekodierte 320×320-Frames, klonten Qwen3VL und Video-/Audio-VAE nach `gpu:1` und meldeten keine ungelösten LoRA-Keys. Für v0.8.8 wurde der neue zentrale Control-Node live mit umgekehrter Zuordnung ausgeführt: MODEL wurde nach `gpu:1`, CLIP und VAE nach `gpu:0` geleitet; ComfyUI akzeptierte die verbundenen COMBO-Ausgänge und führte alle drei offiziellen Selector-Pfade erfolgreich aus. Die v0.8.3-Complete-Song-Finalvalidierung verwendete `Intro-Song.mp3` plus `Intro-Song.md`, plante 22 serielle Szenen mit maximal 14,875 Sekunden, erzeugte 7.200 Frames bei 864×480/24 FPS und muxte alle 12.501 MP3-Pakete payload-identisch in das 300,024-Sekunden-MKV. Für v0.8.4 lief zusätzlich der vollständige 90-Sekunden-Identity-Lock-Test mit `Outro-Song.mp3`, `Outro-Song.md` und `liveavatar-img-00031.png`: acht serielle 480×864-Szenen mit 20 Steps und festem Seed erzeugten 2.160 Frames bei 24 FPS. Das Bild wurde nachweislich als Frame 1 eingesetzt (dekodiert PSNR 38,78 dB), Sängerin, blonde/rosa Haare, schwarzes Glitzer-`DaWasteh`-Shirt, Sci-Fi-Location und fotorealistischer Stil blieben in den Kontaktbögen konsistent; keine zweite Person oder zusätzlichen Arme waren sichtbar. Quelle, Projekt-`joined_video.mkv` und finale MKV enthielten alle 3.751 MP3-Pakete mit identischem SHA-256-Payload `10d219c0…`, und Projekt-Joined und Finaldatei waren byte-identisch. Die fünf neuen Bild-LoRA-Trainer wurden lokal bis zum gespeicherten Adapter ausgeführt; Krea 2 RAW wurde nach dem OOM konsequent entfernt. Der Audio-to-Image-Workflow wurde vollständig mit Gemma 4 und FLUX.2 Klein 4B auf der lokalen ComfyUI-Installation ausgeführt. YuE CoT und YuE ICL wurden jeweils mit einer erzwungenen 10,00-Sekunden-Ausgabe vollständig auf der R9700 ausgeführt. HeartMuLa akzeptierte und dekodierte einen Lauf mit `duration_seconds=301` erfolgreich; das Modell setzte bei 193,68 Sekunden selbst Audio-EOS und bestätigt damit, dass der Wert eine Obergrenze statt einer garantierten Länge ist. Die neuen INT8-Varianten wurden zusätzlich live geprüft: Stable Audio 3 erzeugte 1,02 Sekunden endliches 44,1-kHz-Stereo-FLAC, ACE-Step 1.5 XL exakt 5,00 Sekunden endliches 48-kHz-Stereo-FLAC. YuE INT8 lud beide bitsandbytes-Stufen erfolgreich und erzeugte die 5-Sekunden-Stage-1-Tokens; der anschließende Stage-2-Lauf wurde auf Benutzerwunsch beendet und wird manuell geprüft. Ein vollständiger GPU-End-to-End-Lauf aller 239 Workflows wäre sehr rechen- und zeitintensiv; besonders große Musik-, WAN- und LTX-Workflows sollten auf der R9700 mit dem vorhandenen sicheren Launcher-Profil ausgeführt werden.

## Live Avatar Workflow 12–15 (v0.8.2)
See [Workflow 12–14 release notes](docs/LIVE_AVATAR_WORKFLOW_12_13.md) and the [local Blender VRM guide](docs/live-avatar-local-blender-vrm.md). Workflow 12-I is preflight-only and intentionally has no Spout sender. Workflow 12-II adds smoothed face/head tracking but remains face-only. Workflow 12-III is the body/hand-capable browser VRM path. Workflow 13 supplies references. Workflow 14 remains experimental multiview geometry; Workflow 15 uses a prepared RMBG A-pose front image, native Hunyuan3D 2.1 at latent 4096/octree 512, and avoids the confirmed fragmented multiview geometry route. Its GLB remains untextured and unrigged until the documented local Blender post-pipeline runs.
