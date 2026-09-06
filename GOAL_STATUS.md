# GOAL_STATUS · ComfyUI RDNA4 Optimierung

Auftrag: `COMFYUI_RDNA4_GOAL.md` (5. September 2026). Artefakte unter `performance/rdna4/`.

## Zähler

| Zähler | Stand |
|---|---|
| Goal-Runden (ausgewertet) | 2 Durchläufe (1: 2026-09-05/06, 2: 2026-09-06) |
| Optimierungsexperimente (Hypothese + A/B) | 15 (Durchlauf 1) + 6 (Durchlauf 2: VRAM-Sonden, Checkpoint-Tiefe je Trainer, E2c ACE Turbo, E2c WAN T2V, PEFT-Umgehung) |
| Benchmark-Runs (Server-Jobs, selbst gestartet) | 116 + 24 (Durchlauf 2; davon 4 kontrollierte OOM-/Watchdog-Abbrüche); alle Testserver beendet |
| Testbereiche gemessen | **6 / 6** (Bild, WAN 2.2, LTX 2.5, Musik, MiniMax H3, LoRA-Training) |

## Durchlauf 2 (2026-09-06) — LoRA-Training entsperrt

- **Ursache der beiden Systemabstürze gemessen** (`bench/vram_probe.py`, `raw/vram_probe/`): Der HIP-Allokator löst unter Windows/ROCm keinen OOM aus; jenseits des VRAM lagert der WDDM-Treiber GPU-Allokationen still in den Host-RAM aus (18,4 GiB auf der 16-GiB-RX-9070-XT, 0,5 GiB Host je 512-MiB-Block), bis der Host voll ist. `checkpoint_depth=1` des Core-Trainers legt einen einzigen Checkpoint über das ganze Modell („patching 1 modules“) und spart nichts; bei 1024² überschreitet der Backward des 6B-Modells die 32 GB. SDPA-Backward-Kernel sind in Ordnung.
- **Schutz produktiv:** VRAM-Guard im MultiGPU-Node-Pack (`set_per_process_memory_fraction`, R9700 28,7 GiB / RX 9070 XT 12,8 GiB, `DAWASTEH_VRAM_GUARD`), Startskript v1.1.2. Zweiter Schutz nur im Bench: `bench/host_guard.py` (Commit-Headroom, Nonpaged Pool).
- **Trainer validiert (1024², Rank 16, 8 Forward/Backward):** SDXL depth 1 → 2: 22,9 → 7,9 GiB; Z-Image Base depth 2: 16,1 GiB, 7,1 s/Schritt, Adapter 867 Tensoren; FLUX.2 Klein 4B depth 1 = sauberer OOM (28,2 GiB), depth 2: 15,5 GiB; FLUX.1-dev fp8: OOM auch bei depth 2/3 und Offloading, zusätzlich Host-Commit-Limit; Boogu: Host-Commit-Limit beim Laden (102 GB). Kein Systemabsturz.
- **PEFT-Kollision (B5):** peft 0.19.1 × torchao 0.9.0 (HeartMuLa) lässt jeden PEFT-Trainer im Prozess scheitern; `peft_compat.py` (Qwen3-TTS-Pack) umgeht das prozessweit. ACE-Step-Voice-LoRA damit real trainiert (10 Epochen, Loss 1,19–1,27, Adapter 27,6 GiB Spitze).
- **Verbleibende Splits (E2c):** ACE-Step Turbo 4B warm 218,6 → 10,1 s (kalt 249,6 → 24,6 s); WAN 2.2 T2V warm 159,2 → 69,4 s (kalt 124,8 → 106,9 s). Beide übernommen; Ausgaben nicht bitidentisch (ACE SNR 18–23 dB durch Temperatur-Sampling des LM, WAN PSNR 18,0 dB), keine Sichtprüfung. Zwölf weitere Split-Workflows ungemessen und unverändert.
- **Übernommen (v1.1.2):** `tools/upgrade_v112.py` (5 Trainer `checkpoint_depth` 2, 2 Geräteplatzierungen), `vram_guard.py`, `peft_compat.py`, Startskript, Validator-v112-Schritt; `validate_workflows.py` plain und `--against-head` 0 Fehler; pytest gesamt bestanden.

## Abschluss Durchlauf 1 (2026-09-06 03:45)

- Übernommen (Repo, v1.1.1): 78 Workflows (B1 3, B2 5, E1 67 davon 14 mit E2, E2b 3) als deterministische Migration `tools/upgrade_v111.py`; Validator 0 Fehler; pytest 253 bestanden. Startprofil produktiv unverändert (kein Kandidat besser).
- Ergebnisse: Z-Image Turbo warm 15,6 → 6,2 s, SDXL 10,5 → 9,1 s, FLUX.2 Klein 4B 9,6 → 3,0 s, ACE-Step XL SFT 41,6 → 30,4 s, LTX 2.5 kalt 548 → 152 s; WAN 2.2 I2V und H3 ohne validierten Gewinn (H3 −13 % nur mit INT8-Attention als Opt-in).
- Artefakte: `performance/rdna4/{ENVIRONMENT,WORKFLOWS,REPORT,ROLLBACK}.md`, `benchmark_results.csv`, `raw/`, `api/`, `profiles/`, `workflows/`, `bench/`.

## Offen / nächste Schritte

1. FLUX.1-dev-fp8- und Boogu-Training brauchen mehr Host-Speicher (RAM oder feste Auslagerungsdatei ≥ 64 GB); nicht per Startflag lösbar.
2. Zwölf Split-Workflows (SCAIL2, WanAnimate2, StableAudio3, Kandinsky5, LTX 2.3, H3-Spectrum ×3, H3-Song-to-Video, MiniMax Music 3) einzeln messen, bevor sie umplatziert werden.
3. Sichtprüfung der WAN-T2V-Abweichung (18 dB) und der ACE-Turbo-Ausgaben; INT8-Attention (E8) bleibt Opt-in.
4. Upstream melden: `find_modules_at_depth(depth=1)` in ComfyUI `nodes_train.py`, peft-torchao-Versionsprüfung, Deep-Clone-Verhalten von `SelectCLIPDevice`.
5. Nach dem Push: Updater ausführen (synchronisiert Node-Packs mit VRAM-Guard/peft_compat, Startskript und die 7 geänderten Workflows nach `L:\ComfyUI`).

## Blocker

- Keine harten Blocker mehr. Host-RAM (48 GB) bleibt der systemische Engpass (Trainer-Zweitkopie, LTX 2.5, H3).
