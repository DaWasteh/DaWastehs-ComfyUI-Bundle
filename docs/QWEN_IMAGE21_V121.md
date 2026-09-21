# Qwen Image 2.1 · v1.2.1

Zwei explizite RODENT-Workflows auf Basis der vom Nutzer geladenen Comfy-Org-Beispiele:

- `workflows/Text to Image/Qwen_Image_2_1_BF16-Text-to-Image.json`
- `workflows/Image Editing/Qwen_Image_2_1_BF16-Multi-Image-Edit.json`

Beide verwenden Pixaroma Prompt, Resolution, Save Image und Run Timer, der Edit zusätzlich Load Image und Compare. Eine verbundene DaW Multi-GPU-Steuerung steuert die offiziellen MODEL-/CLIP-/VAE-Selectoren. Standard ist **alles auf der R9700 (gpu:0)**. Keine Cloud-API, keine neuen Python-Pakete, kein Eingriff in ComfyUI-Core oder vorhandene Custom Nodes.

## Lizenz

**Qwen RESEARCH LICENSE AGREEMENT**, Stand 20. September 2026: nichtkommerzielle Nutzung ist auf **Forschung und Evaluation** begrenzt. Für kommerzielle Nutzung ist eine gesonderte Lizenz erforderlich. Das ist keine allgemeine Apache-/MIT-Modellfreigabe. Maßgeblich ist die [Modelllizenz](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE), nicht die Lizenz dieses Workflow-Repositories. Hier werden keine Modellgewichte verteilt.

## Modelle und Eingaben

Alle drei lokal vorhandenen Dateien wurden vollständig gegen die SHA-256-Werte von `Comfy-Org/Qwen-Image-2.1` geprüft. Kein zusätzlicher Modelldownload war nötig. Revisions- und Hash-Pins: [`models.json`](../tools/workflow_templates/v121/models.json).

| ComfyUI-Ziel relativ zu `models/` | Größe, dezimal | Verwendung |
|---|---:|---|
| `diffusion_models/Qwen/qwen_image_2.1_bf16.safetensors` | 14,23 GB | gemeinsamer BF16-DiT |
| `text_encoders/Qwen/qwen3vl_8b_int8_convrot.safetensors` | 9,35 GB | gemeinsamer Qwen3-VL-Text-/Bildencoder |
| `vae/qwen-image/qwen_image_2.1_vae_bf16.safetensors` | 0,68 GB | neuer 2.1-VAE, RGBA-Ausgabe |

Die offiziellen Beispiele wählen einen INT8-DiT; das Bundle verwendet bewusst den bereits geladenen **BF16-DiT**, ohne unnötige zweite Modellkopie. Alte Qwen-Image-VAEs und Qwen2.5-VL sind kein Ersatz. Die separaten Qwen3.5-9B-Prompt-Enhancer-Gewichte sind für diese beiden Rechenketten **nicht erforderlich**.

Der Edit startet mit zwei öffentlichen Comfy-Org-Testbildern. Sie wurden nach `ComfyUI/input/` geladen, vorhandene Nutzereingaben bleiben unverändert:

- `portrait_model_denim.png`: Basis, Format 896×1152
- `clothing_light_blue_denim_shirt.png`: zusätzliche Kleidungsreferenz

Die unveränderlichen Download-URLs und SHA-256-Werte stehen in [`inputs.json`](../tools/workflow_templates/v121/inputs.json) und direkt im Workflow. Auf einer anderen Installation beide Bilder dort herunterladen oder durch eigene Bilder ersetzen. Die reguläre Bundle-Synchronisierung verteilt Workflow-JSON, **nicht** diese Eingabebilder oder die Gewichte.

## Bedienung

### Text to Image

1. Positiven Pixaroma-Prompt bearbeiten; persönliches `@tag`-System bleibt nutzbar.
2. Pixaroma Resolution wählen: Start **1024×1024**, Snap **32**. Ausgabegröße ist direkt verbunden.
3. Queue starten. PNGs mit Workflow-Metadaten landen unter `output/Qwen_Image_2_1/T2I_*.png`.

Offizielle Samplerwerte bleiben **25 Schritte, CFG 1, Euler, Simple, Denoise 1**. Seed 0 ist fest; für Variation Seed ändern oder `control_after_generate` auf `randomize` setzen. Bei CFG 1 wird der Negativprompt beim Sampling nicht ausgewertet; das separate Feld ist für bewusst höhere CFG vorhanden.

Für Transparenz den Prompt entsprechend formulieren:

```text
This is an RGBA format image with transparency. A small red enamel robot,
full body, isolated product illustration. The image has an alpha channel
and a transparent background.
```

PNG erhält den Alpha-Kanal. Ein vorhandener Alpha-Kanal allein bedeutet noch keine perfekte Freistellung. JPG entfernt Transparenz und ist für diesen Zweck ungeeignet. 2048×2048 ist die vom Hersteller beschriebene native 2K-Option; höhere Auflösung kostet mehr Zeit und Speicher.

### Multi-Image Edit

1. **Bild 1** ist die Basis, **Bild 2** die zusätzliche Referenz. Im Prompt mit `<image1>` und `<image2>` darauf verweisen.
2. Pixaroma Load Image startet mit Resize **off**. Die Skalierung übernimmt **einmal** der offizielle `TextEncodeQwenImage21`.
3. `resolution = 0` erhält jede Referenzgröße, gerundet auf das 32px-Raster. `1024` bedeutet ca. 1024² Gesamtpixel je Bild bei erhaltenem Seitenverhältnis, nicht 1024 Pixel Breite.
4. **FREIE GRÖSSE aus**: das vom Textencoder ausgegebene Latent übernimmt das Format von Bild 1. Das ist der offizielle, positionsstabile Standard.
5. **FREIE GRÖSSE an**: nutzt das separate Empty Latent mit Pixaroma Resolution. Ein stark abweichendes Format kann Motiv und Position verschieben. Der nicht gewählte Zweig ist lazy.
6. Vergleich von Bild 1 und Ergebnis im Pixaroma Compare; PNGs unter `output/Qwen_Image_2_1/Edit_*.png`.

**Ein Bild:** zweiten Loader per Strg+M stummschalten und die `<image2>`-Anweisung aus dem Prompt entfernen. Mute, nicht Bypass: ein Loader hat keinen durchreichbaren Bildeingang. Weitere Bilder lassen sich an den Autogrow-Eingängen ergänzen; Core unterstützt bis zu 16. Das ist keine Zusage, dass 16 große Referenzen gleichzeitig in den lokalen Speicher passen.

`QwenImage21Cache` bleibt auf **auto/default**, also ohne Cache-Quantisierung. `cpu` kann VRAM sparen, `off` berechnet Referenzen pro Schritt erneut, `int8`/`int4` verändern die Rechengenauigkeit. Alle sind bewusste Expertenoptionen, keine stillen Optimierungen.

Die Pixaroma-Loader liefern RGB plus separate MASK. Der Maskenausgang ist hier absichtlich nicht verbunden: kein Masken-Inpainting und kein vollständiger Eingabe-Alpha-Roundtrip. Für diesen Modellpfad wird der alte adaptive Qwen-1328-Loader nicht vorgeschaltet; er würde die neue offizielle Referenzskalierung verdoppeln.

## Verifikation und Grenzen

Maschinenlesbarer Nachweis: [`qwen-image21-v121-validation.json`](../performance/rdna4/qwen-image21-v121-validation.json). Getestet auf Windows 11, ComfyUI **0.37.0**, Frontend **1.53.6**, PyTorch **2.13.0+rocm10.1**, R9700 32 GB; bestehendes MultiGPU-Startprofil und VRAM-Guard unverändert.

Die beiden ausgelieferten Standardgraphen wurden im echten Frontend geladen und über `app.graphToPrompt()` serialisiert, nicht durch handgeschriebene Ersatzprompts getestet. Der Serializer prüft die stabile aktive Graphidentität: Frontend 1.53.6 kann während des Starts sonst unbemerkt den Default-Graphen statt der angeforderten Datei serialisieren.

- T2I: 25 Schritte, 1024×1024, PNG, 54,09 Sekunden inklusive kaltem Laden.
- Zwei-Bild-Edit: 25 Schritte, 896×1152, PNG, 85,58 Sekunden auf derselben Instanz.
- Transparenz: 25 Schritte, 512×512, 9,12 Sekunden; echtes RGBA-PNG mit Alpha 0–255, 79,10 % der Pixel unter Alpha 128. Auf hellem Hintergrund kontrolliert; leichte Randsäume bleiben möglich.
- Ein-Bild-Edit: zweiter Loader stumm, Prompt angepasst, Referenzbudget 512 und freie Größe 512×512; 25 Schritte, 20,91 Sekunden. Rote Jacke sichtbar übernommen, erwartete Formatänderung statt identischer Geometrie.
- Native 2K-Ausgabe: 2048×2048, 25 Schritte, 141,30 Sekunden, vollständig gespeichert und visuell geprüft.
- Beide Graphen zusätzlich im Browser auf fehlende Nodes, Ladefehler und tatsächliche Node-Überlappungen geprüft: keine nach abgeschlossener Frontend-Initialisierung.
- Sichtprüfung: T2I folgt dem Schwarzweiß-/Lime-Fashion-Prompt; Edit übernimmt das helle Jeanshemd bei gut erhaltenem Gesicht, Pose und Hintergrund. Das ist eine Beispielabnahme, keine Garantie perfekter Identitätserhaltung bei beliebigen Eingaben.

Exakte Workflow-, API- und Ausgabehashes sind im Nachweis aufgeführt. Alle fünf PNGs enthalten den tatsächlich ausgeführten Prompt und den passenden Workflow als geprüfte Metadaten. Nicht geprüft: beliebige 16-Bild-Kombinationen, andere GPUs/Geräte-Splits, andere Modellquantisierungen, Cache-Quantisierung und Masken-Inpainting. Laufzeiten sind Einzelmessungen, kein Benchmark-Versprechen.

## Reproduktion und Quellen

Abschlusssuite im ComfyUI-venv mit installiertem YuE2-Trainer: **358 Tests bestanden**, **332 Subtests**, **1 bestehender Skip** (fehlende optionale Live-Avatar-Quelldatei). Eine bestehende Pillow-Palettentransparenz-Warnung. Der Sammlungsvalidator prüft **248 Dateien, 301 Graphen, 11.227 Nodes, 5.119 Notes, 7.762 Links und 229 Timer**, ohne Fehler gegen v1.2.0. Die Suite lädt keine Qwen-Gewichte; die fünf GPU-Läufe sind separat nachgewiesen.

```powershell
python tools/build_qwen_image21_workflows.py
$env:YUE2_TRAINER_ROOT = 'L:\ComfyUI\ComfyUI\custom_nodes\ComfyUI-YuE2-Trainer'
L:\ComfyUI\.venv\Scripts\python.exe -m pytest -q -rs
python tools/validate_workflows.py --against-head --baseline-ref v1.2.0
# Echte Frontend-Serialisierung, ohne GPU-Ausführung:
L:\ComfyUI\tmp\minimax-test-venv\Scripts\python.exe performance/rdna4/bench/ui_to_api.py `
  "workflows/Text to Image/Qwen_Image_2_1_BF16-Text-to-Image.json" `
  "tmp/qwen-t2i-api.json" --url http://127.0.0.1:8188
```

Die Quelldateien bleiben SHA-256-gepinnt unter `tools/workflow_templates/v121/` als **internes Reproduktionsarchiv**, nicht als zusätzliche auswählbare Bundle-Workflows. Erst nach erfolgreicher Live-Prüfung werden die beiden ursprünglichen `image_qwen_image_2_1_*.json` aus dem lokalen ComfyUI-Workflow-Hauptordner entfernt. Alle bisherigen 246 Bundle-Workflows bleiben unverändert.
