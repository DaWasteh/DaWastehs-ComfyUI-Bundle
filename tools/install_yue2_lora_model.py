#!/usr/bin/env python3
"""Opt-in download of the pinned noncommercial YuE2 BF16 training checkpoint."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from tools.install_pixal3d_game_models import validate_root, target_path, verify
except ModuleNotFoundError:
    from install_pixal3d_game_models import validate_root, target_path, verify

MODEL = {
    "repo": "Comfy-Org/YuE2",
    "revision": "8e6fcf0f23252ed188b634bd50d44f4b01fba890",
    "path": "checkpoints/yue2_3b_bf16.safetensors",
    "size": 7799983228,
    "sha256": "33765adbf9813c9a50318218760b2fd819a319862460a04884607581961c6fee",
    "license": "CC-BY-NC-4.0",
}


def install(root: Path, *, accept_noncommercial=False, verify_only=False):
    root = validate_root(root)
    target = target_path(root / "models", MODEL["path"])
    valid, detail = verify(target, MODEL["size"], MODEL["sha256"])
    if valid:
        print("OK", target, detail, flush=True)
        return
    if verify_only or target.exists():
        raise ValueError(f"Not overwritten: {target}: {detail}")
    if not accept_noncommercial:
        raise ValueError("YuE2 is CC-BY-NC-4.0; explicit --accept-noncommercial required")
    from huggingface_hub import hf_hub_download

    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
    cache = root / "models/.cache/dawasteh-yue2-bf16"
    print("Downloading YuE2 BF16: 7.80 GB, private/noncommercial use only", flush=True)
    result = Path(hf_hub_download(repo_id=MODEL["repo"], filename=MODEL["path"],
                                 revision=MODEL["revision"], local_dir=cache)).resolve()
    valid, detail = verify(result, MODEL["size"], MODEL["sha256"])
    if not valid:
        raise ValueError(f"Downloaded checkpoint verification failed: {detail}")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(result, target)  # Same volume, atomic, never overwrites existing weights.
    print("OK", target, detail, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comfy-root", type=Path, required=True)
    p.add_argument("--accept-noncommercial", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    a = p.parse_args()
    install(a.comfy_root, accept_noncommercial=a.accept_noncommercial, verify_only=a.verify_only)


if __name__ == "__main__":
    main()
