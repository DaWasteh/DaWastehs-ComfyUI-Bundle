# MiniMax H3 · Turbo-LoRA · 8 Schritte · bereitgestellte MiniMax-Prompt-Guides

## Gewählte LoRA

Für die beiden lokalen pruned/curve-form-H3-Modelle wird diese Konvertierung verwendet:

```text
Repository: drbaph/MiniMax-H3-Turbo-Lora-ComfyUI
Datei:     minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors
Größe:     620.285.592 Byte
SHA-256:   7098acf3ee75028fd9fcd948f50fcc8d995057fabb76f86bd3ca2c0ffc58e409
Lizenz:    Apache-2.0 laut Hugging-Face-Model-Card
Quelle:    https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI
```

Das Repository bezeichnet v4 Step-600 EMA als aktuelle General-Purpose-Empfehlung für pruned ComfyUI-H3-Modelle. Vier Schritte sind für maximale Geschwindigkeit vorgesehen; sechs sind ein Kompromiss; **acht Schritte** werden ausdrücklich als Qualitäts-Ausgangskonfiguration empfohlen.

Lokaler Zielpfad:

```text
L:\ComfyUI\ComfyUI\models\loras\MiniMax H3\minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors
```

Resumierbarer Download einschließlich Zielordner und harter Hash-Prüfung:

```powershell
$TargetDir = "L:\ComfyUI\ComfyUI\models\loras\MiniMax H3"
$Target = Join-Path $TargetDir "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
curl.exe -L -C - --retry 10 --retry-all-errors --retry-delay 3 `
  -o $Target `
  "https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI/resolve/main/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
if ($LASTEXITCODE -ne 0) { throw "LoRA download failed: ExitCode $LASTEXITCODE" }
& "L:\ComfyUI\.venv\Scripts\python.exe" -c "import hashlib,pathlib; p=pathlib.Path(r'$Target'); h=hashlib.sha256(p.read_bytes()).hexdigest(); print(p.stat().st_size,h); assert p.stat().st_size==620285592 and h=='7098acf3ee75028fd9fcd948f50fcc8d995057fabb76f86bd3ca2c0ffc58e409'"
if ($LASTEXITCODE -ne 0) { throw "LoRA size/SHA-256 verification failed" }
```

## Einheitliches Samplingprofil

Alle neun H3-Workflows verwenden:

| Parameter | Wert |
|---|---:|
| LoRA-Stärke | `1.0` |
| Schritte | `8` |
| Sampler | `euler` |
| Scheduler | `beta` |
| Video-Sigma-Shift | `12.0` |
| Audio-Sigma-Shift | `4.0` |

Die sichtbaren FL2VA-/Ref2VA-Graphen enthalten `LoraLoaderModelOnly` direkt zwischen `UNETLoader` und `MiniMaxH3SigmaShift`.

Der Complete-Song-Director erzeugt dieselbe Kette intern:

```text
UNETLoader
  → [Dual GPU: SelectModelDevice gpu:0]
  → LoraLoaderModelOnly · v4 Step-600 EMA · Stärke 1.0
  → MiniMaxH3SigmaShift · Video 12 / Audio 4
  → Spectrum-Patch
  → Euler / Beta / 8 Schritte
```

## Abgedeckte H3-Modelle

```text
models/diffusion_models/MiniMax H3/minimax_h3_fl2va_pruned_int8_convrot.safetensors
models/diffusion_models/MiniMax H3/minimax_h3_ref2va_pruned_int8_convrot.safetensors
```

Die LoRA-Konvertierung passt strukturell zu beiden pruned Modellen. FL2VA ist der klar dokumentierte Beispielpfad des LoRA-Repositories. Ref2VA lädt und sampelt lokal erfolgreich, seine Referenztreue mit Turbo bleibt jedoch eine Community-/Kompatibilitätskombination. Vor langen Ref2VA-Jobs ist deshalb ein kurzes reales Referenzsegment sinnvoll.

## Offene Dual-GPU-Graphen · v0.8.7

Zusätzlich zum Complete-Song-Director werden zwei normale, direkt editierbare Multi-GPU-Workflows ausgeliefert:

```text
workflows/Dual GPU - R9700 + RX 9070 XT/MiniMax-H3-FL2VA-DualGPU-All-Supported-Inputs.json
workflows/Dual GPU - R9700 + RX 9070 XT/MiniMax-H3-Ref2VA-DualGPU-All-Reference-Inputs.json
```

FL2VA stellt First/Last Frame und alle üblichen Generierungsparameter bereit. Ref2VA bewahrt die komplette offene Referenzmatrix des Quellworkflows mit neun Bildern, drei Videos, den zugehörigen Video-Audios und drei eigenständigen Audio-Referenzen. Beide platzieren das Diffusionsmodell vor der Turbo-LoRA auf `gpu:0` sowie Qwen3VL und beide VAEs auf `gpu:1`.

## Live-Prüfung auf beiden AMD-GPUs

Geprüft wurde mit einem ComfyUI-Prozess auf Port 8188:

```text
gpu:0 = AMD Radeon AI PRO R9700 · 32 GB
gpu:1 = AMD Radeon RX 9070 XT · 16 GB
Torch = 2.12.0+rocm7.15
```

Ergebnisse:

- FL2VA + Turbo-LoRA + 8 Schritte: erfolgreich, fünf Frames bei 320×320 dekodiert und gespeichert.
- Ref2VA + Turbo-LoRA + 8 Schritte: erfolgreich, fünf Frames bei 320×320 dekodiert und gespeichert.
- v0.8.7 FL2VA Open: mit zwei echten lokalen First-/Last-Frame-PNGs über den sichtbaren Dual-GPU-Graphen erfolgreich bis zu fünf Frames ausgeführt.
- v0.8.7 Ref2VA Open: mit einer echten lokalen Bildreferenz über den sichtbaren Dual-GPU-Graphen erfolgreich bis zu fünf Frames ausgeführt.
- Alle LoRA-Loader-Pfade liefen ohne `lora key not loaded`-Warnung.
- Modell und Sampling lagen auf `gpu:0`; Qwen3VL, Video-VAE und beim Ref2VA-Lauf Audio-VAE wurden nachweislich als Deepclone auf `gpu:1` erzeugt.

Die kleinen 5-Frame-Läufe prüfen Laden, LoRA-Kompatibilität, Dual-GPU-Platzierung, Conditioning, acht Sampling-Schritte und VAE-Decoding. Sie ersetzen keine visuelle Langzeitabnahme eines vollständigen 8–15-Sekunden-Clips.

## Vom Nutzer bereitgestellte MiniMax-Prompt-Guides

Der Nutzer hat beide Dateien ausdrücklich als direkt von MiniMax ausgegebene Promptregeln bereitgestellt. Eine öffentliche Upstream-URL oder Versionskennung war nicht Teil der Übergabe; deshalb werden Herkunft und Aktualität nicht darüber hinaus behauptet. Die Dateien bleiben bytegetreu im Repository und sind über ihre Hashes nachvollziehbar:

```text
VIDEO_PROMPT_WRITING_GUIDE_base_en.md
SHA-256 2cfebc096a6e08370f288d468d90b60f7f9bcb938f94bf090816e910e48e75fc

VIDEO_PROMPT_WRITING_GUIDE_ref_en.md
SHA-256 1e574f356716ad55612247ffb7bbccbcdb484ad96599d63c7dca1af186b1fab7
```

Die Regeln liegen unverändert unter:

```text
workflows/Reference to Video/VIDEO_PROMPT_WRITING_GUIDE_base_en.md
workflows/Reference to Video/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md
```

Daraus werden zwei eigenständige Workflows erzeugt:

```text
workflows/Prompt Enhancer/MiniMax_H3_Base_FL2VA-Official-Guide-Prompt-Enhancer.json
workflows/Prompt Enhancer/MiniMax_H3_Ref2VA-Official-Guide-Prompt-Enhancer.json
```

Beide verwenden das vorhandene lokale `Qwen/qwen3.5_4b_bf16.safetensors` über ComfyUIs `TextGenerate`-Node. Der kurze Nutzerwunsch kommt in den separaten `PixaromaPrompt`-Node; die Guide-Regeln bleiben geschützt im vorgeschalteten Formel-Node.

### Base / FL2VA

Der Workflow erzwingt:

```text
[optionale I2VA/FL2VA/L2VA-Ausrichtungsanweisung]

integrated_multimodal_description:
overall_soundscape:
non_diegetic_music:
```

Ein Live-Test erzeugte die korrekte FL2VA-Ausrichtungszeile für 0,00 und 8,00 Sekunden sowie alle drei Pflichtfelder.

### Ref2VA

Der Workflow erzwingt genau diese sechs Abschnitte:

```text
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

Der Ref2VA-Guide hat Vorrang. Der Base-Guide ist nur als Anhang für gemeinsame Shot-, Kamera-, Dialog- und Soundregeln enthalten. Da kleine lokale LLMs trotz ausdrücklicher Regel gelegentlich `[Shot 1] At 00:00.000,` schreiben, entfernt ein abschließender `RegexReplace` deterministisch nur diesen regelwidrigen ersten Zeitstempel. Spätere Shot-Zeitstempel bleiben unverändert.

Ein Live-Test bestätigte alle sechs Abschnitte und den bereinigten `[Shot 1]`-Beginn.

## Regeneration und Tests

```powershell
python tools/integrate_h3_turbo_lora.py
python tools/generate_h3_prompt_enhancers.py
python tools/generate_dual_gpu_workflows.py
python -m unittest tests.test_h3_turbo_and_prompt_guides
python -m unittest tests.test_h3_music_video_core
python tools/validate_workflows.py --against-head
```
