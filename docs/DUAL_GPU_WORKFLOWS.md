# Optionale GPU-Platzierung · R9700 + RX 9070 XT · v0.9.3

Seit v0.9.2 gibt es keinen getrennten Ordner `Dual GPU - R9700 + RX 9070 XT` mehr. Die GPU-Steuerung ist direkt in **allen 227 kanonischen Workflows** enthalten. Dadurch existiert pro Aufgabe nur noch ein Workflow, dessen Gerätebelegung vor dem Queue-Lauf geändert werden kann.

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

- **28 bereits kuratierte Profile** behalten ihre bewährte Geräteaufteilung.
- **199 übrige Workflows** starten mit MODEL, CLIP und VAE vollständig auf `gpu:0`, der R9700.
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

Für die lokale Installation werden sie nach `L:\ComfyUI\` kopiert. Das Profil verwendet:

- `HIP_VISIBLE_DEVICES=0,1`
- `CUDA_VISIBLE_DEVICES=0,1` als PyTorch-ROCm-Kompatibilitätsvariable
- `--default-device 0`
- Port `8188`
- `user/comfyui-multigpu.db`
- `--disable-dynamic-vram`, `--disable-async-offload`, `--disable-pinned-memory` und `--cache-classic`

Vor dem Start prüft das Skript die erwartete Reihenfolge:

```text
gpu:0 = AMD Radeon AI PRO R9700
gpu:1 = AMD Radeon RX 9070 XT
```

Während eines schweren Jobs sollte kein weiterer GPU-intensiver Server gleichzeitig um die RX 9070 XT konkurrieren.

## LTX-2.5, Wan Animate 2 und MiniMax Music 3

Die offiziellen Quelltemplates sind bytegenau unter `tools/workflow_templates/` gepinnt; Paketversionen, Upstream und SHA-256-Werte stehen in `tools/workflow_templates/README.md`.

- LTX-2.5 nutzt INT8-ConvRot-DiT und -Textencoder sowie die lokalisierten Modellunterordner.
- Wan Animate 2 nutzt den speichersicheren CPU-/INT8-Pose-Cache; CLIP-Vision bleibt mangels kompatiblem CLIP-Ausgang unverändert.
- MiniMax Music 3 nutzt den vorhandenen FP32-DiT, BF16-Textencoder und DAV.

Die v0.9.0-Abnahmeläufe für LTX-2.5 T2V/I2V/FLF2V und Wan Animate 2 endeten jeweils mit `execution_success` und nichtleeren MP4-Dateien. Der v0.9.1-MiniMax-Music-3-Test bestätigte sowohl vollständige R9700-Belegung als auch die kuratierte verteilte Belegung bis zu einer nichtleeren 7,988-Sekunden-Stereo-FLAC. Diese historischen Smoke-Nachweise gelten weiterhin für die unveränderte Rechentopologie; v0.9.2 konsolidiert Ablage, Steuerung und Layout.

## Regeneration und Prüfung

```powershell
python tools/migrate_workflows_v092.py --check
python tools/consolidate_ace_autosongwriters_v093.py --check
python -m unittest tests.test_dual_gpu_workflows tests.test_rodent_layout tests.test_duration_seconds tests.test_ace_autosongwriter_consolidation
python tools/validate_workflows.py --against-head
# Nach dem v0.9.3-Commit die Konsolidierung gegen den vorherigen Release reproduzieren:
python tools/validate_workflows.py --against-head --baseline-ref v0.9.2
```

Der Validator rekonstruiert GPU-Controls, Sekundensteuerung, RODENT-Layout und die v0.9.3-AutoSongwriter-Konsolidierung deterministisch aus dem gewählten Basis-Ref und prüft zusätzlich die erwarteten Löschungen, zwei Genre-Selector-Ziele und vier gepinnten Template-Neuzugänge. Statische Tests bestätigen Topologie und Geräteverbindungen, ersetzen aber keinen Windows-ROCm-Lauf mit den realen Modellgewichten.
