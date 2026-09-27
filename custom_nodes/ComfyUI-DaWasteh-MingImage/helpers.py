"""Pure helpers for the v1.2.9 Ming Image nodes (no ComfyUI import, unit-testable).

The resolution buckets and the transparency phrase follow inclusionAI's reference implementation
(https://github.com/inclusionAI/Ming-Image, MIT, see prompts/LICENSE-Ming-Image.txt): a reference image is
resized to the bucket entry whose height/width ratio is closest to its own, without cropping.
"""
from __future__ import annotations

import json
import math
import re

import numpy as np

# Keys are height/width ratios, values [height, width] (bailingmm_utils.process_ratio, Ming-Image f39a706).
ASPECT_RATIO_512 = {
    "0.25": [256, 1024], "0.26": [256, 992], "0.27": [256, 960], "0.28": [256, 928],
    "0.32": [288, 896], "0.33": [288, 864], "0.35": [288, 832], "0.4": [320, 800],
    "0.42": [320, 768], "0.48": [352, 736], "0.5": [352, 704], "0.52": [352, 672],
    "0.5455": [384, 704], "0.57": [384, 672], "0.6": [384, 640], "0.65": [416, 640],
    "0.68": [416, 608], "0.72": [416, 576], "0.78": [448, 576],
    "0.82": [448, 544], "0.88": [480, 544], "0.94": [480, 512],
    "1.0": [512, 512], "1.07": [512, 480], "1.13": [544, 480], "1.21": [544, 448],
    "1.29": [576, 448], "1.38": [576, 416],
    "1.46": [608, 416], "1.5385": [640, 416], "1.67": [640, 384], "1.75": [672, 384],
    "1.8333": [704, 384], "2.0": [704, 352], "2.09": [736, 352], "2.4": [768, 320],
    "2.5": [800, 320], "2.89": [832, 288], "3.0": [864, 288], "3.11": [896, 288],
    "3.62": [928, 256], "3.75": [960, 256], "3.88": [992, 256], "4.0": [1024, 256],
}
ASPECT_RATIO_1024 = {
    "0.25": [512, 2048], "0.26": [512, 1984], "0.27": [512, 1920], "0.28": [512, 1856],
    "0.32": [576, 1792], "0.33": [576, 1728], "0.35": [576, 1664], "0.4": [640, 1600],
    "0.42": [640, 1536], "0.48": [704, 1472], "0.5": [704, 1408], "0.52": [704, 1344],
    "0.5581": [768, 1376], "0.5625": [720, 1280], "0.5647": [768, 1360], "0.57": [768, 1344],
    "0.6": [768, 1280], "0.622": [816, 1312], "0.625": [800, 1280], "0.65": [832, 1280],
    "0.6582": [832, 1264], "0.6667": [832, 1248], "0.6709": [848, 1264], "0.68": [832, 1216],
    "0.7013": [864, 1232], "0.72": [832, 1152], "0.7467": [896, 1200], "0.75": [864, 1152],
    "0.7568": [896, 1184], "0.78": [896, 1152], "0.8": [896, 1120], "0.8056": [928, 1152],
    "0.82": [896, 1088], "0.88": [960, 1088], "0.94": [960, 1024], "0.9846": [1024, 1040],
    "1.0": [1024, 1024], "1.07": [1024, 960], "1.13": [1088, 960], "1.21": [1088, 896],
    "1.2414": [1152, 928], "1.25": [1120, 896], "1.2807": [1168, 912], "1.29": [1152, 896],
    "1.3333": [1152, 864], "1.3393": [1200, 896], "1.38": [1152, 832], "1.46": [1216, 832],
    "1.4906": [1264, 848], "1.5": [1248, 832], "1.6": [1280, 800], "1.67": [1280, 768],
    "1.75": [1344, 768], "1.7708": [1360, 768], "1.7778": [1280, 720], "2.0": [1408, 704],
    "2.09": [1472, 704], "2.4": [1536, 640], "2.5": [1600, 640], "2.89": [1664, 576],
    "3.0": [1728, 576], "3.11": [1792, 576], "3.62": [1856, 512], "3.75": [1920, 512],
    "3.88": [1984, 512], "4.0": [2048, 512],
}
BUCKETS = {512: ASPECT_RATIO_512, 1024: ASPECT_RATIO_1024}

# One of the ten fixed phrases from the official "transparent-background generation" tip; exactly one, first.
# v1.2.9 test (1024 px, 3 subjects, INT8 and BF16): this phrase gave real alpha most often (3 of 6); the model still
# paints white or a fake checkerboard in many runs, hence the BiRefNet fallback (alpha_or_mask).
ALPHA_PREFIX = "transparent canvas, not white, not checkerboard"
ALPHA_MIN_SHARE = 0.02
ALPHA_HINT = ("The result is a transparent RGBA cutout: describe only the subject and its own parts, "
              "no background, floor, frame or backdrop layer.")

LAYER_COUNT_PATTERNS = (
    re.compile(r"Number of layers:\s*(\d+)", re.I),
    re.compile(r"Decompose this image into\s+(\d+)\s+layers", re.I),
)
MAX_LAYERS = 12


def bucket_size(height: int, width: int, bucket: int) -> tuple[int, int]:
    """(height, width) of the official bucket entry whose h/w ratio is closest to the image's."""
    if height <= 0 or width <= 0:
        raise ValueError(f"invalid image size {width}x{height}")
    table = BUCKETS[int(bucket)]
    ratio = height / width
    key = min(table, key=lambda k: abs(float(k) - ratio))
    h, w = table[key]
    return int(h), int(w)


def parse_layer_count(text: str) -> int | None:
    """Layer count from 'Number of layers: N' (preferred) or 'Decompose this image into N layers'."""
    for pattern in LAYER_COUNT_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return int(match.group(1))
    return None


def layer_spec(plan: str, layers: int) -> str:
    """The rough plan the layer model (or the enhancer) receives; the official CLI default when the plan is empty."""
    plan = (plan or "").strip()
    if parse_layer_count(plan) is not None:
        return plan
    header = f"Decompose this image into {int(layers)} layers."
    return header if not plan else f"{header}\n{plan}"


def valid_layer_answer(text: str) -> bool:
    """An enhancer answer the layer model can use: a count in range and one line per layer."""
    count = parse_layer_count(text)
    if count is None or not 1 <= count <= MAX_LAYERS:
        return False
    lines = re.findall(r"^\s*Layer\s+(\d+)\s*:", text, re.M | re.I)
    return [int(n) for n in lines] == list(range(1, count + 1))


def strip_fences(text: str) -> str:
    """Remove a ```json ... ``` wrapper and surrounding whitespace."""
    text = (text or "").strip()
    match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", text, re.S)
    return match.group(1).strip() if match else text


def json_prompt(text: str) -> str | None:
    """The rewriter's JSON object as compact-but-readable text, or None when it is not the required schema."""
    body = strip_fences(text)
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(body[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("layers"), list) or "canvas_settings" not in data:
        return None
    return json.dumps(data, ensure_ascii=False, indent=2)


def canvas_note(width: int, height: int) -> str:
    """'Canvas: 2048 × 2048 px, aspect ratio 1:1.' for the rewriter (empty when the size is unknown)."""
    width, height = int(width or 0), int(height or 0)
    if width <= 0 or height <= 0:
        return ""
    d = math.gcd(width, height)
    ratio = f"{width // d}:{height // d}" if max(width, height) // d <= 32 else f"{width / height:.2f}:1"
    return f"\n\nCanvas: {width} × {height} px, aspect ratio {ratio}."


def with_alpha_prefix(prompt: str) -> str:
    prompt = (prompt or "").strip()
    return prompt if prompt.startswith(ALPHA_PREFIX) else f"{ALPHA_PREFIX}\n{prompt}"


def first_accepted(generate, accept, seed: int):
    """Answer of generate(seed) that passes accept, else one retry with seed + 1000 (the v1.2.5 fix for answers that
    stop early), else None. Returns (answer or None, list of rejected answers)."""
    rejected = []
    for attempt_seed in (int(seed), int(seed) + 1000):
        answer = strip_fences(generate(attempt_seed))
        if accept(answer):
            return answer, rejected
        rejected.append(answer)
    return None, rejected


def resolve_prompt(task: str, text: str, enhance: bool, layers: int, *, t2i_system: str, layer_template: str,
                   rewrite=None, has_image: bool = False, width: int = 0, height: int = 0) -> tuple[str, int]:
    """Final (prompt, layer count) of the prompt writer.

    rewrite(user, system, accept) -> accepted answer or None (None also when no LLM is configured); only called with
    enhance on. design/transparent: the official rewriter's JSON caption (transparent adds the official RGBA prefix).
    layers: the official guided prompt with the rough plan; the layer count comes from the final specification.
    """
    if task == "layers":
        spec = layer_spec(text, layers)
        prompt = spec
        if enhance and has_image and rewrite is not None:
            answer = rewrite(layer_template.replace("{spec}", spec), None, valid_layer_answer)
            if answer is not None:
                prompt = answer.strip()
        count = parse_layer_count(prompt) or int(layers)
        if not 1 <= count <= MAX_LAYERS:
            raise ValueError(f"Ebenenzahl {count} außerhalb 1..{MAX_LAYERS}")
        return prompt, count
    if task not in ("design", "transparent"):
        raise ValueError(f"unknown task {task!r}")
    request = (text or "").strip()
    if not request:
        raise ValueError("Bitte beschreiben, was entstehen soll (Knoten PROMPT). / Please enter a prompt.")
    prompt = request
    if enhance and rewrite is not None:
        user = request + canvas_note(width, height)
        if task == "transparent":
            user = f"{user}\n\n{ALPHA_HINT}"
        answer = rewrite(user, t2i_system, lambda out: json_prompt(out) is not None)
        if answer is not None:
            prompt = json_prompt(answer)
    if task == "transparent":
        prompt = with_alpha_prefix(prompt)
    return prompt, int(layers)


def split_layer_frames(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Decoded frames [F,H,W,C] -> (composite [H,W,C], layers [F-1,H,W,4]); frame 0 is the model's composite.

    Layer 1 (index 0) is the front-most layer, the last one the background, as in the official output.
    RGB-only frames get an opaque alpha channel.
    """
    frames = np.asarray(frames, dtype=np.float32)
    if frames.ndim != 4 or frames.shape[0] < 2:
        raise ValueError(f"expected composite + at least one layer as [F,H,W,C], got {frames.shape}")
    if frames.shape[-1] == 3:
        frames = np.concatenate([frames, np.ones_like(frames[..., :1])], axis=-1)
    frames = np.clip(frames[..., :4], 0.0, 1.0)
    return frames[0], frames[1:]


def composite_layers(layers: np.ndarray, background=(1.0, 1.0, 1.0)) -> np.ndarray:
    """Stack RGBA layers back to front (last = background, first = front-most) over a solid colour -> RGB."""
    layers = np.asarray(layers, dtype=np.float32)
    canvas = np.empty(layers.shape[1:3] + (3,), dtype=np.float32)
    canvas[...] = np.asarray(background, dtype=np.float32)
    for layer in layers[::-1]:
        alpha = layer[..., 3:4]
        canvas = layer[..., :3] * alpha + canvas * (1.0 - alpha)
    return canvas


def checkerboard(height: int, width: int, cell: int = 32) -> np.ndarray:
    """Light grey checkerboard [H,W,3] that makes transparency visible in previews."""
    yy, xx = np.meshgrid(np.arange(height) // cell, np.arange(width) // cell, indexing="ij")
    tone = np.where((yy + xx) % 2 == 0, 0.92, 0.78).astype(np.float32)
    return np.repeat(tone[..., None], 3, axis=-1)


def over_checkerboard(rgba: np.ndarray, cell: int = 32) -> np.ndarray:
    """RGBA [H,W,4] (or RGB) over a checkerboard -> RGB."""
    rgba = np.asarray(rgba, dtype=np.float32)
    if rgba.shape[-1] == 3:
        return np.clip(rgba, 0.0, 1.0)
    board = checkerboard(rgba.shape[0], rgba.shape[1], cell)
    alpha = np.clip(rgba[..., 3:4], 0.0, 1.0)
    return np.clip(rgba[..., :3], 0.0, 1.0) * alpha + board * (1.0 - alpha)


def alpha_or_mask(rgba: np.ndarray, mask: np.ndarray | None, min_share: float = ALPHA_MIN_SHARE) -> tuple[np.ndarray, str]:
    """Keep Ming's own alpha when at least `min_share` of the image is transparent; otherwise take the foreground mask
    (BiRefNet, 1 = subject) as alpha. Returns (RGBA [H,W,4], "ming" | "mask" | "opaque")."""
    rgba = np.asarray(rgba, dtype=np.float32)
    if rgba.shape[-1] == 3:
        rgba = np.concatenate([rgba, np.ones_like(rgba[..., :1])], axis=-1)
    if alpha_coverage(rgba) >= min_share:
        return rgba, "ming"
    if mask is None:
        return rgba, "opaque"
    mask = np.clip(np.asarray(mask, dtype=np.float32), 0.0, 1.0)
    if mask.shape != rgba.shape[:2]:
        raise ValueError(f"mask {mask.shape} does not match image {rgba.shape[:2]}")
    out = rgba.copy()
    out[..., 3] = mask
    return out, "mask"


def alpha_coverage(rgba: np.ndarray) -> float:
    """Share of clearly transparent pixels (alpha < 0.05); 0 for RGB input."""
    rgba = np.asarray(rgba, dtype=np.float32)
    if rgba.shape[-1] < 4:
        return 0.0
    return float((rgba[..., 3] < 0.05).mean())
