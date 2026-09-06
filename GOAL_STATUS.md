# GOAL_STATUS · ComfyUI RDNA4 Optimierung

Auftrag: `COMFYUI_RDNA4_GOAL.md` (5. September 2026). Artefakte unter `performance/rdna4/`.

## Zähler

| Zähler | Stand |
|---|---|
| Goal-Runden (ausgewertet) | 1 Durchlauf, abgeschlossen (Teilbericht) |
| Optimierungsexperimente (Hypothese + A/B) | 15 / 16 abgeschlossen (E1, E1b, E2, E1+E2, E2-LTX a/b, E13, E16, E3, E4, E9, E14, E15, E8, E7) |
| Benchmark-Runs (Server-Jobs, selbst gestartet) | 116 (davon 4 Timeouts in E15, 4 Fehlläufe des kaputten WAN-Graphen); alle Testserver beendet |
| Testbereiche gemessen | 5 / 6 gemessen (Bild, WAN 2.2, LTX 2.5, Musik, MiniMax H3); Training = Blocker B4 (2× Systemabsturz) |

## Zuletzt bestätigter Zustand

- 2026-09-05 21:45: Produktionsinstanz auf 127.0.0.1:8188 (PID 29476, Profil v0.9.8) lief mit einem Nutzer-MiniMax-H3-Job; nicht angefasst. Nutzer beendet den Server nach dem Job selbst.
- Ausgangszustand gesichert unter `performance/rdna4/baseline_state/` (Repo-HEAD 1d8da1c, ComfyUI-HEAD 250b2e95 mit lokalem samplers.py-Patch, Startskripte, Launcher, pip-Freeze 352 Pakete, Custom-Node-Stände).
- Benchmark-Harness geschrieben (`performance/rdna4/bench/`): Testserver auf Port 8190 mit eigenem Output/Temp/DB, Probe-Custom-Node nur über `extra_model_paths_bench.yaml`, UI→API über die echte Frontend-Funktion (Selenium/Edge, Test-venv `L:\ComfyUI\tmp\minimax-test-venv`), Run-Recorder mit Trace/VRAM/RAM, Medienprüfung.

## Absturz 2026-09-05 22:31

Der Rechner blieb beim Start des LoRA-Trainings hängen (Serverlog: `WinError 10055 Pufferspeicher fehlt`, danach Dienst-Timeouts, Registry-Flush-Fehler 22:52, Kernel-Power 41 nach Neustart 23:06; Belege `performance/rdna4/raw/crash_2026-09-05_2231_system_events.json`). Vorher war der Swap über die Kette LTX→ACE auf 16,8 GB gewachsen (Deep-Clone-Leaks der gpu:1-Selector-Nodes + RAM-Cache). Gegenmaßnahmen: `bench/mem_guard.py` (Neustart des Testservers bei <14 GB frei oder >6 GB Swap), frischer Serverprozess vor jedem Testbereich, keine parallelen GPU-Jobs.

## Absturz 2 · 2026-09-05 23:10 (LoRA-Training, reproduziert)

Frischer Serverprozess (Start 23:09:42, 33 GB RAM frei, kein Swap), nur der Trainings-Prompt: Systemhänger exakt bei `Training LoRA: 0/32` (erster Forward/Backward des Core-`TrainLoraNode` mit Z-Image Base bf16, Gradient Checkpointing, AdamW), Kernel-Power 41 nach Neustart 23:16:55 (Belege `raw/crash2_2026-09-05_system_events.json`, `raw/server_v098_baseline_230942/server.log`). Beide Abstürze am selben Punkt → **Blocker B4: kein weiteres Training mehr in diesem Durchlauf.** Der Bereich LoRA-Training bleibt mit konkretem Blocker dokumentiert (torch 2.13.0+rocm10.1 / HIP 7.16; der README-Smoke-Test lief noch unter ROCm 7.15).

## Befunde bisher

- Bild Z-Image Turbo: warm 15,0 s, davon 4,2 s Sampling; VRAM_Debug(unload_all_models) kostet ~7,5 s je Lauf → E1 (nur unload aus): warm 7,5 s (n=3), Sampling identisch.
- WAN 2.2 I2V 14B fp8: Repo-Workflow kaputt (48- vs 16-Kanal-Latent, B1), Korrektur validiert; Kurzform warm 77 s, davon 17 s Sampling (8,5 s/Schritt), ~43 s Modellwechsel High/Low (passen nicht beide in 28 GB nutzbaren VRAM) → E3 geplant.
- SelectCLIPDevice/VAEDevice auf gpu:1 erzeugt Deep-Clone (8 s, doppelter RAM) und „memory leak"-GC-Stürme → E2 läuft.
- E13 torch.compile: nicht nutzbar (TritonMissing / No module named 'triton' auf Windows-ROCm), Nachweis `raw/E13_torch_compile_check.txt`.
- E1/E2 Bild (n=3 warm, Seeds 1002–1004, Ausgaben bitidentisch): Z-Image Turbo 15,6 s → 8,2 s (E1) → 6,2 s (E1+E2); SDXL 10,5 → 9,1 s (E2). Host-RAM nach Lauf 3,6 GB → 26,8 GB frei (E1+E2).
- LTX 2.5 Kurzform kalt 548 s, davon ~460 s Textseite auf der vollen RX 9070 XT (Enhancer 0,9 s/Token, Negativprompt 96 s), Video-Sampling 13 s; warm (Text gecacht) 37,7 s. → E2-LTX (CLIP auf gpu:0) läuft.
- ACE-Step XL SFT 60 s: kalt 56 s, warm 41,6 s (Sampling 18 s = 0,24 s/Schritt, LM-Codes 7,6 s, VRAM_Debug-Unload 5,8 s).
- H3 Kurzform (3 s, 20 Schritte): kalt 233 s, warm 129,7 s (n=2), davon 114 s Sampling (6,0 s/Schritt) → sampling-gebunden; TE-Load+Encode 50 s, DiT-Load ~50 s nur bei Prompt-/Modellwechsel.
- E2-LTX (n: 1 kalt + 2 warm je Variante, Frames bitidentisch zur Baseline): kalt 548 s → 189 s (alles gpu:0) bzw. 152 s (CLIP gpu:0, VAE gpu:1); warm 37,7 → 35,4 s; VAE auf gpu:0 macht den Tiled-Decode kalt 53 s statt 17 s → Empfehlung E2b. Host-Swap bleibt bei LTX 17–22 GB (49 GB Gewichte in 47 GB RAM); ein Warmlauf zeigte RAM-Cache-Eviction (+120 s Reloads).
- E16 Kernel-Microbench (RX 9070 XT, `raw/E16_kernel_microbench.json`): bf16 GEMM 135–144 TFLOPS, comfy-kitchen INT8-WMMA 126–174, fp8 `_scaled_mm` 190–248 (relerr 3,7 %); SDPA flash/mem-eff ~73 TFLOPS bei L=16k–32k, comfy-kitchen INT8-Attention 1,7× schneller (relerr 1,6 %). fp8-Compute ist im Build bereits aktiv (SUPPORT_FP8_OPS=True für gfx1201).
- Profil-Experimente (WAN-Kurzform warm, Baseline 77,4 s): E3 reserve-vram 1 → 206 s und Host-RAM 5 GB frei (verworfen); E14 cache-classic → 110 s, Host-RAM 1–3 GB frei (verworfen); E15 expandable_segments → 4 Timeouts à 2400 s, RSS 36 GB (verworfen); E4 fp8_matrix_mult auf FLUX.1-dev-fp8 → 19,3 → 20,1 s (+4 %, verworfen); E9 hipBLAS klassisch → SDXL 0,242 → 0,259 s/Schritt, Z-Image 0,610 → 0,626 (hipBLASLt bleibt). Kein Startprofil-Kandidat schlägt v0.9.8.
- E8 scheiterte zunächst am Flag-Konflikt (`--use-ck-attention` schließt `--use-pytorch-cross-attention` aus); Profil korrigiert, Kette 6 läuft nach der Regression.
- Rollback-Skript: Restore-/Skip-Logik an Kopien getestet (`raw/rollback_restore_test.txt`: unverändert → ok, installierte Version → wiederhergestellt, Nutzeränderung → SKIP).
- B2: fünf TrainLora-Workflows mit Widget-Verschiebung (Frontend 1.51.9); Korrektur validiert.

## Abschluss Durchlauf 1 (2026-09-06 03:45)

- Übernommen (Repo, v1.1.1): 78 Workflows (B1 3, B2 5, E1 67 davon 14 mit E2, E2b 3) als deterministische Migration `tools/upgrade_v111.py`; Validator plain/against-head 0 Fehler; pytest 253 bestanden. Startprofil produktiv unverändert (kein Kandidat besser); Opt-in-Flag-Konflikt in `tools/start-MultiGPU.ps1` behoben.
- Ergebnisse: Z-Image Turbo warm 15,6 → 6,2 s, SDXL 10,5 → 9,1 s, FLUX.2 Klein 4B 9,6 → 3,0 s, ACE-Step 41,6 → 30,4 s, LTX 2.5 kalt 548 → 152 s (Ausgaben bitidentisch bzw. ≥45 dB); WAN 2.2 und H3 ohne validierten Gewinn (H3 −13 % nur mit INT8-Attention als Opt-in ohne Qualitätsnachweis).
- Artefakte: `performance/rdna4/{ENVIRONMENT,WORKFLOWS,REPORT,ROLLBACK}.md`, `benchmark_results.csv`, `raw/`, `api/`, `profiles/`, `workflows/`, `bench/`.

## Offen / nächste Schritte

1. Nächster Durchlauf (nur mit Nutzer am Rechner): TrainLoraNode-Absturz isolieren (Mikro-Backward-Test, dann `gradient_checkpointing=false`, dann SDXL).
2. INT8-Attention (E8) mit Sichtprüfung bewerten; ggf. als dokumentiertes Opt-in-Profil.
3. Deep-Clone-Verhalten von `SelectCLIPDevice` upstream melden; Host-RAM (48 GB) bleibt der Engpass für LTX 2.5 und H3.
4. Nach dem Push: Updater ausführen, damit die 78 korrigierten/optimierten Workflows und das Startskript nach `L:\ComfyUI` synchronisiert werden.

## Blocker

- LoRA-Training: alle konfigurierten Dataset-Ordner `input/lora_training/*` sind leer (0 Bilder). Plan: eigener kleiner synthetischer Testdatensatz aus Benchmark-Bildern unter `input/lora_training/_rdna4_bench/` (nur für den Smoke-Test, kein Qualitätsnachweis).
