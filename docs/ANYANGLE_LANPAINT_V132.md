# Qwen Image 2.1 · AnyAngle (Kamerawinkel) und LanPaint (Masken-Inpainting) · v1.3.2

Vier neue Workflows für Qwen Image 2.1 (BF16-DiT, Qwen3-VL 8B INT8 ConvRot, 2.1-VAE wie bisher):

| Workflow | Zweck |
|---|---|
| `Image Editing/Qwen_Image_2_1_BF16+AnyAngle_LoRA+TripoSplat-Image-to-4-Camera-Angles` | ein Bild → vier neue Kameraansichten, ohne Editor |
| `Image Editing/Qwen_Image_2_1_BF16+AnyAngle_LoRA-Image+Guide-to-Camera-Angle` | Original + eigenes grobes Render → diese Ansicht |
| `Image Editing/Qwen_Image_2_1_BF16+AnyAngle_Studio_T8-Image-to-Camera-Angle` | interaktive 3D-Kamera (AnyAngle Studio) |
| `Image Inpainting/Qwen_Image_2_1_BF16+LanPaint-Image+Mask-Inpaint` | Masken-Inpainting mit dem LanPaint-Sampler |

## Lizenz

Qwen Image 2.1: Qwen Research License, Forschung und Evaluation, nicht kommerziell ohne separate Lizenz
([Modelllizenz](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)). AnyAngle-LoRA: Apache-2.0
([lilylilith/QI_2.1_AnyAngle](https://huggingface.co/lilylilith/QI_2.1_AnyAngle)). TripoSplat: MIT
([VAST-AI/TripoSplat](https://huggingface.co/VAST-AI/TripoSplat)). LanPaint: GPL-3.0
([scraed/LanPaint](https://github.com/scraed/LanPaint)). AnyAngle Studio T8: MIT
([T8mars/Comfyui-Qwen-Image-2.1-MultiAngle-T8](https://github.com/T8mars/Comfyui-Qwen-Image-2.1-MultiAngle-T8)).

## Neue Dateien

Der Updater holt die Node-Packs **LanPaint** und **ComfyUI-AnyAngle-Studio-T8** aus GitHub. Modelle
(SHA-256 in [`tools/workflow_templates/v132/models.json`](../tools/workflow_templates/v132/models.json), Links in den
DOWNLOADS-Notizen der Workflows):

| Datei | Ziel unter `ComfyUI/models/` | Größe |
|---|---|---:|
| `QI2.1_AnyAngle.safetensors` | `loras/Qwen/` | 0,11 GiB |
| `triposplat_fp16.safetensors` | `diffusion_models/TripoSplat/` | 0,69 GiB |
| `triposplat_vae_decoder_fp16.safetensors` | `vae/TripoSplat/` | 0,54 GiB |
| `dino_v3_vit_h.safetensors` | `clip_vision/` | 1,57 GiB |
| `flux2-vae.safetensors` | `vae/FLUX2/` (von FLUX.2 schon vorhanden) | 0,31 GiB |
| `birefnet.safetensors` | `background_removal/` (schon vorhanden) | 0,41 GiB |

LanPaint braucht kein Modell. TripoSplat, Render Splat und BiRefNet sind ComfyUI-Core-Nodes (ab 0.38).

## AnyAngle

AnyAngle ist eine LoRA für Qwen Image 2.1, die ein Bild in eine neue Kameraposition überführt. Sie braucht dazu ein
**grobes Render der Zielansicht**; Stil, Material und Details kommen aus dem Original.

### Vier Kamerawinkel aus einem Bild (ohne Editor)

1. **1 · BILD LADEN**: Figur, Produkt oder Person vor ruhigem Hintergrund.
2. **Queue**. Vier Bilder unter `output/AnyAngle/` (`left45`, `left90`, `right45`, `top35`); die KONTROLLE-Knoten
   zeigen die groben Renders.

Ablauf im Graph: BiRefNet-Maske → TripoSplat (20 Schritte, 262 144 Gaussians) → *Render Splat* aus vier Kameras →
je ein Qwen-Durchlauf mit der AnyAngle-LoRA (20 Schritte, CFG 3, Euler, Simple, Stärke 1). Alle Modelle werden einmal
geladen.

**Winkel ändern** an den KAMERA-Knoten: `yaw` dreht um das Motiv (**90 = Originalkamera**, 180 = linkes Profil, 0 =
rechtes Profil, 270 = Rückansicht), `pitch` hebt die Kamera (positiv = von oben), `distance` regelt die Größe im Bild
(2,3; bei 2,0 waren im Test die Füße abgeschnitten).

### Eigenes Render

Original in Knoten 1, grobes Render in Knoten 2. Das Render darf aus Blender, einem Splat, einer Mira-Scene- oder
Pixal3D-Szene stammen; die KONTROLLE-Bilder des Vier-Winkel-Workflows sind genau solche Renders. Das Ergebnis hat das
Format des Originals, Größe und Lage des Motivs folgen dem Render.

### AnyAngle Studio T8

Bild laden, am Studio-Knoten die Werkbank öffnen, *Reconstruct 3D from photo*, Kamera drehen, **Apply to node**, Queue.
Das Studio liefert Guide, Prompt und LoRA-Stärke; ohne angewandte Szene lehnt ComfyUI den Lauf ab. Es kann außerdem
GLB-Modelle laden, eine Figur posieren, Pose/Tiefe/Canny aus dem Foto ziehen und viele Winkel als Batch einstellen.

### Bildreihenfolge (wichtig)

`<image1>` = **Original**, `<image2>` = **grobes Render**, Prompt `Change the camera angle from <image2> to <image1>.`
Die Modellkarte der LoRA beschreibt die Bilder andersherum. Gemessen (Fuchs, Render 45° links, Seed 7):

| `<image1>` | `<image2>` | Ergebnis |
|---|---|---|
| Original | Render | Ansicht folgt dem Render, Stil und Details des Originals |
| Render | Original | wieder die Frontansicht, das Render wird ignoriert |

Der KV-Cache (`QwenImage21Cache`) ändert das Bild nicht.

### Grenzen

- Das Ergebnis ist nur so gut wie das Splat. Unsichtbare Seiten erfindet TripoSplat; bei der Teekanne entstand in der
  Seitenansicht ein Ausguss, den das Render nicht zeigte.
- Bei der stehenden Person rekonstruierte TripoSplat den Körper leicht nach hinten geneigt; Qwen übernahm die Neigung
  und den nach oben gerichteten Blick. Für Personen `pitch` 0 und kleinere `yaw`-Schritte probieren oder das Studio
  nehmen, dort sieht man die Rekonstruktion vor dem Lauf.
- Hochformat-Originale ergeben Hochformat-Bilder; das quadratische Render wird nur als Vorlage gelesen.

## LanPaint

Gleiche Bedienung wie `Qwen_Image_2_1_BF16-Image+Mask-Inpaint` (v1.2.8): Bild laden, Maske malen, Änderung auf
Englisch beschreiben, Queue. Statt KSampler + Noise-Maske rechnen *LanPaint Encode*, *LanPaint Sampler* und *LanPaint
Decode*; Pixaroma Crop/Stitch und der Masken-Wächter bleiben. Standard nach LanPaint-Empfehlung: 20 Schritte, CFG 4
mit Negativprompt, Euler, Simple, 5 Denkschritte (`LanPaint_NumSteps`), `Image First`.

### Vergleich mit dem normalen Qwen-Sampler

Gleiche Bilder, Masken, Prompts und Seed 7, 1024×1024, R9700:

| Maske | Qwen-Sampler (25 Schritte, CFG 1) | LanPaint (CFG 4, 5 Denkschritte) | Beobachtung |
|---|---:|---:|---|
| Pullover → rote Lederjacke (30 % Maske) | 61 s (kalt) | 111 s (kalt) | beide sauber; LanPaint matter, mit Kragen und mehr Lederstruktur |
| dieselbe Maske, LanPaint mit CFG 1 | – | 39 s | dunkleres, braunrotes Leder; schnellste Variante |
| Haare → platinblond | 64 s | 148 s | praktisch gleichwertig |
| Pflanze → Stehlampe | 29 s | 103 s | beide passend beleuchtet, LanPaint mit größerem Schirm |

Außerhalb der Maske (mehr als 48 px entfernt) ändert sich bei LanPaint **kein Pixel**. Fazit: LanPaint funktioniert mit
Qwen Image 2.1 zuverlässig und setzt Übergänge nahtlos, kostet aber das Zwei- bis Vierfache an Zeit. Bei diesen drei
Masken ist kein klarer Qualitätsvorsprung gegenüber dem v1.2.8-Workflow zu sehen, der mit Differential Diffusion
bereits weiche Kanten hat. Der Workflow ist deshalb als Test- und Alternativweg gedacht, etwa für Masken, an denen
der normale Sampler Nähte oder unpassende Inhalte liefert.

Transparenz mitbearbeiten (LanPaint-Beispiel 31) geht in diesem Graph nicht, weil Crop/Stitch mit RGB arbeiten.

## Messwerte

Echte Läufe über das Frontend (headless Edge) auf der R9700, ComfyUI 0.38.0, Testserver wie die Beispielgalerie:

| Lauf | Dauer | VRAM (PyTorch) | System-Commit |
|---|---:|---:|---:|
| Vier Winkel · Fuchs 1024×1024 | 7,9 min | 28,3 GiB | 105 GiB |
| Vier Winkel · Person 832×1248 | 8,6 min | 28,7 GiB | 105 GiB |
| Vier Winkel · Teekanne 1024×1024 | 9,8 min | 28,7 GiB | 110 GiB |
| Eigenes Render · Fuchs | 2,2 min | 26,2 GiB | 96 GiB |
| AnyAngle Studio · Fuchs (Szene im Editor angewandt) | 2,1 min | 28,1 GiB | 97 GiB |
| TripoSplat allein (Maske, Splat, zwei Renders) | 30 s | – | – |

Ein einzelner Qwen-Durchlauf braucht rund 54 s (2,7 s je Schritt). Der Commit von über 100 GiB liegt über dem RAM
(47 GB) und stützt sich auf die Auslagerungsdatei: vor langen Video-Workflows ComfyUI neu starten.

## Korrektur am ComfyUI-Core: Render Splat auf ROCm

*Render Splat* invertiert je Gaussian eine 3×3-Matrix in einem einzigen `torch.linalg.inv`-Aufruf. Auf diesem
ROCm-Stack scheitert der Aufruf oberhalb von 65 535 Matrizen mit `hipErrorInvalidConfiguration` (60 000 gehen, 70 000
nicht); ein TripoSplat hat 262 144 Gaussians. `ComfyUI-DaWasteh-MultiGPU-Control` teilt die Aufrufe beim Start in
Blöcke zu 32 768 (`splat_inverse.py`, gleiche Werte; abschalten mit `DAWASTEH_SPLAT_LINALG_FIX=0`). Ohne den Patch
bricht der Vier-Winkel-Workflow im ersten Render ab. Upstream ist das noch nicht gemeldet.

## Nachweis

[`anyangle-lanpaint-v132-validation.json`](../performance/rdna4/anyangle-lanpaint-v132-validation.json), abgesichert
durch `tests/test_anyangle_lanpaint_v132.py` und `tests/test_splat_inverse_v132.py`. Die Beispiele stehen in der
[Galerie](https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/).
