# REPORT · ComfyUI auf RDNA4 (R9700 32 GB + RX 9070 XT 16 GB) · Durchlauf 1 · 2026-09-05/06

Teilbericht (Durchlauf 1 abgeschlossen: 15 Experimente, 116 Benchmark-Läufe, alle sechs Bereiche gemessen oder mit konkretem Blocker belegt). Fünf von sechs Pflichtbereichen wurden real gemessen; LoRA-Training ist mit einem reproduzierten Systemabsturz als Blocker dokumentiert. Alle Zahlen stammen aus `benchmark_results.csv` (eine Zeile je Lauf) und den Rohaufzeichnungen unter `raw/<TEST>/<run_id>.json` (Node-Zeiten, Sampler-Schritte, VRAM-Peaks, Host-RAM, Ausgabedateien mit SHA-256). Alle Vergleiche sind A/B bei identischer Arbeit (gleiche Modelle, Prompts, Seeds, Schritte, Auflösung, Frames); Ausgaben wurden mit `bench/check_media.py` gegen die Baseline desselben Seeds verglichen.

## 1. Messaufbau

- Testinstanz: ComfyUI 0.34.0 (`250b2e95`), venv-Python 3.13.13, torch 2.13.0+rocm10.1 (HIP 7.16), Port 8190, exakt die Produktions-Argumente des Profils v0.9.8 plus eigene Output-/Temp-/DB-Pfade (`bench/comfy_server.py`, `profiles/v098_baseline.json`). Produktionsinstanz und -dateien unangetastet (siehe `ROLLBACK.md`).
- Messung: `bench/run_bench.py` → Wandzeit vom `POST /prompt` bis fertiger Datei, Server-Ausführungszeit, Node-Dauern und Sampler-Schrittzeiten aus dem Probe-Trace (`bench/custom_nodes/rdna4_bench_probe`, nur in der Testinstanz geladen), `torch.cuda.max_memory_allocated/reserved` je GPU (vor jedem Lauf zurückgesetzt), PDH-GPU-Speicher des Serverprozesses, Host-RAM/Swap.
- Cold = frischer Serverprozess oder Modell noch nicht geladen; warm = Modelle geladen, nur Seed geändert. Läufe mit unverändertem Seed wurden als vollständig gecacht erkannt (0,3 s) und nicht als warm gewertet (`cached_nodes_n`).
- Kurzformen (Frames/Dauer) sind in `WORKFLOWS.md` dokumentiert; sie werden nicht auf lange Videos extrapoliert.

## 2. Baselines (Profil v0.9.8, unveränderte Repo-Workflows)

| Bereich | Workload (Kurzform) | kalt | warm (Median, n) | Sampling-Anteil | s/Schritt | Peak VRAM gpu:0 alloc/reserved |
|---|---|---|---|---|---|---|
| Bild Z-Image Turbo | 1024², 8 Schritte | 54,6 s | 15,6 s (n=3) | 4,2 s | 0,60 | 12,1 / 12,6 GiB |
| Bild SDXL RealVisXL | 1024², 32 Schritte | 27,8 s | 10,5 s (n=3) | 7,5 s | 0,24 | 5,4 / 6,1 GiB |
| Bild FLUX.1-dev fp8 (E12-Prompt) | 1024², 25 Schritte | 44,4 s | 19,3 s (n=3) | 17,8 s | 0,74 | 21,6 / 24,9 GiB |
| WAN 2.2 I2V 14B fp8 (korrigierter Graph) | 832×480, 49 Frames, 2+2 Schritte | 115,2 s | 77,4 s (n=3) | 17,0 s | 8,5 | 25,6 / 30,9 GiB |
| LTX 2.5 T2V INT8 | 0,9 MP, 73 Frames, 9+4 Schritte, Enhancer an | 548,3 s | 37,7 s (n=2, Text gecacht) | 13,5 s | 0,87 / 3,7 | 21,9 / 22,4 GiB |
| MiniMax H3 I2V (Nutzergraph) | 640², 73 Frames, 20 Schritte | 233,4 s | 129,7 s (n=2) | 114,6 s | 6,0 | 26,5 / 27,5 GiB |
| ACE-Step 1.5 XL SFT | 60 s Audio, 75 Schritte | 56,3 s | 41,6 s (n=2) | 18,0 s | 0,24 | 21,0 / 22,4 GiB |
| LoRA-Training Z-Image Base | 8 Updates × 4 Acc. | – | – | – | – | Blocker B4 |

Wo die Zeit hingeht (warm, Median der Node-Dauern):

- **Z-Image Turbo 15,6 s**: KSampler 8,6 s (davon 4,2 s Sampling, Rest Modell zurück auf die GPU), `VRAM_Debug` 4,5 s + 0,9 s, VAEDecode 1,5 s. Die Aufräumnodes entladen nach jedem Lauf alle Modelle.
- **WAN 2.2 77,4 s**: KSamplerAdvanced High 28,6 s + Low 32,4 s (je 8,5 s Sampling, Rest Laden/Patchen der jeweils anderen 13,6-GB-fp8-Hälfte, die beiden passen nicht gleichzeitig in 28 GB nutzbaren VRAM), VAEDecode 6,7 s, CLIPLoader 9,2 s in einem von drei Läufen (RAM-Druck-Cache hat die Loader-Ausgabe verworfen).
- **LTX 2.5 kalt 548 s**: Prompt-Enhancer (Gemma 4 e2b, 600 Token) 189,7 s, Negativ-Encode 96,1 s, Positiv-Encode 84,6 s, zwei `SelectCLIPDevice`-Deep-Clones 31,2 s + 20,0 s, Video-Sampling nur 13,5 s, Tiled-VAE 17,5 s. Ursache: Textencoder 14,6 GB und Enhancer 10 GB werden auf die 16-GB-RX-9070-XT gezwungen (0 GB frei, 0,9 s/Token).
- **MiniMax H3 warm 129,7 s**: 114,6 s Sampling (6,0 s/Schritt) + VAE 5,1 s + Audio-VAE 1,5 s → sampling-gebunden. Kalt zusätzlich TE-Laden+Encode 49,7 s (27 GB INT8-Qwen3-VL) und DiT-Laden ~50 s; beide passen nicht gemeinsam in den VRAM, der Wechsel fällt nur bei Prompt-/Bildwechsel an.
- **ACE-Step warm 41,6 s**: KSampler 21,6 s (18,0 s Sampling), LM-Audio-Codes 11,2 s (300 Token), `VRAM_Debug` 5,8 s.

Qualität der Baseline-Ausgaben (automatisch): alle PNG/MP4/MP3 dekodierbar, korrekte Maße/Frames/Samplerate (WAN 832×480×49 @16 fps; LTX 1280×704×73 @24 fps + 48 kHz Stereo; H3 640²×73 @24 fps + 32 kHz Stereo; ACE 60,0 s 48 kHz Stereo), keine schwarzen/eingefrorenen Frames, keine NaN, keine Stille. Eine visuelle/auditive Beurteilung erfolgte nicht.

## 3. Befunde am Inventar (Fehler, nicht Performance)

- **B1 · WAN-2.2-I2V-14B-Workflows nicht lauffähig** (3 Dateien: fp8, Q8-GGUF, Bernini): `Wan22ImageToVideoLatent` (48-Kanal, 5B-VAE) mit 14B-Modellen → `size of tensor a (48) must match … (16)`. Korrektur: `WanImageToVideo` + `wan_2.1_vae.safetensors` (`bench/fix_workflows.py`), über das echte Frontend validiert und als Baseline gemessen.
- **B2 · TrainLora-Workflows (5 Dateien)**: fehlender `control_after_generate`-Wert hinter `seed` → Frontend 1.51.9 verschiebt alle folgenden Widgets (`algorithm=true`, `lora_dtype=false`, …). Korrektur: Wert `fixed` eingefügt; Frontend-Serialisierung danach korrekt (`api/fixed_check/`). Der Repo-Mapper `map_widget_values` akzeptiert beide Formen.
- **B3 · Trainingsdaten**: alle fünf konfigurierten Dataset-Ordner leer.
- **B4 · LoRA-Training (Core `TrainLoraNode`) friert den Rechner ein**: zweimal reproduziert (22:31 und 23:10), jeweils beim ersten Forward/Backward, einmal auf frischem Server mit 33 GB freiem RAM. Keine Logmeldung außer `WinError 10055` (kein Pufferspeicher) beim ersten Mal; Kernel-Power 41. Nicht weiter provoziert. Belege: `raw/crash_2026-09-05_2231_system_events.json`, `raw/crash2_2026-09-05_system_events.json`, `raw/server_v098_baseline_230942/server.log`.
- **Speicherleck durch Geräte-Split**: `SelectCLIPDevice`/`SelectVAEDevice` auf ein anderes Gerät als der Loader erzeugt einen `deepclone_multigpu` (vollständige Zweitkopie im Host-RAM, 8–31 s) und hinterlässt ein „totes" `LoadedModel`; ComfyUI führt daraufhin bei jedem Modellwechsel `gc.collect()` aus („Potential memory leak detected … WARNING, memory leak with model ZImageTEModel_/LTXAVTEModel_"). Über eine Sitzung wuchs der Swap so von 2 auf 17 GB.

## 4. Experimente (Hypothese → A/B → Ergebnis)

| Nr. | Hypothese | Workload | Baseline → Kandidat (warm, Median) | n | Qualität | Ergebnis |
|---|---|---|---|---|---|---|
| E1 | `VRAM_Debug.unload_all_models=False` (Aufräumnodes behalten gc/empty_cache) | Z-Image Turbo; Regression ACE-Step, FLUX.2 Klein 4B, WAN 2.2 | 15,6 → 8,2 s (−47 %, ×1,9); ACE 41,6 → 30,4 s (−27 %); FLUX.2 Klein 4B (mit E2) 9,6 → 3,0 s; **WAN 2.2: 77,4 → 84,3 s und Host-RAM 26 → 0,7 GB frei** | 3 / 2 / 3 / 2 | PNG/MP3 bitidentisch; FLUX.2 PSNR 45–47 dB | **angenommen für Bild-/Audio-Kategorien (67 Workflows)**; Video/3D/Live behalten die Barriere (dort gibt sie die CPU-Kopien der wechselnden 14B-Modelle frei) |
| E1b | Aufräumnodes komplett neutral (kein gc, kein empty_cache) | Z-Image Turbo | 15,6 → 7,5 s | 3 | bitidentisch | nur 0,7 s besser als E1; gc/empty_cache beibehalten (Stabilität) |
| E2 | CLIP/VAE auf gpu:0 statt gpu:1 (kein Deep-Clone, kein GC-Sturm) | Z-Image Turbo / SDXL / FLUX.2 Klein 4B | 15,6 → 13,3 s / 10,5 → 9,1 s (−13 %) / kalt 48,0 → 18,7 s; Host-RAM nach Lauf 3,6 → 15,5 GB bzw. 27 → 34 GB frei | 3 / 3 / 3 | bitidentisch (SDXL, Z-Image); FLUX.2 PSNR 45–47 dB (Textencoder auf anderem Gerät) | **angenommen** für 14 Bild-Workflows |
| E1+E2 | Kombination | Z-Image Turbo | 15,6 → 6,2 s (−60 %, ×2,5); kalt 54,6 → 9,1 s (Modelle aus Vorlauf im RAM) | 3 | bitidentisch | **angenommen** |
| E2-LTX a | alles gpu:0 | LTX 2.5 T2V | kalt 548 → 189 s (×2,9); warm 37,7 → 35,4 s | 1+2 | Frames bitidentisch, Audio-RMS 0,2464 vs 0,2466 (Audio-VAE-Gerät) | Tiled-VAE-Decode kalt 53 s statt 17 s → verworfen zugunsten E2b |
| E2-LTX b | CLIP gpu:0, VAE gpu:1 | LTX 2.5 T2V | kalt 548 → 152 s (−72 %, ×3,6); warm 35,4 s, ein Lauf 157,9 s (RAM-Cache-Eviction, Reloads) | 1+2 | Frames + Audio bitidentisch | **angenommen** für 3 LTX-2.5-Workflows; Host-RAM bleibt Engpass (Swap 17–22 GB, 49 GB Gewichte) |
| E13 | `torch.compile` | Mikro-Test | – | – | – | **nicht nutzbar**: `TritonMissing` / `No module named 'triton'` (Windows-ROCm, `raw/E13_torch_compile_check.txt`) |
| E16 | Kernel-Microbench (welcher Linear-/Attention-Pfad ist auf gfx1201 schnell?) | synthetisch, RX 9070 XT | bf16 GEMM 135–144 TFLOPS; comfy-kitchen INT8-WMMA 126–174; fp8 `_scaled_mm` 190–248 (relerr 3,7 %); SDPA flash/mem-eff ~73 TFLOPS (L=16k–32k); comfy-kitchen INT8-Attention 1,7× schneller (relerr 1,6 %) | 10 Iter. | – | fp8-Compute ist im Build bereits aktiv (`SUPPORT_FP8_OPS=True` für gfx1201); INT8-ConvRot spart vor allem Speicher; INT8-Attention nur als Opt-in (E8) |

Profil-Experimente (je Profil ein frischer Serverprozess, Speicherwächter zwischen den Läufen) stehen in Abschnitt 8.

## 5. Umgesetzte Änderungen (Kopien unter `performance/rdna4/workflows/`, gleicher relativer Pfad wie das Original)

| Änderung | Dateien | Nachweis |
|---|---|---|
| E1 `unload_all_models=False` in `VRAM_Debug`-Nodes der Bild-/Audio-Kategorien | 67 (davon 14 zusammen mit E2) | E1 (Z-Image), Regression ACE-Step (−27 %), FLUX.2 Klein 4B; WAN-Gegenprobe negativ → Video/3D/Live ausgenommen; die zwei integritätsgeschützten AutoSongwriter-Genre-Selector und die generatorverwalteten Prompt-Enhancer bleiben unverändert |
| E2 Geräte-Control auf gpu:0/gpu:0/gpu:0 | 14 Bild-Workflows | Z-Image Turbo, SDXL, FLUX.2 Klein 4B |
| E2b CLIP gpu:0, VAE gpu:1 | 3 LTX-2.5-Workflows | LTX T2V gemessen; I2V/FLF2V gleiche Graph-Familie (nicht einzeln gemessen) |
| B1 `WanImageToVideo` + Wan-2.1-VAE | 3 WAN-I2V-Workflows | Frontend-Konvertierung identisch mit getestetem Prompt; WAN-Baseline läuft damit |
| B2 `control_after_generate` eingefügt | 5 TrainLora-Workflows | Frontend-Serialisierung korrekt; Ausführung wegen B4 nicht möglich |

Alle 78 Änderungen sind in `workflows/` übernommen und als deterministische, idempotente Migration `tools/upgrade_v111.py` (Marker `extra.dawasteh_rdna4_v111`) in die Release-Prüfkette integriert: `tools/upgrade_v111.py --check` → 0 Abweichungen; `tools/validate_workflows.py` → `errors: 0` (Link-Summe 7211); `tools/validate_workflows.py --against-head` (Rekonstruktion aus v1.1.0) → `errors: 0`; `pytest tests` → 253 bestanden, 1 übersprungen (neu: `tests/test_upgrade_v111.py`). Die optimierten Kopien wurden über das echte Frontend erneut in API-Prompts konvertiert; Z-Image Turbo ergab exakt den gemessenen E1+E2-Prompt, die WAN-Kopie exakt den getesteten B1-Graphen.

## 8. Profil-Experimente und Regression (Ketten 4–6)

| Nr. | Profiländerung (`profiles/*.json`) | Workload | Baseline → Kandidat (warm, Median) | n | Ergebnis |
|---|---|---|---|---|---|
| E3 | `--reserve-vram 1` (beide Wan-Hälften sollen im VRAM bleiben) | WAN 2.2 | 77,4 → 206,1 s; Host-RAM 26 → 5 GB frei, RSS 32 GB, Wächter-Neustart | 3 | **verworfen** (Host-RAM-Erschöpfung) |
| E4 | `--fast fp8_matrix_mult` | FLUX.1-dev fp8 (Legacy-fp8 ohne Quant-Metadaten) | 19,3 → 20,1 s (+4 %), 0,740 → 0,767 s/Schritt | 3 | **verworfen**; fp8_scaled-Modelle (WAN, Krea 2, …) nutzen ohnehin native fp8-GEMMs (`SUPPORT_FP8_OPS=True`) |
| E9 | klassisches hipBLAS statt hipBLASLt | SDXL / Z-Image Turbo | 0,242 → 0,259 s/Schritt (+7 %) / 0,610 → 0,626 (+3 %) | 3 / 3 | **verworfen**, hipBLASLt bleibt |
| E14 | `--cache-classic` | WAN 2.2 | 77,4 → 110,5 s; Host-RAM 1–3 GB frei | 3 | **verworfen** |
| E15 | `PYTORCH_HIP_ALLOC_CONF=expandable_segments:True` | WAN 2.2 | 4 × Timeout nach 2400 s (Loader 380–400 s, 11,5 s/Schritt, RSS 36 GB, 0,3 GB frei) | 4 | **verworfen** (schädlich) |
| E8 | `--use-ck-attention` (comfy-kitchen INT8-QK-Attention; schließt `--use-pytorch-cross-attention` aus) | H3 / WAN 2.2 | H3 warm 129,7 → 112,8 s (−13 %, 6,03 → 5,19 s/Schritt); WAN 8,5 → 7,3 s/Schritt, gesamt aber 107,8 s (Host-RAM 1,6 GB frei, Neustarts) | 2 / 2 | **nur Opt-in**: PSNR zur Baseline 22–27 dB (Video) liegt im Bereich der ohnehin vorhandenen Lauf-zu-Lauf-Streuung fp8-quantisierter WAN-Ausgaben (kalt vs. warm 25–28 dB), Qualität damit nicht beurteilbar; INT8-Attention bleibt experimentell |
| E7 | `--enable-dynamic-vram` (comfy-aimdo 0.5.2) | Z-Image Turbo (E1+E2) / WAN 2.2 | 6,2 → 105,8 s / 77,4 → 311,2 s; Host-RAM 0,6–2,5 GB frei | 2 / 2 | **verworfen**; `--disable-dynamic-vram` bleibt zwingend, obwohl ComfyUI das Flag entfernen will |

Kein Startprofil-Kandidat schlägt v0.9.8; das Produktionsprofil bleibt unverändert. Einziger Profil-Befund: im Opt-in-Zweig `$UseComfyKitchenAttention` von `start-MultiGPU.ps1` wurde `--use-ck-attention` zusätzlich zu `--use-pytorch-cross-attention` gesetzt, was ComfyUI 0.34 mit `not allowed with argument` ablehnt; v1.1.1 lässt das Pytorch-Flag in diesem Zweig weg (nur das Repo-Skript `tools/start-MultiGPU.ps1`; die Produktionskopie wird erst durch den Updater ersetzt).

Regression der übernommenen Workflows (Baseline-Profil, optimierte Kopien über das echte Frontend konvertiert): ACE-Step 41,6 → 30,4 s (n=2, MP3 bitidentisch); FLUX.2 Klein 4B 9,6 → 3,0 s warm, 48,0 → 18,7 s kalt (n=3, PSNR 45–47 dB); WAN 2.2 mit B1-Korrektur läuft (114,6 s kalt, 84,3 s warm mit E1 → E1 dort zurückgenommen, Endfassung behält die Barriere). Reproduzierbarkeit: WAN-Ausgaben sind auf diesem Stack nur im gleichen Prozesszustand bitidentisch (E14/E3 warm vs. Baseline warm: 49/49 Frames identisch), kalt vs. warm unterscheiden sie sich mit 25–28 dB PSNR (fp8-Requantisierung beim LoRA-Patchen).

Gesamtzähler: 15 Experimente (E1, E1b, E2, E1+E2, E2-LTX a/b, E13, E16, E3, E4, E9, E14, E15, E8, E7), 116 Läufe (`benchmark_results.csv`), zwei Systemabstürze (beide B4), keine Produktionsdatei geändert.

## 6. Nicht umgesetzt / verworfen / offen

- `torch.compile`: kein Triton auf Windows-ROCm (E13).
- Pinned Memory (E5) und Async-Offload (E6): nicht getestet. Pinned würde bis zu 40 % des Host-RAM sperren, während LTX/H3 bereits 17–22 GB Swap erzeugen (Absturzrisiko); Async-Offload wirkt nur bei teilweise geladenen Modellen, alle gemessenen DiTs wurden „loaded completely".
- Geräte-Splits der übrigen Video-/Audio-Workflows (H3-Spectrum, WAN T2V, Kandinsky, SCAIL2, WanAnimate2, LTX 2.3, ACE Turbo, Stable Audio, MiniMax Music 3): gleicher Mechanismus wie E2, aber nicht einzeln gemessen → unverändert gelassen.
- Verbleibende Chancen (priorisiert): (1) H3/LTX sind sampling- bzw. RAM-gebunden: kleinere Textencoder-Varianten oder mehr Host-RAM wären die Hebel; (2) INT8-Attention (E8) als Opt-in mit echter Sichtprüfung; (3) die Deep-Clone-Semantik von `SelectCLIPDevice` upstream melden (Host-RAM-Verdopplung + GC-Sturm); (4) TrainLoraNode-Absturz auf ROCm 10.1 isolieren (Mikro-Backward-Test nur mit Nutzer am Rechner); (5) LoRA-Patching auf fp8-Gewichten bei jedem Modellwechsel (WAN: ~20 s je Hälfte) durch vorgemergte Gewichte vermeiden.
- Host-RAM ist der systemische Engpass für LTX 2.5 (49 GB Gewichte) und H3 (48 GB): Swap 17–22 GB in jedem Lauf. Das ist mit Startflags nicht lösbar; kleinere Textencoder-Varianten oder mehr RAM wären die Hebel.

## 7. Quellen

- Lokaler Code: `comfy/model_management.py` (`is_nvidia`, `supports_fp8_compute`, `cleanup_models_gc`), `comfy_extras/nodes_multigpu.py` (`_retarget_patcher` → `deepclone_multigpu`), `comfy/ops.py` (`pick_operations`), `comfy_kitchen/backends/hip/__init__.py` (WMMA-Kernel), `custom_nodes/comfyui-kjnodes/nodes/nodes.py` (`VRAM_Debug`).
- ComfyUI `comfy/cli_args.py` (lokal, Stand 0.34.0) für alle Flags; PyTorch HIP-Semantik (`torch.cuda` = HIP) bestätigt durch `torch.version.hip = 7.16.26332`, `torch.version.cuda = None`.
