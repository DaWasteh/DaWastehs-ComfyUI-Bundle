# FLUX.2 Klein 9B · vier Bilder zu einer Szene

**Workflow-Datei:** [`workflows/Image Editing/FLUX2_Klein_9B_KV_FP8-Four-Image-Edit.json`](../../../workflows/Image%20Editing/FLUX2_Klein_9B_KV_FP8-Four-Image-Edit.json)  
**Kategorie:** Image Editing · **Eingabe → Ausgabe:** Bild + Text → Bild · **Quant:** FP8

Bis v1.3.0 hieß der Workflow `FLUX2_Klein_9B_KV-Four-Image-Edit.json`.

Bis zu vier Referenzen (Personen, Tier, Ort) werden zu einem neuen Bild zusammengesetzt; Größe über den Resolution-Selector.

Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: <https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/flux2-klein-9b-kv-fp8-four-image-edit>

## Modelle

| Rolle | Datei | Quant | Größe |
|---|---|---|---:|
| Text-Encoder / LLM | `qwen_3_8b_fp8mixed.safetensors` | FP8 mixed | 8,1 GiB |
| Diffusionsmodell | `flux-2-klein-9b-kv-fp8.safetensors` | FP8 | 9,1 GiB |
| VAE | `flux2-vae.safetensors` | FP32 | 0,3 GiB |

## Workflow in ComfyUI

Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):

[![Workflow](workflow-preview.webp)](workflow.webp)

## Beispiele

### Vier Bilder zu einer Szene

Prompt:

```text
A warm lifestyle photograph: the woman from image 1 and the man from image 2 sit side by side at the wooden kitchen table from image 4, the golden retriever from image 3 sits next to them, morning light, natural smiles
```

| Einstellung | Wert |
|---|---|
| seed | 7 |
| steps | 4 |
| cfg | 1 |
| sampler_name | euler |
| scheduler | simple |
| denoise | 1 |
| Dauer (Ausführung) | 44 s |
| VRAM R9700 (belegt / PyTorch-Spitze) | 25,8 GiB / 21,1 GiB |
| RAM (ComfyUI-Prozess) | 18,4 GiB |

Eingabe · ex_portrait_woman.png: ![ex_portrait_woman.png](thumbs/input_ex_portrait_woman.webp) ([Datei](input_ex_portrait_woman.webp))  
Eingabe · ex_portrait_man.png: ![ex_portrait_man.png](thumbs/input_ex_portrait_man.webp) ([Datei](input_ex_portrait_man.webp))  
Eingabe · ex_dog_photo.png: ![ex_dog_photo.png](thumbs/input_ex_dog_photo.webp) ([Datei](input_ex_dog_photo.webp))  
Eingabe · ex_kitchen_table.png: ![ex_kitchen_table.png](thumbs/input_ex_kitchen_table.webp) ([Datei](input_ex_kitchen_table.webp))  
Ausgabe · Ausgabe: [![Ausgabe](thumbs/family.webp)](family.webp) · [Volle Auflösung (1360×768, WebP mit Workflow – per Drag & Drop in ComfyUI ladbar)](family.webp)
