#!/usr/bin/env python3
"""Capture the object_info schemas used by the v1.2.6 WAN video-upscale builder from a running ComfyUI.

Input order is kept exactly as the server reports it (ComfyUI restores widget values
positionally). Machine-specific file lists are reduced to the shipped defaults.

    python tools/workflow_templates/v126/capture_node_schemas.py http://127.0.0.1:8191
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

TYPES = [
    "DaWVUPlanner", "DaWVULoadBlock", "DaWVUSaveBlock", "DaWVUFinalize", "PixaromaPrompt", "PixaromaShowText",
    "DaWVUReadOnlyUNETLoader", "LoraLoaderModelOnly", "ModelSamplingSD3", "DaWVUSpatialTiles",
    "WanContextWindowsManual", "DaWVUReadOnlyCLIPLoader", "CLIPTextEncode", "VAELoader", "ResizeImageMaskNode", "VAEEncodeTiled",
    "KSampler", "VAEDecodeTiled", "PixaromaPauseImage", "PixaromaLoopStart", "PixaromaLoopEnd", "PixaromaRunTimer",
    "SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice", "DaWMultiGPUDeviceControl",
]
BS = "\\"
FILE_LISTS = {
    ("DaWVUPlanner", "video"): ["video.mp4"],
    ("DaWVUReadOnlyUNETLoader", "unet_name"): ["WAN" + BS + "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors"],
    ("LoraLoaderModelOnly", "lora_name"): ["WAN" + BS + "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"],
    ("DaWVUReadOnlyCLIPLoader", "clip_name"): ["UMT5" + BS + "umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
    ("VAELoader", "vae_name"): ["WAN" + BS + "wan_2.1_vae.safetensors"],
}


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8191"
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
