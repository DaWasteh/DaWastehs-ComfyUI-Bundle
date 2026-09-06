# ENVIRONMENT · verifiziert am 2026-09-05

Alle Angaben wurden lokal auf dem tatsächlich benutzten System ermittelt (Befehle in Klammern). Historische Angaben aus der Auftragsdatei, die nicht mehr stimmen, stehen unter „Abweichungen".

## Installation

| Punkt | Wert |
|---|---|
| ComfyUI-Wurzel | `L:\ComfyUI\ComfyUI` (git, HEAD `250b2e95`, Version 0.34.0, `deploy_environment: local-git`) |
| Lokale Änderung im ComfyUI-Baum | nur `comfy/samplers.py` (RDNA4-Sync in `_calc_cond_batch_multigpu`, identisch mit `L:\ComfyUI\multigpu-rdna4-samplers.patch`); gesichert als `baseline_state/comfyui_worktree.diff` |
| Interpreter | `L:\ComfyUI\.venv\Scripts\python.exe` = Python 3.13.13 (MSC v.1944, 64 bit) |
| Startskript (produktiv) | `L:\ComfyUI\start-MultiGPU.ps1` (byteidentisch mit `tools/start-MultiGPU.ps1` im Repo, Profil v0.9.8) über `L:\ComfyUI\scripts\windows_comfy_launcher.py` |
| Produktiv-Argv (aus `/system_stats` der laufenden 8188-Instanz) | `--enable-manager --listen 127.0.0.1 --port 8188 --database-url sqlite:///L:/ComfyUI/ComfyUI/user/comfyui-multigpu.db --default-device 0 --use-pytorch-cross-attention --reserve-vram 4 --disable-dynamic-vram --disable-async-offload --disable-pinned-memory --cache-ram` |
| Produktiv-Umgebung | `HIP_VISIBLE_DEVICES=0,1`, `CUDA_VISIBLE_DEVICES=0,1`, `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`, `TORCH_BLAS_PREFER_HIPBLASLT=1`, OMP/MKL/OpenBLAS/NUMEXPR-Threads = 24 |
| Weitere Startskripte | `start-R9700.ps1` (Solo, Port 8188, hipBLAS klassisch, `--cache-classic`), `start-9070XT.ps1` (Solo, Port 8189, DynamicVRAM + async offload + pinned an, `--fp16-unet`) – beide nicht die aktuell benutzte Konfiguration |
| Modelle | `L:\ComfyUI\ComfyUI\models` (kein `extra_model_paths.yaml`); diffusion_models 754 GB, text_encoders 325 GB, checkpoints 141 GB, loras 37 GB, vae 33 GB |
| Workflows | Repo `L:\GitHub\DaWastehs-ComfyUI-Bundle\workflows` (234 JSON) → per Updater nach `L:\ComfyUI\ComfyUI\user\default\workflows\DaWasteh\` synchronisiert |
| Datenträger | L: 926 GB frei (ComfyUI, Repo); C: 1351 GB frei; weitere NVMe D/E/F/G mit 1,9–7,5 TB frei |

## Pakete (venv, `pip freeze` in `baseline_state/pip_freeze_venv.txt`, 352 Pakete)

| Paket | Version |
|---|---|
| torch | 2.13.0+rocm10.1.0a20260822 (HIP 7.16.26332, ROCm-Nightly) |
| torchvision / torchaudio | 0.28.0 / 2.11.0.2 (+rocm10.1.0a20260822) |
| comfy-kitchen | 0.2.31 (Backends: `hip` aktiv/WMMA, `eager` aktiv, `cuda` vorhanden aber deaktiviert, `triton` fehlt: „No module named 'triton'") |
| comfy-aimdo | 0.5.2 |
| comfyui-frontend-package | 1.51.9 |
| triton / triton-windows | nicht installiert |
| xformers / flash-attn / sageattention | nicht installiert |
| onnxruntime-directml | 1.24.4 |
| transformers / peft / accelerate / bitsandbytes | 4.57.6 / 0.19.1 / 1.13.0 / 0.50.0 |
| numpy / safetensors / gguf | 2.4.4 / 0.8.0 / 0.19.0 |
| av / imageio-ffmpeg | 17.1.0 / 0.6.0 (ffmpeg 7.1 Binary, kein ffprobe) |

## Hardware und GPU-Zuordnung

| Punkt | Wert |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| CPU | 24 logische Kerne (`[Environment]::ProcessorCount`) |
| RAM | 48 504 MB sichtbar (47,4 GiB); beim Start der Messungen 33,9 GB frei |
| GPU-Treiber | AMD 32.0.31021.6002 (beide Karten) |
| HIP/torch-Reihenfolge | `cuda:0` = AMD Radeon AI PRO R9700, gfx1201, 32 CUs, 31,9 GiB, PCI-Bus 8 · `cuda:1` = AMD Radeon RX 9070 XT, gfx1201, 32 CUs, 15,9 GiB, PCI-Bus 4 |
| PDH/DirectML-LUIDs | `0x199af` = R9700 (PCI\VEN_1002&DEV_7551), `0x16581` = RX 9070 XT (DEV_7550); DirectML-Gerät 0 = 9070 XT, 1 = R9700 (andere Reihenfolge als HIP) |
| Peer-Access | `torch.cuda.can_device_access_peer` 0↔1 = False (Transfers laufen über den Host) |
| iGPU | Intel Graphics (nicht verwendet) |
| SDPA-Backends (torch) | flash=True, mem_efficient=True, math=True; ComfyUI: „Using pytorch attention", `ENABLE_PYTORCH_ATTENTION=True` über die gfx1201/ROCm≥7-Regel in `model_management.py` |
| BLAS | `torch.backends.cuda.preferred_blas_library()` = Cublaslt (= hipBLASLt) |
| bf16 | unterstützt |
| Fremdprozesse | AutoTuner.exe (2 Prozesse, ohne llama-server zum Messzeitpunkt), Windows-Desktop nutzt ~3 GB der 9070 XT |

## Benchmark-Instanz

- Port 8190, `performance/rdna4/bench/comfy_server.py`; identische Argumente wie produktiv, zusätzlich `--output-directory`, `--temp-directory`, eigene SQLite-DB unter `bench/bench_state/`, `--extra-model-paths-config bench/extra_model_paths_bench.yaml` (lädt nur den Probe-Node `rdna4_bench_probe`), ohne `--enable-manager`.
- Serverstart bis `/system_stats` erreichbar: 14,3 s. Custom-Node-Importfehler wie produktiv: `comfyui-kjnodes/nodes/triton_vae.py` (kein Triton, nur der PatchTritonVAE-Node fehlt).

## Abweichungen von historischen Angaben in der Auftragsdatei

- `H:\ComfyUI` existiert nicht mehr; produktiv ist ausschließlich `L:\ComfyUI\ComfyUI`.
- PyTorch ist nicht mehr `2.13.0a0+rocm7.13.0a20260416`, sondern `2.13.0+rocm10.1.0a20260822` (HIP 7.16).
- Das alte R9700-Profil (`HIP_VISIBLE_DEVICES=0`, `--cache-none`, `--reserve-vram 2`) ist nicht das aktuelle Profil; produktiv läuft das Dual-GPU-Profil v0.9.8 mit `--reserve-vram 4`, `--cache-ram`, beide GPUs sichtbar, `--default-device 0`.
