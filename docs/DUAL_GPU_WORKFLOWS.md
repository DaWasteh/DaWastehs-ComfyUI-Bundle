# Optionale GPU-Platzierung & RDNA4-Startprofil · v1.3.3

Die GPU-Steuerung ist direkt in **allen 269 Workflows** enthalten — pro Aufgabe existiert genau ein Workflow, dessen Gerätebelegung vor dem Start angepasst werden kann.

## Gerätezuordnung

| ComfyUI/HIP-Gerät | Physische GPU | Standardrolle in Split-Profilen |
|---|---|---|
| `gpu:0` | AMD Radeon AI PRO R9700 · 32 GB | Diffusionsmodell/UNET und Sampling |
| `gpu:1` | AMD Radeon RX 9070 XT · 16 GB | optional CLIP/Textencoder, VAE sowie temporärer `llama-server` (Qwen3.8 27B) |

Die Indizes sind HIP-/PyTorch-Indizes (nicht Vulkan). Die Verteilung erzeugt keinen gemeinsamen 48-GB-VRAM-Pool und führt Graphstufen nicht automatisch parallel aus.

## Zentraler Control-Node (`DaW Multi-GPU Device Control`)

Jeder Workflow besitzt genau einen Root-Node `DaW Multi-GPU Device Control`. Seine Dropdowns `model_device`, `clip_device` und `vae_device` steuern alle verbundenen Core-Nodes `Select Model Device`, `Select CLIP Device` und `Select VAE Device` (auch innerhalb von Subgraphs):

- **Bild-Workflows:** starten vollständig auf `gpu:0` (R9700). Ein Geräte-Split über `SelectCLIPDevice`/`SelectVAEDevice` erzeugt in ComfyUI einen Host-RAM-Deep-Clone und verlängert warme Läufe messbar ([`performance/rdna4/REPORT.md`](../performance/rdna4/REPORT.md)).
- **Kuratierte Split-Profile (Video/Audio):** behalten ihre getestete Aufteilung (u. a. LTX-2.5-VAE auf `gpu:1`, MiniMax Music 3 mit `MODEL=gpu:1`, `CLIP=gpu:0`, `VAE=gpu:1`).
- **Proprietäre Modell-Nodes** (YuE, HeartMuLa, MOSS-TTS, Qwen-TTS) geben keine standardisierten `MODEL`/`CLIP`/`VAE`-Objekte aus; der Control-Node bleibt dort bewusst passiv.

## Laufzeit-Patches in `ComfyUI-DaWasteh-MultiGPU-Control`

Beim ComfyUI-Start aktiviert das Node-Pack fünf zielgerichtete, per Umgebungsvariable abschaltbare Fixes (alle unter ComfyUI `0.46.0` geprüft):

| Modul | Wirkung | Abschalten |
|---|---|---|
| `vram_guard.py` | Begrenzt den HIP-Allokator je GPU auf „freier VRAM beim Start − 3 GiB“, verhindert Windows/WDDM-Spilling in den Host-RAM | `DAWASTEH_VRAM_GUARD=0` |
| `readonly_load.py` | Lädt `.safetensors` ab 1 GiB schreibgeschützt (`mmap.ACCESS_READ`), spart Windows-Commit-Charge (z. B. FLUX.2 dev FP8 mixed: 159 → 104–120 GiB) | `DAWASTEH_READONLY_SAFETENSORS=0` |
| `compute_dtype.py` | Erhält die unterstützten Rechentypen eines Modells nach `Select Model Device` (verhindert schwarze FP8-Bilder bei Qwen Image Edit, [ComfyUI #16682](https://github.com/Comfy-Org/ComfyUI/issues/16682)) | `DAWASTEH_COMPUTE_DTYPE_FIX=0` |
| `sam3_reload.py` | Ermöglicht das Verschieben des SAM3-Textencoders auf `gpu:1` ([ComfyUI #16675](https://github.com/Comfy-Org/ComfyUI/issues/16675)) | `DAWASTEH_SAM3_RELOAD_FIX=0` |
| `splat_inverse.py` | Teilt gebatchte `torch.linalg`-Aufrufe in `Render Splat` / `Splat to Mesh` auf ROCm in 32 768er-Chunks (verhindert `hipErrorInvalidConfiguration` über 65 535 Gaussians) | `DAWASTEH_SPLAT_LINALG_FIX=0` |

## Start auf Port 8188 (`start-MultiGPU.ps1`)

Versionierte Starter: `tools/start-MultiGPU.ps1` und `tools/start-MultiGPU.bat` (vom Updater nach `L:\ComfyUI\` verteilt).

- `HIP_VISIBLE_DEVICES=0,1` und `CUDA_VISIBLE_DEVICES=0,1` + `--default-device 0` (umgeht den Windows-Single-GPU-Zwang von ComfyUI)
- `TORCH_BLAS_PREFER_HIPBLASLT=1` (100–122 TFLOPS auf `gfx1201`) und `--use-pytorch-cross-attention` (AOTriton SDPA)
- `--cache-ram`, `--reserve-vram 4`, VRAM-Guard mit 3 GiB Reserve (`DAWASTEH_VRAM_GUARD_RESERVE_GIB=3`)
- `--disable-dynamic-vram`, `--disable-async-offload`, `--disable-pinned-memory` (statischer Loader; schützt den 48-GB-Host vor Paging/Hängern)
- Opt-in-Schalter im Skriptkopf: `$UseComfyKitchenAttention` (`--use-ck-attention`), `$FastFp8MatrixMult` (`--fast fp8_matrix_mult`)
- Automatische Erkennung des neuesten `b<Build>_hip_llama.cpp\build\bin\llama-server.exe` unter `L:\LAB\ai-local` für `Qwen3.8-27B-IQ4_XS` auf `gpu:1`

Vor jedem Start laufen ein CLI-Preflight gegen `comfy.cli_args` und eine HIP-Reihenfolgeprüfung (`gpu:0 = R9700`, `gpu:1 = RX 9070 XT`):

```powershell
L:\ComfyUI\start-MultiGPU.ps1 -CheckOnly
```

## Validierung

```powershell
L:\ComfyUI\.venv\Scripts\python.exe -B tools/validate_workflows.py --against-head
L:\ComfyUI\.venv\Scripts\python.exe -B -m pytest -q
```
