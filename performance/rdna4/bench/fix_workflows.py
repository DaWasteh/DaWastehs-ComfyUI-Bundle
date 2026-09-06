"""Produce corrected copies of repo workflows found broken during the RDNA4 benchmark.

B1  WAN 2.2 14B I2V graphs: Wan22ImageToVideoLatent (48-ch, 5B VAE) -> WanImageToVideo (16-ch) + wan_2.1_vae
B2  TrainLoraNode graphs: insert the `control_after_generate` value after `seed` so frontend >= 1.5x
    does not shift every following widget by one.

Outputs go to performance/rdna4/workflows/<category>/<name>.json (originals untouched).
Run:  python bench/fix_workflows.py [--apply-to-repo]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "workflows"
DST = Path(__file__).resolve().parents[1] / "workflows"

WAN_I2V = [
    "Text+Image to Video/WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json",
    "Text+Image to Video/WAN22_i2v_14B_Q8_GGUF_lightx2v-Text+Image-to-Video.json",
    "Text+Image to Video/WAN22_bernini_i2v-Text+Image-to-Video.json",
]
TRAIN = [
    "LoRA Generation/Boogu_Image_Base-LoRA-Training.json",
    "LoRA Generation/FLUX1_Dev-LoRA-Training.json",
    "LoRA Generation/FLUX2_Klein_4B_Base-LoRA-Training.json",
    "LoRA Generation/SDXL-LoRA-Training.json",
    "LoRA Generation/ZImage_Base-LoRA-Training.json",
]


def fix_wan_i2v(wf: dict) -> list[str]:
    notes = []
    nodes = {n["id"]: n for n in wf["nodes"]}
    links = {l[0]: l for l in wf["links"]}  # id -> [id, from, from_slot, to, to_slot, type]
    lat = [n for n in wf["nodes"] if n["type"] == "Wan22ImageToVideoLatent"]
    if len(lat) != 1:
        raise RuntimeError(f"expected one Wan22ImageToVideoLatent, found {len(lat)}")
    lat = lat[0]
    for n in wf["nodes"]:
        if n["type"] == "VAELoader":
            wv = n.get("widgets_values") or []
            if wv and "wan2.2_vae" in str(wv[0]):
                wv[0] = "WAN\\wan_2.1_vae.safetensors"
                notes.append(f"VAELoader {n['id']}: wan2.2_vae -> wan_2.1_vae")
    # find sampler nodes consuming the latent, and their positive/negative sources
    latent_out_links = lat["outputs"][0].get("links") or []
    consumers = []
    for lid in latent_out_links:
        l = links[lid]
        consumers.append((l[3], l[4]))
    first_sampler = nodes[consumers[0][0]]
    def link_src(node, name):
        for i in node["inputs"]:
            if i["name"] == name and i.get("link") is not None:
                l = links[i["link"]]
                return l[1], l[2]
        return None
    pos_src = link_src(first_sampler, "positive")
    neg_src = link_src(first_sampler, "negative")
    if not pos_src or not neg_src:
        raise RuntimeError("could not resolve positive/negative sources")
    next_link = max(links) + 1
    # rebuild the latent node as WanImageToVideo
    old_inputs = {i["name"]: i for i in lat["inputs"]}
    lat["type"] = "WanImageToVideo"
    lat["properties"]["Node name for S&R"] = "WanImageToVideo"
    new_inputs = []
    def add_input(name, typ, link=None, widget=None):
        d = {"name": name, "type": typ, "link": link}
        if widget:
            d["widget"] = {"name": name}
        new_inputs.append(d)
    lp = [next_link, pos_src[0], pos_src[1], lat["id"], 0, "CONDITIONING"]; next_link += 1
    ln = [next_link, neg_src[0], neg_src[1], lat["id"], 1, "CONDITIONING"]; next_link += 1
    add_input("positive", "CONDITIONING", lp[0])
    add_input("negative", "CONDITIONING", ln[0])
    for name in ("vae",):
        add_input(name, "VAE", old_inputs[name]["link"])
    for name, typ in (("width", "INT"), ("height", "INT"), ("length", "INT"), ("batch_size", "INT")):
        oi = old_inputs.get(name, {})
        add_input(name, typ, oi.get("link"), widget=True)
    add_input("clip_vision_output", "CLIPVISION_OUTPUT", None)
    add_input("start_image", "IMAGE", old_inputs["start_image"]["link"] if "start_image" in old_inputs else None)
    # fix to_slot of the existing incoming links to the new slot indices
    slot_of = {d["name"]: i for i, d in enumerate(new_inputs)}
    for d in new_inputs:
        if d["link"] is not None and d["link"] in links:
            links[d["link"]][3] = lat["id"]
            links[d["link"]][4] = slot_of[d["name"]]
    links[lp[0]] = lp
    links[ln[0]] = ln
    for src, slot in (pos_src, neg_src):
        outs = nodes[src]["outputs"][slot]
        outs["links"] = list(outs.get("links") or [])
    nodes[pos_src[0]]["outputs"][pos_src[1]]["links"].append(lp[0])
    nodes[neg_src[0]]["outputs"][neg_src[1]]["links"].append(ln[0])
    lat["inputs"] = new_inputs
    # outputs: positive, negative, latent ; move old latent links to slot 2
    old_latent_links = list(latent_out_links)
    lat["outputs"] = [
        {"name": "positive", "type": "CONDITIONING", "links": []},
        {"name": "negative", "type": "CONDITIONING", "links": []},
        {"name": "latent", "type": "LATENT", "links": old_latent_links},
    ]
    for lid in old_latent_links:
        links[lid][2] = 2
    # every sampler that consumed the latent now takes positive/negative from this node
    for cons_id, _ in consumers:
        cons = nodes[cons_id]
        for name, slot in (("positive", 0), ("negative", 1)):
            for i in cons["inputs"]:
                if i["name"] == name and i.get("link") is not None:
                    l = links[i["link"]]
                    old_src, old_slot = l[1], l[2]
                    nodes[old_src]["outputs"][old_slot]["links"] = [x for x in nodes[old_src]["outputs"][old_slot]["links"] if x != l[0]]
                    l[1], l[2] = lat["id"], slot
                    lat["outputs"][slot]["links"].append(l[0])
    # second-stage sampler (takes latent from first sampler) also needs pos/neg from the new node
    for n in wf["nodes"]:
        if n["type"] in ("KSamplerAdvanced", "KSampler") and n["id"] not in [c for c, _ in consumers]:
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
    lat.setdefault("widgets_values", [])
    if len(lat["widgets_values"]) == 4:
        pass
    notes.append(f"node {lat['id']}: Wan22ImageToVideoLatent -> WanImageToVideo (pos/neg rewired, latent slot 2)")
    return notes


def fix_train(wf: dict) -> list[str]:
    notes = []
    for n in wf["nodes"]:
        if n["type"] == "TrainLoraNode":
            wv = n["widgets_values"]
            names = [i["name"] for i in n["inputs"] if i.get("widget")]
            if len(wv) == len(names):
                seed_idx = names.index("seed")
                wv.insert(seed_idx + 1, "fixed")
                notes.append(f"TrainLoraNode {n['id']}: inserted 'fixed' after seed ({len(wv)} widget values)")
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-to-repo", action="store_true", help="also overwrite the repo workflow files")
    a = ap.parse_args()
    for rel, fixer in [(r, fix_wan_i2v) for r in WAN_I2V] + [(r, fix_train) for r in TRAIN]:
        src = SRC / rel
        wf = json.loads(src.read_text(encoding="utf-8"))
        notes = fixer(wf)
        dst = DST / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(wf, ensure_ascii=False, indent=2) + "\n"
        dst.write_text(text, encoding="utf-8")
        if a.apply_to_repo:
            src.write_text(text, encoding="utf-8")
        print(rel, "->", "; ".join(notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
