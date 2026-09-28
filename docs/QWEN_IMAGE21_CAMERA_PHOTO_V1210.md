# Qwen Image 2.1 · Kamerafotos ohne Absturz · v1.2.10

Betrifft `workflows/Image Editing/Qwen_Image_2_1_BF16-Multi-Image-Edit.json` und
`workflows/Image Editing/Qwen_Image_2_1_BF16-Background-Remover.json`.

## Fehler

Mit einem Kamerafoto (Canon-JPG 8192×5464, nach EXIF-Drehung 5464×8192 = 45 MP) brach der Edit im
`TextEncodeQwenImage21` ab:

```text
torch.AcceleratorError: CUDA error: unspecified launch failure (hipErrorLaunchFailure)
  comfy/ldm/wan/vae2_2.py encode -> RMS_norm -> torch.linalg.vector_norm
```

Danach starb zusätzlich der Prompt-Worker-Thread von ComfyUI (`soft_empty_cache` -> `torch.cuda.synchronize`), der
Server nahm keine weiteren Aufträge mehr an.

Ursache: Beide Workflows luden Bilder mit Pixaroma-Resize **off** und `resolution = 0` am Textencoder. `0` heißt
„jede Referenz in Originalgröße“, also ging das 45-MP-Foto ungekürzt in den Qwen-2.1-VAE (und den Vision-Tower) und
wäre auch das Ausgabeformat gewesen. Mit den 896×1152-Beispielbildern von v1.2.1/v1.2.4 fiel das nicht auf. Die
offizielle Comfy-Org-Vorlage nutzt `resolution = 1024`.

## Lösung

Die Pixaroma-Loader (Bild 1 und 2 im Edit, das Bild im Background Remover) verkleinern jetzt nur noch:

| Einstellung | Wert | Wirkung |
|---|---|---|
| Modus | `max_mp` 4.0 | höchstens 4 MP = 2048², die native 2K-Obergrenze von Qwen Image 2.1 |
| Hochskalieren | aus | kleinere Bilder gibt der Loader unverändert weiter (z. B. die 896×1152-Beispielbilder) |
| Snap | 32 (abrunden) | Raster des Textencoders: `resolution = 0` skaliert danach nicht noch einmal |

Beispiel: 5464×8192 → **1664×2496**. `resolution = 0` bleibt, damit kleine Bilder ihr Format behalten.

**Nicht auf off zurückstellen.** Wer schneller arbeiten will, setzt `resolution` am Textencoder auf `1024`
(ca. 1 MP je Referenz und Ausgabe).

## Nachweis

Bericht: [`qwen-image21-camera-photo-v1210-validation.json`](../performance/rdna4/qwen-image21-camera-photo-v1210-validation.json).
Die ausgelieferten Dateien wurden im echten Frontend serialisiert (headless Edge, `app.graphToPrompt`) und auf einem
frischen Testserver mit dem MultiGPU-Profil (VRAM-Guard, R9700) nacheinander ausgeführt, je 25 Schritte:

| Fall | Eingabe | Ausgabe | Zeit |
|---|---|---|---:|
| Edit, Standard | offizielle Beispielbilder 896×1152 | 896×1152 | 89 s |
| Background Remover, Standard | `angry_broccoli.png` 896×1152 | 896×1152 RGBA + Maske | 46 s |
| Edit, Kamerafoto | privates 45-MP-JPG, Anzug-Anweisung, Bild 2 stumm | 1664×2496 | 417 s (Sampling 272 s) |
| Background Remover, Kamerafoto | dasselbe Foto | 1664×2496 RGBA + Maske | 425 s (Sampling 278 s) |

Vergleich auf demselben Server, gleicher Seed: dasselbe Foto mit `resolution = 1024` dauerte 47 s (832×1248).
Das Gesicht wirkt dort weicher und etwas breiter; bei 2K bleiben Gesichtszüge und Bart näher am Original. Das Foto
selbst liegt nicht im Repository, der Bericht enthält nur Größen, Zeiten und Hashes der Ausgaben.

Tests: `tests/test_qwen_image21_camera_photo_v1210.py` rechnet mit Pixaromas eigenem Resize-Code nach
(45 MP → 1664×2496, 896×1152 / 1024² / 2048² unverändert) und prüft den Bericht gegen die ausgelieferten Dateien.
`tools/validate_workflows.py --against-head` vergleicht beide Graphen mit ihren deterministischen Buildern.

## Hinweis für offene Tabs

ComfyUI stellt offene Workflow-Tabs aus dem Browser-Speicher wieder her. Ein vor dem Update geöffneter Tab hat noch
Resize **off**: den Workflow einmal schließen und aus der Workflow-Bibliothek neu öffnen, oder im Pixaroma-Loader
**Max MP** = 4, **Upscaling: Off** und **Snap 32** wählen.
