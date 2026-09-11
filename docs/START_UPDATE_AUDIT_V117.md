# Start-/Update-Audit v1.1.7 · 11. September 2026

## Geprüfter Stand

- Windows 11, Intel Core Ultra 9 285K (24 Kerne/Threads), 48 GB Host-RAM.
- HIP `gpu:0`: Radeon AI PRO R9700, 32 GB; `gpu:1`: Radeon RX 9070 XT, 16 GB; beide `gfx1201`.
- ComfyUI `6338e4bd428247a4a8843496aa98fb7f2a9d3632` vom 10. September. `git ls-remote https://github.com/comfy-org/ComfyUI.git HEAD` ergab denselben Commit: zum Prüfzeitpunkt aktuellster Upstream-Core.
- PyTorch `2.13.0+rocm10.1.0a20260822`, HIP `7.16.26332`, comfy-kitchen `0.2.33`, comfy-aimdo `0.5.3`, Frontend `1.51.10`.
- Der bestehende lokale Patch an `ComfyUI/comfy/samplers.py` wird nicht verändert. Keine Modelle, Workflow-Inhalte, Treiber oder Python-Pakete werden für diesen Skript-Release geändert.

Primärquellen: installierter Core und dessen `comfy/cli_args.py`, `main.py`, `comfy/model_management.py`, `comfy/model_prefetch.py`; Versionsabfrage im echten ComfyUI-venv. Historische A/B-Messungen: [RDNA4-Bericht](../performance/rdna4/REPORT.md).

## Performance-Entscheidung

| Einstellung | Entscheidung und Grund |
|---|---|
| Beide HIP-Geräte, `--default-device 0` | Beibehalten. Verhindert unerwünschten Windows-Single-GPU-Modus; Reihenfolge wird überprüft. |
| hipBLASLt, PyTorch-SDPA/AOTriton | Beibehalten. Im vorhandenen A/B-Bericht schneller als klassisches hipBLAS; keine Pflicht zu externem FlashAttention/Triton. |
| `--cache-ram`, Smart Memory an | Beibehalten. Klassisches Caching erhöhte bei WAN den RAM-Druck. Ohne explizite Schwellen gelten die aktuellen Upstream-Defaults. |
| `--reserve-vram 4`, VRAM-Guard mit 3 GiB Reserve | Beibehalten. Weniger Reserve und Host-RAM-Spilling waren nachgewiesene Stabilitäts-/Performanceprobleme. |
| DynamicVRAM, Async Offload, Pinned Memory aus | Beibehalten. Der 48-GB-Host ist bei großen Video-/Audio-Modellen knapp; DynamicVRAM 0.5.2 war deutlich langsamer bzw. hing. 0.5.3 ist **nicht neu A/B-verifiziert**. |
| CK-Attention, `--fast fp8_matrix_mult` | Weiter nur Opt-in. CK kann schneller sein, verändert aber die Numerik; kein pauschaler Qualitätsnachweis. RDNA4-FP8-Unterstützung wird bereits automatisch erkannt. |
| CPU-Threadzahl | Unverändert 24; kein aktueller End-to-End-Nachweis für eine bessere alternative Anzahl. |
| Neue Comfy-Compiler-Flags | Kein zusätzliches Disable-Flag nötig. `model_prefetch.compilation_enabled()` setzt `aimdo_enabled` voraus, das im statischen Profil aus ist. Der Comfy-Compiler ist **nicht** einfach `torch.compile`/Triton. |

Alle tatsächlich verwendeten Flags werden vom aktuellen Parser akzeptiert. `--disable-dynamic-vram` funktioniert weiterhin, obwohl ComfyUI seine spätere Entfernung ankündigt. Es wird bei einem zukünftigen Wegfall **nicht still entfernt**: der neue CLI-Preflight bricht vor dem GPU-/Serverstart ab.

**Kein neuer Geschwindigkeitsgewinn behauptet.** Dies ist ein Kompatibilitäts-/Sicherheitsrelease mit unveränderten Performance-Defaults. Die alten Messungen belegen eine konservative Ausgangsbasis, nicht das absolute Optimum des neuen Stacks. Während dieser Prüfung testete eine andere Sitzung HIP/Vulkan-LLMs; deshalb keine konkurrierenden Modell-, Trainings- oder RAM-Stresstests. Der VRAM-Guard berücksichtigt freien Speicher beim Initialisieren, nicht spätere Allokationen anderer Programme.

## Behobene Skriptfehler

1. **Launcher wurden gar nicht verteilt.** Die installierte MultiGPU-PS1 entsprach noch v0.9.8 (CRLF): die Attention-Opt-in-Korrektur und die expliziten VRAM-Guard-Schalter aus späteren Releases waren nicht angekommen. Jetzt werden genau `tools/start-MultiGPU.ps1` und `.bat` aus dem festgehaltenen Git-Commit synchronisiert, gesichert und im Manifest/Abschlussvalidator erfasst. Der komplette `tools/`-Baum wird nicht verteilt.
2. **Erste Launcher-Übernahme ohne Datenverlust.** Historische, unveränderte Git-Inhalte werden auch bei Windows-Zeilenenden/BOM erkannt. Persönliche oder unbekannte Änderungen werden nicht ungefragt ersetzt. Anschließend erfolgt immer eine binäre Commit-Blob-Kopie. Geschützte Abweichungen ergeben weiterhin einen nicht erfolgreichen Validierungsabschluss, statt eine vollständige Installation vorzutäuschen; `-Force` ist eine bewusste, globale Überschreiboption mit Backup.
3. **`-SkipDependencies` lief trotzdem durch pip.** Qwen-Pins sowie DirectML-Uninstall/Force-Reinstall werden jetzt ebenfalls ausgelassen. Ohne den Schalter bleiben Upstream-/Paketupdates Standard.
4. **Requirements-Retry.** Anforderungen aller eigenen Packs werden ohne pauschales `--upgrade` erneut geprüft. Nach einem übersprungenen/fehlgeschlagenen pip-Lauf gelten bereits kopierte Nodes nicht mehr fälschlich als erledigte Abhängigkeitsinstallation.
5. **Trockenlauf war nicht trocken.** Keine persistenten Log-/Zielverzeichnisse, kein Entfernen des Legacy-Klons, keine Paketänderungen, kein Abschlussvalidator gegen ein noch nicht aktualisiertes/fehlendes Manifest. Kurzlebige Blob-Dateien in `%TEMP%` werden entfernt; auch explizites `-LogPath` erzeugt im Trockenlauf kein Log.
6. **MultiGPU-Startfenster war ungeschützt.** Der Updater erkennt die laufende PS1 schon vor dem Port-Binding und berücksichtigt `-ComfyUIRoot` statt nur fest codierter Pfade.
7. **Lokaler Branch ohne Upstream.** Die Abfrage vermeidet erwarteten Git-stderr, der unter Windows PowerShell 5.1 mit `ErrorActionPreference=Stop` trotz Umleitung vorher den vorgesehenen lokalen Release-Pfad abbrach.
8. **Startprüfung ohne Server.** `-CheckOnly` prüft die konkrete CLI-Kombination und ROCm/HIP/GPU-Reihenfolge. CLI-/GPU-Fehler stoppen den Launcher. Installierte Kopien nutzen ihren eigenen Root; direkte Repo-Aufrufe behalten den Maschinenstandard, `-ComfyUIRoot` überschreibt ihn. Pfadprüfungen und Verzeichniswechsel verwenden `-LiteralPath`, auch für Roots mit Leerzeichen oder eckigen Klammern.

## Regression und Grenzen

- Windows-PowerShell-AST-Prüfung beider PS1-Dateien; echte `-CheckOnly`-Ausführung mit beiden AMD-Karten, ohne Server/Modelle.
- Gesamtsuite: `L:/ComfyUI/.venv/Scripts/python.exe -B -m unittest discover -s tests`: **295 Tests, 294 bestanden, 1 bestehender Skip**, keine Fehler.
- `python -B tools/validate_workflows.py --against-head`: 231 Dateien, 284 Graphen, 10.335 Nodes, 7.143 Links, **0 Fehler**; Workflow-Semantik unverändert.
- Neue Windows-Fixtures führen den vollständigen Updater mit temporärem Git-Repository aus. Netzwerk/pip werden aufgezeichnet statt ausgeführt; der eingebettete Commit-/Manifest-Validator läuft echt. Abgedeckt: Erstinstallation, v1.1.6-Übernahme ohne Force, CRLF/BOM, Backup, Allowlist, eigene Änderungen, Idempotenz, DryRun mit altem Manifest/Legacy-Klon/LogPath, SkipDependencies, Standard-Paketpfad, Startup-Fenster, CLI-/GPU-Fehler, Attention-Alternativen und benutzerdefinierte Roots.
- Die volle Suite deckte einen **bestehenden Testfixture-Fehler** auf: der synthetische LiveAvatar-HTTP-Dienst schloss unautorisierte POST-Verbindungen vor dem Lesen des Request-Bodys; unter Windows kam teilweise ein Connection Reset statt des erwarteten 401/403 an. Ausschließlich die Fake-Service-Fixture liest jetzt den kleinen Body vor ihrer unveränderten Auth-Prüfung. Der Produktions-Supervisor und dessen Sicherheitsprüfungen bleiben unverändert. Die komplette Suite bestand anschließend; keine gelockerten Assertions oder zusätzlichen Skips.
- Unabhängige Read-only-Reviews prüften Flags und Update-Integration. Die gefundenen Übernahme-/Root-Probleme wurden vor Freigabe korrigiert und mit Fixtures abgesichert.
- Kein vollständiger End-to-End-Lauf aller Modelle und keine Installation neuer Abhängigkeiten. Ein erfolgreicher Skripttest kann zukünftige Upstream-/Nightly-Paketregressionen nicht ausschließen. `-RestoreFrom` stellt gesicherte Bundle-Dateien wieder her, **keine** frühere Torch-/pip-Umgebung und keinen früheren Core-Commit.

## Bedienung

```powershell
L:\ComfyUI\start-MultiGPU.ps1 -CheckOnly
L:\ComfyUI\update-comfyui-rdna4.ps1 -DryRun
L:\ComfyUI\update-comfyui-rdna4.ps1 -SkipUpstream -SkipDependencies
```

Vor echten Updates die ComfyUI-Instanzen sauber beenden. Den neuen installierten PowerShell-Updater bei der ersten Übernahme direkt verwenden; ein bereits laufender alter Updater lädt sich nicht mitten im Lauf neu. Alte Solo-Launcher (`start-R9700.ps1`, `start-9070XT.ps1`) sind kein Teil des versionierten Dual-GPU-Profils und werden nicht still verändert.
