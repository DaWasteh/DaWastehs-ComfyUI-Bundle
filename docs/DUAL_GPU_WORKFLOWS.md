# Dual-GPU-Workflows · R9700 + RX 9070 XT · Port 8188

Diese Sammlung nutzt **einen** ComfyUI-Prozess, der beide Windows-ROCm/HIP-GPUs sieht. Sie verteilt Modellobjekte mit den offiziellen ComfyUI-Core-Nodes, statt zwei Server über HTTP miteinander zu verbinden.

## Gerätezuordnung

| ComfyUI/HIP-Gerät | Physische GPU | Aufgabe |
|---|---|---|
| `gpu:0` | AMD Radeon AI PRO R9700 · 32 GB | Standard: Diffusionsmodell/UNET und Sampling |
| `gpu:1` | AMD Radeon RX 9070 XT · 16 GB | Standard: CLIP/Textencoder sowie Bild-, Video- und Audio-VAE |

Diese Indizes sind **HIP-/PyTorch-Indizes**. Sie sind nicht mit der Vulkan-Reihenfolge anderer Programme gleichzusetzen.

Die Aufteilung erzeugt keinen gemeinsamen 48-GB-VRAM-Pool und führt die Graphschritte nicht automatisch parallel aus. Ihr Hauptnutzen ist, das große Diffusionsmodell auf der R9700 resident zu halten, während die RX 9070 XT Encoding und Decoding übernimmt. Komponenten, die nicht gemeinsam in 16 GB passen, werden weiterhin über ComfyUI/RAM ausgelagert.

## Start

Die versionierten Starter liegen im Repository unter:

- `tools/start-MultiGPU.ps1`
- `tools/start-MultiGPU.bat`

Sie funktionieren wegen der bewusst festen lokalen Pfade direkt aus dem Repository. Für die gewohnte Ablage im ComfyUI-Stamm werden sie einmal kopiert:

```powershell
Copy-Item .\tools\start-MultiGPU.ps1 L:\ComfyUI\start-MultiGPU.ps1 -Force
Copy-Item .\tools\start-MultiGPU.bat L:\ComfyUI\start-MultiGPU.bat -Force
```

Danach kann `L:\ComfyUI\start-MultiGPU.bat` gestartet werden. Der Starter verwendet:

- Port `8188`
- `HIP_VISIBLE_DEVICES=0,1`
- `CUDA_VISIBLE_DEVICES=0,1` als PyTorch-ROCm-Kompatibilitätsvariable
- `--default-device 0`
- eine eigene Datenbank `user/comfyui-multigpu.db`
- das konservative R9700-Profil mit `--disable-dynamic-vram`, `--disable-async-offload`, `--disable-pinned-memory` und `--cache-classic`

Vor dem Start prüft das Skript, dass Port 8188 frei ist und PyTorch exakt diese Reihenfolge meldet:

```text
gpu:0 = AMD Radeon AI PRO R9700
gpu:1 = AMD Radeon RX 9070 XT
```

Während eines schweren Dual-GPU-Jobs sollte Port 8189 keinen weiteren GPU-intensiven Job ausführen, weil dessen Prozess sonst mit dem 8188-Prozess um die RX 9070 XT konkurriert.

## Zentraler GPU-Control-Node · v0.8.8

Jeder der 28 Workflows enthält genau einen sichtbaren Node:

```text
DaW Multi-GPU Device Control
```

Seine drei Dropdowns steuern zentral alle verbundenen offiziellen Selector-Nodes:

| Dropdown | Standard | Gesteuerte Komponenten |
|---|---|---|
| `model_device` | `gpu:0` | alle `Select Model Device`-Nodes |
| `clip_device` | `gpu:1` | alle `Select CLIP Device`-Nodes |
| `vae_device` | `gpu:1` | alle Bild-, Video- und Audio-`Select VAE Device`-Nodes |

Die Werte `default`, `gpu:0` und `gpu:1` können vor jedem Queue-Lauf geändert werden. MODEL und CLIP bieten zusätzlich `cpu` für Diagnosezwecke; VAE folgt bewusst der offiziellen ComfyUI-Auswahl ohne CPU. Auch Selector-Nodes innerhalb von Subgraphs erhalten die Root-Dropdowns über neue COMBO-Subgraph-Eingänge. Beim H3-Complete-Song-Director werden die drei Werte in jeden intern erzeugten Segment-Graphen übernommen.

Der benötigte Custom Node liegt unter:

```text
custom_nodes/ComfyUI-DaWasteh-MultiGPU-Control/
```

Für eine getrennte Live-ComfyUI-Installation muss dieser Ordner nach `L:\ComfyUI\ComfyUI\custom_nodes\` kopiert und ComfyUI neu gestartet werden. Die eigentliche Modellplatzierung bleibt in ComfyUIs offiziellen `Select * Device`-Nodes; der DaWasteh-Node liefert ausschließlich die zentralen Dropdown-Werte.

## Workflow-Ordner

Alle Varianten liegen unter:

```text
workflows/Dual GPU - R9700 + RX 9070 XT/
```

Enthalten sind je ein kuratierter Workflow für:

1. SD 1.5
2. SD 2.1
3. SDXL
4. Anima
5. Boogu
6. FLUX.1
7. FLUX.2
8. FLUX.2 Klein
9. Ideogram 4
10. Krea 2
11. LongCat Image
12. Z-Image
13. Qwen Image Edit
14. SCAIL 2
15. Bernini-R
16. WAN 2.2
17. LTX 2.3
18. LTX 2.5 Text-to-Video · INT8 ConvRot
19. LTX 2.5 Image-to-Video · INT8 ConvRot
20. LTX 2.5 First/Last-Frame-to-Video · INT8 ConvRot
21. Wan Animate 2 Motion Transfer · INT8 ConvRot
22. Kandinsky 5
23. ACE-Step 1.5
24. Stable Audio 3
25. MiniMax Music 3 · FP32-DiT + BF16-Textencoder
26. MiniMax H3 Complete-Song One-Click
27. MiniMax H3 FL2VA · offene Eingaben
28. MiniMax H3 Ref2VA · offene Referenzen

Normale Graphen enthalten direkt und zentral verbunden:

- `Select Model Device` mit `gpu:0`
- `Select CLIP Device` mit `gpu:1`
- `Select VAE Device` mit `gpu:1`

Wenn ein Modell zwei Diffusionsloader besitzt, etwa WAN 2.2 oder Ideogram 4, erhält jeder Loader einen eigenen `Select Model Device`-Node.

MiniMax Music 3 ist wegen der bewusst verwendeten Vollpräzisionsgewichte die dokumentierte Ausnahme zur Standardbelegung: Der große BF16-Autoregressions-/Text-Stack läuft auf `gpu:0` (R9700, 32 GB), während FP32-Flow-Matching-DiT und DAV-Audiodecoder auf `gpu:1` (RX 9070 XT, 16 GB) liegen. Der zentrale Control-Node startet deshalb in diesem Workflow mit `MODEL=gpu:1`, `CLIP=gpu:0`, `VAE=gpu:1`. Das entspricht der funktionalen Zweiteilung des offiziellen Inferenzpfads und erzeugt weiterhin keinen gemeinsamen VRAM-Pool.

Der v0.9.1-Live-Smoke-Test expandierte den Graph über ComfyUIs echten Browser-Serializer und verwendete eine instrumentale Caption, vier Sekunden Maximaldauer, alle 30 Euler-/Simple-Schritte sowie tiled DAV decode. ComfyUI 0.33.0 meldete nach 38,89 Sekunden `execution_success` und speicherte ein endliches, nichtleeres 44,1-kHz-Stereo-FLAC mit 7,988 Sekunden Laufzeit. Das Serverlog bestätigte 17.605,78 MB vollständig geladenen Textstack auf `cuda:0`, den Music-3-MODEL-Deepclone nach `cuda:1` und den vollständig geladenen DAV auf `cuda:1`.

## LTX-2.5 und Wan Animate 2 · v0.9.0

Die vier v0.9.0-Workflows werden deterministisch aus den mit ComfyUI `0.32.0` und `comfyui-workflow-templates-json 0.1.43` ausgelieferten offiziellen Templates erzeugt. Gepinnte Kopien liegen unter `tools/workflow_templates/`; dadurch hängt eine Regeneration nicht von einem später veränderten installierten Python-Paket ab. Paketversion, Upstream und SHA-256-Werte aller vier Dateien sind in [`tools/workflow_templates/README.md`](../tools/workflow_templates/README.md) dokumentiert.

LTX-2.5 verwendet den offiziellen distilled INT8-ConvRot-DiT und INT8-ConvRot-Gemma-4-12B-Textencoder. T2V und I2V verwenden zusätzlich den räumlichen LTX-2.5-Latent-Upscaler; FLF2V interpoliert direkt zwischen erstem und letztem Bild. Wan Animate 2 verwendet den INT8-ConvRot-DiT, FP8-UMT5, CLIP-Vision, WAN-VAE und die LightX2V-I2V-LoRA. Die Modelldateien sind lokal nach Familien unter `models/.../LTX`, `models/.../WAN`, `models/text_encoders/Gemma` und `models/text_encoders/UMT5` abgelegt; die Workflows referenzieren diese Unterordner ausdrücklich.

Für Wan Animate 2 wird `WanAnimate2Cache` gegenüber dem offiziellen Template bewusst auf `cpu`/`int8` gesetzt: Der Core-Node warnt, dass der Cache bei typischer Auflösung/Länge neben dem Modell nicht sicher in VRAM passt. Das große MODEL wird zentral nach `gpu:0` gelegt; CLIP und VAE gehen nach `gpu:1`. CLIP-Vision besitzt keinen offiziellen `SelectCLIPDevice`-kompatiblen CLIP-Ausgang und bleibt deshalb unverändert.

Die vier Graphen wurden vor v0.9.0 über ComfyUIs echten Browser-Serializer in API-Prompts expandiert und mit den realen Gewichten auf Windows-ROCm ausgeführt. Die kurzen Abnahmeläufe waren LTX-2.5 T2V/I2V/FLF2V mit jeweils 2 Sekunden bei 320×320 sowie Wan Animate 2 mit 9 Frames bei 256×256; alle vier endeten mit `execution_success` und schrieben nichtleere MP4-Ausgaben. Diese Smoke-Profile bestätigen Loader, Selector-Wiring, Sampling und Decode, sind aber keine Qualitäts- oder Langzeitmessung der ausgelieferten höheren Standardauflösungen.

## Offene MiniMax-H3-Workflows · v0.8.7

Neben dem spezialisierten Musik-Director enthält der Dual-GPU-Ordner jetzt zwei direkt ausführbare H3-Arbeitsgraphen:

```text
MiniMax-H3-FL2VA-DualGPU-All-Supported-Inputs.json
MiniMax-H3-Ref2VA-DualGPU-All-Reference-Inputs.json
```

Die FL2VA-Variante behält Prompt, First Frame, Last Frame, Auflösung und Länge offen. Die Ref2VA-Variante stellt weiterhin alle neun Bildreferenzen, drei Videoreferenzen, drei zugehörige Video-Audios, drei eigenständige Audio-Referenzen, Prompt, Auflösung, Länge und `ref_image_size=match` bereit. Nicht benötigte Referenz-Slots können wie im Quellworkflow unverbunden bleiben.

Beide Graphen verwenden sichtbar und ohne internen Director:

```text
UNETLoader -> SelectModelDevice gpu:0 -> H3 Turbo LoRA -> Sigma Shift -> Spectrum/Sampling
CLIPLoader -> SelectCLIPDevice gpu:1 -> H3 Conditioning
Video VAE  -> SelectVAEDevice gpu:1 -> Conditioning + Decode
Audio VAE  -> SelectVAEDevice gpu:1 -> Ref2VA/Audio Decode
```

Damit eignen sie sich für normale Bild-/Keyframe-, Charakter-, Objekt-, Bewegungs-, Kamera-, Video- und Audio-Referenzaufgaben, ohne dass ein kompletter Song oder die serielle Segmentplanung des Directors erforderlich ist.

## MiniMax H3 Complete-Song

Der sichtbare H3-One-Click-Workflow enthält keine Loader. Der Director erzeugt für jedes Segment intern einen Child-Graph. Deshalb verwendet die Dual-GPU-Variante den neuen Node-Typ:

```text
DaWH3MusicVideoDirectorDualGPU
```

Dieser ergänzt den internen Child-Graph so:

```text
CLIPLoader  -> SelectCLIPDevice  gpu:1
Video VAE   -> SelectVAEDevice   gpu:1
Audio VAE   -> SelectVAEDevice   gpu:1
UNETLoader  -> SelectModelDevice gpu:0 -> H3 Turbo LoRA v4 Step-600 EMA
```

Der H3-Sigma-Shift, Spectrum-Patch, Guider, Euler-Sampler und Beta-Scheduler erhalten anschließend das LoRA-gepatchte Modell vom im zentralen `model_device`-Dropdown gewählten Gerät; Conditioning und `VAEDecode` verwenden die über `clip_device` und `vae_device` gewählten Geräte. Das v0.8.6-Profil nutzt acht Schritte, Video-Sigma 12 und Audio-Sigma 4. FL2VA und Ref2VA wurden damit über Port 8188 jeweils bis zu fünf dekodierten Frames live ausgeführt; Details stehen in [MINIMAX_H3_TURBO_AND_PROMPTS.md](MINIMAX_H3_TURBO_AND_PROMPTS.md).

## Bewusst ausgeschlossen

YuE, HeartMuLa, MOSS-TTS, Qwen-TTS und ähnliche Custom-Nodes geben keine standardisierten ComfyUI-Objekte vom Typ `MODEL`, `CLIP` oder `VAE` aus. Die offiziellen Selector-Nodes können diese Objekte daher nicht zuverlässig umplatzieren. Diese Modellfamilien wurden bewusst nicht mit scheinbar funktionalen, tatsächlich wirkungslosen Device-Nodes versehen.

## Regeneration und Prüfung

Die 28 Dateien sind deterministisch generiert:

```powershell
python tools/generate_dual_gpu_workflows.py
python -m unittest tests.test_dual_gpu_workflows
python tools/validate_workflows.py --against-head
```

Ein vollständiger Live-Test sollte zuerst mit einem kurzen Bild- oder H3-Einzelsegment erfolgen. Die statische Prüfung bestätigt Topologie und Gerätezuordnung, ersetzt aber keinen Windows-ROCm-Lauf mit den realen Modellgewichten.
