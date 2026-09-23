#!/usr/bin/env python3
"""Capture the object_info schemas used by the v1.2.2 music-video builder from a running ComfyUI.

Input order is kept exactly as the server reports it (ComfyUI restores widget values
positionally). Machine-specific file lists are reduced to the shipped defaults.

    python tools/workflow_templates/v122/capture_node_schemas.py http://127.0.0.1:8190
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

TYPES = [
    "DaWMV2Planner", "DaWMV2PromptWriter", "DaWMV2EncodeScenes", "DaWMV2SceneSetup", "DaWMV2SaveScene", "DaWMV2Finalize",
    "PixaromaPrompt", "PixaromaSizes", "PixaromaShowText", "PixaromaLoadImage", "UNETLoader", "VAELoader", "MiniMaxH3SigmaShift",
    "ModelAttentionBackend", "BlockSparseAttention", "KSamplerSelect", "BasicScheduler", "RandomNoise", "BasicGuider",
    "SamplerCustomAdvanced", "PixaromaPauseImage", "PixaromaLoopStart", "PixaromaLoopEnd", "PixaromaRunTimer",
    "SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice", "DaWMultiGPUDeviceControl",
]
BS = "\\"
FILE_LISTS = {
    ("DaWMV2Planner", "song"): ["song.mp3"],
    ("PixaromaLoadImage", "image"): ["character_sheet_1.png"],
    ("UNETLoader", "unet_name"): ["MiniMax H3" + BS + "fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors"],
    ("VAELoader", "vae_name"): ["MiniMax H3" + BS + "minimax_h3_video_vae_fp16.safetensors",
                                "MiniMax H3" + BS + "minimax_h3_audio_vae_fp32.safetensors"],
    ("DaWMV2PromptWriter", "llm"): ["Qwen" + BS + "qwen3.5_4b_bf16.safetensors"],
    ("DaWMV2EncodeScenes", "text_encoder"): ["MiniMax H3" + BS + "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"],
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
