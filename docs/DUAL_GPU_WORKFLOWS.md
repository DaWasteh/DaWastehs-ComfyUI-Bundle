# Optionale GPU-Platzierung · R9700 + RX 9070 XT · v1.0.0

Seit v0.9.2 gibt es keinen getrennten Ordner `Dual GPU - R9700 + RX 9070 XT` mehr. Die GPU-Steuerung ist direkt in **allen 234 kanonischen Workflows** enthalten. Dadurch existiert pro Aufgabe nur noch ein Workflow, dessen Gerätebelegung vor dem Queue-Lauf geändert werden kann.

## Gerätezuordnung

| ComfyUI/HIP-Gerät | Physische GPU | Standardrolle in kuratierten Split-Profilen |
|---|---|---|
| `gpu:0` | AMD Radeon AI PRO R9700 · 32 GB | großes Diffusionsmodell/UNET und Sampling |
| `gpu:1` | AMD Radeon RX 9070 XT · 16 GB | CLIP/Textencoder sowie Bild-, Video- und Audio-VAE |

Diese Indizes sind HIP-/PyTorch-Indizes und nicht mit der Vulkan-Reihenfolge anderer Programme gleichzusetzen. Die Verteilung erzeugt keinen gemeinsamen 48-GB-VRAM-Pool und führt Graphstufen nicht automatisch parallel aus.

## Zentraler Control-Node in jedem Workflow

Jeder Workflow besitzt genau einen Root-Node:

```text
DaW Multi-GPU Device Control
```

Seine Dropdowns `model_device`, `clip_device` und `vae_device` steuern alle kompatiblen offiziellen `Select Model Device`, `Select CLIP Device` und `Select VAE Device`-Nodes, auch innerhalb eingebetteter Subgraphs.

- **30 explizit kuratierte Profile** einschließlich der beiden Pixal3D-Graphen behalten ihre festgelegte Geräteaufteilung.
- **202 übrige Workflows** starten mit MODEL, CLIP und VAE vollständig auf `gpu:0`, der R9700.
- Reine Utility-Graphen und proprietäre Modellobjekte besitzen den zentralen Control-Node ebenfalls, aber ohne vorgetäuschte Verbindungen zu inkompatiblen Objekten.

YuE, HeartMuLa, MOSS-TTS und Qwen-TTS geben keine standardisierten ComfyUI-Objekte vom Typ MODEL, CLIP oder VAE aus. Offizielle Selector-Nodes können diese Objekte nicht zuverlässig umplatzieren. Der Control-Node bleibt dort bewusst passiv; standardisierte Modell-/LLM-Loader im selben Workflow dürfen trotzdem korrekt angebunden sein.

MiniMax Music 3 bleibt die dokumentierte Ausnahme zur üblichen Split-Belegung: Der große BF16-Autoregressions-/Text-Stack läuft auf `gpu:0` (R9700), während FP32-Flow-Matching-DiT und DAV auf `gpu:1` (RX 9070 XT) liegen. Der zentrale Node startet daher mit `MODEL=gpu:1`, `CLIP=gpu:0`, `VAE=gpu:1`.

## Funktionale Ablage statt Dual-GPU-Sonderordner

Die früher ausschließlich im Dual-GPU-Ordner vorhandenen offiziellen Template-Graphen liegen jetzt hier:

```text
workflows/Text to Video/LTX25_INT8_ConvRot-Text-to-Video.json
workflows/Text+Image to Video/LTX25_INT8_ConvRot-Image-to-Video.json
workflows/Text+Image to Video/LTX25_INT8_ConvRot-First+Last-Frame-to-Video.json
workflows/Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json
```

Alle anderen früheren Dual-GPU-Varianten wurden in ihren bereits vorhandenen kanonischen Workflow integriert, statt als Duplikat erhalten zu bleiben.

Die redundanten Dateien

```text
MiniMax_H3_Spectrum_FL2VA_All_Supported_Inputs.json
MiniMax_H3_Spectrum_FL2VA_MAXIMUM_All_Supported_Inputs.json
```

wurden entfernt. `MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json` deckt ihre FL2VA-Eingaben bereits ab und besitzt nun selbst die optionale zentrale GPU-Steuerung.

## Start auf Port 8188

Die versionierten Starter liegen unter:

- `tools/start-MultiGPU.ps1`
- `tools/start-MultiGPU.bat`

Für die lokale Installation werden sie nach `L:\ComfyUI\` kopiert. Das Profil v0.9.8 verwendet:

- `HIP_VISIBLE_DEVICES=0,1`
- `CUDA_VISIBLE_DEVICES=0,1` als PyTorch-ROCm-Kompatibilitätsvariable; seit ComfyUI 0.34 erzwingt `main.py` unter Windows sonst eine einzelne GPU
- `--default-device 0`
- Port `8188`
- `user/comfyui-multigpu.db`
- `TORCH_BLAS_PREFER_HIPBLASLT=1`: auf gfx1201 gemessen 100–122 TFLOPS bei Transformer-GEMMs statt 60–95 TFLOPS mit klassischem hipBLAS; die früheren `HIPBLAS_STATUS_NOT_SUPPORTED`-Warnfluten für YuE-/HeartCodec-Conv1d-Formen treten mit PyTorch 2.13 nicht mehr auf
- Pinned Memory bleibt aus (`$DisablePinnedMemory = $true`): gemessen zwar 26 GiB/s Host→GPU statt 16 GiB/s pageable, aber ComfyUI pinnt bis zu 40 % des Host-RAM (19 GB von 48 GB); mit einem parallel residenten 27B-llama-server (31 GB Commit) swappte der Host und Wan 2.2 14B fiel auf 765 s pro Schritt. Nur bei freiem Host-RAM einschalten
- DynamicVRAM (comfy-aimdo 0.5.2) blieb auf der R9700 trotz 27 GB nutzbarem VRAM über acht Minuten ohne GPU-Last in „Model Initializing“ hängen, während der statische Loader denselben Z-Image-Graphen in 84 s beendete; `$EnableDynamicVram` bleibt deshalb aus und wird nach jedem ComfyUI-/aimdo-Update neu geprüft, weil ComfyUI `--disable-dynamic-vram` entfernen will
- `--cache-ram` statt `--cache-classic`: der RAM-druckabhängige Standard-Cache vermeidet die in v0.9.7 dokumentierte Host-RAM-Erschöpfung bei mehreren großen Pixal3D-Läufen
- `--disable-dynamic-vram` und `--disable-async-offload` bleiben als Schalter im Skript (`$EnableDynamicVram`, `$AsyncOffloadStreams`); die gemessenen Standardwerte stehen im Skriptkopf
- Opt-in-Schalter: `$UseComfyKitchenAttention` (`--use-ck-attention`, INT8-QK-Attention der comfy-kitchen-HIP-Kernel) und `$FastFp8MatrixMult` (`--fast fp8_matrix_mult`, `torch._scaled_mm` mit 117 TFLOPS gemessen); beide bleiben wegen des Qualitäts-Trade-offs standardmäßig aus

Vor dem Start prüft das Skript die erwartete Reihenfolge:

```text
gpu:0 = AMD Radeon AI PRO R9700
gpu:1 = AMD Radeon RX 9070 XT
```

Während eines schweren Jobs sollte kein weiterer GPU-intensiver Server gleichzeitig um die RX 9070 XT konkurrieren.

## LTX-2.5, Wan Animate 2, MiniMax Music 3 und Pixal3D

Die offiziellen Quelltemplates sind bytegenau unter `tools/workflow_templates/` gepinnt; Paketversionen, Upstream und SHA-256-Werte stehen in `tools/workflow_templates/README.md`.

- LTX-2.5 nutzt INT8-ConvRot-DiT und -Textencoder sowie die lokalisierten Modellunterordner.
- Wan Animate 2 nutzt den speichersicheren CPU-/INT8-Pose-Cache; CLIP-Vision bleibt mangels kompatiblem CLIP-Ausgang unverändert.
- MiniMax Music 3 nutzt den vorhandenen FP32-DiT, BF16-Textencoder und DAV.
- Pixal3D nutzt das offizielle kombinierte Pixal3D-/TRELLIS.2-Template als SHA-256-gepinnte Quelle; die beiden Game-Development-Graphen reduzieren es deterministisch auf den Pixal3D-INT8-Pfad und starten wegen der 32-GB-Anforderung vollständig auf `gpu:0`.

Die v0.9.0-Abnahmeläufe für LTX-2.5 T2V/I2V/FLF2V und Wan Animate 2 endeten jeweils mit `execution_success` und nichtleeren MP4-Dateien. Der v0.9.1-MiniMax-Music-3-Test bestätigte sowohl vollständige R9700-Belegung als auch die kuratierte verteilte Belegung bis zu einer nichtleeren 7,988-Sekunden-Stereo-FLAC. Diese historischen Smoke-Nachweise gelten weiterhin für die unveränderte Rechentopologie; v0.9.2 konsolidiert Ablage, Steuerung und Layout.

## Regeneration und Prüfung

```powershell
python tools/migrate_workflows_v092.py --check
python tools/consolidate_ace_autosongwriters_v093.py --check
python -m unittest tests.test_dual_gpu_workflows tests.test_rodent_layout tests.test_duration_seconds tests.test_ace_autosongwriter_consolidation
python tools/validate_workflows.py --against-head
# Nach dem v0.9.7-Commit die Änderungen gegen den vorherigen Release reproduzieren:
python tools/validate_workflows.py --against-head --baseline-ref v0.9.6
```

Der Validator rekonstruiert GPU-Controls, Sekundensteuerung, RODENT-Layout, die v0.9.3-AutoSongwriter-Konsolidierung, den v0.9.4-Wan-Animate-2-Umbau, die drei aus v0.9.4-Quellen abgeleiteten v0.9.5-Godot-/Live-Voice-Workflows, die v0.9.6-Low-Poly-LOD-Kette sowie beide v0.9.7-Pixal3D-Additionen deterministisch aus dem gewählten Basis-Ref. Er prüft zusätzlich die erwarteten Löschungen, zwei Genre-Selector-Ziele und sechs gepinnte Template-Neuzugänge. Statische Tests sichern Topologie und Geräteverbindungen; beide Pixal3D-Profile wurden darüber hinaus real auf Windows-ROCm bis zum in Blender und Godot importierten PBR-GLB ausgeführt.
