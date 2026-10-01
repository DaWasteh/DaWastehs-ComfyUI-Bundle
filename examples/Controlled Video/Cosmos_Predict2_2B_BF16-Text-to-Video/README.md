# Cosmos Predict2 2B · Text → Video

**Workflow-Datei:** [`workflows/Controlled Video/Cosmos_Predict2_2B_BF16-Text-to-Video.json`](../../../workflows/Controlled%20Video/Cosmos_Predict2_2B_BF16-Text-to-Video.json)  
**Kategorie:** Controlled Video · **Eingabe → Ausgabe:** Text → Video · **Quant:** BF16

Bis v1.3.0 hieß der Workflow `Cosmos_Predict2_2B-Text-to-Video.json`.

Erst ein Startbild mit Cosmos-T2I, dann das Video daraus – alles aus einem Prompt.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/cosmos-predict2-2b-bf16-text-to-video>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Text-Encoder / LLM | `oldt5_xxl_fp8_e4m3fn_scaled.safetensors` | FP8 | 4,6 GiB |
| VAE | `wan_2.1_vae.safetensors` | BF16 | 0,2 GiB |
| Diffusionsmodell | `cosmos_predict2_2B_video2world_480p_16fps.safetensors` | BF16 | 3,6 GiB |
| Diffusionsmodell | `cosmos_predict2_2B_t2i.safetensors` | BF16 | 3,6 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Nur Text

Prompt:

```text
A locked-off camera observes a red rubber ball rolling down a wooden ramp onto a grey concrete floor and bouncing twice, plain white wall, soft daylight
```

| Einstellung | Wert |
|---|---|
| duration | 5 s |
| seed | 118 |
| steps | 30 |
| cfg | 4 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 5 min 40 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 24,0 GiB / 18,9 GiB |
| RAM (ComfyUI-Prozess) | 8,3 GiB |

Ausgabe · Ausgabe: [ball.mp4](ball.mp4)
