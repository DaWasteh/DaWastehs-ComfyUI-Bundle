# Stable Audio 3 Medium (FP32) · Text → Musik/Geräusch

**Workflow-Datei:** [`workflows/Music Generation/StableAudio3_Medium_FP32+Qwen3_5_2B-Text-to-Audio.json`](../../../workflows/Music%20Generation/StableAudio3_Medium_FP32%2BQwen3_5_2B-Text-to-Audio.json)  
**Kategorie:** Music Generation · **Eingabe → Ausgabe:** Text → Audio · **Quant:** FP32

Bis v1.3.0 hieß der Workflow `StableAudio3_Medium-Audio-Generation.json`.

Musik, Instrumente, Soundeffekte oder One-Shots; Qwen3.5 2B formuliert die Beschreibung vorher aus.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/stableaudio3-medium-fp32-qwen3-5-2b-text-to-audio>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Text-Encoder / LLM | `qwen3.5_2b_bf16.safetensors` | BF16 | 4,2 GiB |
| Modell | `stable_audio_3_medium.safetensors` | FP32 | 8,6 GiB |
| Text-Encoder / LLM | `t5gemma_b_b_ul2.safetensors` | BF16 | 1,1 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Musik · Orchester

Prompt:

```text
Cinematic orchestral adventure theme with soaring strings, french horns, choir and timpani, heroic and uplifting
```

| Einstellung | Wert |
|---|---|
| duration | 30 s |
| seed | 42 |
| category | Music |
| Dauer (Ausführung) | 1 min 0 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 14,2 GiB / 9,1 GiB |
| VRAM RX 9070 XT (belegt / PyTorch-Spitze) | 8,8 GiB / 7,0 GiB |
| RAM (ComfyUI-Prozess) | 26,8 GiB |

Qwen3.5 2B formuliert die Beschreibung vorher aus (Reprompt, Standard im Workflow).

Ausgabe · Ausgabe: [orchestra.mp3](orchestra.mp3)  

PreviewAny:

```text
30
```

### Geräusch · Regen

Prompt:

```text
Heavy rain on a tin roof with distant rolling thunder and water dripping from a gutter
```

| Einstellung | Wert |
|---|---|
| duration | 15 s |
| seed | 42 |
| category | SFX |
| Dauer (Ausführung) | 23 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 14,0 GiB / 7,6 GiB |
| VRAM RX 9070 XT (belegt / PyTorch-Spitze) | 9,8 GiB / 7,5 GiB |
| RAM (ComfyUI-Prozess) | 8,3 GiB |

Ausgabe · Ausgabe: [rain.mp3](rain.mp3)  

PreviewAny:

```text
15
```
