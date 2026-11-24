# DaWastehs ComfyUI-Bundle · v1.3.3

Kuratierte, lokal getestete ComfyUI-Workflows, Custom Nodes und RDNA4-Start-/Update-Skripte für Windows 11 mit **AMD Radeon AI PRO R9700 (32 GB)** und **AMD Radeon RX 9070 XT (16 GB)** unter PyTorch/ROCm.

**Beispielgalerie (GitHub Pages):** <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/> — Quellen im Repo unter [`examples/`](examples/README.md) (269 Workflows mit Screenshots, Eingaben, Ergebnissen, kopierbaren Prompts, Laufzeiten und RAM-/VRAM-Werten).

## Geprüfter Stand · v1.3.3

- **ComfyUI Core:** `0.46.0` (Commit `da8bd08e4`)
- **Stack:** Python `3.13.13`, PyTorch `2.13.0+rocm10.1.0a20260822` (HIP `7.16.26332`), `comfy-kitchen 0.2.42`, `comfy-aimdo 0.6.0`, Frontend `1.59.11`
- **Custom Nodes:** alle **11 eigenen Node-Packs (71 Nodes)** sowie alle 5 Laufzeit-Patches in `ComfyUI-DaWasteh-MultiGPU-Control` und `peft_compat` in `ComfyUI-DaWasteh-Qwen3TTS-LoRA` unter ComfyUI `0.46.0` ohne Ladefehler geprüft
- **Workflows:** alle **269 Workflows in 33 Kategorien** gegen das Live-`/object_info` von ComfyUI `0.46.0` geprüft — **0 fehlende Nodes, 0 Validierungsfehler**
- **v1.3.3-Fix:** `Comfyui-PlagueKind-Nodes` hat in v1.6.0 `MMH3UltimateUpscale` entfernt. Sowohl `Video Upscaling/MiniMax_FastH3_INT8-Video-Ultimate-Upscale.json` als auch die Ultimate-Methode in `MV 5c` (`ComfyUI-DaWasteh-H3-MusicVideo`) nutzen jetzt den Nachfolger **`MMH3SplitUpscale`** (`MMH3TemporalSplitParamsV10`, `MMH3SpatialSplitParamsV10` + `MinimaxH3LatentUpscaler3D`) aus `Comfyui_Minimax_h3_latent_Upscaler` (LBH-123-AI, bereits vom Updater mitgepflegt).
- **Start-/Update-Skripte:** `start-MultiGPU.ps1`, `start-R9700.ps1`, `start-9070XT.ps1`, `stop-*.ps1`, `windows_comfy_launcher.py` und `update-comfyui-rdna4.ps1` gegen ComfyUI `0.46.0` geprüft (`-CheckOnly`-Preflight jetzt auch in den Solo-Startern). Details: [`docs/COMPATIBILITY_AUDIT_V133.md`](docs/COMPATIBILITY_AUDIT_V133.md).

## Start & Update (`L:\ComfyUI`)

Die versionierten Skripte liegen unter `tools/` und werden vom Updater mit Hash-Prüfung, Backup und Schutz eigener Änderungen nach `L:\ComfyUI\` verteilt:

```powershell
# Starten (Dual-GPU: gpu:0 = R9700, gpu:1 = RX 9070 XT, Port 8188)
L:\ComfyUI\start-MultiGPU.bat
L:\ComfyUI\start-MultiGPU.ps1 -CheckOnly        # CLI- & GPU-Preflight ohne Serverstart

# Update (ComfyUI-Core, externe GitHub-Nodes, Bundle-Workflows/-Nodes/-Launcher, pip/ROCm)
L:\ComfyUI\update-comfyui-rdna4.bat
L:\ComfyUI\update-comfyui-rdna4.ps1 -DryRun
L:\ComfyUI\update-comfyui-rdna4.ps1 -SkipUpstream -SkipDependencies
L:\ComfyUI\update-comfyui-rdna4.ps1 -RestoreFrom "L:\ComfyUI\_update_backups\<Zeitstempel>"
```

**Aktives RDNA4-Profil (`start-MultiGPU.ps1`, Performance-Profil v0.9.8):**

- `HIP_VISIBLE_DEVICES=0,1` + `CUDA_VISIBLE_DEVICES=0,1` + `--default-device 0` (verhindert Single-GPU-Zwang unter Windows)
- `TORCH_BLAS_PREFER_HIPBLASLT=1`, `--use-pytorch-cross-attention` (AOTriton SDPA), `--cache-ram`, `--reserve-vram 4`
- `--disable-dynamic-vram`, `--disable-async-offload`, `--disable-pinned-memory` (statischer Loader; schützt den 48-GB-Host vor Paging/Hängern)
- **VRAM-Guard aktiv** (`DAWASTEH_VRAM_GUARD=1`, 3 GiB Reserve je GPU): verhindert stilles Windows/WDDM-Spilling in den Host-RAM und erzwingt sauberes `torch.OutOfMemoryError`
- **Externer Prompt-LLM (`Qwen3.8 27B IQ4_XS`):** `start-MultiGPU.ps1` findet automatisch das neueste `b<Build>_hip_llama.cpp\build\bin\llama-server.exe` unter `L:\LAB\ai-local` und startet den Server auf `gpu:1` nur während des Schreibens (genutzt von MV 2, Ming Image und dem Bild-Prompt-Enhancer).

Vor echten Updates alle ComfyUI-Instanzen sauber beenden (`Strg+C` oder `stop-R9700.bat` / `stop-9070XT.bat`). Details zu Flags, Solo-Startern und Dual-GPU-Platzierung: [`docs/DUAL_GPU_WORKFLOWS.md`](docs/DUAL_GPU_WORKFLOWS.md) und [`docs/COMPATIBILITY_AUDIT_V133.md`](docs/COMPATIBILITY_AUDIT_V133.md).

## Eigene Custom Nodes (11 Pakete · 71 Nodes)

| Paket | Zweck | Dokumentation |
|---|---|---|
| `ComfyUI-DaWasteh-MultiGPU-Control` | Zentrale GPU-Dropdowns (`DaWMultiGPUDeviceControl`), Adaptive Load Image/Video sowie 5 RDNA4-/Core-Laufzeit-Fixes (VRAM-Guard, Read-only-Safetensors, `SelectModelDevice`-Compute-Dtype [#16682](https://github.com/Comfy-Org/ComfyUI/issues/16682), SAM3-Reload [#16675](https://github.com/Comfy-Org/ComfyUI/issues/16675), Render-Splat-Chunking) | [README](custom_nodes/ComfyUI-DaWasteh-MultiGPU-Control/README.md) |
| `ComfyUI-DaWasteh-H3-MusicVideo` | FastH3 Song → Musikvideo (Planer, Whisper-Timing, Qwen3.8-Prompt-Writer, Szenen-Prüfung MV 5b, optionaler Upscale MV 5c) + Video-Upscaling-Rahmen (VU 1–4, MultiDiffusion-Kacheln, Read-only-Loader) | [README](custom_nodes/ComfyUI-DaWasteh-H3-MusicVideo/README.md) |
| `ComfyUI-DaWasteh-H3-AutoLength` | Audio-/Referenzvideo-Längenberechnung auf das MiniMax-H3-Raster (`17k+5`) und verlustfreies Original-Audio-Muxing | [README](custom_nodes/ComfyUI-DaWasteh-H3-AutoLength/README.md) |
| `ComfyUI-DaWasteh-LiveAvatar` | Browser-VRM-Full-Body-Avatar, DirectML-Live-Face-/Person-Swap (Spout/OBS), Cached OpenPose, RVC-Live-Voice-Launcher, VRM-Texture-Creator | [README](custom_nodes/ComfyUI-DaWasteh-LiveAvatar/README.md) · [Anleitung](LIVE_AVATAR_ANLEITUNG.md) |
| `ComfyUI-DaWasteh-MingImage` | Ming Image 0.1 Design: offizielle Buckets, Qwen3.8-Prompt-Rewriter, Layer-Split, Alpha-Fallback (BiRefNet) | [README](custom_nodes/ComfyUI-DaWasteh-MingImage/README.md) |
| `ComfyUI-DaWasteh-MiraScene` | Foto → bearbeitbare 3D-Szene (SAM3-Masken, Mira-CCM, objektweises TRELLIS.2, Boden-/Schwerkraft-Platzierung, GLB-Export) | [README](custom_nodes/ComfyUI-DaWasteh-MiraScene/README.md) |
| `ComfyUI-DaWasteh-PromptEnhancer` | Entwurf → fertiger Bild-Prompt via Qwen3.8 27B (Fließtext, Text im Bild, Tags, Bearbeiten, optionales Bild) | [README](custom_nodes/ComfyUI-DaWasteh-PromptEnhancer/README.md) |
| `ComfyUI-DaWasteh-VisionTools` | SDPose-3:4-Personenrahmen, robuster Video-Batch-Loader, Masken-Wächter (`DaWRequireMask`), 16-Bit-Tiefenexport | [README](custom_nodes/ComfyUI-DaWasteh-VisionTools/README.md) |
| `ComfyUI-DaWasteh-GamePhysics` | CPU-Collision-Proxy (`ConvexPolygonShape3D` für Godot) und Frame-only-Video-Adapter | [README](custom_nodes/ComfyUI-DaWasteh-GamePhysics/README.md) |
| `ComfyUI-DaWasteh-AutoSongwriter` | Genre-Selector-Profile (BPM, Tonart, Sprache, Stilrichtung) für ACE-Step / HeartMuLa | [README](custom_nodes/ComfyUI-DaWasteh-AutoSongwriter/README.md) |
| `ComfyUI-DaWasteh-Qwen3TTS-LoRA` | PEFT-Voice-LoRA-Training & Inferenz für Qwen3-TTS sowie `peft_compat` / `qwen_tts_compat` | [README](custom_nodes/ComfyUI-DaWasteh-Qwen3TTS-LoRA/README.md) |

## Workflow-Übersicht (269 Workflows · 33 Kategorien)

| Kategorie | Anzahl | Schwerpunkt |
|---|---:|---|
| `Text to Image` | 46 | Ming Image 0.1 Design & RGBA, Qwen Image 2.1, FLUX.1/2, Krea 2, Z-Image, Ideogram 4, SDXL, Anima, Boogu, LongCat, Cosmos |
| `Image Editing` | 27 | Qwen Image 2.1 (Multi-Image Edit, Background Remover, AnyAngle 4-Winkel/Guide/Studio), Ming Image Edit, FLUX.2 Klein, Qwen Image Edit 2509/2511, Bernini, SDXL |
| `Music Generation` | 23 | ACE-Step 1.5 (Turbo/XL/INT8/LoRA/AutoSongwriter), HeartMuLa 3B, MiniMax Music 3, Stable Audio 3 (FP32/INT8), YuE 7B (FP16/INT8/ICL), YuE2 3B (privat) |
| `Live Avatar` | 19 | Browser-VRM (06), DirectML Live Face/Person Swap (16/17), LivePortrait/Spout (03–05, 12), Buffered AI Mirror (07/11), VRM-Creator & Turnarounds (08–10, 13–14) |
| `Prompt Tools` | 15 | Prompt Stack/Pack/Multi, Ideogram-4-Builder, Text-Tools, XY-Plot |
| `Image Utilities` | 13 | Ming Design-Layer, RMBG-2.0, LaMa Object Remover, Combine, Blend, Compare, Filter, Scale |
| `Prompt Enhancer` | 13 | Qwen3.8 27B Bild-Prompt-Enhancer, Gemma 4 / Qwen 3.5 Bild-/Audio-/Video-Verständnis, MiniMax H3 & Music 3 Enhancer |
| `Pixaroma Node Demos` | 12 | Kuratierte Pixaroma-Node-Beispiele |
| `Text+Image to Video` | 12 | LTX-2.3 (inkl. Director), LTX-2.5 INT8, WAN 2.2 (5B/14B FP8/Q8), Bernini-R, Kandinsky 5 Lite |
| `Voice Design` | 12 | Qwen3-TTS (CustomVoice, VoiceClone, VoiceDesign, Dialog, LoRA-Live), MOSS-TTS v1.5, DirectML-RVC Live-Mikrofon |
| `Game Development` | 9 | Pixal3D & TRELLIS.2 PBR/Shape + Godot-Collision (inkl. MultiView), Hunyuan3D Low-Poly LOD0–3, FLUX.2 PS1-Texturen |
| `LoRA Generation` | 8 | Bild-LoRAs (SDXL, Z-Image, FLUX.1, FLUX.2 Klein, Boogu), ACE-Step Voice-LoRA, Qwen3-TTS Voice-LoRA, YuE2 Stil-LoRA (privat) |
| `Reference to Video` | 6 | FastH3 Song → Musikvideo (One-Click mit Review & Upscale), MiniMax H3 FL2VA, Ref2VA, AutoLength |
| `Text to Video` | 6 | LTX-2.3 (Dev/Distilled FP8/MXFP8/Q8), LTX-2.5 INT8, WAN 2.2 14B |
| `Controlled Video` | 5 | Cosmos Predict2 2B (I2V, First+Last, Continuation, T2V), WAN 2.2 Fun Control 5B |
| `Image Inpainting` | 5 | Qwen Image 2.1 Mask-Inpaint (nativ & LanPaint 2.2), FLUX.2 Klein 4B/9B Inpaint |
| `Character Animation` | 4 | WAN 2.1 SCAIL-2 (Animation, Replacement, Long+DPO), Wan Animate 2 Motion Transfer |
| `NSFW` | 4 | Getrennte SDXL-Workflows |
| `Pose & Depth` | 4 | SDPose WholeBody & Depth Anything 3 Large (Bild & Video) |
| `Video Upscaling` | 4 | WAN 2.2 Low-Noise (MultiDiffusion), SeedVR2 3B INT8, MiniMax FastH3 Latent 3D & Split/Ultimate Upscale |
| `Audio to Video` | 3 | LTX-2.3 Bild+Audio → Video, FLUX.2 + Gemma 4 AudioReact, Pixaroma AudioReact |
| `Character & Consistency` | 3 | FLUX.1 Kontext, SDXL + IP-Adapter / FaceID |
| `Image Upscaling` | 3 | Z-Image Turbo Tiled Upscale, NMKD Siax 4×, Bicubic |
| `Image to 3D-Mesh` | 3 | Mira-Scene + TRELLIS.2 (Foto → 3D-Szene & Layout-Vorschau), Hunyuan3D 2.1 |
| `Batch Processing` | 2 | Ordner-Batch-Edit (FLUX.2 Klein 9B), Folder-to-Cropped-Images |
| `Einzelkategorien (8)` | 8 | Audio to Image, Image Fusion, Image Outpainting, Talking Video (InfiniteTalk), Templates & Tests, Video Editing (Bernini-R), Video to Audio (MMAudio), Vocal Separation (MelBand-RoFormer) |

## Benennung

Seit v1.3.1 folgen alle Modell-Workflows dem einheitlichen Schema:

`<Modell>[_<Variante>]_<Quant>[+<Hilfsmodell>]-<Eingabe>-to-<Ausgabe>[-<Zweck>].json`

| Teil | Bedeutung | Beispiele |
|---|---|---|
| Modell / Variante | Modellfamilie, Größe oder Finetune | `FLUX2_Klein_9B_KV`, `ZImage_Turbo`, `LTX23_22B_Distilled`, `Qwen_Image_2_1` |
| Quant | Geladene Gewichte | `BF16`, `FP16`, `FP32`, `FP8`, `FP8mixed`, `INT8`, `Q8_0`, `Q6_K`, `IQ4_XS` |
| `+Hilfsmodell` | Zweites Modell / LoRA / Adapter | `+Qwen3_5_4B`, `+AnyAngle_LoRA`, `+LanPaint`, `+IPAdapter` |
| Eingabe `-to-` Ausgabe | Richtung der Pipeline | `Text-to-Image`, `Image+Mask-Inpaint`, `Song+Lyrics-to-Music-Video` |
| Zweck | Optional zur Unterscheidung | `-Low-VRAM`, `-Director-2-Stage`, `-Character-Keep` |

Werkzeuge ohne eigenes Modell und die nummerierte Live-Avatar-Serie behalten ihre Namen. Die vollständige Alt→Neu-Zuordnung liegt in [`tools/workflow_renames_v131.json`](tools/workflow_renames_v131.json) und wird vom Updater automatisch migriert.

## Lokale Patches & Umgebungshinweise

- **ComfyUI-Core (`L:\ComfyUI\multigpu-rdna4-samplers.patch`):** Konservative HIP-Synchronisierung in `comfy/samplers.py` für nicht-NVIDIA-MultiGPU-Samplings; `git pull --ff-only --autostash` erhält den Patch bei Core-Updates.
- **YuE & HeartMuLa (`tools/patches/`):**
  - `ComfyUI_YuE-Windows-RDNA4-longform-ICL.patch` (SDPA statt Flash-Attention, 5–600 s Tokenplanung, optionaler `AUDIO`-Eingang)
  - `ComfyUI_YuE-Windows-long-genre-filenames.patch` (kürzt lange Genre-Dateinamen auf 60 Zeichen gegen Windows `OSError 22`)
  - `ComfyUI-HeartMuLa-600s-context.patch` (600 s Kontextplanung)
- **LivePortrait & KJNodes (`tools/patches/`):**
  - `ComfyUI-LivePortraitKJ-PyTorch-2.6-verified-landmark-load.patch` (SHA-256-geprüftes TorchScript-Landmark-Modell für PyTorch 2.6+)
  - `ComfyUI-KJNodes-WebcamCaptureCV2-Windows-Backend.patch` (explizite DirectShow-/MSMF-Wahl)
- **Abhängigkeits-Pins im Updater:** `qwen3-tts-constraints.txt` (`transformers==4.57.6`, `huggingface-hub==0.36.2`), danach `onnxruntime-directml>=1.24.4` (Last Writer Wins für `DmlExecutionProvider`), zuletzt `protobuf==5.29.6`, `ml_dtypes==0.6.0`, `insightface==1.0.1` (`--no-deps`).
- **Externe GitHub-Node-Packs (vom Updater gepflegt):** `ComfyUI-Pixaroma`, `comfyui-spectrum-minimax-h3`, `Comfyui-PlagueKind-Nodes`, `Comfyui_Minimax_h3_latent_Upscaler`, `LanPaint`, `ComfyUI-AnyAngle-Studio-T8` sowie gepinntes `third_party\Mira-Scene`.
- **Pixaroma Prompt-Bibliothek:** `prompt-libraries/DaWasteh-Pixaroma-Prompt-Library.json` (Import im Pixaroma-Tags-Editor oder via `python tools/install_pixaroma_prompt_library.py`).

## RDNA4-Leitlinien & Lokales LoRA-Training

- Keine NVIDIA-/CUDA-spezifischen Pfade (kein Nunchaku, `nvfp4`, TensorRT, xformers, Triton-Pflicht, `CUDAExecutionProvider` oder hartcodiertes `cuda:0`).
- **Bild-LoRA-Trainer (Core-Nodes, `LoRA Generation/`):** starten sicher mit 2 Schritten (`_smoke`), Rank 16, BF16, `checkpoint_depth = 2`. Auf der R9700 (32 GB VRAM / 48 GB RAM) laufen SDXL (~7,9 GiB), FLUX.2 Klein 4B (~15,5 GiB) und Z-Image Base (~16,1 GiB); FLUX.1 dev FP8 und Boogu Base sprengen 48 GB Host-RAM, enden aber dank VRAM-Guard mit lesbarem OOM statt Systemfreeze.
- **Audio-/Voice-LoRAs:** ACE-Step 1.5 XL Voice-LoRA, Qwen3-TTS 0.6B/1.7B PEFT-LoRA (`ComfyUI-DaWasteh-Qwen3TTS-LoRA`) und YuE2 3B Stil-LoRA (privat/nichtkommerziell).

## Dokumentation

Alle ausführlichen Anleitungen, Messwerte und Grenzen liegen im Index [`docs/README.md`](docs/README.md):

- **System, Skripte & Kompatibilität:** [`docs/COMPATIBILITY_AUDIT_V133.md`](docs/COMPATIBILITY_AUDIT_V133.md) · [`docs/DUAL_GPU_WORKFLOWS.md`](docs/DUAL_GPU_WORKFLOWS.md) · [`docs/START_UPDATE_AUDIT_V117.md`](docs/START_UPDATE_AUDIT_V117.md) · [`docs/EXAMPLES_GALLERY_V131.md`](docs/EXAMPLES_GALLERY_V131.md) · [`performance/rdna4/REPORT.md`](performance/rdna4/REPORT.md)
- **Bild & Editing:** [`docs/ANYANGLE_LANPAINT_V132.md`](docs/ANYANGLE_LANPAINT_V132.md) · [`docs/PROMPT_ENHANCER_V130.md`](docs/PROMPT_ENHANCER_V130.md) · [`docs/MING_IMAGE_V129.md`](docs/MING_IMAGE_V129.md) · [`docs/QWEN_IMAGE21_V121.md`](docs/QWEN_IMAGE21_V121.md) · [`docs/QWEN_IMAGE21_INPAINT_V128.md`](docs/QWEN_IMAGE21_INPAINT_V128.md) · [`docs/POSE_DEPTH_V128.md`](docs/POSE_DEPTH_V128.md)
- **Video, Musikvideo & Upscaling:** [`docs/H3_MUSIC_VIDEO_V122.md`](docs/H3_MUSIC_VIDEO_V122.md) (und V124/V125/V127) · [`docs/VIDEO_UPSCALE_V123.md`](docs/VIDEO_UPSCALE_V123.md) · [`docs/VIDEO_UPSCALE_WAN_V126.md`](docs/VIDEO_UPSCALE_WAN_V126.md) · [`docs/MINIMAX_H3_AUDIO_V113.md`](docs/MINIMAX_H3_AUDIO_V113.md)
- **3D & Game Assets:** [`docs/MIRA_SCENE_V129.md`](docs/MIRA_SCENE_V129.md) · [`docs/PIXAL3D_GAME_ASSETS_V097.md`](docs/PIXAL3D_GAME_ASSETS_V097.md) · [`docs/GODOT_GAME_ASSET_START.md`](docs/GODOT_GAME_ASSET_START.md) · [`docs/MODEL_WORKFLOWS_V118.md`](docs/MODEL_WORKFLOWS_V118.md)
- **Musik & Stimme:** [`docs/MINIMAX_MUSIC3.md`](docs/MINIMAX_MUSIC3.md) · [`docs/YUE2_LORA_V119.md`](docs/YUE2_LORA_V119.md) · [`docs/YUE2_RELIABILITY_V120.md`](docs/YUE2_RELIABILITY_V120.md) · [`docs/LIVE_VOICE_SWAP_V095.md`](docs/LIVE_VOICE_SWAP_V095.md)
- **Live Avatar:** [`LIVE_AVATAR_ANLEITUNG.md`](LIVE_AVATAR_ANLEITUNG.md) · [`docs/LIVE_PERSON_SWAP_V100.md`](docs/LIVE_PERSON_SWAP_V100.md) · [`docs/LIVE_FACE_SWAP_V099.md`](docs/LIVE_FACE_SWAP_V099.md)

## Prüfung & Tests

```powershell
L:\ComfyUI\.venv\Scripts\python.exe -B tools/validate_workflows.py --against-head
L:\ComfyUI\.venv\Scripts\python.exe -B -m pytest -q
L:\ComfyUI\start-MultiGPU.ps1 -CheckOnly
```
