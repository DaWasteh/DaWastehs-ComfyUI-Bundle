# FLUX.2 Klein 4B + Gemma 4 · Audio → Audio-React-Video

**Workflow-Datei:** [`workflows/Audio to Video/FLUX2_Klein_4B_BF16+Gemma4_E4B-Audio-to-AudioReact-Video.json`](../../../workflows/Audio%20to%20Video/FLUX2_Klein_4B_BF16%2BGemma4_E4B-Audio-to-AudioReact-Video.json)  
**Kategorie:** Audio to Video · **Eingabe → Ausgabe:** Audio → Prompt + Video · **Quant:** BF16

Bis v1.3.0 hieß der Workflow `FLUX2_Klein_4B_Gemma4-Audio-Context-to-AudioReact-Video.json`.

Gemma 4 hört das Audio und beschreibt eine passende Szene, Klein 4B malt sie, Pixaroma animiert das Bild im Takt (MP4 mit Originalton).

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/flux2-klein-4b-bf16-gemma4-e4b-audio-to-audioreact-video>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Diffusionsmodell | `flux-2-klein-4b.safetensors` | BF16 | 7,2 GiB |
| Text-Encoder / LLM | `qwen_3_4b.safetensors` | BF16 | 7,5 GiB |
| VAE | `flux2-vae.safetensors` | FP32 | 0,3 GiB |
| Text-Encoder / LLM | `gemma4_e4b_it_fp8_scaled.safetensors` | FP8 | 8,4 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Musik → passendes Bild → Audio-React-Video

| Einstellung | Wert |
|---|---|
| seed | 42 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 48 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 25,9 GiB / 23,8 GiB |
| RAM (ComfyUI-Prozess) | 24,5 GiB |

Der von Gemma geschriebene Bildprompt wird am Pause-Knoten unverändert übernommen („Continue“).

Eingabe · ex_song_pop_excerpt.mp3: [input_ex_song_pop_excerpt.mp3](input_ex_song_pop_excerpt.mp3)  
Ausgabe · 5 · MP4 mit Originalsound speichern: [song.mp4](song.mp4)  

Generierter visueller Prompt:

```text
A lone figure stands on a windswept, desolate cliff edge at twilight, bathed in an ethereal, dramatic light. The mood is intensely melancholic and epic, with a cool, muted color palette of deep blues, grays, and bruised purples. The composition is wide-angle, emphasizing the vastness of the landscape against the smallness of the subject, captured from a low, sweeping perspective.
```
