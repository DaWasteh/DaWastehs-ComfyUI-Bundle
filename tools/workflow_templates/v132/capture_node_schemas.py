#!/usr/bin/env python3
"""Capture the object_info schemas used by the v1.3.2 builder (LanPaint mask inpaint, AnyAngle camera angles) from a
running ComfyUI (0.38 with LanPaint 2.2 and AnyAngle Studio T8 installed).

Input order is kept exactly as the server reports it (ComfyUI restores widget values positionally). Machine-specific
file lists are reduced to the shipped defaults.

    python tools/workflow_templates/v132/capture_node_schemas.py http://127.0.0.1:8192
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

TYPES = [
    # shared Qwen Image 2.1 chain
    "UNETLoader", "CLIPLoader", "VAELoader", "LoraLoaderModelOnly", "TextEncodeQwenImage21", "QwenImage21Cache",
    "KSampler", "VAEDecode", "SplitImageWithAlpha", "LoadImage", "PixaromaLoadImage", "PixaromaSaveImage",
    "PixaromaCompare", "PixaromaPrompt", "PreviewImage", "ImageBatch",
    # LanPaint mask inpaint
    "PixaromaInpaintCrop", "PixaromaInpaintStitch", "DaWRequireMask", "LanPaint_ImageEncode", "LanPaint_KSampler",
    "LanPaint_ImageDecode",
    # AnyAngle: TripoSplat reconstruction and splat render
    "LoadBackgroundRemovalModel", "RemoveBackground", "TripoSplatPreprocessImage", "CLIPVisionLoader",
    "TripoSplatConditioning", "ModelSamplingAuraFlow", "VAEDecodeTripoSplat", "CreateCameraInfo", "RenderSplat",
    "SplatToFile3D", "SaveGLB", "ImageScale",
    # AnyAngle Studio T8
    "AnyAngleStudioT8", "AnyAngleOptionalLoRAT8",
    # runtime
    "PixaromaRunTimer", "SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice", "DaWMultiGPUDeviceControl",
]
BS = "\\"
FILE_LISTS = {
    ("UNETLoader", "unet_name"): ["Qwen" + BS + "qwen_image_2.1_bf16.safetensors", "TripoSplat" + BS + "triposplat_fp16.safetensors"],
    ("CLIPLoader", "clip_name"): ["Qwen" + BS + "qwen3vl_8b_int8_convrot.safetensors"],
    ("VAELoader", "vae_name"): ["qwen-image" + BS + "qwen_image_2.1_vae_bf16.safetensors", "FLUX2" + BS + "flux2-vae.safetensors",
                                "TripoSplat" + BS + "triposplat_vae_decoder_fp16.safetensors"],
    ("LoraLoaderModelOnly", "lora_name"): ["Qwen" + BS + "QI2.1_AnyAngle.safetensors"],
    ("CLIPVisionLoader", "clip_name"): ["dino_v3_vit_h.safetensors"],
    ("LoadBackgroundRemovalModel", "bg_removal_name"): ["birefnet.safetensors"],
    ("LoadImage", "image"): ["portrait_model_denim.png", "character_fox.png"],
    ("PixaromaLoadImage", "image"): ["character_fox.png", "character_fox_guide_left.png"],
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
