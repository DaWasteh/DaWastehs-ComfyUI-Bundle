#!/usr/bin/env python3
"""Capture the object_info schemas used by the v1.2.9 builders (Ming Image, Mira-Scene) from a running ComfyUI.

Input order is kept exactly as the server reports it (ComfyUI restores widget values
positionally). Machine-specific file lists are reduced to the shipped defaults.

    python tools/workflow_templates/v129/capture_node_schemas.py http://127.0.0.1:8192
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

TYPES = [
    # loaders and sampling
    "DaWVUReadOnlyUNETLoader", "DaWVUReadOnlyCLIPLoader", "VAELoader", "ModelSamplingAuraFlow", "KSampler", "ConditioningZeroOut", "VAEDecode",
    "EmptyLatentImage", "EmptyQwenImageLayeredLatentImage", "LatentCutToBatch", "SplitImageWithAlpha",
    # text / edit encoders
    "CLIPTextEncode", "TextEncodeMingImageEdit",
    # Ming Image pack
    "DaWMingReferenceSize", "DaWMingPromptWriter", "DaWMingLayerSplit", "DaWMingAlphaFallback", "DaWMingCheckerboard",
    # alpha fallback
    "LoadBackgroundRemovalModel", "RemoveBackground",
    # Mira-Scene pack + native SAM 3.1, MoGe-2, TRELLIS.2 and 3D output
    "DaWMiraPrepareImage", "DaWMiraMasks", "DaWMiraLoadCCM", "DaWMiraCCM", "DaWMiraTrellisObjects", "DaWMiraAssembleScene",
    "CheckpointLoaderSimple", "SAM3_Detect", "LoadMoGeModel", "MoGeInference", "UNETLoader", "CFGOverride", "RescaleCFG",
    "CLIPVisionLoader", "Save3DAdvanced", "SaveGLB",
    # UI / IO
    "PixaromaPrompt", "PixaromaResolution", "PixaromaLoadImage", "PixaromaSaveImage", "PixaromaCompare",
    "PreviewImage", "PreviewAny",
    # runtime
    "PixaromaRunTimer", "SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice", "DaWMultiGPUDeviceControl",
]
BS = "\\"
FILE_LISTS = {
    ("DaWVUReadOnlyUNETLoader", "unet_name"): ["Ming" + BS + "ming_image_0.1_design_int8_convrot.safetensors",
                                  "Ming" + BS + "ming_image_0.1_design_layer_int8_convrot.safetensors"],
    ("DaWVUReadOnlyCLIPLoader", "clip_name"): ["Ming" + BS + "ming_image_0.1_ling_mini_2.0_int8_convrot.safetensors",
                                  "Ming" + BS + "ming_image_0.1_ling_mini_2.0_layer_int8_convrot.safetensors"],
    ("VAELoader", "vae_name"): ["Ming" + BS + "ming_image_vae_bf16.safetensors", "trellis_2_shape_vae_bf16.safetensors",
                                "trellis_2_texture_vae_bf16.safetensors"],
    ("PixaromaLoadImage", "image"): ["ming_card_making_input.png", "modern_living_room.png"],
    ("LoadBackgroundRemovalModel", "bg_removal_name"): ["birefnet.safetensors"],
    ("CheckpointLoaderSimple", "ckpt_name"): ["SAM3" + BS + "sam3.1_multiplex_fp16.safetensors"],
    ("LoadMoGeModel", "model_name"): ["moge_2_vitl_normal_fp16.safetensors"],
    ("DaWMiraLoadCCM", "pipeline"): ["Mira-Scene" + BS + "pipeline"],
    ("UNETLoader", "unet_name"): ["trellis_2_int8_convrot.safetensors"],
    ("CLIPVisionLoader", "clip_name"): ["dino_v3_vit_l.safetensors"],
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
