#!/usr/bin/env python3
"""Capture the object_info schemas used by the v1.3.0 builder (image prompt enhancer) from a running ComfyUI.

Input order is kept exactly as the server reports it (ComfyUI restores widget values
positionally). Machine-specific file lists are reduced to the shipped defaults.

    python tools/workflow_templates/v130/capture_node_schemas.py http://127.0.0.1:8192
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

TYPES = [
    # prompt enhancer pack
    "DaWImagePromptEnhancer",
    # UI / IO
    "PixaromaPrompt", "PixaromaLoadImage", "PixaromaShowText",
    # runtime
    "PixaromaRunTimer", "SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice", "DaWMultiGPUDeviceControl",
]
FILE_LISTS = {
    ("PixaromaLoadImage", "image"): ["example.png"],
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
