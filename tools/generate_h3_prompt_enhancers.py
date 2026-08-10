#!/usr/bin/env python3
"""Generate two MiniMax H3 prompt enhancers from MiniMax's writing guides."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

try:
    from tools.generate_dual_gpu_workflows import refresh_refinement
except ModuleNotFoundError:
    from generate_dual_gpu_workflows import refresh_refinement

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "workflows" / "Reference to Video"
PROMPT_DIR = ROOT / "workflows" / "Prompt Enhancer"
TEMPLATE = PROMPT_DIR / "Qwen3VL_8b_fp8_scaled-Krea2-Prompt-Enhancer.json"
BASE_GUIDE = REFERENCE_DIR / "VIDEO_PROMPT_WRITING_GUIDE_base_en.md"
REF_GUIDE = REFERENCE_DIR / "VIDEO_PROMPT_WRITING_GUIDE_ref_en.md"
MODEL = r"Qwen\qwen3.5_4b_bf16.safetensors"


@dataclass(frozen=True)
class Enhancer:
    name: str
    output: str
    guides: tuple[Path, ...]
    role: str


ENHANCERS = (
    Enhancer(
        "MiniMax H3 Base / FL2VA",
        "MiniMax_H3_Base_FL2VA-Official-Guide-Prompt-Enhancer.json",
        (BASE_GUIDE,),
        "Rewrite T2VA, I2VA, FL2VA, or L2VA requests into the exact three-field MiniMax H3 base-mode format.",
    ),
    Enhancer(
        "MiniMax H3 Ref2VA",
        "MiniMax_H3_Ref2VA-Official-Guide-Prompt-Enhancer.json",
        (REF_GUIDE, BASE_GUIDE),
        "Rewrite full-reference requests into the exact six-section MiniMax H3 Ref2VA format.",
    ),
)


def _instruction(enhancer: Enhancer, guide_text: str) -> str:
    if "Ref2VA" in enhancer.name:
        contract = """MANDATORY OUTPUT CONTRACT FOR THIS REF2VA WORKFLOW
Your first characters must be `subject_definitions:`. Return exactly these six sections, once each, in this order:
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:

This is full-reference mode. Never replace these six sections with the Base guide's three-field format. Never use `integrated_multimodal_description:`. The Base guide included later is only an appendix for shared shot, camera, dialogue, and sound-writing rules. Write `[Shot 1]` with no timestamp; only later shots receive strictly increasing cut timestamps."""
    else:
        contract = """MANDATORY OUTPUT CONTRACT FOR THIS BASE/FL2VA WORKFLOW
Use the applicable MiniMax keyframe-alignment instruction first when the task is I2VA, FL2VA, or L2VA. Then return exactly these three fields in this order:
integrated_multimodal_description:
overall_soundscape:
non_diegetic_music:

Do not emit Ref2VA-only sections such as `subject_definitions`, `summary`, or `retention_analysis`. Write `[Shot 1]` with no timestamp; only later shots receive strictly increasing cut timestamps."""
    return f"""You are a strict MiniMax H3 audiovisual prompt rewriter.

TASK
{enhancer.role}

{contract}

RULE PRIORITY
1. Obey the mandatory output contract above even if an appendix describes another mode.
2. Preserve every user-supplied fact, exact dialogue/lyrics, visible text, language, reference role, and requested duration.
3. Follow the MiniMax writing guide below exactly, including section names, ordering, reference labels, shot numbering, timestamps, speaker IDs, dialogue tags, soundscape, and non-diegetic music rules.
4. Do not invent dialogue, lyrics, visible text, reference assets, or unsupported facts. If required timing/reference information is missing, make the narrowest safe interpretation instead of adding commentary.
5. Write the requested output sections in English. Preserve the original language only where the guide requires it.
6. Return only the finished MiniMax H3 prompt. Do not add a preamble, explanation, Markdown fence, checklist, or critique.

OFFICIAL MINIMAX GUIDE
{guide_text}

USER REQUEST
"""


def build(enhancer: Enhancer) -> dict:
    workflow = copy.deepcopy(json.loads(TEMPLATE.read_text(encoding="utf-8")))
    texts = [path.read_text(encoding="utf-8") for path in enhancer.guides]
    combined = "\n\n---\n\n".join(texts)
    by_id = {node["id"]: node for node in workflow["nodes"]}
    by_id[1]["widgets_values"] = [_instruction(enhancer, combined), "", "\n\n"]
    by_id[1]["title"] = f"Official MiniMax Guide + {enhancer.name} Request"
    values = list(by_id[2]["widgets_values"])
    values[1] = 4096
    values[3] = 0.3
    values[5] = 0.9
    by_id[2]["widgets_values"] = values
    by_id[2]["title"] = f"Generate {enhancer.name} Prompt"
    by_id[3]["widgets_values"] = ["The generated MiniMax H3 prompt appears here after the first run."]
    by_id[4]["widgets_values"] = [MODEL, "stable_diffusion", "default"]
    by_id[4]["title"] = "Qwen 3.5 4B · strict H3 prompt rewriting"
    by_id[9]["title"] = f"Your {enhancer.name} request"

    # MiniMax requires Shot 1 without a timestamp. Small local LLMs sometimes
    # still emit "[Shot 1] At 00:00.000," despite explicit instructions, so a
    # deterministic final sanitizer enforces that part of the official format.
    link_to_preview = next(link for link in workflow["links"] if link[3] == 3 and link[4] == 0)
    original_origin, original_slot = link_to_preview[1], link_to_preview[2]
    regex_id = max(int(node["id"]) for node in workflow["nodes"] if isinstance(node.get("id"), int)) + 1
    new_link_id = max(int(link[0]) for link in workflow["links"] if isinstance(link[0], int)) + 1
    link_to_preview[1], link_to_preview[2] = regex_id, 0
    source_node = by_id[original_origin]
    source_node["outputs"][original_slot]["links"] = [new_link_id if value == link_to_preview[0] else value for value in source_node["outputs"][original_slot].get("links", [])]
    workflow["links"].append([new_link_id, original_origin, original_slot, regex_id, 0, "STRING"])
    workflow["nodes"].append({
        "id": regex_id,
        "type": "RegexReplace",
        "pos": [float(by_id[3]["pos"][0]) - 500.0, float(by_id[3]["pos"][1])],
        "size": [440, 292],
        "flags": {},
        "order": max(int(node.get("order", 0)) for node in workflow["nodes"]) + 1,
        "mode": 0,
        "inputs": [
            {"localized_name": "string", "name": "string", "type": "STRING", "widget": {"name": "string"}, "link": new_link_id},
            {"localized_name": "regex_pattern", "name": "regex_pattern", "type": "STRING", "widget": {"name": "regex_pattern"}, "link": None},
            {"localized_name": "replace", "name": "replace", "type": "STRING", "widget": {"name": "replace"}, "link": None},
            {"localized_name": "case_insensitive", "name": "case_insensitive", "type": "BOOLEAN", "widget": {"name": "case_insensitive"}, "link": None},
            {"localized_name": "multiline", "name": "multiline", "type": "BOOLEAN", "widget": {"name": "multiline"}, "link": None},
            {"localized_name": "dotall", "name": "dotall", "type": "BOOLEAN", "widget": {"name": "dotall"}, "link": None},
            {"localized_name": "count", "name": "count", "type": "INT", "widget": {"name": "count"}, "link": None},
        ],
        "outputs": [{"localized_name": "STRING", "name": "STRING", "type": "STRING", "slot_index": 0, "links": [link_to_preview[0]]}],
        "title": "Enforce official Shot 1 timestamp rule",
        "properties": {"Node name for S&R": "RegexReplace", "cnr_id": "comfy-core"},
        "widgets_values": ["", r"(\[Shot 1\])\s+At\s+00:00(?:\.000)?,\s*", r"\1 ", True, True, False, 1],
    })
    workflow["last_node_id"] = regex_id
    workflow["last_link_id"] = new_link_id
    workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dawasteh-h3-prompt-enhancer:{enhancer.output}"))
    workflow["revision"] = 0
    workflow.setdefault("extra", {})["dawasteh_h3_prompt_guide"] = {
        "version": 1,
        "mode": enhancer.name,
        "model": MODEL,
        "guides": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
            for path, text in zip(enhancer.guides, texts)
        ],
        "output_contract": "final prompt only",
    }
    refresh_refinement(workflow)
    return workflow


def generate(destination: Path = PROMPT_DIR) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    for enhancer in ENHANCERS:
        path = destination / enhancer.output
        path.write_text(json.dumps(build(enhancer), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=PROMPT_DIR)
    args = parser.parse_args()
    paths = generate(args.destination)
    print(f"Generated {len(paths)} MiniMax H3 prompt enhancers in {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
