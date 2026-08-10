from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageOps

try:
    import av  # PyAV ships with current ComfyUI installations.
except Exception:  # FFmpeg fallbacks cover every operation used by this extension.
    av = None

H3_FPS = 24.0
H3_MAX_FRAMES = 3600
ANALYSIS_SAMPLE_RATE = 12000
DEFAULT_H3_TURBO_LORA = r"MiniMax H3\minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"


def sanitize_name(value: str, default: str = "Intro_Music_Video") -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    value = re.sub(r"_+", "_", value).strip("._-")
    return value[:96] or default


def atomic_write_json(path: str | Path, value: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def read_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def update_manifest(path: str | Path, updater) -> dict[str, Any]:
    manifest = read_json(path)
    updater(manifest)
    manifest["updated_at"] = time.time()
    atomic_write_json(path, manifest)
    return manifest


def sha256_file(path: str, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def lightweight_file_fingerprint(path: str) -> str:
    stat = os.stat(path)
    digest = hashlib.sha256()
    digest.update(os.path.abspath(path).encode("utf-8", "surrogatepass"))
    digest.update(str(stat.st_size).encode())
    digest.update(str(stat.st_mtime_ns).encode())
    with open(path, "rb") as handle:
        digest.update(handle.read(1024 * 1024))
        if stat.st_size > 1024 * 1024:
            handle.seek(max(0, stat.st_size - 1024 * 1024))
            digest.update(handle.read(1024 * 1024))
    return digest.hexdigest()


def align_h3_frames(frame_count: int) -> int:
    frame_count = max(5, int(frame_count))
    aligned = frame_count + ((5 - frame_count) % 17)
    if aligned > H3_MAX_FRAMES:
        raise ValueError(f"One H3 scene would require {aligned} frames, above the node limit {H3_MAX_FRAMES}.")
    return aligned


def normalize_server_address(address: str) -> str:
    address = (address or "127.0.0.1:8188").strip().rstrip("/")
    if not re.match(r"^https?://", address, flags=re.I):
        address = "http://" + address
    return address


def run_command(command: list[str], *, input_bytes: bytes | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, input=input_bytes, capture_output=True, check=False, timeout=timeout)
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\n{error}")
    return result


def find_ffmpeg() -> str:
    candidates: list[str | None] = [os.environ.get("FFMPEG_PATH"), shutil.which("ffmpeg"), shutil.which("ffmpeg.exe")]
    try:
        import imageio_ffmpeg  # type: ignore
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    for module_name in ("videohelpersuite.utils", "videohelpersuite.load_video_nodes"):
        try:
            module = __import__(module_name, fromlist=["ffmpeg_path"])
            candidates.append(getattr(module, "ffmpeg_path", None))
        except Exception:
            pass
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
        resolved = shutil.which(candidate)
        if resolved:
            return os.path.abspath(resolved)
    raise RuntimeError(
        "FFmpeg was not found. Put ffmpeg.exe on PATH, set FFMPEG_PATH, or keep "
        "ComfyUI-VideoHelperSuite installed with a working FFmpeg configuration."
    )


def find_ffprobe(ffmpeg: str) -> str:
    directory = os.path.dirname(os.path.abspath(ffmpeg))
    names = ["ffprobe.exe", "ffprobe"] if os.name == "nt" else ["ffprobe", "ffprobe.exe"]
    for name in names:
        sibling = os.path.join(directory, name)
        if os.path.isfile(sibling):
            return sibling
        found = shutil.which(name)
        if found:
            return os.path.abspath(found)
    raise RuntimeError("ffprobe was not found next to FFmpeg or on PATH")


def probe_audio_duration(ffmpeg: str, path: str) -> float:
    if av is not None:
        try:
            with av.open(path, mode="r") as container:
                if not container.streams.audio:
                    raise ValueError(f"No audio stream found in '{path}'")
                stream = container.streams.audio[0]
                if stream.duration is not None and stream.time_base is not None:
                    value = float(stream.duration * stream.time_base)
                    if math.isfinite(value) and value > 0:
                        return value
                if container.duration is not None:
                    value = float(container.duration / av.time_base)
                    if math.isfinite(value) and value > 0:
                        return value
        except Exception:
            pass
    ffprobe = find_ffprobe(ffmpeg)
    result = run_command([
        ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration:format=duration",
        "-of", "json", path,
    ], timeout=120)
    payload = json.loads(result.stdout.decode("utf-8", "replace"))
    values = []
    for stream in payload.get("streams", []):
        values.append(stream.get("duration"))
    values.append(payload.get("format", {}).get("duration"))
    for raw in values:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            return value
    raise ValueError(f"Could not determine audio duration for '{path}'")


def decode_analysis_mono(ffmpeg: str, path: str, sample_rate: int = ANALYSIS_SAMPLE_RATE) -> np.ndarray:
    result = run_command([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-map", "0:a:0", "-vn",
        "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1",
    ], timeout=1200)
    samples = np.frombuffer(result.stdout, dtype="<f4").astype(np.float32, copy=True)
    if samples.size < sample_rate // 2:
        raise ValueError("The selected song contains less than half a second of decodable audio")
    samples[~np.isfinite(samples)] = 0.0
    return samples


def decode_audio_for_comfy(ffmpeg: str, path: str) -> dict[str, Any]:
    # FFmpeg fallback is deliberately used even when PyAV is present: it normalizes odd layouts reliably.
    sample_rate = 48000
    result = run_command([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-map", "0:a:0", "-vn",
        "-ac", "2", "-ar", str(sample_rate), "-f", "f32le", "pipe:1",
    ], timeout=600)
    data = np.frombuffer(result.stdout, dtype="<f4").astype(np.float32, copy=True)
    if data.size < 2:
        raise ValueError(f"No decodable audio samples found in '{path}'")
    usable = data.size - (data.size % 2)
    waveform = torch.from_numpy(data[:usable].reshape(-1, 2).T).unsqueeze(0).contiguous()
    return {"waveform": waveform, "sample_rate": sample_rate}


def extract_segment_audio(
    ffmpeg: str,
    source_path: str,
    destination: str,
    start_seconds: float,
    output_duration_seconds: float,
) -> None:
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_name(destination_path.stem + ".tmp" + destination_path.suffix)
    run_command([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start_seconds:.9f}", "-i", source_path,
        "-map", "0:a:0", "-vn", "-af", "apad", "-t", f"{output_duration_seconds:.9f}",
        "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(temporary),
    ], timeout=600)
    if not temporary.exists() or temporary.stat().st_size < 1024:
        raise RuntimeError(f"FFmpeg did not produce a valid segment audio file: {temporary}")
    os.replace(temporary, destination_path)


def save_reference_image_from_input(source_path: str, destination: str) -> None:
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG", optimize=True)


def save_reference_tensor(image: torch.Tensor, destination: str) -> None:
    if image is None or not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[0] < 1:
        raise ValueError("Expected a non-empty ComfyUI IMAGE tensor")
    array = (
        image[0, ..., :3].detach().float().cpu().clamp(0.0, 1.0).mul(255.0).add(0.5).to(torch.uint8).numpy()
    )
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array, mode="RGB").save(destination, format="PNG", optimize=True)


def load_image_tensor(path: str) -> torch.Tensor:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0).contiguous()


def canonical_reference_frame(path: str, width: int, height: int) -> np.ndarray:
    """Contain a reference image without cropping and return an RGB uint8 video frame."""
    if width <= 0 or height <= 0:
        raise ValueError("Reference-frame dimensions must be positive")
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        contained = ImageOps.contain(image, (int(width), int(height)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (int(width), int(height)), (8, 8, 8))
    offset = ((int(width) - contained.width) // 2, (int(height) - contained.height) // 2)
    canvas.paste(contained, offset)
    return np.asarray(canvas, dtype=np.uint8).copy()


def save_canonical_reference_frame(path: str, destination: str, width: int, height: int) -> None:
    frame = canonical_reference_frame(path, width, height)
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame, mode="RGB").save(destination, format="PNG", optimize=True)


def encode_images_to_h264(
    ffmpeg: str,
    images: torch.Tensor,
    frame_count: int,
    output_path: str,
    *,
    crf: float,
    preset: str,
    first_frame_path: str | None = None,
) -> None:
    if not isinstance(images, torch.Tensor) or images.ndim != 4:
        raise ValueError("images must be [frames, height, width, channels]")
    if frame_count <= 0 or int(images.shape[0]) < frame_count:
        raise ValueError(f"Decoded H3 output has {int(images.shape[0])} frames, but {frame_count} are required")
    height, width = int(images.shape[1]), int(images.shape[2])
    if width % 2 or height % 2:
        raise ValueError("H.264 yuv420p requires even width and height")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.stem + ".tmp" + output.suffix)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s:v", f"{width}x{height}", "-r", "24", "-i", "pipe:0", "-an", "-c:v", "libx264",
        "-preset", preset, "-crf", f"{float(crf):.3f}", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-video_track_timescale", "90000", str(temporary),
    ]
    forced_first_frame = canonical_reference_frame(first_frame_path, width, height) if first_frame_path else None
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for start in range(0, frame_count, 8):
            chunk = images[start:min(frame_count, start + 8), ..., :3]
            array = chunk.detach().float().cpu().clamp(0.0, 1.0).mul(255.0).add(0.5).to(torch.uint8).contiguous().numpy()
            if start == 0 and forced_first_frame is not None:
                array[0] = forced_first_frame
            process.stdin.write(array.tobytes(order="C"))
        process.stdin.close()
        error = process.stderr.read() if process.stderr is not None else b""
        if process.stderr is not None:
            process.stderr.close()
        return_code = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    if return_code != 0:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise RuntimeError(f"FFmpeg failed while encoding a segment ({return_code}):\n{error.decode('utf-8', 'replace')}")
    if not temporary.exists() or temporary.stat().st_size < 512:
        raise RuntimeError("FFmpeg returned success but did not create a valid segment video")
    os.replace(temporary, output)


def count_video_frames(ffmpeg: str, path: str) -> int:
    """Count decoded frames, preferring PyAV so ffprobe is not required."""
    class _NoVideoStreamError(ValueError):
        pass

    if av is not None:
        try:
            with av.open(path) as container:
                video_streams = list(container.streams.video)
                if not video_streams:
                    raise _NoVideoStreamError(f"No video stream found in {path}")
                return sum(1 for _ in container.decode(video=0))
        except _NoVideoStreamError as exc:
            raise ValueError(str(exc)) from exc
        except Exception:
            # Keep the command-line probe for unsupported/corrupt media. PyAV's
            # FFmpeg errors inherit ValueError, so only our explicit no-stream
            # sentinel may bypass this fallback.
            pass
    ffprobe = find_ffprobe(ffmpeg)
    result = run_command([
        ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames,nb_frames", "-of", "json", path,
    ], timeout=300)
    payload = json.loads(result.stdout.decode("utf-8", "replace"))
    streams = payload.get("streams") or []
    if not streams:
        raise ValueError(f"No video stream found in {path}")
    for key in ("nb_read_frames", "nb_frames"):
        raw = streams[0].get(key)
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return 0


def _robust_normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        return values
    low, high = np.percentile(values, [10.0, 95.0])
    if not math.isfinite(float(low)) or not math.isfinite(float(high)) or high <= low + 1e-12:
        return np.zeros_like(values)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _smooth(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or values.size < 3:
        return values.astype(np.float32, copy=True)
    kernel = np.ones(width, dtype=np.float32) / float(width)
    return np.convolve(values, kernel, mode="same").astype(np.float32)


def _estimate_tempo(onset: np.ndarray, feature_rate: float) -> tuple[float, int, int]:
    centered = onset.astype(np.float64) - float(np.mean(onset))
    if not np.any(np.abs(centered) > 1e-7):
        lag = max(1, round(feature_rate * 0.5))
        return 120.0, lag, 0
    fft_size = 1 << int(math.ceil(math.log2(max(2, centered.size * 2))))
    spectrum = np.fft.rfft(centered, n=fft_size)
    autocorrelation = np.fft.irfft(spectrum * np.conjugate(spectrum), n=fft_size)[:centered.size]
    lag_min = max(1, int(round(feature_rate * 60.0 / 190.0)))
    lag_max = min(centered.size - 1, int(round(feature_rate * 60.0 / 55.0)))
    if lag_max <= lag_min:
        lag = max(1, round(feature_rate * 0.5))
        return 120.0, lag, 0
    scores = autocorrelation[lag_min:lag_max + 1].copy()
    for offset, lag in enumerate(range(lag_min, lag_max + 1)):
        if lag * 2 < autocorrelation.size:
            scores[offset] += 0.35 * autocorrelation[lag * 2]
        if lag // 2 >= lag_min:
            scores[offset] += 0.15 * autocorrelation[lag // 2]
    best_lag = lag_min + int(np.argmax(scores))
    bpm = 60.0 * feature_rate / best_lag
    while bpm < 78.0:
        bpm *= 2.0
        best_lag = max(1, int(round(best_lag / 2)))
    while bpm > 172.0:
        bpm /= 2.0
        best_lag *= 2
    phase_scores = [float(np.sum(onset[offset::best_lag])) for offset in range(best_lag)]
    return float(bpm), int(best_lag), int(np.argmax(phase_scores) if phase_scores else 0)


def _build_beat_track(onset: np.ndarray, feature_rate: float, lag: int, phase: int) -> list[dict[str, Any]]:
    beats: list[dict[str, Any]] = []
    search = max(1, int(round(0.12 * feature_rate)))
    previous = -1
    number = 0
    for expected in range(phase, onset.size, max(1, lag)):
        low, high = max(0, expected - search), min(onset.size, expected + search + 1)
        if high <= low:
            continue
        refined = low + int(np.argmax(onset[low:high]))
        if refined <= previous:
            continue
        beats.append({
            "time": refined / feature_rate,
            "strength": float(onset[refined]),
            "beat_number": number,
            "bar_start": number % 4 == 0,
        })
        previous = refined
        number += 1
    return beats


def _parse_timed_text(text: str, duration: float) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return []
    pattern = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]\s*(.*)")
    timed: list[dict[str, Any]] = []
    plain: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            fraction_raw = match.group(3) or "0"
            timed.append({
                "time": int(match.group(1)) * 60 + int(match.group(2)) + int(fraction_raw) / (10 ** len(fraction_raw)),
                "text": match.group(4).strip(),
            })
        else:
            plain.append(line)
    if timed:
        return sorted(timed, key=lambda item: item["time"])
    step = duration / max(1, len(plain))
    return [{"time": index * step, "text": line} for index, line in enumerate(plain)]


def _text_excerpt(timed_text: list[dict[str, Any]], start: float, end: float) -> str:
    if not timed_text:
        return ""
    selected = [item["text"] for item in timed_text if start - 0.5 <= float(item["time"]) < end + 0.5]
    if not selected:
        midpoint = (start + end) / 2.0
        selected = [min(timed_text, key=lambda item: abs(float(item["time"]) - midpoint))["text"]]
    return " / ".join(str(value) for value in selected[:3] if value)[:360]


def analyze_song_and_plan_segments(
    ffmpeg: str,
    audio_path: str,
    *,
    target_seconds: float,
    min_seconds: float,
    max_seconds: float,
    lyrics_or_story: str,
) -> dict[str, Any]:
    if not (0.5 <= min_seconds <= target_seconds <= max_seconds <= 149.0):
        raise ValueError("Scene durations must satisfy 0.5 <= min <= target <= max <= 149 seconds")
    probed_duration = probe_audio_duration(ffmpeg, audio_path)
    samples = decode_analysis_mono(ffmpeg, audio_path, ANALYSIS_SAMPLE_RATE)
    decoded_duration = samples.size / float(ANALYSIS_SAMPLE_RATE)
    duration = min(probed_duration, decoded_duration) if abs(probed_duration - decoded_duration) > 0.25 else decoded_duration

    fft_size, hop = 1024, 256
    if samples.size < fft_size:
        samples = np.pad(samples, (0, fft_size - samples.size))
    frames = np.lib.stride_tricks.sliding_window_view(samples, fft_size)[::hop]
    weighted = frames * np.hanning(fft_size).astype(np.float32)
    rms = np.sqrt(np.mean(weighted * weighted, axis=1) + 1e-12).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(weighted, axis=1)).astype(np.float32)
    log_spectrum = np.log1p(spectrum)
    flux = np.zeros(frames.shape[0], dtype=np.float32)
    if frames.shape[0] > 1:
        flux[1:] = np.maximum(log_spectrum[1:] - log_spectrum[:-1], 0.0).sum(axis=1)
    frequencies = np.fft.rfftfreq(fft_size, d=1.0 / ANALYSIS_SAMPLE_RATE).astype(np.float32)
    centroid = (spectrum * frequencies).sum(axis=1) / (spectrum.sum(axis=1) + 1e-9)

    feature_rate = ANALYSIS_SAMPLE_RATE / float(hop)
    onset = _robust_normalize(_smooth(flux, max(1, int(feature_rate * 0.08))))
    energy = _robust_normalize(_smooth(rms, max(1, int(feature_rate * 0.50))))
    brightness = _robust_normalize(_smooth(centroid, max(1, int(feature_rate * 0.75))))
    novelty = np.zeros_like(energy)
    look = max(1, int(feature_rate * 1.5))
    if energy.size > look:
        novelty[look:] += np.abs(energy[look:] - energy[:-look])
        novelty[look:] += 0.5 * np.abs(brightness[look:] - brightness[:-look])
    novelty = _robust_normalize(_smooth(novelty, max(1, int(feature_rate * 0.35))))

    bpm, beat_lag, beat_phase = _estimate_tempo(onset, feature_rate)
    beats = _build_beat_track(onset, feature_rate, beat_lag, beat_phase)
    total_frames = max(5, int(math.ceil(duration * H3_FPS - 1e-9)))
    min_frames = max(5, int(round(min_seconds * H3_FPS)))
    target_frames = max(min_frames, int(round(target_seconds * H3_FPS)))
    max_frames = max(target_frames, int(round(max_seconds * H3_FPS)))

    candidates: list[dict[str, Any]] = []
    for beat in beats:
        frame = int(round(float(beat["time"]) * H3_FPS))
        feature_index = min(onset.size - 1, max(0, int(round(float(beat["time"]) * feature_rate))))
        candidates.append({**beat, "frame": frame, "novelty": float(novelty[feature_index])})

    boundaries = [0]
    while total_frames - boundaries[-1] > max_frames:
        start = boundaries[-1]
        desired, low = start + target_frames, start + min_frames
        high = min(total_frames - min_frames, start + max_frames)
        eligible = [candidate for candidate in candidates if low <= int(candidate["frame"]) <= high]
        if eligible:
            span = max(1, high - low)
            def score(candidate: dict[str, Any]) -> float:
                proximity = 1.0 - min(1.0, abs(int(candidate["frame"]) - desired) / span)
                return 1.45 * proximity + 0.75 * float(candidate["strength"]) + 0.95 * float(candidate["novelty"]) + (0.45 if candidate["bar_start"] else 0.0)
            boundary = int(max(eligible, key=score)["frame"])
        else:
            boundary = min(high, max(low, desired))
        boundaries.append(boundary if boundary > start else min(total_frames, start + target_frames))
    boundaries.append(total_frames)
    if len(boundaries) >= 3 and boundaries[-1] - boundaries[-2] < min_frames:
        boundaries.pop(-2)

    timed_text = _parse_timed_text(lyrics_or_story, duration)
    median_energy = float(np.median(energy))
    segments: list[dict[str, Any]] = []
    for index, (start_frame, end_frame) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        exact_frames = int(end_frame - start_frame)
        start, end = start_frame / H3_FPS, min(duration, end_frame / H3_FPS)
        f0 = max(0, min(energy.size - 1, int(start * feature_rate)))
        f1 = max(f0 + 1, min(energy.size, int(math.ceil(end * feature_rate))))
        segment_energy = float(np.mean(energy[f0:f1]))
        segment_onset = float(np.mean(onset[f0:f1]))
        segment_novelty = float(np.max(novelty[f0:f1]))
        previous_energy = float(np.mean(energy[max(0, f0 - (f1 - f0)):f0])) if f0 > 0 else segment_energy
        if index == 0:
            role = "opening / intro"
        elif index == len(boundaries) - 2:
            role = "finale / outro"
        elif segment_novelty > 0.76 and segment_energy > median_energy:
            role = "drop or chorus transition"
        elif segment_energy > 0.72:
            role = "high-energy chorus / peak"
        elif segment_energy < 0.27:
            role = "quiet breakdown / atmospheric passage"
        elif segment_energy > previous_energy + 0.12:
            role = "rising build"
        elif segment_energy < previous_energy - 0.12:
            role = "release / cooldown"
        else:
            role = "steady verse / development"
        h3_frames = align_h3_frames(exact_frames)
        segments.append({
            "index": index,
            "start_frame": int(start_frame),
            "end_frame": int(end_frame),
            "target_frames": exact_frames,
            "h3_frames": h3_frames,
            "start": start,
            "end": end,
            "duration": exact_frames / H3_FPS,
            "conditioning_audio_duration": h3_frames / H3_FPS,
            "energy": segment_energy,
            "onset_density": segment_onset,
            "structural_change": segment_novelty,
            "progress": ((start + end) / 2.0) / max(duration, 1e-6),
            "role": role,
            "text_excerpt": _text_excerpt(timed_text, start, end),
        })

    return {
        "duration": duration,
        "decoded_duration": decoded_duration,
        "estimated_bpm": bpm,
        "beat_count": len(beats),
        "target_video_frames": total_frames,
        "target_video_duration": total_frames / H3_FPS,
        "analysis_summary": {
            "energy_mean": float(np.mean(energy)),
            "energy_max": float(np.max(energy)),
            "onset_mean": float(np.mean(onset)),
            "brightness_mean": float(np.mean(brightness)),
        },
        "segments": segments,
    }


CAMERAS_LOW = [
    "a restrained slow dolly-in with stable framing", "a gentle lateral tracking shot with subtle parallax",
    "a slow floating crane movement", "a quiet locked-off composition with natural micro-movement",
]
CAMERAS_MID = [
    "a smooth orbit around the subject", "a controlled handheld follow shot",
    "a medium-speed push through layered foreground elements", "a sweeping side-to-side tracking move",
]
CAMERAS_HIGH = [
    "a fast kinetic orbit with clean motion arcs", "an energetic forward chase shot timed to the rhythm",
    "a dramatic crane dive followed by a rapid pull-back", "a forceful low-angle tracking shot with rhythmic camera accents",
]
ACTIONS_LOW = [
    "subtle breathing, fabric movement, drifting particles, and small expressive gestures",
    "slow environmental transformation and restrained character motion",
    "delicate light pulses and calm movement that leaves visual room for the music",
]
ACTIONS_MID = [
    "purposeful performance movement, evolving scenery, and rhythmic environmental motion",
    "clear body movement with synchronized background activity and practical effects",
    "a readable visual action that develops continuously across the shot",
]
ACTIONS_HIGH = [
    "controlled lead-vocal performance with one clear gesture and stable anatomy",
    "decisive but restrained singer movement, rhythmic light response, and readable hands",
    "an energetic facial performance with subtle hair and fabric motion while the body remains anatomically stable",
]
LIGHTING = [
    "cinematic volumetric lighting with controlled contrast", "neon reflections and layered practical lights",
    "soft atmospheric backlight with moving highlights", "high-contrast stage lighting with rhythmic pulses",
    "moonlit haze with selective saturated accents",
]
IDENTITY_LOCK = "identity lock (recommended)"
PREVIOUS_FRAME_CONTINUITY = "previous-frame continuity"
BOTH_REFERENCES = "both references (experimental)"


def _reference_prefix(
    has_base_reference: bool,
    has_previous_reference: bool,
    reference_strategy: str,
) -> str:
    lines: list[str] = []
    picture = 1
    if has_base_reference:
        if reference_strategy == IDENTITY_LOCK:
            lines.append(
                f"<Picture {picture}> is the immutable cast, identity, wardrobe, hairstyle, color-palette, rendering-style, and production-design bible. "
                "Reproduce the same adult singer and the same visible garment design in every shot; it is not loose inspiration."
            )
        else:
            lines.append(f"Use <Picture {picture}> as the persistent identity, face, body, clothing, color palette, and production-design reference.")
        picture += 1
    if has_previous_reference:
        lines.append(f"Use <Picture {picture}> only as the immediate continuity anchor from the preceding shot; continue its pose, lighting direction, spatial logic, and screen direction without freezing the image.")
    lines.append("Use <Audio 1> as the exact temporal reference for performance energy, movement accents, environmental reactions, and camera rhythm.")
    if reference_strategy == IDENTITY_LOCK and has_base_reference:
        lines.append(
            "Show exactly one adult singer, never a second person, clone, crowd, reflection-double, or body duplicate. "
            "Keep one consistent photorealistic cinematic language and one coherent location family. Keep anatomy conservative and readable: exactly two arms and two hands, natural shoulders and fingers, no fused or extra limbs."
        )
    return " ".join(lines)


def build_deterministic_prompts(
    segments: list[dict[str, Any]],
    master_visual_concept: str,
    *,
    has_base_reference: bool,
    continuity: bool,
    reference_strategy: str = IDENTITY_LOCK,
) -> list[str]:
    master = " ".join((master_visual_concept or "").split()) or "A coherent cinematic performance-driven music video with an evolving visual story."
    prompts: list[str] = []
    total = len(segments)
    for segment in segments:
        index = int(segment["index"])
        energy = float(segment["energy"])
        if energy < 0.35:
            camera, action = CAMERAS_LOW[index % len(CAMERAS_LOW)], ACTIONS_LOW[index % len(ACTIONS_LOW)]
        elif energy > 0.68:
            camera, action = CAMERAS_HIGH[index % len(CAMERAS_HIGH)], ACTIONS_HIGH[index % len(ACTIONS_HIGH)]
        else:
            camera, action = CAMERAS_MID[index % len(CAMERAS_MID)], ACTIONS_MID[index % len(ACTIONS_MID)]
        if reference_strategy == IDENTITY_LOCK and has_base_reference:
            previous = False
        else:
            previous = continuity and index > 0
        base_for_shot = has_base_reference and not (reference_strategy == PREVIOUS_FRAME_CONTINUITY and index > 0)
        excerpt = str(segment.get("text_excerpt") or "").strip()
        lyric = f"Current lyrical or narrative cue: {excerpt}. Translate it into imagery without showing the words. " if excerpt else ""
        ending = "Resolve into a deliberate, memorable final composition." if index == total - 1 else "End on a clean composition that cuts naturally into the next shot."
        lighting = LIGHTING[0] if reference_strategy == IDENTITY_LOCK and has_base_reference else LIGHTING[index % len(LIGHTING)]
        prompts.append(
            _reference_prefix(base_for_shot, previous, reference_strategy)
            + f" Global music-video concept: {master} Shot {index + 1} of {total}; musical function: {segment['role']}; relative energy {energy:.2f}. "
            + f"Create one uninterrupted cinematic shot using {camera}. Show {action}. Lighting: {lighting}. "
            + lyric + ending
            + " Preserve anatomy and identity, maintain coherent motion, and avoid duplicate subjects, internal jump cuts, subtitles, captions, unrelated logos, watermarks, and random text. Preserve any intentional garment graphic already visible in the reference."
        )
    return prompts


def _extract_json_array(text: str) -> list[Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("The local LLM did not return a JSON array")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, list):
        raise ValueError("The local LLM response is not a JSON list")
    return value


def query_local_llm_scene_prompts(
    *,
    base_url: str,
    model: str,
    timeout: float,
    segments: list[dict[str, Any]],
    master_visual_concept: str,
    lyrics_or_story: str,
    has_base_reference: bool,
    continuity: bool,
    reference_strategy: str = IDENTITY_LOCK,
) -> list[str]:
    base = (base_url or "http://127.0.0.1:8080/v1").rstrip("/")
    if not re.match(r"^https?://", base, flags=re.I):
        base = "http://" + base
    model = (model or "").strip()
    if not model:
        with urllib.request.urlopen(urllib.request.Request(base + "/models", method="GET"), timeout=timeout) as response:
            models = json.loads(response.read().decode("utf-8")).get("data") or []
        if not models:
            raise RuntimeError("The local OpenAI-compatible endpoint returned no models")
        model = str(models[0]["id"])
    compact = [{
        "index": item["index"], "start": round(float(item["start"]), 3), "end": round(float(item["end"]), 3),
        "role": item["role"], "energy": round(float(item["energy"]), 3),
        "onset_density": round(float(item["onset_density"]), 3), "text_excerpt": item.get("text_excerpt", ""),
    } for item in segments]
    body = {
        "model": model,
        "temperature": 0.65,
        "top_p": 0.9,
        "max_tokens": max(2048, min(12000, len(segments) * 240)),
        "messages": [
            {"role": "system", "content": (
                "You are a rigorous cinematic music-video shot planner. Return only a JSON array with one object per supplied segment: "
                "{\"index\": integer, \"shot\": concise English visual description}. Build one coherent arc while varying locations, action, framing and camera movement. "
                "Describe exactly one uninterrupted shot per segment. Never request visible lyrics, subtitles, logos, watermarks, duplicate subjects, or internal jump cuts. "
                "Do not include MiniMax reference tags; the workflow adds them safely."
            )},
            {"role": "user", "content": json.dumps({
                "global_concept": master_visual_concept,
                "lyrics_or_story": (lyrics_or_story or "")[:16000],
                "segments": compact,
            }, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        base + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = json.loads(response.read().decode("utf-8"))["choices"][0]["message"]["content"]
    items = _extract_json_array(str(content))
    by_index: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item["index"])
            shot = " ".join(str(item.get("shot") or item.get("prompt") or "").split())
        except Exception:
            continue
        if shot:
            by_index[index] = shot
    if len(by_index) != len(segments) or any(index not in by_index for index in range(len(segments))):
        raise ValueError(f"The local LLM returned {len(by_index)} usable shots for {len(segments)} segments")
    prompts: list[str] = []
    for index, segment in enumerate(segments):
        previous = continuity and index > 0 and reference_strategy != IDENTITY_LOCK
        base_for_shot = has_base_reference and not (reference_strategy == PREVIOUS_FRAME_CONTINUITY and index > 0)
        prompts.append(
            _reference_prefix(base_for_shot, previous, reference_strategy)
            + f" Global concept: {master_visual_concept}. Shot {index + 1} of {len(segments)}, musical role {segment['role']}, relative energy {float(segment['energy']):.2f}. "
            + by_index[index]
            + " Preserve anatomy, stable identity and temporal coherence. No subtitles, captions, logos, watermarks, random text, duplicate subject, or internal jump cut."
        )
    return prompts


def build_segment_api_prompt(manifest_path: str, segment_index: int, manifest: dict[str, Any]) -> dict[str, Any]:
    settings = manifest["settings"]
    segment = manifest["segments"][segment_index]
    patched_model = "15" if settings["spectrum_enabled"] else "14"
    prompt: dict[str, Any] = {
        "1": {"class_type": "DaWH3MusicVideoLoadSegment", "inputs": {"manifest_path": manifest_path, "segment_index": segment_index}},
        "10": {"class_type": "CLIPLoader", "inputs": {"clip_name": settings["text_encoder"], "type": "minimax", "device": "default"}},
        "11": {"class_type": "VAELoader", "inputs": {"vae_name": settings["video_vae"]}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": settings["audio_vae"]}},
        "13": {"class_type": "UNETLoader", "inputs": {"unet_name": settings["diffusion_model"], "weight_dtype": "default"}},
        "14": {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": ["13", 0], "shift_video": settings["shift_video"], "shift_audio": settings["shift_audio"]}},
        "16": {"class_type": "RandomNoise", "inputs": {"noise_seed": ["1", 4]}},
        "17": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
            "clip": ["10", 0], "vae": ["11", 0], "audio_vae": ["12", 0], "prompt": ["1", 3],
            "width": settings["width"], "height": settings["height"], "length": ["1", 1],
            "ref_image_size": settings.get("ref_image_size", "match"), "ref_audios.ref_audio_0": ["1", 0],
        }},
        "18": {"class_type": "BasicGuider", "inputs": {"model": [patched_model, 0], "conditioning": ["17", 0]}},
        "19": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": settings["sampler_name"]}},
        "20": {"class_type": "BasicScheduler", "inputs": {"model": [patched_model, 0], "scheduler": settings["scheduler"], "steps": settings["steps"], "denoise": 1.0}},
        "21": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["16", 0], "guider": ["18", 0], "sampler": ["19", 0], "sigmas": ["20", 0], "latent_image": ["17", 1]}},
        "22": {"class_type": "VAEDecode", "inputs": {"samples": ["21", 0], "vae": ["11", 0]}},
        "23": {"class_type": "DaWH3MusicVideoSaveSegment", "inputs": {"images": ["22", 0], "manifest_path": manifest_path, "segment_index": segment_index, "target_frames": ["1", 2]}},
    }
    image_input = 0
    reference_strategy = settings.get("reference_strategy", BOTH_REFERENCES)
    has_base_reference = bool(manifest.get("reference_image_path"))
    use_base_reference = has_base_reference and not (
        reference_strategy == PREVIOUS_FRAME_CONTINUITY and segment_index > 0
    )
    use_previous_reference = bool(settings["continuity"] and segment_index > 0) and (
        not has_base_reference or reference_strategy in {PREVIOUS_FRAME_CONTINUITY, BOTH_REFERENCES}
    )
    if use_base_reference:
        prompt["2"] = {"class_type": "DaWH3MusicVideoLoadImagePath", "inputs": {"image_path": manifest["reference_image_path"]}}
        prompt["17"]["inputs"][f"ref_images.ref_image_{image_input}"] = ["2", 0]
        image_input += 1
    if use_previous_reference:
        previous = manifest["segments"][segment_index - 1]["continuity_path"]
        prompt["3"] = {"class_type": "DaWH3MusicVideoLoadImagePath", "inputs": {"image_path": previous}}
        prompt["17"]["inputs"][f"ref_images.ref_image_{image_input}"] = ["3", 0]
    if settings["spectrum_enabled"]:
        prompt["15"] = {"class_type": "SpectrumApplyMiniMaxH3", "inputs": {
            "model": ["14", 0], "enabled": True, "blend_weight": settings["spectrum_blend_weight"],
            "degree": settings["spectrum_degree"], "ridge_lambda": settings["spectrum_ridge_lambda"],
            "window_size": settings["spectrum_window_size"], "flex_window": settings["spectrum_flex_window"],
            "warmup_steps": settings["spectrum_warmup_steps"], "tail_actual_steps": settings["spectrum_tail_actual_steps"],
            "max_history": settings["spectrum_max_history"], "debug": settings["spectrum_debug"],
            "history_storage": settings["spectrum_history_storage"],
        }}
    model_source = ["13", 0]
    if settings.get("dual_gpu", False):
        prompt.update({
            "30": {"class_type": "SelectCLIPDevice", "inputs": {"clip": ["10", 0], "device": settings.get("clip_device", "gpu:1")}},
            "31": {"class_type": "SelectVAEDevice", "inputs": {"vae": ["11", 0], "device": settings.get("vae_device", "gpu:1")}},
            "32": {"class_type": "SelectVAEDevice", "inputs": {"vae": ["12", 0], "device": settings.get("vae_device", "gpu:1")}},
            "33": {"class_type": "SelectModelDevice", "inputs": {"model": ["13", 0], "device": settings.get("model_device", "gpu:0")}},
        })
        model_source = ["33", 0]
        prompt["17"]["inputs"].update({"clip": ["30", 0], "vae": ["31", 0], "audio_vae": ["32", 0]})
        prompt["22"]["inputs"]["vae"] = ["31", 0]
    prompt["29"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": model_source,
        "lora_name": settings.get("turbo_lora", DEFAULT_H3_TURBO_LORA),
        "strength_model": 1.0,
    }}
    prompt["14"]["inputs"]["model"] = ["29", 0]
    return prompt


def build_finalize_api_prompt(manifest_path: str) -> dict[str, Any]:
    return {"1": {"class_type": "DaWH3MusicVideoFinalize", "inputs": {"manifest_path": manifest_path}}}


def queue_prompt(server_address: str, prompt: dict[str, Any], prompt_id: str | None = None) -> dict[str, Any]:
    base = normalize_server_address(server_address)
    body = {"prompt": prompt, "prompt_id": prompt_id or str(uuid.uuid4())}
    request = urllib.request.Request(
        base + "/prompt", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Comfy-Usage-Source": "DaWasteh-H3-MusicVideo"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"ComfyUI rejected a generated child prompt ({exc.code}): {detail}") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not reach the local ComfyUI API at {base}") from exc
    if "prompt_id" not in payload:
        raise RuntimeError(f"Unexpected response from ComfyUI /prompt: {payload}")
    return payload


def get_active_prompt_ids(server_address: str) -> set[str]:
    base = normalize_server_address(server_address)
    try:
        with urllib.request.urlopen(base + "/queue", timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return set()
    active: set[str] = set()
    for key in ("queue_running", "queue_pending"):
        for item in payload.get(key, []) or []:
            if isinstance(item, list) and len(item) > 1:
                active.add(str(item[1]))
    return active


def segment_files_valid(ffmpeg: str, manifest: dict[str, Any]) -> list[bool]:
    result: list[bool] = []
    for segment in manifest["segments"]:
        path = str(segment["video_path"])
        valid = os.path.isfile(path) and os.path.getsize(path) >= 512
        if valid:
            try:
                valid = count_video_frames(ffmpeg, path) == int(segment["target_frames"])
            except Exception:
                valid = False
        result.append(valid)
    return result


def concat_and_mux_project(ffmpeg: str, manifest_path: str) -> str:
    manifest = read_json(manifest_path)
    valid = segment_files_valid(ffmpeg, manifest)
    if not all(valid):
        missing = [str(manifest["segments"][index]["video_path"]) for index, ok in enumerate(valid) if not ok]
        raise RuntimeError("Cannot finalize; segment files are missing or invalid:\n" + "\n".join(missing[:10]))
    project_dir = Path(manifest["project_dir"])
    concat_file = project_dir / "concat.txt"
    lines = []
    for segment in manifest["segments"]:
        normalized = os.path.abspath(str(segment["video_path"])).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{normalized}'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    silent_concat = project_dir / "joined_video_silent.mp4"
    try:
        run_command([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-an", "-c:v", "copy", "-avoid_negative_ts", "make_zero", str(silent_concat),
        ], timeout=7200)
    except Exception:
        settings = manifest["settings"]
        run_command([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-an", "-r", "24", "-c:v", "libx264", "-preset", settings["video_preset"], "-crf", str(settings["final_crf"]),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent_concat),
        ], timeout=14400)
    output = Path(manifest["final_output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    joined_deliverable = project_dir / f"joined_video{output.suffix.lower()}"
    joined_temporary = joined_deliverable.with_name(joined_deliverable.stem + ".tmp" + joined_deliverable.suffix)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent_concat), "-i", manifest["source_audio_copy"],
        "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "1", "-c:v", "copy", "-c:a", "copy",
    ]
    if output.suffix.lower() == ".mp4":
        command += ["-movflags", "+faststart"]
    command.append(str(joined_temporary))
    try:
        run_command(command, timeout=7200)
    except Exception as exc:
        if output.suffix.lower() == ".mp4":
            raise RuntimeError(
                "MP4 rejected the original audio codec while -c:a copy was enforced. Use MKV to preserve WAV/PCM, FLAC, Opus or other codecs unchanged."
            ) from exc
        raise
    if not joined_temporary.exists() or joined_temporary.stat().st_size < 1024:
        raise RuntimeError("Final mux returned success but no joined deliverable was created")
    os.replace(joined_temporary, joined_deliverable)

    temporary = output.with_name(output.stem + ".tmp" + output.suffix)
    shutil.copy2(joined_deliverable, temporary)
    os.replace(temporary, output)

    def record_deliverables(value: dict[str, Any]) -> None:
        value["silent_concat_path"] = str(silent_concat)
        value["joined_deliverable_path"] = str(joined_deliverable)

    update_manifest(manifest_path, record_deliverables)
    return str(output)
