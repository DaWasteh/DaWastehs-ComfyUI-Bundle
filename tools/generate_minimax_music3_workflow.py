#!/usr/bin/env python3
"""Generate the full-quality MiniMax Music 3 workflow with optional GPU placement."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from pathlib import Path

try:
    from tools.generate_dual_gpu_workflows import (
        WORKFLOW_TEMPLATES,
        _localize_model_paths,
        install_run_timer,
        refresh_refinement,
    )
    from tools.migrate_workflows_v092 import migrate_workflow
except ModuleNotFoundError:
    from generate_dual_gpu_workflows import (
        WORKFLOW_TEMPLATES,
        _localize_model_paths,
        install_run_timer,
        refresh_refinement,
    )
    from migrate_workflows_v092 import migrate_workflow

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = WORKFLOW_TEMPLATES / "audio_minimax_music_3.json"
OUTPUT = ROOT / "workflows" / "Music Generation" / "MiniMax_Music3_FP32-BF16-Text-to-Music.json"


def build() -> dict:
    workflow = copy.deepcopy(json.loads(TEMPLATE.read_text(encoding="utf-8-sig")))
    _localize_model_paths(workflow)
    install_run_timer(workflow)
    workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh:minimax-music3:fp32-bf16:text-to-music"))
    workflow["revision"] = 0
    workflow.setdefault("extra", {})["dawasteh_minimax_music3"] = {
        "version": 1,
        "source": "Comfy-Org/workflow_templates:templates/audio_minimax_music_3.json",
        "source_sha256": hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
        "precision": {"dit": "fp32", "text_encoder": "bf16", "dav": "source"},
        "models": {
            "diffusion": r"MiniMax Music 3\minimax_music3_dit_fp32.safetensors",
            "text_encoder": r"MiniMax Music 3\minimax_music3_text_encoder_bf16.safetensors",
            "vae": r"MiniMax Music 3\minimax_music3_dav.safetensors",
        },
        "validation": {
            "status": "live-smoke-passed",
            "date": "2026-08-14",
            "profile": "4 second maximum duration, 30 Euler/simple steps, tiled DAV decode",
            "result": "execution_success; 7.988 second nonempty 44.1 kHz stereo FLAC",
        },
    }
    refresh_refinement(workflow)
    return migrate_workflow(workflow, "Music Generation/MiniMax_Music3_FP32-BF16-Text-to-Music.json")


def generate(destination: Path = OUTPUT) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(f"Generated {generate(args.destination)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
