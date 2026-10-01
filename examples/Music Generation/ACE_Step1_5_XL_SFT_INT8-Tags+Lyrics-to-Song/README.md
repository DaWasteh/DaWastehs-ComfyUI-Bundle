# ACE-Step 1.5 XL SFT (INT8) · Stil-Tags + Songtext → Song

**Workflow-Datei:** [`workflows/Music Generation/ACE_Step1_5_XL_SFT_INT8-Tags+Lyrics-to-Song.json`](../../../workflows/Music%20Generation/ACE_Step1_5_XL_SFT_INT8-Tags%2BLyrics-to-Song.json)  
**Kategorie:** Music Generation · **Eingabe → Ausgabe:** Tags + Songtext → Song · **Quant:** INT8

Bis v1.3.0 hieß der Workflow `ACE-Step1_5_XL_SFT_INT8_ConvRot-Music-Generation.json`.

INT8-Variante des XL-SFT-Modells – im Quant-Vergleich neben BF16.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/ace-step1-5-xl-sft-int8-tags-lyrics-to-song>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Diffusionsmodell | `acestep_v1.5_xl_sft_int8_convrot.safetensors` | INT8 | 4,7 GiB |
| VAE | `ace_1.5_vae.safetensors` | BF16 | 0,3 GiB |
| Text-Encoder | `qwen_0.6b_ace15.safetensors` | BF16 | 1,1 GiB |
| Text-Encoder | `qwen_4b_ace15.safetensors` | BF16 | 7,8 GiB |
| LoRA | `taylor_swift_v2_rank16.safetensors` | BF16 | 0,0 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Pop · englisch

Prompt:

```text
upbeat modern pop, female vocals, catchy chorus, bright synths, punchy drums, summer vibe, 118 BPM
```

| Einstellung | Wert |
|---|---|
| lyrics | [Verse]
Morning light on the window pane
City waking up again
Coffee cups and a paper plane
Flying out into the rain

[Chorus]
We are running on sunshine
Every heartbeat feels like a sign
Turn it up, we got all night
We are running on sunshine

[Verse]
Neon signs on a subway train
Every stranger knows my name
Dancing through the evening haze
We don't need to change a thing

[Chorus]
We are running on sunshine
Every heartbeat feels like a sign
Turn it up, we got all night
We are running on sunshine |
| duration | 60 s |
| seed | 42 |
| language | en |
| steps | 75 |
| cfg | 4 |
| sampler_name | euler |
| scheduler | normal |
| denoise | 1 |
| shift | 3 |
| Dauer (Ausführung) | 49 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 18,3 GiB / 21,3 GiB |
| RAM (ComfyUI-Prozess) | 10,4 GiB |

Die Stimmen-LoRA ist im Beispiel überbrückt: die lokal installierten LoRAs bilden reale Sängerinnen nach und werden hier nicht gezeigt.

Ausgabe · Ausgabe: [pop.mp3](pop.mp3)  

### Indie-Rock · deutsch

Prompt:

```text
energetic German indie rock, male vocals, distorted electric guitars, driving drums, anthemic chorus, 140 BPM
```

| Einstellung | Wert |
|---|---|
| lyrics | [Verse]
Wir fahren nachts durch leere Straßen
die Stadt schläft, doch wir sind wach
die Lichter ziehen an uns vorbei
wie Sterne über dem Dach

[Chorus]
Wir sind laut, wir sind hier
nichts hält uns heute auf
wir sind laut, wir sind hier
und die Nacht nimmt ihren Lauf

[Verse]
Ein altes Radio, ein kaputter Sitz
wir singen jedes Lied mit
der Morgen kommt, doch nicht so schnell
wir halten noch ein bisschen Schritt

[Chorus]
Wir sind laut, wir sind hier
nichts hält uns heute auf
wir sind laut, wir sind hier
und die Nacht nimmt ihren Lauf |
| duration | 60 s |
| seed | 42 |
| language | de |
| steps | 75 |
| cfg | 4 |
| sampler_name | euler |
| scheduler | normal |
| denoise | 1 |
| shift | 3 |
| Dauer (Ausführung) | 26 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 26,9 GiB / 21,3 GiB |
| RAM (ComfyUI-Prozess) | 2,6 GiB |

Die Stimmen-LoRA ist im Beispiel überbrückt: die lokal installierten LoRAs bilden reale Sängerinnen nach und werden hier nicht gezeigt.

Ausgabe · Ausgabe: [rock.mp3](rock.mp3)
