# Kompatibilitäts- und Skript-Audit · v1.3.3

**Prüfdatum:** 24. November 2026  
**Zielsystem:** Windows 11 · Intel Core Ultra 9 285K (24 Threads) · 48 GB RAM · `gpu:0` AMD Radeon AI PRO R9700 (32 GB, `gfx1201`) · `gpu:1` AMD Radeon RX 9070 XT (16 GB, `gfx1201`)

## Geprüfter Softwarestand (`L:\ComfyUI`)

| Komponente | Installierte Version |
|---|---|
| ComfyUI Core | `0.46.0` (Commit `da8bd08e4`, `origin/master` aktuell) |
| Python | `3.13.13` (`.venv`) |
| PyTorch / ROCm | `2.13.0+rocm10.1.0a20260822` (HIP `7.16.26332`) |
| `comfy-kitchen` | `0.2.42` (HIP-Backend aktiv) |
| `comfy-aimdo` | `0.6.0` |
| `comfyui-frontend-package` | `1.59.11` |
| `comfyui-workflow-templates` | `0.11.118` |
| `comfyui-manager` | `4.2.2` |
| `transformers` / `peft` / `diffusers` | `4.57.6` / `0.19.1` / `0.38.0` |
| `onnxruntime-directml` | `1.24.4` (`DmlExecutionProvider` aktiv) |

Lokaler Core-Patch `L:\ComfyUI\multigpu-rdna4-samplers.patch` (`comfy/samplers.py`) greift weiterhin sauber unter ComfyUI `0.46.0`.

## 1. Custom Nodes (11 Pakete · 71 Nodes)

Alle 11 eigenen Custom-Node-Packs wurden gegen eine isolierte ComfyUI-`0.46.0`-Instanz (echtes Startprofil, Port 8198/8199, eigene DB/Temp/Output) live geladen und über `/object_info` verifiziert:

- **11/11 Pakete ohne Import- oder Registrierungsfehler geladen** (insgesamt 71 registrierte DaWasteh-Nodes).
- **Alle 5 Laufzeit-Patches in `ComfyUI-DaWasteh-MultiGPU-Control` aktiv und signaturkompatibel:**
  - `vram_guard.py`: R9700 auf 28,69 / 31,86 GiB und RX 9070 XT auf 12,77 / 15,92 GiB begrenzt (3 GiB Reserve).
  - `compute_dtype.py`: Upstream-Issue [#16682](https://github.com/Comfy-Org/ComfyUI/issues/16682) ist in `0.46.0` weiterhin offen; der Patch greift sauber auf `SelectModelDeviceNode._force_supported_compute_dtype`.
  - `readonly_load.py`: `comfy.utils.load_torch_file`, `_TYPES`, `DISABLE_MMAP`, `comfy.memory_management.aimdo_enabled` und `comfy.storage.annotate_state_dict` unverändert; 3 Referenzen gepatcht.
  - `sam3_reload.py`: Upstream-Issue [#16675](https://github.com/Comfy-Org/ComfyUI/issues/16675) ist in `0.46.0` weiterhin offen; `SAM3.process_clip_state_dict` unverändert und sauber gepatcht.
  - `splat_inverse.py`: `RenderSplat` / `SplatToMesh` / `TransformSplat` auf ROCm weiter in 32 768er-Chunks.
- **`ComfyUI-DaWasteh-H3-MusicVideo` (`h3_highres.py`):** `install_patches()` gibt `True` zurück (`comfy.ldm.minimax.model._mod_scale_shift`, `_mod_gate`, `MLP.forward` sowie `comfy.sd`-Loader-Signaturen unverändert).
- **`ComfyUI-DaWasteh-Qwen3TTS-LoRA`:** `peft_compat.py` greift sauber; `qwen_tts_compat.py` unverändert.

## 2. Behobene Fremd-Node-Inkompatibilität (`MMH3UltimateUpscale`)

Beim Live-Abgleich aller 269 Workflows gegen `/object_info` von ComfyUI `0.46.0` fielen genau 4 fehlende Node-Klassen auf:

- `MMH3UltimateUpscale`, `MMH3LatentUpscaleWithModelParams`, `MMH3TemporalSplitParams`, `MMH3SpatialSplitParams`

**Ursache:** `Comfyui-PlagueKind-Nodes` hat in v1.6.0 (8. November 2026) das eingebettete `ComfyUI-H3-UltimateUpscale-LD` entfernt.

**Behebung in v1.3.3:** Migration auf den weiterentwickelten Nachfolger **`MMH3SplitUpscale`** (`MMH3TemporalSplitParamsV10`, `MMH3SpatialSplitParamsV10`) kombiniert mit `MinimaxH3LatentUpscaler3D` aus `Comfyui_Minimax_h3_latent_Upscaler` (LBH-123-AI, bereits installiert und vom Updater per Git verfolgt; gleiches 3D-Upscaler-Modell `minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors`):

- `custom_nodes/ComfyUI-DaWasteh-H3-MusicVideo/upscale_mv.py` (`ULTIMATE`-Methode in MV 5c, Version `1 → 2`)
- `tools/build_video_upscale_v123.py` und `workflows/Video Upscaling/MiniMax_FastH3_INT8-Video-Ultimate-Upscale.json`

Nach der Migration melden **269/269 Workflows** gegen `/object_info` **0 fehlende Node-Klassen**.

## 3. Start-, Stop- und Update-Skripte (`L:\ComfyUI`)

| Skript | Prüfung gegen ComfyUI `0.46.0` | Änderung in v1.3.3 |
|---|---|---|
| `start-MultiGPU.ps1` / `.bat` | `-CheckOnly` bestanden (CLI-Parser + beide HIP-GPUs in richtiger Reihenfolge); isolierter Serverstart in 16,6 s bereit; automatische `llama-server`-Erkennung findet `b12634_hip_llama.cpp` | Banner auf `v1.3.3` und Kopfkommentare auf `0.46.0` aktualisiert; Performance-Defaults unverändert |
| `start-R9700.ps1` / `start-R9700AIPro.bat` | Alle CLI-Flags von `0.46.0` akzeptiert; GPU `0` = R9700 | `-CheckOnly`, Port-Belegungsprüfung und CLI-Preflight ergänzt (Profil unverändert) |
| `start-9070XT.ps1` / `start-RX9070XT.bat` | Alle CLI-Flags von `0.46.0` akzeptiert; GPU `0` (HIP `1`) = RX 9070 XT | `-CheckOnly`, Port-Belegungsprüfung und CLI-Preflight ergänzt (Profil unverändert) |
| `stop-R9700.ps1/.bat`, `stop-9070XT.ps1/.bat` | Prozessprüfung passt exakt zum `windows_comfy_launcher.py`-Kommando | keine Änderung nötig |
| `scripts/windows_comfy_launcher.py` | Isoliertes `--temp-directory` und `SIGBREAK`-Bootstrap intakt | keine Änderung nötig |
| `update-comfyui-rdna4.ps1` / `.bat` | Produktivlauf vom 24.11.2026 (`update-20261124-174632.log`) sauber durchgelaufen; `transformers==4.57.6` erfüllt `requirements.txt` (`>=4.50.3`); `pip check` zeigt nur die zwei dokumentierten Absichts-Pins (`onnxruntime-directml` statt `onnxruntime`, `protobuf 5.29.6` für `insightface`/`onnx`) | Hilfetext und Log-Überschrift von „Pixaroma und Spectrum“ auf alle 6 externen GitHub-Node-Packs aktualisiert |

Hinweis zu `--disable-dynamic-vram`: ComfyUI `0.46.0` akzeptiert das Flag weiterhin mit einer Deprecation-Warnung. Es bleibt bis zu einem eigenen A/B-Test von `comfy-aimdo 0.6.0` bewusst aktiv; der CLI-Preflight in allen drei Startern bricht sauber vor dem Serverstart ab, falls Upstream das Flag künftig entfernt.
