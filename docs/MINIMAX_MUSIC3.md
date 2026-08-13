# MiniMax Music 3 · lokale Workflows

## Modelle

Quelle: [`Comfy-Org/MiniMax-Music-3`](https://huggingface.co/Comfy-Org/MiniMax-Music-3)

```text
ComfyUI/models/diffusion_models/MiniMax Music 3/minimax_music3_dit_fp32.safetensors
ComfyUI/models/text_encoders/MiniMax Music 3/minimax_music3_text_encoder_bf16.safetensors
ComfyUI/models/vae/MiniMax Music 3/minimax_music3_dav.safetensors
```

Die Workflows verwenden bewusst den vollständigen FP32-DiT und vollständigen BF16-Textencoder, die lokal vorhanden sind. Das gepinnte offizielle Quelltemplate `tools/workflow_templates/audio_minimax_music_3.json` hat SHA-256 `0322153265b3e785961511b7849f6659f46a8fa7e8cb66976e5279ff1774b228`.

## Text-to-Music

```text
workflows/Music Generation/MiniMax_Music3_FP32-BF16-Text-to-Music.json
```

Der Workflow übernimmt die offizielle Music-3-Topologie: strukturierte Caption + getaggte Lyrics → nativer Music-3-Textencoder → 30 Euler/Simple-Schritte → DAV-Audiodecode → MP3. Der Standard ist 60 Sekunden; Music 3 unterstützt bis ungefähr 300 Sekunden. Für lange Songs reduziert `tiled_decode=true` den VAE-VRAM-Bedarf.

Der Live-Smoke-Test am 2026-08-14 verwendete eine instrumentale Caption, vier Sekunden Maximaldauer, alle 30 ausgelieferten Euler-/Simple-Schritte und tiled DAV decode. ComfyUI meldete `execution_success` nach 32,55 Sekunden und speicherte ein nichtleeres, endliches 44,1-kHz-Stereo-FLAC mit 7,988 Sekunden Laufzeit.

## Dual GPU

```text
workflows/Dual GPU - R9700 + RX 9070 XT/MiniMax-Music3-DualGPU-Text-to-Music.json
```

Vollpräzisionsbelegung:

| Komponente | Gerät |
|---|---|
| BF16-Autoregressions-/Text-Stack (`CLIP`) | `gpu:0` · R9700 · 32 GB |
| FP32-Flow-Matching-DiT (`MODEL`) | `gpu:1` · RX 9070 XT · 16 GB |
| DAV (`VAE`) | `gpu:1` · RX 9070 XT · 16 GB |

Das ist eine Platzierung, kein gemeinsamer 48-GB-VRAM-Pool. Alle drei Werte bleiben im zentralen `DaW Multi-GPU Device Control` änderbar.

Der echte Dual-GPU-Smoke-Test am 2026-08-14 expandierte den Subgraph über ComfyUIs Browser-Serializer und endete nach 38,89 Sekunden mit `execution_success`. Das Serverlog bestätigte den vollständigen 17.605,78-MB-Textstack auf `cuda:0`, einen Deepclone des Music-3-MODEL nach `cuda:1` sowie einen Deepclone und vollständigen Load des DAV nach `cuda:1`. Die Ausgabe ist ein nichtleeres, endliches 44,1-kHz-Stereo-FLAC mit 7,988 Sekunden Laufzeit.

## Offizieller Caption-Enhancer

```text
workflows/Prompt Enhancer/MiniMax_Music3-Official-Skill-Caption-Enhancer.json
```

Nur die beiden grünen Felder bearbeiten:

1. Musikidee/Caption
2. optionale getaggte Lyrics

Der Qwen-3.5-4B-Workflow gibt ausschließlich `### Global Metadata`, `### Vocal Details` und `### Arrangement` aus. Das Ergebnis in das Caption-Feld des Music-3-Workflows kopieren; die Lyrics separat unverändert in dessen Lyrics-Feld übernehmen. Der Live-Test am 2026-08-14 endete nach 33,07 Sekunden mit `execution_success`, bewahrte Instrumental-/Keine-Gitarren-Vorgaben und alle vier übergebenen Abschnittstags und gab genau die drei Pflichtüberschriften ohne Lyrics-Zitate aus.

Die eingebetteten Quellen aus MiniMax' offiziellem `music-caption-rewriter` sind unter `prompt-libraries/MiniMax-Music3-Official-Skill/` gepinnt. Der Ein-Pass-ComfyUI-Adapter enthält Core-Skill und Genre-Router, aber nicht die ungefähr 1.000 vollständigen Upstream-Templates: `TextGenerate` besitzt keinen Dateisystemzugriff für deren progressive Auswahl und behauptet daher keine Template-Suche.

## LoRA-Training · derzeit technisch blockiert

MiniMax hat mit Stand 2026-08-14 keinen offiziellen Music-3-LoRA-Trainingsweg, keine Zielmodulliste und keinen Trainings-Dataset-/Adapter-Validierungsweg veröffentlicht. Zusätzlich ist der von ComfyUI geladene Music-3-DAV ausdrücklich decoder-only: `VAEEncodeAudio` kann damit keine echten Music-3-Trainingslatents erzeugen und bricht mit `MiniMax Music3 DAV cannot encode audio` ab.

Darum liefert dieses Bundle bewusst **keinen scheinbar funktionalen LoRA-Workflow** aus. Dafür werden mindestens ein echter Music-3-Audio-Latent-Encoder beziehungsweise offizielle vorcodierte Trainingslatents sowie eine verifizierte Adapter-Trainingsrecipe benötigt. Sobald MiniMax oder ComfyUI diese Grundlage veröffentlicht, kann ein ehrlicher Workflow ergänzt werden.

## Aktueller Prüfstatus

Statische JSON-/Topologie-, Determinismus-, Pfad-, Skill-Hash- und Repository-Tests sind vorhanden. Normaler Workflow, Dual-GPU-Workflow und Caption-Enhancer sind mit den vollständigen lokalen Gewichten live bestätigt. Die kurzen Smoke-Profile beweisen Loader, Textencoding, Geräteplatzierung, 30-Schritt-Sampling, DAV-Decoding und Dateiausgabe, aber keine Qualität oder Stabilität bei den ausgelieferten längeren Standarddauern.
