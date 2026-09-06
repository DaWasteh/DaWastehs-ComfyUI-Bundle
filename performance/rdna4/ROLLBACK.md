# ROLLBACK · Ausgangszustand, Änderungen, Rückweg

## Ausgangszustand (gesichert 2026-09-05 21:48, `baseline_state/`)

| Datei | Inhalt |
|---|---|
| `repo_git_head.txt`, `repo_git_status.txt` | Repo `L:\GitHub\DaWastehs-ComfyUI-Bundle` auf `1d8da1c` (v1.1.0), nur `COMFYUI_RDNA4_GOAL.md` untracked |
| `comfyui_git_head.txt`, `comfyui_git_status.txt`, `comfyui_worktree.diff` | ComfyUI `250b2e95` (0.34.0) mit dem bestehenden lokalen Patch in `comfy/samplers.py` |
| `start-MultiGPU.ps1.orig`, `start-MultiGPU.bat.orig`, `start-R9700.ps1.orig`, `start-9070XT.ps1.orig`, `windows_comfy_launcher.py.orig` | Startskripte und Launcher aus `L:\ComfyUI\` |
| `comfy_samplers.py.orig` | vollständige Datei |
| `pip_freeze_venv.txt` (352 Pakete), `pip_version.txt` | Paketstand `L:\ComfyUI\.venv` (keine Paketänderung in diesem Durchlauf) |
| `custom_nodes_state.txt` | Commit-Hashes bzw. „kein git" aller 40 Custom-Node-Ordner |
| `sha256_originals.txt` | Prüfsummen der drei Produktionsdateien, gegen die `bench/rollback.py` vergleicht |

## Änderungen an der Produktionsinstallation `L:\ComfyUI`

| Nr. | Änderung | Umfang | Rückweg | Prüfstatus |
|---|---|---|---|---|
| P1 | Ordner `L:\ComfyUI\ComfyUI\input\lora_training\_rdna4_bench\` (3 PNG + 3 TXT, Benchmark-Datensatz) | neu, 6 Dateien | `python bench/rollback.py --apply` löscht den Ordner | Dry-Run `bench/rollback.py` am 2026-09-05 22:11 zeigte korrekt `[remove] … (6 files)` und alle drei Produktionsdateien `== original` |
| P2 | Startprofil `start-MultiGPU.ps1` | **unverändert** (SHA-256 `37a8e28f…` wie Original, erneut geprüft nach Abschluss) | falls später ein neues Profil kopiert wird: `bench/rollback.py --apply` stellt `baseline_state/start-MultiGPU.ps1.orig` wieder her, aber nur wenn die Live-Datei exakt der installierten Version aus `profiles/installed/` entspricht (Schutz vor Überschreiben späterer Nutzeränderungen) | Hash-Vergleich getestet (Dry-Run) |
| P3 | `comfy/samplers.py`, Launcher | unverändert | wie P2 | Hash-Vergleich getestet |
| – | Custom Nodes, venv-Pakete, Modelle, Treiber, Registry, Pagefile | nicht angefasst | – | – |

Die Benchmark-Instanz schrieb ausschließlich nach `performance/rdna4/raw/server_*/output|temp` und `performance/rdna4/bench/bench_state/*.db`; die Produktions-DB `user/comfyui-multigpu.db` blieb unberührt.

## Änderungen im Repo (Git-verwaltet)

| Nr. | Änderung | Rückweg |
|---|---|---|
| R1 | Neue Dateien `performance/rdna4/**`, `GOAL_STATUS.md`, `COMFYUI_RDNA4_GOAL.md` | `git rm -r performance/rdna4 GOAL_STATUS.md` bzw. Commit zurücksetzen (`git revert <commit>`; kein `git reset --hard`) |
| R2 | 78 Workflow-Kopien unter `performance/rdna4/workflows/<Kategorie>/<Name>.json` (identisch mit den geänderten Repo-Dateien, gleicher relativer Pfad) | Kopien löschen |
| R3 | **In `workflows/` übernommen (v1.1.1, nach Regression):** 78 Dateien = 3× WAN-I2V-Korrektur (B1), 5× TrainLora-Widget (B2), 67× `VRAM_Debug.unload_all_models=False` (E1, nur Bild-/Audio-Kategorien; davon 14 zusätzlich mit Geräte-Control gpu:0 = E2), 3× LTX CLIP gpu:0 (E2b); jede Datei trägt `extra.dawasteh_rdna4_v111` | vor dem Commit `git checkout -- workflows/`; nach dem Commit `git revert <v1.1.1-Commit>` oder `git checkout v1.1.0 -- workflows/` (kein `git reset --hard`) |
| R4 | `tools/upgrade_v111.py` (deterministische Migration), `tools/validate_workflows.py` (v111-Schritt, Link-Summe 7211), `tools/migrate_workflows_v092.py` (Gerätetabelle für die 17 umplatzierten Workflows), `tests/test_upgrade_v111.py`, `tests/test_workflow_refinement.py` (Erwartung `seed_control_after_generate`), README/docs | Git |
| – | Startprofile: **kein** Produktions-Startprofil geändert; kein Profil-Kandidat war besser als v0.9.8 (siehe REPORT.md) | – |
| – | venv/Pakete/Custom Nodes/ComfyUI-Code: unverändert | – |

## Getesteter Rückweg

`bench/rollback.py` wurde am 2026-09-06 an Kopien in einem Scratch-Ordner geprüft (`raw/rollback_restore_test.txt`): unveränderte Datei → `[ok]`; von diesem Durchlauf installierte Version → wiederhergestellt und SHA-256-identisch mit dem Original; nachträglich vom Nutzer geänderte Datei → `[SKIP] … manual review` (Exit 1, Datei unangetastet). Der Dry-Run gegen die echten Produktionsdateien meldete alle drei als `== original`.

## Rollback-Skript

```powershell
L:\ComfyUI\.venv\Scripts\python.exe performance\rdna4\bench\rollback.py            # Vorschau
L:\ComfyUI\.venv\Scripts\python.exe performance\rdna4\bench\rollback.py --apply    # ausführen
L:\ComfyUI\.venv\Scripts\python.exe performance\rdna4\bench\rollback.py --apply --remove-bench-db
```

Das Skript überschreibt keine Datei, die weder dem Original noch der von diesem Durchlauf installierten Version entspricht; solche Fälle werden als `[SKIP] … manual review` gemeldet (Exit-Code 1).

## Testinstanz beenden

```powershell
L:\ComfyUI\.venv\Scripts\python.exe performance\rdna4\bench\comfy_server.py stop --run-dir performance\rdna4\raw\<server_ordner>
```

`comfy_server.py stop` verweigert das Beenden jedes Prozesses, dessen Kommandozeile `--port 8188` oder `--port 8189` enthält.
