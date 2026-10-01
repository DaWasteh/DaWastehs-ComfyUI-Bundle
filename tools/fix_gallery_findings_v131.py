#!/usr/bin/env python3
"""v1.3.1: workflow bugs found by the example gallery runs.

* WAN 2.2 TI2V 5B and WAN 2.2 Fun Control 5B decoded the whole clip with a plain ``VAEDecode``. On the R9700 (32 GB)
  a 5-second 1280x704 clip already failed: the Wan 2.2 VAE asked for 18.6 GiB in one convolution, and ComfyUI's
  automatic tiled retry sizes its tiles from an estimate and failed the same way (the default 10 seconds need twice as
  much). The decoder becomes ``VAEDecodeTiled`` with the ComfyUI defaults 512 / 64 / 64 / 8, as in the other video
  workflows of the bundle.
* Kandinsky 5 Lite image to video decoded with a plain ``VAEDecode`` on the RX 9070 XT (16 GB). ComfyUI's tiled
  retry cuts 256 px tiles but decodes all 121 frames at once and asked for 16.9 GiB in one convolution. The decoder
  becomes ``VAEDecodeTiled`` 256 / 64 / 32 / 8 (32-frame blocks). Even the tiles failed on the second GPU: the
  Qwen 2.5 VL 7B text encoder stays loaded there (9.5 GiB), the decode could not get 4.2 GiB. The VAE moves to the
  R9700 next to the 2B model; the text encoder stays on the second GPU.
* SDPose and Depth Anything 3 video: the VHS Meta Batch Manager stored its value as a list. VHS restores its nodes by
  widget name and adds a hidden ``count`` widget, so the frontend showed "Failed to restore node: META-BATCH" and
  painted the node red on every load. The value is stored the way VHS saves it (``{"frames_per_batch": 64,
  "count": 0}``); ``tools/build_vision_workflows_v128.py`` writes the same.
* MMAudio video to audio: the sampler spreads the whole input video over ``duration`` seconds, but ``duration`` (8)
  and the ``frame_rate`` of the video output (8) were fixed values. Any other clip got a sound track that did not sit
  on the picture, and a 16 fps clip came out at half speed with the sound ending halfway. A ``VHS_VideoInfoLoaded``
  node now passes the fps and the length of the loaded video to both.
* Ideogram 4 text to image and idea -> prompt -> image sampled with BasicScheduler karras / 28 steps, res_2m and an
  AuraFlow shift of 5. That schedule does not fit the flow model: every picture carried a hatched, crackled pattern,
  soft areas and unreadable small lettering. Both use the chain of ComfyUI's official Ideogram 4 template now:
  Ideogram4Scheduler (preset "Default": 20 steps, mu 0, std 1.75), euler, CFG override 3 from 0.7, and shift 1
  (native; the schedule comes from the scheduler). In idea -> prompt -> image the scheduler takes its size from the
  same resolution node as the latent.
* FLUX.2 Klein Base 4B text to image sampled the undistilled base model like the distilled one: CFG 1 with a zeroed
  negative. Without guidance the base model gives soft, washed-out pictures and garbled lettering (its own settings
  note says "undistilled, more steps, higher guidance"). As in ComfyUI's official Klein base template it now uses
  CFG 5 and an empty text encode as negative (the base model was trained with empty-prompt dropout; a zeroed
  conditioning is not what it knows as "unconditional"). 24 steps stay (template: 20).
* FLUX.2 Klein 4B + Gemma 4 audio -> audio-react video: the "VRAM Debug" node before the VAE decode unloaded all
  models. ComfyUI moves unloaded weights back into system RAM, so FLUX.2 Klein, Qwen3 4B and Gemma 4 E4B took about
  14 GiB more RAM right before the Pixaroma audio engine, which renders frame by frame on the GPU but keeps every frame
  in RAM (8 s at 1024x1024 = 2.2 GB) and refuses to start when less is free ("above the 0.9 GB currently free").
  The node only empties the cache now, like the sibling audio-to-image workflow.
* Idea -> Ideogram 4 fields (Qwen3.5): the "Save Text" node wrote to ``H:\\ComfyUI\\ComfyUI\\output\\prompts\\``, a drive
  of the machine the workflow was built on; every other setup failed with "The system cannot find the path". It saves
  to ``output/prompts/`` relative to the ComfyUI folder both launchers start in.
* Qwen Image Edit 2511 · 8 camera angles (official "multiple angles" template): every angle loaded its own 41 GB model,
  text encoder, VAE and LoRAs; see ``tools/restructure_qwen_angles_v131.py``. One shared chain feeds all eight angles.
* Z-Image Turbo tiled upscale loaded ``qwen3_8b_abliterated_v2-fp8mixed`` (the FLUX.2 Klein 9B encoder, 4096 wide)
  as its text encoder; Z-Image expects Qwen3 4B (2560 wide) and the sampler stopped with
  "normalized_shape=[2560] ... got input of size [3, 512, 12288]". The loader now uses ``Qwen\\qwen_3_4b.safetensors``
  like the Z-Image text-to-image workflow.
* WAN 2.2 14B text to video loaded the image-to-video models and Lightning LoRAs (``wan2.2_i2v_*``) although its own
  model note lists the text-to-video files; without a start image the I2V models only produced noise. The four
  loaders now use ``wan2.2_t2v_{high,low}_noise_14B_fp8_scaled`` and the v1.1 T2V Lightning LoRAs.
* Ideogram 4 + Qwen3.5 (idea -> JSON -> image, idea -> fields, idea -> JSON): the optional sketch loader
  ("③ SKETCH / PAINT-VORLAGE (optional)") was active with the placeholder ``example.png``. ComfyUI then drops the whole
  Qwen branch at validation (or rejects the prompt), and the image workflow rendered an empty caption: noise. The loader
  is muted (Ctrl+M to use a sketch). In idea -> JSON -> image the generated JSON also never reached the prompt builder;
  it now feeds the builder's ``import_json`` (import_mode "when empty": the editor regions are seeded from the JSON and
  stay editable).
* SDXL RealVisXL + IP-Adapter (PLUS FACE): every SDE sampler (dpmpp_3m_sde_gpu, dpmpp_3m_sde, dpmpp_2m_sde_gpu) burnt
  colour blotches into the face on this ROCm stack as soon as the IP-Adapter patch was active (without IP-Adapter the
  same sampler was clean); dpmpp_2m / karras is clean. Sampler and FaceDetailer switch to it, steps and CFG stay.
* SDXL Illustrious V2 (NSFW): the sampler held 180 steps at CFG 69, which burns every image; 30 steps at CFG 6.5.
* SDXL Multi-Checkpoint (NSFW): the third checkpoint sampled the encoded input image again instead of the second
  stage's result (its VAE Encode, node 18, was left unconnected), so stages 1 and 2 never reached the output.
* LTX-2.3 22B text to video (4 workflows) and image to video: the tiled VAE decode asked for 2.6-3.3 GiB in one
  piece while the 22B model stayed loaded (ComfyUI underestimates the decode and unloads nothing): out of memory at
  1280x704 under the VRAM guard. Text to video decodes in 384 px tiles (was 512), image to video in 384 px tiles and
  32-frame blocks (was 768 px and 4096 frames, i.e. the whole clip at once). Measured: both run, no visible seams.
* LTX-2.3 dev MXFP8 text to video put the text encoder on the RX 9070 XT; Gemma 3 12B takes 25 GB there once loaded,
  so every run stopped in CLIPTextEncode. All three roles default to the R9700 like the other LTX-2.3 workflows.
* Bernini-R image edit loaded ``T5\\t5xxl_fp8_e4m3fn_scaled`` as the Wan text encoder ("invalid tokenizer"); the video
  edit workflow and every WAN workflow use ``UMT5\\umt5_xxl_fp8_e4m3fn_scaled``. The subgraph instance passes
  ``clip_name`` in and overrides the inner loader, so its own widget value is corrected as well.
* FLUX.1 Kontext Character Keep: the zeroed negative (``ConditioningZeroOut``) had lost its input link, so ComfyUI
  refused the prompt ("Required input is missing"). It is connected to the text encoder again, like in the official
  Kontext template. The saved default instruction asked to undress the person in the input photo, which neither fits
  a character-keep workflow nor the category; it is replaced by a neutral character-keep instruction.

Workflows are addressed by their v1.3.0 names.

  python tools/fix_gallery_findings_v131.py [--check]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

try:
    from tools.restructure_qwen_angles_v131 import refresh_note, restructure as restructure_angles
    from tools.rodent_layout import apply_rodent_layout, refresh_topology_hashes
    from tools.workflow_names_v131 import new_key
except ModuleNotFoundError:  # run from inside tools/
    from restructure_qwen_angles_v131 import refresh_note, restructure as restructure_angles
    from rodent_layout import apply_rodent_layout, refresh_topology_hashes
    from workflow_names_v131 import new_key

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / "workflows"

TILED = [512, 64, 64, 8]
TILED_NOTE = (
    "# Erklärung · VAE Decode (Tiled) · Node {id}\n\n"
    "**Zweck:** Dekodiert das Video-Latent in Kacheln (räumlich 512 px, zeitlich 64 Frames) zu Bildern. "
    "Seit v1.3.1 statt VAE Decode: ein 5-Sekunden-Clip in 1280×704 brauchte ungekachelt über 18 GiB in einer "
    "einzigen Faltung und scheiterte auch auf der R9700 (32 GB).\n\n"
    "**Einstellbare Werte**\n"
    "- `tile_size` = `512` — Kachelgröße in Pixeln. Kleiner spart VRAM (z. B. 256 auf 16-GB-Karten), größer ist etwas "
    "schneller.\n"
    "- `overlap` = `64` — Überlappung der Kacheln; verhindert sichtbare Nähte.\n"
    "- `temporal_size` = `64` — Frames je Durchgang. Kleiner spart VRAM bei langen Clips.\n"
    "- `temporal_overlap` = `8` — Überlappung zwischen den Frame-Blöcken.\n\n"
    "**Eingänge**\n"
    "- `samples` (LATENT, Link {samples}): das fertige Video-Latent aus dem Sampler\n"
    "- `vae` (VAE, Link {vae}): Wan-2.2-VAE\n\n"
    "**Ausgänge**\n"
    "- `IMAGE` (IMAGE, {n_out} Verbindung(en)): die Einzelbilder für das Video"
)
KANDINSKY_TILED = [256, 64, 32, 8]
KANDINSKY_TILED_NOTE = (
    "# Erklärung · VAE Decode (Tiled) · Node {id}\n\n"
    "**Zweck:** Dekodiert das Video-Latent in Kacheln (räumlich 256 px, zeitlich 32 Frames) zu Bildern. "
    "Seit v1.3.1 statt VAE Decode: ComfyUIs automatischer Kachel-Versuch dekodiert alle Frames auf einmal und "
    "forderte bei 5 Sekunden 768×512 auf der RX 9070 XT (16 GB) 16,9 GiB in einer einzigen Faltung.\n\n"
    "**Einstellbare Werte**\n"
    "- `tile_size` = `256` — Kachelgröße in Pixeln. Größer ist etwas schneller und braucht mehr VRAM "
    "(512 mit dem VAE auf einer 32-GB-Karte).\n"
    "- `overlap` = `64` — Überlappung der Kacheln; verhindert sichtbare Nähte.\n"
    "- `temporal_size` = `32` — Frames je Durchgang; bestimmt den VRAM-Bedarf am stärksten.\n"
    "- `temporal_overlap` = `8` — Überlappung zwischen den Frame-Blöcken.\n\n"
    "**Eingänge**\n"
    "- `samples` (LATENT, Link {samples}): das fertige Video-Latent aus dem Sampler\n"
    "- `vae` (VAE, Link {vae}): HunyuanVideo-VAE\n\n"
    "**Ausgänge**\n"
    "- `IMAGE` (IMAGE, {n_out} Verbindung(en)): die Einzelbilder für das Video"
)
DECODE_TARGETS = {  # rel: (node id, widget values, note)
    "Text+Image to Video/WAN22_5B-Text+Image-to-Video.json": (8, TILED, TILED_NOTE),
    "Controlled Video/WAN22_5B_Fun-Control-to-Video.json": (8, TILED, TILED_NOTE),
    "Text+Image to Video/Kandinsky5_Lite-Text+Image-to-Video.json": (85, KANDINSKY_TILED, KANDINSKY_TILED_NOTE),
}
ENCODER_TARGETS = {"Image Upscaling/ZImage_Turbo-Tiled-Upscale.json": 201}
OLD_ENCODER = "Qwen\\qwen3_8b_abliterated_v2-fp8mixed.safetensors"
NEW_ENCODER = "Qwen\\qwen_3_4b.safetensors"


def _note_for(wf: dict, node_id: int) -> dict | None:
    return next((n for n in wf.get("nodes", []) if n.get("type") in ("MarkdownNote", "Note")
                 and (n.get("properties") or {}).get("dawasteh_note_for") == node_id), None)


def tile_decode(wf: dict, node_id: int, values: list = TILED, note_text: str = TILED_NOTE) -> bool:
    node = next((n for n in wf.get("nodes", []) if n.get("id") == node_id), None)
    if node is None or node.get("type") != "VAEDecode":
        return False
    links = {i["name"]: i.get("link") for i in node.get("inputs", [])}
    node["type"] = "VAEDecodeTiled"
    node["size"] = [270, 150]  # the column below it is re-laid out by apply_rodent_layout() in apply()
    node["properties"] = {"Node name for S&R": "VAEDecodeTiled", "cnr_id": "comfy-core", "ver": "0.13.0"}
    node["widgets_values"] = list(values)
    note = _note_for(wf, node_id)
    if note is not None:
        n_out = len(node["outputs"][0].get("links") or [])
        note["title"] = f"Erklärung · VAE Decode (Tiled) · Node {node_id}"
        note["widgets_values"] = [note_text.format(id=node_id, samples=links.get("samples"), vae=links.get("vae"),
                                                    n_out=n_out)]
    return True


def fix_encoder(wf: dict, node_id: int) -> bool:
    node = next((n for n in wf.get("nodes", []) if n.get("id") == node_id), None)
    if node is None or node.get("type") != "CLIPLoader" or node["widgets_values"][0] != OLD_ENCODER:
        return False
    node["widgets_values"][0] = NEW_ENCODER
    note = _note_for(wf, node_id)
    if note is not None:
        note["widgets_values"] = [note["widgets_values"][0].replace(OLD_ENCODER, NEW_ENCODER)]
    return True


KONTEXT = "Character & Consistency/FLUX1_Kontext-Character-Keep.json"
KONTEXT_PROMPT = ("Keep the exact same character: identical face, hair, body proportions and outfit. Place the person "
                  "in a new scene, standing in a sunny city park, natural light, photorealistic.")


def fix_kontext(wf: dict) -> bool:
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    zero, encoder, prompt = nodes.get(10), nodes.get(7), nodes.get(28)
    if not (zero and encoder and zero.get("type") == "ConditioningZeroOut" and zero["inputs"][0].get("link") is None):
        return False
    link_id = int(wf.get("last_link_id", 0)) + 1
    wf["last_link_id"] = link_id
    wf["links"].append([link_id, 7, 0, 10, 0, "CONDITIONING"])
    zero["inputs"][0]["link"] = link_id
    encoder["outputs"][0]["links"] = [*(encoder["outputs"][0].get("links") or []), link_id]
    old_text = None
    if prompt is not None and prompt.get("type") == "PixaromaPrompt":
        state = prompt.setdefault("properties", {}).setdefault("promptState", {})
        old_text = state.get("text")
        state["text"] = KONTEXT_PROMPT
    for note in wf["nodes"]:
        target = (note.get("properties") or {}).get("dawasteh_note_for")
        if note.get("type") not in ("MarkdownNote", "Note") or target not in (7, 10):
            continue
        text = note["widgets_values"][0]
        if target == 10:
            text = text.replace("- `conditioning` (CONDITIONING, nicht verbunden): liefert Eingabedaten",
                                f"- `conditioning` (CONDITIONING, Link {link_id}): liefert Eingabedaten")
        else:
            text = text.replace("(CONDITIONING, 1 Verbindung(en))", "(CONDITIONING, 2 Verbindung(en))")
            if old_text:
                start = text.find("- `text` = `")
                end = text.find("` — ", start)
                if start >= 0 and end > start:
                    short = KONTEXT_PROMPT if len(KONTEXT_PROMPT) <= 110 else KONTEXT_PROMPT[:107].rstrip() + "…"
                    text = text[:start] + f"- `text` = `{short}" + text[end:]
        note["widgets_values"] = [text]
    return True


PROMPT_MANIFEST = ROOT / "tools" / "pixaroma_prompt_manifest.json"


def sync_prompt_manifest(manifest: dict) -> bool:
    """The Pixaroma prompt manifest pins the integrated prompt text; follow the new Kontext default."""
    path = "workflows/" + new_key(KONTEXT)
    entry = next((e for e in manifest["entries"] if e["path"] == path), None)
    target = next((t for t in (entry or {}).get("targets", []) if t.get("node_id") == 7), None)
    if target is None or target.get("source_text") == KONTEXT_PROMPT:
        return False
    target["source_text"] = KONTEXT_PROMPT
    target["source_hash"] = hashlib.sha256(
        json.dumps(KONTEXT_PROMPT, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return True


WAN_T2V = "Text to Video/WAN22_14B_fp8_lightx2v-Text-to-Video.json"
WAN_T2V_FILES = {
    164: ("WAN\\wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", "WAN\\wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors"),
    165: ("WAN\\wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "WAN\\wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors"),
    166: ("WAN\\wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
          "WAN\\wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors"),
    167: ("WAN\\wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
          "WAN\\wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"),
}


def fix_wan_t2v(wf: dict) -> list:
    changed = []
    for node in wf.get("nodes", []):
        pair = WAN_T2V_FILES.get(node.get("id"))
        if pair and node.get("widgets_values") and node["widgets_values"][0] == pair[0]:
            node["widgets_values"][0] = pair[1]
            note = _note_for(wf, node["id"])
            if note is not None:
                note["widgets_values"] = [note["widgets_values"][0].replace(pair[0], pair[1])]
            changed.append(node["id"])
    return changed


IDEOGRAM_AUTO = "Prompt Enhancer/Ideogram4_Qwen3_5-Auto-Prompt-to-Image.json"
IDEOGRAM_OPTIONAL_SKETCH = {
    IDEOGRAM_AUTO: 213,
    "Prompt Tools/Ideogram4_Qwen3_5-Field-Text-Builder.json": 3,
    "Prompt Tools/Ideogram4_Qwen3_5-JSON-Prompt-Builder.json": 3,
}
MUTED_HINT = ("\n\n**v1.3.1:** standardmäßig stummgeschaltet – der Eingang ist optional, und eine fehlende Platzhalterdatei "
              "ließ ComfyUI den ganzen Qwen-Zweig verwerfen. Zum Verwenden Node auswählen und Strg+M drücken.")


def fix_ideogram(rel: str, wf: dict) -> list:
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    changed = []
    loader = nodes.get(IDEOGRAM_OPTIONAL_SKETCH[rel])
    if loader is not None and loader.get("type") == "LoadImage" and loader.get("mode", 0) == 0:
        loader["mode"] = 2
        note = _note_for(wf, loader["id"])
        if note is not None and MUTED_HINT not in note["widgets_values"][0]:
            note["widgets_values"] = [note["widgets_values"][0] + MUTED_HINT]
        changed.append(loader["id"])
    if rel == IDEOGRAM_AUTO:
        writer, builder = nodes.get(210), nodes.get(185)
        slot = next((k for k, i in enumerate(builder["inputs"]) if i["name"] == "import_json"), None)
        if writer and slot is not None and builder["inputs"][slot].get("link") is None:
            link_id = int(wf.get("last_link_id", 0)) + 1
            wf["last_link_id"] = link_id
            wf["links"].append([link_id, 210, 0, 185, slot, "STRING"])
            builder["inputs"][slot]["link"] = link_id
            writer["outputs"][0]["links"] = [*(writer["outputs"][0].get("links") or []), link_id]
            note = _note_for(wf, 185)
            if note is not None:
                note["widgets_values"] = [note["widgets_values"][0].replace(
                    "- `import_json` (STRING, nicht verbunden)", f"- `import_json` (STRING, Link {link_id})")]
            changed.append(185)
    return changed


IPADAPTER = "Character & Consistency/SDXL_IPAdapter-Character-Keep.json"
ILLUSTRIOUS_V2 = "NSFW/SDXL_Illustrious_v2-Text-to-Image.json"
MULTI_CHECKPOINT = "NSFW/SDXL_Multi-Checkpoint_v1-Text-to-Image.json"


def _set_widget(wf: dict, node: dict, index: int, old, new) -> bool:
    values = node.get("widgets_values") or []
    if index >= len(values) or values[index] != old:
        return False
    values[index] = new
    note = _note_for(wf, node["id"])
    if note is not None:
        note["widgets_values"] = [note["widgets_values"][0].replace(f"= `{old}`", f"= `{new}`", 1)]
    return True


def fix_ipadapter(wf: dict) -> list:
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    changed = []
    for node_id, sampler_index in ((8, 4), (11, 7)):  # KSampler, FaceDetailer
        node = nodes.get(node_id)
        if node and _set_widget(wf, node, sampler_index, "dpmpp_3m_sde_gpu", "dpmpp_2m"):
            _set_widget(wf, node, sampler_index + 1, "sgm_uniform", "karras")
            changed.append(node_id)
    return changed


def fix_illustrious_v2(wf: dict) -> list:
    node = next((n for n in wf.get("nodes", []) if n.get("id") == 3 and n.get("type") == "KSampler"), None)
    if node and node["widgets_values"][2:4] == [180, 69]:
        _set_widget(wf, node, 2, 180, 30)
        _set_widget(wf, node, 3, 69, 6.5)
        return [3]
    return []


def fix_multi_checkpoint(wf: dict) -> list:
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    encode, sampler, source = nodes.get(18), nodes.get(19), nodes.get(37)
    slot = next((k for k, i in enumerate(sampler["inputs"]) if i["name"] == "latent_image"), None) if sampler else None
    if not (encode and source and slot is not None) or encode["outputs"][0].get("links"):
        return []
    old = sampler["inputs"][slot]["link"]
    link = next((l for l in wf["links"] if l[0] == old), None)
    if link is None or link[1] != 37:
        return []
    link[1], link[2] = 18, 0  # same link id, now from the stage-2 VAE Encode
    source["outputs"][0]["links"] = [x for x in source["outputs"][0]["links"] if x != old]
    encode["outputs"][0]["links"] = [old]
    for node_id, before, after in ((18, "(LATENT, 0 Verbindung(en))", "(LATENT, 1 Verbindung(en))"),
                                   (37, "(LATENT, 3 Verbindung(en))", "(LATENT, 2 Verbindung(en))")):
        note = _note_for(wf, node_id)
        if note is not None:
            note["widgets_values"] = [note["widgets_values"][0].replace(before, after)]
    return [19]


LTX_DECODE = {  # rel: (node id, subgraph id or None, old values, new values)
    "Text to Video/LTX23_dev_Q8_GGUF-Text-to-Video.json": (12, None, [512, 64, 32, 8], [384, 64, 32, 8]),
    "Text to Video/LTX23_dev_mxfp8-Text-to-Video.json": (12, None, [512, 64, 32, 8], [384, 64, 32, 8]),
    "Text to Video/LTX23_distilled_fp8-Text-to-Video.json": (13, None, [512, 64, 32, 8], [384, 64, 32, 8]),
    "Text to Video/LTX23_distilled_mxfp8-Text-to-Video.json": (13, None, [512, 64, 32, 8], [384, 64, 32, 8]),
    "Text+Image to Video/LTX23-Image-to-Video.json": (315, "2454ad83-157c-40dd-9f19-5daaf4041ce0",
                                                      [768, 64, 4096, 4], [384, 64, 32, 8]),
}
LTX_MXFP8 = "Text to Video/LTX23_dev_mxfp8-Text-to-Video.json"
BERNINI_IMAGE = "Image Editing/Bernini_R-Image-Edit.json"
T5_WRONG = "T5" + chr(92) + "t5xxl_fp8_e4m3fn_scaled.safetensors"
UMT5 = "UMT5" + chr(92) + "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
DECODE_NAMES = ("tile_size", "overlap", "temporal_size", "temporal_overlap")


def _graph(wf: dict, subgraph: str | None) -> dict | None:
    if subgraph is None:
        return wf
    return next((g for g in (wf.get("definitions") or {}).get("subgraphs") or [] if g.get("id") == subgraph), None)


def _note_in(graph: dict, node_id) -> dict | None:
    return next((n for n in graph.get("nodes", []) if n.get("type") in ("MarkdownNote", "Note")
                 and (n.get("properties") or {}).get("dawasteh_note_for") == node_id), None)


def fix_ltx_decode(rel: str, wf: dict) -> list:
    node_id, subgraph, old, new = LTX_DECODE[rel]
    graph = _graph(wf, subgraph)
    node = next((n for n in (graph or {}).get("nodes", []) if n.get("id") == node_id), None)
    if node is None or node.get("type") != "VAEDecodeTiled" or node.get("widgets_values") != old:
        return []
    node["widgets_values"] = list(new)
    note = _note_in(graph, node_id)
    if note is not None:
        text = note["widgets_values"][0]
        for name, before, after in zip(DECODE_NAMES, old, new):
            text = text.replace(f"`{name}` = `{before}`", f"`{name}` = `{after}`")
        note["widgets_values"] = [text]
    return [node_id]


ROLES = ("model_device", "clip_device", "vae_device")


def resplit_devices(wf: dict, old: list, new: list, reason: str) -> list:
    node = next((n for n in wf.get("nodes", []) if n.get("type") == "DaWMultiGPUDeviceControl"), None)
    if node is None or node.get("widgets_values") != old:
        return []
    node["widgets_values"] = list(new)
    gpu = (wf.get("extra") or {}).get("dawasteh_dual_gpu")
    if isinstance(gpu, dict):  # the documented defaults follow the control (the curated v0.9.2 split no longer fits)
        gpu["defaults"] = dict(zip(("MODEL", "CLIP", "VAE"), new))
        gpu["manual_device_dropdowns"] = dict(zip(ROLES, new))
        gpu["curated_split_default"] = False
        gpu["v131_resplit"] = reason
    note = _note_for(wf, node["id"])
    if note is not None:
        text = note["widgets_values"][0]
        for name, before, after in zip(ROLES, old, new):
            text = text.replace(f"`{name}` = `{before}`", f"`{name}` = `{after}`")
        note["widgets_values"] = [text]
    return [node["id"]]


def fix_ltx_mxfp8_devices(wf: dict) -> list:
    return resplit_devices(wf, ["gpu:0", "gpu:1", "gpu:1"], ["gpu:0", "gpu:0", "gpu:0"],
                           "Gemma 3 12B needs 25 GB loaded: text encoder and VAE back on the R9700")


KANDINSKY = "Text+Image to Video/Kandinsky5_Lite-Text+Image-to-Video.json"


def fix_kandinsky_vae_device(wf: dict) -> list:
    return resplit_devices(wf, ["gpu:0", "gpu:1", "gpu:1"], ["gpu:0", "gpu:1", "gpu:0"],
                           "the Qwen 2.5 VL text encoder keeps 9.5 GiB on the second GPU: VAE decode on the R9700")


def fix_bernini_encoder(wf: dict) -> list:
    changed = []
    for graph in [wf, *((wf.get("definitions") or {}).get("subgraphs") or [])]:
        for node in graph.get("nodes", []):
            if node.get("type") == "CLIPLoader" and (node.get("widgets_values") or [None])[0] == T5_WRONG:
                node["widgets_values"][0] = UMT5
                note = _note_in(graph, node["id"])
                if note is not None:
                    note["widgets_values"] = [note["widgets_values"][0].replace(T5_WRONG, UMT5)]
                changed.append(node["id"])
    for node in wf.get("nodes", []):  # subgraph instances pass clip_name in and override the inner loader
        values = node.get("widgets_values")
        if isinstance(values, list) and T5_WRONG in values:
            node["widgets_values"] = [UMT5 if v == T5_WRONG else v for v in values]
            changed.append(node["id"])
    return changed


IDEOGRAM_FIELDS = "Prompt Tools/Ideogram4_Qwen3_5-Field-Text-Builder.json"
SAVE_TEXT_OLD = "H:" + chr(92) + "ComfyUI" + chr(92) + "ComfyUI" + chr(92) + "output" + chr(92) + "prompts" + chr(92)
SAVE_TEXT_NEW = "output/prompts/"


def fix_save_text_path(wf: dict) -> list:
    changed = []
    for node in wf.get("nodes", []):
        values = node.get("widgets_values")
        if node.get("type") == "easy saveText" and isinstance(values, list) and values and values[0] == SAVE_TEXT_OLD:
            values[0] = SAVE_TEXT_NEW
            note = _note_for(wf, node["id"])
            if note is not None:
                note["widgets_values"] = [note["widgets_values"][0].replace(SAVE_TEXT_OLD, SAVE_TEXT_NEW)]
            changed.append(node["id"])
    return changed


KLEIN_BASE = "Text to Image/FLUX2_Klein_base_4b-Text-to-Image.json"
KLEIN_BASE_CFG = 5.0
KLEIN_BASE_NEGATIVE_TITLE = "Negativ (leer, CFG 5)"
KLEIN_BASE_NEGATIVE_NOTE = (
    "# Erklärung · {title} · Node 4\n\n"
    "**Zweck:** Leerer Negativ-Prompt über denselben Text-Encoder. Seit v1.3.1 statt ConditioningZeroOut: das "
    "Base-Modell ist nicht destilliert und braucht echtes CFG; als „unbedingt“ kennt es den leeren Prompt, nicht eine "
    "genullte Konditionierung (wie die offizielle ComfyUI-Vorlage für Klein Base).\n\n"
    "**Einstellbare Werte**\n"
    "- `text` = `` — Negativ-Prompt. Leer lassen ist der Normalfall; Begriffe hier drängt CFG aus dem Bild.\n\n"
    "**Eingänge**\n"
    "- `clip` (CLIP, Link {link}): Qwen3-4B-Text-Encoder\n"
    "- `text` (STRING, nicht verbunden): Negativ-Text\n\n"
    "**Ausgänge**\n"
    "- `CONDITIONING` (CONDITIONING, 1 Verbindung(en)): negative Konditionierung für den KSampler"
)
KLEIN_BASE_SETTINGS = ("CFG: 1.0, Negativ leer.", "CFG: 5 (undestilliert: echtes CFG wie in der offiziellen ComfyUI-Vorlage), "
                       "Negativ: leerer Text-Encode.")


def fix_klein_base(wf: dict) -> list:
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    neg, pos, sampler, clip_dev = nodes.get(4), nodes.get(3), nodes.get(6), nodes.get(26)
    if not (neg and neg.get("type") == "ConditioningZeroOut" and sampler and sampler.get("type") == "KSampler"
            and pos and clip_dev and clip_dev.get("type") == "SelectCLIPDevice"):
        return []
    link_id = neg["inputs"][0]["link"]  # positive -> zero out; becomes clip selector -> negative text encode
    link = next(l for l in wf["links"] if l[0] == link_id)
    link[1:6] = [26, 0, 4, 0, "CLIP"]
    pos["outputs"][0]["links"] = [i for i in pos["outputs"][0]["links"] if i != link_id]
    clip_dev["outputs"][0]["links"] = [*clip_dev["outputs"][0]["links"], link_id]
    neg.update({"type": "CLIPTextEncode", "title": KLEIN_BASE_NEGATIVE_TITLE, "widgets_values": [""],
                "inputs": [{"localized_name": "clip", "name": "clip", "type": "CLIP", "link": link_id},
                           {"localized_name": "text", "name": "text", "type": "STRING", "widget": {"name": "text"},
                            "link": None}]})
    neg["properties"]["Node name for S&R"] = "CLIPTextEncode"
    sampler["widgets_values"][3] = KLEIN_BASE_CFG
    note = _note_for(wf, 4)
    if note is not None:
        note["title"] = f"Erklärung · {KLEIN_BASE_NEGATIVE_TITLE} · Node 4"
        note["widgets_values"] = [KLEIN_BASE_NEGATIVE_NOTE.format(title=KLEIN_BASE_NEGATIVE_TITLE, link=link_id)]
    note = _note_for(wf, 6)
    if note is not None:
        note["widgets_values"] = [note["widgets_values"][0].replace("- `cfg` = `1` —", "- `cfg` = `5` — Base-Modell "
                                                                    "(undestilliert): echtes CFG, 4–6 üblich.")]
    for node_id in (3, 26):
        note = _note_for(wf, node_id)
        if note is not None:
            refresh_note(note, nodes[node_id], wf)
    for n in wf["nodes"]:
        if n.get("type") in ("Note", "MarkdownNote") and KLEIN_BASE_SETTINGS[0] in n["widgets_values"][0]:
            n["widgets_values"] = [n["widgets_values"][0].replace(*KLEIN_BASE_SETTINGS)]
    return [4, 6]


IDEOGRAM_T2I = "Text to Image/Ideogram4-Text-to-Image.json"
IDEOGRAM_SAMPLING = {  # rel: scheduler, sampler select, CFG override, model sampling, resolution node (or None)
    IDEOGRAM_T2I: (12, 11, 4, 3, None),
    IDEOGRAM_AUTO: (190, 163, 184, 198, 191),
}
IDEOGRAM_SCHEDULER = [20, 1024, 1024, 0.0, 1.75]  # the official template's "Default" preset (V4_DEFAULT_20)
IDEOGRAM_SCHEDULER_TITLE = "Ideogram 4 Scheduler (20 Schritte)"
IDEOGRAM_SCHEDULER_NOTE = (
    "# Erklärung · {title} · Node {id}\n\n"
    "**Zweck:** Rauschplan von Ideogram 4 (Logit-Normal-Zeitplan mit Auflösungsterm), wie in der offiziellen "
    "ComfyUI-Vorlage. Seit v1.3.1 statt BasicScheduler karras/28 mit res_2m: dieser Plan passt nicht zu dem "
    "Flow-Modell und hinterließ ein Raster-/Krakelee-Muster über dem ganzen Bild, unscharfe Flächen und unleserliche "
    "kleine Schrift.\n\n"
    "**Einstellbare Werte**\n"
    "- `steps` = `20` — Preset „Default“. „Quality“: 48 Schritte, mu 0, std 1,5; „Turbo“: 12 Schritte, mu 0,5, "
    "std 1,75.\n"
    "- `width` / `height` = `1024` — {size}\n"
    "- `mu` = `0` — Verschiebung des Plans (Preset-Wert).\n"
    "- `std` = `1.75` — Streuung des Plans.\n\n"
    "**Eingänge**\n"
    "- `steps` (INT, nicht verbunden): Schritte\n"
    "- `width` (INT, {width_link}): Bildbreite\n"
    "- `height` (INT, {height_link}): Bildhöhe\n"
    "- `mu` (FLOAT, nicht verbunden): Verschiebung\n"
    "- `std` (FLOAT, nicht verbunden): Streuung\n\n"
    "**Ausgänge**\n"
    "- `SIGMAS` (SIGMAS, {n_out} Verbindung(en)): Rauschplan für den Sampler"
)
IDEOGRAM_SETTINGS = [
    ("Steps: 25-28.", "Steps: 20 (Ideogram4Scheduler, Preset „Default“; „Quality“ 48 Schritte, mu 0, std 1,5)."),
    ("CFGOverride: 3 / 0.9 / 1.", "CFGOverride: 3 / 0.7 / 1."),
    ("Sampler: res_2m.", "Sampler: euler."),
    ("Scheduler: karras.", "Scheduler: Ideogram4Scheduler wie in der offiziellen Vorlage (karras hinterließ ein Raster-Muster)."),
    ("ModelSamplingAuraFlow shift: 5.", "ModelSamplingAuraFlow shift: 1 (nativ; den Zeitplan liefert der Scheduler)."),
]


def _swap_value(wf: dict, node: dict, old: str, new: str, title_old: str = "", title_new: str = "") -> None:
    note = _note_for(wf, node["id"])
    if note is not None:
        text = note["widgets_values"][0].replace(old, new)
        if title_old:
            text = text.replace(title_old, title_new)
            note["title"] = note["title"].replace(title_old, title_new)
        note["widgets_values"] = [text]
    if title_old and node.get("title"):
        node["title"] = node["title"].replace(title_old, title_new)


def fix_ideogram_sampling(rel: str, wf: dict) -> list:
    sched_id, sampler_id, cfg_id, aura_id, size_id = IDEOGRAM_SAMPLING[rel]
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    sched = nodes.get(sched_id)
    if sched is None or sched.get("type") != "BasicScheduler" or sched.get("widgets_values") != ["karras", 28, 1]:
        return []
    model_link = sched["inputs"][0]["link"]
    link = next(l for l in wf["links"] if l[0] == model_link)
    nodes[link[1]]["outputs"][link[2]]["links"].remove(model_link)
    size = [None, None]
    if size_id is None:
        wf["links"].remove(link)
    else:  # the latent size comes from the resolution node; the scheduler's resolution term needs the same size
        link[1:6] = [size_id, 0, sched_id, 1, "INT"]
        wf["last_link_id"] += 1
        wf["links"].append([wf["last_link_id"], size_id, 1, sched_id, 2, "INT"])
        size = [model_link, wf["last_link_id"]]
        for slot, link_id in enumerate(size):
            nodes[size_id]["outputs"][slot]["links"].append(link_id)
    widget = lambda name, kind, link_id=None: {"localized_name": name, "name": name, "type": kind,
                                                "widget": {"name": name}, "link": link_id}
    sched.update({"type": "Ideogram4Scheduler", "title": IDEOGRAM_SCHEDULER_TITLE,
                  "widgets_values": list(IDEOGRAM_SCHEDULER),
                  "inputs": [widget("steps", "INT"), widget("width", "INT", size[0]), widget("height", "INT", size[1]),
                             widget("mu", "FLOAT"), widget("std", "FLOAT")]})
    sched["properties"]["Node name for S&R"] = "Ideogram4Scheduler"
    note = _note_for(wf, sched_id)
    if note is not None:
        linked = size_id is not None
        note["title"] = f"Erklärung · {IDEOGRAM_SCHEDULER_TITLE} · Node {sched_id}"
        note["widgets_values"] = [IDEOGRAM_SCHEDULER_NOTE.format(
            title=IDEOGRAM_SCHEDULER_TITLE, id=sched_id,
            size=("kommt vom Auflösungs-Node, wie beim Latent." if linked else
                  "muss zur Latent-Größe passen; bei anderer Bildgröße beide Werte mit ändern."),
            width_link=f"Link {size[0]}" if linked else "nicht verbunden",
            height_link=f"Link {size[1]}" if linked else "nicht verbunden",
            n_out=len(sched["outputs"][0].get("links") or []))]
    nodes[sampler_id]["widgets_values"] = ["euler"]
    _swap_value(wf, nodes[sampler_id], "`sampler_name` = `res_2m`", "`sampler_name` = `euler`", "(res_2m)", "(euler)")
    nodes[cfg_id]["widgets_values"][1] = 0.7
    _swap_value(wf, nodes[cfg_id], "`start_percent` = `0.9`", "`start_percent` = `0.7`")
    nodes[aura_id]["widgets_values"] = [1.0]
    _swap_value(wf, nodes[aura_id], "`shift` = `5`", "`shift` = `1`", "(shift 5)", "(shift 1)")
    for node_id in {link[1] for link in wf["links"] if link[3] == sched_id} | {aura_id}:
        note = _note_for(wf, node_id)
        if note is not None:
            refresh_note(note, nodes[node_id], wf)
    for n in wf["nodes"]:
        if n.get("type") in ("Note", "MarkdownNote") and not (n.get("properties") or {}).get("dawasteh_note_for"):
            text = n["widgets_values"][0]
            for old, new in IDEOGRAM_SETTINGS:
                text = text.replace(old, new)
            n["widgets_values"] = [text]
    return [sched_id, sampler_id, cfg_id, aura_id]


AUDIOREACT = "Audio to Video/FLUX2_Klein_4B_Gemma4-Audio-Context-to-AudioReact-Video.json"
UNLOAD_OLD = ("- `unload_all_models` = `True` — Steuert diesen Parameter. AN gibt Modell-/VRAM-Speicher nach dem Lauf frei, "
              "macht den nächsten Lauf aber langsamer; AUS hält das Modell für Wiederholungen im Cache.")
UNLOAD_NEW = ("- `unload_all_models` = `False` — Seit v1.3.1 AUS: Entladen schiebt FLUX.2 Klein, Qwen3 4B und Gemma 4 "
              "zurück in den Arbeitsspeicher (rund 14 GiB). Genau dort legt die Pixaroma-Audio-Engine alle Frames ab "
              "(8 s bei 1024×1024 ≈ 2,2 GB) und bricht ab, wenn zu wenig RAM frei ist. Sie rendert Frame für Frame "
              "auf der GPU und braucht dafür kaum VRAM. AN nur, wenn die GPU für den VAE-Decode zu knapp ist.")


def fix_audioreact_unload(wf: dict) -> list:
    node = next((n for n in wf.get("nodes", []) if n.get("id") == 34), None)
    if node is None or node.get("type") != "VRAM_Debug" or node.get("widgets_values") != [True, True, True]:
        return []
    node["widgets_values"] = [True, True, False]
    note = _note_for(wf, 34)
    if note is not None:
        note["widgets_values"] = [note["widgets_values"][0].replace(UNLOAD_OLD, UNLOAD_NEW)]
    return [34]


ANGLES = "Image Editing/Multi-Character-Angles-One-Click.json"
MMAUDIO = "Video to Audio/MMAudio_Video-to-Audio.json"
MMAUDIO_INFO_TITLE = "Video-Info · fps und Dauer"
MMAUDIO_INFO_NOTE = (
    "# Erklärung · {title} · Node {id}\n\n"
    "**Zweck:** Liest Bildrate und Länge des geladenen Videos (nach `force_rate`, `frame_load_cap` und "
    "`skip_first_frames` des Video-Loaders). Seit v1.3.1 bekommen der MMAudio Sampler und die Video-Ausgabe beide "
    "Werte automatisch: vorher standen fest 8 Sekunden und 8 fps im Workflow; bei jedem anderen Video saß der Ton "
    "nicht auf dem Bild, und ein 16-fps-Video lief halb so schnell, der Ton endete nach der Hälfte.\n\n"
    "**Einstellbare Werte**\n"
    "- Keine; alles kommt aus dem Video-Loader.\n\n"
    "**Eingänge**\n"
    "- `video_info` (VHS_VIDEOINFO, Link {info_link}): Angaben des Nodes „Eingangs-Video“\n\n"
    "**Ausgänge**\n"
    "- `fps🟦` (FLOAT, 1 Verbindung(en)): Bildrate → `frame_rate` von „Video+Audio kombinieren“\n"
    "- `frame_count🟦` (INT, nicht verbunden): Anzahl der geladenen Frames\n"
    "- `duration🟦` (FLOAT, 1 Verbindung(en)): Länge in Sekunden → `duration` des MMAudio Samplers\n"
    "- `width🟦`, `height🟦` (INT, nicht verbunden): Bildgröße"
)


def _input(node: dict, name: str) -> dict | None:
    return next((i for i in node.get("inputs", []) if i.get("name") == name), None)


def fix_mmaudio(wf: dict) -> list:
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    load, sampler, combine = nodes.get(3), nodes.get(4), nodes.get(6)
    if not (load and sampler and combine and load["type"] == "VHS_LoadVideo" and sampler["type"] == "MMAudioSuiteSampler"
            and combine["type"] == "VHS_VideoCombine"):
        return []
    duration, frame_rate = _input(sampler, "duration"), _input(combine, "frame_rate")
    if duration is None or frame_rate is None or duration.get("link") is not None or frame_rate.get("link") is not None:
        return []
    info_id, note_id = wf["last_node_id"] + 1, wf["last_node_id"] + 2
    info_link, fps_link, duration_link = wf["last_link_id"] + 1, wf["last_link_id"] + 2, wf["last_link_id"] + 3
    wf["last_node_id"], wf["last_link_id"] = note_id, duration_link
    wf["links"] += [[info_link, 3, 3, info_id, 0, "VHS_VIDEOINFO"],
                    [fps_link, info_id, 0, 6, combine["inputs"].index(frame_rate), "FLOAT"],
                    [duration_link, info_id, 2, 4, sampler["inputs"].index(duration), "FLOAT"]]
    load["outputs"][3]["links"] = [info_link]
    frame_rate["link"], duration["link"] = fps_link, duration_link
    order = max(n.get("order", 0) for n in wf["nodes"]) + 1
    wf["nodes"].append({
        "id": info_id, "type": "VHS_VideoInfoLoaded", "title": MMAUDIO_INFO_TITLE, "pos": list(load["pos"]),
        "size": [300, 150], "flags": {}, "order": order, "mode": 0,
        "inputs": [{"localized_name": "video_info", "name": "video_info", "type": "VHS_VIDEOINFO", "link": info_link}],
        "outputs": [{"localized_name": "fps🟦", "name": "fps🟦", "type": "FLOAT", "links": [fps_link]},
                    {"localized_name": "frame_count🟦", "name": "frame_count🟦", "type": "INT", "links": None},
                    {"localized_name": "duration🟦", "name": "duration🟦", "type": "FLOAT", "links": [duration_link]},
                    {"localized_name": "width🟦", "name": "width🟦", "type": "INT", "links": None},
                    {"localized_name": "height🟦", "name": "height🟦", "type": "INT", "links": None}],
        "properties": {"Node name for S&R": "VHS_VideoInfoLoaded", "cnr_id": "comfyui-videohelpersuite"},
        "widgets_values": {},
    })
    wf["nodes"].append({
        "id": note_id, "type": "MarkdownNote", "title": f"Erklärung · {MMAUDIO_INFO_TITLE} · Node {info_id}",
        "pos": list(load["pos"]), "size": [390, 400], "flags": {}, "order": order + 1, "mode": 0,
        "inputs": [], "outputs": [],
        "properties": {"Node name for S&R": "MarkdownNote", "cnr_id": "comfy-core", "dawasteh_note_for": info_id,
                       "dawasteh_generated_note": True},
        "widgets_values": [MMAUDIO_INFO_NOTE.format(title=MMAUDIO_INFO_TITLE, id=info_id, info_link=info_link)],
    })
    for node_id, name, link, text in (
            (4, "duration", duration_link, "Länge des geladenen Videos aus „Video-Info“; der Sampler verteilt das "
                                            "ganze Video auf diese Dauer"),
            (6, "frame_rate", fps_link, "Bildrate des geladenen Videos aus „Video-Info“, damit Bild und Ton gleich "
                                         "lang sind")):
        note = _note_for(wf, node_id)
        if note is None:
            continue
        lines = []
        for line in note["widgets_values"][0].split("\n"):
            if line.startswith(f"- `{name}` = "):
                line = f"- `{name}` — seit v1.3.1 verbunden: {text}."
            elif line.startswith(f"- `{name}` ("):
                line = f"- `{name}` (FLOAT, Link {link}): {text}"
            lines.append(line)
        note["widgets_values"] = ["\n".join(lines)]
    refinement = (wf.get("extra") or {}).get("dawasteh_workflow_refinement")
    if isinstance(refinement, dict) and "generated_notes" in refinement:
        refinement["generated_notes"] += 1
    return [info_id, note_id, 4, 6]


META_BATCH = ("Pose & Depth/SDPose-Pose-from-Video.json", "Pose & Depth/DepthAnything3-Depth-from-Video.json")


def fix_meta_batch(wf: dict) -> list:
    changed = []
    for node in wf.get("nodes", []):
        values = node.get("widgets_values")
        if node.get("type") == "VHS_BatchManager" and isinstance(values, list) and len(values) == 1:
            node["widgets_values"] = {"frames_per_batch": values[0], "count": 0}
            changed.append(node["id"])
    return changed


def apply(rel: str, wf: dict) -> list:
    """Repair workflow ``rel`` (v1.3.0 path) in place; returns the changed node ids."""
    changed = []
    if rel in DECODE_TARGETS and tile_decode(wf, *DECODE_TARGETS[rel]):
        changed.append(DECODE_TARGETS[rel][0])
        apply_rodent_layout(wf, new_key(rel))  # the taller node pushes CreateVideo/SaveVideo down (RODENT grid)
    if rel in ENCODER_TARGETS and fix_encoder(wf, ENCODER_TARGETS[rel]):
        changed.append(ENCODER_TARGETS[rel])
    if rel == WAN_T2V:
        changed += fix_wan_t2v(wf)
    if rel in IDEOGRAM_OPTIONAL_SKETCH:
        ideogram = fix_ideogram(rel, wf)
        changed += ideogram
        if 185 in ideogram:
            apply_rodent_layout(wf, new_key(rel))  # a new link changes the RODENT stage order
    if rel == IPADAPTER:
        changed += fix_ipadapter(wf)
    if rel == ILLUSTRIOUS_V2:
        changed += fix_illustrious_v2(wf)
    if rel == MULTI_CHECKPOINT:
        chain = fix_multi_checkpoint(wf)
        changed += chain
        if chain:
            apply_rodent_layout(wf, new_key(rel))  # a moved link changes the RODENT stage order
    if rel in LTX_DECODE:
        changed += fix_ltx_decode(rel, wf)
    if rel == LTX_MXFP8:
        changed += fix_ltx_mxfp8_devices(wf)
    if rel == KANDINSKY:
        changed += fix_kandinsky_vae_device(wf)
    if rel == BERNINI_IMAGE:
        changed += fix_bernini_encoder(wf)
    if rel in META_BATCH:
        changed += fix_meta_batch(wf)
    if rel == ANGLES:
        angles = restructure_angles(wf)
        changed += angles
        if angles:
            apply_rodent_layout(wf, new_key(rel))  # moved nodes and new links change the RODENT stage order
    if rel == IDEOGRAM_FIELDS:
        changed += fix_save_text_path(wf)
    if rel in IDEOGRAM_SAMPLING:
        sampling = fix_ideogram_sampling(rel, wf)
        changed += sampling
        if sampling:
            apply_rodent_layout(wf, new_key(rel))  # removed and new links change the RODENT stage order
    if rel == AUDIOREACT:
        changed += fix_audioreact_unload(wf)
    if rel == KLEIN_BASE:
        klein = fix_klein_base(wf)
        changed += klein
        if klein:
            apply_rodent_layout(wf, new_key(rel))  # a moved link changes the RODENT stage order
    if rel == MMAUDIO:
        mmaudio = fix_mmaudio(wf)
        changed += mmaudio
        if mmaudio:
            apply_rodent_layout(wf, new_key(rel))  # a new node and new links change the RODENT stage order
    if rel == KONTEXT and fix_kontext(wf):
        changed.append(10)
        apply_rodent_layout(wf, new_key(rel))  # a new link changes the RODENT stage order
    if changed:
        refresh_topology_hashes(wf)  # the RODENT marker pins node types and widget values
    return changed


def main() -> int:
    check = "--check" in sys.argv
    renames = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
    pending = 0
    for rel in [*DECODE_TARGETS, *ENCODER_TARGETS, KONTEXT, WAN_T2V, *IDEOGRAM_OPTIONAL_SKETCH, IPADAPTER, ILLUSTRIOUS_V2, MULTI_CHECKPOINT, *LTX_DECODE, BERNINI_IMAGE, *META_BATCH, MMAUDIO, ANGLES,
                AUDIOREACT, KLEIN_BASE, IDEOGRAM_T2I]:
        path = WF / rel if (WF / rel).exists() else WF / renames.get(rel, rel)
        wf = json.loads(path.read_text(encoding="utf-8"))
        changed = apply(rel, wf)
        pending += len(changed)
        if changed and not check:
            path.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("repaired", path.relative_to(WF).as_posix(), changed)
    manifest = json.loads(PROMPT_MANIFEST.read_text(encoding="utf-8"))
    if sync_prompt_manifest(manifest):
        pending += 1
        if not check:  # same one-line style as tools/integrate_pixaroma_prompts.py writes
            PROMPT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n",
                                       encoding="utf-8")
            print("updated", PROMPT_MANIFEST.relative_to(ROOT).as_posix())
    return 1 if (check and pending) else 0


if __name__ == "__main__":
    raise SystemExit(main())
