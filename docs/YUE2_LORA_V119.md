# YuE2 · privates Stil-LoRA-Training und Anwendung · v1.1.9

## Was dieser Workflow kann

Zwei native ComfyUI-Workflows im bekannten RODENT-Stil (Nerdy Rodent), mit deutschen Einstiegshinweisen, Parameterreferenzen, zentraler GPU-Steuerung und jeweils einem Pixaroma-Timer:

- **Training:** `workflows/LoRA Generation/YuE2_3B_BF16-PRIVATE-Style-LoRA-Training.json`
- **Anwendung:** `workflows/Music Generation/YuE2_3B_BF16-PRIVATE-LoRA-Music-Generation.json`

Der Trainer lernt **echte Low-Rank-Adapter der akustischen NAR-Stufe**. Ziel sind Klangstil, Instrumentierung und Stimmfarbe. Das AR-Text-/Kompositionsmodell bleibt eingefroren. Das ist **kein verlässliches Voice-Cloning** und kein Training des gesamten YuE2-Modells. Die Trainingsaufgabe ist aus der veröffentlichten Inferenz rekonstruiert und bleibt experimentell.

YuE2-Gewichte: **CC-BY-NC-4.0**, Quellenangabe und nichtkommerzielle Nutzung beachten. Hier ausdrücklich für private Projekte; Streaming-Songs weiterhin mit ACE-Step erstellen. Nur eigene oder ausreichend freigegebene Aufnahmen verwenden. Weder Gewichte noch Adapter, Audio oder private Songtexte werden mit dem öffentlichen Bundle verteilt.

## Installation

Benötigt: aktueller ComfyUI-Core mit nativen YuE2-Nodes, Pixaroma, Bundle-MultiGPU-Control, Starnodes-YuE2-Trainer sowie der **BF16**-Checkpoint. INT8/convrot wird nicht trainiert und ist für diese LoRA-Anwendung nicht freigegeben. Vorhandene INT8-Workflows und Gewichte bleiben unverändert.

Im Bundle-Repository, während ComfyUI beendet ist:

```powershell
# Gepinnter Trainer mit geprüftem Windows-/RDNA4-Patch:
L:/ComfyUI/.venv/Scripts/python.exe tools/install_yue2_lora_node.py --comfy-root L:/ComfyUI/ComfyUI

# 7.799.983.228 Bytes, nur nach ausdrücklichem nichtkommerziellem Opt-in:
L:/ComfyUI/.venv/Scripts/python.exe tools/install_yue2_lora_model.py --comfy-root L:/ComfyUI/ComfyUI --accept-noncommercial

# Offline-Dateiprüfung:
L:/ComfyUI/.venv/Scripts/python.exe tools/install_yue2_lora_node.py --comfy-root L:/ComfyUI/ComfyUI --verify-only
L:/ComfyUI/.venv/Scripts/python.exe tools/install_yue2_lora_model.py --comfy-root L:/ComfyUI/ComfyUI --verify-only
```

Die Installer installieren **keine Python-Pakete** und verändern keine Torch-/ROCm-Version. `soundfile`, `matplotlib`, `safetensors`, `tokenizers`, `transformers` und PyTorch waren lokal bereits vorhanden. Nur falls nötig die beiden zusätzlichen Pakete `soundfile matplotlib` mit der ComfyUI-Python-Umgebung installieren, ohne pauschales Upgrade. Kein bitsandbytes/FlashAttention/Triton nötig. Danach ComfyUI neu starten und die beiden JSON-Dateien öffnen; lokal liegen sie zusätzlich unter `user/default/workflows/DaWasteh/`.

Der Trainer wird als revisions- und dateigeprüfter Snapshot **ohne `.git`** installiert. Allgemeine Upstream-Pulls können dadurch nicht versehentlich den getesteten Patch ersetzen. Er gehört nicht zu den automatisch aktualisierten eigenen Node-Packs. Ein späteres Trainer-Upgrade muss bewusst geprüft und installiert werden; vorhandene abweichende Dateien werden nicht überschrieben. Der normale Bundle-Updater verteilt die beiden Workflows, lädt aber weder Trainer noch Modell automatisch herunter.

### Gepinnte Quellen

| Bestandteil | Version / Nachweis |
|---|---|
| [Starnodes2024/ComfyUI-YuE2-Trainer](https://github.com/Starnodes2024/ComfyUI-YuE2-Trainer) | `4578039513304149fdfd1c00a22783f06812997f` |
| Lokaler Patch | `tools/patches/ComfyUI-YuE2-Trainer-Windows-RDNA4.patch` |
| SHA-256 aller installierten Trainerdateien | `tools/workflow_templates/yue2-lora/trainer-manifest.json` |
| [Comfy-Org/YuE2](https://huggingface.co/Comfy-Org/YuE2) | `8e6fcf0f23252ed188b634bd50d44f4b01fba890` |
| Modell | `models/checkpoints/yue2_3b_bf16.safetensors` |
| Modell-SHA-256 | `33765adbf9813c9a50318218760b2fd819a319862460a04884607581961c6fee` |

Trainercode MIT; mitgelieferter Referenzcode und Drittanbieterhinweise bleiben erhalten (Apache-2.0 und zugehörige Notices). Die Modelllizenz wird dadurch nicht zu MIT.

## Eigene Trainingsdaten

```text
ComfyUI/input/yue2_lora/my_style/
  001.wav
  001.txt
  002.flac
  002.txt
```

- Relative Ordnerangaben beziehen sich auf `ComfyUI/input`, absolute Ordner funktionieren ebenfalls.
- TXT beschreibt **Stil/Instrumente/Stimmcharakter**, nicht zwingend das gesungene Transkript. Beispiel: `instrumental, warm analog synthesizer, pulsing bass, steady electronic drums, 96 BPM`.
- UTF-8 und UTF-8-BOM sind unterstützt. Fehlende TXT-Dateien ergeben leere Captions; alternativ `caption_mode=default` mit einer gemeinsamen Beschreibung.
- Keine rekursive Unterordner-Suche. WAV/FLAC bevorzugen; komprimierte Formate hängen von den installierten Audiodecodern ab.
- Der Loader bereitet 48-kHz-Stereo vor. Clips sind standardmäßig 6s lang; kürzere Dateien und kurze Reststücke werden verworfen. Bei vollständig zu kurzen Daten entsteht ein klarer Fehler.
- Einheitliches, gut beschriebenes Material ist wichtiger als Menge. Für ernsthaftes Stiltraining später z.B. 5–30 geeignete Songs; die tatsächliche Datenmenge und Lizenz müssen selbst geprüft werden.

## Trainieren

1. Beide `checkpoint`-Felder auf dieselbe BF16-Basis setzen.
2. `audio_folder` auswählen; `trigger_word` z.B. `my_style` festlegen.
3. Einen **neuen** `lora_name` ohne Pfadzeichen wählen. Bestehende finale, rohe oder geplante Zwischen-Adapter werden nicht überschrieben.
4. Mit dem sicheren Kurzprofil starten und anschließend das Ergebnis vergleichen.

| Parameter | Ausgelieferter Kurzstart | Weiterführender Ausgangspunkt, separat prüfen |
|---|---:|---:|
| Schritte | 100 | etwa 3000 |
| Clipdauer | 6s | 10s |
| Rank / Alpha | 16 / 16 | 32 / 32 |
| Lernrate | 1e-4 | zunächst 1e-4 |
| Optimizer | AdamW | AdamW |
| Accumulation | 1 | 1 |
| Warmup | 10 | 50 |
| Scheduler | Cosine | Cosine |
| EMA | 0.99 | 0.999 |

**100 Schritte sind kein fertig trainierter Qualitätsadapter.** Für einen noch kürzeren Installationscheck: 5 Schritte, Warmup 0, `log_every=1`. Nicht allein wegen niedrigerem Loss länger trainieren; Überanpassung kann dumpfen oder repetitiven Klang erzeugen.

Ergebnis unter `models/loras/`:

- `<lora_name>.safetensors`: EMA-geglätteter Adapter.
- `<lora_name>_raw.safetensors`: ungemittelter Vergleich.
- Optional `<lora_name>_stepN.safetensors`: Zwischenadapter, **kein Optimizer-/RNG-Resume**.

Loss-/LR-Kurve wird als PNG unter `output/Music/PRIVATE_YuE2/LoRA/` gespeichert; Datensatzübersicht, Pfad und Log sind im Workflow sichtbar. Abbruch funktioniert an Trainingsschritten und VAE-Chunk-Grenzen. Ohne erfolgreichen Abschluss wird kein finaler Adapter exportiert; bereits geschriebene Zwischenadapter bleiben erhalten.

Der VAE-Cache liegt standardmäßig unter `temp/yue2_latents/`, getrennt nach Checkpoint und Datensatz. Jede Queue scannt den Ordner neu, vorhandene Latents können wiederverwendet werden. Bei Audioänderungen ohne verlässliche Größen-/Zeitstempeländerung `force_reencode` einschalten. Der Schalter löscht nur den zugeordneten `.npy`-Cache, keine fremden Dateien im übergeordneten Ordner. Ganze Audiodateien werden im RAM gelesen, die VAE-Verarbeitung ist GPU-seitig gechunkt; das ist **kein unbegrenzter Streaming-Dataset-Loader**.

## GPU und RDNA4-Schutz

R9700 `gpu:0`, BF16, PyTorch-SDPA, klassisches hipBLAS; kein `torch.compile`, kein verpflichtendes CUDA-only-Paket. Im Trainingsgraphen steuert **VAE-GPU das Encoding**, **MODEL-GPU das komplette AR/NAR-Trainingsmodell**. CLIP-GPU ist dort ohne Funktion. Beide Trainingsgeräte sind tatsächlich verbunden, nicht nur beschriftet. Unsichtbare/CPU-Geräte werden abgewiesen; andere GPUs wurden nicht als Trainingsprofil freigegeben.

Der lokale Patch behebt/ergänzt:

- Korrekte `comfy.model_management`-Imports für Entladen und Abbrechen.
- Explicit `inference_mode(False)` **und** `enable_grad()`; reproduzierbare Adapterinitialisierung mit begrenztem RNG-Kontext.
- ROCm ohne fused-AdamW und ohne bitsandbytes-Zwang.
- Eindeutigen Frontend-Seed-Kontrollwert, damit nachfolgende Widgets nicht verrutschen.
- Linkbares Core-`COMBO` für die zentrale GPU-Auswahl.
- Quantisierte Checkpoints ablehnen; nichtendliche Audiodaten, Latents, Losses und Gradienten abweisen.
- Cache-Namensräume, atomische Cache-Dateien und Schutz bestehender Adapter.

Training exklusiv ausführen: vorherige Comfy-Modelle werden entladen. Bei OOM Clipdauer/Rank senken und nach schwerem HIP-Fehler den Server neu starten. Der globale Bundle-VRAM-Guard bleibt aktiv; weder Startskripte noch Core-Dateien werden durch diese Ergänzung verändert.

## Adapter anwenden

1. Musik-Workflow öffnen und LoRA-Liste nach dem Training aktualisieren.
2. Den eigenen nativen YuE2-NAR-Adapter wählen. **Keine YuE-v1-, ACE-Step-, Bild- oder FL-YuE2-AR-LoRAs.**
3. Trainings-Trigger an den Anfang von STYLE setzen, danach Klangbeschreibung; eigene Lyrics optional.
4. **ABC leer lassen.** Der Core verwendet dann automatisch `cot=off`; die sichtbare `mode`-Auswahl wird ignoriert. So bleibt die Anwendung näher am Trainingsmodus, obwohl AR weiterhin semantische Tokens generiert.
5. `strength_model=1.0` als Start, `0.0` als Baseline. Mit denselben beiden Seeds/Prompts vergleichen, dann EMA und `_raw`. Hohe Stärke kann Artefakte verstärken.
6. `max_duration=30s` ist nur eine Obergrenze. Die tatsächlich erzeugte Dauer steuert das Latent direkt. Nach Hörtests längere Obergrenzen wählen.

32 DPM2/SGM-uniform-Schritte, CFG 1, vollständige Stereo-FLAC nach der Queue. Kein kontinuierlicher Audio-Stream. `LoraLoaderModelOnly` verändert nur die akustische NAR-Stufe; AR und VAE bleiben unverändert.

## Validierung und Reproduktion

Die öffentlichen Nachweise stehen in [`performance/rdna4/yue2-lora-v119-validation.json`](../performance/rdna4/yue2-lora-v119-validation.json). Getestet auf Windows/R9700, ComfyUI **0.36.0**, Frontend **1.52.7**, PyTorch **2.13.0+rocm10.1.0a20260822**.

| Prüfung | Ergebnis |
|---|---|
| Echtes Training | 3 eigens synthetisierte 12s-Aufnahmen → 6 × 6s Clips; **100 Schritte**, 196 trainierte Projektionen, 17,43 Mio. trainierbare Parameter; Queue 26,74s einschließlich Encoding/Export |
| Loss-Diagnostik | Erster Einzelwert 0,50915; letzter geloggter 10-Schritt-Mittelwert 0,18985; unterschiedliche zufällige Timesteps, keine Validierungs-Loss-/Qualitätsmessung |
| Adapter | EMA und Raw je 106.474.864 Bytes, 336 endliche Tensoren, alle 112 fusionierten LoRA-Up-Matrizen ungleich null |
| Baseline | 30s, 48 kHz, Stereo; Queue 22,08s, inklusive kalter Modell-/AR-Arbeit |
| EMA / Raw | Je 30s, 48 kHz, Stereo; Queue 3,92 / 3,03s **mit gecachtem AR-Conditioning**, nicht mit kalten Gesamtläufen vergleichbar |
| Signalprüfung | Endliche, nichtstumme Audios, keine Vollpegelsamples; EMA/Raw verändern beide das PCM und unterscheiden sich voneinander |
| LoRA zurück auf 0 | Nach erneutem Modellladen und negativem Test **bitidentisches Baseline-PCM**, Queue 19,28s |
| Überschreibschutz | Erneutes Training unter gleichem Namen endet erwartungsgemäß mit `FileExistsError`; Adapter-Hash unverändert |
| Echter Abbruch | 10.000-Schritte-Lauf nach dem ersten Fortschritt unterbrochen, `execution_interrupted`, kein finaler Adapter; anschließende Musik-Queue erfolgreich |
| Testsuite | **338 bestanden, 1 übersprungen, 330 Subtests bestanden**; bestehende Pillow-Warnung |

Die gespeicherten Graphen wurden durch das **echte Frontend importiert und als API-Prompts exportiert**. Trainingshyperparameter und Musik-Sampling entsprechen den ausgelieferten Defaults. Abweichungen sind nur der synthetische Datensatzordner, private Test-Dateinamen und die bewusst verglichenen LoRA-Stärken/Adapter. Die Testadapter sind Installations-/Funktionsproben, keine mitgelieferten Qualitäts-LoRAs; im normalen Workflow ist anschließend der eigene Datensatz auszuwählen.

Erfolgreiche technische Tests sind **keine Hörabnahme**, keine Stiltreue-Zertifizierung und kein Nachweis von Voice-Cloning. Mehrtausend-Schritte-Training, echte Gesangsdaten, andere GPUs und sehr lange Quellen wurden nicht qualitätsvalidiert. Private Testmedien und Adapter bleiben ausschließlich lokal.

```powershell
L:/ComfyUI/.venv/Scripts/python.exe -m tools.build_yue2_lora_workflows --destination tmp/yue2-rebuild
$env:YUE2_TRAINER_ROOT = 'L:/ComfyUI/ComfyUI/custom_nodes/ComfyUI-YuE2-Trainer'
L:/ComfyUI/.venv/Scripts/python.exe -m pytest tests/test_yue2_lora_v119.py -q
L:/ComfyUI/.venv/Scripts/python.exe tools/validate_workflows.py
```

Die Backend-Tests sind ohne `YUE2_TRAINER_ROOT` ausdrücklich übersprungen; statische Workflow-/Installer-Tests bleiben unabhängig von GPU und Modell verfügbar. Das echte Training ist ein separater ComfyUI-Queue-Test, nicht durch diese Unit-Tests ersetzt.
