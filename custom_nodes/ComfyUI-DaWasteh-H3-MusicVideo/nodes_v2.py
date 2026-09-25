"""v1.2.2 FastH3 music-video nodes: plan once, write MiniMax prompts, encode once, extend scene by scene.

Graph contract (see tools/build_h3_music_video_v122.py):

    Planner -> Prompt Writer (Qwen3.5) -> Encode Scenes (H3 text encoder, once)
        -> Scene 1: Scene Setup -> sampler -> Save Scene -> Pixaroma Pause gate
        -> Pixaroma Loop (scene_count - 1 rounds): Scene Setup -> sampler -> Save Scene
        -> Finalize (joins scenes, stream-copies the original audio)

Everything heavy is persisted in the project folder, so a restarted or resumed run skips
finished work: Prompt Writer and Encode Scenes request their model lazily only when their
results are missing, and Save Scene requests its latent (and therefore the whole sampler
chain) only for scenes that are not rendered yet.
"""
from __future__ import annotations

import gc
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

import comfy.audio
import comfy.model_management
import comfy.nested_tensor
import comfy.utils
import folder_paths
from comfy_api.latest import io, ui

from . import mv2
from .core import (
    atomic_write_json,
    count_video_frames,
    decode_analysis_mono,
    encode_images_to_h264,
    find_ffmpeg,
    lightweight_file_fingerprint,
    probe_audio_duration,
    read_json,
    run_command,
    sanitize_name,
    sha256_file,
)

CATEGORY = "DaWasteh/MiniMax H3/Music Video v2"
TAIL_ENCODE_VRAM = 14 * 1024 ** 3
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif"}
PROJECTS = "DaWasteh_H3_MusicVideo_v2"
CONTINUITY_OPTIONS = ["22", "5", "39"]
LANGUAGES = ["auto"] + list(mv2.LANGUAGE_TAGS)
WHISPER_MODELS = ["small", "base", "tiny", "medium"]
WRITER_MODES = ["Qwen3.5 LLM (empfohlen)", "Vorlage ohne LLM"]
TAG = "[DaWasteh H3 MV2]"


def _log(message: str) -> None:
    print(f"{TAG} {message}", flush=True)


def _song_options() -> list[str]:
    root = Path(folder_paths.get_input_directory())
    found = [str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS]
    return sorted(found, key=str.casefold) or ["song.mp3"]


def _manifest(plan: str) -> dict[str, Any]:
    if not plan or not os.path.isfile(plan):
        raise FileNotFoundError(f"Music-video plan not found: {plan!r}. Run the Planner node first.")
    manifest = read_json(plan)
    if manifest.get("schema") != mv2.SCHEMA:
        raise ValueError(f"{plan} is not a v1.2.2 music-video plan")
    return manifest


def _save(plan: str, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = time.time()
    atomic_write_json(plan, manifest)


def _project_dir(plan: str) -> Path:
    return Path(plan).parent


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _decode_window(ffmpeg: str, path: str, start: float, seconds: float, sample_rate: int = 48000) -> torch.Tensor:
    """Stereo float waveform [1, 2, N] of an exact window; before 0 / after the end is real silence."""
    want = int(round(seconds * sample_rate))
    lead = int(round(max(0.0, -start) * sample_rate))
    result = run_command([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, start):.6f}", "-i", path,
        "-t", f"{max(0.0, seconds - lead / sample_rate):.6f}", "-map", "0:a:0", "-vn", "-ac", "2", "-ar", str(sample_rate),
        "-f", "f32le", "pipe:1",
    ], timeout=600)
    data = np.frombuffer(result.stdout, dtype="<f4")
    data = data[: data.size - data.size % 2].reshape(-1, 2).T
    out = np.zeros((2, want), dtype=np.float32)
    usable = min(want - lead, data.shape[1])
    if usable > 0:
        out[:, lead:lead + usable] = data[:, :usable]
    return torch.from_numpy(out).unsqueeze(0)


def _whisper_words(samples_16k: np.ndarray, model_name: str, language: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    import whisper  # openai-whisper, shipped in the ComfyUI venv

    device = comfy.model_management.get_torch_device()
    model = whisper.load_model(model_name, device=device)
    try:
        options = {"word_timestamps": True, "fp16": False, "condition_on_previous_text": False}
        if language != "auto":
            options["language"] = language
        result = model.transcribe(samples_16k.astype(np.float32), **options)
    finally:
        del model
        gc.collect()
        comfy.model_management.soft_empty_cache()
    segments = [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]} for s in result.get("segments", [])]
    words = [{"word": w["word"], "start": float(w["start"]), "end": float(w["end"])}
             for s in result.get("segments", []) for w in s.get("words", []) or []]
    return words, segments, str(result.get("language") or "en")


# ---------------------------------------------------------------------------
# 1 · Planner
# ---------------------------------------------------------------------------

class DaWMV2Planner(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMV2Planner",
            display_name="MV 1 · Song + Lyrics Planner (Dauer, Szenen, Timing)",
            category=CATEGORY,
            description=("Measures the song, aligns the lyrics to the vocals with local Whisper, and splits the song into "
                         "scenes of different lengths at section and line boundaries. Any song length works."),
            inputs=[
                io.Combo.Input("song", options=_song_options(), upload=io.UploadType.audio,
                               tooltip="MP3/WAV/FLAC/M4A/OGG. The original file is copied and later muxed back untouched."),
                io.String.Input("lyrics", multiline=True, default="", tooltip="Lyrics with optional [Verse]/[Chorus] headers or [mm:ss.xx] timestamps. Empty = instrumental plan."),
                io.String.Input("video_idea", multiline=True, default="", tooltip="Your idea for the video: story, look, locations, mood."),
                io.Int.Input("width", default=864, min=256, max=2048, step=32),
                io.Int.Input("height", default=480, min=256, max=2048, step=32),
                io.String.Input("project_name", default="Music_Video"),
                io.Int.Input("seed", default=20260923, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True,
                             tooltip="Base seed; every scene gets its own derived seed. Change it to re-roll the whole video."),
                io.Float.Input("target_scene_seconds", default=7.0, min=3.0, max=13.0, step=0.25),
                io.Float.Input("min_scene_seconds", default=4.0, min=2.0, max=13.0, step=0.25, advanced=True),
                io.Float.Input("max_scene_seconds", default=9.0, min=4.0, max=14.0, step=0.25, advanced=True,
                               tooltip="864x480: up to 9 s keeps FastH3 fully in VRAM (<=243 H3 frames). Longer scenes load it partially and sample 2-4x slower."),
                io.Combo.Input("continuity_frames", options=CONTINUITY_OPTIONS, default="22", advanced=True,
                               tooltip="Frames of the previous scene frozen at the start of the next one (22 = 0.92 s)."),
                io.Combo.Input("lyrics_language", options=LANGUAGES, default="auto", advanced=True),
                io.Combo.Input("whisper_model", options=WHISPER_MODELS, default="small", advanced=True),
                io.Boolean.Input("resume_existing_scenes", default=True, advanced=True,
                                 tooltip="On: finished scenes of the same plan are reused. Off: every scene is rendered again."),
            ],
            outputs=[io.String.Output("plan"), io.Int.Output("scene_count"), io.Int.Output("loop_rounds"), io.String.Output("plan_text")],
        )

    @classmethod
    def fingerprint_inputs(cls, song, **kwargs):
        try:
            return lightweight_file_fingerprint(folder_paths.get_annotated_filepath(song)) + mv2.stable_hash(kwargs)
        except Exception:
            return float("nan")

    @classmethod
    def execute(cls, song, lyrics, video_idea, width, height, project_name, seed, target_scene_seconds,
                min_scene_seconds, max_scene_seconds, continuity_frames, lyrics_language, whisper_model,
                resume_existing_scenes) -> io.NodeOutput:
        if int(width) % 32 or int(height) % 32:
            raise ValueError("MiniMax H3 width and height must be multiples of 32")
        ffmpeg = find_ffmpeg()
        song_path = os.path.abspath(folder_paths.get_annotated_filepath(song))
        if not os.path.isfile(song_path):
            raise FileNotFoundError(song_path)
        split = mv2.SplitSettings(float(target_scene_seconds), float(min_scene_seconds), float(max_scene_seconds), int(continuity_frames))
        split.validate()
        name = sanitize_name(project_name, "Music_Video")
        key_payload = {
            "song": lightweight_file_fingerprint(song_path), "lyrics": lyrics, "idea": video_idea, "w": int(width),
            "h": int(height), "seed": int(seed), "split": split.__dict__, "lang": lyrics_language, "whisper": whisper_model,
        }
        fingerprint = mv2.stable_hash(key_payload, 12)
        project = Path(folder_paths.get_output_directory()) / PROJECTS / f"{name}_{fingerprint}"
        plan = project / "plan.json"
        if plan.is_file():
            manifest = read_json(plan)
            if manifest.get("schema") == mv2.SCHEMA and manifest.get("fingerprint") == fingerprint:
                if not resume_existing_scenes:
                    manifest["render_nonce"] = time.time_ns()
                    _save(str(plan), manifest)
                _log(f"Reusing plan {plan}")
                n = len(manifest["scenes"])
                return io.NodeOutput(str(plan), n, max(1, n - 1), mv2.plan_text(manifest))

        project.mkdir(parents=True, exist_ok=True)
        source_copy = project / ("source_audio" + (Path(song_path).suffix.lower() or ".audio"))
        shutil.copy2(song_path, source_copy)
        probed = probe_audio_duration(ffmpeg, str(source_copy))
        mono = decode_analysis_mono(ffmpeg, str(source_copy), 12000)
        duration = min(probed, mono.size / 12000.0) if abs(probed - mono.size / 12000.0) > 0.25 else mono.size / 12000.0
        features = mv2.audio_features(mono, 12000)
        sections, lines, timed = mv2.parse_lyrics(lyrics)
        alignment = {"method": "none", "coverage": 0.0, "language": "en"}
        extras: list[mv2.LyricLine] = []
        if lines and timed:
            for line_a, line_b in zip(lines, lines[1:] + [None]):
                line_a.end = min(duration, (line_b.start if line_b else line_a.start + 4.0) - 0.05)
            mv2._interpolate_missing(lines, duration)
            alignment = {"method": "lrc", "coverage": 1.0, "language": "en" if lyrics_language == "auto" else lyrics_language}
        elif lines:
            try:
                samples_16k = decode_analysis_mono(ffmpeg, str(source_copy), 16000)
                _log(f"Aligning {len(lines)} lyric lines with Whisper {whisper_model} ...")
                words, segments, language = _whisper_words(samples_16k, whisper_model, lyrics_language)
                coverage = mv2.align_lines_to_words(lines, words, duration)
                alignment = {"method": f"whisper-{whisper_model}", "coverage": round(coverage, 4), "language": language}
                if coverage < 0.25:
                    raise RuntimeError(f"only {coverage:.0%} of the lyric words were recognised")
                extras = mv2.add_unmatched_sung_passages(lines, segments)
            except Exception as exc:
                _log(f"Whisper alignment unavailable ({exc}); spreading lines over the vocal range instead.")
                active = np.nonzero(features["energy"] > 0.2)[0]
                first = active[0] / features["rate"] if active.size else 0.0
                last = active[-1] / features["rate"] if active.size else duration
                mv2.distribute_lines_evenly(lines, float(first), float(last))
                alignment = {"method": "estimate", "coverage": 0.0, "language": "en" if lyrics_language == "auto" else lyrics_language}
        sections = mv2.resolve_sections(sections, lines, duration)
        all_lines = sorted(lines + extras, key=lambda l: float(l.start or 0.0))
        scenes = mv2.build_scenes(duration, features, sections, all_lines, split)
        parts = mv2.story_parts(scenes)
        music_hint = f"The original song continues at about {features['bpm']:.0f} BPM."
        bible = mv2.default_bible(video_idea, [], parts, music_hint)
        previous_camera = previous_location = previous_part = None
        for scene in scenes:
            scene["shots"] = mv2.build_scene_shots(scene, all_lines, bible, index=scene["index"], previous_camera=previous_camera,
                                                   previous_location=previous_location, previous_part=previous_part)
            previous_camera, previous_location, previous_part = scene["shots"][-1]["camera"], scene["shots"][-1]["location"], scene["part"]
            scene["seed"] = mv2.scene_seed(int(seed), scene["index"])
            scene["prompt"] = mv2.assemble_prompt(scene, bible, index=scene["index"], total=len(scenes),
                                                  language=mv2.LANGUAGE_TAGS.get(alignment["language"], "English"))
            scene["prompt_source"] = "template"
        manifest = {
            "schema": mv2.SCHEMA, "fingerprint": fingerprint, "created_at": time.time(), "project_name": name,
            "project_dir": str(project), "song_name": Path(song_path).name, "source_audio": str(source_copy),
            "source_audio_sha256": sha256_file(str(source_copy)), "duration": duration, "total_frames": int(math.ceil(duration * mv2.FPS - 1e-9)),
            "width": int(width), "height": int(height), "seed": int(seed), "overlap_frames": int(continuity_frames),
            "video_idea": video_idea, "lyrics": lyrics, "alignment": alignment,
            "analysis": {"bpm": features["bpm"], "beats": len(features["beats"]), "energy_mean": float(np.mean(features["energy"]))},
            "sections": [s.as_dict() for s in sections], "lines": [l.as_dict() for l in all_lines],
            "bible": bible, "parts": parts, "scenes": scenes, "render_nonce": 0 if resume_existing_scenes else time.time_ns(),
        }
        _save(str(plan), manifest)
        _log(f"Planned {len(scenes)} scenes for {duration:.2f} s -> {plan}")
        n = len(scenes)
        return io.NodeOutput(str(plan), n, max(1, n - 1), mv2.plan_text(manifest))


# ---------------------------------------------------------------------------
# 2 · Prompt Writer
# ---------------------------------------------------------------------------

DEFAULT_LLM = "Qwen\\qwen3.5_4b_bf16.safetensors"
DEFAULT_H3_TE = "MiniMax H3\\qwen3vl_32b_minimax_h3_int8_convrot.safetensors"


def _text_encoder_options(preferred: str) -> list[str]:
    try:
        options = list(folder_paths.get_filename_list("text_encoders"))
    except Exception:
        options = []
    if preferred not in options:
        options.insert(0, preferred)
    return options


def _load_text_model(name: str, clip_type: str):
    """Load a text model privately. Only this node references it, so dropping the reference frees VRAM and
    host RAM at once; a cached CLIPLoader output would keep 8-26 GB alive (or offload it to host RAM)
    for the whole render loop. v1.2.4: read-only file mapping (no commit charge for the file itself)."""
    from . import h3_highres
    return h3_highres.load_clip_readonly(folder_paths.get_full_path_or_raise("text_encoders", name), clip_type)


def _release_text_model() -> None:
    gc.collect()
    comfy.model_management.cleanup_models()
    comfy.model_management.soft_empty_cache()


def _llm(clip, prompt: str, *, image=None, max_length: int = 400, temperature: float = 0.7, seed: int = 0,
         system_prompt: str = "") -> str:
    tokens = clip.tokenize(prompt, image=image, skip_template=False, min_length=1, thinking=False, system_prompt=system_prompt)
    ids = clip.generate(tokens, do_sample=True, max_length=max_length, temperature=temperature, top_k=64, top_p=0.95,
                        min_p=0.05, repetition_penalty=1.05, presence_penalty=0.0, seed=seed, mtp=True)
    text = clip.decode(ids)
    return text.split("</think>")[-1].strip()


def _image_key(image) -> str:
    if image is None:
        return "none"
    small = torch.nn.functional.interpolate(image[:1].movedim(-1, 1).float(), size=(32, 32), mode="area")
    return mv2.stable_hash((small * 255).round().to(torch.uint8).flatten().tolist(), 16)


class DaWMV2PromptWriter(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMV2PromptWriter",
            display_name="MV 2 · MiniMax Prompt Writer (Qwen3.5 · Idee + Lyrics + Charaktere)",
            category=CATEGORY,
            description=("Turns the video idea, the timed lyrics and up to three character sheets into one MiniMax H3 "
                         "prompt per scene (integrated_multimodal_description / overall_soundscape / non_diegetic_music), "
                         "with <d>-tagged lyrics for lip sync and varied shots, locations and camera moves."),
            inputs=[
                io.String.Input("plan", force_input=True),
                io.Combo.Input("mode", options=WRITER_MODES, default=WRITER_MODES[0]),
                io.Combo.Input("llm", options=_text_encoder_options(DEFAULT_LLM), default=DEFAULT_LLM,
                               tooltip="Qwen3.5 (4B recommended, vision capable for character sheets). Loaded only while prompts are written, then freed."),
                io.Float.Input("temperature", default=0.7, min=0.1, max=1.5, step=0.05, advanced=True),
                io.Int.Input("llm_seed", default=7, min=0, max=0xFFFFFFFF, advanced=True),
                io.Image.Input("character_1", optional=True, tooltip="Character sheet of the lead singer (optional)."),
                io.Image.Input("character_2", optional=True),
                io.Image.Input("character_3", optional=True),
            ],
            outputs=[io.String.Output("plan"), io.String.Output("prompts")],
        )

    @classmethod
    def _key(cls, manifest, mode, llm, temperature, llm_seed, images) -> str:
        return mv2.stable_hash({"fp": manifest["fingerprint"], "mode": mode, "llm": llm, "t": float(temperature), "seed": int(llm_seed),
                                "chars": [_image_key(i) for i in images], "v": mv2.PROMPT_VERSION})

    @classmethod
    def execute(cls, plan, mode, llm, temperature, llm_seed, character_1=None, character_2=None, character_3=None) -> io.NodeOutput:
        manifest = _manifest(plan)
        images = [character_1, character_2, character_3]
        key = cls._key(manifest, mode, llm, temperature, llm_seed, images)
        if manifest.get("prompts_key") == key:
            return io.NodeOutput(plan, _prompts_text(manifest))
        use_llm = mode == WRITER_MODES[0]
        llm_name = llm
        llm = _load_text_model(llm_name, "stable_diffusion") if use_llm else None
        try:
            return cls._write(plan, manifest, key, use_llm, llm, images, temperature, llm_seed)
        finally:
            del llm
            _release_text_model()

    @classmethod
    def _write(cls, plan, manifest, key, use_llm, llm, images, temperature, llm_seed) -> io.NodeOutput:
        scenes = manifest["scenes"]
        parts = mv2.story_parts(scenes)
        language = mv2.LANGUAGE_TAGS.get(manifest["alignment"].get("language", "en"), "English")
        lines = [mv2.LyricLine(l["text"], l["section"], l["start"], l["end"], l["source"]) for l in manifest["lines"]]
        progress = comfy.utils.ProgressBar(len(scenes) + 4)
        characters: list[str] = []
        for k, image in enumerate(i for i in images if i is not None):
            if use_llm:
                text = mv2.clean_sentence(_llm(llm, mv2.CHARACTER_REQUEST, image=image[:1], max_length=220, temperature=0.3, seed=int(llm_seed) + k), 700)
            else:
                text = f"the person shown in character sheet {k + 1}"
            characters.append(text.rstrip("."))
            _log(f"Character {k + 1}: {text}")
        progress.update(1)
        music_facts = f"{manifest['duration']:.0f} seconds, about {manifest['analysis']['bpm']:.0f} BPM"
        fallback = mv2.default_bible(manifest["video_idea"], characters, parts, f"The original song continues at about {manifest['analysis']['bpm']:.0f} BPM.")
        bible = fallback
        if use_llm:
            request = mv2.bible_llm_request(manifest["video_idea"], manifest["lyrics"], characters, parts, music_facts)
            raw = _llm(llm, request, max_length=700, temperature=float(temperature), seed=int(llm_seed), system_prompt=mv2.BIBLE_SYSTEM)
            bible = mv2.parse_bible_text(raw, fallback, parts)
            if characters:
                bible["singer"] = mv2.character_description(characters[0])
                bible["characters"] = characters
            _log("Bible:\n" + raw)
        progress.update(1)
        previous_camera = previous_location = previous_part = None
        previous_summary = ""
        for scene in scenes:
            scene["shots"] = mv2.build_scene_shots(scene, lines, bible, index=scene["index"], previous_camera=previous_camera,
                                                   previous_location=previous_location, previous_part=previous_part)
            source = "template"
            if use_llm:
                upcoming = next((s for s in scenes[scene["index"] + 1:] if s["part"] != scene["part"]), None)
                request = mv2.scene_llm_request(scene, bible, index=scene["index"], total=len(scenes),
                                                idea=manifest["video_idea"], previous_summary=previous_summary,
                                                next_location=bible["locations"].get(upcoming["part"]) if upcoming else None)
                try:
                    raw = _llm(llm, request, max_length=160 + 110 * len(scene["shots"]), temperature=float(temperature),
                               seed=int(llm_seed) + 100 + scene["index"], system_prompt=mv2.BIBLE_SYSTEM)
                    actions = mv2.parse_shot_text(raw, len(scene["shots"]))
                    for shot, action in zip(scene["shots"], actions):
                        if action:
                            shot["action"] = action
                    source = "llm" if any(actions) else "template (LLM output unparsable)"
                except Exception as exc:
                    source = f"template (LLM failed: {exc})"
            scene["prompt"] = mv2.assemble_prompt(scene, bible, index=scene["index"], total=len(scenes), language=language)
            scene["prompt_source"] = source
            previous_camera, previous_location, previous_part = scene["shots"][-1]["camera"], scene["shots"][-1]["location"], scene["part"]
            previous_summary = mv2.summarize_for_next(scene["shots"])
            progress.update(1)
        manifest["bible"] = bible
        manifest["prompts_key"] = key
        _save(plan, manifest)
        return io.NodeOutput(plan, _prompts_text(manifest))


def _prompts_text(manifest: dict[str, Any]) -> str:
    rows = [f"STYLE: {manifest['bible'].get('style')}", f"SINGER: {manifest['bible'].get('singer')}", ""]
    for scene in manifest["scenes"]:
        rows.append(f"=== Szene {scene['index'] + 1} · {mv2.fmt_ts(scene['start'])}–{mv2.fmt_ts(scene['end'])} · "
                    f"{scene['section']} · {scene.get('prompt_source')}\n{scene['prompt']}\n")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# 3 · Encode all scene prompts once
# ---------------------------------------------------------------------------

def _cond_key(scene: dict[str, Any], text_encoder: str, prefix: str = "") -> str:
    payload = {"prompt": scene["prompt"], "te": text_encoder, "v": 1}
    if prefix:  # v1.2.4 LoRA trigger; without one the v1.2.2 keys stay valid
        payload["prefix"] = prefix
    return mv2.stable_hash(payload)


def _model_prefix(model_info: str | None) -> tuple[str, str]:
    """model_info JSON from MV 0 -> (prompt prefix for the LoRA trigger word, model signature for resume keys)."""
    if not model_info:
        return "", ""
    info = json.loads(model_info)
    trigger = str(info.get("trigger") or "").strip()
    prefix = f"{trigger}, " if trigger and info.get("lora") else ""
    return prefix, mv2.stable_hash(info)


def _cond_path(plan: str, index: int) -> Path:
    return _project_dir(plan) / "conditioning" / f"scene_{index:04d}.pt"


class DaWMV2EncodeScenes(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMV2EncodeScenes",
            display_name="MV 3 · H3 Text Encoder · alle Szenen einmal",
            category=CATEGORY,
            description=("Encodes every scene prompt once with the Qwen3-VL-32B H3 text encoder and stores the "
                         "conditioning on disk. The render loop then never needs the 26 GB text encoder again."),
            inputs=[
                io.String.Input("plan", force_input=True),
                io.Combo.Input("text_encoder", options=_text_encoder_options(DEFAULT_H3_TE), default=DEFAULT_H3_TE,
                               tooltip="MiniMax H3 Qwen3-VL-32B text encoder. Loaded once for all scenes, then freed completely."),
                io.String.Input("model_info", force_input=True, optional=True,
                                tooltip="From MV 0: the LoRA trigger word is put in front of every scene prompt, and a "
                                        "different model/LoRA/strength re-renders the scenes instead of resuming them."),
            ],
            outputs=[io.String.Output("plan")],
        )

    @classmethod
    def _missing(cls, plan: str, text_encoder: str, prefix: str = "") -> list[int]:
        manifest = _manifest(plan)
        return [s["index"] for s in manifest["scenes"]
                if s.get("cond_key") != _cond_key(s, text_encoder, prefix) or not _cond_path(plan, s["index"]).is_file()]

    @classmethod
    def execute(cls, plan, text_encoder, model_info=None) -> io.NodeOutput:
        prefix, model_key = _model_prefix(model_info)
        missing = cls._missing(plan, text_encoder, prefix)
        manifest = _manifest(plan)
        if missing:
            clip = _load_text_model(text_encoder, "minimax")
            progress = comfy.utils.ProgressBar(len(missing))
            for index in missing:
                scene = manifest["scenes"][index]
                cond = clip.encode_from_tokens_scheduled(clip.tokenize(prefix + scene["prompt"]))
                cond = [[c[0].detach().cpu(), {k: (v.detach().cpu() if torch.is_tensor(v) else v) for k, v in c[1].items()}] for c in cond]
                path = _cond_path(plan, index)
                path.parent.mkdir(parents=True, exist_ok=True)
                torch.save(cond, str(path) + ".tmp")
                os.replace(str(path) + ".tmp", path)
                scene["cond_key"] = _cond_key(scene, text_encoder, prefix)
                progress.update(1)
            _log(f"Encoded {len(missing)} scene prompts{' with trigger ' + prefix.strip(', ') if prefix else ''}; releasing the text encoder")
            del clip
            _release_text_model()
        if missing or manifest.get("text_encoder") != text_encoder or manifest.get("prompt_prefix", "") != prefix \
                or manifest.get("model_key", "") != model_key:
            manifest.update({"text_encoder": text_encoder, "prompt_prefix": prefix, "model_key": model_key})
            _save(plan, manifest)
        return io.NodeOutput(plan)


# ---------------------------------------------------------------------------
# Scene bookkeeping shared by Setup / Save
# ---------------------------------------------------------------------------

def _render_key(manifest: dict[str, Any], index: int) -> str:
    scene = manifest["scenes"][index]
    previous = _render_key(manifest, index - 1) if index > 0 and scene["prefix_frames"] else ""
    payload = {
        "prompt": scene["prompt"], "seed": scene["seed"], "w": manifest["width"], "h": manifest["height"],
        "gen": scene["gen_frames"], "prefix": scene["prefix_frames"], "audio": scene["audio_start_frame"],
        "frames": scene["frames"], "previous": previous, "nonce": manifest.get("render_nonce", 0),
    }
    if manifest.get("model_key"):  # v1.2.4: another model / LoRA / strength / trigger renders the scenes again
        payload.update({"model": manifest["model_key"], "prompt_prefix": manifest.get("prompt_prefix", "")})
    return mv2.stable_hash(payload)


def _scene_files(plan: str, index: int) -> dict[str, Path]:
    root = _project_dir(plan)
    return {
        "video": root / "scenes" / f"scene_{index:04d}.mp4",
        "tail": root / "scenes" / f"scene_{index:04d}_tail_latent.pt",
        "sheet": root / "scenes" / f"scene_{index:04d}_sheet.png",
        "preview": root / "preview" / f"scene_{index:04d}_with_audio.mp4",
    }


def _scene_done(plan: str, manifest: dict[str, Any], index: int) -> bool:
    scene = manifest["scenes"][index]
    files = _scene_files(plan, index)
    return (scene.get("render_key") == _render_key(manifest, index) and files["video"].is_file()
            and files["tail"].is_file() and scene.get("verified_frames") == scene["frames"])


def _unload_vaes(*vaes) -> None:
    """Drop the VAEs from VRAM so FastH3 is loaded completely before the next sampling. Measured: with the 5 GB
    video VAE left resident, ComfyUI loads FastH3 only partially (150 MB offloaded) and sampling slows ~5x."""
    for vae in vaes:
        patcher = getattr(vae, "patcher", None)
        if patcher is not None:
            comfy.model_management.unload_model_and_clones(patcher)
    comfy.model_management.soft_empty_cache()


def _resolve_index(manifest: dict[str, Any], scene_index: int, index_offset: int) -> int:
    return int(scene_index) + int(index_offset)


DEFAULT_FASTH3 = "MiniMax H3\\fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors"
DEFAULT_REALISM_LORA = "MiniMax H3\\h3-realism-people-t2v-i2v-r2v.safetensors"
DEFAULT_TRIGGER = "r34l1sm"
NO_LORA = "none"


def _file_options(folder: str, preferred: str, first: list[str] | None = None) -> list[str]:
    try:
        options = list(folder_paths.get_filename_list(folder))
    except Exception:
        options = []
    if preferred not in options and preferred != NO_LORA:
        options.insert(0, preferred)
    return (first or []) + options


class DaWMV2LoadModel(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMV2LoadModel",
            display_name="MV 0 · FastH3 + Realismus-LoRA (RAM-schonend, hohe Auflösung)",
            category=CATEGORY,
            description=("Loads FastH3 from a read-only file mapping (Windows does not charge the 22 GB file to the "
                         "commit limit), applies an optional LoRA and, above ~65k tokens (e.g. 1920x1088), keeps "
                         "enough VRAM free for the activations of every extend scene."),
            inputs=[
                io.Combo.Input("unet_name", options=_file_options("diffusion_models", DEFAULT_FASTH3), default=DEFAULT_FASTH3),
                io.Combo.Input("lora_name", options=_file_options("loras", DEFAULT_REALISM_LORA, [NO_LORA]),
                               default=DEFAULT_REALISM_LORA,
                               tooltip="MiniMax H3 LoRA (models/loras). 'none' = plain FastH3."),
                io.Float.Input("lora_strength", default=0.8, min=-2.0, max=2.0, step=0.05,
                               tooltip="fal Realism People: 1.0 intended, 0.6-0.8 lighter. FastH3 is an 8-step "
                                       "distillate, the LoRA was trained on H3 FL2VA."),
                io.String.Input("trigger_word", default=DEFAULT_TRIGGER,
                                tooltip="Put in front of every scene prompt while a LoRA is active (fal Realism People: r34l1sm). "
                                        "Empty = no trigger."),
                io.Boolean.Input("high_resolution_memory", default=True, advanced=True,
                                 tooltip="Above 65k tokens: allocator without fragmentation, MLP in token chunks, "
                                         "weights moved out of VRAM when the activations need the space. "
                                         "864x480 is not affected."),
            ],
            outputs=[io.Model.Output("model"), io.String.Output("model_info")],
        )

    @classmethod
    def execute(cls, unet_name, lora_name, lora_strength, trigger_word, high_resolution_memory) -> io.NodeOutput:
        import nodes as comfy_nodes
        from . import h3_highres

        path = folder_paths.get_full_path_or_raise("diffusion_models", unet_name)
        model = h3_highres.load_diffusion_model_readonly(path)
        use_lora = lora_name != NO_LORA and float(lora_strength) != 0.0
        if use_lora:
            model = comfy_nodes.LoraLoaderModelOnly().load_lora_model_only(model, lora_name, float(lora_strength))[0]
        if high_resolution_memory:
            h3_highres.install_patches()
            model = h3_highres.attach(model)
        info = {"model": unet_name, "lora": lora_name if use_lora else None,
                "strength": round(float(lora_strength), 4) if use_lora else 0.0,
                "trigger": trigger_word.strip() if use_lora else ""}
        _log(f"MV 0: {unet_name} read-only" + (f" + LoRA {lora_name} @ {lora_strength}" if use_lora else ""))
        return io.NodeOutput(model, json.dumps(info, sort_keys=True))


class DaWMV2SceneSetup(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMV2SceneSetup",
            display_name="MV 4 · Szene vorbereiten · Song-Audio + Extend (letzte Frames)",
            category=CATEGORY,
            description=("Loads the pre-encoded prompt of one scene and builds its H3 latent: the original song audio of "
                         "the scene is frozen in the audio stream (lip sync), and for every scene after the first the last "
                         "frames of the previous scene are frozen at the start of the video stream (seamless extend)."),
            inputs=[
                io.String.Input("plan", force_input=True),
                io.Int.Input("scene_index", default=0, min=0, max=100000),
                io.Int.Input("index_offset", default=0, min=0, max=100000, advanced=True),
                io.Vae.Input("vae"), io.Vae.Input("audio_vae"),
            ],
            outputs=[io.Conditioning.Output("positive"), io.Latent.Output("latent"), io.Int.Output("seed"), io.String.Output("info")],
        )

    @classmethod
    def execute(cls, plan, scene_index, index_offset, vae, audio_vae) -> io.NodeOutput:
        from comfy_extras.nodes_minimax_h3 import temporal_shape

        manifest = _manifest(plan)
        index = _resolve_index(manifest, scene_index, index_offset)
        if index >= len(manifest["scenes"]):
            raise IndexError(f"Scene {index + 1} does not exist; the plan has {len(manifest['scenes'])} scenes")
        scene = manifest["scenes"][index]
        cond_file = _cond_path(plan, index)
        if scene.get("cond_key") != _cond_key(scene, manifest.get("text_encoder", ""), manifest.get("prompt_prefix", "")) \
                or not cond_file.is_file():
            raise RuntimeError(f"Scene {index + 1} has no current conditioning; run 'MV 3 · H3 Text Encoder' first")
        positive = torch.load(str(cond_file), map_location="cpu", weights_only=False)

        width, height, gen = manifest["width"], manifest["height"], scene["gen_frames"]
        frame_count, latent_t, audio_t = temporal_shape(gen)
        device = comfy.model_management.intermediate_device()
        video = torch.zeros([1, 24, latent_t, height // 16, width // 16], device=device)
        video_mask = torch.ones_like(video)

        prefix = int(scene["prefix_frames"])
        if prefix:
            tail_file = _scene_files(plan, index - 1)["tail"]
            if not tail_file.is_file():
                raise RuntimeError(f"Scene {index} (previous) has no saved continuity latent: {tail_file}")
            z = torch.load(str(tail_file), map_location="cpu", weights_only=True).to(device=device, dtype=video.dtype)
            if z.ndim != 5 or z.shape[1] != 24 or z.shape[3] != height // 16 or z.shape[4] != width // 16:
                raise RuntimeError(f"Continuity latent {tuple(z.shape)} does not match {width}x{height}")
            t_p = min(int(z.shape[2]), latent_t)
            video[:, :, :t_p] = z[:, :, :t_p]
            video_mask[:, :, :t_p] = 0.0

        ffmpeg = find_ffmpeg()
        start = scene["audio_start_frame"] / mv2.FPS
        waveform = _decode_window(ffmpeg, manifest["source_audio"], start, frame_count / mv2.FPS)
        vae_rate = int(getattr(audio_vae, "audio_sample_rate", 32000))
        if vae_rate != 48000:
            waveform = comfy.audio.resample(waveform, 48000, vae_rate)
        audio = audio_vae.encode(waveform.movedim(1, -1)).to(device=device, dtype=torch.float32)
        if audio.shape[-1] > audio_t:
            audio = audio[..., :audio_t]
        elif audio.shape[-1] < audio_t:
            audio = torch.cat([audio, audio[..., -1:].repeat_interleave(audio_t - audio.shape[-1], dim=-1)], dim=-1)

        _unload_vaes(vae, audio_vae)
        latent = {
            "samples": comfy.nested_tensor.NestedTensor((video, audio)),
            "noise_mask": comfy.nested_tensor.NestedTensor((video_mask, torch.zeros_like(audio))),
        }
        info = (f"Szene {index + 1}/{len(manifest['scenes'])} · {mv2.fmt_ts(scene['start'])}–{mv2.fmt_ts(scene['end'])} · "
                f"{scene['frames']} neue Frames + {prefix} Übergang = {gen} H3-Frames · Seed {scene['seed']}")
        _log(info)
        return io.NodeOutput(positive, latent, int(scene["seed"]), info)


def _contact_sheet(frames: torch.Tensor, count: int = 8) -> Image.Image:
    total = int(frames.shape[0])
    picks = [min(total - 1, round(i * (total - 1) / (count - 1))) for i in range(count)]
    tiles = [Image.fromarray(frames[p, ..., :3].mul(255).round().clamp(0, 255).to(torch.uint8).cpu().numpy()) for p in picks]
    w, h = tiles[0].size
    scale = min(1.0, 480 / w)
    tw, th = max(2, int(w * scale)), max(2, int(h * scale))
    cols = 4
    sheet = Image.new("RGB", (cols * tw, math.ceil(count / cols) * th))
    for k, tile in enumerate(tiles):
        sheet.paste(tile.resize((tw, th), Image.Resampling.LANCZOS), ((k % cols) * tw, (k // cols) * th))
    return sheet


def _pil_to_image(image: Image.Image) -> torch.Tensor:
    return torch.from_numpy(np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0).unsqueeze(0)


def _preview_ui(path: Path):
    try:
        relative = path.resolve().relative_to(Path(folder_paths.get_output_directory()).resolve())
        sub = str(relative.parent).replace("\\", "/")
        return ui.PreviewVideo([ui.SavedResult(relative.name, "" if sub == "." else sub, io.FolderType.output)])
    except Exception:
        return None


class DaWMV2SaveScene(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMV2SaveScene",
            display_name="MV 5 · Szene speichern · Vorschau mit Originalton",
            category=CATEGORY,
            description=("Decodes one scene, keeps exactly its new frames, stores the continuity frames for the next "
                         "extend and shows a preview with the original song audio. Finished scenes of the same plan "
                         "are skipped without sampling (resume)."),
            inputs=[
                io.String.Input("plan", force_input=True),
                io.Int.Input("scene_index", default=0, min=0, max=100000),
                io.Int.Input("index_offset", default=0, min=0, max=100000, advanced=True),
                io.Vae.Input("vae"),
                io.Latent.Input("latent", lazy=True, optional=True),
                io.AnyType.Input("after", optional=True, tooltip="Ordering token: the previous scene or the approval gate."),
            ],
            outputs=[io.String.Output("token"), io.Image.Output("preview"), io.String.Output("info")],
            is_output_node=True,
        )

    @classmethod
    def check_lazy_status(cls, plan, scene_index, index_offset, vae, latent=None, after=None):
        manifest = _manifest(plan)
        index = _resolve_index(manifest, scene_index, index_offset)
        if index >= len(manifest["scenes"]) or latent is not None or _scene_done(plan, manifest, index):
            return []
        return ["latent"]

    @classmethod
    def execute(cls, plan, scene_index, index_offset, vae, latent=None, after=None) -> io.NodeOutput:
        manifest = _manifest(plan)
        index = _resolve_index(manifest, scene_index, index_offset)
        total = len(manifest["scenes"])
        if index >= total:
            return io.NodeOutput(f"{plan}|end", torch.zeros(1, 64, 64, 3), f"Keine Szene {index + 1} (Plan hat {total}).")
        files = _scene_files(plan, index)
        scene = manifest["scenes"][index]
        if latent is None:
            if not _scene_done(plan, manifest, index):
                raise RuntimeError(f"Scene {index + 1} is not rendered and no latent was supplied")
            sheet = Image.open(files["sheet"]) if files["sheet"].is_file() else Image.new("RGB", (64, 64))
            info = f"Szene {index + 1}/{total} bereits fertig (übersprungen): {files['video']}"
            _log(info)
            ui_preview = _preview_ui(files["preview"]) if files["preview"].is_file() else None
            token = f"{plan}|{index}|{scene['render_key']}"
            return io.NodeOutput(token, _pil_to_image(sheet), info, ui=ui_preview) if ui_preview else io.NodeOutput(token, _pil_to_image(sheet), info)

        samples = latent["samples"]
        video_latent = samples.unbind()[0] if getattr(samples, "is_nested", False) else samples
        images = vae.decode(video_latent)
        if images.ndim == 5:
            images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
        prefix, new = int(scene["prefix_frames"]), int(scene["frames"])
        if images.shape[0] < prefix + new:
            raise RuntimeError(f"Decoded {images.shape[0]} frames, need {prefix + new}")
        used = images[prefix:prefix + new]
        del images
        ffmpeg = find_ffmpeg()
        files["video"].parent.mkdir(parents=True, exist_ok=True)
        files["preview"].parent.mkdir(parents=True, exist_ok=True)
        encode_images_to_h264(ffmpeg, used, new, str(files["video"]), crf=15.0, preset="medium")
        overlap = int(manifest["overlap_frames"])
        tail = used[max(0, new - overlap):new, ..., :3].contiguous()
        # ComfyUI budgets ~1 GB for an H3 video-VAE encode; 22 frames at 864x480 allocate >7 GB at once.
        # Make room explicitly (FastH3 is partially offloaded and reloaded for the next scene by ComfyUI).
        comfy.model_management.free_memory(TAIL_ENCODE_VRAM, getattr(vae, "device", None) or comfy.model_management.get_torch_device())
        try:
            tail_latent = vae.encode(tail).detach().to("cpu", dtype=torch.float32)
        except torch.OutOfMemoryError:
            _log("Continuity encode ran out of VRAM; unloading all models and retrying once")
            comfy.model_management.unload_all_models()
            gc.collect()
            comfy.model_management.soft_empty_cache()
            tail_latent = vae.encode(tail).detach().to("cpu", dtype=torch.float32)
        torch.save(tail_latent, str(files["tail"]) + ".tmp")
        os.replace(str(files["tail"]) + ".tmp", files["tail"])
        del tail
        sheet = _contact_sheet(used)
        sheet.save(files["sheet"])
        verified = count_video_frames(ffmpeg, str(files["video"]))
        if verified != new:
            raise RuntimeError(f"Scene {index + 1}: encoded {verified} frames instead of {new}")
        run_command([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(files["video"]), "-ss", f"{scene['start']:.6f}",
            "-t", f"{new / mv2.FPS:.6f}", "-i", manifest["source_audio"], "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(files["preview"]),
        ], timeout=600)
        scene.update({"render_key": _render_key(manifest, index), "verified_frames": verified, "completed_at": time.time()})
        _save(plan, manifest)
        del used
        gc.collect()
        _unload_vaes(vae)
        info = f"Szene {index + 1}/{total} gespeichert: {files['video']} ({verified} Frames)"
        _log(info)
        token = f"{plan}|{index}|{scene['render_key']}"
        ui_preview = _preview_ui(files["preview"])
        if ui_preview:
            return io.NodeOutput(token, _pil_to_image(sheet), info, ui=ui_preview)
        return io.NodeOutput(token, _pil_to_image(sheet), info)


# ---------------------------------------------------------------------------
# 6 · Finalize
# ---------------------------------------------------------------------------

def _audio_codec(path: str) -> str:
    try:
        import av
        with av.open(path) as container:
            return str(container.streams.audio[0].codec_context.name)
    except Exception:
        return "unknown"


class DaWMV2Finalize(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMV2Finalize",
            display_name="MV 6 · Fertiges Musikvideo · Originalton unverändert",
            category=CATEGORY,
            description=("Joins all scenes without re-encoding and muxes the original song file stream-copied "
                         "(-c:a copy), so the audio is bit-identical to the input. MP3/AAC go into MP4, other codecs into MKV."),
            inputs=[
                io.String.Input("plan", force_input=True),
                io.AnyType.Input("after", optional=True, tooltip="Token of the last scene (Loop End)."),
                io.Combo.Input("container", options=["auto", "mp4", "mkv"], default="auto"),
            ],
            outputs=[io.String.Output("final_file")],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, plan, container, after=None) -> io.NodeOutput:
        manifest = _manifest(plan)
        missing = [s["index"] + 1 for s in manifest["scenes"] if not _scene_done(plan, manifest, s["index"])]
        if missing:
            raise RuntimeError(f"Scenes not rendered yet: {missing[:20]}. Press Continue / run the workflow again.")
        ffmpeg = find_ffmpeg()
        root = _project_dir(plan)
        concat = root / "concat.txt"
        concat.write_text("".join(f"file '{_scene_files(plan, s['index'])['video'].as_posix()}'\n" for s in manifest["scenes"]), encoding="utf-8")
        silent = root / "joined_video_silent.mp4"
        run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                     "-an", "-c:v", "copy", str(silent)], timeout=7200)
        frames = count_video_frames(ffmpeg, str(silent))
        codec = _audio_codec(manifest["source_audio"])
        suffix = container if container != "auto" else ("mp4" if codec in {"mp3", "aac", "mp3float", "alac"} else "mkv")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        final = Path(folder_paths.get_output_directory()) / "video" / "DaWasteh_MusicVideo" / f"{manifest['project_name']}_{stamp}.{suffix}"
        final.parent.mkdir(parents=True, exist_ok=True)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", manifest["source_audio"],
                   "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy"]
        if suffix == "mp4":
            command += ["-movflags", "+faststart"]
        try:
            run_command(command + [str(final)], timeout=7200)
        except RuntimeError as exc:
            if suffix != "mp4":
                raise
            final = final.with_suffix(".mkv")
            run_command(command[:-2] + [str(final)], timeout=7200)
            _log(f"MP4 rejected audio codec {codec}; wrote MKV instead ({exc})")
        manifest["final_output"] = str(final)
        manifest["final_frames"] = frames
        manifest["completed_at"] = time.time()
        _save(plan, manifest)
        _log(f"COMPLETE {final} · {frames} frames ({frames / mv2.FPS:.2f} s) · audio {codec} stream-copied")
        preview = _preview_ui(final)
        return io.NodeOutput(str(final), ui=preview) if preview else io.NodeOutput(str(final))


V2_NODES = [DaWMV2Planner, DaWMV2PromptWriter, DaWMV2EncodeScenes, DaWMV2LoadModel, DaWMV2SceneSetup, DaWMV2SaveScene,
            DaWMV2Finalize]
