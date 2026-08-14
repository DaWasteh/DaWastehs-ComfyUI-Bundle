#!/usr/bin/env python3
"""Consolidate 14 ACE-Step AutoSongwriters into two genre-selectable workflows."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from tools import migrate_workflows_v092 as v092
except ModuleNotFoundError:  # Direct execution
    import migrate_workflows_v092 as v092


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
MIGRATION_KEY = "dawasteh_v093_autosongwriter"
MIGRATION_VERSION = 2
CUSTOM_NODE_TYPE = "DaWAutoSongwriterGenreSelector"
PROFILE_LABELS = [
    "POP · 120 BPM · C major",
    "GLOW · 96 BPM · G major",
    "DRIVE · 108 BPM · A minor",
    "CLUB · 126 BPM · F# minor",
    "NIGHT · 84 BPM · E minor",
    "RUSH · 138 BPM · D major",
    "CUSTOM · own genre / new style",
]
LANGUAGES = [
    "ar", "az", "bg", "bn", "ca", "cs", "da", "de", "el", "en", "es", "fa", "fi", "fr",
    "he", "hi", "hr", "ht", "hu", "id", "is", "it", "ja", "ko", "la", "lt", "ms", "ne",
    "nl", "no", "pa", "pl", "pt", "ro", "ru", "sa", "sk", "sr", "sv", "sw", "ta", "te",
    "th", "tl", "tr", "uk", "ur", "vi", "yue", "zh", "unknown",
]
KEYS = [
    "C major", "C# major", "Db major", "D major", "D# major", "Eb major",
    "E major", "F major", "F# major", "Gb major", "G major", "G# major",
    "Ab major", "A major", "A# major", "Bb major", "B major",
    "C minor", "C# minor", "Db minor", "D minor", "D# minor", "Eb minor",
    "E minor", "F minor", "F# minor", "Gb minor", "G minor", "G# minor",
    "Ab minor", "A minor", "A# minor", "Bb minor", "B minor",
]


@dataclass(frozen=True)
class TargetWorkflow:
    path: str
    source: str
    model: str
    display_model: str
    filename_prefix: str


TARGET_WORKFLOWS = (
    TargetWorkflow(
        "Music Generation/ACE-Step1_5_XL_SFT_Gemma4_e4B-AutoSongwriter-Genre-Selector.json",
        "Music Generation/ACE-Step1_5_XL_SFT_Gemma4_e4B-AutoSongwriter-POP-120-Cmajor.json",
        "Gemma4-e4B",
        "Gemma 4 e4B FP8 (lower VRAM)",
        "audio/ACE_Album/POP_Track",
    ),
    TargetWorkflow(
        "Music Generation/ACE-Step1_5_XL_SFT_Qwen3_5_4B-AutoSongwriter-Genre-Selector.json",
        "Music Generation/ACE-Step1_5_XL_SFT_Qwen3_5_4B-AutoSongwriter-POP-120-Cmajor.json",
        "Qwen3.5-4B",
        "Qwen 3.5 4B BF16 (quality)",
        "audio/ACE_Album/POP_Track",
    ),
)

_SOURCE_STEMS = (
    "AutoSongwriter-CLUB-126-Fsharpminor.json",
    "AutoSongwriter-DRIVE-108-Aminor.json",
    "AutoSongwriter-GLOW-96-Gmajor.json",
    "AutoSongwriter-NIGHT-84-Eminor.json",
    "AutoSongwriter-POP-120-Cmajor.json",
    "AutoSongwriter-RUSH-138-Dmajor.json",
    "Idea-to-Lyrics-to-Music.json",
)
SOURCE_WORKFLOWS = {
    f"Music Generation/ACE-Step1_5_XL_SFT_{model}-{suffix}"
    for model in ("Gemma4_e4B", "Qwen3_5_4B")
    for suffix in _SOURCE_STEMS
}
TARGET_PATHS = {target.path for target in TARGET_WORKFLOWS}


CUSTOM_NODE_OBJECT_INFO: dict[str, Any] = {
    "display_name": "DaW AutoSongwriter Genre Selector",
    "description": (
        "Selects one of six curated genre profiles or a new custom genre and emits the matching "
        "music direction, BPM, ACE-Step key/language, and output filename prefix."
    ),
    "input": {
        "required": {
            "profile": ["COMBO", {"options": PROFILE_LABELS}],
            "custom_genre_or_direction": ["STRING", {"multiline": True}],
            "custom_bpm": ["INT", {"default": 120, "min": 10, "max": 300}],
            "custom_key": ["COMBO", {"options": KEYS}],
            "lyrics_language": ["COMBO", {"options": LANGUAGES}],
        }
    },
    "input_order": {
        "required": [
            "profile", "custom_genre_or_direction", "custom_bpm", "custom_key", "lyrics_language"
        ]
    },
    "output": ["STRING", "INT", "COMBO", "COMBO", "STRING"],
    "output_name": ["music_direction", "bpm", "keyscale", "language", "filename_prefix"],
    "output_tooltips": [
        "Structured direction and selected metadata for the songwriter LLM.",
        "BPM for the ACE-Step encoder.",
        "Key scale for the ACE-Step encoder.",
        "Lyrics language for the ACE-Step encoder.",
        "Profile-specific Save Audio prefix.",
    ],
}


LYRICS_INSTRUCTIONS = """You are a professional songwriter preparing lyrics for ACE-Step 1.5.

Turn the supplied SONG IDEA and MUSICAL DIRECTION into one original, singable song for a target duration of about 180 seconds. The MUSICAL DIRECTION block contains the selected profile, requested lyrics language, and exact BPM, key, and time-signature metadata. Write the lyrics in that requested language and match the pacing to the metadata, but never print BPM, key, time signature, language code, or technical settings.

OUTPUT RULES:
- Output only the lyrics. No preamble, explanation, title heading, Markdown fence, analysis, <think> block, or notes outside the song.
- Write naturally and idiomatically in the requested language. Never copy or closely paraphrase an existing song, quote recognizable lyrics, or name an artist.
- Use structural labels such as [Intro], [Verse 1], [Pre-Chorus], [Chorus], [Verse 2], [Bridge], [Final Chorus], [Outro]. Section labels may include short performance or arrangement cues after a dash.
- Include at least one [Instrumental Break], [Solo], or clearly marked instrumental passage so the vocal is not continuous under a livestream.
- Keep most lines short and rhythmically singable. Prefer concrete images, actions, and details over abstract slogans.
- Build a clear emotional or narrative development. The chorus needs a memorable hook that is not merely the working title repeated.
- Avoid generic AI-song clichés, including endless fire, wings, destiny, neon hearts, breaking chains, touching the sky, being infinite, and vague darkness-versus-light language unless the specific story truly requires it.
- Do not force rhymes. Do not turn the lyrics into prose.
- Use the requested lyric density: full narrative usually 170-240 words; hook-forward usually 115-180 words; sparse usually 60-110 words.
- Keep the complete output under 3,500 characters so it remains comfortably within ACE-Step's lyric input.

The first block below is the SONG IDEA. The second block begins after MUSICAL DIRECTION."""


def _node(workflow: dict[str, Any], node_id: int) -> dict[str, Any]:
    return next(node for node in workflow["nodes"] if node.get("id") == node_id)


def _remove_generated_notes(workflow: dict[str, Any], target_ids: set[int]) -> None:
    workflow["nodes"] = [
        node for node in workflow.get("nodes", [])
        if not (
            node.get("properties", {}).get(v092.NOTE_PROPERTY) in target_ids
            and node.get("properties", {}).get("dawasteh_generated_note")
        )
    ]


def _workflow_integrity(workflow: dict[str, Any]) -> str:
    normalized = copy.deepcopy(workflow)
    normalized.get("extra", {}).get(MIGRATION_KEY, {}).pop("integrity_sha256", None)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_consolidated(workflow: dict[str, Any], target: TargetWorkflow) -> None:
    marker = workflow.get("extra", {}).get(MIGRATION_KEY, {})
    expected_hash = marker.get("integrity_sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError(f"{target.path}: v0.9.3 AutoSongwriter integrity marker is missing")
    actual_hash = _workflow_integrity(workflow)
    if actual_hash != expected_hash:
        raise ValueError(
            f"{target.path}: v0.9.3 AutoSongwriter integrity mismatch "
            f"(expected {expected_hash}, got {actual_hash})"
        )


def consolidate_workflow(source: dict[str, Any], target: TargetWorkflow) -> dict[str, Any]:
    """Return the deterministic v0.9.3 target for one songwriter model."""
    workflow = copy.deepcopy(source)
    marker = workflow.get("extra", {}).get(MIGRATION_KEY, {})
    if marker.get("version") == MIGRATION_VERSION:
        _validate_consolidated(workflow, target)
        return workflow

    old_selector = _node(workflow, 138)
    if old_selector.get("type") != "PixaromaPrompt":
        raise ValueError(f"{target.source}: node 138 is not the expected musical-direction prompt")
    encoder = _node(workflow, 94)
    if encoder.get("type") != "TextEncodeAceStepAudio1.5":
        raise ValueError(f"{target.source}: node 94 is not the expected ACE-Step encoder")

    existing_link_ids = [
        link[0] for link in workflow.get("links", [])
        if isinstance(link, list) and link and isinstance(link[0], int)
    ]
    bpm_link = max(existing_link_ids, default=0) + 1
    key_link = bpm_link + 1
    language_link = key_link + 1
    filename_link = language_link + 1

    old_selector.update({
        "type": CUSTOM_NODE_TYPE,
        "title": "2 · GENRE / PRESET — SELECT OR CUSTOMIZE",
        "size": [620, 420],
        "inputs": [
            {"name": "profile", "type": "COMBO", "link": None},
            {"name": "custom_genre_or_direction", "type": "STRING", "link": None},
            {"name": "custom_bpm", "type": "INT", "link": None},
            {"name": "custom_key", "type": "COMBO", "link": None},
            {"name": "lyrics_language", "type": "COMBO", "link": None},
        ],
        "outputs": [
            {"name": "music_direction", "type": "STRING", "links": [285]},
            {"name": "bpm", "type": "INT", "links": [bpm_link]},
            {"name": "keyscale", "type": "COMBO", "links": [key_link]},
            {"name": "language", "type": "COMBO", "links": [language_link]},
            {"name": "filename_prefix", "type": "STRING", "links": [filename_link]},
        ],
        "properties": {
            "Node name for S&R": CUSTOM_NODE_TYPE,
            "cnr_id": "ComfyUI-DaWasteh-AutoSongwriter",
        },
        "widgets_values": [PROFILE_LABELS[0], "", 120, "C major", "en"],
        "color": "#1f7a4c",
        "bgcolor": "#123d2b",
    })

    bpm_input = next(item for item in encoder["inputs"] if item.get("name") == "bpm")
    key_input = next(item for item in encoder["inputs"] if item.get("name") == "keyscale")
    language_input = next(item for item in encoder["inputs"] if item.get("name") == "language")
    save_audio = _node(workflow, 107)
    filename_input = next(item for item in save_audio["inputs"] if item.get("name") == "filename_prefix")
    linked_inputs = (bpm_input, key_input, language_input, filename_input)
    if any(item.get("link") is not None for item in linked_inputs):
        raise ValueError(f"{target.source}: ACE-Step metadata or output filename is already linked")
    bpm_input["link"] = bpm_link
    key_input["link"] = key_link
    language_input["link"] = language_link
    filename_input["link"] = filename_link
    workflow["links"].extend([
        [bpm_link, 138, 1, 94, encoder["inputs"].index(bpm_input), "INT"],
        [key_link, 138, 2, 94, encoder["inputs"].index(key_input), "COMBO"],
        [language_link, 138, 3, 94, encoder["inputs"].index(language_input), "COMBO"],
        [filename_link, 138, 4, 107, save_audio["inputs"].index(filename_input), "STRING"],
    ])

    _node(workflow, 141)["widgets_values"][0] = LYRICS_INSTRUCTIONS
    save_audio["widgets_values"][0] = target.filename_prefix
    _node(workflow, 149).update({
        "title": "AUTO-SONGWRITER · IDEA + GENRE SELECTOR",
        "widgets_values": [f"""# ACE Album Auto-Songwriter · one workflow per LLM

Edit the green **SONG IDEA** field, then choose one genre profile in the green **GENRE / PRESET** node.

Bundled choices: POP, GLOW, DRIVE, CLUB, NIGHT, RUSH, plus CUSTOM for any new genre. The selector sends its curated direction, exact BPM/key metadata, lyrics language, and profile-specific filename to the connected nodes.

For CUSTOM, enter the new genre or detailed musical direction and set custom BPM/key. With a bundled profile, that text is appended as optional extra direction. The language dropdown applies to every profile.

Then queue the workflow. It writes structured lyrics in the requested language, derives the English ACE-Step caption, unloads the songwriter LLM, generates a 180-second song, and saves it under `output/audio/ACE_Album/`.

**LLM:** {target.display_model}. The Voice LoRA is preserved; choose another LoRA or bypass it when needed. The seed is randomized; set it to fixed to reproduce a complete result."""],
    })
    _node(workflow, 150).update({
        "title": "Genre selector · preset metadata and custom mode",
        "widgets_values": ["""# Six curated profiles plus your own genre

The former per-genre files differed mainly in musical direction, BPM, key, filename, and explanatory text. This selector now keeps those settings together:

- POP · 120 BPM · C major
- GLOW · 96 BPM · G major
- DRIVE · 108 BPM · A minor
- CLUB · 126 BPM · F# minor
- NIGHT · 84 BPM · E minor
- RUSH · 138 BPM · D major
- CUSTOM · your text, BPM, and key

ACE-Step receives concrete linked BPM, key, and language values. Save Audio receives the profile-specific prefix (`POP_Track`, `GLOW_Track`, and so on; `CUSTOM_Track` for a new genre). CUSTOM replaces the former generic Idea-to-Lyrics workflow while keeping the newer two-stage lyrics-and-caption pipeline."""],
    })

    workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dawasteh-v093:{target.path}"))
    workflow["last_link_id"] = filename_link
    workflow.setdefault("extra", {}).setdefault("dawasteh_workflow_refinement", {}).update({
        "version": 3,
        "purpose": "ACE-Step 1.5 consolidated auto-songwriter",
        "prompt_model": target.model,
        "preset": "genre-selector",
    })
    workflow["extra"][MIGRATION_KEY] = {
        "version": MIGRATION_VERSION,
        "release": "v0.9.3",
        "source_workflows": 7,
        "bundled_profiles": 6,
        "custom_profile": True,
        "selector_node": CUSTOM_NODE_TYPE,
    }
    gpu = workflow["extra"].get("dawasteh_dual_gpu", {})
    gpu.update({
        "family": Path(target.path).stem,
        "source": f"workflows/{target.path}",
    })

    _remove_generated_notes(workflow, {94, 107, 138, 141})
    v092.OBJECT_INFO[CUSTOM_NODE_TYPE] = CUSTOM_NODE_OBJECT_INFO
    v092._rebuild_presentation(workflow, target.path)
    workflow["extra"][MIGRATION_KEY]["integrity_sha256"] = _workflow_integrity(workflow)
    return workflow


def desired_targets(source_root: Path = WORKFLOWS) -> dict[str, dict[str, Any]]:
    desired: dict[str, dict[str, Any]] = {}
    for target in TARGET_WORKFLOWS:
        target_path = source_root / Path(target.path)
        source_path = source_root / Path(target.source)
        if source_path.is_file():
            source = json.loads(source_path.read_text(encoding="utf-8-sig"))
        elif target_path.is_file():
            source = json.loads(target_path.read_text(encoding="utf-8-sig"))
        else:
            raise FileNotFoundError(f"missing both target {target.path} and source {target.source}")
        desired[target.path] = consolidate_workflow(source, target)
    return desired


def migrate_collection(destination: Path = WORKFLOWS, *, check: bool = False) -> tuple[int, int, int]:
    desired = desired_targets(destination)
    changed = 0
    for key, workflow in sorted(desired.items()):
        path = destination / Path(key)
        rendered = json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"
        current = path.read_text(encoding="utf-8-sig") if path.is_file() else None
        if current != rendered:
            changed += 1
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(rendered, encoding="utf-8")

    removed = 0
    for key in sorted(SOURCE_WORKFLOWS):
        path = destination / Path(key)
        if path.exists():
            removed += 1
            if not check:
                path.unlink()
    return len(desired), changed, removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows", type=Path, default=WORKFLOWS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    total, changed, removed = migrate_collection(args.workflows, check=args.check)
    print(f"targets={total} changed={changed} removed={removed} check={args.check}")
    return 1 if args.check and (changed or removed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
