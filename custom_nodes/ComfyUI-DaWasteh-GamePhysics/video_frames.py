"""Bounded frame-only VHS adapter: never cache/materialize its lazy audio map."""

from pathlib import Path
import math


def load_frames(loader, video, fps, width, height, frame_limit):
    if not math.isfinite(fps) or not 1 <= fps <= 60:
        raise ValueError("fps must be finite and between 1 and 60")
    if not 1 <= frame_limit <= 93:
        raise ValueError("frame_limit must be between 1 and 93")
    if any(size < 64 or size > 2048 or size % 8 for size in (width, height)):
        raise ValueError("Dimensions must be multiples of 8 between 64 and 2048")
    path = Path(video)
    if (
        path.is_absolute()
        or ":" in video
        or ".." in video.replace("\\", "/").split("/")
    ):
        raise ValueError("Choose a local video within ComfyUI/input")
    # VHS returns a LazyAudioMap even when its AUDIO output is disconnected.
    # ComfyUI's RAM-cache scan iterates that map and can kill prompt_worker for
    # silent videos. Discard it here without accessing/iterating any audio value.
    result = loader.load_video(
        video=video,
        force_rate=fps,
        custom_width=width,
        custom_height=height,
        frame_load_cap=frame_limit,
        skip_first_frames=0,
        select_every_nth=1,
        format="Wan",
    )
    images = result[0]
    if not 1 <= images.shape[0] <= frame_limit:
        raise ValueError("Decoder returned an unexpected frame count")
    return images
