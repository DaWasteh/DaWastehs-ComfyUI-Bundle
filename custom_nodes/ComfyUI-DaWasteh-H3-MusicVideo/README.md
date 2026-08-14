# DaWasteh MiniMax H3 – Complete Song Music Video

Ein einzelner sichtbarer ComfyUI-Master-Workflow für lange Musikvideos. Der Master analysiert den Song, plant beatnahe Szenen, erzeugt MiniMax-H3-Unterjobs nacheinander, speichert jeden Clip sofort, setzt alle Clips zusammen und muxxt den ursprünglichen Audiostream ohne Neukodierung ein.

## Voraussetzungen

- Aktuelles ComfyUI mit nativer MiniMax-H3-Unterstützung (`MiniMaxH3ReferenceToVideo`, `MiniMaxH3SigmaShift`, `VAEDecode`).
- `ComfyUI-Spectrum-MiniMax-H3`, sofern `spectrum_enabled = true` bleibt.
- Funktionierendes FFmpeg **und ffprobe**. VideoHelperSuite bringt gewöhnlich ein passendes FFmpeg mit; alternativ beide Programme auf `PATH` legen.
- Die vier H3-Komponenten sowie die v0.8.6-Turbo-LoRA:

```text
models/diffusion_models/MiniMax H3/minimax_h3_ref2va_pruned_int8_convrot.safetensors
models/text_encoders/MiniMax H3/qwen3vl_32b_minimax_h3_int8_convrot.safetensors
models/vae/MiniMax H3/minimax_h3_video_vae_fp16.safetensors
models/vae/MiniMax H3/minimax_h3_audio_vae_fp32.safetensors
models/loras/MiniMax H3/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors
```

Die LoRA stammt aus `drbaph/MiniMax-H3-Turbo-Lora-ComfyUI`, ist die für pruned/curve-form-ComfyUI-Modelle konvertierte v4-Step-600-EMA-Empfehlung und muss den SHA-256-Wert `7098acf3ee75028fd9fcd948f50fcc8d995057fabb76f86bd3ca2c0ffc58e409` besitzen.

## Installation

1. Die Ordner `ComfyUI-DaWasteh-H3-MusicVideo` und `ComfyUI-DaWasteh-MultiGPU-Control` nach `L:\ComfyUI\ComfyUI\custom_nodes\` kopieren. Alternativ den beiliegenden PowerShell-Installer ausführen.
2. ComfyUI vollständig neu starten.
3. Im Browser `Strg+F5` drücken.
4. `MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json` laden. Seit v0.9.2 enthält dieser kanonische Workflow selbst die optionale GPU-Steuerung; ein separater Dual-GPU-Klon ist nicht mehr nötig.

Keine zusätzlichen Python-Pakete werden installiert.

## Dual-GPU-Modus auf Port 8188

`DaWH3MusicVideoDirectorDualGPU` ergänzt jeden intern erzeugten Segment-Graphen automatisch um ComfyUIs offizielle Device-Selector-Nodes. Ab v0.8.8 liefert der sichtbare `DaW Multi-GPU Device Control`-Node drei zentrale Dropdowns für MODEL, CLIP und alle VAEs. Standardmäßig läuft das Diffusionsmodell auf der R9700 (`gpu:0`) und wird dort anschließend mit der Turbo-LoRA gepatcht; Qwen3VL, Video-VAE und Audio-VAE liegen auf der RX 9070 XT (`gpu:1`). Die Auswahl wird in jeden versteckten Segment-Graphen übernommen und kann vor dem Queue-Lauf manuell geändert werden. Dafür muss ComfyUI mit beiden sichtbaren HIP-Geräten gestartet sein. Die versionierten Starter liegen unter `tools/start-MultiGPU.ps1` und `tools/start-MultiGPU.bat`; sie können direkt verwendet oder nach `L:\ComfyUI\` kopiert werden.

Die Schritte bleiben seriell und die VRAM-Speicher werden nicht zu einem 48-GB-Pool vereinigt. Die Platzierung reduziert vor allem Modellwechsel und VRAM-Druck auf der R9700.

## Turbo-Samplingprofil · v0.8.6

Alle H3-Workflows verwenden die vom Kompatibilitäts-Repository empfohlene Qualitätskonfiguration: LoRA-Stärke 1,0, 8 Schritte, Euler-Sampler, Beta-Scheduler, Video-Sigma-Shift 12 und Audio-Sigma-Shift 4. Vier Schritte sind schneller, acht Schritte sind für die v4-Step-600-EMA-Konvertierung ausdrücklich als bessere Ausgangskonfiguration empfohlen.

Die LoRA wurde live mit beiden lokalen pruned INT8-ConvRot-Modellen geprüft: FL2VA und Ref2VA luden ohne ungelöste LoRA-Keys und erzeugten über den Dual-GPU-Server jeweils fünf dekodierte Testframes. Ref2VA-Turbo bleibt hinsichtlich Referenztreue eine Community-/Kompatibilitätskombination und sollte für lange Produktionen zuerst mit einem kurzen Referenzsegment geprüft werden.

## Bedienung

1. `song`: Musikdatei auswählen/hochladen.
2. `reference_image`: für eine feste Sängerin auswählen.
3. `reference_strategy = identity lock (recommended)`: übergibt in jeder Szene ausschließlich das unveränderte Originalbild als Identitäts-, Kleidungs- und Stilreferenz. So wird kein bereits gedriftetes Endbild als zweite Figur eingespeist. `previous-frame continuity` und `both references (experimental)` bleiben für Sonderfälle verfügbar.
4. `force_reference_as_first_frame = true`: setzt eine uncropped Contain-Version des Referenzbilds deterministisch als Frame 1 der ersten Szene ein. Für ein 9:16-Bild empfiehlt sich 480×864.
5. `master_visual_concept`: eine feste Location-Familie und Bildsprache beschreiben. Variationen auf Kamera und subtile Performance begrenzen.
6. `lyrics_or_story_optional`: optionaler semantischer Inhalt. Normale Zeilen werden zeitlich verteilt; LRC-artige Zeilen wie `[02:17.40] Text` werden zeitlich zugeordnet.
7. Queue einmal starten.

Der Master-Job analysiert und startet die Job-Kette. Danach erzeugt jeder erfolgreiche Szenenjob automatisch den nächsten. Erst nachdem alle Clips als gültig bestätigt wurden, wird der Finalizer eingereiht.

## Was die Analyse tatsächlich versteht

Die automatische Analyse misst unter anderem Lautstärke/Energie, spektrale Helligkeit, Transienten, Strukturwechsel und ein geschätztes Tempo. Sie kann **nicht zuverlässig den semantischen Inhalt gesungener Lyrics erkennen**. Dafür ist das optionale Textfeld da.

Mit `scene_prompt_planner = local OpenAI-compatible LLM` kann ein lokales Modell an `http://127.0.0.1:8080/v1` aus Konzept, Text und Segmentmerkmalen einen zusammenhängenderen Szenenplan schreiben. Schlägt das LLM fehl, wird automatisch der deterministische Planer verwendet.

## Segmentierung und Audio

- Standardziel: ungefähr 10 Sekunden, Grenzen 7–13 Sekunden; für sichere H3-Läufe `max_scene_seconds` höchstens 15 Sekunden setzen.
- Schnitte werden möglichst auf starke Beats/Taktanfänge oder Strukturwechsel gelegt.
- Jede Szene wird für H3 auf das gültige `17k+5`-Raster bei 24 fps aufgerundet.
- Nur die exakt benötigten Zielframes werden gespeichert; die Summe aller Szenenframes entspricht der Songdauer auf dem 24-fps-Raster.
- H3-generiertes Audio wird nie verwendet.
- Beim finalen Mux wird der ursprüngliche Audiostream mit FFmpeg `-c:a copy` übernommen: keine Normalisierung, kein Resampling, kein Audiofilter, keine erneute Audiokodierung.
- Standardausgabe ist MKV, weil dieser Container auch WAV/PCM, FLAC, Opus, MP3 und AAC zuverlässig per Stream-Copy aufnehmen kann. MP4 funktioniert nur, wenn der Original-Audiocodec MP4-kompatibel ist.

## Resume und Dateipfade

Projektstatus und Szenenplan:

```text
ComfyUI/output/DaWasteh_H3_MusicVideo_Projects/<Projekt-ID>/
├── manifest.json
├── scene_plan.json
├── source_audio.<Original-Endung>
├── first_frame_reference.png
├── joined_video.<container>          # fertiger Film MIT Originalaudio
├── joined_video_silent.mp4           # klar benannter interner Video-Zwischenstand
├── segment_audio/
├── segments/
└── continuity/
```

`joined_video.<container>` ist das direkt sichtbare Projekt-Deliverable mit Originalaudio. Der Finalizer kopiert es byte-identisch zusätzlich nach:

```text
ComfyUI/output/video/MiniMax_H3_MusicVideo/<Projekt-ID>/<Projektname>.mkv
```

Das Manifest nennt beide Pfade ausdrücklich als `joined_deliverable_path` und `final_output_path`; `silent_concat_path` bezeichnet nur den tonlosen internen Zwischenstand.

Bei einem OOM oder sonstigen Fehler denselben Master-Workflow erneut starten. Gültige Clips werden erkannt. Mit Kontinuität werden ab dem ersten fehlenden Clip alle späteren Clips neu gerechnet, weil sie vom vorherigen Endbild abhängen. `force_rebuild = true` löscht das konkrete Projekt und beginnt vollständig neu.

## Grenzen

- Das ist eine lokale Queue-Orchestrierung, kein einzelner fünf Minuten großer H3-Latent. Genau dadurch bleibt der VRAM-Bedarf pro Szene begrenzt.
- Visuelle Kontinuität über viele unabhängige generative Shots ist nicht garantiert. Der neue Identity-Lock vermeidet die besonders riskante Mischung aus Original und rekursiv gedriftetem Endframe, erzwingt eine Visual Bible und konservativere Anatomie-Prompts. Einzelne fehlerhafte Szenen können trotzdem einen gezielten Neulauf erfordern.
- Ein vollständiges Musikvideo besteht standardmäßig aus ungefähr 25–40 H3-Renders. Es ist entsprechend rechenintensiv.
- Der Master-Node zeigt den erwarteten Zielpfad sofort; die eigentliche Datei entsteht erst im automatisch eingereihten Finalizer.
