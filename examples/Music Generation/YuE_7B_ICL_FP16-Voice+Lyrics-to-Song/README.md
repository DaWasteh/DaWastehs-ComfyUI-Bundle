# YuE 7B ICL (FP16) · Referenzgesang + Songtext → Song

**Workflow-Datei:** [`workflows/Music Generation/YuE_7B_ICL_FP16-Voice+Lyrics-to-Song.json`](../../../workflows/Music%20Generation/YuE_7B_ICL_FP16-Voice%2BLyrics-to-Song.json)  
**Kategorie:** Music Generation · **Eingabe → Ausgabe:** Audio + Songtext → Song · **Quant:** FP16

Bis v1.3.0 hieß der Workflow `YuE_7B-FP16_R9700-Reference-Voice-ICL-Music-Generation.json`.

In-Context-Learning: ein ca. 30 s langer Referenzgesang gibt Stimme und Stil vor.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/yue-7b-icl-fp16-voice-lyrics-to-song>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Modell | `ckpt_00360000.pth` | – | 1,3 GiB |
| Modell | `decoder_131000.pth` | – | 0,1 GiB |
| Modell | `decoder_151000.pth` | – | 0,1 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Referenzgesang + Songtext → Song

Prompt:

```text
pop, uplifting, female vocal, bright synths
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
| duration | 2 Abschnitte (~60 s) |
| seed | 42 |
| Dauer (Ausführung) | 27 min 8 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 14,3 GiB / 13,6 GiB |
| RAM (ComfyUI-Prozess) | 17,6 GiB |

Referenzgesang ist der Pop-Song aus dem ACE-Step-Turbo-Beispiel.

Eingabe · ex_song_pop.mp3: [input_ex_song_pop.mp3](input_ex_song_pop.mp3)  
Ausgabe · YuE ICL als MP3 speichern: [icl.mp3](icl.mp3)
