# GOAL_STATUS · ComfyUI RDNA4 Optimierung

Auftrag: `COMFYUI_RDNA4_GOAL.md` (5. September 2026), zuletzt `COMFYUI_v1.1.3_Arbeitsauftrag.md`
(6. September 2026). Artefakte unter `performance/rdna4/`.

## Zähler

| Zähler | Stand |
|---|---|
| Goal-Runden (ausgewertet) | 2 Durchläufe (1: 2026-09-05/06, 2: 2026-09-06) |
| Optimierungsexperimente (Hypothese + A/B) | 15 (Durchlauf 1) + 6 (Durchlauf 2: VRAM-Sonden, Checkpoint-Tiefe je Trainer, E2c ACE Turbo, E2c WAN T2V, PEFT-Umgehung) |
| Benchmark-Runs (Server-Jobs, selbst gestartet) | 116 + 24 (Durchlauf 2; davon 4 kontrollierte OOM-/Watchdog-Abbrüche); alle Testserver beendet |
| Testbereiche gemessen | **6 / 6** (Bild, WAN 2.2, LTX 2.5, Musik, MiniMax H3, LoRA-Training) |

## Durchlauf 4 (2026-09-06) — Auftrag §5/§6 abgeschlossen (v1.1.5)

- **§6 optionale Zweige.** Gegen die Prompt-Validierung von ComfyUI 0.34.0 gemessen: ein
  verbundener Loader mit fehlender Datei blockiert (HTTP 400), ein stummgeschalteter nicht
  (HTTP 200), ein unverbundener ebenfalls nicht. Der MAXIMUM-Workflow lieferte 13 aktive
  Platzhalter-Loader aus und war damit **ausgeliefert nicht lauffähig**. Diese Zweige stehen jetzt
  auf Mute (nicht Bypass — ein Loader hat keinen Eingang zum Durchreichen), beschriftet mit
  `OPTIONAL · … · Strg+M schaltet ein`. Vor dem Stummschalten prüft die Migration, dass jede
  ausgehende Verbindung in einem optionalen Eingang endet; bei zwei Workflows speist das
  Referenzvideo Pflichteingänge (`length`, `duration`) — dort wird dokumentiert statt geändert.
  Verifiziert: der stummgeschaltete MAXIMUM-Graph besteht die Validierung (HTTP 200).
- **§5 Sekundensteuerung.** Rasterwerte gegen die Node-Schemata verifiziert (`EmptyLTXVLatentVideo`
  step 8, WAN/Kandinsky/SCAIL step 4, `MiniMaxH3ImageToVideo` step 17 = `align_frame_count`). Der
  Marker trägt jetzt `minimum_frames`, eine Rundungsregel und eine `preview`-Tabelle mit
  gewünschter Dauer, berechneten Frames und tatsächlicher Dauer an drei Stützstellen (Minimum,
  Standard, nicht ganzzahlig) — z. B. LTX 2.3: 4,0 s → 97 Frames → 3,84 s.
- **Prüfungen:** pytest 290 bestanden, Validator plain und `--against-head` je 0 Fehler,
  `upgrade_v115.py` idempotent, RODENT-Layout unverletzt.

### Damit ist der Auftrag `COMFYUI_v1.1.3_Arbeitsauftrag.md` vollständig abgearbeitet

§3 Audiofix (v1.1.3, Hörabnahme bestanden) · §4 Konsolidierung (v1.1.3) · §5 Sekundensteuerung
(v1.1.5) · §6 optionale Inputs (v1.1.5) · §7 GPU-Zuweisung (geprüft: bitidentisches No-op, v1.1.4)
· §8 Update-Skript (v1.1.3, zwei Korrekturen in v1.1.4) · §9 Release.

### Offen (ausserhalb des Auftrags)

- **w4a8-Quantisierung** (Textencoder 15,7 GB statt 27 GB, UNETs 12,5 GB statt 21 GB) — Community-
  Quantisierung, noch nicht bewertet. Die offizielle 4-Bit-Variante `nvfp4_awq` ist für gfx1201
  ungeeignet (keine HIP-Kernel, Projekt-Blacklist).
- 16 Workflows verweisen auf Nutzer-Medien, die es lokal nicht gibt (eigene Bilder, Tonspuren).
  Das ist beabsichtigt und wurde bewusst nicht angefasst — dort wählt der Nutzer seine Datei.

## Durchlauf 3 (2026-09-06) — MiniMax-H3-Audiofix, Konsolidierung, Update-Skript (v1.1.3)

**Auftrag:** `COMFYUI_v1.1.3_Arbeitsauftrag.md`. Details der Audiountersuchung:
[docs/MINIMAX_H3_AUDIO_V113.md](docs/MINIMAX_H3_AUDIO_V113.md).

- **Vergleichsbasis rekonstruiert, nicht geraten:** Die ausgeführten Graphen liegen als
  `prompt`-Metadatum in den MP4s. Damit waren alle vier Läufe exakt vergleichbar.
- **Turbo-LoRA und Schrittzahl als Ursache ausgeschlossen.** `MiniMax_H3_00002_`/`00003_` sind ein
  vom Nutzer selbst erzeugtes, vollständig kontrolliertes Paar (gleicher Seed, gleicher Prompt,
  einziger Unterschied ein `PrimitiveBoolean` für LoRA + 20↔8 Schritte). Gemessener HF-Abstand
  −28,5 dB gegenüber −29,1 dB: **0,6 dB**. Beide bleiben unverändert.
- **Drei belegte Abweichungen von der Hersteller-Referenz zurückgenommen** (`tools/upgrade_v113.py`,
  6 Workflows): `shift_audio` 4.0 → 3.0 (Default in Knoten, Modellkonfiguration und DiT),
  `euler`/`beta` → `res_multistep`/`simple` (offizielle Vorlage, Verfahren 2. statt 1. Ordnung bei
  gleicher NFE-Zahl), Spectrum auf Bypass (prognostiziert den gepackten Video+**Audio**-Zustand;
  `audio_blend_weight = 0.0` hält Audio nachweislich **nicht** exakt). Alle drei stammten aus
  `tools/integrate_h3_turbo_lora.py`, das mitkorrigiert wurde.
- **Defekt reproduziert:** Ref2VA auf isolierter Bench-Instanz nachgestellt (+0,7 dB Original,
  −0,3 dB Reproduktion). Fix im kontrollierten Paar: **−0,3 → −2,7 dB (2,4 dB besser)**.
- **Konsolidierung** (`tools/consolidate_workflows_v113.py`): 3 General-Prompt-Enhancer → 1 mit
  Modell-Presets, Ref2VA-Dublette entfernt (234 → 231 Dateien). Die beiden Official-Guide-Enhancer
  bleiben bewusst getrennt (unterschiedliche Ausgabeverträge, keine reine Modellvariante).
- **Update-Skript v1.1.3:** `param()`-Block (`-ComfyUIRoot`, `-ReleaseVersion`, `-DryRun`,
  `-LogPath`, `-RestoreFrom`, `-IncludeUpstream`, `-UpdateDependencies`, `-Force`), Logdatei,
  Trockenlauf, Wiederherstellung über `restore-map.json`, Manifest v2 mit SHA-256 je Datei und
  daraus abgeleiteter Schutz persönlich veränderter Dateien, Alt→Neu-Bericht. Pauschale
  `pip install --upgrade`-Läufe und Upstream-Pulls wurden hier zu Opt-in gemacht.
  **Korrigiert in v1.1.6 (2026-09-06):** Das Opt-in war nicht beauftragt und ließ den
  Standardaufruf über die `.bat` ComfyUI-Core, Pixaroma, Spectrum und pip/torch ungeändert.
  Beides ist wieder Standard; `-SkipUpstream` und `-SkipDependencies` schalten es gezielt ab.
  `-ReleaseVersion` folgt ohne Angabe dem neuesten erreichbaren Tag statt einem fest
  eingetragenen `v1.1.3`.
- **Prüfungen grün:** pytest 279 bestanden (1 übersprungen), `validate_workflows.py` plain und
  `--against-head` je 0 Fehler, beide Migrationswerkzeuge idempotent, PowerShell-Syntaxprüfung OK.

### Verlauf der Hörabnahme

Hörabnahme durch den Nutzer am 2026-09-06: **„Fix ist definitiv besser, aber immer noch eine
roboterhafte Stimme im Vergleich zum offiziellen Workflow."** Der Fix ist damit als Verbesserung
bestätigt und wurde auf Anweisung als **v1.1.3 veröffentlicht**; das Problem ist aber nicht gelöst.

Der wichtigste noch ungeprüfte Verdacht ist die **8-Schritt-Turbo-Destillation**. Der kontrollierte
Vergleich `00002_`/`00003_` belegt einen identischen *Rauschboden* (0,6 dB) — er sagt aber nichts
über *Klangfarbe und Prosodie*, also genau die Größen, die „roboterhaft" beschreibt. `00002_`
(Turbo an, 8 Schritte) wurde nie bewertet; dieser Hörvergleich kostet nichts und entscheidet.

### Nacharbeit v1.1.4 (2026-09-06, nach der Hörabnahme)

- **Turbo-LoRA endgültig entlastet.** Der Nutzer hat `00002_` (Turbo) gegen `00003_` (kein Turbo)
  gehört: beide klingen gut. Ein Turbo-Qualitätsschalter wurde deshalb **nicht** gebaut.
- **Geräteaufteilung und SigmaShift sind exakte No-ops.** Kontrollierter Dreiervergleich bei
  identischen Eingaben: offizielle Konfiguration, + `DaWMultiGPUDeviceControl`, + `MiniMaxH3SigmaShift`
  (12.0/3.0) liefern **bitidentisches** Audio (SHA-256 über die dekodierten PCM-Daten). Der Audiopfad
  unserer Workflows ist nach v1.1.3 byte-für-byte der offizielle.
- **Methodische Korrektur:** Der HF-Abstand streut allein durch den Seed um ±7 dB (Seitenverhältnis-
  Test kehrte sich beim zweiten Seed vollständig um). Die früher berichteten 2,4 dB für den
  v1.1.3-Fix liegen **innerhalb dieser Streuung** und sind kein belastbarer Effektnachweis; der Fix
  bleibt durch die Hörabnahme und die Rücknahme dokumentierter Abweichungen begründet.
- **Vorverarbeitung geprüft — kein Defekt, sondern Schutz.** `MiniMaxH3ImageToVideo` skaliert den
  `first_frame` mit `crop="disabled"`, also reines Verzerren auf die Latent-Geometrie; unsere
  `PixaromaResizeCrop`-Kette verhindert genau diese Quetschung. Unser **echter** FL2VA-Graph mit den
  Eingaben des offiziellen Laufs: HNR 5,67 gegen 5,84, Silbenrhythmus 14,6 gegen 13,6, HF-Abstand
  −25,3 gegen −26,5 dB — alles innerhalb der Seed-Streuung. **Bei gleichen Eingaben ist unser
  Workflow messtechnisch gleichwertig zum offiziellen.**
- **Verbleibende Unterschiede sind Eingaben, nicht Pipeline:** anderer Seed, anderes Referenzbild,
  andere Dauer, anderes Seitenverhältnis. Nur der Prompt war identisch. H3 ist bild-konditioniert
  (das Referenzbild geht über `clip.tokenize(prompt, images=...)` in den VLM ein und prägt die
  Stimme mit).

### Abschluss: Hörabnahme bestanden

Der Nutzer hat A (offizieller Graph), B (unser Workflow, gleiche Eingaben) und C (unser Workflow,
16:9) gehört: **alle drei klingen gut.** Damit ist der v1.1.3-Audiofix als Lösung bestätigt, das
16:9-Format bleibt unverändert, und die zwischenzeitliche Beobachtung „immer noch roboterhaft"
stammte aus einem Vergleich mit anderen Eingaben (Seed, Referenzbild, Dauer) — nicht aus einem
Restdefekt. H3 ist bild-konditioniert.

**v1.1.4** enthält darüber hinaus zwei echte Korrekturen am Update-Skript, die beim ersten
Produktivlauf von v1.1.3 aufgefallen sind: der eingebettete Abschluss-Validator verstand das neue
Manifest-Format v2 nicht (Abbruch mit ExitCode 1 nach erfolgreicher Übernahme), und der Trockenlauf
führte die beiden Abhängigkeits-Pins tatsächlich aus, statt sie nur anzuzeigen.

### Offen aus dem Auftrag (nicht umgesetzt)

- **§5 Sekundensteuerung** über alle Video-Workflows. Der vorhandene Sekunden-Vertrag (53
  Workflows) und das H3-Raster (17k+5, `align_frame_count`) sind geprüft und korrekt, aber nicht
  auf die übrigen Modelle ausgeweitet.
- **§6 zentrale Ein/Aus-Schalter** für optionale Funktionszweige.
- **w4a8-Quantisierung** (Textencoder 15,7 GB statt 27 GB) — auf Nutzerwunsch zurückgestellt. Die
  offizielle 4-Bit-Variante `nvfp4_awq` ist für gfx1201 ungeeignet (keine HIP-Kernel,
  Projekt-Blacklist); passend wäre nur die Community-`w4a8`.
- **v1.1.2 wurde nie getaggt** (Tags springen von v1.1.1 auf v1.1.3).

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
