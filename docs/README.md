# Dokumentation · Übersicht

Alle thematischen Guides, Kompatibilitätsprüfungen und technischen Referenzen des Bundles.

## System, Skripte & Galerie

| Dokument | Inhalt |
|---|---|
| [`COMPATIBILITY_AUDIT_V133.md`](COMPATIBILITY_AUDIT_V133.md) | ComfyUI-0.46.0-Kompatibilitätsprüfung aller 11 Custom-Node-Packs, 269 Workflows und Start-/Update-Skripte (`v1.3.3`) |
| [`DUAL_GPU_WORKFLOWS.md`](DUAL_GPU_WORKFLOWS.md) | Optionale Dual-GPU-Platzierung (`DaWMultiGPUDeviceControl`), RDNA4-Startprofil und Laufzeit-Patches |
| [`START_UPDATE_AUDIT_V117.md`](START_UPDATE_AUDIT_V117.md) | Historisches Skript-Audit (`v1.1.7`, ComfyUI 0.35.0) – Sicherheits-/Sync-Architektur des Updaters |
| [`EXAMPLES_GALLERY_V131.md`](EXAMPLES_GALLERY_V131.md) | Beispielgalerie, Namensschema (`v1.3.1`), behobene Workflow-Fehler und Umgebungshinweise |
| [`DAUER_UND_OPTIONALE_ZWEIGE_V115.md`](DAUER_UND_OPTIONALE_ZWEIGE_V115.md) | Sekundensteuerung nach Modell-Raster und stummgeschaltete optionale Eingabezweige |
| [`WAN_ANIMATE2_ADAPTIVE_MEDIA.md`](WAN_ANIMATE2_ADAPTIVE_MEDIA.md) | Adaptive Load Image/Video und Wan-Animate-2-Sekundensteuerung |

## Bild, Prompting & Vision

| Dokument | Inhalt |
|---|---|
| [`ANYANGLE_LANPAINT_V132.md`](ANYANGLE_LANPAINT_V132.md) | Qwen Image 2.1 AnyAngle (Kamerawinkel mit TripoSplat / eigenem Render / Studio) und LanPaint 2.2 Inpainting |
| [`PROMPT_ENHANCER_V130.md`](PROMPT_ENHANCER_V130.md) | Bild-Prompt-Enhancer mit lokalem Qwen3.8 27B GGUF über `llama-server` |
| [`MING_IMAGE_V129.md`](MING_IMAGE_V129.md) | Ming Image 0.1 Design: Text-to-Image, RGBA-Freisteller, Edit und Design-Layer-Zerlegung |
| [`QWEN_IMAGE21_V121.md`](QWEN_IMAGE21_V121.md) | Qwen Image 2.1 Text-to-Image und Multi-Image Edit |
| [`QWEN_IMAGE21_BACKGROUND_REMOVER_V124.md`](QWEN_IMAGE21_BACKGROUND_REMOVER_V124.md) | Qwen Image 2.1 Background Remover |
| [`QWEN_IMAGE21_INPAINT_V128.md`](QWEN_IMAGE21_INPAINT_V128.md) | Qwen Image 2.1 Masken-Inpainting |
| [`QWEN_IMAGE21_CAMERA_PHOTO_V1210.md`](QWEN_IMAGE21_CAMERA_PHOTO_V1210.md) | 4-MP-Kappung gegen `hipErrorLaunchFailure` bei hochauflösenden Kamerafotos |
| [`POSE_DEPTH_V128.md`](POSE_DEPTH_V128.md) | SDPose WholeBody und Depth Anything 3 Large für Bilder und Videos |

## Video, Musikvideo & Upscaling

| Dokument | Inhalt |
|---|---|
| [`H3_MUSIC_VIDEO_V122.md`](H3_MUSIC_VIDEO_V122.md) | FastH3 Song → Musikvideo (Grundarchitektur: Planer, Whisper-Timing, Extend, Lippensync) |
| [`H3_MUSIC_VIDEO_V124.md`](H3_MUSIC_VIDEO_V124.md) | Musikvideo: Realismus-LoRA und 1920×1088 ohne OOM (`h3_highres.py`) |
| [`H3_MUSIC_VIDEO_V125.md`](H3_MUSIC_VIDEO_V125.md) | Musikvideo: Szenen-Prüfung (`MV 5b`), Qwen3.8-27B-Prompt-Writer, 1664×928 |
| [`H3_MUSIC_VIDEO_V127.md`](H3_MUSIC_VIDEO_V127.md) | Musikvideo: Optionaler Upscale nach jeder Freigabe (`MV 5c`), Favoriten 960×544 / 1280×704 |
| [`VIDEO_UPSCALE_V123.md`](VIDEO_UPSCALE_V123.md) | Video-Upscaling: MiniMax FastH3 Split/Ultimate (`MMH3SplitUpscale` seit v1.3.3), Latent 3D und SeedVR2 3B |
| [`VIDEO_UPSCALE_WAN_V126.md`](VIDEO_UPSCALE_WAN_V126.md) | Video-Upscaling mit WAN 2.2 Low-Noise (MultiDiffusion-Kacheln, Vorlauf, WAN-2.1-kompatibel) |
| [`MINIMAX_H3_AUDIO_V113.md`](MINIMAX_H3_AUDIO_V113.md) | MiniMax-H3-Audiountersuchung (`shift_audio`, Sampler, Spectrum) |
| [`MINIMAX_H3_TURBO_AND_PROMPTS.md`](MINIMAX_H3_TURBO_AND_PROMPTS.md) | MiniMax H3 Turbo-LoRA und offizielle Prompt-Guides |

## 3D & Game Development

| Dokument | Inhalt |
|---|---|
| [`MIRA_SCENE_V129.md`](MIRA_SCENE_V129.md) | Mira-Scene: Einzelbild → bearbeitbare 3D-Szene mit TRELLIS.2 und Boden-/Auflage-Platzierung |
| [`PIXAL3D_GAME_ASSETS_V097.md`](PIXAL3D_GAME_ASSETS_V097.md) | Pixal3D PBR-Game-Assets für Godot |
| [`GODOT_GAME_ASSET_START.md`](GODOT_GAME_ASSET_START.md) | Godot-Startworkflows (PS1-Texturen, Hunyuan3D Low-Poly LOD0–3, Collision) |
| [`MODEL_WORKFLOWS_V118.md`](MODEL_WORKFLOWS_V118.md) | YuE2, Cosmos Predict2, TRELLIS.2 und Pixal3D mit Collision-Proxy |

## Musik & Stimme

| Dokument | Inhalt |
|---|---|
| [`MINIMAX_MUSIC3.md`](MINIMAX_MUSIC3.md) | MiniMax Music 3 Workflows und Official-Skill-Caption-Enhancer |
| [`YUE2_LORA_V119.md`](YUE2_LORA_V119.md) | YuE2 privates Stil-LoRA-Training und Anwendung |
| [`YUE2_RELIABILITY_V120.md`](YUE2_RELIABILITY_V120.md) | YuE2 Latent-Cache, FFmpeg-Fallback und isolierte Temp-Ordner |
| [`LIVE_VOICE_SWAP_V095.md`](LIVE_VOICE_SWAP_V095.md) | DirectML-RVC Live-Mikrofon-Voice-Swap |
| [`OMNIVOICE_LIVE_SWAP_EVALUATION.md`](OMNIVOICE_LIVE_SWAP_EVALUATION.md) | Bewertung von OmniVoice (verworfen für Live-S2S) |

## Live Avatar

- Hauptanleitung: [`../LIVE_AVATAR_ANLEITUNG.md`](../LIVE_AVATAR_ANLEITUNG.md)
- [`LIVE_PERSON_SWAP_V100.md`](LIVE_PERSON_SWAP_V100.md) · [`LIVE_FACE_SWAP_V099.md`](LIVE_FACE_SWAP_V099.md) · [`LIVE_AVATAR_WORKFLOW_12_13.md`](LIVE_AVATAR_WORKFLOW_12_13.md)
- [`live-avatar-local-blender-vrm.md`](live-avatar-local-blender-vrm.md) · [`live-avatar-v072-voice-backend-evaluation.md`](live-avatar-v072-voice-backend-evaluation.md) · [`live-avatar-vrm-model-licenses.md`](live-avatar-vrm-model-licenses.md)
