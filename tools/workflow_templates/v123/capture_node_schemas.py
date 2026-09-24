#!/usr/bin/env python3
"""Capture the object_info schemas used by the v1.2.3 video-upscale builder from a running ComfyUI.

Input order is kept exactly as the server reports it (ComfyUI restores widget values
positionally). Machine-specific file lists are reduced to the shipped defaults.

    python tools/workflow_templates/v123/capture_node_schemas.py http://127.0.0.1:8190
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

TYPES = [
    "DaWVUPlanner", "DaWVULoadBlock", "DaWVUSaveBlock", "DaWVUFinalize", "DaWH3PromptOnce", "DaWH3VideoToAVLatent",
    "PixaromaPrompt", "PixaromaShowText", "UNETLoader", "VAELoader", "MiniMaxH3SigmaShift", "ModelAttentionBackend",
    "BlockSparseAttention", "KSamplerSelect", "BasicScheduler", "RandomNoise", "BasicGuider", "SamplerCustomAdvanced",
    "VAEDecode", "MMH3UltimateUpscale", "MMH3LatentUpscaleParams", "MMH3LatentUpscaleWithModelParams", "MMH3TemporalSplitParams", "MMH3SpatialSplitParams",
    "MinimaxH3LatentUpscaler3D", "LTXVSeparateAVLatent", "LTXVConcatAVLatent", "ResizeImageMaskNode", "SeedVR2Preprocess",
    "VAEEncodeTiled", "SeedVR2TemporalChunk", "SeedVR2Conditioning", "KSampler", "SeedVR2TemporalMerge", "VAEDecodeTiled",
    "SeedVR2PostProcessing", "PixaromaPauseImage", "PixaromaLoopStart", "PixaromaLoopEnd", "PixaromaRunTimer",
    "SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice", "DaWMultiGPUDeviceControl",
]
BS = "\\"
FILE_LISTS = {
    ("DaWVUPlanner", "video"): ["video.mp4"],
    ("UNETLoader", "unet_name"): ["MiniMax H3" + BS + "fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors",
                                  "SeedVR2" + BS + "seedvr2_3b_int8_convrot.safetensors"],
    ("VAELoader", "vae_name"): ["MiniMax H3" + BS + "minimax_h3_video_vae_fp16.safetensors",
                                "MiniMax H3" + BS + "minimax_h3_audio_vae_fp32.safetensors",
                                "SeedVR2" + BS + "seedvr2_ema_vae_fp16.safetensors"],
    ("DaWH3PromptOnce", "text_encoder"): ["MiniMax H3" + BS + "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"],
    ("MinimaxH3LatentUpscaler3D", "model_name"): ["minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"],
    ("MMH3LatentUpscaleWithModelParams", "model_name"): ["minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"],
}


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8190"
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
