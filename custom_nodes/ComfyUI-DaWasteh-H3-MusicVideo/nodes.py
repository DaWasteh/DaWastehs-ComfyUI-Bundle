from __future__ import annotations

import gc
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import folder_paths
import nodes as comfy_nodes
import comfy.model_management
from comfy_api.latest import ComfyExtension, io, ui

from .core import (
    BOTH_REFERENCES,
    IDENTITY_LOCK,
    PREVIOUS_FRAME_CONTINUITY,
    analyze_song_and_plan_segments,
    atomic_write_json,
    build_deterministic_prompts,
    build_finalize_api_prompt,
    build_segment_api_prompt,
    concat_and_mux_project,
    count_video_frames,
    decode_audio_for_comfy,
    encode_images_to_h264,
    extract_segment_audio,
    find_ffmpeg,
    get_active_prompt_ids,
    lightweight_file_fingerprint,
    load_image_tensor,
    query_local_llm_scene_prompts,
    queue_prompt,
    read_json,
    sanitize_name,
    save_canonical_reference_frame,
    save_reference_image_from_input,
    save_reference_tensor,
    segment_files_valid,
    sha256_file,
    update_manifest,
)

CATEGORY = "DaWasteh/MiniMax H3/Music Video"
NONE_IMAGE = "NONE — audio + text only"
DEFAULT_DIFFUSION = r"MiniMax H3\minimax_h3_ref2va_pruned_int8_convrot.safetensors"
DEFAULT_TEXT_ENCODER = r"MiniMax H3\qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
DEFAULT_VIDEO_VAE = r"MiniMax H3\minimax_h3_video_vae_fp16.safetensors"
DEFAULT_AUDIO_VAE = r"MiniMax H3\minimax_h3_audio_vae_fp32.safetensors"
DEFAULT_TURBO_LORA = r"MiniMax H3\minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"

_AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif", ".mp4", ".mkv", ".mov", ".webm"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _input_files(extensions: set[str]) -> list[str]:
    root = Path(folder_paths.get_input_directory())
    root.mkdir(parents=True, exist_ok=True)
    result: list[str] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in extensions:
            result.append(str(path.relative_to(root)).replace("\\", "/"))
    return sorted(result, key=str.casefold)


def _song_options() -> list[str]:
    return _input_files(_AUDIO_EXTENSIONS) or ["INTRO_SONG.wav"]


def _image_options() -> list[str]:
    return [NONE_IMAGE] + _input_files(_IMAGE_EXTENSIONS)


def _model_options(folder: str, preferred: str) -> tuple[list[str], str]:
    try:
        options = list(folder_paths.get_filename_list(folder))
    except Exception:
        options = []
    if preferred not in options:
        options.insert(0, preferred)
    return options, preferred


def _resolve_input(value: str) -> str:
    path = os.path.abspath(folder_paths.get_annotated_filepath(value))
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Input file not found: {path}")
    return path


def _required_node_check(spectrum_enabled: bool, dual_gpu: bool = False) -> None:
    required = {
        "CLIPLoader", "VAELoader", "UNETLoader", "MiniMaxH3SigmaShift", "MiniMaxH3ReferenceToVideo",
        "RandomNoise", "BasicGuider", "KSamplerSelect", "BasicScheduler", "SamplerCustomAdvanced", "VAEDecode",
        "LoraLoaderModelOnly",
    }
    if spectrum_enabled:
        required.add("SpectrumApplyMiniMaxH3")
    if dual_gpu:
        required.update({"SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"})
    missing = sorted(name for name in required if name not in comfy_nodes.NODE_CLASS_MAPPINGS)
    if missing:
        raise RuntimeError(
            "Required nodes are not loaded: " + ", ".join(missing) + ". Update ComfyUI, install/enable "
            "ComfyUI-Spectrum-MiniMax-H3 when Spectrum is enabled, then restart ComfyUI."
        )


def _project_fingerprint(audio_path: str, reference_path: str | None, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(lightweight_file_fingerprint(audio_path).encode())
    digest.update((lightweight_file_fingerprint(reference_path) if reference_path else "NO_REFERENCE_IMAGE").encode())
    digest.update(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return digest.hexdigest()


def _active_project_prompt_ids(manifest: dict[str, Any]) -> set[str]:
    active = get_active_prompt_ids(str(manifest.get("server_address", "127.0.0.1:8188")))
    known = {str(value) for value in manifest.get("queued_prompt_ids", []) if value}
    return active.intersection(known)


def _queue_next_work_item(manifest_path: str) -> str:
    ffmpeg = find_ffmpeg()
    manifest = read_json(manifest_path)
    valid = segment_files_valid(ffmpeg, manifest)
    server = str(manifest.get("server_address", "127.0.0.1:8188"))
    active = get_active_prompt_ids(server)

    if all(valid):
        final_path = str(manifest["final_output_path"])
        if os.path.isfile(final_path) and os.path.getsize(final_path) >= 1024:
            def mark_complete(value):
                value["status"] = "complete"
            update_manifest(manifest_path, mark_complete)
            return f"Project already complete: {final_path}"
        existing = str(manifest.get("finalizer_prompt_id") or "")
        if existing and existing in active:
            return f"Finalizer already queued/running: {existing}"
        response = queue_prompt(server, build_finalize_api_prompt(manifest_path))
        prompt_id = str(response["prompt_id"])
        def mark_finalizer(value):
            value["finalizer_prompt_id"] = prompt_id
            value.setdefault("queued_prompt_ids", []).append(prompt_id)
            value["status"] = "finalizing"
        update_manifest(manifest_path, mark_finalizer)
        return f"All scenes complete; queued finalizer {prompt_id}"

    next_index = valid.index(False)
    if manifest["settings"]["continuity"] and next_index > 0 and not valid[next_index - 1]:
        raise RuntimeError(f"Continuity invariant failed: scene {next_index} is missing its preceding valid scene")
    entry = manifest["segments"][next_index]
    existing = str(entry.get("prompt_id") or "")
    if existing and existing in active:
        return f"Scene {next_index + 1} already queued/running: {existing}"
    response = queue_prompt(server, build_segment_api_prompt(manifest_path, next_index, manifest))
    prompt_id = str(response["prompt_id"])
    def mark_scene(value):
        segment = value["segments"][next_index]
        segment["status"] = "queued"
        segment["prompt_id"] = prompt_id
        value.setdefault("queued_prompt_ids", []).append(prompt_id)
        value["status"] = "rendering"
    update_manifest(manifest_path, mark_scene)
    return f"Queued scene {next_index + 1}/{len(manifest['segments'])}: {prompt_id}"


class DaWH3MusicVideoDirector(io.ComfyNode):
    NODE_ID = "DaWH3MusicVideoDirector"
    DISPLAY_NAME = "H3 Complete-Song Music Video Director (One Click)"
    DUAL_GPU = False

    @classmethod
    def define_schema(cls):
        diffusion_options, diffusion_default = _model_options("diffusion_models", DEFAULT_DIFFUSION)
        text_options, text_default = _model_options("text_encoders", DEFAULT_TEXT_ENCODER)
        vae_options, _ = _model_options("vae", DEFAULT_VIDEO_VAE)
        if DEFAULT_AUDIO_VAE not in vae_options:
            vae_options.append(DEFAULT_AUDIO_VAE)
        return io.Schema(
            node_id=cls.NODE_ID,
            display_name=cls.DISPLAY_NAME,
            category=CATEGORY,
            description=(
                "Analyzes a complete song, plans beat-aware shots, renders one MiniMax H3 scene at a time through "
                "the local ComfyUI queue, resumes failures, concatenates every scene, and stream-copies the original audio."
            ),
            inputs=[
                io.Combo.Input("song", options=_song_options(), upload=io.UploadType.audio),
                io.Combo.Input("reference_image", options=_image_options(), default=NONE_IMAGE, upload=io.UploadType.image),
                io.String.Input("project_name", default="Intro_Music_Video"),
                io.String.Input(
                    "master_visual_concept",
                    default=(
                        "A cinematic streamer intro music video. A recurring protagonist moves through an evolving science-fiction world; "
                        "the scale, lighting and camera energy rise with the music and culminate in a memorable final composition."
                    ),
                    multiline=True,
                    dynamic_prompts=False,
                ),
                io.String.Input(
                    "lyrics_or_story_optional",
                    default="",
                    multiline=True,
                    dynamic_prompts=False,
                    tooltip="Optional plain lyrics/story, or timestamped LRC-style lines such as [01:23.45] text. Rhythm analysis alone cannot infer lyrical meaning.",
                ),
                io.Combo.Input("scene_prompt_planner", options=["automatic audio analysis", "local OpenAI-compatible LLM"], default="automatic audio analysis"),
                io.Float.Input("target_scene_seconds", default=10.0, min=4.0, max=30.0, step=0.25),
                io.Float.Input("min_scene_seconds", default=7.0, min=3.0, max=30.0, step=0.25, advanced=True),
                io.Float.Input("max_scene_seconds", default=13.0, min=4.0, max=45.0, step=0.25, advanced=True),
                io.Boolean.Input("continuity_from_previous_last_frame", default=True, advanced=True),
                io.Int.Input("width", default=864, min=320, max=2048, step=32, advanced=True),
                io.Int.Input("height", default=480, min=320, max=2048, step=32, advanced=True),
                io.Int.Input("steps", default=8, min=1, max=100, advanced=True),
                io.Int.Input("seed", default=314159265358979, min=0, max=0xFFFFFFFFFFFFFFFF, advanced=True),
                io.Combo.Input("seed_mode", options=["increment per scene", "fixed", "deterministic hash"], default="fixed", advanced=True),
                io.Boolean.Input("spectrum_enabled", default=True, advanced=True),
                io.Float.Input("segment_crf", default=14.0, min=0.0, max=35.0, step=1.0, advanced=True),
                io.Float.Input("final_crf_fallback", default=18.0, min=0.0, max=35.0, step=1.0, advanced=True),
                io.Combo.Input("video_preset", options=["fast", "medium", "slow"], default="medium", advanced=True),
                io.Combo.Input("output_container", options=["mkv", "mp4"], default="mkv", advanced=True),
                io.Boolean.Input("resume_existing", default=True, advanced=True),
                io.Boolean.Input("force_rebuild", default=False, advanced=True),
                io.String.Input("local_llm_base_url", default="http://127.0.0.1:8080/v1", advanced=True),
                io.String.Input("local_llm_model", default="", advanced=True),
                io.Float.Input("local_llm_timeout", default=180.0, min=5.0, max=1800.0, step=5.0, advanced=True),
                io.String.Input("server_address", default="127.0.0.1:8188", advanced=True),
                io.Combo.Input("diffusion_model", options=diffusion_options, default=diffusion_default, advanced=True),
                io.Combo.Input("text_encoder", options=text_options, default=text_default, advanced=True),
                io.Combo.Input("video_vae", options=vae_options, default=DEFAULT_VIDEO_VAE, advanced=True),
                io.Combo.Input("audio_vae", options=vae_options, default=DEFAULT_AUDIO_VAE, advanced=True),
                io.Float.Input("shift_video", default=12.0, min=0.01, max=100.0, step=0.01, advanced=True),
                io.Float.Input("shift_audio", default=4.0, min=0.01, max=100.0, step=0.01, advanced=True),
                io.Combo.Input("sampler_name", options=["euler", "res_multistep"], default="euler", advanced=True),
                io.Combo.Input("scheduler", options=["beta", "normal", "simple"], default="beta", advanced=True),
                io.Float.Input("spectrum_blend_weight", default=0.50, min=0.0, max=1.0, step=0.01, advanced=True),
                io.Int.Input("spectrum_degree", default=4, min=1, max=16, advanced=True),
                io.Float.Input("spectrum_ridge_lambda", default=0.10, min=0.0, max=10.0, step=0.01, advanced=True),
                io.Float.Input("spectrum_window_size", default=2.0, min=1.0, max=16.0, step=0.05, advanced=True),
                io.Float.Input("spectrum_flex_window", default=0.75, min=0.0, max=8.0, step=0.05, advanced=True),
                io.Int.Input("spectrum_warmup_steps", default=5, min=0, max=64, advanced=True),
                io.Int.Input("spectrum_tail_actual_steps", default=1, min=0, max=64, advanced=True),
                io.Int.Input("spectrum_max_history", default=8, min=2, max=64, advanced=True),
                io.Combo.Input("spectrum_history_storage", options=["system_ram", "vram"], default="system_ram", advanced=True),
                io.Boolean.Input("spectrum_debug", default=False, advanced=True),
                # Keep new serialized widgets after every v0.8.3 widget. ComfyUI
                # restores list-style widget values positionally, so insertion in
                # the middle would corrupt existing user workflows.
                io.Combo.Input(
                    "reference_strategy",
                    options=[IDENTITY_LOCK, PREVIOUS_FRAME_CONTINUITY, BOTH_REFERENCES],
                    default=IDENTITY_LOCK,
                    tooltip="Identity lock sends only the original reference to every scene and avoids recursive character drift.",
                    advanced=True,
                ),
                io.Boolean.Input(
                    "force_reference_as_first_frame",
                    default=True,
                    tooltip="For scene 1, replace the generated first frame with a contained, uncropped copy of the selected reference image.",
                    advanced=True,
                ),
            ],
            outputs=[io.String.Output("manifest_path"), io.String.Output("expected_final_file"), io.String.Output("status")],
            is_output_node=True,
        )

    @classmethod
    def execute(
        cls, song, reference_image, project_name, master_visual_concept, lyrics_or_story_optional,
        scene_prompt_planner, target_scene_seconds, min_scene_seconds, max_scene_seconds,
        continuity_from_previous_last_frame, width, height, steps, seed, seed_mode, spectrum_enabled,
        segment_crf, final_crf_fallback, video_preset, output_container, resume_existing, force_rebuild,
        local_llm_base_url, local_llm_model, local_llm_timeout, server_address, diffusion_model,
        text_encoder, video_vae, audio_vae, shift_video, shift_audio, sampler_name, scheduler,
        spectrum_blend_weight, spectrum_degree, spectrum_ridge_lambda, spectrum_window_size,
        spectrum_flex_window, spectrum_warmup_steps, spectrum_tail_actual_steps, spectrum_max_history,
        spectrum_history_storage, spectrum_debug, reference_strategy, force_reference_as_first_frame,
    ) -> io.NodeOutput:
        _required_node_check(bool(spectrum_enabled), dual_gpu=cls.DUAL_GPU)
        if int(width) % 32 or int(height) % 32:
            raise ValueError("MiniMax H3 width and height must be divisible by 32")
        if not (float(min_scene_seconds) <= float(target_scene_seconds) <= float(max_scene_seconds)):
            raise ValueError("Scene duration settings must satisfy min <= target <= max")
        if spectrum_history_storage == "vram":
            print("[DaWasteh H3 MusicVideo] Warning: system_ram is safer than vram for a long multi-shot project.")

        ffmpeg = find_ffmpeg()
        audio_path = _resolve_input(str(song))
        selected_reference = str(reference_image)
        reference_source = None if selected_reference == NONE_IMAGE else _resolve_input(selected_reference)
        project_name = sanitize_name(str(project_name))

        settings = {
            "width": int(width), "height": int(height), "steps": int(steps), "seed": int(seed), "seed_mode": str(seed_mode),
            "continuity": bool(continuity_from_previous_last_frame), "reference_strategy": str(reference_strategy),
            "force_reference_as_first_frame": bool(force_reference_as_first_frame), "spectrum_enabled": bool(spectrum_enabled),
            "segment_crf": float(segment_crf), "final_crf": float(final_crf_fallback), "video_preset": str(video_preset),
            "output_container": str(output_container), "diffusion_model": str(diffusion_model), "text_encoder": str(text_encoder),
            "video_vae": str(video_vae), "audio_vae": str(audio_vae), "shift_video": float(shift_video),
            "shift_audio": float(shift_audio), "sampler_name": str(sampler_name), "scheduler": str(scheduler),
            "ref_image_size": "match", "spectrum_blend_weight": float(spectrum_blend_weight),
            "spectrum_degree": int(spectrum_degree), "spectrum_ridge_lambda": float(spectrum_ridge_lambda),
            "spectrum_window_size": float(spectrum_window_size), "spectrum_flex_window": float(spectrum_flex_window),
            "spectrum_warmup_steps": int(spectrum_warmup_steps), "spectrum_tail_actual_steps": int(spectrum_tail_actual_steps),
            "spectrum_max_history": int(spectrum_max_history), "spectrum_history_storage": str(spectrum_history_storage),
            "spectrum_debug": bool(spectrum_debug), "dual_gpu": cls.DUAL_GPU, "turbo_lora": DEFAULT_TURBO_LORA,
        }
        fingerprint_payload = {
            "project_name": project_name, "master_visual_concept": str(master_visual_concept),
            "lyrics_or_story_optional": str(lyrics_or_story_optional), "scene_prompt_planner": str(scene_prompt_planner),
            "target_scene_seconds": float(target_scene_seconds), "min_scene_seconds": float(min_scene_seconds),
            "max_scene_seconds": float(max_scene_seconds), "settings": settings,
        }
        fingerprint = _project_fingerprint(audio_path, reference_source, fingerprint_payload)
        project_id = f"{project_name}_{fingerprint[:12]}"
        output_root = Path(folder_paths.get_output_directory())
        project_dir = output_root / "DaWasteh_H3_MusicVideo_Projects" / project_id
        manifest_path = project_dir / "manifest.json"
        final_output = output_root / "video" / "MiniMax_H3_MusicVideo" / project_id / f"{project_name}.{output_container}"

        if force_rebuild and project_dir.exists():
            shutil.rmtree(project_dir)
        elif project_dir.exists() and not resume_existing:
            shutil.rmtree(project_dir)

        if manifest_path.exists() and resume_existing and not force_rebuild:
            manifest = read_json(manifest_path)
            if manifest.get("fingerprint") != fingerprint:
                raise RuntimeError("Existing project fingerprint differs; enable force_rebuild.")
        else:
            project_dir.mkdir(parents=True, exist_ok=True)
            for child in ("segment_audio", "segments", "continuity"):
                (project_dir / child).mkdir(exist_ok=True)
            source_suffix = Path(audio_path).suffix or ".audio"
            source_copy = project_dir / f"source_audio{source_suffix}"
            shutil.copy2(audio_path, source_copy)
            reference_copy: Path | None = None
            first_frame_reference: Path | None = None
            if reference_source:
                reference_copy = project_dir / "reference.png"
                save_reference_image_from_input(reference_source, str(reference_copy))
                if bool(force_reference_as_first_frame):
                    first_frame_reference = project_dir / "first_frame_reference.png"
                    save_canonical_reference_frame(
                        str(reference_copy), str(first_frame_reference), int(width), int(height)
                    )

            print(f"[DaWasteh H3 MusicVideo] Analyzing {Path(audio_path).name} ...")
            analysis = analyze_song_and_plan_segments(
                ffmpeg, str(source_copy), target_seconds=float(target_scene_seconds), min_seconds=float(min_scene_seconds),
                max_seconds=float(max_scene_seconds), lyrics_or_story=str(lyrics_or_story_optional),
            )
            segments = analysis["segments"]
            if not segments:
                raise RuntimeError("Song analysis produced no scenes")
            if len(segments) > 120:
                raise ValueError(f"Planner produced {len(segments)} scenes; increase target_scene_seconds")
            has_reference = reference_copy is not None
            prompts = build_deterministic_prompts(
                segments, str(master_visual_concept), has_base_reference=has_reference,
                continuity=bool(continuity_from_previous_last_frame), reference_strategy=str(reference_strategy),
            )
            planner_note = "deterministic rhythm/energy/structure planner"
            if scene_prompt_planner == "local OpenAI-compatible LLM":
                try:
                    prompts = query_local_llm_scene_prompts(
                        base_url=str(local_llm_base_url), model=str(local_llm_model), timeout=float(local_llm_timeout),
                        segments=segments, master_visual_concept=str(master_visual_concept),
                        lyrics_or_story=str(lyrics_or_story_optional), has_base_reference=has_reference,
                        continuity=bool(continuity_from_previous_last_frame), reference_strategy=str(reference_strategy),
                    )
                    planner_note = "local LLM scene planner"
                except Exception as exc:
                    planner_note = f"local LLM failed; deterministic fallback used: {exc}"
                    print(f"[DaWasteh H3 MusicVideo] {planner_note}")

            for segment, prompt in zip(segments, prompts):
                index = int(segment["index"])
                audio_segment = project_dir / "segment_audio" / f"segment_{index:04d}.wav"
                video_segment = project_dir / "segments" / f"segment_{index:04d}.mp4"
                continuity_frame = project_dir / "continuity" / f"last_{index:04d}.png"
                extract_segment_audio(
                    ffmpeg, str(source_copy), str(audio_segment), float(segment["start"]),
                    float(segment["conditioning_audio_duration"]),
                )
                if seed_mode == "fixed":
                    scene_seed = int(seed)
                elif seed_mode == "deterministic hash":
                    scene_seed = int(hashlib.sha256(f"{fingerprint}:{index}".encode()).hexdigest()[:16], 16)
                else:
                    scene_seed = (int(seed) + index * 1000003) & 0xFFFFFFFFFFFFFFFF
                segment.update({
                    "prompt": prompt, "seed": scene_seed, "audio_path": str(audio_segment),
                    "video_path": str(video_segment), "continuity_path": str(continuity_frame),
                    "status": "pending", "prompt_id": None, "handoff_complete": False,
                })

            manifest = {
                "schema_version": 1, "project_id": project_id, "project_name": project_name,
                "fingerprint": fingerprint, "created_at": time.time(), "updated_at": time.time(), "status": "planned",
                "project_dir": str(project_dir), "reference_image_path": str(reference_copy) if reference_copy else None,
                "first_frame_reference_path": str(first_frame_reference) if first_frame_reference else None,
                "source_audio_copy": str(source_copy), "source_audio_original": audio_path,
                "source_audio_sha256": sha256_file(str(source_copy)), "source_audio_duration": analysis["duration"],
                "final_output_path": str(final_output), "server_address": str(server_address),
                "master_visual_concept": str(master_visual_concept), "lyrics_or_story": str(lyrics_or_story_optional),
                "planner_note": planner_note, "analysis": {key: value for key, value in analysis.items() if key != "segments"},
                "settings": settings, "segments": segments, "queued_prompt_ids": [], "finalizer_prompt_id": None,
            }
            atomic_write_json(manifest_path, manifest)
            atomic_write_json(project_dir / "scene_plan.json", {"analysis": manifest["analysis"], "segments": segments})

        # Refresh server address so a moved server can resume the same project.
        if str(manifest.get("server_address")) != str(server_address):
            manifest["server_address"] = str(server_address)
            atomic_write_json(manifest_path, manifest)

        valid = segment_files_valid(ffmpeg, manifest)
        if all(valid) and os.path.isfile(str(manifest["final_output_path"])):
            status = f"Complete: {manifest['final_output_path']}"
            return io.NodeOutput(str(manifest_path), str(manifest["final_output_path"]), status)

        active = _active_project_prompt_ids(manifest)
        if active:
            status = f"Project already has {len(active)} queued/running child job(s); no duplicate was added."
            return io.NodeOutput(str(manifest_path), str(manifest["final_output_path"]), status)

        if settings["continuity"] and not all(valid):
            first_missing = valid.index(False)
            for index in range(first_missing, len(valid)):
                for key in ("video_path", "continuity_path"):
                    try:
                        os.remove(str(manifest["segments"][index][key]))
                    except OSError:
                        pass
                manifest["segments"][index]["status"] = "pending"
                manifest["segments"][index]["prompt_id"] = None
                manifest["segments"][index]["handoff_complete"] = False
            atomic_write_json(manifest_path, manifest)

        handoff = _queue_next_work_item(str(manifest_path))
        manifest = read_json(manifest_path)
        status = (
            f"{handoff}. Planned {len(manifest['segments'])} scenes for {manifest['source_audio_duration']:.2f}s; "
            f"estimated BPM {manifest['analysis']['estimated_bpm']:.1f}. Final file: {manifest['final_output_path']}"
        )
        print(f"[DaWasteh H3 MusicVideo] {status}")
        return io.NodeOutput(str(manifest_path), str(manifest["final_output_path"]), status)

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        # Action/output node: inspect manifest and queue state on every explicit run.
        return float("nan")


class DaWH3MusicVideoDirectorDualGPU(DaWH3MusicVideoDirector):
    NODE_ID = "DaWH3MusicVideoDirectorDualGPU"
    DISPLAY_NAME = "H3 Complete-Song Music Video Director (Dual GPU · 8188)"
    DUAL_GPU = True


class DaWH3MusicVideoLoadSegment(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWH3MusicVideoLoadSegment", display_name="H3 Music Video: Load Planned Audio Scene", category=CATEGORY,
            inputs=[io.String.Input("manifest_path"), io.Int.Input("segment_index", default=0, min=0, max=10000)],
            outputs=[
                io.Audio.Output("audio"), io.Int.Output("h3_length"), io.Int.Output("target_frames"),
                io.String.Output("scene_prompt"), io.Int.Output("seed"), io.String.Output("scene_info"),
            ],
        )

    @classmethod
    def execute(cls, manifest_path: str, segment_index: int) -> io.NodeOutput:
        ffmpeg = find_ffmpeg()
        manifest = read_json(manifest_path)
        segment = manifest["segments"][int(segment_index)]
        audio = decode_audio_for_comfy(ffmpeg, str(segment["audio_path"]))
        def mark_running(value):
            entry = value["segments"][int(segment_index)]
            entry["status"] = "running"
            entry["started_at"] = time.time()
        update_manifest(manifest_path, mark_running)
        info = (
            f"scene {int(segment_index) + 1}/{len(manifest['segments'])}: {segment['start']:.3f}-{segment['end']:.3f}s, "
            f"target {segment['target_frames']} frames, H3 aligned {segment['h3_frames']} frames"
        )
        print(f"[DaWasteh H3 MusicVideo] {info}")
        return io.NodeOutput(audio, int(segment["h3_frames"]), int(segment["target_frames"]), str(segment["prompt"]), int(segment["seed"]), info)

    @classmethod
    def fingerprint_inputs(cls, manifest_path: str, segment_index: int):
        manifest = read_json(manifest_path)
        segment = manifest["segments"][int(segment_index)]
        stat = os.stat(str(segment["audio_path"]))
        return f"{manifest.get('fingerprint')}|{segment_index}|{stat.st_mtime_ns}|{stat.st_size}|{segment.get('prompt')}"


class DaWH3MusicVideoLoadImagePath(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWH3MusicVideoLoadImagePath", display_name="H3 Music Video: Load Project Reference", category=CATEGORY,
            inputs=[io.String.Input("image_path")], outputs=[io.Image.Output("image")],
        )

    @classmethod
    def execute(cls, image_path: str) -> io.NodeOutput:
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Project reference image is missing: {image_path}")
        return io.NodeOutput(load_image_tensor(image_path))

    @classmethod
    def fingerprint_inputs(cls, image_path: str):
        stat = os.stat(image_path)
        return f"{os.path.abspath(image_path)}|{stat.st_mtime_ns}|{stat.st_size}"


class DaWH3MusicVideoSaveSegment(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWH3MusicVideoSaveSegment", display_name="H3 Music Video: Save Scene and Queue Next", category=CATEGORY,
            inputs=[
                io.Image.Input("images"), io.String.Input("manifest_path"),
                io.Int.Input("segment_index", default=0, min=0, max=10000), io.Int.Input("target_frames", default=240, min=1, max=3600),
            ],
            outputs=[io.String.Output("segment_file"), io.String.Output("handoff_status")], is_output_node=True,
        )

    @classmethod
    def execute(cls, images, manifest_path: str, segment_index: int, target_frames: int) -> io.NodeOutput:
        ffmpeg = find_ffmpeg()
        manifest = read_json(manifest_path)
        segment = manifest["segments"][int(segment_index)]
        output_path = str(segment["video_path"])
        first_frame_path = None
        if int(segment_index) == 0 and bool(manifest["settings"].get("force_reference_as_first_frame")):
            first_frame_path = manifest.get("first_frame_reference_path")
        encode_images_to_h264(
            ffmpeg, images, int(target_frames), output_path,
            crf=float(manifest["settings"]["segment_crf"]), preset=str(manifest["settings"]["video_preset"]),
            first_frame_path=str(first_frame_path) if first_frame_path else None,
        )
        save_reference_tensor(images[int(target_frames) - 1:int(target_frames)], str(segment["continuity_path"]))
        verified = count_video_frames(ffmpeg, output_path)
        if verified != int(target_frames):
            raise RuntimeError(f"Scene {int(segment_index) + 1} encoded {verified} frames instead of {target_frames}")
        def mark_complete(value):
            entry = value["segments"][int(segment_index)]
            entry["status"] = "complete"
            entry["completed_at"] = time.time()
            entry["verified_frames"] = verified
            entry["reference_first_frame_forced"] = bool(first_frame_path)
        update_manifest(manifest_path, mark_complete)
        print(f"[DaWasteh H3 MusicVideo] Saved scene {int(segment_index) + 1}: {output_path}")
        gc.collect()
        comfy.model_management.soft_empty_cache()
        handoff = _queue_next_work_item(manifest_path)
        def mark_handoff(value):
            value["segments"][int(segment_index)]["handoff_complete"] = True
            value["segments"][int(segment_index)]["handoff_status"] = handoff
        update_manifest(manifest_path, mark_handoff)
        print(f"[DaWasteh H3 MusicVideo] {handoff}")
        return io.NodeOutput(output_path, handoff)


class DaWH3MusicVideoFinalize(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWH3MusicVideoFinalize", display_name="H3 Music Video: Join Scenes + Copy Original Audio", category=CATEGORY,
            inputs=[io.String.Input("manifest_path")], outputs=[io.String.Output("final_file")], is_output_node=True,
        )

    @classmethod
    def execute(cls, manifest_path: str) -> io.NodeOutput:
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
        gc.collect()
        ffmpeg = find_ffmpeg()
        final_path = concat_and_mux_project(ffmpeg, manifest_path)
        def mark_complete(value):
            value["status"] = "complete"
            value["completed_at"] = time.time()
            value["final_output_path"] = final_path
        update_manifest(manifest_path, mark_complete)
        output_root = Path(folder_paths.get_output_directory()).resolve()
        final = Path(final_path).resolve()
        preview = None
        try:
            relative = final.relative_to(output_root)
            subfolder = str(relative.parent).replace("\\", "/")
            preview = ui.PreviewVideo([ui.SavedResult(relative.name, subfolder if subfolder != "." else "", io.FolderType.output)])
        except Exception:
            pass
        print(
            f"[DaWasteh H3 MusicVideo] COMPLETE: {final_path}\n"
            "[DaWasteh H3 MusicVideo] H3-generated audio was discarded; the original source audio stream was muxed with -c:a copy."
        )
        return io.NodeOutput(final_path, ui=preview) if preview is not None else io.NodeOutput(final_path)


class DaWastehH3MusicVideoExtension(ComfyExtension):
    async def get_node_list(self):
        return [
            DaWH3MusicVideoDirector, DaWH3MusicVideoDirectorDualGPU,
            DaWH3MusicVideoLoadSegment, DaWH3MusicVideoLoadImagePath,
            DaWH3MusicVideoSaveSegment, DaWH3MusicVideoFinalize,
        ]


async def comfy_entrypoint() -> DaWastehH3MusicVideoExtension:
    return DaWastehH3MusicVideoExtension()
