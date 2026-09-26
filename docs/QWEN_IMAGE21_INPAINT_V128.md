# Qwen Image 2.1 · Bild mit Maske bearbeiten · v1.2.8

`workflows/Image Inpainting/Qwen_Image_2_1_BF16-Mask-Inpaint.json`: Bild laden, Maske malen, auf Englisch
beschreiben, was im markierten Bereich entstehen soll, fertig. Alles außerhalb der Maske bleibt **pixelgenau das
Original**, auch bei großen Fotos. Modelle wie bei den übrigen Qwen-Image-2.1-Workflows (v1.2.1): BF16-DiT,
Qwen3-VL 8B INT8 ConvRot, 2.1-VAE. Es gibt keinen neuen Download.

## Lizenz

Qwen Research License: Forschung und Evaluation, nicht kommerziell ohne separate Lizenz
([Modelllizenz](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)).

## Bedienung

1. **1 · BILD LADEN**: Bild hochladen oder auswählen.
2. **2 · MASKE MALEN** (Pixaroma Inpaint Crop): *Editor öffnen*, den Bereich übermalen, speichern. Alternativ am Bild
   Rechtsklick → *Open in MaskEditor*. Eine im Crop-Editor gemalte Maske hat Vorrang.
3. **3 · ÄNDERUNG**: z. B. `Change the green sweater into a red leather jacket with a silver zipper.`,
   `A small orange traffic cone standing on the street.` oder `Remove the car. Show the empty street …`
4. **Queue**. Ergebnis `output/Qwen_Image_2_1/Inpaint_*.png` (mit Workflow), VERGLEICH zeigt vorher/nachher,
   KONTROLLE den Ausschnitt, den Qwen bearbeitet hat.

**Etwas entfernen:** großzügig malen, das ganze Objekt samt Schatten, Rädern, Griffen. Was nicht übermalt ist,
bleibt stehen (siehe Nachweis: ein knapp gemaltes Auto hinterlässt Stoßfänger und Radunterkanten).

## Aufbau

Inpaint Crop schneidet den Bereich um die Maske plus **64 px Umgebung** aus und bringt ihn auf **1024 px** an der
langen Kante (32-px-Raster, passend zu `TextEncodeQwenImage21` mit `resolution = 0`). Der Ausschnitt ist Qwens
Referenzbild **und** das Start-Latent; `SetLatentNoiseMask` lässt nur die maskierten Latents neu rechnen,
`Differential Diffusion` sorgt für weiche Maskenkanten. Nach dem Decode (RGBA → RGB) setzt Inpaint Stitch **nur den
Maskenbereich** mit 16 px weicher Kante ins Original zurück. Samplerwerte wie offiziell: 25 Schritte, CFG 1, Euler,
Simple, Seed 0 (für Varianten auf *randomize*).

**Masken-Wächter** (`DaWRequireMask`, Paket `ComfyUI-DaWasteh-VisionTools`): Ohne Maske ist die Noise-Maske leer,
Qwen dürfte nichts ändern, und das Bild käme stillschweigend unverändert zurück. Der Wächter bricht stattdessen mit
einem deutschen Hinweis ab. Weil auch der Ausschnitt durch ihn läuft, starten Textencoder und VAE erst nach der
Prüfung: Abbruch nach **1,1 s** statt 46 s.

## Nachweis

[`vision-workflows-v128-validation.json`](../performance/rdna4/vision-workflows-v128-validation.json), abgesichert
durch `tests/test_vision_workflows_v128.py`. Serialisiert über das echte Frontend (`app.graphToPrompt`), ausgeführt
auf der R9700 (ComfyUI 0.37.0, Frontend 1.53.6). Masken wie ein Nutzer grob gemalt, als Alpha-PNG wie der MaskEditor
sie speichert. „Außen“ = Pixel mehr als 48 px von der Maske entfernt.

| Fall | Bild | Zeit | außen geändert | Ergebnis |
|---|---|---:|---:|---|
| Pullover → rote Lederjacke (49 % Maske) | 896×1152 | 61,5 s kalt | 0 Pixel | Leder, Reißverschluss, Licht passend; Gesicht und Hintergrund original |
| Pflanze in leeren Hintergrund | 896×1152 | 23,2 s | 0 | Palme im weißen Topf mit Bodenschatten |
| kleiner Verkehrskegel (1,4 % Maske) | 2048×2048 | 41,4 s | 0 | scharf, passende Beleuchtung |
| Auto entfernen, knappe Maske | 2048×2048 | 21,3 s | 0 | **Reste**: Stoßfänger und Räder außerhalb der Maske bleiben stehen |
| Auto entfernen, großzügige Maske | 2048×2048 | 21,2 s | 0 | sauber: Hausfront, Gehweg, Straße ergänzt |
| gleiche Pullover-Maske über den Pixaroma-Editor | 896×1152 | 36,3 s | 0 | identisch zum MaskEditor-Pfad |
| keine Maske | 896×1152 | 1,1 s | – | Abbruch mit Hinweis (gewollt) |

Speicher: VRAM-Spitze 24,8 GiB (R9700), System-Commit-Spitze 76 GB kalt / 60–63 GB warm von 97 GB.

**Verworfene Varianten** (gleiche Bilder, gleicher Seed):

- Qwens natives Edit-Latent statt Noise-Maske (dann nur Stitch): an der Maskenkante sichtbare hellere Naht, weil
  Qwen den ganzen Ausschnitt neu zeichnet. Die Noise-Maske fügt sich nahtlos ein.
- 160 px Umgebung: gleich sauber, erfindet aber eher neue Objekte (ein zusätzlicher Busch).
- 1536 px Ausschnitt: kein sichtbarer Gewinn, 62 s statt 21 s. Sinnvoll erst bei großen Masken auf sehr großen Fotos.

## Grenzen

- Qwen erzeugt den Maskenbereich neu; Material, Licht und Perspektive passen meist, exakte Details (Logos, Schrift)
  sind nicht garantiert.
- PNGs mit Transparenz: Der Alpha-Kanal wird von *Load Image* als Maske gelesen.
- Getestet sind die sieben Fälle oben; kein Benchmark über viele Bildarten.
