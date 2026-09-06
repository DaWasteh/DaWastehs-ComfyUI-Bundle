# WORKFLOWS · Inventar, Testfälle, Blocker (Stand 2026-09-05)

## Inventar

234 Workflow-JSONs im Repo (`workflows/`), identisch nach `L:\ComfyUI\ComfyUI\user\default\workflows\DaWasteh\` synchronisiert. Alle 234 enthalten den zentralen `DaWMultiGPUDeviceControl`-Node; 93 enthalten KJNodes-`VRAM_Debug`-Aufräumbarrieren (eingefügt von `tools/add_memory_cleanup_nodes.py`, Einstellung `empty_cache + gc_collect + unload_all_models`).

| Kategorie | Anzahl | Kategorie | Anzahl |
|---|---|---|---|
| Text to Image | 42 | Image Editing | 21 |
| Live Avatar | 19 | Music Generation | 19 |
| Prompt Tools | 15 | Prompt Enhancer | 14 |
| Image Utilities | 12 | Pixaroma Node Demos | 12 |
| Text+Image to Video | 12 | Voice Design | 12 |
| Reference to Video (MiniMax H3) | 7 | LoRA Generation | 7 |
| Text to Video | 6 | Character Animation / Game Development / NSFW | 4 / 4 / 4 |
| Audio to Video / Character & Consistency / Image Inpainting / Image Upscaling | je 3 | Batch Processing | 2 |
| Audio to Image, Controlled Video, Image Fusion, Image Outpainting, Image to 3D-Mesh, Talking Video, Templates & Tests, Video Editing, Video to Audio, Vocal Separation | je 1 | | |

Remote-/API-Anteile: nur `LiveAvatar-09 … Meshy` (Meshy-Cloud-Nodes, optional) sowie die beiden Ideogram-4-Workflows (lokales Ideogram-4-Modell, der `Ideogram4PromptBuilderKJ`-Node ist ein lokaler Prompt-Builder). Alle Benchmark-Workflows rechnen vollständig lokal; es wurden keine API-Nodes ausgeführt.

## Gewählte Ausgangssuite (ein repräsentativer Workflow pro Pflichtbereich)

| Bereich | Quelle | Testkopie (API-Prompt) | Kurzform für die Messung | Status |
|---|---|---|---|---|
| Bild | `Text to Image/ZImage_turbo-Text-to-Image.json` (Z-Image Turbo bf16 + Qwen3-4B + FLUX-ae; CLIP/VAE auf gpu:1) und `SDXL_RealVisXL_V4-Text-to-Image.json` | `api/IMG_ZTurbo.json`, `api/IMG_SDXL.json` | unverändert: 1024², 8 Schritte res_multistep bzw. 32 Schritte dpmpp_2m_sde_gpu | Baseline gemessen |
| WAN 2.2 | `Text+Image to Video/WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json` | `api/WAN22_I2V_14B_fixed.json` (siehe Blocker B1) | 832×480, 49 Frames (3 s @ 16 fps), 4 Schritte (2 High + 2 Low), lightx2v-LoRAs, Bild `13_profile_left_00001_.png` | Baseline gemessen |
| LTX 2.5 | `Text to Video/LTX25_INT8_ConvRot-Text-to-Video.json` (INT8-ConvRot-DiT 22B + Gemma-4-12B-INT8-Textencoder + Gemma-4-e2b-Prompt-Enhancer, zweistufig mit Latent-Upsampler) | `api/LTX25_T2V_short.json` | 3 s statt 5 s (73 Frames @ 24 fps), 0,9 MP 16:9 unverändert, beide Sampler-Stufen und Enhancer unverändert | Baseline gemessen, E2b angenommen |
| MiniMax H3 | echter Nutzerlauf vom 2026-09-05 (Core-Nodes `MiniMaxH3ImageToVideo`, FL2VA INT8-ConvRot 21 GB + Qwen3-VL-32B INT8 27 GB, 0,4 MP 1:1, 20 Schritte res_multistep, Turbo-LoRA aus) aus `/history` der 8188-Instanz | `api/H3_I2V_user.json`, Kurzform `api/H3_I2V_user_short.json` | 3 s statt 13 s (73 statt 312 Frames), sonst identisch | Baseline gemessen (sampling-gebunden) |
| Musik | `Music Generation/ACE-Step1_5_XL_SFT-Music-Generation.json` (ACE-Step 1.5 XL SFT bf16, Qwen 0.6B + 4B, LM-Audio-Codes an) | `api/ACE_XL_SFT_short.json` | 60 s statt 210 s, 75 Schritte euler cfg 4 unverändert | Baseline gemessen, E1 angenommen (41,6 → 30,4 s) |
| LoRA-Training | `LoRA Generation/ZImage_Base-LoRA-Training.json` (Core-Nodes `TrainLoraNode`/`SaveLoRA`, Z-Image Base bf16) | `api/TRAIN_ZImage_bench.json` | 8 Optimizer-Updates × 4 Accumulation, Rank 16, bf16, Gradient Checkpointing, eigener 3-Bild-Testdatensatz | **Blocker B4**: zwei reproduzierte Systemabstürze beim ersten Trainingsschritt (22:31 und 23:10) |

Weitere konvertierte Prompts für Regression: `api/H3_FL2VA_Spectrum.json` (Spectrum-Sampler-Variante), `api/ACE_INT8.json`.

Alle API-Prompts wurden mit `bench/ui_to_api.py` über die echte Frontend-Funktion `app.graphToPrompt()` (Selenium, Edge headless, Frontend 1.51.9 des Testservers) erzeugt; keine handgeschriebene Nachbildung.

## Reproduzierbare Blocker und Befunde am Inventar

- **B1 · WAN 2.2 I2V-14B-Workflows sind kaputt.** `WAN22_i2v_14B_fp8_lightx2v`, `WAN22_i2v_14B_Q8_GGUF_lightx2v` und `WAN22_bernini_i2v` kombinieren die 14B-Modelle (16-Kanal-Latents, Wan-2.1-VAE) mit `Wan22ImageToVideoLatent` (48-Kanal-Latent des 5B-TI2V-Modells) und `wan2.2_vae.safetensors`. Fehler bei jeder Auflösung: `The size of tensor a (48) must match the size of tensor b (16)` in `latent_formats.py:770` (`raw/VID-WAN22/VID-WAN22_v098_baseline_cold_20260905-220402.json`). Die Testkopie ersetzt den Node durch `WanImageToVideo` (positive/negative/latent) und die VAE durch `wan_2.1_vae.safetensors`; die korrigierten UI-Workflows liegen unter `workflows/` dieses Ordners und sind in v1.1.1 ins Repo übernommen.
- **B2 · Bild-LoRA-Trainer: Widget-Verschiebung.** Die fünf `TrainLoraNode`-Workflows speichern 18 `widgets_values` ohne den `control_after_generate`-Eintrag hinter `seed`. Frontend 1.51.9 fügt diesen Widget hinzu und verschiebt alle folgenden Werte um eins: das echte Frontend serialisiert `lora_dtype=false`, `quantized_backward="LoRA"`, `algorithm=true`, `offloading="[None]"` (siehe `api/TRAIN_ZImage.json`). Die Testkopie setzt die beabsichtigten Werte explizit; die fünf Workflows sind in v1.1.1 korrigiert (`tools/upgrade_v111.py`).
- **B5 · PEFT-Trainer (ACE-Step-Voice-LoRA, Qwen3-TTS) scheitern an torchao 0.9.0 (Durchlauf 2):** peft 0.19.1 verlangt torchao ≥ 0.16 und wirft im LoRA-Dispatcher einen `ImportError`; `fl-acestep-training` schluckt ihn als „Error: PEFT not installed“ und beendet den Node nach 12 s ohne Adapter (`raw/server_v098_vramguard_113009/server.log`). torchao 0.9.0 wird von ComfyUI-HeartMuLa verlangt. v1.1.2 wendet die bereits im Qwen3-TTS-Node vorhandene Umgehung (`peft_compat.py`) prozessweit beim Laden des Node-Packs an.
- **B3 · Trainingsdaten fehlen.** Alle konfigurierten Ordner `input/lora_training/{boogu-image-base,flux1-dev,flux2-klein-4b-base,sdxl,zimage-base}` sind leer. Für den Smoke-Test wurde `input/lora_training/_rdna4_bench/` mit drei im Benchmark erzeugten Z-Image-Turbo-Bildern und identischen Captions angelegt (kein Qualitätsnachweis, nur Funktions- und Geschwindigkeitsprüfung).
- **B4 · LoRA-Training stürzt das System ab — in Durchlauf 2 (2026-09-06) aufgeklärt und behoben, siehe `REPORT.md` §9:** Ursache ist die Kombination aus `checkpoint_depth=1` (ein Checkpoint über das ganze Modell, kein Speichergewinn) und dem Windows/ROCm-Verhalten, VRAM-Überläufe ohne OOM in den Host-RAM auszulagern. v1.1.2 setzt `checkpoint_depth=2` in allen fünf Core-Trainern und begrenzt den HIP-Allokator (VRAM-Guard). Z-Image Base, SDXL und FLUX.2 Klein 4B trainieren damit (16,1 / 7,9 / 15,5 GiB Spitze); FLUX.1-dev fp8 und Boogu bleiben auf diesem Rechner unlauffähig (VRAM- bzw. Host-Commit-Limit), enden aber mit einem lesbaren Fehler. Ursprünglicher Befund: Zweimal (22:31 nach langer Kette mit 16,8 GB Swap; 23:10 auf frischem Server mit 33 GB freiem RAM) blieb der Rechner beim ersten Schritt von `TrainLoraNode` (Z-Image Base bf16, Gradient Checkpointing, AdamW, bf16-LoRA) komplett stehen (Kernel-Power 41, keine Fehlermeldung im Log außer `WinError 10055` beim ersten Mal). Stack: torch 2.13.0+rocm10.1.0a20260822, HIP 7.16.26332; der im README dokumentierte 1-Schritt-Smoke-Test lief unter ROCm 7.15. Nicht weiter reproduziert, um den Rechner nicht erneut zu verlieren. Nächster Schritt nur nach Freigabe: isolierter Mikro-Backward-Test (kleines Modul, SDPA-Backward, Checkpointing) in einem Subprozess auf der RX 9070 XT, danach TrainLora mit `gradient_checkpointing=false` bzw. auf SDXL als Gegenprobe.
- Ohne Kürzung nicht messbar im Budget: MiniMax H3 13 s (Nutzerlauf 26,7 min bei 20 Schritten), ACE-Step 210 s, LTX 5 s – deshalb Kurzformen; keine Extrapolation ohne Kennzeichnung.
