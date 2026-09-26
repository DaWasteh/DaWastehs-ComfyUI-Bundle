#!/usr/bin/env python3
"""Capture the object_info schemas used by the v1.2.8 builder (Qwen 2.1 mask edit, pose, depth) from a running ComfyUI.

Input order is kept exactly as the server reports it (ComfyUI restores widget values
positionally). Machine-specific file lists are reduced to the shipped defaults.

    python tools/workflow_templates/v128/capture_node_schemas.py http://127.0.0.1:8192
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

TYPES = [
    # Qwen Image 2.1 mask edit
    "UNETLoader", "CLIPLoader", "VAELoader", "LoadImage", "PixaromaInpaintCrop", "PixaromaInpaintStitch", "DaWRequireMask",
    "TextEncodeQwenImage21", "VAEEncode", "SetLatentNoiseMask", "DifferentialDiffusion", "QwenImage21Cache", "KSampler",
    "VAEDecode", "SplitImageWithAlpha", "PixaromaSaveImage", "PixaromaCompare", "PixaromaPrompt", "PreviewImage",
    # pose
    "PixaromaLoadImage", "CheckpointLoaderSimple", "RTDETR_detect", "SDPoseKeypointExtractor", "SDPoseDrawKeypoints",
    "DaWPoseBoxes", "DrawBBoxes", "ImageBlend", "SavePoseKpsAsJsonFile",
    # depth
    "LoadDA3Model", "DA3Inference", "DA3Render", "DaWSaveDepth16",
    # video frame
    "VHS_BatchManager", "DaWLoadVideoBatches", "VHS_VideoCombine",
    # runtime
    "PixaromaRunTimer", "SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice", "DaWMultiGPUDeviceControl",
]
BS = "\\"
FILE_LISTS = {
    ("UNETLoader", "unet_name"): ["Qwen" + BS + "qwen_image_2.1_bf16.safetensors", "SDPose" + BS + "rt_detr_v4-x-hgnet_fp16.safetensors"],
    ("CLIPLoader", "clip_name"): ["Qwen" + BS + "qwen3vl_8b_int8_convrot.safetensors"],
    ("VAELoader", "vae_name"): ["qwen-image" + BS + "qwen_image_2.1_vae_bf16.safetensors"],
    ("LoadImage", "image"): ["portrait_model_denim.png"],
    ("PixaromaLoadImage", "image"): ["dancer.png", "retro_futuristic_home.png"],
    ("CheckpointLoaderSimple", "ckpt_name"): ["SDPose" + BS + "sdpose_wholebody_fp16.safetensors"],
    ("LoadDA3Model", "model_name"): ["DepthAnything3" + BS + "depth_anything_3_mono_large.safetensors"],
    ("DaWLoadVideoBatches", "video"): ["man_in_the_rain.mp4", "empty_room_assembly.mp4"],
}


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8192"
    schemas = {}
    for kind in TYPES:
        with urllib.request.urlopen(f"{base}/object_info/{kind}", timeout=30) as response:
            schemas[kind] = json.load(response)[kind]
    for (kind, name), options in FILE_LISTS.items():
        spec = schemas[kind]["input"]["required"][name]
        if isinstance(spec[0], list):
            spec[0] = options
        else:
            spec[1]["options"] = options
        if len(spec) > 1 and isinstance(spec[1], dict) and "default" in spec[1]:
            spec[1]["default"] = options[0]
    target = Path(__file__).with_name("node-schemas.json")
    target.write_text(json.dumps(schemas, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(target)


if __name__ == "__main__":
    main()
