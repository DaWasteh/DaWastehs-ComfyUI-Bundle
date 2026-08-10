# Dual-GPU-Workflows · R9700 + RX 9070 XT · Port 8188

Diese Sammlung nutzt **einen** ComfyUI-Prozess, der beide Windows-ROCm/HIP-GPUs sieht. Sie verteilt Modellobjekte mit den offiziellen ComfyUI-Core-Nodes, statt zwei Server über HTTP miteinander zu verbinden.

## Gerätezuordnung

| ComfyUI/HIP-Gerät | Physische GPU | Aufgabe |
|---|---|---|
| `gpu:0` | AMD Radeon AI PRO R9700 · 32 GB | Diffusionsmodell/UNET und Sampling |
| `gpu:1` | AMD Radeon RX 9070 XT · 16 GB | CLIP/Textencoder sowie Bild-, Video- und Audio-VAE |

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
18. Kandinsky 5
19. ACE-Step 1.5
20. Stable Audio 3
21. MiniMax H3 Complete-Song One-Click
22. MiniMax H3 FL2VA · offene Eingaben
23. MiniMax H3 Ref2VA · offene Referenzen

Normale Graphen enthalten direkt:

- `Select Model Device` mit `gpu:0`
- `Select CLIP Device` mit `gpu:1`
- `Select VAE Device` mit `gpu:1`

Wenn ein Modell zwei Diffusionsloader besitzt, etwa WAN 2.2 oder Ideogram 4, erhält jeder Loader einen eigenen `Select Model Device`-Node.

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

Der H3-Sigma-Shift, Spectrum-Patch, Guider, Euler-Sampler und Beta-Scheduler erhalten anschließend das LoRA-gepatchte Modell von `gpu:0`; Conditioning und `VAEDecode` verwenden die auf `gpu:1` platzierten Hilfsmodelle. Das v0.8.6-Profil nutzt acht Schritte, Video-Sigma 12 und Audio-Sigma 4. FL2VA und Ref2VA wurden damit über Port 8188 jeweils bis zu fünf dekodierten Frames live ausgeführt; Details stehen in [MINIMAX_H3_TURBO_AND_PROMPTS.md](MINIMAX_H3_TURBO_AND_PROMPTS.md).

## Bewusst ausgeschlossen

YuE, HeartMuLa, MOSS-TTS, Qwen-TTS und ähnliche Custom-Nodes geben keine standardisierten ComfyUI-Objekte vom Typ `MODEL`, `CLIP` oder `VAE` aus. Die offiziellen Selector-Nodes können diese Objekte daher nicht zuverlässig umplatzieren. Diese Modellfamilien wurden bewusst nicht mit scheinbar funktionalen, tatsächlich wirkungslosen Device-Nodes versehen.

## Regeneration und Prüfung

Die 23 Dateien sind deterministisch generiert:

```powershell
python tools/generate_dual_gpu_workflows.py
python -m unittest tests.test_dual_gpu_workflows
python tools/validate_workflows.py --against-head
```

Ein vollständiger Live-Test sollte zuerst mit einem kurzen Bild- oder H3-Einzelsegment erfolgen. Die statische Prüfung bestätigt Topologie und Gerätezuordnung, ersetzt aber keinen Windows-ROCm-Lauf mit den realen Modellgewichten.
