# YuE2, Cosmos Predict2, TRELLIS.2 und Pixal3D · v1.1.8

## Einsatz und Grenzen

- **YuE2: ausschließlich privat/nichtkommerziell.** Die Modellgewichte stehen unter CC-BY-NC-4.0. Diese Workflows sind für private Projekte vorgesehen; Streaming-Songs bleiben bei ACE-Step. Die öffentlichen JSON-Workflows enthalten weder Modellgewichte noch private Songtexte oder Audioaufnahmen.
- **Cosmos Predict2 erzeugt Bilder/Videos**, keine Simulationszustände, Kräfte, Materialien, Collision oder Game-Engine-Szenen. „Physikalisch plausibel“ ist ein Generierungsziel, keine Garantie.
- **TRELLIS.2/Pixal3D erzeugen statische Meshes.** Form, PBR-Material und separate Collision werden getrennt exportiert. Kein Rig, keine Animation, keine automatische Gelenk- oder Gebäude-Semantik.
- **Echte Collision:** der eigene CPU-Node erzeugt eine konservative konvexe Hülle oder Box und eine Godot-4-Physikszene. Geeignet für massive Props. Türen, Innenräume, Zwischenräume und Gelenke erfordern separate Compound-Collider/Handarbeit. Eine konvexe Hülle ist kein begehbares Gebäude.

## Workflows

Alle 13 Ergänzungen verwenden RODENT-Funktionsgruppen (Credit: Nerdy Rodent), deutsche Einstiegshinweise, eine Parameterreferenz, genau einen Pixaroma-Timer und die zentrale GPU-Wahl. Standard ist die R9700 (`gpu:0`); die Gaming-GPU wird nicht benötigt. Ausgaben erscheinen erst nach der Queue: **keine Echtzeit-Musikgenerierung**.

| Ordner | Datei / Eingaben |
|---|---|
| `Music Generation` | `YuE2_3B_INT8-PRIVATE-Text-to-Music.json`: Style + Lyrics → ABC-Plan → Musik |
| `Music Generation` | `YuE2_3B_INT8-PRIVATE-ABC-to-Music.json`: Style + Lyrics + eigene ABC-Notation; leerer ABC-Eingang schaltet die Planung aus |
| `Music Generation` | `YuE2_3B_INT8-PRIVATE-Audio-Cover.json`: Referenzaudio → SheetSage2 → symbolische Melodie → neues Arrangement |
| `Text to Image` | `Cosmos_Predict2_2B-Text-to-Image.json`: Text → Bild |
| `Controlled Video` | `Cosmos_Predict2_2B-Image-to-Video.json`: Text + Startbild |
| `Controlled Video` | `Cosmos_Predict2_2B-First-Last-Frame.json`: Text + Start-/Endbild |
| `Controlled Video` | `Cosmos_Predict2_2B-Video-Continuation.json`: Text + kurzer Videoanfang |
| `Controlled Video` | `Cosmos_Predict2_2B-Text-to-Video.json`: eigener T2I-Checkpoint erzeugt das Startbild für Video2World |
| `Game Development` | `TRELLIS2_INT8-Shape-Collision.json`: Einzelbild → vereinfachte Form + Collision |
| `Game Development` | `TRELLIS2_INT8-PBR-Collision.json`: Einzelbild → PBR-Sichtmesh + Collision |
| `Game Development` | `Pixal3D_INT8-Shape-Collision.json`: Einzelbild + Kameraschätzung → Form + Collision |
| `Game Development` | `Pixal3D_INT8-PBR-Collision.json`: Einzelbild + Kameraschätzung → PBR + Collision |
| `Game Development` | `Pixal3D_INT8-MultiView-PBR-Collision.json`: Front/links/hinten/rechts → PBR + Collision, eigener MultiView-Checkpoint |

### YuE2

Style enthält Genre, Sprache, Stimme, Tempo, Instrumente und Stimmung. Lyrics enthalten singbaren Text mit `[Verse]`, `[Chorus]` usw. Für Instrumentals eine passende Style-Beschreibung und keine gesungenen Texte verwenden; Erfolg/Struktur bleiben modellabhängig.

Die ABC-Notation ist editierbarer symbolischer Musikinhalt, kein MIDI-/Audio-Upload. `full` plant Melodie/Akkorde, `melody` eine Melodie. Bei Cover müssen SheetSage2 und YuE2 denselben Modus verwenden. Cover überträgt **nicht** die Stimmidentität und ist kein Voice-Cloning.

`max_duration=120` ist eine Obergrenze. Der Generator kann früher stoppen; seine tatsächliche Sekunden-Ausgabe steuert das Audio-Latent. Native Decodierung: 32 DPM2/SGM-uniform-Schritte, CFG 1; FLAC mit 48 kHz. Größere Dauern schrittweise testen, nicht blind auf 900 Sekunden stellen. Nur eigene oder ausreichend lizenzierte Referenzen laden.

### Cosmos Predict2

Gewählt: **2B T2I** und **2B Video2World 480p/16fps**, nicht die 28,5-GB-14B-Varianten. Der Video-Standard entspricht dem offiziellen Beispiel: 848×480, 93 Frames, 16fps, 30 Euler/simple-Schritte, CFG 4. Containerdauer: **5,8125 Sekunden**. Die Sekundensteuerung rundet auf `4n+1`; andere Auflösungen/Längen sind nicht automatisch gleich gut. 720p/10fps erfordern andere Checkpoints und sind hier nicht als getestete Profile enthalten.

`DaWVideoFrames` begrenzt die Referenz auf fünf Frames bei 16fps und 848×480. Der Adapter verwendet VideoHelperSuite, gibt aber ausschließlich IMAGE zurück: Dessen unbenutzte Lazy-AUDIO-Ausgabe wird nicht im RAM-Cache abgelegt. Ein tonloses Referenzvideo konnte zuvor beim späteren Cache-Aufräumen den ComfyUI-Worker beenden; der aufeinanderfolgende Live-Test Video-Continuation → Text-to-Video besteht mit diesem Adapter. Core/VHS-Dateien und globale Cache-Defaults wurden nicht verändert. Andere alte VHS-Workflows werden dadurch nicht pauschal repariert. Die Ausgabe enthält **keinen übernommenen Ton**. Start-/Endbilder sollten dieselbe Szene zeigen. Text→Video ist bewusst zweistufig und benötigt beide 2B-Gewichte.

**Nicht verwechseln:** `oldt5_xxl` ist T5 1.0, nicht Flux-T5 1.1. Predict2 braucht **WAN 2.1 VAE**, nicht den vorhandenen Cosmos-CV8-VAE.

### 3D-Eingaben

Single-View: ein vollständiges Einzelobjekt, ruhiges Licht, keine Nachbarobjekte. BiRefNet entfernt den Hintergrund; bei korrektem Alpha den Background-Switch ausschalten. Pixal3D nutzt MoGe für das horizontale FOV (manuell editierbar nach Trennen der FOV-Verbindung).

MultiView: quadratische Ansichten in 90°-Schritten, gleicher Maßstab, schwarzer Hintergrund, konsistente Kamera. Default-FOV 20° für kalibrierte Render; fotografische Ansichten brauchen ein passendes gemeinsames FOV. Nicht benötigte Ansichten am Conditioning-Node trennen. Das sind **Eingabeanforderungen**, keine automatische Kamerakalibrierung oder Konsistenzprüfung. Kein Text-, Video-, Pointcloud- oder Pose-Eingang wird vorgetäuscht.

1024³ Formstufe; AMD-geprüfter 256³-UDF-Remesh, QEF aus, `midpoint`, maximal 12.000 Dreiecke. Das Budget ist eine Obergrenze. PBR-Atlas: 1024px mit Base Color, Metallic/Roughness, AO und Normal. Shape-Workflows lassen die Textur-/UV-Stufen tatsächlich aus.

### Collision in Godot und Blender

Unter `output/GameDev/<Familie>/<Variante>/` entstehen:

1. `asset_*.glb`: Sichtmesh, je nach Variante mit/ohne PBR.
2. `asset_collision_*.glb`: getrennte Kontrollgeometrie, auch in Blender importierbar.
3. `asset_collision_*.tscn` und gleichnamiges JSON: tatsächliche Godot-4-Szene plus Bericht.

Die `.tscn` enthält eingebettete `ConvexPolygonShape3D`-Punkte und `CollisionShape3D` unter `StaticBody3D` oder `RigidBody3D`. Sie benötigt das Collision-GLB **nicht**, um physikalisch zu funktionieren. Das Sichtmesh separat in derselben Ausrichtung hinzufügen; Einheiten/Achsen werden nicht automatisch umgerechnet. Bei dynamischen Props Masse bewusst wählen, nicht aus dem Bild schätzen.

Default: 128 Collision-Vertices. Eine komplexere Hülle wird nicht nach innen vereinfacht, sondern **explizit als Box umschlossen**; der Report nennt den Rückfall. Die vollständige Ausgangsgeometrie wird auf Einschluss geprüft. Größere Hüllen sind einstellbar, aber teurer. Kein automatisches Zerlegen in mehrere Collider.

## Installation und Reproduktion

ComfyUI-Core 0.35.0 / Templates 0.11.60 waren die lokale Basis. Benötigt werden außerdem Pixaroma, VideoHelperSuite, die Bundle-GPU-Steuerung und `ComfyUI-DaWasteh-GamePhysics` (NumPy/SciPy). Kein CUDA-/Triton-/FlashAttention-Zusatz erforderlich.

```powershell
# Modelle ohne YuE2:
L:/ComfyUI/.venv/Scripts/python.exe tools/install_models_v118.py --comfy-root L:/ComfyUI/ComfyUI

# YuE2 ausdrücklich nur für private/nichtkommerzielle Nutzung einschließen:
L:/ComfyUI/.venv/Scripts/python.exe tools/install_models_v118.py --comfy-root L:/ComfyUI/ComfyUI --include-private-yue2

# Alle ausgewählten lokalen Dateien prüfen, ohne Downloads:
L:/ComfyUI/.venv/Scripts/python.exe tools/install_models_v118.py --comfy-root L:/ComfyUI/ComfyUI --include-private-yue2 --verify-only

# Deterministisch erzeugen (vom Repository-Root):
L:/ComfyUI/.venv/Scripts/python.exe -m tools.build_workflows_v118 --destination tmp/v118-rebuild
```

`tools/workflow_templates/v118/model-manifest.json` enthält **15 eindeutige Dateien**, jeweils Größe, SHA-256, Repository-Revision und lokales Ziel. Vorhandene Pixal-/Trellis-VAEs, MoGe, BiRefNet und WAN-VAE werden geprüft und wiederverwendet. Rund 30,12 GB waren auf Bastis Installation zusätzlich nötig. Abweichende vorhandene Dateien werden nicht überschrieben. Der Updater installiert keine Modellpakete ungefragt. Die gespeicherten `v118_*`-Referenznamen sind lokale Testdateien, keine mitgelieferten Medien: auf anderen Installationen eigene Bild-/Video-/Audioeingaben auswählen.

Quellen/Dateihashes: `tools/workflow_templates/v118/sources.json`. Die fünf Pixaroma-3D-Modellvorlagen wurden auf Modelle, Sampling, Form-/Texturpfade und 1024/1536-Auflösungen geprüft; ihre `3D\\...`-Modellpfade und ungeprüften High-VRAM-Defaults wurden nicht blind übernommen. Die 3D-Generierung baut auf dem bereits gepinnten offiziellen Core-Template und dem lokal geprüften v0.9.7-Remesh auf.

## Lizenzquellen

- [YuE2 / CC-BY-NC-4.0](https://huggingface.co/Comfy-Org/YuE2)
- [Cosmos Predict2 / NVIDIA Open Model License](https://huggingface.co/Comfy-Org/Cosmos_Predict2_repackaged)
- [Pixal3D](https://huggingface.co/Comfy-Org/Pixal3D) und [TRELLIS.2](https://huggingface.co/Comfy-Org/TRELLIS.2): MIT-markierte Gewichte; eingebettetes DINOv3 unter [Metas separater Lizenz](https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md).

Keine Rechtsberatung; aktuelle Originalbedingungen vor Veröffentlichung prüfen.

## Teststatus

Alle **13 Workflows** wurden mit echten Modellen auf der R9700 ausgeführt; die aus den endgültigen Graphen im Browser exportierten funktionalen API-Prompts wurden gegen die ausgeführten Prompts abgeglichen. Nachweis mit Ausgabe-Hashes: [`performance/rdna4/v118-validation.json`](../performance/rdna4/v118-validation.json).

| Test | Ergebnis / beobachtete Zeit |
|---|---|
| YuE2 Text / leeres ABC / Cover | 109,56 / 106,4 / 30,96 Sekunden Stereo-FLAC bei 48 kHz; ca. 90 / 70 / 30 Sekunden Supervisor-Zeit |
| YuE2 ausgefülltes ABC | zusätzlicher 30-Sekunden-Cap-Test erfolgreich; ca. 20 Sekunden |
| Cosmos Text-to-Image | 1024²-PNG, ca. 30 Sekunden |
| Cosmos vier Video-Varianten | je 93 Frames, 848×480, 16fps, 5,8125 Sekunden; ca. 430–451 Sekunden |
| Pixal3D Shape / PBR | 11.972 Dreiecke; ca. 190 Sekunden Shape, danach ca. 30 Sekunden PBR **mit gecachter Form** |
| TRELLIS.2 Shape / PBR | 11.940 Dreiecke; ca. 40 Sekunden Shape, danach ca. 30 Sekunden PBR **mit gecachter Form** |
| Pixal3D MultiView PBR | 11.998 Dreiecke; ca. 751 Sekunden, einschließlich vierfacher DINO/NAF-Vorbereitung |
| Godot-Collision | tatsächliche `.tscn` geladen; fallender RigidBody kommt auf exportiertem Collider zur Ruhe |

Die drei PBR-GLBs wurden in Blender importiert und von vorn/hinten gerendert: gültige UVs/Texturen, keine degenerierten Dreiecke, Budget eingehalten. Hull-/Box-Ausgabe mit StaticBody/RigidBody und Masse wurde zusätzlich über den echten Node geprüft. Bei den Axt-Tests überschritt die Hülle das 128-Vertex-Defaultbudget und fiel ausdrücklich auf eine konservative Box zurück.

**Prüfgrenzen:** Das ist eine technische Ausführungs-/Ausgabeprüfung, keine Hörabnahme oder physikalische Genauigkeitszertifizierung. Die Audio-Dateien sind endlich und nicht stumm; ABC/Cover enthalten vereinzelte Vollpegelsamples. Cosmos erzeugt sichtbare Bewegung, zeigt aber beim First-/Last-Frame-Test Farbkippen am Ende und bei Text-to-Video Geisterfragmente; auch exakt zwei Sprünge wurden nicht als erfüllt bestätigt. First/Last ist deshalb ein experimenteller Steuerpfad. Keine der neuen Varianten ist als Echtzeit- oder 14B-/16-GB-GPU-Profil freigegeben. MultiView ist deutlich langsamer als Single-View; der beobachtete Prozess-RAM-Peak während TRELLIS/MultiView lag bei rund 20,44 GiB, nicht bei einem garantierten Maximalwert.

Vollständige lokale Testsuite: **324 bestanden, 1 übersprungen, 326 Subtests bestanden**; eine bestehende Pillow-Warnung. Sammlung: 244 Dateien, 297 Graphen, 11.114 Knoten, 5.074 Notes, 7.690 Links, 225 Timer. Bestandsgraphen wurden nicht verändert.
