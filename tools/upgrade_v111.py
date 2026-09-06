#!/usr/bin/env python3
"""v1.1.1 deterministic workflow migration (RDNA4 performance pass, performance/rdna4/REPORT.md).

Applies, idempotently, to the v1.1.0 collection:

  B1  WAN 2.2 I2V 14B graphs (3): Wan22ImageToVideoLatent (48-ch, 5B VAE) -> WanImageToVideo + wan_2.1_vae
  B2  TrainLoraNode graphs (5): insert the missing ``control_after_generate`` value after ``seed``
  E1  VRAM_Debug.unload_all_models -> False in image/audio categories (measured: Z-Image Turbo 15.6 -> 8.2 s,
      ACE-Step 41.6 -> 30.4 s, outputs bit-identical); video/3D/live categories keep the barrier
  E2  14 image workflows: CLIP/VAE from gpu:1 to gpu:0 (deep-clone + dead-model GC avoided)
  E2b 3 LTX-2.5 workflows: CLIP to gpu:0, VAE stays on gpu:1 (cold 548 -> 152 s)

Every migrated file carries ``extra[MARKER_KEY] = {"version": MARKER_VERSION}`` so that
``tools/validate_workflows.py --against-head --baseline-ref v1.1.0`` can rebuild it from the previous release.

  python tools/upgrade_v111.py --check     # verify workflows/ == apply(HEAD files)
  python tools/upgrade_v111.py --apply     # rewrite workflows/ in place
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / "workflows"
MARKER_KEY = "dawasteh_rdna4_v111"
MARKER_VERSION = 1

WAN_I2V = {
    "Text+Image to Video/WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json",
    "Text+Image to Video/WAN22_i2v_14B_Q8_GGUF_lightx2v-Text+Image-to-Video.json",
    "Text+Image to Video/WAN22_bernini_i2v-Text+Image-to-Video.json",
}
TRAIN = {
    "LoRA Generation/Boogu_Image_Base-LoRA-Training.json",
    "LoRA Generation/FLUX1_Dev-LoRA-Training.json",
    "LoRA Generation/FLUX2_Klein_4B_Base-LoRA-Training.json",
    "LoRA Generation/SDXL-LoRA-Training.json",
    "LoRA Generation/ZImage_Base-LoRA-Training.json",
}
E1_CATEGORIES = {
    "Audio to Image", "Batch Processing", "Character & Consistency", "Image Editing", "Image Fusion",
    "Image Inpainting", "Image Outpainting", "Image Upscaling", "Image Utilities", "Music Generation", "NSFW",
    "Pixaroma Node Demos", "Prompt Tools", "Templates & Tests", "Text to Image",
}  # "Prompt Enhancer" is generator-managed (tools/generate_*_enhancer*.py) and stays untouched
# integrity-guarded by tools/consolidate_ace_autosongwriters_v093.py; left untouched
E1_EXCLUDE = {
    "Music Generation/ACE-Step1_5_XL_SFT_Gemma4_e4B-AutoSongwriter-Genre-Selector.json",
    "Music Generation/ACE-Step1_5_XL_SFT_Qwen3_5_4B-AutoSongwriter-Genre-Selector.json",
}
E2_IMAGE = {
    "Image Editing/Bernini_R-Image-Edit.json",
    "Image Editing/Qwen_Image_Edit_2509-Image-Edit.json",
    "Text to Image/Anima_base_v1-Text-to-Image.json",
    "Text to Image/Boogu_image_base-Text-to-Image.json",
    "Text to Image/FLUX1_dev_fp8-Text-to-Image.json",
    "Text to Image/FLUX2_Klein_4b-Text-to-Image.json",
    "Text to Image/FLUX2_dev_fp8mixed-Text-to-Image.json",
    "Text to Image/Ideogram4-Text-to-Image.json",
    "Text to Image/Krea2_raw-Text-to-Image.json",
    "Text to Image/LongCat_image-Text-to-Image.json",
    "Text to Image/SD15_v1-5-pruned-emaonly-Text-to-Image.json",
    "Text to Image/SD21_wd-1-5-beta2-unclip-Text-to-Image.json",
    "Text to Image/SDXL_RealVisXL_V4-Text-to-Image.json",
    "Text to Image/ZImage_turbo-Text-to-Image.json",
}
E2B_LTX = {
    "Text to Video/LTX25_INT8_ConvRot-Text-to-Video.json",
    "Text+Image to Video/LTX25_INT8_ConvRot-Image-to-Video.json",
    "Text+Image to Video/LTX25_INT8_ConvRot-First+Last-Frame-to-Video.json",
}


def _graphs(wf: dict):
    yield wf
    for sg in wf.get("definitions", {}).get("subgraphs", []) or []:
        yield sg


def fix_wan_i2v(wf: dict) -> bool:
    lat = [n for n in wf["nodes"] if n["type"] == "Wan22ImageToVideoLatent"]
    if not lat:
        return False
    lat = lat[0]
    nodes = {n["id"]: n for n in wf["nodes"]}
    links = {l[0]: l for l in wf["links"]}
    for n in wf["nodes"]:
        if n["type"] == "VAELoader":
            wv = n.get("widgets_values") or []
            if wv and "wan2.2_vae" in str(wv[0]):
                wv[0] = "WAN\\wan_2.1_vae.safetensors"
    consumers = [(links[lid][3], links[lid][4]) for lid in (lat["outputs"][0].get("links") or [])]
    first = nodes[consumers[0][0]]

    def link_src(node, name):
        for i in node["inputs"]:
            if i["name"] == name and i.get("link") is not None:
                l = links[i["link"]]
                return l[1], l[2]
        return None

    pos_src, neg_src = link_src(first, "positive"), link_src(first, "negative")
    next_link = max(links) + 1
    old_inputs = {i["name"]: i for i in lat["inputs"]}
    lat["type"] = "WanImageToVideo"
    lat["properties"]["Node name for S&R"] = "WanImageToVideo"
    new_inputs = []

    def add_input(name, typ, link=None, widget=False):
        d = {"name": name, "type": typ, "link": link}
        if widget:
            d["widget"] = {"name": name}
        new_inputs.append(d)

    lp = [next_link, pos_src[0], pos_src[1], lat["id"], 0, "CONDITIONING"]
    ln = [next_link + 1, neg_src[0], neg_src[1], lat["id"], 1, "CONDITIONING"]
    add_input("positive", "CONDITIONING", lp[0])
    add_input("negative", "CONDITIONING", ln[0])
    add_input("vae", "VAE", old_inputs["vae"]["link"])
    for name in ("width", "height", "length", "batch_size"):
        add_input(name, "INT", old_inputs.get(name, {}).get("link"), widget=True)
    add_input("clip_vision_output", "CLIPVISION_OUTPUT", None)
    add_input("start_image", "IMAGE", old_inputs["start_image"]["link"] if "start_image" in old_inputs else None)
    slot_of = {d["name"]: i for i, d in enumerate(new_inputs)}
    for d in new_inputs:
        if d["link"] is not None and d["link"] in links:
            links[d["link"]][3] = lat["id"]
            links[d["link"]][4] = slot_of[d["name"]]
    links[lp[0]] = lp
    links[ln[0]] = ln
    for src, slot, lid in ((pos_src[0], pos_src[1], lp[0]), (neg_src[0], neg_src[1], ln[0])):
        outs = nodes[src]["outputs"][slot]
        outs["links"] = list(outs.get("links") or []) + [lid]
    lat["inputs"] = new_inputs
    old_latent_links = list(lat["outputs"][0].get("links") or [])
    lat["outputs"] = [
        {"name": "positive", "type": "CONDITIONING", "links": []},
        {"name": "negative", "type": "CONDITIONING", "links": []},
        {"name": "latent", "type": "LATENT", "links": old_latent_links},
    ]
    for lid in old_latent_links:
        links[lid][2] = 2
    for n in wf["nodes"]:
        if n["type"] in ("KSamplerAdvanced", "KSampler"):
            for name, slot in (("positive", 0), ("negative", 1)):
                for i in n["inputs"]:
                    if i["name"] == name and i.get("link") is not None:
                        l = links[i["link"]]
                        if (l[1], l[2]) in (pos_src, neg_src):
                            nodes[l[1]]["outputs"][l[2]]["links"] = [x for x in nodes[l[1]]["outputs"][l[2]]["links"] if x != l[0]]
                            l[1], l[2] = lat["id"], slot
                            lat["outputs"][slot]["links"].append(l[0])
    wf["links"] = [links[k] for k in sorted(links)]
    wf["last_link_id"] = max(links)
    return True


def fix_train(wf: dict) -> bool:
    changed = False
    for n in wf["nodes"]:
        if n["type"] == "TrainLoraNode":
            wv = n["widgets_values"]
            names = [i["name"] for i in n["inputs"] if i.get("widget")]
            if len(wv) == len(names):
                wv.insert(names.index("seed") + 1, "fixed")
                changed = True
    return changed


def apply_e1(wf: dict) -> bool:
    changed = False
    for g in _graphs(wf):
        for node in g.get("nodes", []):
            if node.get("type") == "VRAM_Debug":
                wv = node.get("widgets_values")
                if isinstance(wv, list) and len(wv) >= 3 and wv[2] is True:
                    wv[2] = False
                    changed = True
    return changed


def set_control(wf: dict, values: list[str] | None, clip_only: bool = False) -> bool:
    changed = False
    for node in wf.get("nodes", []):
        if node.get("type") == "DaWMultiGPUDeviceControl":
            wv = node.get("widgets_values") or []
            if len(wv) != 3:
                continue
            new = [wv[0], "gpu:0", wv[2]] if clip_only else list(values)
            if list(wv) != new:
                node["widgets_values"] = new
                changed = True
            defaults = wf.get("extra", {}).get("dawasteh_dual_gpu", {}).get("defaults")
            if isinstance(defaults, dict):
                expected = {"MODEL": new[0], "CLIP": new[1], "VAE": new[2]}
                if defaults != expected:
                    defaults.update(expected)
                    changed = True
    return changed


def apply(wf: dict, rel: str) -> dict:
    """Return the v1.1.1 form of *wf* (already-migrated input is returned unchanged)."""
    wf = copy.deepcopy(wf)
    rel = rel.replace("\\", "/")
    category = rel.split("/")[0]
    touched = False
    if rel in WAN_I2V:
        if fix_wan_i2v(wf):
            touched = True
        # the rewired graph gets the deterministic RODENT layout (as migrate_workflow would produce)
        try:
            from tools.rodent_layout import apply_rodent_layout
        except ModuleNotFoundError:  # direct execution from tools/
            from rodent_layout import apply_rodent_layout
        before = copy.deepcopy(wf)
        apply_rodent_layout(wf, rel)
        touched |= wf != before
    if rel in TRAIN:
        touched |= fix_train(wf)
    if category in E1_CATEGORIES and rel not in E1_EXCLUDE:
        touched |= apply_e1(wf)
    if rel in E2_IMAGE:
        touched |= set_control(wf, ["gpu:0", "gpu:0", "gpu:0"])
    if rel in E2B_LTX:
        touched |= set_control(wf, None, clip_only=True)
    is_target = (
        rel in WAN_I2V or rel in TRAIN or rel in E2_IMAGE or rel in E2B_LTX
        or (category in E1_CATEGORIES and rel not in E1_EXCLUDE
            and any(n.get("type") == "VRAM_Debug" for g in _graphs(wf) for n in g.get("nodes", [])))
    )
    if touched or is_target:
        wf.setdefault("extra", {})[MARKER_KEY] = {"version": MARKER_VERSION}
        # keep the RODENT layout marker consistent with the (possibly changed) graph content
        try:
            from tools.rodent_layout import RODENT_KEY, _topology_hash
        except ModuleNotFoundError:  # direct execution from tools/
            from rodent_layout import RODENT_KEY, _topology_hash
        for g in _graphs(wf):
            marker = g.get("extra", {}).get(RODENT_KEY)
            if marker and marker.get("topology_sha256") != _topology_hash(g):
                marker["topology_sha256"] = _topology_hash(g)
    return wf


def targets() -> set[str]:
    out = set(WAN_I2V) | set(TRAIN) | set(E2_IMAGE) | set(E2B_LTX)
    for p in sorted(WORKFLOWS.glob("*/*.json")):
        rel = p.relative_to(WORKFLOWS).as_posix()
        if rel.split("/")[0] in E1_CATEGORIES and rel not in E1_EXCLUDE:
            wf = json.loads(p.read_text(encoding="utf-8"))
            if any(n.get("type") == "VRAM_Debug" for g in _graphs(wf) for n in g.get("nodes", [])):
                out.add(rel)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    changed = 0
    bad = []
    for p in sorted(WORKFLOWS.glob("*/*.json")):
        rel = p.relative_to(WORKFLOWS).as_posix()
        wf = json.loads(p.read_text(encoding="utf-8"))
        new = apply(wf, rel)
        if new != wf:
            if a.apply:
                p.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                changed += 1
            elif a.check:
                bad.append(rel)
    if a.check:
        print(f"{len(bad)} workflows not in v1.1.1 form" + (": " + ", ".join(bad[:5]) if bad else ""))
        return 1 if bad else 0
    print(f"{changed} workflows rewritten" if a.apply else "dry run (use --apply/--check)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
