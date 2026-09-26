"""Pure helpers for the v1.2.8 vision tools (no ComfyUI import, unit-testable)."""
from __future__ import annotations

import numpy as np

MASK_THRESHOLD = 0.5

EMPTY_MASK_MESSAGE = (
    "Keine Maske gemalt: Bitte im Knoten 'MASKE MALEN · Inpaint Crop' den Editor öffnen und den Bereich "
    "übermalen, der verändert werden soll (oder am BILD-Knoten Rechtsklick → Open in MaskEditor). "
    "Ohne Maske würde das Bild unverändert zurückkommen. / No mask painted: paint the area to change first."
)


def mask_pixels(mask) -> int:
    """Number of mask pixels that count as painted (> 0.5), summed over the batch."""
    array = np.asarray(mask, dtype=np.float32)
    return int((array > MASK_THRESHOLD).sum())


def require_mask(mask, min_pixels: int) -> int:
    """Return the painted pixel count or raise the user-facing error when the mask is (almost) empty."""
    painted = mask_pixels(mask)
    if painted < max(1, int(min_pixels)):
        raise ValueError(f"{EMPTY_MASK_MESSAGE} (gemalte Pixel: {painted}, Minimum: {max(1, int(min_pixels))})")
    return painted


def expand_pose_boxes(bboxes, width: int, height: int, aspect: float = 0.75, scale: float = 1.25):
    """Grow person boxes to the pose model's aspect (w/h) around their centre, like MMPose's top-down crop.

    SDPoseKeypointExtractor stretches every box to 768x1024 without keeping the aspect ratio; a standing person
    (box ~1:3) is squeezed about 2x sideways. Boxes are clipped to the image (the extractor clips anyway).
    Accepts the RT-DETR format: list (per frame) of lists of {"x", "y", "width", "height", ...} dicts.
    """
    def grow(box: dict) -> dict:
        cx, cy = box["x"] + box["width"] / 2.0, box["y"] + box["height"] / 2.0
        w, h = box["width"] * scale, box["height"] * scale
        if w / max(h, 1e-6) < aspect:
            w = h * aspect
        else:
            h = w / aspect
        x1, y1 = max(0.0, cx - w / 2.0), max(0.0, cy - h / 2.0)
        x2, y2 = min(float(width), cx + w / 2.0), min(float(height), cy + h / 2.0)
        return {**box, "x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}

    if isinstance(bboxes, dict):
        return grow(bboxes)
    return [[grow(b) for b in frame] if isinstance(frame, list) else grow(frame) for frame in bboxes]


def reset_stale_meta_batch(meta_batch, prompt: dict | None, unique_id) -> bool:
    """Close generators/writers a failed or cancelled VHS meta-batch run left open. Returns True when it reset.

    VHS resets its batch manager only when the manager node executes with requeue == 0. After a run that failed or
    was cancelled in its first batch, the manager's output is cached (same inputs), so the next run would continue the
    old generator: its first batch came from the previous video. A fresh run is requeue == 0 on the manager this
    loader is wired to; at that point nothing may be open yet.
    """
    if meta_batch is None:
        return False
    link = ((prompt or {}).get(str(unique_id)) or {}).get("inputs", {}).get("meta_batch")
    if not isinstance(link, (list, tuple)) or not link:
        return False
    manager = (prompt or {}).get(str(link[0])) or {}
    if manager.get("inputs", {}).get("requeue", 0):
        return False  # a re-queued prompt continues the running meta batch
    if not (getattr(meta_batch, "inputs", None) or getattr(meta_batch, "outputs", None)):
        return False
    frames = meta_batch.frames_per_batch
    meta_batch.reset()
    meta_batch.frames_per_batch = frames
    meta_batch.unique_id = str(link[0])
    return True


def to_uint16_gray(image) -> np.ndarray:
    """IMAGE frame (H, W, C) in [0, 1] -> (H, W) uint16 from the first channel, rounded, clipped."""
    array = np.asarray(image, dtype=np.float32)
    if array.ndim == 3:
        array = array[..., 0]
    if array.ndim != 2:
        raise ValueError(f"expected one image (H, W, C) or (H, W); got shape {array.shape}")
    return np.clip(np.rint(np.nan_to_num(array, nan=0.0) * 65535.0), 0, 65535).astype(np.uint16)
