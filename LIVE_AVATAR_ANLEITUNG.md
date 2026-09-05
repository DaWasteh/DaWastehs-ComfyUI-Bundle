# Live-Avatar-Anleitung · v1.1.0

Diese Anleitung beschreibt die lokalen Live-Avatar-Wege dieses Repositories auf dem Windows-RDNA4-System. Alle Kamera- und Referenzbilder bleiben bei den lokalen Wegen auf dem Rechner.

> **Wichtig:** Die Workflows haben unterschiedliche Fähigkeiten. Ein 2D-Bild ist kein geriggter 3D-Avatar. Nur ein vorhandenes VRM0-Modell besitzt Körper-Rig, Finger und Gesichtsmorphs.

## Schnellwahl

| Ziel | Workflow | Ausgabe für OBS |
|---|---|---|
| Geriggter High-Realism-Avatar mit Gesicht, Händen, Körper und adaptivem Bildausschnitt | 06 | Chrome-Fensteraufnahme |
| Drei Bilder + Prompt als später auswählbare lokale VRM-Variante | 08, danach 06 | Chrome-Fensteraufnahme |
| Transparentes 2D-Bild mit LivePortrait-Gesichtsanimation | 02 → 03 | Spout2 `ComfyLiveAvatar` |
| Schnellere experimentelle LivePortrait-Dauerausgabe | 05 | Spout2 `ComfyLiveAvatarFast` |
| Langsamer KI-Webcam-Charaktertausch | 07 | Spout2 `ComfyAICharacterSwapExperimental` |
| Realistische 2D-Referenzbilder erzeugen | 10 | keine Live-Ausgabe |
| Externe DirectML-Face-Swap-Kandidaten ehrlich vergleichen | 12-I | Testsender `LiveAvatar12Bakeoff` über OBS/Spout |
| Hochwertigere Portrait-Reenactment-Ausgabe mit echten Metriken | 12-II | Spout2 `ComfyLiveAvatarQuality` |
| Zuverlässiger geriggter Modus | 12-III | Chrome-Fensteraufnahme |
| Korrigierte Full-Body-/Turnaround-Referenzansichten erzeugen | 13 | keine Live-Ausgabe |
| Aus vier Ansichten echte lokale 3D-Geometrie erzeugen | 14 | statisches GLB unter `output/LiveAvatar/` |
| **Echtes Kamerabild mit getauschter Gesichtsidentität (Live-Deepfake, realistisch)** | **16** | Spout2 `ComfyLiveFaceSwap` |
| **Getauschtes Gesicht + Körper auf leerem Raum, wer rausgeht ist weg, plus RVC-Stimme** | **17** | Spout2 `ComfyLivePersonSwap` |

## Voraussetzungen

1. ComfyUI läuft lokal unter `http://127.0.0.1:8188/`.
2. Die Live-Avatar-Custom-Node liegt unter `L:/ComfyUI/ComfyUI/custom_nodes/ComfyUI-DaWasteh-LiveAvatar/`.
3. Die geprüften VRM0-Presets sind installiert:

   ```powershell
   L:/ComfyUI/.venv/Scripts/python.exe tools/install_live_avatar_vrm_models.py --comfy-root L:/ComfyUI/ComfyUI
   ```

4. Für Spout-Ausgaben ist das OBS-Spout2-Plugin auf diesem System unter `C:/ProgramData/obs-studio/plugins/win-spout/` installiert. Ältere Workflow-Notizen nennen alternativ den benutzerspezifischen `%APPDATA%`-Ordner; für diese OBS-32-Installation gilt der verifizierte `ProgramData`-Pfad. OBS anschließend neu starten.
5. Nur eigene, lizenzierte oder ausdrücklich einvernehmlich bereitgestellte Bilder und Stimmen verwenden.

### Zusätzliche Abhängigkeiten nach Workflow

| Workflow | Erforderlich |
|---|---|
| 03/04 | `ComfyUI-LivePortraitKJ`, `ComfyUI-KJNodes`, LivePortrait-Modelle und `ComfyUI-DaWasteh-LiveAvatar` |
| 05 | dieselben LivePortrait-Modelle plus `ComfyUI-DaWasteh-LiveAvatar` |
| 06 | `ComfyUI-DaWasteh-LiveAvatar`, gebautes lokales Frontend und installierte VRM0-Presets |
| 07 | zusätzlich OpenPose-Preprocessor, SD1.5-Checkpoint, LCM-LoRA, OpenPose-ControlNet, IPAdapter Plus und CLIP Vision |
| 08 | SD1.5-Checkpoint, LCM-LoRA, IPAdapter Plus, CLIP Vision und ein kompatibles VRM0-Basismodell mit genau einer eingebetteten Basisfarbtextur |
| 12-I | Extern installierter, lizenzierter Kandidat mit hash-gepinnter Konfiguration, Loopback-Health-Adapter und aktiver Identitätsfreigabe; standardmäßig vollständig deaktiviert |
| 12-II | Dieselben LivePortrait-Voraussetzungen wie 05 plus aktualisierte DaWasteh-Node für DirectShow- und Transport-/AI-Metriken |
| 12-III | Dieselben lokalen Browser-/VRM-Voraussetzungen wie 06 |
| 13 | Die bereits installierten Qwen-Image-Edit-2511-Modelle und Multiple-Angles-LoRA aus `Multi-Character-Angles-One-Click` |
| 14 | Installierter Core-Checkpoint `Hunyuan3D\\hunyuan_3d_v2.1.safetensors`; keine CUDA-Texture-Wrapper erforderlich |

Workflow 07 und 08 verwenden die gepinnten KI-Assets. Zuerst `Run (Instant)` stoppen und eine leere Queue abwarten, dann aus dem Repository-Root ausführen:

```powershell
L:/ComfyUI/.venv/Scripts/python.exe tools/install_live_avatar_ai_assets.py --comfy-root L:/ComfyUI/ComfyUI
```

Der Installer erwartet den vorhandenen SD1.5-Checkpoint `models/checkpoints/v1-5-pruned-emaonly-fp16.safetensors` und das vorhandene CLIP-Vision-Modell `models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`. Nach einer Neuinstallation ComfyUI neu starten, damit die Modelllisten aktualisiert werden.

## Drei Inputbilder + Prompt → auswählbare VRM-Variante

Dafür ist **Workflow 08** vorgesehen:

`workflows/Live Avatar/LiveAvatar-08-Local-VRM-Texture-Creator-Realistic+Stylized.json`

### Was der Workflow wirklich erzeugt

Workflow 08 nimmt ein vorhandenes, bereits geriggtes VRM0-Basismodell mit genau einer eingebetteten Basisfarbtextur und ersetzt ausschließlich diese UV-Textur. Mehrtextur-Modelle werden mit einer klaren Fehlermeldung abgelehnt, statt nur teilweise verändert zu werden. Ein vorhandener Alpha-Kanal der Textur bleibt erhalten. Das akzeptierte Ergebnis wird als neue `.vrm`-Datei unter ComfyUIs globalem Modellordner `models/live-avatar-vrm/` gespeichert und kann anschließend in Workflow 06 ausgewählt werden.

**Warum Prompt/Seed dort kaum wirken:** Der KSampler bearbeitet kein normales Personenbild, sondern die zerschnittenen UV-Inseln der vorhandenen Olivia-Textur. Vier LCM-Schritte, CFG 1,5 und Denoise 0,20 bewahren absichtlich diese UV-Struktur. Höhere Werte ändern mehr, erzeugen aber typischerweise Nahtfehler und seltsame Körperteile. Workflow 08 ist daher nur ein konservatives Farb-/Stil-Experiment und kein 3D-Modellgenerator. Für neue Geometrie Workflow 14 verwenden.

Er erzeugt **keine neue Geometrie**, kein neues Rig und keine zuverlässige Identitätsrekonstruktion. Körperform, Gesichtskontur, Haare als Geometrie, Finger, Morphs und UV-Inseln bleiben vom Basismodell. Die drei Bilder führen zu einer erscheinungs-/ähnlichkeitsgeführten Texturvariante.

### Geeignete Referenzbilder

Verwende drei Bilder derselben klar erwachsenen, lizenzierten beziehungsweise einvernehmlich abgebildeten Person:

1. **Frontalansicht**
2. **Dreiviertelansicht**
3. **Seitenansicht/Profil**

Für ein besseres Mittel:

- ähnliche Beleuchtung, Mimik und Bildqualität,
- Gesicht in allen Bildern ungefähr gleich groß,
- möglichst gleicher Haarschnitt und gleiche Kleidung,
- keine weiteren Personen, Texte, Logos oder UI-Elemente,
- keine extremen Perspektiven oder verdeckten Gesichter.

Das erste Bild bestimmt die Zielgröße des Referenz-Batches; die beiden anderen Bilder werden dafür mittig angepasst. Sehr unterschiedliche Ausschnitte schwächen das Ergebnis.

### Schritt für Schritt

1. Workflow 08 in ComfyUI öffnen.
2. Im Node **„1 · Licensed VRM0 template + UV texture“** ein passendes VRM0-Basismodell auswählen.
3. Die Bilder laden:
   - **„Referenz 1 · Frontalansicht“**
   - **„Referenz 2 · Dreiviertelansicht“**
   - **„Referenz 3 · Seitenansicht“**
4. Im positiven Prompt das gewünschte Aussehen beschreiben, zum Beispiel:

   ```text
   realistic adult fantasy character, natural skin tones, dark brown hair,
   plain black fitted clothing, detailed fabric, no logos, preserve UV seams
   ```

5. Im Speichern-Node einen neuen eindeutigen Namen setzen, zum Beispiel:

   ```text
   basti-avatar-v1.vrm
   ```

   `allow_overwrite` auf `false` lassen. So wird kein vorhandener Avatar unbemerkt überschrieben.
6. Der Speichern-Node **„OPT-IN (MUTED)“** ist standardmäßig stummgeschaltet. Zuerst genau einmal normal **Run** drücken; dabei wird nur die Vorschau erzeugt und noch keine `.vrm`-Datei gespeichert.
7. Die flache UV-Vorschau auf Text, Logos, harte Nähte, verschmolzene Details oder starke Farbflächen prüfen. Bei Fehlern Prompt oder Seed ändern und erneut mit weiterhin stummgeschaltetem Speichern-Node ausführen.
8. Nur bei akzeptierter Vorschau den Speichern-Node aktivieren und erneut normal **Run** drücken. Der feste Seed und ComfyUI-Cache verwenden exakt die bereits geprüfte Textur.
9. Workflow 06 öffnen, im Browser **„Modellliste aktualisieren“** drücken und die neue `.vrm`-Datei auswählen.
10. Die Variante zusätzlich am gerenderten 3D-Modell aus mehreren Ansichten prüfen. Die flache UV-Vorschau allein beweist keine sauberen Nähte am Mesh. Abgelehnte Dateien unter `models/live-avatar-vrm/` löschen oder nicht auswählen.

### Sichere Startwerte

- IPAdapter-Gewicht: `0.35`
- Referenzkombination: `average`
- Img2Img-Denoise: `0.20`
- LCM-Schritte: `4`

Ein höheres IPAdapter-Gewicht kann Referenzmerkmale stärker mischen, aber UV-Strukturen verschlechtern. Ein höheres Denoise verändert mehr, erhöht jedoch die Gefahr kaputter UV-Nähte. Die Startwerte sind absichtlich konservativ.

## Geriggten VRM-Avatar live starten · Workflow 06

1. `LiveAvatar-06-VRM-Full-Body-Hand-Face+Live-Mic.json` öffnen.
2. Einmal **normal Run** drücken, niemals `Run (Instant)`.
3. Falls ComfyUI die URL nicht sichtbar anzeigt, diese Adresse in Chrome öffnen:

   <http://127.0.0.1:8188/dawasteh/vrm-live/>

4. Kamera so aufstellen, dass für Ganzkörpertracking Hüften, Knie und Knöchel stabil sichtbar sind; gleichmäßiges Licht und freie Hände verbessern die Erkennung. Der Automatikmodus fällt bei verlorenen Bein-Landmarks auf eine stabile Oberkörperpose zurück. Hand- und Fingertracking bleibt bei Verdeckung, schnellen Bewegungen oder Händen außerhalb des Bildes best-effort.
5. Im Browser:
   - Kamera erlauben,
   - **Kamera starten**,
   - das lokale Preset **DaWasteh High-Realism v5 · Source-Face** verwenden oder eine andere VRM0-Datei wählen,
   - **Webcam-Bildausschnitt folgen** eingeschaltet lassen: sichtbare Schulter-/Hüft-/Beinanker steuern Zoom und Position, sodass Kopf oder Beine auch im Avatarbild verschwinden, wenn sie die Webcam verlassen,
   - **Neutrale Pose kalibrieren**,
   - in der Leistungszeile mindestens 24 Render-FPS prüfen; Tracking-FPS und Render-FPS sind absichtlich getrennte Werte,
   - optional **OBS-Chroma-Grün** aktivieren,
   - **OBS-Präsentationsmodus** drücken oder `P`.
6. In OBS eine **Fensteraufnahme** hinzufügen und das Chrome-Fenster **„DaWasteh VRM Live Avatar“** auswählen.
7. Bei grünem Hintergrund unter **Filter → Chroma-Key** Grün entfernen.

Der Browser rendert unabhängig vom Tracking-Takt und verarbeitet per `requestVideoFrameCallback` ausschließlich neue Kameraframes. Verlorene Gesichts-, Blick-, Mund-, Körper-, Bein- und Handziele laufen kontrolliert zur Modellruhe zurück, statt die letzte Pose einzufrieren. v0.8.5 begrenzt zusätzlich unplausible Gelenkwinkel und die Änderungsgeschwindigkeit von Körper- und Beinrotationen; die Standardglättung ist ruhiger eingestellt. Full-HD wird nur bis zur für OBS nutzbaren Backing-Auflösung supersampelt. Browser-Rendering und synthetisches Kameratracking sind automatisiert geprüft; physische Kameraqualität, schnelle Gesten und die konkrete OBS-Szenenkomposition müssen auf dem jeweiligen Aufbau sichtbar kontrolliert werden.

Das lokale v5-Modell übernimmt die Körpergeometrie des geprüften v2-Rigs, ergänzt aber ein alpha-gefedertes, an den Kopfknochen gebundenes Gesichtsdetail aus `L:/ComfyUI/ComfyUI/input/liveavatar-img-00031.png`. Dieses Detail besitzt eigene Blink- und Vokal-Morphs. Frontal ist die Ähnlichkeit dadurch deutlich höher; es bleibt bewusst ein hybrides VRM0 und keine vollständige volumetrische Rekonstruktion des einzelnen Portraitfotos. Extreme Profilansichten sind daher weniger quelltreu als die Frontalansicht.

Workflow 06 erzeugt keinen Spout-Sender. Chrome-Fensteraufnahme ist zuverlässiger als eine OBS-Browserquelle, weil Kamera-Freigabe und Interaktion im normalen Browser kontrollierbar bleiben.

### Optional als OBS-Browserquelle

Die gleiche URL kann in eine OBS-Browserquelle eingetragen werden. Danach über **Rechtsklick → Interagieren** die Kamera starten. Dieser Weg ist nicht der primär getestete Pfad; wenn Kamera oder WebGL in OBS/CEF nicht funktionieren, Chrome plus Fensteraufnahme verwenden.

## 2D-Avatar über LivePortrait und Spout · Workflow 03

1. Ein Quellbild erzeugen oder bereitstellen.
2. Mit Workflow 02 den Hintergrund entfernen.
3. Das transparente PNG in Workflow 03 unter **„Transparenten Avatar laden“** wählen.
4. Prüfen, dass Backend und Kameraindex zusammenpassen. Die Zahlen sind nicht backendübergreifend stabil:
   - DirectShow: Elgato Virtual Camera `0`, Facecam Pro `1`, Logitech BRIO `2`, OBS Virtual Camera `3`
   - Media Foundation: Logitech BRIO `0`, Elgato Virtual Camera `1`, Facecam Pro `2`
5. Zuerst genau einen normalen Lauf ausführen.
6. Danach **Run (Instant)** aktivieren, damit neue Webcam-Frames verarbeitet werden.
7. In OBS **Spout2 Capture** hinzufügen.
8. Sender **`ComfyLiveAvatar`** auswählen und Alpha/Transparenz aktivieren.

Der Spout-Sender hält das letzte fertige Bild sichtbar, erzeugt aber nur dann neue Bewegung, wenn weitere ComfyUI-Ausführungen stattfinden.

## Continuous LivePortrait · Workflow 05

1. Workflow 05 öffnen.
2. Einmal normal **Run** drücken.
3. In OBS den Spout2-Sender **`ComfyLiveAvatarFast`** mit Composite Mode `Default` wählen.
4. Mit ComfyUI **Interrupt** stoppen.

Bei Workflow 05 niemals `Run (Instant)` verwenden. Der Continuous-Node hält den ComfyUI-Ausführungsthread belegt und animiert ausschließlich Gesicht/Kopf.

## Buffered AI Mirror · Workflow 07

Workflow 07 kombiniert Webcam, OpenPose, SD1.5-LCM und IPAdapter. Er läuft auf der R9700 nur ungefähr mit 0,36–0,50 neuen Frames pro Sekunde und ist deshalb kein echter Echtzeitpfad. Der reparierte Kamera-Node ist ausdrücklich auf Logitech BRIO, DirectShow und Index 2 gestellt; damit darf OBS die Elgato-Kamera parallel weiterverwenden.

- Wiederholte Ausführung beziehungsweise `Run (Instant)` verwenden.
- In OBS den Spout2-Sender **`ComfyAICharacterSwapExperimental`** auswählen.
- Echte AI-Produktion und wiederholte 30-Hz-Präsentation getrennt unter `<ComfyUI-Elternordner>/logs/live-avatar-07/metrics.json` prüfen; der Workflow speichert dafür portabel `live-avatar-07/metrics.json` relativ zum lokalen Log-Root. Beim Wechsel zwischen Workflow 07 und 11 werden die Zähler trotz identischem Sendernamen zurückgesetzt; die Spout-Worker aktualisieren Präsentationen und Duplikate einmal pro Sekunde auch ohne neuen AI-Frame.
- Die BRIO für ComfyUI frei lassen.

Die v0.8.5-Abnahme enthielt eine echte isolierte OBS-Aufnahme während vier neuer Workflow-07-Ausgaben: 20,03 Sekunden MKV, 1280×720, 30 FPS. Vierzig bei 2 Hz dekodierte Videostichproben ergaben 18 unterschiedliche Hashes. Das temporäre OBS-Testprofil und die Testszene wurden anschließend entfernt; Streaming wurde nie gestartet.

## Optimierter Buffered AI Mirror · Workflow 11

Workflow 11 bleibt ein separater Graph und überschreibt Workflow 07 nicht. Er verwendet `DaWastehCachedOpenPose`, hält die OpenPose-Gewichte nach dem ersten Lauf auf der R9700 und nutzt standardmäßig 384×384 mit Körper- und Gesichtserkennung. Die besonders teure Handerkennung ist zunächst deaktiviert.

- Nach Installation oder Aktualisierung von `ComfyUI-DaWasteh-LiveAvatar` ComfyUI 8188 neu starten.
- Workflow 11 laden und zuerst einen einzelnen Kaltstart ausführen.
- Danach `Run (Instant)` aktivieren.
- Der OBS-Sender bleibt **`ComfyAICharacterSwapExperimental`**.
- Bisher gemessene warme Laufzeit: 0,62–0,68 Sekunden, Median 0,645 Sekunden beziehungsweise etwa 1,55 neue Bilder/s.
- v0.8.5 deaktiviert nur das ungenutzte OpenPose-Diagnose-JSON; die Poseausgabe und Bildqualität bleiben unverändert.
- Echte neue AI-Frames, wiederholte Spout-Präsentationen und Duplikate stehen getrennt in `<ComfyUI-Elternordner>/logs/live-avatar-11/metrics.json`; der Workflow verwendet portabel `live-avatar-11/metrics.json` relativ zum lokalen Log-Root. Metrikziele sind aus Sicherheitsgründen auf JSON-Dateien unter dem lokalen `L:/ComfyUI/logs`-Baum beschränkt.
- Für wichtigere Handposen im Cached-OpenPose-Node `detect_hand = enable` setzen; das kostet auf der R9700 ungefähr 0,54 Sekunden zusätzlich pro Frame.

Zwei Diffusionsläufe auf derselben GPU werden absichtlich nicht parallel gestartet: OpenPose, VAE und Sampler würden um dieselben GPU-Ressourcen konkurrieren, während Frames veralten und die Ende-zu-Ende-Latenz steigt. Auch 8188 und 8189 poolen keinen VRAM; ein Bridge-Node würde den seriellen Graphen nicht auf 24 neue Bilder/s bringen und zusätzliche Transfer-/Sortierlatenz erzeugen. Daher benötigt der produktive Workflow 06 nur 8188. 8189 bleibt höchstens für eine unabhängige Nebenaufgabe wie den Voice-Begleiter reserviert.

## OBS-Fehlerbehebung

### Kein Spout-Sender in OBS

- Erst einen erfolgreichen Workflow-Lauf abwarten.
- OBS nach Plugin-Installation neu starten.
- Richtigen Namen wählen: `ComfyLiveAvatar`, `ComfyLiveAvatarFast` oder `ComfyAICharacterSwapExperimental`.
- Workflow 06 verwendet grundsätzlich keinen Spout-Sender.

### Sender sichtbar, Bild bleibt schwarz

OBS und der sendende ComfyUI-Prozess müssen für Spout auf derselben physischen GPU laufen. Für den ComfyUI-Server auf Port 8188 bedeutet das auf diesem System üblicherweise die Radeon AI Pro R9700. Die Zuordnung in Windows unter **System → Anzeige → Grafik** prüfen und beide Programme danach neu starten.

### Webcam lässt sich nicht öffnen

- Andere Browser-Tabs und OBS-Kameraquellen schließen beziehungsweise deaktivieren.
- Workflow 03, 07 oder 11: `Run (Instant)` stoppen, im `WebcamCaptureCV2`-Node `release=true` setzen und einmal ausführen; anschließend für den nächsten Start wieder auf `false` stellen.
- Bei `0xC00D3704` Backend und Index prüfen: MSMF-Index 1 ist auf diesem Rechner die Elgato Virtual Camera, nicht die Logitech BRIO. Workflows 07/11 verwenden deshalb DirectShow-Index 2.
- Workflow 05: mit **Interrupt** stoppen und die leere Queue abwarten.
- Workflow 06: Browser-Tab beziehungsweise Fenster schließen, damit `getUserMedia` die Kamera freigibt.
- USB-Neuverbindungen können die OpenCV-Kameraindizes verändern.
- Workflow 06 und die Workflows 03/05/07/11 nicht gleichzeitig dieselbe Kamera verwenden lassen.

### Neue VRM-Datei erscheint nicht

- In Workflow 06 **„Modellliste aktualisieren“** drücken.
- Prüfen, dass der Dateiname auf `.vrm` endet.
- Nicht versuchen, eine ungeriggte `.glb` lediglich in `.vrm` umzubenennen.
- Der Browser unterstützt derzeit geprüfte VRM0-Dateien; nicht jede VRM-1.0-Datei ist kompatibel.

## Audio · optionaler DirectML-RVC-Begleiter

Workflow 06 liefert nur Video. Die optionale Live-Stimmwandlung läuft getrennt über den lokalen DirectML-RVC-Begleiter und ist ausdrücklich nicht Qwen-TTS/Voice-LoRA.

Installation und Start aus dem Repository-Root:

```powershell
L:/ComfyUI/.venv/Scripts/python.exe tools/install_live_voice_converter.py --destination L:/ComfyUI/voice-changer-dml-b2332
powershell -ExecutionPolicy Bypass -File tools/start_live_voice_converter.ps1 -InstallPath L:/ComfyUI/voice-changer-dml-b2332
```

Nur ein eigenes oder ausdrücklich lizenziertes kompatibles RVC-Modell verwenden. Das virtuelle Audiokabel ist nicht Bestandteil dieses Repositories. Das konvertierte Signal über ein separates Kabel in OBS aufnehmen und das Originalmikrofon im Mix stummschalten, um Doppelton, Originalstimmen-Leakage und Feedback zu vermeiden.

Offene manuelle Abnahmen für diesen optionalen Audiopfad sind physische Mikrofon-/Kabel-Routingqualität, mindestens zehn Minuten Stabilität, hörbare Qualitätsprüfung, kein Feedback beziehungsweise Originalsignal und die gewünschte Ende-zu-Ende-Latenz. Details und gemessene DirectML-Werte: [docs/live-avatar-v072-voice-backend-evaluation.md](docs/live-avatar-v072-voice-backend-evaluation.md).

## Workflow 12–15 · v0.8.5

Die vollständige Sicherheits-, Supervisor-, Benchmark-, GPU- und Rollback-Anleitung steht in [`docs/LIVE_AVATAR_WORKFLOW_12_13.md`](docs/LIVE_AVATAR_WORKFLOW_12_13.md). Keine externe Face-Swap-App und kein Modell werden durch die Workflows installiert. Die ausgelieferte Beispielkonfiguration ist absichtlich widerrufen, abgelaufen und deaktiviert.

Vor einem Start müssen die lokale Konfiguration unter `L:/ComfyUI/config/live-avatar-12.json`, getrennte Gesicht-/Stimmfreigaben, exakte Asset-/Modell-/Programm-Hashes, die sichtbare OBS-Kennzeichnung und die DirectML-Adapter-LUIDs eingetragen sein. `Start-LiveAvatar-Workflow12.bat` startet nach erfolgreicher Prüfung RVC → Video → OBS; `Stop-LiveAvatar-Workflow12.bat` ist der verifizierte Kill-Switch in Gegenrichtung. Ein öffentlicher Stream wird nie automatisch gestartet.

Workflow 12-I ist nur der ComfyUI-Precheck und erzeugt absichtlich keinen Spout-Sender. Erst der konfigurierte externe Adapter darf den pro Lauf eindeutig benannten Sender öffnen; der Supervisor empfängt vor READY mehrere Frame-Sync-Präsentationen und verlangt neben der richtigen Auflösung auch wechselnde Pixel-Hashes. Jeden Kandidaten zehn Minuten bei 720p und danach 1080p testen. Transport-FPS enthalten Wiederholungen; als echter Erfolg gelten nur mindestens 24 unterschiedliche Frames/s und p95 höchstens 41,67 ms.

Workflow 12-II schreibt getrennte AI-/Spout-/Duplikat-/Latenzmetriken nach `L:/ComfyUI/logs/live-avatar-12/quality-metrics.json`. Das neue geglättete Gesichts-Cropping erhöht die nutzbare Gesichtsauflösung, kann aber technisch keine Hände oder Oberkörperdeformation hinzufügen. Dafür Workflow 12-III mit einem geriggten VRM verwenden.

Workflow 13 liefert sechs korrigierte Full-Body-/Turnaround-Ansichten und zwei Ausdrucksreferenzen. Workflow 14 konditioniert Hunyuan3D wirklich mit Front/Links/Hinten/Rechts und erzeugt neue GLB-Geometrie. Das GLB ist statisch, untexturiert und ungeriggt; automatisches lokales AMD-Rigging ist mit den aktuell installierten Komponenten nicht verfügbar.


## Workflow 16 und 17 · Live Face Swap und Live Person Swap über DirectML · v1.0.0

Workflow 16 behält das **echte Kamerabild** und tauscht nur die Gesichtsidentität: BRIO (DirectShow-Index 2, 1280×720) → SCRFD → `hyperswap_1c_256` auf einem 0,8×-Crop → xseg_3-Occluder (Hände und Brillengestell bleiben echt) ∧ bisenet-Regionsmaske (Mundinneres bleibt echt) → digitale Rasur der Bartzone → LAB-Farbabgleich → GPEN-BFR-256 → Spout2 `ComfyLiveFaceSwap`. Workflow 17 legt das Ergebnis samt deinem Körper per MODNet-Matting auf eine leere Hintergrundplatte (Spout2 `ComfyLivePersonSwap`) und startet den DirectML-RVC-Stimmdienst mit.

**Zielidentität, mehrere Fotos:** Der Node **Face Swap Identity from Images** hat vier IMAGE-Eingänge (`source_images`, `more_images`, `more_images_2`, `more_images_3`); drei LoadImage-Nodes (frontal, Dreiviertel links/rechts) sind vorverdrahtet. Für 5–20 Fotos den Node **Face Swap Identity from Folder** nehmen: Fotos nach `L:/ComfyUI/ComfyUI/input/face-swap-identity/` legen und den Ordner wählen. Frontal, lächelnd, Mund offen und Dreiviertelansichten stabilisieren; das Ziel möglichst ohne Brille.

**Testbild:** ein Bild von **dir**, wie die Kamera dich sieht. Der Node **Webcam Snapshot** nimmt es beim ersten Run nach 3 s auf und behält es (`retake` ändern für ein neues). Die Vorschau zeigt darauf den Swap mit allen Reglern und die Millisekunden je Stufe.

1. **Run**: Identität, Testbild und Vorschau. Regler bei Bedarf: `crop_scale` 0,8 (0,7 gegen Bartreste), `color_match` 0,5, `keep_mouth` an, `shave` skin (none, wenn das Ziel selbst Bart trägt).
2. Workflow 17: Beim ersten Run wartet der obere Snapshot-Node 8 s, in denen du **aus dem Bild gehst** (Clean Plate, gecacht; `retake` erhöhen nach Licht- oder Kamerawechsel).
3. Live-Node **Bypass** aufheben, in OBS die Spout2-Quelle `ComfyLiveFaceSwap` bzw. `ComfyLivePersonSwap` anlegen, **Run**. Beenden nur mit **Interrupt**, nie Run (Instant).
4. Metriken: `L:/ComfyUI/logs/live-face-swap/metrics.json`. Bildrate unter Kamerarate: `parser_every` 2 (Standard in 17), `enhancer_every` 2. Bei Abendlicht senkt die BRIO die Bildrate selbst auf rund 15 Bilder/s; mehr Licht oder feste Belichtung hilft.
5. v1.1.0-Regler gegen Flackern und schwache Identität: `identity_strength` 0,85, `temporal_smoothing` 0,3, `mask_feather` 3, `lookahead_frames` 2 (Ausgabe zwei Kamerabilder verzögert, dafür zentriert geglättet), `glasses` swap/keep/remove. Ein Ganzgesicht-Modell (`dfm/<name>` aus `models/deepfacelive/`) ist der Weg zu einem abkaufbaren Ergebnis; der Trainingsweg für den eigenen Avatar steht in [docs/LIVE_PERSON_SWAP_V100.md](docs/LIVE_PERSON_SWAP_V100.md).

DirectML-Gerät 1 ist die R9700 (Swapper, Enhancer, gleiche GPU wie Spout/OBS), Gerät 0 die RX 9070 XT (Occluder, Parser, Matting im Worker-Thread; dort läuft auch der RVC-Dienst). Gemessen: Workflow 16 hält die Kamerarate (22,9 KI-Bilder/s), die Engine allein schafft 42 Bilder/s ohne und 29 mit Matting. Ein Ganzkörpertausch (andere Statur, Kleidung, Frisur) ist auf dieser Hardware in Echtzeit nicht flimmerfrei möglich; Workflow 17 ist deshalb Gesicht + Hintergrund + Stimme. Alle Modelle, Hashes, Lizenzen, Messreihen und Regler: [docs/LIVE_PERSON_SWAP_V100.md](docs/LIVE_PERSON_SWAP_V100.md); die DirectML-Grundlagen aus v0.9.9: [docs/LIVE_FACE_SWAP_V099.md](docs/LIVE_FACE_SWAP_V099.md).

## Workflow 15 · lokaler High-Realism-GLB→VRM-Pfad

Workflow 15 nutzt **eine** manuell geprüfte, mit RMBG freigestellte, level-kamerierte vollständige A-Pose-Frontansicht mit getrennten Armen/Beinen und sichtbaren Händen. Der native Hunyuan3D-2.1-Pfad läuft mit latent `4096` und Octree `512`. Die getestete Multiview-Geometrie ist fragmentierungsanfällig und wird daher nicht für diesen Geometriepfad verwendet. Das GLB ist statisch, untexturiert und ungeriggt; danach `tools/build_high_realism_local_vrm.py` mit Blender-Postpipeline verwenden.

Auf Windows-ROCm nicht Hunyuan Paint, nvdiffrast oder CUDA-Rasterizer nachinstallieren: sie sind kein unterstützter lokaler Texturpfad. Das ist kein fotorealistischer Einbild-Klon; Finger, Gesicht, Haare, Seiten/Rücken, Mund und Gelenkdeformation vor Freigabe sichtbar prüfen und bei Bedarf in Blender nacharbeiten.
