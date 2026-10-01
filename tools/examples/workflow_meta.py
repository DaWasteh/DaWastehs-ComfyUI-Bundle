"""German titles, one-paragraph summaries and input/output types of every workflow for the example gallery.

Keys are the workflow paths as of v1.3.0 (the rename map in tools/workflow_renames_v131.json turns them into the
v1.3.1 names). ``note`` explains why a workflow has no example output.
"""
from __future__ import annotations

META: dict[str, dict] = {}


def m(path: str, title: str, summary: str, inputs: list[str], outputs: list[str], note: str = "") -> None:
    META[path] = {"title": title, "summary": summary, "inputs": inputs, "outputs": outputs, "note": note}


T = "Text to Image/"
# ------------------------------------------------------------------------------------------------ Text to Image
m(T + "Anima_base_v1-Text-to-Image.json", "Anima Base · Text → Bild",
  "Anime-/Illustrationsmodell (2B, Cosmos-Architektur) mit kleinem Qwen3-0,6B-Text-Encoder. Versteht natürliche Sätze "
  "und Danbooru-Tags; 28 Schritte, CFG 4,5.", ["Text"], ["Bild"])
m(T + "Anima_hosekiLustrousmix_v10-Text-to-Image.json", "Anima Hoseki Lustrous Mix · Text → Bild",
  "Community-Finetune von Anima mit glänzendem, detailreichem Anime-Stil. Gleiche Einstellungen wie Anima Base.",
  ["Text"], ["Bild"])
m(T + "Boogu_image_base-Text-to-Image.json", "Boogu Image Base · Text → Bild",
  "Boogu-Basismodell mit Qwen3-VL-8B-Text-Encoder und FLUX-VAE: 50 Schritte mit CFG 4 – langsam, aber das "
  "Ausgangsmodell für eigene LoRAs.", ["Text"], ["Bild"])
m(T + "Boogu_turbo_via_LoRA-Text-to-Image.json", "Boogu + Turbo-LoRA · Text → Bild",
  "Dasselbe Boogu-Basismodell mit Turbo-LoRA: 4 Schritte, CFG 1 – etwa zehnmal schneller als ohne LoRA.",
  ["Text"], ["Bild"])
m(T + "Cosmos_Predict2_2B-Text-to-Image.json", "Cosmos Predict2 2B · Text → Bild",
  "NVIDIAs kleines Weltmodell (2B) im Bildmodus. Als Text-zu-Bild eher schlicht; es liefert vor allem Startbilder für "
  "die Cosmos-Videoworkflows.", ["Text"], ["Bild"])
m(T + "FLUX1_EclecticEuphoria_Distilled_v2-Text-to-Image.json", "FLUX.1 EclecticEuphoria Distilled · Text → Bild",
  "Destillierter FLUX.1-Finetune als GGUF Q6_K: 10 Schritte statt 25, dafür etwas weniger Details.", ["Text"],
  ["Bild"])
m(T + "FLUX1_EclecticEuphoria_Libre_v2-Text-to-Image.json", "FLUX.1 EclecticEuphoria Libre · Text → Bild",
  "FLUX.1-Finetune (FP8) mit freierem, farbigerem Stil als FLUX.1 dev; 24 Schritte.", ["Text"], ["Bild"])
m(T + "FLUX1_Kontext_dev-Text-to-Image.json", "FLUX.1 Kontext dev · Text → Bild",
  "Das Bearbeitungsmodell FLUX.1 Kontext ohne Eingabebild, also als normales Text-zu-Bild-Modell (FP8).", ["Text"],
  ["Bild"])
m(T + "FLUX1_dev_Q6_K-Text-to-Image.json", "FLUX.1 dev (GGUF Q6_K) · Text → Bild",
  "FLUX.1 dev als GGUF Q6_K (~9,8 GB statt 11,9 GB FP8). Gleiche Einstellungen wie die FP8-Version – im "
  "Quant-Vergleich direkt nebeneinander.", ["Text"], ["Bild"])
m(T + "FLUX1_dev_abliterated_Q8-Text-to-Image.json", "FLUX.1 dev abliterated (Q8_0) · Text → Bild",
  "Zensurfreie („abliterated“) FLUX.1-dev-Variante als GGUF Q8_0 mit zusätzlicher Uncensored-LoRA.", ["Text"],
  ["Bild"])
m(T + "FLUX1_dev_fp8-Text-to-Image.json", "FLUX.1 dev (FP8) · Text → Bild",
  "Der Klassiker: FLUX.1 dev 12B in FP8, clip_l + T5-XXL, 25 Schritte, Guidance 3,5.", ["Text"], ["Bild"])
m(T + "FLUX2_Klein_4b-Text-to-Image.json", "FLUX.2 Klein 4B · Text → Bild",
  "Das kleinste FLUX.2 (4B, destilliert, BF16): 4 Schritte, wenige Sekunden pro Bild, Qwen3-4B als Text-Encoder.",
  ["Text"], ["Bild"])
m(T + "FLUX2_Klein_9B_Qwen3_5-Text-to-Prompt-to-Image.json", "FLUX.2 Klein 9B + Qwen3.5 · Idee → Prompt → Bild",
  "Qwen3.5 4B schreibt aus einer kurzen Idee einen ausführlichen Prompt, du bestätigst ihn am Pause-Knoten, dann malt "
  "FLUX.2 Klein 9B (FP8) das Bild.", ["Text"], ["Prompt", "Bild"])
m(T + "FLUX2_Klein_9b_Q6_K-Text-to-Image.json", "FLUX.2 Klein 9B (GGUF Q6_K) · Text → Bild",
  "FLUX.2 Klein 9B als GGUF Q6_K – kleiner als FP8, gleiche 8 Schritte.", ["Text"], ["Bild"])
m(T + "FLUX2_Klein_9b_dare_merged-Text-to-Image.json", "FLUX.2 Klein 9B DARE-Merge (BF16) · Text → Bild",
  "Community-Merge von FLUX.2 Klein 9B in voller BF16-Präzision (17 GB).", ["Text"], ["Bild"])
m(T + "FLUX2_Klein_9b_kv_fp8-Text-to-Image.json", "FLUX.2 Klein 9B KV (FP8) · Text → Bild",
  "Offizielles FLUX.2 Klein 9B mit KV-Cache-Variante in FP8; 8 Schritte, Qwen3-8B-Text-Encoder.", ["Text"], ["Bild"])
m(T + "FLUX2_Klein_base_4b-Text-to-Image.json", "FLUX.2 Klein Base 4B · Text → Bild",
  "Das nicht destillierte Basismodell von Klein 4B (24 Schritte) – gedacht als Grundlage für LoRA-Training.",
  ["Text"], ["Bild"])
m(T + "FLUX2_dev_Q6_K-Text-to-Image.json", "FLUX.2 dev (GGUF Q6_K) · Text → Bild",
  "Das große FLUX.2 dev (32B) als GGUF Q6_K mit Mistral-Small-Text-Encoder. Höchste Qualität der FLUX-Familie, "
  "dafür einige Minuten pro Bild.", ["Text"], ["Bild"])
m(T + "FLUX2_dev_fp8mixed-Text-to-Image.json", "FLUX.2 dev (FP8 mixed) · Text → Bild",
  "FLUX.2 dev 32B in gemischter FP8-Präzision, Mistral-Small-3 BF16 als Text-Encoder, 24 Schritte.", ["Text"],
  ["Bild"])
m(T + "FLUX2_dev_fp8mixed_v2-Text-to-Image.json", "FLUX.2 dev (FP8 mixed v2) · Text → Bild",
  "Neuere FP8-mixed-Quantisierung von FLUX.2 dev (flux2-dev_fp8mixed_NEW) – gleiche Einstellungen wie v1.",
  ["Text"], ["Bild"])
m(T + "Ideogram4-Text-to-Image.json", "Ideogram 4 (FP8) · Text → Bild",
  "Ideogram 4 mit strukturiertem Prompt-Builder (JSON-Felder für Motiv, Text, Stil) und Dual-Model-Guider – stark bei "
  "Schrift und Layouts.", ["Text"], ["Bild"])
m(T + "Krea2_raw-Text-to-Image.json", "Krea 2 Raw (BF16) · Text → Bild",
  "Das unverfeinerte Krea-2-Basismodell in BF16: 52 Schritte, CFG 3,5 – langsam, sehr natürliche Fotos.", ["Text"],
  ["Bild"])
m(T + "Krea2_turbo-2K-Text-to-Image.json", "Krea 2 Turbo · Idee → Prompt → 2K-Bild",
  "Qwen3-VL 4B erweitert die Idee zum Prompt (Pause zum Prüfen), Krea 2 Turbo malt in 8 Schritten und ein zweiter "
  "Durchgang vergrößert auf 2K.", ["Text"], ["Prompt", "Bild"])
m(T + "Krea2_turbo-Extra-Pass-Text-to-Image.json", "Krea 2 Turbo + Extra-Durchgang · Text → Bild",
  "Krea 2 Turbo (FP8, 8 Schritte), danach 1,5× Latent-Vergrößerung mit einem kurzen zweiten Durchgang für mehr "
  "Details.", ["Text"], ["Bild"])
m(T + "Krea2_turbo-Low-VRAM-Text-to-Image.json", "Krea 2 Turbo (Low VRAM) · Text → Bild",
  "Krea 2 Turbo in FP8 mit FP8-Text-Encoder – die sparsamste Krea-Variante, 8 Schritte.", ["Text"], ["Bild"])
m(T + "Krea2_turbo-Uncensored-Prompt-Enhanced-Text-to-Image.json", "Krea 2 Turbo + abliterated Qwen3-VL · Idee → Prompt → Bild",
  "Ein abliterated Qwen3-VL 4B schreibt den Prompt (Pause zum Prüfen), Krea 2 Turbo malt das Bild.", ["Text"],
  ["Prompt", "Bild"])
m(T + "Krea2_turbo_via_LoRA-Text-to-Image.json", "Krea 2 Raw + Turbo-LoRA · Text → Bild",
  "Krea 2 Raw in BF16 mit Turbo-LoRA: 8 Schritte statt 52 bei voller Präzision.", ["Text"], ["Bild"])
m(T + "LongCat_image-Text-to-Image.json", "LongCat Image · Text → Bild",
  "Meituans LongCat Image (BF16) mit Qwen2.5-VL-7B-Encoder; 20 Schritte, CFG 4.", ["Text"], ["Bild"])
m(T + "LongCat_image_turbo-Text-to-Image.json", "LongCat Image Turbo · Text → Bild",
  "Destillierte LongCat-Variante: 4 Schritte, CFG 1.", ["Text"], ["Bild"])
m(T + "Ming_Image_0_1_Design_INT8-Text-to-Image.json", "Ming Image 0.1 Design · Text → Design",
  "Grafikdesign-Modell (Poster, Karten, Folien) in INT8. Der Qwen3.8-27B-Prompt-Writer schreibt vorher das "
  "offizielle Design-JSON; Standardgröße 2048².", ["Text"], ["Bild"])
m(T + "Ming_Image_0_1_Design_INT8-Transparent-RGBA.json", "Ming Image 0.1 Design · Text → transparentes PNG",
  "Sticker, Logos und Freisteller mit echtem Alphakanal; liefert das Modell keinen, stellt BiRefNet frei.",
  ["Text"], ["Bild (RGBA)"])
m(T + "Qwen_Image_2_1_BF16-Text-to-Image.json", "Qwen Image 2.1 (BF16) · Text → Bild",
  "Alibabas Qwen Image 2.1 in voller Präzision: sehr gute Schrift, lange Prompts, bis 2K. 25 Schritte, CFG 1.",
  ["Text"], ["Bild"])
m(T + "SD15_v1-5-pruned-emaonly-Text-to-Image.json", "Stable Diffusion 1.5 · Text → Bild",
  "Das originale SD 1.5 (FP16) als Referenz: 512 px nativ, 28 Schritte. Klein und schnell, aber sichtbar älter.",
  ["Text"], ["Bild"])
m(T + "SD21_wd-1-5-beta2-unclip-Text-to-Image.json", "SD 2.1 Waifu Diffusion 1.5 · Text → Bild",
  "Waifu Diffusion 1.5 Beta 2 (SD-2.1-Basis, 768 px) mit Anime-VAE.", ["Text"], ["Bild"])
m(T + "SDXL_EclecticEuphoria_Illus_Real_v3-Text-to-Image.json", "SDXL EclecticEuphoria Illus Real v3 · Text → Bild",
  "Illustrious-basiertes SDXL-Modell mit halbrealistischem Look; Tag-Prompts.", ["Text"], ["Bild"])
m(T + "SDXL_EclecticEuphoria_Illustrious_v2-Text-to-Image.json", "SDXL EclecticEuphoria Illustrious v2 · Text → Bild",
  "Illustrious-SDXL für Anime-Illustrationen; Tag-Prompts, 30 Schritte.", ["Text"], ["Bild"])
m(T + "SDXL_NoobAI_XL_v1_1-Text-to-Image.json", "SDXL NoobAI XL 1.1 · Text → Bild",
  "Beliebtes Anime-SDXL (BF16) auf Illustrious-Basis mit großem Danbooru-Wissen.", ["Text"], ["Bild"])
m(T + "SDXL_RealVisXL_V4-Text-to-Image.json", "SDXL RealVisXL V4 · Text → Bild",
  "Fotorealistisches SDXL-Modell (FP16) mit natürlichen Prompts; 32 Schritte, CFG 5.", ["Text"], ["Bild"])
m(T + "SDXL_animij_v8-Text-to-Image.json", "SDXL animij v8 · Text → Bild",
  "Anime-SDXL mit weichem, farbenfrohem Stil; Tag-Prompts.", ["Text"], ["Bild"])
m(T + "SDXL_moodyRealMix_zitV4DPO-Text-to-Image.json", "Z-Image Turbo MoodyRealMix V4 DPO · Text → Bild",
  "Stimmungsvoller Foto-Finetune von Z-Image Turbo (lag bisher fälschlich als SDXL im Bundle). 8 Schritte, CFG 1.",
  ["Text"], ["Bild"])
m(T + "SDXL_novaAnimeXL_ilV190-Text-to-Image.json", "SDXL Nova Anime XL (IL v190) · Text → Bild",
  "Illustrious-basiertes Anime-SDXL mit kräftigen Farben; Tag-Prompts.", ["Text"], ["Bild"])
m(T + "SDXL_oneObsession_v20Bold-Text-to-Image.json", "SDXL One Obsession v2.0 Bold · Text → Bild",
  "Illustrious-Mix mit kräftigem, plakativem Stil; Tag-Prompts.", ["Text"], ["Bild"])
m(T + "SDXL_ponyDiffusionV6XL-Text-to-Image.json", "SDXL Pony Diffusion V6 · Text → Bild",
  "Pony Diffusion V6 XL; braucht die score_9/score_8_up-Präfixe und Tag-Prompts.", ["Text"], ["Bild"])
m(T + "SDXL_ultrarealFineTune_v4-Text-to-Image.json", "FLUX.1 dev UltraReal v4 (FP8) · Text → Bild",
  "Fotorealistischer FLUX.1-dev-Finetune (lag bisher fälschlich als SDXL im Bundle). 25 Schritte, Guidance 3,5.",
  ["Text"], ["Bild"])
m(T + "ZImage_base-Text-to-Image.json", "Z-Image Base · Text → Bild",
  "Das nicht destillierte Z-Image (6B, BF16): 40 Schritte mit CFG 4 und Negativprompt – Grundlage für LoRAs.",
  ["Text"], ["Bild"])
m(T + "ZImage_turbo-Text-to-Image.json", "Z-Image Turbo · Text → Bild",
  "Alibabas schnelles 6B-Modell: 8 Schritte, CFG 1, sehr gute Fotos und Schrift in wenigen Sekunden.", ["Text"],
  ["Bild"])


# Category modules register their entries on import.
import workflow_meta_image  # noqa: E402,F401
import workflow_meta_video  # noqa: E402,F401
import workflow_meta_audio  # noqa: E402,F401
import workflow_meta_misc  # noqa: E402,F401
