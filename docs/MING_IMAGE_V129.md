# Ming Image 0.1 Design · Designs, Freisteller, Bearbeiten, Ebenen zerlegen · v1.2.9

Ming Image 0.1 Design und Ming Image 0.1 Design-Layer (inclusionAI, MIT, je 6B) laufen seit ComfyUI #16482 nativ.
Design ist auf **Grafik mit Text** trainiert (Poster, UI-Screens, Infografiken, Karten, Folien) und setzt Texte in
Anführungszeichen buchstabengetreu; Design-Layer zerlegt ein fertiges, flaches Design in transparente Ebenen.

| Workflow | Ergebnis unter `output/` |
|---|---|
| `Text to Image/Ming_Image_0_1_Design_INT8-Text-to-Image` | `Ming_Image/Design_*.png` (Standard 2048×2048) |
| `Text to Image/Ming_Image_0_1_Design_INT8-Text-to-Transparent-Image` | `Ming_Image/Transparent_*.png` (RGBA, Standard 1024×1024) |
| `Image Editing/Ming_Image_0_1_Design_INT8-Image-Edit` | `Ming_Image/Edit_*.png` (Arbeitsgröße des 1024er-Buckets) |
| `Image Utilities/Ming_Image_0_1_Design_Layer_INT8-Image-to-Layers` | `Ming_Image/Layers/Layer_*.png` (N RGBA-Ebenen, 1 = vorne) |

## Modelle (gepinnt in `tools/workflow_templates/v129/models.json`)

| Datei (Comfy-Org/Ming-Image) | Größe | Zielordner |
|---|---:|---|
| `ming_image_0.1_design_int8_convrot.safetensors` | 5,75 GiB | `models/diffusion_models/Ming/` |
| `ming_image_0.1_design_layer_int8_convrot.safetensors` | 5,75 GiB | `models/diffusion_models/Ming/` |
| `ming_image_0.1_ling_mini_2.0_int8_convrot.safetensors` (Text-Encoder Design) | 18,17 GiB | `models/text_encoders/Ming/` |
| `ming_image_0.1_ling_mini_2.0_layer_int8_convrot.safetensors` (Text-Encoder Layer) | 18,17 GiB | `models/text_encoders/Ming/` |
| `ming_image_vae_bf16.safetensors` (RGBA-VAE, alle vier) | 0,24 GiB | `models/vae/Ming/` |
| `birefnet.safetensors` (Comfy-Org/BiRefNet, schon seit v1.1.8) | 0,41 GiB | `models/background_removal/` |

Design und Design-Layer haben **je einen eigenen Text-Encoder**. INT8 ConvRot wie im offiziellen Template; BF16 (12,3 GB
DiT) brachte im Test keine sichtbare Verbesserung und rechnete bei 1024² etwa halb so schnell. Der Prompt-Writer nutzt das
Qwen3.8-27B-GGUF, das der Musikvideo-Prompt-Writer schon verwendet; das offizielle Template lädt dafür einen zweiten,
17,3 GB großen Text-Encoder (`qwen3.8_27b_w4a8`), der hier nicht gebraucht wird.

## Was die Workflows anders machen als das offizielle Template (gemessen, R9700)

| Entscheidung | Grund |
|---|---|
| **ModelSamplingAuraFlow, Shift 3,86** | Der Referenz-Code rechnet ab 1024 px mit dynamischem Shift mu = 1,35 (linear e^1,35 = 3,86). Das Template nutzt `ModelSamplingFlux(1,15/0,5)` mit der Bildgröße: bei 2048² mu ≈ 3,2 (linear ≈ 25). Gleicher Seed: Das Template glättete die verlangte Papierkörnung und die vergilbten Ränder weg und schrieb „VINTAGE FINSS“ auf ein Schild, 3,86 setzte beides korrekt um. `ModelSamplingSD3` (Zeitschritt ×1000) liefert bei Ming nur Rauschen. |
| **RAM-schonende Loader** (`DaWVUReadOnly*`, v1.2.6) | Die Core-Loader rechnen die 19,5-GB-Text-Encoder-Datei (copy-on-write) zusätzlich zur VRAM-Kopie auf den Commit: 2048² erreichte **96,6 von 97,4 GB** (0,01 GB RAM frei). Schreibgeschützt gemappt: **77,3 GB**, gleiche Gewichte (alle 1707 + 882 + 194 Tensoren bitgleich). |
| PyTorch-Attention statt „comfy kitchen attention“ | INT8-Attention war nur ~4 % schneller (44 statt 46 s bei 2048²), veränderte das Bild aber deutlich (mittlere Abweichung 14/255). |
| Prompt-Writer über llama.cpp | Offizieller Rewriter-Prompt, Qwen3.8 27B IQ4_XS auf der RX 9070 XT (nur während des Schreibens), das echte Format wird mitgegeben (ohne wählte er für ein quadratisches Poster „3:4“). |
| Edit mit **einem** Bild | Offiziell nimmt Ming ein Eingabebild. Mit zwei Bildern (Core-Knoten erlaubt bis zu 8) kam bei Fotos in 3 von 3 Versuchen nur Bild 2 unverändert heraus; beim Design landete der Sticker über dem Datum. |
| Freisteller: Präfix + BiRefNet-Fallback | siehe unten |

## Text → Bild

Der Writer macht aus einer kurzen Beschreibung (Deutsch geht, sichtbare Texte in Anführungszeichen) das Figma-artige
JSON aus Ebenen, Koordinaten, Farben und exakten Texten, mit dem Ming trainiert wurde. Mit `enhance` aus geht der Text
direkt an Ming (auch ein eigenes JSON). Offizielle Werte: 12 Schritte, CFG 1, Euler, Simple.

Zeiten (R9700, warm): 2048² 38–48 s (langes JSON mit ~3000 Token: 48 s), 1024² ≈ 10 s. Writer: kurze Anfrage ≈ 30 s
inkl. Serverstart, eine sehr lange (4.259 Zeichen) 2 min. Die RX 9070 XT belegt dabei ≈ 15 GB; danach wird alles frei.

## Freisteller (RGBA)

Die Ming-VAE hat vier Kanäle und kann echte Transparenz schreiben. Das Modell nutzt sie aber **nur manchmal**: Von 18
Läufen (1024², drei offizielle Präfixe, Auto/Katze/Fuchs-Sticker, INT8 und BF16) hatten 6 einen echten Alpha-Kanal, die
übrigen malten Weiß oder ein **Schein-Schachbrett**. Am häufigsten klappte der Präfix
`transparent canvas, not white, not checkerboard` (3 von 6); der chinesische Präfix erzeugte einmal ein 2×2-Raster.
Deshalb:

1. Der Workflow setzt diesen Präfix vor den (umgeschriebenen) Prompt.
2. **DaWMingAlphaFallback** behält Mings Alpha, wenn mindestens 2 % des Bildes transparent sind (dann mit weichen,
   halbtransparenten Schatten), und nimmt sonst die **BiRefNet**-Maske. BiRefNet lädt nur in diesem Fall (lazy).
3. *Alpha-Quelle* zeigt `ming` oder `mask`.

Sticker mit „weißem Rand“ bleiben weiß umrandet (der Rand gehört zum Motiv).

## Bearbeiten

Das Bild wird auf den offiziellen 1024er-Bucket gebracht (Tabelle aus dem Referenz-Code, nächstes Seitenverhältnis,
ohne Beschnitt; 1024² bleibt 1024², 896×1152 bleibt 896×1152, 1920×1080 → 1280×720). Gezielte Änderungen an Designs
gelingen sehr genau: „7TH OCTOBER“ → „12TH JULY“ ließ Schleife, Glitzerrand und alle anderen Texte stehen. Fotos gehen
auch (Pullover → rote Lederjacke), Mings Schwerpunkt sind aber Designs. ≈ 22 s warm.

## Ebenen zerlegen (Design-Layer)

Das Layer-Modell erzeugt **Komposit + N Ebenen als Frames eines Latents** (`EmptyQwenImageLayeredLatentImage`, gleiches
Layout). Jedes Frame wird einzeln dekodiert (`LatentCutToBatch` t/1 vor `VAEDecode`, wie der Referenz-Code), das erste
(Komposit) wird verworfen. Offiziell: 12 Schritte, **CFG 2**, Negativ = genullte Text-Embeddings (`ConditioningZeroOut`,
die Referenz-Frames bleiben erhalten), 1024er-Bucket.

Der Writer bekommt den offiziellen „guided prompt“ mit dem groben Plan **und dem Bild** (Vision-Projektor des GGUF) und
schreibt die Spezifikation: Texte wörtlich nach vorn, Karte/Banner dahinter als eigene Ebene, Hauptmotiv als eigene Ebene,
Hintergrund zuletzt. Die Ebenenzahl für das Latent kommt aus dieser Antwort. Eine unvollständige Antwort (Ebenenliste
passt nicht zur Zahl) wird einmal mit anderem Seed wiederholt, dann gilt der grobe Plan.

Offizielles Kartenbeispiel mit der offiziellen 6-Ebenen-Spezifikation: gleiche Aufteilung wie inclusionAIs Referenz
(Texte · Illustration oben rechts · Illustrationen in den Ecken · Schleife · Karte mit Glitzerrand · roter Hintergrund),
verdeckte Stellen ergänzt, wieder übereinander gelegt **PSNR 30,8 dB** gegen das Original. Mit Seed 1 wanderte ein Teil
des Glitzerrands in den Hintergrund (24,4 dB): Fehlt etwas, anderen Seed probieren. Der 512er-Bucket (≈ 50 s statt
≈ 4 min) verschmolz Karte und Hintergrund zu einer Ebene, mit beiden Shifts (3,86 und dem offiziellen 1,88 für 512).

## Speicher

Mit den RAM-schonenden Loadern: Commit-Spitze 64–86 GB von 97,4 GB (2048² mit langem JSON am höchsten), VRAM der R9700
bis 31,5 GB (Text-Encoder 18,3 GB + DiT 5,9 GB, ComfyUI lagert vor dem VAE-Decode aus). Während der Writer läuft, liegt
das GGUF zusätzlich im RAM der Maschine. Der *freie* RAM fiel in den Messungen bis auf 0 GB (gemappte Modelldateien,
Windows lagert sie bei Bedarf aus), der Commit blieb bei höchstens 86 von 97,4 GB, kein Lauf scheiterte.

## Nachweis

Alle vier Workflows über das echte Frontend (headless Edge, `app.graphToPrompt`) auf der R9700 ausgeführt, dazu
Varianten; Einzelwerte in `performance/rdna4/ming-image-v129-validation.json`, gesichert durch
`tests/test_ming_image_workflows_v129.py` und `tests/test_ming_image_nodes_v129.py`.

| Fall | Zeit (kalt/mit Writer) | Commit-Spitze | Ergebnis |
|---|---:|---:|---|
| Text → Bild, Standard (Writer an, 2048²) | 114,4 s | 80,7 GB | 2048² RGB, Prompt = JSON (4090 Zeichen) |
| Text → Bild, Writer aus, 1024² | 36,1 s | 69,9 GB | 1024² RGB, Text direkt |
| Text → Bild ohne GGUF im Startprofil | 76,2 s | 84,3 GB | 2048² RGB, Text direkt (Warnung im Log) |
| Freisteller, Standard (Fuchs-Sticker) | 72,3 s | 84,1 GB | RGBA, 70 % transparent, Alpha-Quelle `ming` |
| Freisteller, Katze | 64,3 s | 85,7 GB | RGBA, 29 % transparent, Alpha-Quelle `mask` |
| Bearbeiten, Karte 1024² (Datum ändern) | 26,1 s | 69,6 GB | 1024×1024 RGB |
| Bearbeiten, Hochformat-Foto 896×1152 | 20,1 s | 71,4 GB | 896×1152 RGB |
| Ebenen, Standard (grober Plan + Writer mit Bild) | 287,0 s | 79,9 GB | 6/6 RGBA-Ebenen, 30,6 dB |
| Ebenen, ohne Plan und Writer, 4 Ebenen | 182,5 s | 75,5 GB | 4/4 RGBA-Ebenen, 30,9 dB |
| Ebenen ohne GGUF (nur grober Plan) | 259,0 s | 77,3 GB | 6/6 RGBA-Ebenen, 27,4 dB |

Alle PNGs enthalten den Workflow. Modelle: alle sechs Dateien per SHA-256 gegen das Manifest geprüft. Zeiten schließen
Modell-Wechsel zwischen den Fällen ein (Design ↔ Layer, jeweils 19,5-GB-Text-Encoder); warm siehe oben.

## Grenzen

- Echte Transparenz nur in einem Teil der Läufe (Fallback siehe oben).
- Mehrere Referenzbilder im Edit funktionieren nicht zuverlässig (daher nur ein Bild).
- Kleine Typografie-Eigenheiten kommen vor (z. B. „12.Juli“ ohne Leerzeichen in allen SEEFEST-Läufen).
- Lizenz: Ming Image 0.1 (Code und Gewichte) steht unter MIT; die Rewriter-Prompts im Paket `prompts/` stammen aus dem
  Ming-Image-Repository (Commit f39a706).
