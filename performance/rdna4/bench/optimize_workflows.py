"""Apply measured workflow-level optimisations to copies of the repo workflows.

E1  VRAM_Debug: unload_all_models -> False (keep empty_cache / gc_collect). Measured on Z-Image Turbo:
    warm 15.6 s -> 8.2 s, outputs bit-identical (same seed).
E2  Image workflows with CLIP/VAE on gpu:1: -> gpu:0. SelectCLIPDevice/SelectVAEDevice to a device that
    differs from the loader device deep-clones the model (8 s + duplicate host RAM) and leaves a dead
    LoadedModel that triggers full gc.collect() on every model load. Measured: Z-Image Turbo warm
    8.2 s -> 6.2 s (with E1), SDXL 10.5 s -> 9.1 s, outputs bit-identical.

Copies are written to performance/rdna4/workflows/<category>/<name>.json (same relative path as the
original in workflows/, so the mapping is unambiguous). --apply-to-repo overwrites the repo files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "workflows"
DST = Path(__file__).resolve().parents[1] / "workflows"

# E1 scope: categories where the cleanup barrier was measured to cost time without freeing needed host RAM
# (image + audio). Video/3D/game/live categories keep unload_all_models=True: on WAN 2.2 I2V (two 14B models
# alternating) the barrier is what frees the offloaded CPU copies; without it host RAM fell to 0.7 GB.
E1_CATEGORIES = {
    "Audio to Image", "Batch Processing", "Character & Consistency", "Image Editing", "Image Fusion",
    "Image Inpainting", "Image Outpainting", "Image Upscaling", "Image Utilities", "Music Generation", "NSFW",
    "Pixaroma Node Demos", "Prompt Tools", "Templates & Tests", "Text to Image",
}

# E2 scope: image workflows only (video/audio splits are evaluated separately).
IMAGE_SPLIT_TO_GPU0 = [
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
]


# E2b scope: LTX-2.5 graphs (measured on T2V: cold 548 s -> 152 s, frames bit-identical): CLIP on gpu:0, VAE stays on gpu:1.
LTX_CLIP_TO_GPU0 = [
    "Text to Video/LTX25_INT8_ConvRot-Text-to-Video.json",
    "Text+Image to Video/LTX25_INT8_ConvRot-Image-to-Video.json",
    "Text+Image to Video/LTX25_INT8_ConvRot-First+Last-Frame-to-Video.json",
]


def vram_debug_widgets(node: dict) -> list | None:
    # widgets order per KJNodes: empty_cache, gc_collect, unload_all_models
    wv = node.get("widgets_values")
    if isinstance(wv, list) and len(wv) >= 3:
        return wv
    return None


def walk_graphs(wf: dict):
    yield wf
    for sg in wf.get("definitions", {}).get("subgraphs", []) or []:
        yield sg


def apply_e1(wf: dict) -> int:
    n = 0
    for g in walk_graphs(wf):
        for node in g.get("nodes", []):
            if node.get("type") == "VRAM_Debug":
                wv = vram_debug_widgets(node)
                if wv and wv[2] is True:
                    wv[2] = False
                    n += 1
    return n


def apply_e2(wf: dict) -> int:
    n = 0
    for node in wf.get("nodes", []):
        if node.get("type") == "DaWMultiGPUDeviceControl":
            wv = node.get("widgets_values") or []
            if len(wv) == 3 and tuple(wv) != ("gpu:0", "gpu:0", "gpu:0"):
                node["widgets_values"] = ["gpu:0", "gpu:0", "gpu:0"]
                n += 1
    return n


def apply_e2b(wf: dict) -> int:
    n = 0
    for node in wf.get("nodes", []):
        if node.get("type") == "DaWMultiGPUDeviceControl":
            wv = node.get("widgets_values") or []
            if len(wv) == 3 and wv[1] != "gpu:0":
                node["widgets_values"] = [wv[0], "gpu:0", wv[2]]
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-to-repo", action="store_true")
    ap.add_argument("--no-e1", action="store_true")
    ap.add_argument("--no-e2", action="store_true")
    a = ap.parse_args()
    changed = 0
    for src in sorted(SRC.glob("*/*.json")):
        rel = src.relative_to(SRC).as_posix()
        # keep earlier B1/B2 fixes if a fixed copy already exists
        base = DST / rel if (DST / rel).exists() else src
        wf = json.loads(base.read_text(encoding="utf-8"))
        n1 = 0 if (a.no_e1 or rel.split("/")[0] not in E1_CATEGORIES) else apply_e1(wf)
        n2 = 0 if (a.no_e2 or rel not in IMAGE_SPLIT_TO_GPU0) else apply_e2(wf)
        n3 = 0 if (a.no_e2 or rel not in LTX_CLIP_TO_GPU0) else apply_e2b(wf)
        if n1 or n2 or n3:
            dst = DST / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(wf, ensure_ascii=False, indent=2) + "\n"
            dst.write_text(text, encoding="utf-8")
            if a.apply_to_repo:
                src.write_text(text, encoding="utf-8")
            changed += 1
            print(f"{rel}: E1 nodes={n1} E2={'yes' if n2 else 'no'} E2b={'yes' if n3 else 'no'}")
    print(f"{changed} workflows written to {DST}" + (" and applied to repo" if a.apply_to_repo else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
