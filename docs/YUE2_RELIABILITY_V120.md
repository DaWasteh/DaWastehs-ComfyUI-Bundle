# YuE2-Zuverlässigkeit · v1.2.0

## Zwei unterschiedliche Fehler

1. **Latents verschwinden während des Encodings:** Der v1.1.9-Trainer legte seinen Standardcache unter `ComfyUI/temp/yue2_latents` ab. Mehrere GPU-Instanzen teilten diesen Baum. ComfyUI entfernt ihn beim Start und beim ordentlichen Beenden; dadurch konnte eine zweite Instanz die aktiven Trainingsdaten der ersten löschen. Der Fehler trat beim Schreiben einer `.tmp.npy` auf, nicht auf der GPU.
2. **MP3-Decoder bricht ab:** TorchAudio benötigt in diesem Stack TorchCodec. Ohne dieses Paket fiel der alte Loader auf SoundFile zurück, das eine konkrete MP3 mit `LibsndfileError: Unspecified internal error` nicht lesen konnte. Dieselbe Datei ließ sich mit dem vorhandenen FFmpeg vollständig und ohne gemeldete Decoderfehler lesen. Das ist weder eine Zehn-Minuten-Grenze noch ein Beleg für eine defekte GPU.

## Änderungen

- Leeres `cache_folder` nutzt jetzt **`<ComfyUI>/training_cache/yue2_latents`**. Relative Pfade beziehen sich auf den ComfyUI-Root. Der aktive Temp-Ordner und der alte gemeinsame `ComfyUI/temp`-Baum werden als Cacheziele abgelehnt. Bei eigenen Pfaden ebenfalls alle anderen temporären Verzeichnisse meiden.
- Bestehende explizite, dauerhafte Cachepfade bleiben nutzbar. Cache-Schlüssel sind unverändert: Checkpoint, Datensatz, Dateigröße/-zeit und Clipdauer bestimmen die Wiederverwendung. Keine automatische Migration gelöschter Temp-Daten und kein erzwungenes Neu-Encoding.
- Atomische Cache-Schreibvorgänge verwenden eindeutige Staging-Dateien. Eine abschließende Existenzprüfung erkennt zwischenzeitlich verschwundene Latents, statt einen unvollständigen Datensatz ans Training zu geben.
- Audio wird über **SoundFile → TorchAudio → FFmpeg** gelesen. FFmpeg wird auf PATH oder über das vorhandene `imageio-ffmpeg` gefunden. Kein TorchCodec-/CUDA-Paket wird nachinstalliert und der AMD-Torch-Stack bleibt unverändert.
- FFmpeg läuft ohne Shell, mit explizitem ersten Audiostream, Stereo/48-kHz-Float32, dateigepuffertem PCM, begrenzter Laufzeit und Abbruchprüfung. Fehlermeldungen nennen Quelldatei und Decoder. **Keine automatische Dateilöschung und kein stilles Überspringen defekter Quellen.** Bereits fertige Latents bleiben beim Wiederholen nutzbar.
- Der gemeinsame **`scripts/windows_comfy_launcher.py`** weist jedem gestarteten Server einen eigenen Temp-Root unter `<Installation>/tmp/comfyui-<port>-<supervisor-pid>/temp` zu. Das schützt auch einen zweiten Startversuch auf demselben Port. Die lokalen R9700-, RX9070XT- und MultiGPU-Profile nutzen denselben Supervisor. Explizites `--temp-directory` bleibt erhalten; bei manuellen Starts muss der Aufrufer selbst einen exklusiven Pfad wählen.
- Der Bundle-Updater verteilt den Supervisor aus Commit-Blobs, mit Hash-Prüfung, Backup und Schutz persönlicher Änderungen. Nur der exakt bekannte alte Supervisor wird ohne bisherigen Manifest-Eintrag automatisch übernommen. Die GPU-/Speicher-/BLAS-Startdefaults ändern sich nicht.
- Beim erneuten echten Frontend-Export wurde der inzwischen hinzugekommene optionale Core-Eingang `YuE2GenerateMusic.cfg_scale` mit dem aktuellen Standard **1.0** in Schema/Workflow aufgenommen. Der aktuelle API-Vertrag ist separat vom historischen v1.1.9-Vertrag gespeichert; keine nachträgliche Umschreibung alter Messergebnisse.

## Installation und Wiederholung

ComfyUI vor dem Upgrade beenden. Den normalen Bundle-Updater für Workflows und Supervisor verwenden; wer nur die Bundle-Dateien aktualisieren will, setzt `-SkipDependencies -SkipUpstream`. Der getrennt gepinnte Trainer braucht weiterhin ein bewusstes Upgrade:

```powershell
L:/ComfyUI/.venv/Scripts/python.exe tools/install_yue2_lora_node.py --comfy-root L:/ComfyUI/ComfyUI --upgrade
L:/ComfyUI/.venv/Scripts/python.exe tools/install_yue2_lora_node.py --comfy-root L:/ComfyUI/ComfyUI --verify-only
```

`--upgrade` akzeptiert nur den unveränderten v1.1.9-Snapshot oder die bereits aktuelle Version. Der neue Snapshot wird vor dem Austausch vollständig geprüft; der bisherige Trainer bleibt unter `<Installation>/backups/yue2-trainer-v119-…` erhalten, **außerhalb** von `custom_nodes`. Bei abweichendem Eigenbau erfolgt kein Überschreiben. Keine zusätzlichen Modelle oder Python-Pakete werden installiert.

Im Dataset-Node `cache_folder` leer lassen oder einen dauerhaften absoluten Pfad angeben, `force_reencode=false`. Nach dem Serverneustart erneut queuen. Bei wirklich nicht dekodierbarer Musik die genannte Datei reparieren oder bewusst aus dem Datensatz nehmen; ein Dateiname allein oder eine ID3-Kommentarwarnung ist kein Löschgrund.

Die ausgelieferten 100-Schritte-/6s-/Rank16-Defaults bleiben ein sicherer **Kurztest**, kein Qualitätsversprechen. Ein privates Langtraining ist separat zu konfigurieren. Dateien kürzer als die gewählte Clipdauer werden weiterhin gemeldet und nicht als Trainingsclips verwendet; Endstücke unter einer Clipdauer fallen weg. Alle Dateien werden beim Dataset-Bau geprüft, aber der Trainer zieht seine Clips zufällig: Ein erfolgreicher Lauf garantiert nicht, dass jeder Clip gezogen wurde.

## Verifikation

Der aktuelle maschinenlesbare Nachweis steht unter [`performance/rdna4/yue2-lora-v120-validation.json`](../performance/rdna4/yue2-lora-v120-validation.json). Der frühere v1.1.9-Nachweis bleibt als historischer Bericht unverändert; seine Hashes gehören zur damaligen Version.

Regressionsprüfungen umfassen 612 synthetische Cacheeinträge samt Wiederverwendung, echte FFmpeg-Dekodierung mit Unicode-Pfad, alle Decoderfehler, Abbruch, verlorenen Cache, Temp-Isolation und geschütztes Snapshot-Upgrade. Zusätzlich wurde ComfyUIs tatsächlich installierte Cleanup-Funktion ausgeführt: Der andere Instanzbaum und eine bereits aktive Trainingscachedatei blieben unverändert.

### Vollständiger Lauf auf der R9700

| Prüfung | Ergebnis |
|---|---|
| Privater Datensatz | **612/612 Quellen**, 3.386 × 42s Clips, 2.370,2 Minuten nutzbare Clipdauer; keine Datei gelöscht |
| Vorbereitung | 205 vorhandene Caches wiederverwendet, 407 Quellen neu encodiert; **6 Decoder-Fallbacks erfolgreich** |
| Training | **10.000 Schritte**, Rank/Alpha 64, Warmup 50, AdamW 1e-4, EMA 0.999; rund 0,33s/Schritt, insgesamt **81,1 Minuten inklusive Dataset** |
| Adapter | EMA und Raw je **425.766.912 Bytes**; je 336 endliche Tensoren und 112 nichtnull LoRA-Up-Matrizen |
| Wiederholung | Vollständiger Dataset-Bau aus Cache erfolgreich, etwa 3s Queuezeit |
| Anwendung | Baseline → EMA → Stärke 0: je 30s/48-kHz-Stereo-FLAC; EMA verändert PCM, Stärke 0 stellt die Baseline bitidentisch wieder her |
| Grenzen der Audioprüfung | EMA-Test enthält **6 Vollpegelsamples von 2.880.000**; keine Aussage über hörbare Stilqualität. Baseline ca. 24s Queuezeit, Folgeläufe ca. 6s mit gecachtem AR-Conditioning, daher kein fairer Kaltstart-Performancevergleich |
| Tests | **349 bestanden, 1 übersprungen, 330 Subtests bestanden**; vorhandene Pillow-Warnung |
| Workflow-Validator | Alle 246 Workflows, einschließlich deterministischer Migration von v1.1.9, **0 Fehler** |

Private Musik, Dateilisten, Captions, Adapter und API-Historien bleiben ausschließlich lokal. Öffentliche Nachweise enthalten nur technische Aggregate, Konfigurationen und Hashes. Erfolgreiches Training und lesbare Adapter sind keine Hörabnahme und keine Stiltreue-/Voice-Cloning-Garantie. YuE2 bleibt ausschließlich privat/nichtkommerziell gemäß CC-BY-NC-4.0.
