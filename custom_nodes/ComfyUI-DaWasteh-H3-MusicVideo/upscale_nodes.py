"""v1.2.3 video upscaling frame: plan blocks at hard cuts, load/encode a block, save it, join with the original audio.

The three upscale workflows (Nerdy Rodent's MiniMax H3 methods: PlagueKind MMH3 Ultimate Upscale,
LBH Latent Upscaler 3D, native SeedVR2) share this frame:

    VU 1 Planner -> VU 2 Load Block -> [method] -> VU 3 Save Block -> Pixaroma Pause gate
                 -> Pixaroma Loop (blocks - 1 rounds) -> VU 4 Finalize

Blocks keep the decoded high-resolution frames small (a 90 s film at 1280x704 would need ~22 GB as
one IMAGE tensor) and make any input length work. Block borders are placed on hard cuts whenever
possible, so independently re-sampled blocks do not show a visible jump.
"""
from __future__ import annotations

import gc
import math
import os
import shutil
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
    encode_images_to_h264,
    find_ffmpeg,
    lightweight_file_fingerprint,
    read_json,
    run_command,
    sanitize_name,
)
from .nodes_v2 import (
    DEFAULT_H3_TE,
    TAIL_ENCODE_VRAM,
    _audio_codec,
    _contact_sheet,
    _decode_window,
    _load_text_model,
    _pil_to_image,
    _preview_ui,
    _release_text_model,
    _text_encoder_options,
    _unload_vaes,
)

CATEGORY = "DaWasteh/MiniMax H3/Video Upscale"
SCHEMA = "dawasteh-video-upscale/1"
PROJECTS = "DaWasteh_VideoUpscale"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
ALIGN_MODES = ["h3 (17k+5)", "seedvr2 (4k+1)", "none"]
FPS = 24
TAG = "[DaWasteh VideoUpscale]"


def _log(message: str) -> None:
    print(f"{TAG} {message}", flush=True)


def _video_options() -> list[str]:
    root = Path(folder_paths.get_input_directory())
    found = [str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    return sorted(found, key=str.casefold) or ["video.mp4"]


def _plan(path: str) -> dict[str, Any]:
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"Upscale plan not found: {path!r}. Run 'VU 1 · Planer' first.")
    plan = read_json(path)
    if plan.get("schema") != SCHEMA:
        raise ValueError(f"{path} is not a video-upscale plan")
    return plan


def _save_plan(path: str, plan: dict[str, Any]) -> None:
    plan["updated_at"] = time.time()
    atomic_write_json(path, plan)


def align_count(frames: int, mode: str) -> int:
    if mode.startswith("h3"):
        return mv2.align_frames(frames)
    if mode.startswith("seedvr2"):
        return frames + ((1 - frames) % 4)
    return frames


def target_size(width: int, height: int, scale: float, multiple: int = 32) -> tuple[int, int]:
    return (max(multiple, int(round(width * scale / multiple)) * multiple),
            max(multiple, int(round(height * scale / multiple)) * multiple))


def plan_blocks(motion: np.ndarray, total: int, settings: mv2.SplitSettings, cut_threshold: float) -> tuple[list[tuple[int, int]], list[int]]:
    """Blocks of total frames; motion[i] = mean abs difference between frame i-1 and i (motion[0] = 0).
    Hard cuts are strongly preferred block borders, calm frames mildly preferred."""
    diffs = motion[1:] if motion.size > 1 else np.zeros(1, dtype=np.float32)
    # A cut is a jump well above the motion around it (a global threshold misses cuts in busy footage).
    cuts = []
    for i in range(1, min(total, motion.size)):
        lo, hi = max(1, i - 12), min(motion.size, i + 13)
        neighbours = np.concatenate([motion[lo:i], motion[i + 1:hi]])
        if motion[i] > cut_threshold and neighbours.size and motion[i] > 2.5 * float(np.median(neighbours)):
            cuts.append(i)
    scale = float(np.percentile(diffs, 95)) if diffs.size else 1.0
    scale = scale if scale > 1e-6 else 1.0
    candidates: dict[int, float] = {}
    for frame in range(3, total, 3):  # every third frame keeps the DP fast for 10-minute videos
        candidates[frame] = 1.5 + 2.0 * min(1.0, float(motion[frame]) / scale)
    for frame in cuts:
        candidates[frame] = -3.0
    return mv2.plan_scene_frames(total / FPS, candidates, settings), cuts


def _decode_small_gray(ffmpeg: str, path: str, total: int) -> np.ndarray:
    result = run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-map", "0:v:0", "-vf", "scale=128:72",
                          "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"], timeout=3600)
    frames = np.frombuffer(result.stdout, dtype=np.uint8)
    count = frames.size // (128 * 72)
    frames = frames[: count * 128 * 72].reshape(count, 72, 128).astype(np.float32)
    motion = np.zeros(max(total, count), dtype=np.float32)
    if count > 1:
        motion[1:count] = np.abs(frames[1:] - frames[:-1]).mean(axis=(1, 2))
    return motion[:total]


def _probe(path: str) -> dict[str, Any]:
    import av
    with av.open(path) as container:
        if not container.streams.video:
            raise ValueError(f"No video stream in {path}")
        stream = container.streams.video[0]
        fps = float(stream.average_rate or stream.guessed_rate or FPS)
        return {"width": stream.codec_context.width, "height": stream.codec_context.height, "fps": fps,
                "has_audio": bool(container.streams.audio),
                "audio_codec": container.streams.audio[0].codec_context.name if container.streams.audio else None}


# ---------------------------------------------------------------------------
# VU 1 · Planner
# ---------------------------------------------------------------------------

class DaWVUPlanner(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWVUPlanner",
            display_name="VU 1 · Video-Upscale Planer (Blöcke an Schnitten, Zielgröße)",
            category=CATEGORY,
            description=("Splits a video of any length into blocks for upscaling. Block borders are placed on hard cuts "
                         "when possible; the target size is the source size times 'scale', snapped to 32 px."),
            inputs=[
                io.Combo.Input("video", options=_video_options(), upload=io.UploadType.video,
                               tooltip="Video from ComfyUI/input (subfolders allowed). Its audio stream is muxed back untouched."),
                io.String.Input("video_path_override", default="", tooltip="Optional absolute path (e.g. a finished music video in output/). Wins over 'video'."),
                io.String.Input("project_name", default="Upscale"),
                io.Float.Input("scale", default=1.5, min=1.0, max=4.0, step=0.05),
                io.Float.Input("target_block_seconds", default=7.0, min=1.0, max=30.0, step=0.25),
                io.Float.Input("min_block_seconds", default=2.0, min=0.5, max=30.0, step=0.25, advanced=True),
                io.Float.Input("max_block_seconds", default=10.0, min=1.0, max=60.0, step=0.25,
                               tooltip="Upper block length. H3 re-sampling per block must fit in VRAM; the workflow default is measured."),
                io.Float.Input("cut_threshold", default=18.0, min=1.0, max=128.0, step=0.5, advanced=True,
                               tooltip="Mean grey-level change (0-255) between two frames that counts as a hard cut."),
                io.String.Input("method_tag", default="upscale", advanced=True,
                                tooltip="Part of the project folder; keeps results of different methods apart."),
                io.Boolean.Input("resume_existing_blocks", default=True, advanced=True),
            ],
            outputs=[io.String.Output("plan"), io.Int.Output("block_count"), io.Int.Output("loop_rounds"),
                     io.Int.Output("target_width"), io.Int.Output("target_height"), io.String.Output("plan_text")],
        )

    @classmethod
    def fingerprint_inputs(cls, video, video_path_override, **kwargs):
        try:
            path = video_path_override.strip() or folder_paths.get_annotated_filepath(video)
            return lightweight_file_fingerprint(path) + mv2.stable_hash(kwargs)
        except Exception:
            return float("nan")

    @classmethod
    def execute(cls, video, video_path_override, project_name, scale, target_block_seconds, min_block_seconds,
                max_block_seconds, cut_threshold, method_tag, resume_existing_blocks) -> io.NodeOutput:
        source = os.path.abspath(video_path_override.strip().strip('"') or folder_paths.get_annotated_filepath(video))
        if not os.path.isfile(source):
            raise FileNotFoundError(source)
        if not (min_block_seconds <= target_block_seconds <= max_block_seconds):
            raise ValueError("Block lengths must satisfy min <= target <= max")
        ffmpeg = find_ffmpeg()
        info = _probe(source)
        name = sanitize_name(project_name, "Upscale")
        key = mv2.stable_hash({"src": lightweight_file_fingerprint(source), "scale": float(scale), "t": float(target_block_seconds),
                               "min": float(min_block_seconds), "max": float(max_block_seconds), "cut": float(cut_threshold),
                               "tag": method_tag}, 12)
        project = Path(folder_paths.get_output_directory()) / PROJECTS / f"{name}_{sanitize_name(method_tag, 'upscale')}_{key}"
        plan_path = project / "plan.json"
        if plan_path.is_file():
            plan = read_json(plan_path)
            if plan.get("schema") == SCHEMA and plan.get("key") == key:
                if not resume_existing_blocks:
                    plan["render_nonce"] = time.time_ns()
                    _save_plan(str(plan_path), plan)
                n = len(plan["blocks"])
                return io.NodeOutput(str(plan_path), n, max(1, n - 1), plan["target_width"], plan["target_height"], _plan_text(plan))
        project.mkdir(parents=True, exist_ok=True)
        working = source
        if abs(info["fps"] - FPS) > 0.01:
            working = str(project / "working_24fps.mp4")
            _log(f"Source runs at {info['fps']:.3f} fps; creating a 24 fps working copy")
            run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", source, "-map", "0:v:0", "-vf", f"fps={FPS}",
                         "-c:v", "libx264", "-crf", "10", "-preset", "medium", "-pix_fmt", "yuv420p", working], timeout=14400)
        total = count_video_frames(ffmpeg, working)
        motion = _decode_small_gray(ffmpeg, working, total)
        settings = mv2.SplitSettings(float(target_block_seconds), float(min_block_seconds), float(max_block_seconds), 0)
        frames, cuts = plan_blocks(motion, total, settings, float(cut_threshold))
        cut_set = set(cuts)
        tw, th = target_size(info["width"], info["height"], float(scale))
        plan = {
            "schema": SCHEMA, "key": key, "created_at": time.time(), "project_name": name, "method_tag": method_tag,
            "project_dir": str(project), "source": source, "working_video": working, "fps": FPS, "source_fps": info["fps"],
            "width": info["width"], "height": info["height"], "scale": float(scale), "target_width": tw, "target_height": th,
            "total_frames": total, "has_audio": info["has_audio"], "audio_codec": info["audio_codec"], "hard_cuts": len(cuts),
            "blocks": [{"index": k, "start_frame": a, "end_frame": b, "frames": b - a, "starts_at_cut": a in cut_set}
                       for k, (a, b) in enumerate(frames)],
            "render_nonce": 0 if resume_existing_blocks else time.time_ns(),
        }
        _save_plan(str(plan_path), plan)
        _log(f"Planned {len(frames)} blocks for {total} frames ({len(cuts)} hard cuts) -> {tw}x{th}")
        n = len(frames)
        return io.NodeOutput(str(plan_path), n, max(1, n - 1), tw, th, _plan_text(plan))


def _plan_text(plan: dict[str, Any]) -> str:
    rows = [f"{Path(plan['source']).name}: {plan['width']}x{plan['height']} -> {plan['target_width']}x{plan['target_height']} "
            f"(x{plan['scale']:.2f}), {plan['total_frames']} Frames ({plan['total_frames'] / FPS:.2f} s), "
            f"{len(plan['blocks'])} Blöcke, {plan['hard_cuts']} harte Schnitte erkannt", ""]
    for block in plan["blocks"]:
        rows.append(f"{block['index'] + 1:>3}. Frames {block['start_frame']}–{block['end_frame'] - 1} "
                    f"({block['frames'] / FPS:.2f} s){' · beginnt an Schnitt' if block['starts_at_cut'] else ''}")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# VU 2 · Load block
# ---------------------------------------------------------------------------

def _block(plan: dict[str, Any], block_index: int, index_offset: int) -> tuple[int, dict[str, Any] | None]:
    index = int(block_index) + int(index_offset)
    return index, (plan["blocks"][index] if index < len(plan["blocks"]) else None)


def _read_frames(ffmpeg: str, path: str, start: int, count: int, width: int, height: int) -> torch.Tensor:
    result = run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{start / FPS:.6f}", "-i", path,
                          "-map", "0:v:0", "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], timeout=3600)
    data = np.frombuffer(result.stdout, dtype=np.uint8)
    got = data.size // (width * height * 3)
    if got < count:
        raise RuntimeError(f"Decoded {got} of {count} frames at frame {start}")
    frames = data[: count * width * height * 3].reshape(count, height, width, 3)
    return torch.from_numpy(frames.astype(np.float32) / 255.0)


class DaWVULoadBlock(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWVULoadBlock",
            display_name="VU 2 · Block laden (Frames + Originalton)",
            category=CATEGORY,
            description=("Loads the frames and the original audio of one block. The frame count is padded (last frame "
                         "repeated) to the grid of the method: H3 17k+5, SeedVR2 4k+1. VU 3 removes the padding again."),
            inputs=[
                io.String.Input("plan", force_input=True),
                io.Int.Input("block_index", default=0, min=0, max=100000),
                io.Int.Input("index_offset", default=0, min=0, max=100000, advanced=True),
                io.Combo.Input("frame_alignment", options=ALIGN_MODES, default=ALIGN_MODES[0]),
            ],
            outputs=[io.Image.Output("images"), io.Audio.Output("audio"), io.Int.Output("frames"), io.String.Output("info")],
        )

    @classmethod
    def execute(cls, plan, block_index, index_offset, frame_alignment) -> io.NodeOutput:
        manifest = _plan(plan)
        index, block = _block(manifest, block_index, index_offset)
        if block is None:
            raise IndexError(f"Block {index + 1} does not exist; the plan has {len(manifest['blocks'])} blocks")
        ffmpeg = find_ffmpeg()
        count = block["frames"]
        padded = align_count(count, frame_alignment)
        images = _read_frames(ffmpeg, manifest["working_video"], block["start_frame"], count, manifest["width"], manifest["height"])
        if padded > count:
            images = torch.cat([images, images[-1:].repeat(padded - count, 1, 1, 1)], dim=0)
        start = block["start_frame"] / FPS
        if manifest["has_audio"]:
            waveform = _decode_window(ffmpeg, manifest["source"], start, padded / FPS)
        else:
            waveform = torch.zeros(1, 2, int(round(padded / FPS * 48000)))
        info = (f"Block {index + 1}/{len(manifest['blocks'])} · Frames {block['start_frame']}–{block['end_frame'] - 1} · "
                f"{count} Frames (+{padded - count} Auffüllung)")
        _log(info)
        return io.NodeOutput(images, {"waveform": waveform, "sample_rate": 48000}, count, info)


# ---------------------------------------------------------------------------
# H3 helpers: video+audio -> AV latent, prompt encoded once
# ---------------------------------------------------------------------------

class DaWH3VideoToAVLatent(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWH3VideoToAVLatent",
            display_name="H3 · Video + Originalton → AV-Latent",
            category=CATEGORY,
            description=("Encodes existing frames (17k+5) with the H3 video VAE and the matching audio with the H3 audio "
                         "VAE into the nested AV latent that the H3 upscale nodes expect (as if H3 had generated it)."),
            inputs=[io.Vae.Input("vae"), io.Vae.Input("audio_vae"), io.Image.Input("images"), io.Audio.Input("audio")],
            outputs=[io.Latent.Output("latent")],
        )

    @classmethod
    def execute(cls, vae, audio_vae, images, audio) -> io.NodeOutput:
        from comfy_extras.nodes_minimax_h3 import temporal_shape

        frames = int(images.shape[0])
        if frames % 17 != 5:
            raise ValueError(f"H3 needs 17k+5 frames, got {frames}; set VU 2 frame_alignment to 'h3 (17k+5)'")
        _, latent_t, audio_t = temporal_shape(frames)
        comfy.model_management.free_memory(TAIL_ENCODE_VRAM, getattr(vae, "device", None) or comfy.model_management.get_torch_device())
        try:
            video = vae.encode(images[..., :3])
        except torch.OutOfMemoryError:
            comfy.model_management.unload_all_models()
            gc.collect()
            comfy.model_management.soft_empty_cache()
            video = vae.encode(images[..., :3])
        device = comfy.model_management.intermediate_device()
        video = video.to(device=device, dtype=torch.float32)
        if video.shape[2] != latent_t:
            raise RuntimeError(f"Video latent has {video.shape[2]} frames, expected {latent_t}")
        waveform = audio["waveform"][:1]
        rate = int(getattr(audio_vae, "audio_sample_rate", 32000))
        if int(audio["sample_rate"]) != rate:
            waveform = comfy.audio.resample(waveform, int(audio["sample_rate"]), rate)
        encoded = audio_vae.encode(waveform.movedim(1, -1)).to(device=device, dtype=torch.float32)
        if encoded.shape[-1] > audio_t:
            encoded = encoded[..., :audio_t]
        elif encoded.shape[-1] < audio_t:
            encoded = torch.cat([encoded, encoded[..., -1:].repeat_interleave(audio_t - encoded.shape[-1], dim=-1)], dim=-1)
        _unload_vaes(vae, audio_vae)
        return io.NodeOutput({"samples": comfy.nested_tensor.NestedTensor((video, encoded))})


class DaWH3PromptOnce(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWH3PromptOnce",
            display_name="H3 · Prompt einmal encodieren (Textencoder danach frei)",
            category=CATEGORY,
            description=("Encodes the prompt with the MiniMax H3 text encoder once and caches the conditioning on disk; "
                         "the 26 GB encoder is loaded only when the text changes and released right after."),
            inputs=[
                io.String.Input("prompt", multiline=True, default=""),
                io.Combo.Input("text_encoder", options=_text_encoder_options(DEFAULT_H3_TE), default=DEFAULT_H3_TE),
            ],
            outputs=[io.Conditioning.Output("conditioning")],
        )

    @classmethod
    def execute(cls, prompt, text_encoder) -> io.NodeOutput:
        cache = Path(folder_paths.get_output_directory()) / PROJECTS / "_conditioning" / f"{mv2.stable_hash({'p': prompt, 'te': text_encoder}, 20)}.pt"
        if cache.is_file():
            return io.NodeOutput(torch.load(str(cache), map_location="cpu", weights_only=False))
        clip = _load_text_model(text_encoder, "minimax")
        try:
            cond = clip.encode_from_tokens_scheduled(clip.tokenize(prompt))
            cond = [[c[0].detach().cpu(), {k: (v.detach().cpu() if torch.is_tensor(v) else v) for k, v in c[1].items()}] for c in cond]
        finally:
            del clip
            _release_text_model()
        cache.parent.mkdir(parents=True, exist_ok=True)
        torch.save(cond, str(cache) + ".tmp")
        os.replace(str(cache) + ".tmp", cache)
        return io.NodeOutput(cond)


# ---------------------------------------------------------------------------
# VU 3 · Save block
# ---------------------------------------------------------------------------

def _files(plan: str, index: int) -> dict[str, Path]:
    root = Path(plan).parent
    return {"video": root / "blocks" / f"block_{index:04d}.mp4", "sheet": root / "blocks" / f"block_{index:04d}_sheet.png",
            "preview": root / "preview" / f"block_{index:04d}_with_audio.mp4"}


BLOCK_FIELDS = ("index", "start_frame", "end_frame", "frames", "starts_at_cut")


def _render_key(manifest: dict[str, Any], index: int) -> str:
    # Only the planned fields: SaveBlock stores render_key/size/... in the same dict afterwards.
    block = {name: manifest["blocks"][index][name] for name in BLOCK_FIELDS}
    return mv2.stable_hash({"key": manifest["key"], "block": block, "nonce": manifest.get("render_nonce", 0),
                            "size": [manifest["target_width"], manifest["target_height"]]})


def _done(plan: str, manifest: dict[str, Any], index: int) -> bool:
    block = manifest["blocks"][index]
    return (block.get("render_key") == _render_key(manifest, index) and _files(plan, index)["video"].is_file()
            and block.get("verified_frames") == block["frames"])


class DaWVUSaveBlock(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWVUSaveBlock",
            display_name="VU 3 · Block speichern · Vorschau mit Originalton",
            category=CATEGORY,
            description=("Keeps exactly the block's frames (padding removed), stores the block and shows it with the "
                         "original audio. Finished blocks are skipped without re-sampling (resume)."),
            inputs=[
                io.String.Input("plan", force_input=True),
                io.Int.Input("block_index", default=0, min=0, max=100000),
                io.Int.Input("index_offset", default=0, min=0, max=100000, advanced=True),
                io.Image.Input("images", lazy=True, optional=True),
                io.AnyType.Input("after", optional=True, tooltip="Ordering token: previous block or the approval gate."),
            ],
            outputs=[io.String.Output("token"), io.Image.Output("preview"), io.String.Output("info")],
            is_output_node=True,
        )

    @classmethod
    def check_lazy_status(cls, plan, block_index, index_offset, images=None, after=None):
        manifest = _plan(plan)
        index, block = _block(manifest, block_index, index_offset)
        if block is None or images is not None or _done(plan, manifest, index):
            return []
        return ["images"]

    @classmethod
    def execute(cls, plan, block_index, index_offset, images=None, after=None) -> io.NodeOutput:
        manifest = _plan(plan)
        index, block = _block(manifest, block_index, index_offset)
        total = len(manifest["blocks"])
        if block is None:
            return io.NodeOutput(f"{plan}|end", torch.zeros(1, 64, 64, 3), f"Kein Block {index + 1} (Plan hat {total}).")
        files = _files(plan, index)
        if images is None:
            sheet = Image.open(files["sheet"]) if files["sheet"].is_file() else Image.new("RGB", (64, 64))
            info = f"Block {index + 1}/{total} bereits fertig (übersprungen)"
            preview = _preview_ui(files["preview"]) if files["preview"].is_file() else None
            token = f"{plan}|{index}|{block['render_key']}"
            return io.NodeOutput(token, _pil_to_image(sheet), info, ui=preview) if preview else io.NodeOutput(token, _pil_to_image(sheet), info)
        count = int(block["frames"])
        if images.shape[0] < count:
            raise RuntimeError(f"Block {index + 1}: got {images.shape[0]} frames, need {count}")
        used = images[:count, ..., :3]
        h, w = int(used.shape[1]) // 2 * 2, int(used.shape[2]) // 2 * 2
        used = used[:, :h, :w]
        ffmpeg = find_ffmpeg()
        files["video"].parent.mkdir(parents=True, exist_ok=True)
        files["preview"].parent.mkdir(parents=True, exist_ok=True)
        encode_images_to_h264(ffmpeg, used, count, str(files["video"]), crf=14.0, preset="medium")
        verified = count_video_frames(ffmpeg, str(files["video"]))
        if verified != count:
            raise RuntimeError(f"Block {index + 1}: encoded {verified} frames instead of {count}")
        sheet = _contact_sheet(used)
        sheet.save(files["sheet"])
        if manifest["has_audio"]:
            run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(files["video"]),
                         "-ss", f"{block['start_frame'] / FPS:.6f}", "-t", f"{count / FPS:.6f}", "-i", manifest["source"],
                         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                         "-movflags", "+faststart", str(files["preview"])], timeout=600)
        else:
            shutil.copy2(files["video"], files["preview"])
        block.update({"render_key": _render_key(manifest, index), "verified_frames": verified, "size": [w, h],
                      "completed_at": time.time()})
        _save_plan(plan, manifest)
        del used, images
        gc.collect()
        comfy.model_management.soft_empty_cache()
        info = f"Block {index + 1}/{total} gespeichert ({verified} Frames, {w}x{h})"
        _log(info)
        preview = _preview_ui(files["preview"])
        token = f"{plan}|{index}|{block['render_key']}"
        return io.NodeOutput(token, _pil_to_image(sheet), info, ui=preview) if preview else io.NodeOutput(token, _pil_to_image(sheet), info)


# ---------------------------------------------------------------------------
# VU 4 · Finalize
# ---------------------------------------------------------------------------

class DaWVUFinalize(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWVUFinalize",
            display_name="VU 4 · Hochskaliertes Video · Originalton unverändert",
            category=CATEGORY,
            description=("Joins all blocks without re-encoding and stream-copies the source's audio (-c:a copy). "
                         "MP3/AAC go into MP4, other codecs into MKV."),
            inputs=[io.String.Input("plan", force_input=True), io.AnyType.Input("after", optional=True),
                    io.Combo.Input("container", options=["auto", "mp4", "mkv"], default="auto")],
            outputs=[io.String.Output("final_file")],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, plan, container, after=None) -> io.NodeOutput:
        manifest = _plan(plan)
        missing = [b["index"] + 1 for b in manifest["blocks"] if not _done(plan, manifest, b["index"])]
        if missing:
            raise RuntimeError(f"Blocks not rendered yet: {missing[:20]}")
        sizes = {tuple(b["size"]) for b in manifest["blocks"]}
        if len(sizes) != 1:
            raise RuntimeError(f"Blocks have different sizes {sorted(sizes)}; re-render with one target size")
        ffmpeg = find_ffmpeg()
        root = Path(plan).parent
        concat = root / "concat.txt"
        concat.write_text("".join(f"file '{_files(plan, b['index'])['video'].as_posix()}'\n" for b in manifest["blocks"]), encoding="utf-8")
        silent = root / "joined_silent.mp4"
        run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                     "-an", "-c:v", "copy", str(silent)], timeout=7200)
        frames = count_video_frames(ffmpeg, str(silent))
        codec = _audio_codec(manifest["source"]) if manifest["has_audio"] else None
        suffix = container if container != "auto" else ("mp4" if codec in {None, "mp3", "aac", "mp3float", "alac"} else "mkv")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        w, h = next(iter(sizes))
        final = (Path(folder_paths.get_output_directory()) / "video" / PROJECTS /
                 f"{manifest['project_name']}_{sanitize_name(manifest['method_tag'], 'upscale')}_{w}x{h}_{stamp}.{suffix}")
        final.parent.mkdir(parents=True, exist_ok=True)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent)]
        if manifest["has_audio"]:
            command += ["-i", manifest["source"], "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy"]
        else:
            command += ["-map", "0:v:0", "-c:v", "copy"]
        if suffix == "mp4":
            command += ["-movflags", "+faststart"]
        run_command(command + [str(final)], timeout=7200)
        manifest.update({"final_output": str(final), "final_frames": frames, "completed_at": time.time()})
        _save_plan(plan, manifest)
        _log(f"COMPLETE {final} · {frames} frames · {w}x{h} · audio {codec or 'none'} stream-copied")
        preview = _preview_ui(final)
        return io.NodeOutput(str(final), ui=preview) if preview else io.NodeOutput(str(final))


UPSCALE_NODES = [DaWVUPlanner, DaWVULoadBlock, DaWH3VideoToAVLatent, DaWH3PromptOnce, DaWVUSaveBlock, DaWVUFinalize]
