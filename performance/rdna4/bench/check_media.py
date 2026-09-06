"""Quality / sanity checks for benchmark outputs (images, video, audio).

  python check_media.py FILE [FILE ...]              -> JSON facts per file
  python check_media.py --compare A B                -> PSNR / mean abs diff between two outputs (same seed A/B)

Checks: dimensions, frame count, fps, duration, sample rate, channels,
decodability, NaN/Inf (audio), black/empty frames, silence, per-frame stats.
These are automatic checks only; they do not replace a visual/auditory review.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
AUDIO_EXT = {".flac", ".mp3", ".wav", ".ogg", ".opus", ".m4a"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def video_frames(path: Path, max_frames: int | None = None):
    import av

    with av.open(str(path)) as c:
        vs = next((s for s in c.streams if s.type == "video"), None)
        if vs is None:
            return None, []
        frames = []
        for i, fr in enumerate(c.decode(vs)):
            frames.append(fr.to_ndarray(format="gray"))
            if max_frames and len(frames) >= max_frames:
                break
        return vs, frames


def analyze_video(path: Path) -> dict:
    import av

    out = {"kind": "video"}
    with av.open(str(path)) as c:
        out["container_duration_s"] = (c.duration / 1e6) if c.duration else None
        for s in c.streams:
            if s.type == "video":
                out["width"], out["height"] = s.codec_context.width, s.codec_context.height
                out["fps"] = float(s.average_rate) if s.average_rate else None
                out["codec"] = s.codec_context.name
                out["stream_frames_meta"] = s.frames
            elif s.type == "audio":
                out["audio_codec"] = s.codec_context.name
                out["audio_sample_rate"] = s.codec_context.sample_rate
                out["audio_channels"] = s.codec_context.channels
    vs, frames = video_frames(path)
    out["frames_decoded"] = len(frames)
    if frames:
        means = np.array([f.mean() for f in frames])
        stds = np.array([f.std() for f in frames])
        out["frame_mean_luma"] = {"min": float(means.min()), "mean": float(means.mean()), "max": float(means.max())}
        out["frame_std_luma"] = {"min": float(stds.min()), "mean": float(stds.mean())}
        out["black_frames"] = int(((means < 8) & (stds < 4)).sum())
        out["flat_frames"] = int((stds < 2).sum())
        if len(frames) > 1:
            diffs = [float(np.abs(frames[i].astype(np.int16) - frames[i - 1].astype(np.int16)).mean()) for i in range(1, len(frames))]
            out["mean_interframe_absdiff"] = float(np.mean(diffs))
            out["frozen_pairs"] = int(sum(1 for d in diffs if d < 0.05))
        out["video_duration_s"] = len(frames) / out["fps"] if out.get("fps") else None
    if out.get("audio_codec"):
        out.update({("audio_" + k): v for k, v in analyze_audio(path).items() if k not in ("kind",)})
    return out


def analyze_audio(path: Path) -> dict:
    import av

    out = {"kind": "audio"}
    chunks = []
    with av.open(str(path)) as c:
        s = next((st for st in c.streams if st.type == "audio"), None)
        if s is None:
            out["error"] = "no audio stream"
            return out
        out["sample_rate"] = s.codec_context.sample_rate
        out["channels"] = s.codec_context.channels
        out["codec"] = s.codec_context.name
        resampler = av.AudioResampler(format="fltp", layout="stereo" if s.codec_context.channels >= 2 else "mono",
                                      rate=s.codec_context.sample_rate)
        for fr in c.decode(s):
            for rf in resampler.resample(fr):
                chunks.append(rf.to_ndarray())
    if not chunks:
        out["error"] = "no audio decoded"
        return out
    x = np.concatenate(chunks, axis=1).astype(np.float32)
    out["samples"] = int(x.shape[1])
    out["duration_s"] = x.shape[1] / out["sample_rate"]
    out["nan_inf"] = int((~np.isfinite(x)).sum())
    xf = np.nan_to_num(x)
    out["peak"] = float(np.abs(xf).max())
    out["rms"] = float(np.sqrt((xf ** 2).mean()))
    win = max(1, out["sample_rate"] // 10)
    n = x.shape[1] // win
    if n:
        seg = xf[:, : n * win].reshape(xf.shape[0], n, win)
        seg_rms = np.sqrt((seg ** 2).mean(axis=(0, 2)))
        out["silent_100ms_fraction"] = float((seg_rms < 1e-4).mean())
        out["clipped_fraction"] = float((np.abs(xf) >= 0.999).mean())
    return out


def analyze_image(path: Path) -> dict:
    from PIL import Image

    im = Image.open(path)
    arr = np.asarray(im.convert("RGB")).astype(np.float32)
    return {"kind": "image", "width": im.width, "height": im.height, "mode": im.mode,
            "mean": float(arr.mean()), "std": float(arr.std()),
            "black": bool(arr.mean() < 8 and arr.std() < 4), "flat": bool(arr.std() < 2)}


def analyze(path: Path) -> dict:
    ext = path.suffix.lower()
    base = {"file": str(path), "bytes": path.stat().st_size if path.exists() else None}
    if not path.exists():
        return {**base, "error": "missing"}
    try:
        if ext in VIDEO_EXT:
            base.update(analyze_video(path))
        elif ext in AUDIO_EXT:
            base.update(analyze_audio(path))
        elif ext in IMAGE_EXT:
            base.update(analyze_image(path))
        else:
            base["error"] = f"unsupported extension {ext}"
    except Exception as e:
        base["error"] = f"{type(e).__name__}: {e}"
    return base


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(((a.astype(np.float64) - b.astype(np.float64)) ** 2).mean())
    if mse == 0:
        return float("inf")
    return 10 * np.log10(255.0 ** 2 / mse)


def compare(a: Path, b: Path) -> dict:
    ext = a.suffix.lower()
    out = {"a": str(a), "b": str(b)}
    if ext in IMAGE_EXT:
        from PIL import Image

        xa = np.asarray(Image.open(a).convert("RGB"))
        xb = np.asarray(Image.open(b).convert("RGB"))
        if xa.shape != xb.shape:
            out["error"] = f"shape mismatch {xa.shape} vs {xb.shape}"
            return out
        out["psnr_db"] = psnr(xa, xb)
        out["mean_abs_diff"] = float(np.abs(xa.astype(np.int16) - xb.astype(np.int16)).mean())
        out["identical"] = bool(np.array_equal(xa, xb))
    elif ext in VIDEO_EXT:
        _, fa = video_frames(a)
        _, fb = video_frames(b)
        n = min(len(fa), len(fb))
        out["frames_a"], out["frames_b"] = len(fa), len(fb)
        if n == 0 or fa[0].shape != fb[0].shape:
            out["error"] = "no comparable frames"
            return out
        ps = [psnr(fa[i], fb[i]) for i in range(n)]
        out["psnr_db_mean"] = float(np.mean([p for p in ps if np.isfinite(p)])) if any(np.isfinite(ps)) else float("inf")
        out["psnr_db_min"] = float(min(ps))
        out["identical_frames"] = int(sum(1 for i in range(n) if np.array_equal(fa[i], fb[i])))
        if any(s.type == "audio" for s in []):
            pass
        try:
            aa, ab = analyze_audio(a), analyze_audio(b)
            if "rms" in aa and "rms" in ab:
                out["audio_rms_a"], out["audio_rms_b"] = aa["rms"], ab["rms"]
                out["audio_duration_a"], out["audio_duration_b"] = aa["duration_s"], ab["duration_s"]
        except Exception:
            pass
    elif ext in AUDIO_EXT:
        import av

        def load(p):
            chunks = []
            with av.open(str(p)) as c:
                s = next(st for st in c.streams if st.type == "audio")
                rs = av.AudioResampler(format="fltp", layout="stereo", rate=s.codec_context.sample_rate)
                for fr in c.decode(s):
                    for rf in rs.resample(fr):
                        chunks.append(rf.to_ndarray())
            return np.concatenate(chunks, axis=1)

        xa, xb = load(a), load(b)
        n = min(xa.shape[1], xb.shape[1])
        out["samples_a"], out["samples_b"] = int(xa.shape[1]), int(xb.shape[1])
        d = xa[:, :n] - xb[:, :n]
        out["max_abs_diff"] = float(np.abs(d).max())
        out["rms_diff"] = float(np.sqrt((d ** 2).mean()))
        out["snr_db"] = float(10 * np.log10((xa[:, :n] ** 2).mean() / max((d ** 2).mean(), 1e-20)))
        out["identical"] = bool(np.array_equal(xa[:, :n], xb[:, :n]) and xa.shape == xb.shape)
    else:
        out["error"] = "unsupported"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--compare", nargs=2)
    ap.add_argument("--json-out")
    a = ap.parse_args()
    if a.compare:
        res = compare(Path(a.compare[0]), Path(a.compare[1]))
    else:
        res = [analyze(Path(f)) for f in a.files]
    text = json.dumps(res, ensure_ascii=False, indent=1, default=str)
    print(text)
    if a.json_out:
        Path(a.json_out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
