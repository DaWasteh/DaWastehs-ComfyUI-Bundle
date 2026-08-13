#!/usr/bin/env python3
"""Generate a MiniMax Music 3 caption enhancer from MiniMax's official skill."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from pathlib import Path

try:
    from tools.generate_dual_gpu_workflows import refresh_refinement
except ModuleNotFoundError:
    from generate_dual_gpu_workflows import refresh_refinement

ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = ROOT / "workflows" / "Prompt Enhancer"
TEMPLATE = PROMPT_DIR / "Qwen3VL_8b_fp8_scaled-Krea2-Prompt-Enhancer.json"
SKILL_DIR = ROOT / "prompt-libraries" / "MiniMax-Music3-Official-Skill"
SKILL = SKILL_DIR / "SKILL.md"
GENRE_ROUTER = SKILL_DIR / "genre-router.md"
OUTPUT = PROMPT_DIR / "MiniMax_Music3-Official-Skill-Caption-Enhancer.json"
MODEL = r"Qwen\qwen3.5_4b_bf16.safetensors"


def _instruction(skill_text: str, router_text: str) -> str:
    return f"""You are a strict MiniMax Music 3 caption rewriter.

TASK
Transform the user's Caption and optional tagged Lyrics into a new, generation-ready MiniMax Music 3 structured caption.

LOCAL COMFYUI ADAPTATION
This one-pass workflow has the official core skill and genre router embedded below, but it cannot open the skill's family-index and template files at generation time. Follow the official input, constraint, lyric-safety, timeline, and validation rules. This adapter intentionally narrows the skill's language and machine-readable output exceptions to one English caption with three headings because its result feeds ComfyUI's Music 3 Caption field directly. Use the embedded router as musical guidance, then synthesize directly from the user's brief. Do not claim to have retrieved, scored, or copied a template. Do not expose private reasoning.

MANDATORY OUTPUT CONTRACT
- Return only the finished caption in English.
- Return exactly these three Markdown headings, once each and in this order:
  ### Global Metadata
  ### Vocal Details
  ### Arrangement
- Target approximately 250–450 words.
- Lyrics are context only: never quote, paraphrase, summarize, or reproduce lyric lines.
- Treat only bracketed lyric tags as executable section, musical, vocal, or production directives.
- Preserve every explicit constraint and exclusion; never invent an exact BPM, key, vocal gender, or technical detail when it is not justified.
- Do not add a title, preamble, explanation, checklist, JSON, template ID, or Markdown fence.

OFFICIAL MINIMAX MUSIC CAPTION REWRITER SKILL
{skill_text}

OFFICIAL GENRE ROUTER
{router_text}

USER CAPTION
"""


def build() -> dict:
    skill_text = SKILL.read_text(encoding="utf-8")
    router_text = GENRE_ROUTER.read_text(encoding="utf-8")
    workflow = copy.deepcopy(json.loads(TEMPLATE.read_text(encoding="utf-8")))
    by_id = {node["id"]: node for node in workflow["nodes"]}

    by_id[1]["widgets_values"] = [_instruction(skill_text, router_text), "", "\n\n"]
    by_id[1]["title"] = "Official MiniMax Music 3 Skill + Caption"
    by_id[2]["widgets_values"] = ["", 4096, "on", 0.25, 64, 0.9, 0.05, 1.05, 0, 0, False, True]
    by_id[2]["title"] = "Generate Structured MiniMax Music 3 Caption"
    by_id[3]["widgets_values"] = ["The enhanced MiniMax Music 3 caption appears here after the first run."]
    by_id[3]["title"] = "COPY THIS INTO THE MUSIC WORKFLOW'S CAPTION FIELD"
    by_id[4]["widgets_values"] = [MODEL, "stable_diffusion", "default"]
    by_id[4]["title"] = "Qwen 3.5 4B · Official Music 3 Skill Adapter"
    by_id[9]["title"] = "1 · YOUR MUSIC IDEA / CAPTION"
    by_id[9]["color"] = "#1e3323"
    by_id[9]["bgcolor"] = "#36543d"
    by_id[9]["widgets_values"] = [""]
    by_id[9].setdefault("properties", {}).setdefault("promptState", {})["text"] = ""

    caption_to_instruction = next(link for link in workflow["links"] if link[0] == 4)
    caption_to_instruction[3] = 1
    caption_to_instruction[4] = 1

    prompt_link = next(link for link in workflow["links"] if link[0] == 2)
    prompt_link[1] = 12
    prompt_link[2] = 0
    by_id[1]["outputs"][0]["links"] = [6]

    lyrics_node = copy.deepcopy(by_id[9])
    lyrics_node.update({
        "id": 11,
        "pos": [float(by_id[9]["pos"][0]), float(by_id[9]["pos"][1]) + 500.0],
        "title": "2 · OPTIONAL TAGGED LYRICS",
        "widgets_values": [""],
    })
    lyrics_node["outputs"][0]["links"] = [7]
    lyrics_properties = lyrics_node.setdefault("properties", {})
    lyrics_properties.setdefault("promptState", {})["text"] = ""
    lyrics_properties["dawasteh_pixaroma_prompt_integration"] = {
        "kind": "prompt",
        "target": [12, "string_b"],
    }

    merge_node = {
        "id": 12,
        "type": "StringConcatenate",
        "pos": [float(by_id[1]["pos"][0]) + 760.0, float(by_id[1]["pos"][1])],
        "size": [520, 330],
        "flags": {},
        "order": max(int(node.get("order", 0)) for node in workflow["nodes"]) + 1,
        "mode": 0,
        "inputs": [
            {"localized_name": "string_a", "name": "string_a", "type": "STRING", "widget": {"name": "string_a"}, "link": 6},
            {"localized_name": "string_b", "name": "string_b", "type": "STRING", "widget": {"name": "string_b"}, "link": 7},
            {"localized_name": "delimiter", "name": "delimiter", "type": "STRING", "widget": {"name": "delimiter"}, "link": None},
        ],
        "outputs": [{"localized_name": "STRING", "name": "STRING", "type": "STRING", "links": [2]}],
        "title": "Caption + Optional Lyrics (tags are executable)",
        "properties": {"Node name for S&R": "StringConcatenate", "cnr_id": "comfy-core"},
        "widgets_values": ["", "", "\n\nUSER LYRICS (never reproduce lyric lines; use bracketed tags only)\n"],
        "color": "#1e3323",
        "bgcolor": "#36543d",
    }
    workflow["nodes"].extend([lyrics_node, merge_node])
    workflow["links"].extend([
        [6, 1, 0, 12, 0, "STRING"],
        [7, 11, 0, 12, 1, "STRING"],
    ])

    workflow["last_node_id"] = 12
    workflow["last_link_id"] = 7
    workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh:minimax-music3:official-skill-caption-enhancer"))
    workflow["revision"] = 0
    workflow.setdefault("extra", {})["dawasteh_minimax_music3_prompt_skill"] = {
        "version": 1,
        "upstream": "https://github.com/MiniMax-AI/MiniMax-Music3/tree/main/skills/music-caption-rewriter",
        "model": MODEL,
        "sources": [
            {"path": SKILL.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(skill_text.encode("utf-8")).hexdigest()},
            {"path": GENRE_ROUTER.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(router_text.encode("utf-8")).hexdigest()},
        ],
        "adapter_limit": "one-pass workflow embeds the core skill and router, not the 1000-template progressive-disclosure library",
        "output_contract": ["### Global Metadata", "### Vocal Details", "### Arrangement"],
    }
    refresh_refinement(workflow)
    return workflow


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
