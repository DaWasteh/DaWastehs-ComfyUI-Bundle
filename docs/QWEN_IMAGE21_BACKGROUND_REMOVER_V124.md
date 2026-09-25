# Qwen Image 2.1 · Background Remover · v1.2.4

`workflows/Image Editing/Qwen_Image_2_1_BF16-Background-Remover.json` stellt ein Motiv frei und speichert ein
**PNG mit echtem Alpha-Kanal** plus die **Alpha-Maske** als Graustufen-PNG. Grundlage ist Comfy-Orgs offizielle
Vorlage `image_qwen_image_2_1_background_removal` (ein Subgraph), hier als flacher RODENT-Graph mit dem lokalen
Modellprofil aus v1.2.1: BF16-DiT, Qwen3-VL 8B INT8 ConvRot und der neue 2.1-VAE, der vier Kanäle (RGBA) dekodiert.
Es gibt kein zusätzliches Segmentierungsmodell und keinen neuen Download.

## Lizenz

Qwen Research License: Forschung und Evaluation, nicht kommerziell ohne separate Lizenz
([Modelllizenz](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)).

## Bedienung

1. **BILD** im Pixaroma Load Image wählen (Resize **off**; Unterordner wie `input/Sheets/` werden angezeigt).
2. **Queue**. Anweisung ist die offizielle `Remove the background, and output a PNG image`.
3. Ergebnisse unter `output/Qwen_Image_2_1/`:
   - `BG_Removed_*.png`: Motiv mit Transparenz
   - `BG_Mask_*.png`: Maske, weiß = Motiv, schwarz = entfernt (für Compositing in anderen Programmen)
4. **VERGLEICH** zeigt Original und Ergebnis übereinander.

`resolution = 0` behält das Bildformat (auf 32 px gerundet). Offizielle Samplerwerte: 25 Schritte, CFG 1, Euler,
Simple, Seed 0 (fest, reproduzierbar).

### Anweisung anpassen

- Bestimmte Dinge behalten: `Remove the background, keep only the person and the guitar, and output a PNG image`
- **Collagen und Charaktersheets:** Die offizielle Anweisung hält dort *alles* für Hintergrund, das Ergebnis ist
  komplett transparent. Getestet und sauber:
  `Remove only the plain background. Keep every person, all clothing, accessories, text and drawn elements unchanged, and output a PNG image`

## Nachweis

[`qwen-image21-background-removal-v124-validation.json`](../performance/rdna4/qwen-image21-background-removal-v124-validation.json),
abgesichert durch `tests/test_qwen_image21_background_remover_v124.py`. Der ausgelieferte Graph wurde über das
echte Frontend serialisiert (`app.graphToPrompt`) und auf der R9700 ausgeführt (ComfyUI 0.37.0, Frontend 1.53.6).

| Bild | Anweisung | Zeit | Ergebnis |
|---|---|---:|---|
| `angry_broccoli.png` (offizielles Beispiel, 896×1152) | offiziell | 85,6 s kalt / 45,2 s warm | sauber freigestellt, 57,8 % transparent |
| `portrait_model_denim.png` (Comfy-Org, 896×1152) | offiziell | 48,2 s | Haar- und Jackenkanten sauber, 1,2 % halbtransparente Randpixel |
| privates Charaktersheet (1440×1088, nicht im Repo) | offiziell | 87,3 s | **leer** (Alpha ≤ 4), siehe oben |
| dasselbe Sheet | Collage-Anweisung | 89,4 s | alle Figuren, Ausschnitte, Texte erhalten, nur der Hintergrund entfernt |

## Grenzen

- Qwen **erzeugt das Motiv neu** (Edit, kein reines Maskieren). Farben und Details bleiben nah am Original, sind aber
  nicht pixelidentisch. Wer exakt die Originalpixel braucht, legt `BG_Mask_*.png` als Maske über das Original.
- Haare, Glas und Rauch können halbtransparente Säume haben.
- Getestet sind die vier Fälle oben; kein Benchmark über viele Bildarten.
