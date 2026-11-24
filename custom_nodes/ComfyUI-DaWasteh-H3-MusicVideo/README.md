# DaWasteh MiniMax H3 – Song → Musikvideo & Video-Upscaling (v1.3.3)

Seit **v1.2.2** besteht der Workflow `MiniMax_FastH3_INT8-Song+Lyrics-to-Music-Video.json` aus sichtbaren Schritten
statt eines einzelnen Director-Nodes. Grundlage ist **FastH3** (FastVideo, 8 Schritte, VSA-Sparse-Attention).

| Node | Aufgabe |
|---|---|
| `MV 0 · FastH3 + Realismus-LoRA` (`DaWMV2LoadModel`) | v1.2.4: FastH3 schreibgeschützt abgebildet (kein Commit für die 22-GB-Datei), optionale LoRA mit Triggerwort, ab ~65k Tokens Aktivierungsreserve pro Schritt (1920×1088 ohne OOM) |
| `MV 1 · Song + Lyrics Planner` (`DaWMV2Planner`) | Dauer, Tempo/Energie, Lyrics-Timing per lokalem Whisper, Szenen mit variablen Längen an Abschnitts-/Zeilengrenzen |
| `MV 2 · MiniMax Prompt Writer` (`DaWMV2PromptWriter`) | v1.2.5 `auto`: GGUF-Modell aus dem Startprofil (Qwen3.8 27B, `llama-server` mit MTP-Kopf auf gpu:1, nur während des Schreibens gestartet), sonst Qwen3.5 4B. Charaktersheets → Text, Produktionsbibel (Stil, Orte in Story-Reihenfolge), Handlung je Shot mit den Abschnittsvorgaben der Videoidee → MiniMax-Format mit `<d>`-Lyrics |
| `MV 3 · H3-Textencoder` (`DaWMV2EncodeScenes`) | Qwen3-VL-32B encodiert alle Szenen einmal (v1.2.4: mit LoRA-Triggerwort, schreibgeschützt geladen), danach vollständig freigegeben |
| `MV 4 · Szene vorbereiten` (`DaWMV2SceneSetup`) | Original-Songausschnitt fest im Audio-Strom (Lippensync), bei Folgeszenen 22 eingefrorene Frames der Vorgängerszene (Extend) |
| `MV 5 · Szene speichern` (`DaWMV2SaveScene`) | exakt die neuen Frames speichern, Übergangs-Latent für die nächste Szene, Vorschau mit Originalton, Resume |
| `MV 5b · Szene prüfen` (`DaWMV2ReviewScene`) | v1.2.5: zeigt jede neue Szene als Video mit Originalton im Node und hält den Lauf an: **Weiter**, **Neu rendern** (neuer Seed, im selben Lauf; frühere Takes bleiben wählbar) oder **Rest ohne Prüfung**. Entscheidung per `POST /dawasteh/mv2/review` (Frontend-Erweiterung `web/mv2_review.js`, Logik in `review.py`) |
| `MV 5c · Upscale an/aus + Methode` (`DaWMV2UpscaleSettings`) | v1.2.7 / v1.3.3: ein Schalter für das ganze Video – aus, WAN 2.2 Low-Noise, SeedVR2 3B, H3 Latent Upscaler 3D oder H3 Ultimate/Split Upscale (seit v1.3.3 über `MMH3SplitUpscale` aus `Comfyui_Minimax_h3_latent_Upscaler`) – und die Ziel-Langseite (Standard 1920) |
| `MV 5c · Szene hochskalieren` (`DaWMV2UpscaleScene`) | v1.2.7: hinter jedem MV 5b; skaliert genau den freigegebenen Take hoch, bevor die nächste Szene gerendert wird, per Graph-Expansion in die Kette der gewählten Methode (dieselben Nodes und Einstellungen wie in `workflows/Video Upscaling/`). Logik in `upscale_mv.py`; interne Teile `DaWMV2UpscaleSource`, `DaWMV2UpscaleModels`, `DaWMV2UpscaleSave` |
| `MV 6 · Fertiges Musikvideo` (`DaWMV2Finalize`) | Szenen verlustfrei aneinander, Originaldatei per `-c:a copy` darunter. v1.2.7: zusätzlich der Film aus den hochskalierten Szenen und optional ein Vergleichsvideo (links Original, rechts Upscale) |

Ablauf im Graph: Planung → Szene 1 → **MV 5b** (prüfen) → **MV 5c** (hochskalieren) → **Pixaroma Loop** über die
restlichen Szenen, jede mit MV 5b und MV 5c → Finale. Bis v1.2.4 gab es nur nach Szene 1 ein Pixaroma-Bildgate. Details, Messwerte und Grenzen:
`docs/H3_MUSIC_VIDEO_V122.md`; LoRA, 1920×1088 und die Speicherursache des früheren Extend-OOM:
`docs/H3_MUSIC_VIDEO_V124.md` (Modul `h3_highres.py`); Prompt Writer und Szenen-Prüfung: `docs/H3_MUSIC_VIDEO_V125.md`;
Upscale nach jeder Freigabe: `docs/H3_MUSIC_VIDEO_V127.md`.

Projektordner: `ComfyUI/output/DaWasteh_H3_MusicVideo_v2/<Projekt>_<Hash>/` (`plan.json`, `conditioning/`, `scenes/`,
`preview/`, `takes/` mit verworfenen Takes, `upscaled/<Methode>_<B>x<H>/` mit den hochskalierten Szenen). Fertige Filme:
`ComfyUI/output/video/DaWasteh_MusicVideo/<Projekt>_<Zeit>.mp4|mkv`, dazu `…_upscale_<Methode>_<B>x<H>` und
`…_vergleich_original_vs_<Methode>`.

Zusätzliche Abhängigkeit: `openai-whisper` (im Bundle-venv vorhanden; Modell `small` ≈ 460 MB wird beim ersten Lauf
nach `~/.cache/whisper` geladen). Ohne Whisper verteilt der Planer die Zeilen über den Gesangsbereich.

## Video-Upscaling · v1.2.3, erweitert in v1.2.6

`upscale_nodes.py` liefert den gemeinsamen Rahmen der Workflows in `workflows/Video Upscaling/`
(Ultimate Upscale, Latent Upscaler 3D, SeedVR2; v1.2.6: WAN 2.2 Low-Noise):

| Node | Aufgabe |
|---|---|
| `VU 1 · Video-Upscale Planer` (`DaWVUPlanner`) | Blöcke an harten Schnitten, Zielgröße = Quelle × `scale` auf 32 px, 24-fps-Arbeitskopie falls nötig |
| `VU 2 · Block laden` (`DaWVULoadBlock`) | Frames eines Blocks, aufgefüllt auf das Raster der Methode (H3 `17k+5`, SeedVR2/WAN `4k+1`), dazu der Tonausschnitt. v1.2.6: optionaler Vorlauf `lead_frames` (echte Frames derselben Einstellung, an Schnitten der wiederholte erste Frame), den `VU 3` wieder verwirft |
| `H3 · Video + Originalton → AV-Latent` (`DaWH3VideoToAVLatent`) | H3-Video- und Audio-VAE-Encode mit Speicherfreigabe vorab |
| `H3 · Prompt einmal encodieren` (`DaWH3PromptOnce`) | Qwen3-VL lädt nur beim ersten Mal, Ergebnis unter `_conditioning/` zwischengespeichert |
| `VU 3 · Block speichern` (`DaWVUSaveBlock`) | Vorlauf und Auffüllung abschneiden, Block speichern, Vorschau mit Originalton, Resume |
| `VU 4 · Hochskaliertes Video` (`DaWVUFinalize`) | Blöcke verlustfrei verbinden, Original-Tonspur per `-c:a copy` |
| `VU · Räumliche Kacheln` (`DaWVUSpatialTiles`, `spatial_tiles.py`) | v1.2.6: Modell-Patch, rechnet große Frames in überlappenden Kacheln nativer Größe und überblendet sie bei jedem Schritt (MultiDiffusion); arbeitet mit WANs zeitlichen Context-Windows zusammen |
| `VU · Diffusion-Modell laden (RAM-schonend)` / `VU · Textencoder laden (RAM-schonend)` (`DaWVUReadOnlyUNETLoader`, `DaWVUReadOnlyCLIPLoader`, `readonly_loaders.py`) | v1.2.6: wie `UNETLoader`/`CLIPLoader`, aber mit schreibgeschützter Dateiabbildung (Funktionen aus `h3_highres.py`): Windows rechnet die Datei nicht auf das Commit-Limit an, Ergebnis bitidentisch |

Details und Messwerte: `docs/VIDEO_UPSCALE_V123.md`, WAN: `docs/VIDEO_UPSCALE_WAN_V126.md`.

---

# Legacy (bis v1.2.1): H3 Complete-Song Director

Die älteren Nodes `DaWH3MusicVideoDirector`, `DaWH3MusicVideoDirectorDualGPU`, `DaWH3MusicVideoLoadSegment`,
`DaWH3MusicVideoSaveSegment`, `DaWH3MusicVideoFinalize` und `DaWH3MusicVideoLoadImagePath` bleiben für ältere
gespeicherte Workflows registriert, werden vom ausgelieferten Musikvideo-Workflow aber nicht mehr verwendet.
