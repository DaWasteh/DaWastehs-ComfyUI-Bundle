"""Real-time one-image face swap for Windows/RDNA4 through ONNX Runtime DirectML.

The pipeline follows the FaceFusion/Deep-Live-Cam recipe without importing either
application or the ``insightface`` package (its ``onnx`` import collides with the
protobuf pin of the audio packs): SCRFD detection (``buffalo_l/det_10g``), ArcFace
identity embedding (``w600k_r50``), ``inswapper_128`` or ``hyperswap_1a_256`` as the swapper, an optional
GFPGAN 1.4 / GPEN-BFR-256 face enhancer, a blurred box mask paste-back and the
existing latest-frame Spout transport. All ONNX sessions run on one DirectML
adapter; ComfyUI's ROCm/HIP torch device is not involved, so the swap can share
the R9700 with OBS/Spout or run on the RX 9070 XT.

Model licences (see docs/LIVE_FACE_SWAP_V099.md): inswapper_128 non-commercial,
hyperswap_1a_256 ResearchRAIL, GFPGAN Apache-2.0, GPEN non-commercial, buffalo_l
non-commercial research. Nothing is downloaded automatically.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

LOGGER = logging.getLogger(__name__)

# Normalised five-point templates (left eye, right eye, nose, mouth corners),
# identical to the FaceFusion warp templates.
WARP_TEMPLATES: dict[str, np.ndarray] = {
    "arcface_128": np.array(
        [
            [0.36167656, 0.40387734],
            [0.63696719, 0.40235469],
            [0.50019687, 0.56044219],
            [0.38710391, 0.72160547],
            [0.61507734, 0.72034453],
        ],
        dtype=np.float32,
    ),
    "ffhq_512": np.array(
        [
            [0.37691676, 0.46864664],
            [0.62285697, 0.46912813],
            [0.50123859, 0.61331904],
            [0.39308822, 0.72541100],
            [0.61150205, 0.72490465],
        ],
        dtype=np.float32,
    ),
    # DeepFaceLab "whole face" crop used by DeepFaceLive .dfm models
    "dfl_whole_face": np.array(
        [
            [0.35342266, 0.39285716],
            [0.62797622, 0.39285716],
            [0.48660713, 0.54017860],
            [0.38839287, 0.68750011],
            [0.59821427, 0.68750011],
        ],
        dtype=np.float32,
    ),
}


@dataclass(frozen=True)
class SwapperSpec:
    file_name: str
    kind: str  # "inswapper" | "hyperswap" | "alphaface" | "uniface"
    template: str
    size: int
    mean: float
    std: float
    licence: str
    sha256: str
    source_kind: str = "embedding"  # "embedding" (ArcFace vector) | "image" (aligned source crop)
    denormalize_output: bool = False


@dataclass(frozen=True)
class MaskModelSpec:
    file_name: str
    size: int
    licence: str
    sha256: str


@dataclass(frozen=True)
class EnhancerSpec:
    file_name: str
    template: str
    size: int
    licence: str
    sha256: str


SWAPPERS: dict[str, SwapperSpec] = {
    "inswapper_128": SwapperSpec(
        "inswapper_128.onnx", "inswapper", "arcface_128", 128, 0.0, 1.0,
        "InsightFace non-commercial",
        "a290273ed497312095dac48cdef20feec9d5208298223dd01288ab202b54bea7",
    ),
    "hyperswap_1a_256": SwapperSpec(
        "hyperswap_1a_256.onnx", "hyperswap", "arcface_128", 256, 0.5, 0.5,
        "FaceFusion ResearchRAIL",
        "c0e98a8a03a238f461ed3d2570e426b49f46745ee400854a60dceeb70c246add",
        denormalize_output=True,
    ),
    "hyperswap_1c_256": SwapperSpec(
        "hyperswap_1c_256.onnx", "hyperswap", "arcface_128", 256, 0.5, 0.5,
        "FaceFusion ResearchRAIL",
        "5528c2d76fe9986c99d829278987ef9f3a630cb606db7628d02b57b330f406a5",
        denormalize_output=True,
    ),
    "alphaface_256": SwapperSpec(
        "alphaface_256.onnx", "alphaface", "arcface_128", 256, 0.0, 1.0,
        "AlphaFace non-commercial",
        "efcca3ffa1c28b75a007f689b39f7d4716c02810e7fa72d892e175f0b058a2e2",
    ),
    "uniface_256": SwapperSpec(
        "uniface_256.onnx", "uniface", "ffhq_512", 256, 0.5, 0.5,
        "UniFace (xc-csc101), licence unknown",
        "eb5ce2af024cddf88ecb93b24e29a6eb44e354aba7d3319e84d29dcd868820f3",
        source_kind="image",
        denormalize_output=True,
    ),
}

# Face occluder (hands/hair/objects in front of the face) and face parser
# (CelebAMask-HQ regions) from FaceFusion; both run on the aligned crop.
OCCLUDERS: dict[str, MaskModelSpec] = {
    # xseg_3 keeps beard, mouth interior and eyes behind glasses as face (only
    # hands/objects and the glasses frames are cut out); xseg_1 removes them all.
    "xseg_3": MaskModelSpec("xseg_3.onnx", 256, "DeepFaceLab GPL-3.0", "48ccd7e8541e159a5a754ec9e62df2f12065f7df8f9af842c1750342c6533559"),
    "xseg_2": MaskModelSpec("xseg_2.onnx", 256, "DeepFaceLab GPL-3.0", "cd9a0879eaf43841d765472cf1f8c330dbf9dcb03da0eace93e95f3bcc399042"),
    "xseg_1": MaskModelSpec("xseg_1.onnx", 256, "DeepFaceLab GPL-3.0", "c4d1498b8a03b5fe2a3a5d2ef2a0402ab03bd51edaf5b2d8d5fb764702a97dd3"),
}
PARSERS: dict[str, MaskModelSpec] = {
    "bisenet_resnet_34": MaskModelSpec("bisenet_resnet_34.onnx", 512, "yakhyo MIT", "4a0b8c958a3c938913bd06a8365dbb3c8761afba6ecbf0d14b3b1f77eb230c96"),
}
# Portrait matting for the person/background split of Workflow 17.
MATTERS: dict[str, MaskModelSpec] = {
    "modnet": MaskModelSpec("modnet.onnx", 512, "MODNet Apache-2.0", "a9edce4b47653992aacd1bee48126e65a415ed54e2ecbe51bdca25a8cab0c0d3"),
}

# CelebAMask-HQ class ids used by bisenet (FaceFusion face_mask_region_set)
FACE_REGIONS: dict[str, int] = {
    "skin": 1, "left-eyebrow": 2, "right-eyebrow": 3, "left-eye": 4, "right-eye": 5,
    "glasses": 6, "nose": 10, "mouth": 11, "upper-lip": 12, "lower-lip": 13,
}
DEFAULT_REGIONS: tuple[str, ...] = tuple(FACE_REGIONS)

ENHANCERS: dict[str, EnhancerSpec] = {
    "gpen_bfr_256": EnhancerSpec("gpen_bfr_256.onnx", "arcface_128", 256, "GPEN non-commercial", "bad8bf0426873828df2dbf4e3b3d9ababba9da7965b8b72426569486f7ae5c25"),
    "gfpgan_1.4": EnhancerSpec("gfpgan_1.4.onnx", "ffhq_512", 512, "GFPGAN Apache-2.0", "accc4757b26bdb89b32b4d3500d4f79c9dff97c1dd7c7104bf9dcb95e3311385"),
    "gpen_bfr_512": EnhancerSpec("gpen_bfr_512.onnx", "ffhq_512", 512, "GPEN non-commercial", "d5f066b9068a8b74217f9712e28e875a6144629b108a6f7355acbdb3a2832c54"),
}

DETECTOR_PACK = "buffalo_l"
DETECTOR_FILES = ("det_10g.onnx", "w600k_r50.onnx")
SWAPPER_SUBDIR = "insightface"
# DeepFaceLive .dfm models (trained per identity with DeepFaceLab; the model
# *is* the identity, no source photo needed). Listed as ``dfm/<file stem>``.
DFM_SUBDIR = "deepfacelive"
DFM_PREFIX = "dfm/"
ENHANCER_SUBDIR = "facerestore_models"
MASK_SUBDIR = "face_parsing"
MATTING_SUBDIR = "background_removal"


# --------------------------------------------------------------------------- #
# Pure geometry / image helpers (unit-tested without any model)
# --------------------------------------------------------------------------- #
def scaled_template(template: str, crop_scale: float = 1.0) -> np.ndarray:
    """Template points shrunk towards their centre; ``crop_scale`` < 1 widens the crop.

    A wider crop lets the swapper regenerate chin, beard and jaw line that the
    tight FaceFusion templates leave untouched (visible as a double chin when
    the mouth opens). The model still sees a face, only somewhat smaller.
    """
    points = WARP_TEMPLATES[template]
    scale = float(np.clip(crop_scale, 0.5, 1.5))
    if scale == 1.0:
        return points
    centre = points.mean(axis=0, keepdims=True)
    # No vertical shift: hyperswap/inswapper lose identity quickly when the face
    # sits off the trained template centre (measured: beard returns at 0.06).
    return ((points - centre) * scale + centre).astype(np.float32)


def estimate_affine(landmarks_5: np.ndarray, template: str, size: int, crop_scale: float = 1.0) -> np.ndarray:
    """Affine matrix mapping five landmarks onto ``template`` scaled to ``size``."""
    import cv2

    if landmarks_5.shape != (5, 2):
        raise ValueError("five (x, y) landmarks are required")
    target = scaled_template(template, crop_scale) * float(size)
    matrix = cv2.estimateAffinePartial2D(
        landmarks_5.astype(np.float32), target, method=cv2.RANSAC, ransacReprojThreshold=100
    )[0]
    if matrix is None:
        raise ValueError("could not estimate the face alignment matrix")
    return matrix


def warp_face(frame: np.ndarray, landmarks_5: np.ndarray, template: str, size: int, crop_scale: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    import cv2

    matrix = estimate_affine(landmarks_5, template, size, crop_scale)
    crop = cv2.warpAffine(frame, matrix, (size, size), borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_AREA)
    return crop, matrix


def create_box_mask(size: int, blur: float, padding: tuple[int, int, int, int] = (0, 0, 0, 0)) -> np.ndarray:
    """Soft rectangular blend mask; ``blur`` is a 0..1 fraction of the crop size."""
    import cv2

    blur_amount = int(size * 0.5 * float(blur))
    blur_area = max(blur_amount // 2, 1)
    mask = np.ones((size, size), dtype=np.float32)
    top, right, bottom, left = padding
    mask[: max(blur_area, int(size * top / 100)), :] = 0
    mask[-max(blur_area, int(size * bottom / 100)) :, :] = 0
    mask[:, : max(blur_area, int(size * left / 100))] = 0
    mask[:, -max(blur_area, int(size * right / 100)) :] = 0
    if blur_amount > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), blur_amount * 0.25)
    return np.clip(mask, 0.0, 1.0)


def paste_back(frame: np.ndarray, crop: np.ndarray, mask: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Blend an aligned crop back into ``frame`` using the inverse affine matrix."""
    import cv2

    height, width = frame.shape[:2]
    crop_h, crop_w = crop.shape[:2]
    inverse = cv2.invertAffineTransform(matrix)
    corners = np.array([[0, 0], [crop_w, 0], [crop_w, crop_h], [0, crop_h]], dtype=np.float32)
    projected = cv2.transform(corners[None, :, :], inverse)[0]
    x1, y1 = np.clip(np.floor(projected.min(axis=0)).astype(int), 0, [width, height])
    x2, y2 = np.clip(np.ceil(projected.max(axis=0)).astype(int), 0, [width, height])
    if x2 <= x1 or y2 <= y1:
        return frame
    shifted = inverse.copy()
    shifted[:, 2] -= (x1, y1)
    region_size = (int(x2 - x1), int(y2 - y1))
    inverse_mask = np.clip(cv2.warpAffine(mask, shifted, region_size), 0.0, 1.0).astype(np.float32)
    inverse_crop = cv2.warpAffine(crop, shifted, region_size, borderMode=cv2.BORDER_REPLICATE)
    result = frame.copy()
    region = np.ascontiguousarray(result[y1:y2, x1:x2])
    result[y1:y2, x1:x2] = cv2.blendLinear(inverse_crop, region, inverse_mask, 1.0 - inverse_mask)
    return result


def prepare_swapper_input(crop_bgr: np.ndarray, spec: SwapperSpec) -> np.ndarray:
    """BGR uint8 crop → normalised NCHW RGB float32 batch of one."""
    rgb = crop_bgr[:, :, ::-1].astype(np.float32) / 255.0
    rgb = (rgb - spec.mean) / spec.std
    return np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32)


def normalize_swapper_output(output_chw: np.ndarray, spec: SwapperSpec) -> np.ndarray:
    """Model CHW output → BGR uint8 crop."""
    rgb = output_chw.transpose(1, 2, 0)
    if spec.denormalize_output:
        rgb = rgb * spec.std + spec.mean
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.ascontiguousarray((rgb[:, :, ::-1] * 255.0).round().astype(np.uint8))


def prepare_enhancer_input(crop_bgr: np.ndarray) -> np.ndarray:
    rgb = crop_bgr[:, :, ::-1].astype(np.float32) / 255.0
    rgb = (rgb - 0.5) / 0.5
    return np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32)


def normalize_enhancer_output(output_chw: np.ndarray) -> np.ndarray:
    rgb = (np.clip(output_chw, -1.0, 1.0) + 1.0) / 2.0
    rgb = rgb.transpose(1, 2, 0)
    return np.ascontiguousarray((rgb * 255.0).round().astype(np.uint8)[:, :, ::-1])


def source_embedding_for(spec: SwapperSpec, embedding: np.ndarray, emap: np.ndarray | None) -> np.ndarray:
    """Convert a raw ArcFace embedding into the swapper's ``source`` input."""
    embedding = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
    norm = float(np.linalg.norm(embedding))
    if norm == 0.0:
        raise ValueError("source embedding has zero norm")
    if spec.kind == "inswapper":
        if emap is None:
            raise ValueError("inswapper needs the model's emap initializer")
        return np.ascontiguousarray((embedding @ emap) / norm, dtype=np.float32)
    if spec.kind == "alphaface":  # FaceFusion feeds the raw (un-normalised) ArcFace vector
        return np.ascontiguousarray(embedding, dtype=np.float32)
    return np.ascontiguousarray(embedding / norm, dtype=np.float32)


def prepare_source_image(crop_bgr: np.ndarray) -> np.ndarray:
    """Aligned source crop → NCHW RGB float32 in 0..1 (uniface/blendswap ``source``)."""
    rgb = crop_bgr[:, :, ::-1].astype(np.float32) / 255.0
    return np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32)


def sharpen_mask(mask: np.ndarray, sigma: float = 5.0) -> np.ndarray:
    """FaceFusion's mask post-processing: blur, then stretch 0.5..1 to 0..1."""
    import cv2

    blurred = cv2.GaussianBlur(np.clip(mask, 0.0, 1.0).astype(np.float32), (0, 0), sigma)
    return ((np.clip(blurred, 0.5, 1.0) - 0.5) * 2.0).astype(np.float32)


def prepare_occluder_input(crop_bgr: np.ndarray, size: int) -> np.ndarray:
    """xseg expects NHWC BGR float32 in 0..1."""
    import cv2

    resized = cv2.resize(crop_bgr, (size, size))
    return np.ascontiguousarray(resized[None].astype(np.float32) / 255.0)


_IMAGENET_MEAN_255 = (0.485 * 255.0, 0.456 * 255.0, 0.406 * 255.0)
_IMAGENET_INV_STD = np.array([1.0 / 0.229, 1.0 / 0.224, 1.0 / 0.225], dtype=np.float32).reshape(1, 3, 1, 1)


def prepare_parser_input(crop_bgr: np.ndarray, size: int) -> np.ndarray:
    """bisenet expects NCHW RGB float32 normalised with ImageNet statistics."""
    import cv2

    blob = cv2.dnn.blobFromImage(crop_bgr, 1.0 / 255.0, (size, size), _IMAGENET_MEAN_255, swapRB=True)
    blob *= _IMAGENET_INV_STD
    return np.ascontiguousarray(blob, dtype=np.float32)


def region_mask_from_classes(class_map: np.ndarray, regions: tuple[str, ...], size: int, extra: np.ndarray | None = None) -> np.ndarray:
    import cv2

    wanted = [FACE_REGIONS[name] for name in regions if name in FACE_REGIONS]
    mask = np.isin(class_map, wanted).astype(np.float32)
    if extra is not None:
        mask = np.maximum(mask, extra.astype(np.float32))
    if mask.shape[0] != size:
        mask = cv2.resize(mask, (size, size))
    return sharpen_mask(mask)


HAIR_CLASS = 17
MOUTH_CLASS = FACE_REGIONS["mouth"]


def beard_mask_from_classes(
    class_map: np.ndarray,
    template_points: np.ndarray,
    size: int,
    crop_bgr: np.ndarray | None = None,
    extent: float = 1.0,
) -> np.ndarray:
    """Beard/moustache zone on the aligned crop (float 0/1 at class-map size).

    bisenet labels beards as *skin*, so the zone is geometric: skin and neck of
    the lower face from just below the nose tip downwards, minus nose, lips and
    mouth. ``extent`` 0 disables, 1 covers moustache and chin, 0.6 chin only.
    The whole zone is smoothed (no texture test): that is temporally stable and
    hyperswap/inswapper then render bare skin there.
    """
    import cv2

    map_size = class_map.shape[0]
    if extent <= 0.0:
        return np.zeros((map_size, map_size), dtype=np.float32)
    scale = map_size / float(size)
    nose_y = float(template_points[2, 1]) * scale
    mouth_y = float((template_points[3, 1] + template_points[4, 1]) * 0.5) * scale
    eye_span = float(np.linalg.norm(template_points[1] - template_points[0])) * scale
    skin = np.isin(class_map, [FACE_REGIONS["skin"], 14])  # skin + neck
    keep = np.isin(class_map, [FACE_REGIONS["upper-lip"], FACE_REGIONS["lower-lip"], MOUTH_CLASS, FACE_REGIONS["nose"]])
    top_full = int(nose_y + eye_span * 0.15)
    top_chin = int(mouth_y + eye_span * 0.10)
    blend = float(np.clip((extent - 0.6) / 0.4, 0.0, 1.0))
    top = int(round(top_chin + (top_full - top_chin) * blend))
    mask = np.zeros((map_size, map_size), dtype=np.uint8)
    mask[top:, :] = 1
    mask &= skin.astype(np.uint8)
    if mask.any():
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, int(eye_span * 0.16)),) * 2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask[keep] = 0
    return mask.astype(np.float32)


def extend_occlusion_downward(occlusion: np.ndarray, beard_zone: np.ndarray, size: int) -> np.ndarray:
    """Let the xseg face mask grow downward inside the beard zone.

    xseg outlines the face oval and stops at the chin line, so a goatee hanging
    below the chin would keep showing through. Inside the (parser-derived) beard
    zone the mask is dilated downward by ~10 % of the crop; hands elsewhere stay
    excluded.
    """
    import cv2

    zone = beard_zone
    if zone.shape[0] != size:
        zone = cv2.resize(zone, (size, size), interpolation=cv2.INTER_NEAREST)
    reach = max(3, int(size * 0.15))
    kernel = np.ones((reach, 1), dtype=np.uint8)
    grown = cv2.dilate(occlusion, kernel, anchor=(0, reach - 1))
    return np.maximum(occlusion, grown * (zone > 0.5)).astype(np.float32)


def cheek_color(crop_bgr: np.ndarray, class_map: np.ndarray, template_points: np.ndarray, size: int) -> np.ndarray | None:
    """Median BGR of the cheek skin between eye and nose level."""
    import cv2

    map_size = class_map.shape[0]
    scale = map_size / float(size)
    nose_y = float(template_points[2, 1]) * scale
    eye_span = float(np.linalg.norm(template_points[1] - template_points[0])) * scale
    zone = np.zeros((map_size, map_size), dtype=bool)
    zone[int(max(0, nose_y - eye_span * 0.35)):int(nose_y + eye_span * 0.05), :] = True
    zone &= (class_map == FACE_REGIONS["skin"])
    if zone.sum() < 32:
        return None
    small = crop_bgr if crop_bgr.shape[0] == map_size else cv2.resize(crop_bgr, (map_size, map_size), interpolation=cv2.INTER_AREA)
    return np.median(small[zone].reshape(-1, 3), axis=0).astype(np.float32)


def shave_crop(
    crop_bgr: np.ndarray,
    beard_mask: np.ndarray,
    mode: str = "skin",
    skin_color: np.ndarray | None = None,
    skin_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Replace the beard zone with smooth skin so the swapper regenerates a bare chin.

    ``skin`` fills the zone by normalised convolution of the surrounding *skin*
    pixels (``skin_mask``: cheeks/forehead, never hair, neck or background), so
    the fill carries the real shading gradient instead of one flat colour;
    ``skin_color`` is the fallback where no skin is nearby. Runs at quarter
    resolution (~1 ms). ``inpaint`` uses OpenCV Telea inpainting (slower).
    """
    import cv2

    if beard_mask is None or not beard_mask.any():
        return crop_bgr
    size = crop_bgr.shape[0]
    binary = (beard_mask > 0.5).astype(np.uint8)
    if binary.shape[0] != size:
        binary = cv2.resize(binary, (size, size), interpolation=cv2.INTER_NEAREST)
    if mode == "inpaint":
        return cv2.inpaint(crop_bgr, binary, 3, cv2.INPAINT_TELEA)
    low = max(32, size // 4)
    small = cv2.resize(crop_bgr, (low, low), interpolation=cv2.INTER_AREA).astype(np.float32)
    small_mask = cv2.resize(binary, (low, low), interpolation=cv2.INTER_AREA).astype(np.float32)
    if skin_mask is not None:
        source = cv2.resize(skin_mask.astype(np.float32), (low, low), interpolation=cv2.INTER_AREA)
        source = np.clip(source - small_mask, 0.0, 1.0)
    else:
        source = 1.0 - small_mask
    sigma = low * 0.18
    weighted = cv2.GaussianBlur(small * source[..., None], (0, 0), sigma)
    weights = cv2.GaussianBlur(source, (0, 0), sigma)
    if skin_color is None:
        skin_color = small[source > 0.5].reshape(-1, 3).mean(axis=0) if (source > 0.5).any() else small.mean(axis=(0, 1))
    confidence = np.clip(weights / 0.05, 0.0, 1.0)[..., None]
    fill_small = (weighted / np.maximum(weights, 1e-4)[..., None]) * confidence + skin_color.reshape(1, 1, 3) * (1.0 - confidence)
    fill = cv2.resize(fill_small, (size, size), interpolation=cv2.INTER_LINEAR)
    soft = cv2.resize(cv2.GaussianBlur(small_mask, (0, 0), low * 0.04), (size, size), interpolation=cv2.INTER_LINEAR)[..., None]
    shaved = crop_bgr.astype(np.float32) * (1.0 - soft) + fill * soft
    return np.clip(shaved, 0, 255).astype(np.uint8)


def prepare_dfm_input(crop_bgr: np.ndarray) -> np.ndarray:
    """DeepFaceLive models expect a lightly sharpened NHWC BGR crop in 0..1."""
    import cv2

    sharp = cv2.addWeighted(crop_bgr, 1.75, cv2.GaussianBlur(crop_bgr, (0, 0), 2), -0.75, 0)
    return np.ascontiguousarray(sharp[None].astype(np.float32) / 255.0)


def dfm_mask(source_mask: np.ndarray, target_mask: np.ndarray, size: int) -> np.ndarray:
    """FaceFusion's deep-swapper mask: min of both model masks, eroded twice, blurred."""
    import cv2

    mask = np.minimum(np.squeeze(source_mask), np.squeeze(target_mask)).reshape(size, size).clip(0, 1).astype(np.float32)
    mask = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=2)
    return cv2.GaussianBlur(mask, (0, 0), 6.25)


def equalize_frame_color(reference: np.ndarray, target: np.ndarray, size: int) -> np.ndarray:
    import cv2

    ref_small = cv2.resize(reference, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
    tgt_small = cv2.resize(target, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
    difference = cv2.resize(ref_small - tgt_small, target.shape[:2][::-1], interpolation=cv2.INTER_CUBIC)
    return np.clip(target.astype(np.float32) + difference, 0, 255).astype(np.uint8)


def match_frame_color(reference: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Multi-scale low-frequency colour transfer (FaceFusion vision.match_frame_color)."""
    for size in np.linspace(16, target.shape[0], 3, endpoint=False):
        reference = equalize_frame_color(reference, target, max(2, int(size)))
    return equalize_frame_color(reference, target, target.shape[0])


def fix_zone_color(swapped: np.ndarray, reference: np.ndarray, zone: np.ndarray, strength: float = 0.7) -> np.ndarray:
    """Shift the swapped pixels inside ``zone`` towards the reference's LAB mean.

    The swapper renders the shaved beard zone flat and greyish; the reference is
    the shaved input whose zone carries the real skin tone.
    """
    import cv2

    if zone is None or strength <= 0.0:
        return swapped
    size = swapped.shape[0]
    binary = zone > 0.5
    if binary.shape[0] != size:
        binary = cv2.resize(zone, (size, size), interpolation=cv2.INTER_NEAREST) > 0.5
    if binary.sum() < 50:
        return swapped
    lab_swapped = cv2.cvtColor(swapped, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_reference = cv2.cvtColor(reference, cv2.COLOR_BGR2LAB).astype(np.float32)
    delta = lab_reference[binary].mean(axis=0) - lab_swapped[binary].mean(axis=0)
    soft = cv2.GaussianBlur(binary.astype(np.float32), (0, 0), size * 0.025)[..., None]
    return cv2.cvtColor(np.clip(lab_swapped + delta * soft * float(strength), 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def moustache_band(class_map: np.ndarray) -> np.ndarray:
    """Upper-lip pixels above the mouth interior: bisenet labels a moustache as lip."""
    lips = np.isin(class_map, [FACE_REGIONS["upper-lip"], FACE_REGIONS["lower-lip"]])
    mouth = class_map == MOUTH_CLASS
    band = lips.astype(np.float32)
    top = int(np.where(mouth.any(axis=1))[0].min()) if mouth.any() else class_map.shape[0]
    band[top:] = 0.0
    return band


def boost_identity(source: np.ndarray, live: np.ndarray | None, strength: float) -> np.ndarray:
    """Push the source identity away from the live face (FaceFusion face_swapper_weight).

    ``strength`` 0 = plain source embedding, 1 = source * 1.35 - live * 0.35.
    """
    if live is None or strength <= 0.0:
        return source
    amount = 0.35 * float(np.clip(strength, 0.0, 1.0))
    live = np.asarray(live, dtype=np.float32).reshape(1, -1)
    live = live / max(float(np.linalg.norm(live)), 1e-6)
    return np.ascontiguousarray(source * (1.0 + amount) - live * amount, dtype=np.float32)


def glasses_frame_mask(occlusion: np.ndarray, template_points: np.ndarray, size: int) -> np.ndarray:
    """Thin glasses frames = what xseg cuts out inside the eye band (uint8 0/1)."""
    import cv2

    eye_y = float((template_points[0, 1] + template_points[1, 1]) * 0.5)
    eye_span = float(np.linalg.norm(template_points[1] - template_points[0]))
    band = np.zeros((size, size), dtype=np.uint8)
    band[int(max(0, eye_y - eye_span * 0.6)):int(min(size, eye_y + eye_span * 0.6)), :] = 1
    cut = ((occlusion < 0.5).astype(np.uint8)) & band
    if cut.any():
        cut = cv2.dilate(cut, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    return cut


def remove_glasses_frames(crop_bgr: np.ndarray, frame_mask: np.ndarray) -> np.ndarray:
    """Inpaint the thin frame lines so the swapper renders a face without glasses."""
    import cv2

    if frame_mask is None or not frame_mask.any():
        return crop_bgr
    return cv2.inpaint(crop_bgr, frame_mask.astype(np.uint8), 3, cv2.INPAINT_TELEA)


def feather_mask(mask: np.ndarray, sigma: float) -> np.ndarray:
    import cv2

    if sigma <= 0.0:
        return mask
    return cv2.GaussianBlur(mask, (0, 0), float(sigma)).astype(np.float32)


def temporal_blend(previous: np.ndarray | None, current: np.ndarray, weight: float) -> np.ndarray:
    """EMA in crop space (face-aligned, so a plain blend is motion-compensated enough)."""
    if previous is None or weight <= 0.0 or previous.shape != current.shape:
        return current
    keep = float(np.clip(weight, 0.0, 0.9))
    if current.dtype == np.uint8:
        mixed = previous.astype(np.float32) * keep + current.astype(np.float32) * (1.0 - keep)
        return np.clip(mixed, 0, 255).astype(np.uint8)
    return (previous * keep + current * (1.0 - keep)).astype(current.dtype)


def prepare_matting_input(frame_bgr: np.ndarray, size: int) -> np.ndarray:
    """MODNet expects NCHW RGB float32 normalised to -1..1."""
    import cv2

    resized = cv2.resize(frame_bgr, (size, size), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(cv2.dnn.blobFromImage(resized, 1.0 / 127.5, (size, size), (127.5, 127.5, 127.5), swapRB=True), dtype=np.float32)


def color_statistics(image_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    """LAB mean/std per channel inside ``mask`` as a (2, 3) array, or None."""
    import cv2

    region = mask > 0.5
    if region.sum() < 64:
        return None
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)[region]
    return np.stack([lab.mean(axis=0), np.maximum(lab.std(axis=0), 1.0)])


def match_color(
    swapped: np.ndarray,
    reference: np.ndarray,
    mask: np.ndarray,
    strength: float,
    reference_stats: np.ndarray | None = None,
) -> np.ndarray:
    """Move the swapped crop's LAB statistics towards the live crop inside ``mask``.

    ``reference_stats`` (from :func:`color_statistics`, optionally smoothed over
    time) replaces the per-frame measurement so the tone does not flicker.
    """
    import cv2

    weight = float(np.clip(strength, 0.0, 1.0))
    if weight <= 0.0:
        return swapped
    source_stats = color_statistics(swapped, mask)
    if reference_stats is None:
        reference_stats = color_statistics(reference, mask)
    if source_stats is None or reference_stats is None:
        return swapped
    swapped_lab = cv2.cvtColor(swapped, cv2.COLOR_BGR2LAB).astype(np.float32)
    target_mean = source_stats[0] * (1.0 - weight) + reference_stats[0] * weight
    target_std = source_stats[1] * (1.0 - weight) + reference_stats[1] * weight
    matched = (swapped_lab - source_stats[0]) * (target_std / source_stats[1]) + target_mean
    matched = np.clip(matched, 0, 255).astype(np.uint8)
    return cv2.cvtColor(matched, cv2.COLOR_LAB2BGR)


def composite_background(frame_bgr: np.ndarray, alpha: np.ndarray, background_bgr: np.ndarray) -> np.ndarray:
    """Alpha-blend the person over a background of the same size (OpenCV, ~2 ms at 720p)."""
    import cv2

    weight = np.ascontiguousarray(alpha, dtype=np.float32)
    return cv2.blendLinear(frame_bgr, background_bgr, weight, 1.0 - weight)


def blend_identity(source: np.ndarray, target: np.ndarray | None, strength: float) -> np.ndarray:
    """Mix the swapped identity with the live face (1.0 = full source identity)."""
    if target is None or strength >= 1.0:
        return source
    weight = float(np.clip(strength, 0.0, 1.0))
    target = np.asarray(target, dtype=np.float32).reshape(1, -1)
    target = target / max(float(np.linalg.norm(target)), 1e-6)
    return np.ascontiguousarray(source * weight + target * (1.0 - weight), dtype=np.float32)


def average_embedding(embeddings: list[np.ndarray]) -> np.ndarray:
    if not embeddings:
        raise ValueError("no source face embeddings were provided")
    stacked = np.stack([np.asarray(e, dtype=np.float32).ravel() for e in embeddings])
    return stacked.mean(axis=0)


def largest_face(bboxes: np.ndarray, kpss: np.ndarray | None, previous_center: np.ndarray | None = None) -> int | None:
    """Pick the tracked face: nearest to the previous centre, else the largest."""
    if bboxes is None or len(bboxes) == 0 or kpss is None:
        return None
    areas = (bboxes[:, 2] - bboxes[:, 0]) * (bboxes[:, 3] - bboxes[:, 1])
    if previous_center is not None:
        centers = np.stack([(bboxes[:, 0] + bboxes[:, 2]) * 0.5, (bboxes[:, 1] + bboxes[:, 3]) * 0.5], axis=1)
        distances = np.linalg.norm(centers - previous_center, axis=1)
        sizes = np.sqrt(np.maximum(areas, 1.0))
        close = np.where(distances < sizes * 0.75)[0]
        if len(close):
            return int(close[np.argmax(areas[close])])
    return int(np.argmax(areas))


def smooth_landmarks(previous: np.ndarray | None, current: np.ndarray, alpha: float) -> np.ndarray:
    """Exponential smoothing that resets on large jumps (fast head moves)."""
    if previous is None or alpha <= 0.0:
        return current.astype(np.float32)
    jump = float(np.linalg.norm(current - previous, axis=1).max())
    eye_distance = float(np.linalg.norm(current[1] - current[0]))
    if jump > max(eye_distance, 1.0) * 0.5:
        return current.astype(np.float32)
    keep = float(np.clip(alpha, 0.0, 0.95))
    return (previous * keep + current * (1.0 - keep)).astype(np.float32)


def bgr_to_rgba(frame_bgr: np.ndarray) -> np.ndarray:
    rgb = frame_bgr[:, :, ::-1]
    alpha = np.full(rgb.shape[:2] + (1,), 255, dtype=np.uint8)
    return np.ascontiguousarray(np.concatenate((rgb, alpha), axis=2))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Minimal ONNX protobuf reader (the venv pins protobuf 3.19 for audio tools, so
# the ``onnx`` package cannot be imported; only one initializer is needed)
# --------------------------------------------------------------------------- #
_ONNX_DTYPES = {1: np.float32, 6: np.int32, 7: np.int64, 10: np.float16, 11: np.float64}


def _read_varint(buffer: memoryview, position: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        byte = buffer[position]
        position += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, position
        shift += 7
        if shift > 70:
            raise ValueError("malformed varint")


def _iter_fields(buffer: memoryview, start: int, end: int):
    """Yield (field_number, wire_type, payload_start, payload_end) for one message."""
    position = start
    while position < end:
        key, position = _read_varint(buffer, position)
        field, wire = key >> 3, key & 7
        if wire == 0:
            _, next_position = _read_varint(buffer, position)
            yield field, wire, position, next_position
            position = next_position
        elif wire == 1:
            yield field, wire, position, position + 8
            position += 8
        elif wire == 2:
            length, payload = _read_varint(buffer, position)
            yield field, wire, payload, payload + length
            position = payload + length
        elif wire == 5:
            yield field, wire, position, position + 4
            position += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")


def _decode_tensor(buffer: memoryview, start: int, end: int) -> tuple[str, np.ndarray | None]:
    dims: list[int] = []
    data_type = 0
    name = ""
    raw: bytes | None = None
    floats: list[float] = []
    for field, wire, payload_start, payload_end in _iter_fields(buffer, start, end):
        if field == 1 and wire == 0:
            dims.append(_read_varint(buffer, payload_start)[0])
        elif field == 1 and wire == 2:  # packed dims
            position = payload_start
            while position < payload_end:
                value, position = _read_varint(buffer, position)
                dims.append(value)
        elif field == 2 and wire == 0:
            data_type = _read_varint(buffer, payload_start)[0]
        elif field == 8 and wire == 2:
            name = bytes(buffer[payload_start:payload_end]).decode("utf-8", "replace")
        elif field == 9 and wire == 2:
            raw = bytes(buffer[payload_start:payload_end])
        elif field == 4 and wire == 2:
            floats.extend(np.frombuffer(bytes(buffer[payload_start:payload_end]), dtype="<f4").tolist())
        elif field == 4 and wire == 5:
            floats.append(float(np.frombuffer(bytes(buffer[payload_start:payload_end]), dtype="<f4")[0]))
    if raw is not None:
        dtype = _ONNX_DTYPES.get(data_type)
        if dtype is None:
            return name, None
        return name, np.frombuffer(raw, dtype=np.dtype(dtype).newbyteorder("<")).reshape(dims)
    if floats:
        return name, np.asarray(floats, dtype=np.float32).reshape(dims)
    return name, None


def read_onnx_initializer(path: Path, wanted: str, fallback_shape: tuple[int, ...] | None = None) -> np.ndarray:
    """Return one named initializer of an ONNX file without importing ``onnx``.

    InsightFace and FaceFusion read the identity map as the *last* initializer of
    ``inswapper_128.onnx`` (the re-exported file names it ``initializer``), so an
    optional ``fallback_shape`` selects the last initializer of that shape when
    ``wanted`` is absent.
    """
    import mmap

    fallback: np.ndarray | None = None
    with path.open("rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            buffer = memoryview(mapped)
            try:
                for field, wire, graph_start, graph_end in _iter_fields(buffer, 0, len(buffer)):
                    if field != 7 or wire != 2:  # ModelProto.graph
                        continue
                    for graph_field, graph_wire, tensor_start, tensor_end in _iter_fields(buffer, graph_start, graph_end):
                        if graph_field != 5 or graph_wire != 2:  # GraphProto.initializer
                            continue
                        name, tensor = _decode_tensor(buffer, tensor_start, tensor_end)
                        if name == wanted:
                            if tensor is None:
                                raise RuntimeError(f"initializer {wanted!r} has an unsupported data type")
                            return np.ascontiguousarray(tensor.astype(np.float32))
                        if fallback_shape is not None and tensor is not None and tuple(tensor.shape) == tuple(fallback_shape):
                            fallback = np.ascontiguousarray(tensor.astype(np.float32))
            finally:
                buffer.release()
    if fallback is not None:
        return fallback
    raise RuntimeError(f"{path.name} has no {wanted!r} initializer")


# --------------------------------------------------------------------------- #
# Model discovery
# --------------------------------------------------------------------------- #
def models_root() -> Path:
    import folder_paths

    return Path(folder_paths.models_dir).resolve()


def available_dfm_models(root: Path | None = None) -> list[str]:
    root = models_root() if root is None else root
    folder = root / DFM_SUBDIR
    if not folder.is_dir():
        return []
    return [DFM_PREFIX + path.stem for path in sorted(folder.glob("*.dfm"))]


def dfm_spec(name: str) -> SwapperSpec:
    """Spec for a ``dfm/<stem>`` model; the crop size is read from the session."""
    stem = name[len(DFM_PREFIX):] if name.startswith(DFM_PREFIX) else name
    return SwapperSpec(stem + ".dfm", "dfm", "dfl_whole_face", 0, 0.0, 1.0, "DeepFaceLab model licence (see model author)", "", source_kind="none")


def resolve_swapper(name: str) -> SwapperSpec:
    if name.startswith(DFM_PREFIX):
        return dfm_spec(name)
    return SWAPPERS[name]


def available_swappers(root: Path | None = None) -> list[str]:
    root = models_root() if root is None else root
    names = [name for name, spec in SWAPPERS.items() if (root / SWAPPER_SUBDIR / spec.file_name).is_file()]
    return names + available_dfm_models(root)


def available_enhancers(root: Path | None = None) -> list[str]:
    root = models_root() if root is None else root
    return [name for name, spec in ENHANCERS.items() if (root / ENHANCER_SUBDIR / spec.file_name).is_file()]


def available_mask_models(specs: dict[str, MaskModelSpec], subdir: str, root: Path | None = None) -> list[str]:
    root = models_root() if root is None else root
    return [name for name, spec in specs.items() if (root / subdir / spec.file_name).is_file()]


def detector_ready(root: Path | None = None) -> bool:
    root = models_root() if root is None else root
    pack = root / SWAPPER_SUBDIR / "models" / DETECTOR_PACK
    return all((pack / name).is_file() for name in DETECTOR_FILES)


def directml_providers(device_id: int) -> tuple[list[str], list[dict[str, Any]]]:
    return ["DmlExecutionProvider", "CPUExecutionProvider"], [{"device_id": int(device_id)}, {}]


# --------------------------------------------------------------------------- #
# SCRFD detector and ArcFace embedder (ported from InsightFace, MIT licence)
# --------------------------------------------------------------------------- #
ARCFACE_112_TEMPLATE = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)


def distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def distance2kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    preds = []
    for i in range(0, distance.shape[1], 2):
        preds.append(points[:, i % 2] + distance[:, i])
        preds.append(points[:, i % 2 + 1] + distance[:, i + 1])
    return np.stack(preds, axis=-1)


def nms(dets: np.ndarray, threshold: float) -> list[int]:
    x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
        overlap = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(overlap <= threshold)[0] + 1]
    return keep


class ScrfdDetector:
    """SCRFD face detector with five landmarks (``det_10g.onnx``)."""

    def __init__(self, session: Any, det_size: int, threshold: float, nms_threshold: float = 0.4) -> None:
        self.session = session
        self.det_size = int(det_size)
        self.threshold = float(threshold)
        self.nms_threshold = float(nms_threshold)
        self.input_name = session.get_inputs()[0].name
        self.output_names = [item.name for item in session.get_outputs()]
        count = len(self.output_names)
        if count == 9:
            self.strides, self.num_anchors, self.fmc = [8, 16, 32], 2, 3
        elif count == 15:
            self.strides, self.num_anchors, self.fmc = [8, 16, 32, 64, 128], 1, 5
        else:
            raise RuntimeError(f"unsupported SCRFD output layout ({count} outputs)")
        self._centers: dict[tuple[int, int, int], np.ndarray] = {}

    def _anchor_centers(self, height: int, width: int, stride: int) -> np.ndarray:
        key = (height, width, stride)
        centers = self._centers.get(key)
        if centers is None:
            centers = np.stack(np.mgrid[:height, :width][::-1], axis=-1).astype(np.float32)
            centers = (centers * stride).reshape((-1, 2))
            if self.num_anchors > 1:
                centers = np.stack([centers] * self.num_anchors, axis=1).reshape((-1, 2))
            self._centers[key] = centers
        return centers

    def detect(self, frame_bgr: np.ndarray, max_num: int = 0, metric: str = "default") -> tuple[np.ndarray, np.ndarray]:
        import cv2

        height, width = frame_bgr.shape[:2]
        scale = min(self.det_size / float(width), self.det_size / float(height))
        new_w, new_h = max(1, int(width * scale)), max(1, int(height * scale))
        resized = cv2.resize(frame_bgr, (new_w, new_h))
        canvas = np.zeros((self.det_size, self.det_size, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized
        blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128.0, (self.det_size, self.det_size), (127.5, 127.5, 127.5), swapRB=True)
        outputs = self.session.run(self.output_names, {self.input_name: blob})
        scores_list, boxes_list, kps_list = [], [], []
        for index, stride in enumerate(self.strides):
            scores = outputs[index].reshape(-1)
            box_preds = outputs[index + self.fmc].reshape(-1, 4) * stride
            kps_preds = outputs[index + self.fmc * 2].reshape(-1, 10) * stride
            centers = self._anchor_centers(self.det_size // stride, self.det_size // stride, stride)
            positive = np.where(scores >= self.threshold)[0]
            if positive.size == 0:
                continue
            scores_list.append(scores[positive])
            boxes_list.append(distance2bbox(centers, box_preds)[positive])
            kps_list.append(distance2kps(centers, kps_preds)[positive].reshape(-1, 5, 2))
        if not scores_list:
            return np.empty((0, 5), dtype=np.float32), np.empty((0, 5, 2), dtype=np.float32)
        scores = np.concatenate(scores_list)
        boxes = np.concatenate(boxes_list) / scale
        kpss = np.concatenate(kps_list) / scale
        order = scores.argsort()[::-1]
        dets = np.hstack((boxes, scores[:, None])).astype(np.float32)[order]
        kpss = kpss[order]
        keep = nms(dets, self.nms_threshold)
        dets, kpss = dets[keep], kpss[keep]
        if max_num > 0 and dets.shape[0] > max_num:
            dets, kpss = dets[:max_num], kpss[:max_num]
        return dets, kpss.astype(np.float32)


class ArcFaceEmbedder:
    """ArcFace recognition (``w600k_r50.onnx``) on an aligned 112x112 crop."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.output_name = session.get_outputs()[0].name
        shape = session.get_inputs()[0].shape
        self.size = int(shape[2]) if isinstance(shape[2], int) else 112

    def align(self, frame_bgr: np.ndarray, landmarks_5: np.ndarray) -> np.ndarray:
        import cv2

        ratio = self.size / 112.0
        target = ARCFACE_112_TEMPLATE * ratio
        matrix = cv2.estimateAffinePartial2D(landmarks_5.astype(np.float32), target, method=cv2.LMEDS)[0]
        if matrix is None:
            raise ValueError("could not align the face for ArcFace")
        return cv2.warpAffine(frame_bgr, matrix, (self.size, self.size), borderValue=0.0)

    def embed(self, frame_bgr: np.ndarray, landmarks_5: np.ndarray) -> np.ndarray:
        import cv2

        aligned = self.align(frame_bgr, landmarks_5)
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 127.5, (self.size, self.size), (127.5, 127.5, 127.5), swapRB=True)
        return self.session.run([self.output_name], {self.input_name: blob})[0].reshape(-1).astype(np.float32)


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
@dataclass
class FaceIdentity:
    embedding: np.ndarray
    source_count: int
    fingerprint: str
    source_crop: np.ndarray | None = None  # aligned ffhq_512/256 crop for image-conditioned swappers


@dataclass
class SwapTimings:
    detect_ms: float = 0.0
    swap_ms: float = 0.0
    mask_ms: float = 0.0
    enhance_ms: float = 0.0
    matte_ms: float = 0.0
    total_ms: float = 0.0
    face_found: bool = False


@dataclass
class MaskBranch:
    """Everything the mask worker computes for one frame (runs beside the swapper)."""

    classes: np.ndarray | None = None
    beard: np.ndarray | None = None
    cheek: np.ndarray | None = None
    occlusion: np.ndarray | None = None
    alpha: np.ndarray | None = None
    skin: np.ndarray | None = None
    ms: float = 0.0
    parse_ms: float = 0.0
    occlusion_ms: float = 0.0
    matte_ms: float = 0.0


class FaceSwapEngine:
    """Owns the DirectML sessions; call from one thread at a time."""

    def __init__(
        self,
        root: Path,
        swapper: str,
        enhancer: str | None,
        dml_device_id: int,
        det_size: int,
        det_threshold: float = 0.5,
        session_factory: Any = None,
        detector_factory: Any = None,
        embedder_factory: Any = None,
        occluder: str | None = None,
        parser: str | None = None,
        matter: str | None = None,
        mask_device_id: int | None = None,
        parallel_masks: bool = True,
    ) -> None:
        self.root = Path(root)
        self.is_dfm = swapper.startswith(DFM_PREFIX)
        self.mask_device_id = int(dml_device_id if mask_device_id is None else mask_device_id)
        # DirectML sessions of two threads must not share one adapter (ORT raises
        # opaque device errors), so the worker only exists on a second adapter.
        self.parallel_masks = bool(parallel_masks) and self.mask_device_id != int(dml_device_id)
        self._pool: ThreadPoolExecutor | None = None
        self._previous_branch: MaskBranch | None = None
        self.last_alpha: np.ndarray | None = None
        self._previous_mask: np.ndarray | None = None
        self._previous_swapped: np.ndarray | None = None
        self._previous_stats: np.ndarray | None = None
        self._live_embedding: np.ndarray | None = None
        self._live_embedding_age = 0
        self._last_jump = 0.0
        self.swapper_name = swapper
        self.spec = resolve_swapper(swapper)
        self.enhancer_name = enhancer if enhancer and enhancer != "none" else None
        self.enhancer_spec = ENHANCERS[self.enhancer_name] if self.enhancer_name else None
        self.occluder_name = occluder if occluder and occluder != "none" else None
        self.occluder_spec = OCCLUDERS[self.occluder_name] if self.occluder_name else None
        self.parser_name = parser if parser and parser != "none" else None
        self.parser_spec = PARSERS[self.parser_name] if self.parser_name else None
        self.matter_name = matter if matter and matter != "none" else None
        self.matter_spec = MATTERS[self.matter_name] if self.matter_name else None
        self.occluder: Any = None
        self.parser: Any = None
        self.matter: Any = None
        self._matter_input = ""
        self.dml_device_id = int(dml_device_id)
        self.det_size = int(det_size)
        self.det_threshold = float(det_threshold)
        self.lock = threading.Lock()
        self._session_factory = session_factory or self._create_session
        self._custom_session_factory = session_factory is not None
        self._detector_factory = detector_factory or self._create_detector
        self._embedder_factory = embedder_factory or self._create_embedder
        self.detector: Any = None
        self.embedder: Any = None
        self.swapper: Any = None
        self.enhancer: Any = None
        self.emap: np.ndarray | None = None
        self._swapper_inputs: dict[str, str] = {}
        self._enhancer_inputs: dict[str, str] = {}
        self._previous_center: np.ndarray | None = None
        self._previous_landmarks: np.ndarray | None = None
        self._frame_index = 0

    # -- loading ------------------------------------------------------------
    def _create_session(self, path: Path, fixed_dims: int | None = None, device_id: int | None = None) -> Any:
        import onnxruntime

        providers, options = directml_providers(self.dml_device_id if device_id is None else device_id)
        available = onnxruntime.get_available_providers()
        if "DmlExecutionProvider" not in available:
            raise RuntimeError(
                "onnxruntime has no DmlExecutionProvider; install onnxruntime-directml last "
                f"(available: {available})"
            )
        session_options = onnxruntime.SessionOptions()
        session_options.log_severity_level = 3
        if fixed_dims is not None:
            # DirectML rejects SCRFD's dynamic Reshape at 320 px unless the free
            # image dimensions are pinned; the pinned graph is also ~3x faster.
            probe = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            for dim in probe.get_inputs()[0].shape:
                if isinstance(dim, str):
                    session_options.add_free_dimension_override_by_name(dim, int(fixed_dims))
            del probe
        return onnxruntime.InferenceSession(str(path), sess_options=session_options, providers=providers, provider_options=options)

    def _detector_pack(self) -> Path:
        return self.root / SWAPPER_SUBDIR / "models" / DETECTOR_PACK

    def _create_detector(self) -> Any:
        path = self._detector_pack() / "det_10g.onnx"
        if self._custom_session_factory:
            session = self._session_factory(path)
        else:
            session = self._create_session(path, fixed_dims=self.det_size)
        return ScrfdDetector(session, self.det_size, self.det_threshold)

    def _create_embedder(self) -> Any:
        return ArcFaceEmbedder(self._session_factory(self._detector_pack() / "w600k_r50.onnx"))

    def load(self) -> "FaceSwapEngine":
        if self.detector is not None:
            return self
        if not detector_ready(self.root):
            raise RuntimeError(f"InsightFace {DETECTOR_PACK} is missing under {self._detector_pack()}")
        swapper_path = self.root / (DFM_SUBDIR if self.is_dfm else SWAPPER_SUBDIR) / self.spec.file_name
        if not swapper_path.is_file():
            raise RuntimeError(f"swapper model is missing: {swapper_path}")
        self.detector = self._detector_factory()
        self.embedder = self._embedder_factory()
        self.swapper = self._session_factory(swapper_path)
        if self.is_dfm:
            shape = self.swapper.get_inputs()[0].shape
            size = int(shape[1]) if isinstance(shape[1], int) else 224
            self.spec = SwapperSpec(self.spec.file_name, "dfm", "dfl_whole_face", size, 0.0, 1.0, self.spec.licence, "", source_kind="none")
            names = [item.name for item in self.swapper.get_inputs()]
            self._swapper_inputs = {"target": names[0], "morph": next((n for n in names if "morph" in n), "")}
        else:
            self._swapper_inputs = self._map_inputs(self.swapper)
        if self.spec.kind == "inswapper":
            self.emap = self._load_emap(swapper_path)
        if self.enhancer_spec is not None:
            enhancer_path = self.root / ENHANCER_SUBDIR / self.enhancer_spec.file_name
            if not enhancer_path.is_file():
                raise RuntimeError(f"enhancer model is missing: {enhancer_path}")
            self.enhancer = self._session_factory(enhancer_path)
            self._enhancer_inputs = self._map_inputs(self.enhancer)
        if self.occluder_spec is not None:  # runs on the swapper thread/adapter, beside the swap
            self.occluder = self._session_factory(self._require(self.root / MASK_SUBDIR / self.occluder_spec.file_name, "occluder"))
        if self.parser_spec is not None:
            self.parser = self._mask_session(self._require(self.root / MASK_SUBDIR / self.parser_spec.file_name, "face parser"))
        if self.matter_spec is not None:
            self.matter = self._mask_session(self._require(self.root / MATTING_SUBDIR / self.matter_spec.file_name, "matting"))
            self._matter_input = self.matter.get_inputs()[0].name
        if self.parallel_masks and self._pool is None and (self.parser is not None or self.matter is not None):
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="DaWastehFaceSwapMasks")
        return self

    def _mask_session(self, path: Path) -> Any:
        """Occluder/parser/matting sessions live on ``mask_device_id`` (default: the other GPU)."""
        if self._custom_session_factory:
            return self._session_factory(path)
        return self._create_session(path, device_id=self.mask_device_id)

    @staticmethod
    def _require(path: Path, label: str) -> Path:
        if not path.is_file():
            raise RuntimeError(f"{label} model is missing: {path}")
        return path

    @staticmethod
    def _map_inputs(session: Any) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for item in session.get_inputs():
            name = item.name
            lowered = name.lower()
            if "source" in lowered or "embed" in lowered or "latent" in lowered:
                mapping["source"] = name
            elif "weight" in lowered:
                mapping["weight"] = name
            elif "target" in lowered or "input" in lowered or "image" in lowered:
                mapping["target"] = name
        if "target" not in mapping:
            inputs = [item.name for item in session.get_inputs()]
            raise RuntimeError(f"could not identify the image input of the ONNX model: {inputs}")
        return mapping

    @staticmethod
    def _load_emap(path: Path) -> np.ndarray:
        cache = path.with_suffix(".emap.npy")
        if cache.is_file():
            emap = np.load(cache)
            if emap.shape == (512, 512):
                return emap.astype(np.float32)
        emap = read_onnx_initializer(path, "emap", fallback_shape=(512, 512))
        if emap.shape != (512, 512):
            raise RuntimeError(f"{path.name}: unexpected emap shape {emap.shape}")
        try:
            np.save(cache, emap)
        except OSError:
            LOGGER.warning("could not cache emap next to %s", path)
        return emap

    # -- identity -----------------------------------------------------------
    def identity_from_images(self, images_bgr: list[np.ndarray]) -> FaceIdentity:
        self.load()
        embeddings: list[np.ndarray] = []
        source_crop: np.ndarray | None = None
        for image in images_bgr:
            bboxes, kpss = self.detector.detect(image)
            index = largest_face(bboxes, kpss, None)
            if index is None:
                continue
            landmarks = np.asarray(kpss[index], dtype=np.float32)
            embeddings.append(self.embedder.embed(image, landmarks))
            if source_crop is None and self.spec.source_kind == "image":
                source_crop, _ = warp_face(image, landmarks, self.spec.template, self.spec.size)
        if not embeddings:
            raise RuntimeError("no face was detected in the source image(s)")
        raw = average_embedding(embeddings)
        prepared = source_embedding_for(self.spec, raw, self.emap) if not self.is_dfm else np.asarray(raw, dtype=np.float32).reshape(1, -1)
        fingerprint = hashlib.sha256(prepared.tobytes()).hexdigest()[:16]
        return FaceIdentity(prepared, len(embeddings), fingerprint, source_crop)

    # -- per frame ----------------------------------------------------------
    def reset_tracking(self) -> None:
        self._previous_center = None
        self._previous_landmarks = None
        self._previous_branch = None
        self.last_alpha = None
        self._previous_mask = None
        self._previous_swapped = None
        self._previous_stats = None
        self._live_embedding = None
        self._live_embedding_age = 0
        self._last_jump = 0.0
        self._frame_index = 0

    def detect_face(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        """Tracked five-point landmarks of the main face (raw, unsmoothed) or None."""
        self.load()
        bboxes, kpss = self.detector.detect(frame_bgr)
        index = largest_face(bboxes, kpss, self._previous_center)
        if index is None:
            return None
        bbox = bboxes[index]
        self._previous_center = np.array([(bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5], dtype=np.float32)
        return np.asarray(kpss[index], dtype=np.float32)

    def _mask_branch(self, frame_bgr: np.ndarray | None, crop: np.ndarray | None, template_points: np.ndarray | None,
                     regions: tuple[str, ...], shave: str, shave_extent: float, matte: bool,
                     reuse: MaskBranch | None = None) -> MaskBranch:
        """Parser and matting for one frame; safe to run in the worker thread."""
        started = time.perf_counter()
        branch = MaskBranch()
        if crop is not None and template_points is not None:
            size = crop.shape[0]
            if reuse is not None and reuse.classes is not None:
                branch.classes, branch.beard, branch.cheek, branch.skin = reuse.classes, reuse.beard, reuse.cheek, reuse.skin
            elif self.parser is not None and (regions or shave != "none") and not self.is_dfm:
                stage = time.perf_counter()
                branch.classes = self._parse_crop(crop)
                if shave != "none":
                    branch.beard = beard_mask_from_classes(branch.classes, template_points, size, crop, shave_extent)
                    if shave_extent >= 0.9:
                        branch.beard = np.maximum(branch.beard, moustache_band(branch.classes))
                    branch.cheek = cheek_color(crop, branch.classes, template_points, size)
                    branch.skin = (branch.classes == FACE_REGIONS["skin"]).astype(np.float32)
                branch.parse_ms = (time.perf_counter() - stage) * 1000.0
        if matte and self.matter is not None and frame_bgr is not None:
            stage = time.perf_counter()
            branch.alpha = self.matte(frame_bgr)
            branch.matte_ms = (time.perf_counter() - stage) * 1000.0
        branch.ms = (time.perf_counter() - started) * 1000.0
        return branch

    def swap_frame(
        self,
        frame_bgr: np.ndarray,
        identity: FaceIdentity,
        *,
        mask_blur: float = 0.3,
        mask_padding: tuple[int, int, int, int] = (0, 0, 0, 0),
        landmark_smoothing: float = 0.5,
        enhancer_blend: float = 0.8,
        enhancer_every: int = 1,
        crop_scale: float = 1.0,
        color_match: float = 0.0,
        regions: tuple[str, ...] = DEFAULT_REGIONS,
        shave: str = "none",
        shave_extent: float = 1.0,
        matte: bool = False,
        parser_every: int = 1,
        identity_strength: float = 0.0,
        temporal_smoothing: float = 0.0,
        mask_feather: float = 0.0,
        glasses: str = "swap",
        landmarks: np.ndarray | None = None,
        timings: SwapTimings | None = None,
    ) -> np.ndarray:
        """Return a swapped BGR frame; the untouched frame when no face is present.

        ``identity_strength`` extrapolates the source identity away from the live
        face (needs the live ArcFace embedding, refreshed every 10 frames);
        ``temporal_smoothing`` blends mask, swapped crop and colour statistics
        with the previous frame in crop space (reset on fast head moves);
        ``mask_feather`` is an extra Gaussian sigma (px of the crop) on the final
        mask; ``glasses`` "swap" renders the swapper's glasses, "keep" leaves the
        real glasses (parser region) untouched, "remove" inpaints the frame lines
        before the swap and lets only the real frames through.
        ``landmarks`` (5×2) skips detection, e.g. from a look-ahead buffer.

        ``parser_every`` > 1 reuses the previous frame's class map (crop space is
        face-aligned, so the regions barely move) and only re-parses every n-th
        frame; the matte is still computed for every frame.

        With ``matte`` the person alpha of this frame is left in ``last_alpha``
        (computed on the mask worker while the swapper runs).
        """
        self.load()
        timings = timings if timings is not None else SwapTimings()
        started = time.perf_counter()
        if landmarks is None:
            bboxes, kpss = self.detector.detect(frame_bgr)
            index = largest_face(bboxes, kpss, self._previous_center)
            if index is not None:
                bbox = bboxes[index]
                self._previous_center = np.array([(bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5], dtype=np.float32)
                landmarks = np.asarray(kpss[index], dtype=np.float32)
        timings.detect_ms = (time.perf_counter() - started) * 1000.0
        if landmarks is None:
            self._previous_center = None
            self._previous_landmarks = None
            self._previous_mask = None
            self._previous_swapped = None
            timings.face_found = False
            if matte and self.matter is not None:
                matte_started = time.perf_counter()
                self.last_alpha = self.matte(frame_bgr)
                timings.matte_ms = (time.perf_counter() - matte_started) * 1000.0
            else:
                self.last_alpha = None
            timings.total_ms = (time.perf_counter() - started) * 1000.0
            return frame_bgr
        raw_landmarks = np.asarray(landmarks, dtype=np.float32)
        if self._previous_landmarks is not None:
            self._last_jump = float(np.linalg.norm(raw_landmarks - self._previous_landmarks, axis=1).max()) / max(float(np.linalg.norm(raw_landmarks[1] - raw_landmarks[0])), 1.0)
        else:
            self._last_jump = 1.0
        landmarks = smooth_landmarks(self._previous_landmarks, raw_landmarks, landmark_smoothing)
        self._previous_landmarks = landmarks
        timings.face_found = True
        # temporal blends only while the head moves slowly (crops stay aligned)
        temporal = float(temporal_smoothing) if self._last_jump < 0.08 else 0.0

        if self.is_dfm:
            crop_scale = 1.0  # DeepFaceLive models are trained on the exact whole-face crop
        crop, matrix = warp_face(frame_bgr, landmarks, self.spec.template, self.spec.size, crop_scale)
        template_points = scaled_template(self.spec.template, crop_scale) * self.spec.size
        want_masks = (self.parser is not None and not self.is_dfm) or (matte and self.matter is not None)
        future: Future | None = None
        branch: MaskBranch | None = None
        reuse = self._previous_branch if (parser_every > 1 and self._frame_index % int(parser_every) != 0) else None
        if want_masks:
            if self._pool is not None:
                future = self._pool.submit(self._mask_branch, frame_bgr, crop, template_points, regions, shave, shave_extent, matte, reuse)
            else:
                branch = self._mask_branch(frame_bgr, crop, template_points, regions, shave, shave_extent, matte, reuse)

        # Shave with the previous frame's beard zone so the parser is off the
        # critical path (crop space is face-aligned, the zone barely moves).
        swap_started = time.perf_counter()
        swap_input = crop
        if shave != "none" and self.parser is not None and not self.is_dfm:
            shave_branch = branch or self._previous_branch
            if shave_branch is None and future is not None:
                branch = future.result()
                future = None
                shave_branch = branch
            if shave_branch is not None and shave_branch.beard is not None:
                swap_input = shave_crop(crop, shave_branch.beard, shave, shave_branch.cheek, shave_branch.skin)
        occlusion = self._occlusion_mask(crop) if self.occluder is not None else None
        frames_mask: np.ndarray | None = None
        if glasses == "remove" and occlusion is not None:
            frames_mask = glasses_frame_mask(occlusion, template_points, self.spec.size)
            swap_input = remove_glasses_frames(swap_input, frames_mask)
        source_embedding = identity.embedding
        if identity_strength > 0.0 and self.spec.source_kind == "embedding" and self.embedder is not None and not self.is_dfm:
            if self._live_embedding is None or self._live_embedding_age >= 10:
                self._live_embedding = self.embedder.embed(frame_bgr, landmarks)
                self._live_embedding_age = 0
            self._live_embedding_age += 1
            source_embedding = boost_identity(identity.embedding, self._live_embedding, identity_strength)
        model_mask: np.ndarray | None = None
        if self.is_dfm:
            feeds = {self._swapper_inputs["target"]: prepare_dfm_input(swap_input)}
            if self._swapper_inputs.get("morph"):
                feeds[self._swapper_inputs["morph"]] = np.array([1.0], dtype=np.float32)
            target_mask, face, source_mask = self.swapper.run(None, feeds)
            swapped_crop = np.clip(face[0] * 255.0, 0, 255).astype(np.uint8)
            if color_match > 0.0:
                # only the coarse (16 px) colour field: FaceFusion's full multi-scale
                # transfer copies beard and glasses shading back onto the new face
                swapped_crop = equalize_frame_color(crop, swapped_crop, 16)
            model_mask = dfm_mask(source_mask[0], target_mask[0], self.spec.size)
        else:
            feeds = {self._swapper_inputs["target"]: prepare_swapper_input(swap_input, self.spec)}
            if "source" in self._swapper_inputs:
                if self.spec.source_kind == "image":
                    if identity.source_crop is None:
                        raise RuntimeError(f"{self.swapper_name} needs an identity extracted with the same swapper (source crop missing)")
                    feeds[self._swapper_inputs["source"]] = prepare_source_image(identity.source_crop)
                else:
                    feeds[self._swapper_inputs["source"]] = source_embedding
            output = self.swapper.run(None, feeds)[0][0]
            swapped_crop = normalize_swapper_output(output, self.spec)
            if swap_input is not crop and self._previous_branch is not None and self._previous_branch.beard is not None:
                swapped_crop = fix_zone_color(swapped_crop, swap_input, self._previous_branch.beard)
        swapped_crop = temporal_blend(self._previous_swapped, swapped_crop, temporal)
        self._previous_swapped = swapped_crop
        timings.swap_ms = (time.perf_counter() - swap_started) * 1000.0

        mask_started = time.perf_counter()
        if future is not None:
            branch = future.result()
        if branch is not None:
            self._previous_branch = branch
            self.last_alpha = branch.alpha
        else:
            self.last_alpha = None
        classes = branch.classes if branch is not None else None
        beard = branch.beard if branch is not None else None
        # With a parser the region mask already fades skin/hair/neck edges, so the
        # box fade only has to hide the crop border (the chin sits close to it).
        box_blur = mask_blur * 0.5 if classes is not None else mask_blur
        masks = [create_box_mask(self.spec.size, box_blur, mask_padding)]
        if model_mask is not None:
            masks.append(model_mask)
        if occlusion is not None:
            if beard is not None:
                occlusion = extend_occlusion_downward(occlusion, beard, self.spec.size)
            masks.append(occlusion)
        if classes is not None and regions and not self.is_dfm:
            paste_regions = tuple(name for name in regions if not (glasses == "keep" and name == "glasses")) if glasses == "keep" else regions
            masks.append(region_mask_from_classes(classes, paste_regions, self.spec.size, beard))
        mask = np.minimum.reduce(masks).clip(0.0, 1.0) if len(masks) > 1 else masks[0]
        if mask_feather > 0.0:
            mask = feather_mask(mask, mask_feather)
        mask = temporal_blend(self._previous_mask, mask, temporal)
        self._previous_mask = mask
        if color_match > 0.0:
            stats = color_statistics(swap_input, mask)
            if stats is not None and self._previous_stats is not None and temporal > 0.0:
                stats = self._previous_stats * temporal + stats * (1.0 - temporal)
            self._previous_stats = stats
            swapped_crop = match_color(swapped_crop, swap_input, mask, color_match, stats)
        result = paste_back(frame_bgr, swapped_crop, mask, matrix)
        timings.mask_ms = (time.perf_counter() - mask_started) * 1000.0 + (branch.ms if branch is not None else 0.0)
        timings.matte_ms = 0.0

        self._frame_index += 1
        if self.enhancer is not None and enhancer_blend > 0.0 and (self._frame_index % max(1, int(enhancer_every))) == 0:
            enhance_started = time.perf_counter()
            result = self._enhance(result, landmarks, enhancer_blend, mask_blur)
            timings.enhance_ms = (time.perf_counter() - enhance_started) * 1000.0
        timings.total_ms = (time.perf_counter() - started) * 1000.0
        return result

    def _occlusion_mask(self, crop_bgr: np.ndarray) -> np.ndarray:
        import cv2

        spec = self.occluder_spec
        assert spec is not None
        feed = {self.occluder.get_inputs()[0].name: prepare_occluder_input(crop_bgr, spec.size)}
        raw = self.occluder.run(None, feed)[0][0]
        mask = np.clip(np.squeeze(raw), 0.0, 1.0).astype(np.float32)
        if mask.shape[0] != crop_bgr.shape[0]:
            mask = cv2.resize(mask, crop_bgr.shape[:2][::-1])
        return sharpen_mask(mask)

    def _parse_crop(self, crop_bgr: np.ndarray) -> np.ndarray:
        """CelebAMask-HQ class map of the crop at half parser resolution (fast argmax)."""
        spec = self.parser_spec
        assert spec is not None
        feed = {self.parser.get_inputs()[0].name: prepare_parser_input(crop_bgr, spec.size)}
        logits = self.parser.run([self.parser.get_outputs()[0].name], feed)[0][0]
        step = max(1, spec.size // max(crop_bgr.shape[0], 1))
        return logits[:, ::step, ::step].argmax(0).astype(np.int16)

    def matte(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Person alpha (H x W float32 0..1) from the matting model; 1 = person."""
        import cv2

        if self.matter is None:
            raise RuntimeError("no matting model is loaded")
        spec = self.matter_spec
        assert spec is not None
        raw = self.matter.run(None, {self._matter_input: prepare_matting_input(frame_bgr, spec.size)})[0]
        alpha = np.clip(np.squeeze(raw), 0.0, 1.0).astype(np.float32)
        return cv2.resize(alpha, frame_bgr.shape[:2][::-1], interpolation=cv2.INTER_LINEAR)

    def _enhance(self, frame_bgr: np.ndarray, landmarks: np.ndarray, blend: float, mask_blur: float) -> np.ndarray:
        spec = self.enhancer_spec
        assert spec is not None
        crop, matrix = warp_face(frame_bgr, landmarks, spec.template, spec.size)
        feeds = {self._enhancer_inputs["target"]: prepare_enhancer_input(crop)}
        if "weight" in self._enhancer_inputs:
            feeds[self._enhancer_inputs["weight"]] = np.array([1.0], dtype=np.float64)
        output = self.enhancer.run(None, feeds)[0][0]
        enhanced_crop = normalize_enhancer_output(output)
        weight = float(np.clip(blend, 0.0, 1.0))
        if weight < 1.0:  # blend inside the crop, not over the whole frame
            enhanced_crop = np.clip(crop.astype(np.float32) * (1.0 - weight) + enhanced_crop.astype(np.float32) * weight, 0, 255).astype(np.uint8)
        mask = create_box_mask(spec.size, mask_blur, (0, 0, 0, 0))
        return paste_back(frame_bgr, enhanced_crop, mask, matrix)


_ENGINES: dict[tuple[Any, ...], FaceSwapEngine] = {}
_ENGINES_LOCK = threading.Lock()


def shared_engine(
    root: Path,
    swapper: str,
    enhancer: str | None,
    dml_device_id: int,
    det_size: int,
    occluder: str | None = None,
    parser: str | None = None,
    matter: str | None = None,
    mask_device_id: int | None = None,
) -> FaceSwapEngine:
    mask_device = int(dml_device_id if mask_device_id is None else mask_device_id)
    key = (str(root), swapper, enhancer or "none", int(dml_device_id), int(det_size), occluder or "none", parser or "none", matter or "none", mask_device)
    with _ENGINES_LOCK:
        engine = _ENGINES.get(key)
        if engine is None:
            engine = FaceSwapEngine(root, swapper, enhancer, dml_device_id, det_size, occluder=occluder, parser=parser, matter=matter, mask_device_id=mask_device)
            _ENGINES[key] = engine
    return engine


# --------------------------------------------------------------------------- #
# ComfyUI tensor helpers
# --------------------------------------------------------------------------- #
def image_tensor_to_bgr_list(image: Any) -> list[np.ndarray]:
    array = image.detach().cpu().numpy() if hasattr(image, "detach") else np.asarray(image)
    if array.ndim == 3:
        array = array[None]
    frames = []
    for item in array:
        rgb = np.clip(item[..., :3] * 255.0, 0, 255).astype(np.uint8)
        frames.append(np.ascontiguousarray(rgb[:, :, ::-1]))
    return frames


def bgr_list_to_image_tensor(frames: list[np.ndarray]) -> Any:
    import torch

    stacked = np.stack([frame[:, :, ::-1].astype(np.float32) / 255.0 for frame in frames])
    return torch.from_numpy(np.ascontiguousarray(stacked))


def _live_nodes() -> Any:
    """Reuse the Spout/camera workers of nodes.py in both package and test loading."""
    try:
        from . import nodes  # type: ignore[import-not-found]

        return nodes
    except ImportError:
        pass
    existing = sys.modules.get("live_avatar_nodes")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location("live_avatar_nodes", Path(__file__).with_name("nodes.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
SHAVE_MODES = ["none", "skin", "inpaint"]
BACKGROUND_MODES = ["off", "image", "green", "blur"]
GLASSES_MODES = ["swap", "keep", "remove"]
SWAP_TUNING_INPUTS = {
    "mask_blur": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05}),
    "crop_scale": ("FLOAT", {"default": 0.8, "min": 0.6, "max": 1.2, "step": 0.05, "tooltip": "<1 widens the aligned crop so chin, beard and jaw are regenerated (0.8 measured best)"}),
    "color_match": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "LAB colour transfer from the live face to the swapped face"}),
    "keep_mouth": ("BOOLEAN", {"default": True, "tooltip": "keep the real mouth interior (teeth, tongue) - Deep-Live-Cam style mouth mask"}),
    "shave": (SHAVE_MODES, {"default": "skin", "tooltip": "smooth the beard area before swapping so the swapper renders bare skin"}),
    "shave_extent": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "1 = moustache and chin, 0.6 = chin only"}),
    "enhancer_blend": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
    "identity_strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "push the source identity away from your own face (FaceFusion swapper weight); 0 = plain embedding"}),
    "temporal_smoothing": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 0.8, "step": 0.05, "tooltip": "blend mask, swapped face and colour statistics with the previous frame while the head moves slowly"}),
    "mask_feather": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 12.0, "step": 0.5, "tooltip": "extra Gaussian sigma (crop pixels) on the final mask edge"}),
    "glasses": (GLASSES_MODES, {"default": "swap", "tooltip": "swap: swapper renders the glasses; keep: your real glasses and eyes stay; remove: inpaint the frames before the swap, only the real frames show"}),
}


def _regions_for(keep_mouth: bool) -> tuple[str, ...]:
    return tuple(name for name in DEFAULT_REGIONS if not (keep_mouth and name == "mouth"))


def _default_choice(available: list[str], preferred: str) -> str:
    return preferred if preferred in available else available[0]


def _resize_background(background: np.ndarray | None, frame: np.ndarray, mode: str) -> np.ndarray:
    """Background plate for the matting composite in frame size (BGR uint8)."""
    import cv2

    height, width = frame.shape[:2]
    if mode == "image":
        if background is None:
            raise RuntimeError("background_mode 'image' needs a background image (a clean plate without you in it)")
        if background.shape[:2] != (height, width):
            background = cv2.resize(background, (width, height), interpolation=cv2.INTER_AREA)
        return background
    if mode == "green":
        return np.full_like(frame, (0, 255, 0))
    if mode == "blur":
        return cv2.GaussianBlur(frame, (0, 0), max(4.0, width / 40.0))
    return frame


class LookaheadBuffer:
    """Delay frames by ``depth`` and average the landmarks with the frames ahead.

    Detection runs on every captured frame immediately (2 ms); the swap runs on
    the oldest buffered frame with the centred mean of its landmarks and those
    of the following frames (jump-guarded), which removes jitter without lag.
    """

    def __init__(self, depth: int) -> None:
        self.depth = max(0, int(depth))
        self.items: list[tuple[Any, np.ndarray, np.ndarray | None]] = []

    def push(self, captured: Any, frame: np.ndarray, landmarks: np.ndarray | None):
        if self.depth == 0:
            return captured, frame, landmarks
        self.items.append((captured, frame, landmarks))
        if len(self.items) <= self.depth:
            return None
        oldest_captured, oldest_frame, oldest_landmarks = self.items.pop(0)
        if oldest_landmarks is None:
            return oldest_captured, oldest_frame, None
        window = [oldest_landmarks]
        eye = max(float(np.linalg.norm(oldest_landmarks[1] - oldest_landmarks[0])), 1.0)
        for _, _, future in self.items:
            if future is None or float(np.linalg.norm(future - oldest_landmarks, axis=1).max()) > eye * 0.35:
                break
            window.append(future)
        return oldest_captured, oldest_frame, np.mean(np.stack(window), axis=0).astype(np.float32)


class DaWastehFaceSwapModelLoader:
    """Load detector, swapper, enhancer, occluder, parser and matting on one DirectML adapter."""

    CATEGORY = "DaWasteh/Live Avatar"
    RETURN_TYPES = ("DAW_FACESWAP",)
    RETURN_NAMES = ("face_swap",)
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        swappers = available_swappers() or list(SWAPPERS)
        enhancers = ["none", *(available_enhancers() or list(ENHANCERS))]
        occluders = ["none", *(available_mask_models(OCCLUDERS, MASK_SUBDIR) or list(OCCLUDERS))]
        parsers = ["none", *(available_mask_models(PARSERS, MASK_SUBDIR) or list(PARSERS))]
        matters = ["none", *(available_mask_models(MATTERS, MATTING_SUBDIR) or list(MATTERS))]
        return {
            "required": {
                "swapper": (swappers, {"default": _default_choice(swappers, "hyperswap_1c_256")}),
                "enhancer": (enhancers, {"default": _default_choice(enhancers, "gpen_bfr_256")}),
                "occluder": (occluders, {"default": _default_choice(occluders, "xseg_3"), "tooltip": "hands/objects in front of the face stay visible; xseg_3 keeps beard, mouth and glasses lenses as face"}),
                "parser": (parsers, {"default": _default_choice(parsers, "bisenet_resnet_34"), "tooltip": "face regions for the paste mask, the mouth mask and the beard shave"}),
                "matting": (matters, {"default": "none", "tooltip": "person matting for Workflow 17 (background replacement)"}),
                "dml_device_id": ("INT", {"default": 1, "min": 0, "max": 7, "tooltip": "DirectML adapter for detector, swapper and enhancer; on this host 1 = R9700, 0 = RX 9070 XT"}),
                "mask_device_id": ("INT", {"default": 0, "min": 0, "max": 7, "tooltip": "DirectML adapter for occluder, parser and matting; they run on a worker thread beside the swapper, so the other GPU is the fastest choice"}),
                "det_size": ([320, 480, 640], {"default": 320}),
                "det_threshold": ("FLOAT", {"default": 0.5, "min": 0.1, "max": 0.95, "step": 0.05}),
            }
        }

    def load(self, swapper: str, enhancer: str, occluder: str, parser: str, matting: str, dml_device_id: int, mask_device_id: int, det_size: int, det_threshold: float):
        engine = shared_engine(models_root(), swapper, enhancer, dml_device_id, int(det_size), occluder=occluder, parser=parser, matter=matting, mask_device_id=mask_device_id)
        engine.det_threshold = float(det_threshold)
        engine.load()
        return (engine,)


class DaWastehFaceSwapIdentity:
    """Average the ArcFace identity of one or more consented source images."""

    CATEGORY = "DaWasteh/Live Avatar"
    RETURN_TYPES = ("DAW_FACE_IDENTITY", "STRING")
    RETURN_NAMES = ("identity", "summary")
    FUNCTION = "extract"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"face_swap": ("DAW_FACESWAP",), "source_images": ("IMAGE",)},
            "optional": {
                "more_images": ("IMAGE",),
                "more_images_2": ("IMAGE",),
                "more_images_3": ("IMAGE",),
            },
        }

    def extract(self, face_swap: FaceSwapEngine, source_images: Any, more_images: Any = None, more_images_2: Any = None, more_images_3: Any = None):
        frames = image_tensor_to_bgr_list(source_images)
        for extra in (more_images, more_images_2, more_images_3):
            if extra is not None:
                frames.extend(image_tensor_to_bgr_list(extra))
        with face_swap.lock:
            identity = face_swap.identity_from_images(frames)
        summary = f"{identity.source_count}/{len(frames)} source faces averaged · {face_swap.swapper_name} · id {identity.fingerprint}"
        return (identity, summary)


def list_identity_folders() -> list[str]:
    """Sub-folders of ComfyUI/input that hold identity photos."""
    try:
        import folder_paths

        root = Path(folder_paths.get_input_directory())
    except Exception:
        return []
    folders = sorted(item.name for item in root.iterdir() if item.is_dir() and not item.name.startswith("."))
    return folders


def load_folder_images(folder: Path) -> list[np.ndarray]:
    import cv2

    frames: list[np.ndarray] = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            continue
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is not None:
            frames.append(image)
    return frames


class DaWastehFaceSwapIdentityFromFolder:
    """Average the identity over every photo in an input sub-folder (drop 5-20 photos there)."""

    CATEGORY = "DaWasteh/Live Avatar"
    RETURN_TYPES = ("DAW_FACE_IDENTITY", "STRING")
    RETURN_NAMES = ("identity", "summary")
    FUNCTION = "extract"

    @classmethod
    def INPUT_TYPES(cls):
        folders = list_identity_folders() or ["face-swap-identity"]
        return {
            "required": {
                "face_swap": ("DAW_FACESWAP",),
                "folder": (folders, {"default": _default_choice(folders, "face-swap-identity"), "tooltip": "sub-folder of ComfyUI/input with photos of the target person (front, 3/4, smile, mouth open)"}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, face_swap: Any, folder: str) -> str:
        import folder_paths

        root = Path(folder_paths.get_input_directory()) / folder
        if not root.is_dir():
            return "missing"
        return ";".join(f"{item.name}:{item.stat().st_mtime_ns}" for item in sorted(root.iterdir()))

    def extract(self, face_swap: FaceSwapEngine, folder: str):
        import folder_paths

        root = Path(folder_paths.get_input_directory()) / folder
        frames = load_folder_images(root) if root.is_dir() else []
        if not frames:
            raise RuntimeError(f"no images found in {root}; create the folder under ComfyUI/input and drop photos there")
        with face_swap.lock:
            identity = face_swap.identity_from_images(frames)
        summary = f"{identity.source_count}/{len(frames)} faces from {folder} · {face_swap.swapper_name} · id {identity.fingerprint}"
        return (identity, summary)


class DaWastehWebcamSnapshot:
    """Grab frames from the webcam (test images of yourself, or a clean background plate)."""

    CATEGORY = "DaWasteh/Live Avatar"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "grab"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cam_index": ("INT", {"default": 2, "min": 0, "max": 255}),
                "capture_backend": (["auto", "DirectShow", "Media Foundation"], {"default": "DirectShow"}),
                "capture_width": ("INT", {"default": 1280, "min": 320, "max": 4096}),
                "capture_height": ("INT", {"default": 720, "min": 240, "max": 4096}),
                "mirror": ("BOOLEAN", {"default": True}),
                "delay_seconds": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 30.0, "step": 0.5, "tooltip": "time to step out of the frame for a clean plate, or to pose"}),
                "frames": ("INT", {"default": 1, "min": 1, "max": 16}),
                "frame_interval_seconds": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 10.0, "step": 0.1}),
                "retake": ("INT", {"default": 0, "min": 0, "max": 1000000, "tooltip": "change the value to capture again; otherwise the last capture stays cached"}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> str:
        # Deterministic on purpose: the capture is cached until a widget (e.g. retake) changes.
        return json.dumps(kwargs, sort_keys=True, default=str)

    def grab(self, cam_index: int, capture_backend: str, capture_width: int, capture_height: int, mirror: bool, delay_seconds: float, frames: int, frame_interval_seconds: float, retake: int = 0):
        live = _live_nodes()
        slot = live.LatestFrameSlot()
        capture = live.CaptureWorker(slot, cam_index, capture_width, capture_height, False, 0, 0, mirror, capture_backend, output_size=None)
        grabbed: list[np.ndarray] = []
        try:
            capture.start()
            deadline = time.monotonic() + float(delay_seconds)
            sequence = 0
            while time.monotonic() < deadline:
                slot.raise_if_error()
                item = slot.get_after(sequence, 0.5)
                if item is not None:
                    sequence = item[1]
            while len(grabbed) < int(frames):
                slot.raise_if_error()
                item = slot.get_after(sequence, 2.0)
                if item is None:
                    continue
                captured, sequence = item
                image = captured.image if isinstance(captured, live.TimedFrame) else captured
                grabbed.append(np.ascontiguousarray(image))
                if len(grabbed) < int(frames):
                    time.sleep(float(frame_interval_seconds))
        finally:
            capture.stop()
        return (bgr_list_to_image_tensor(grabbed),)


class DaWastehFaceSwapImage:
    """Offline preview: swap every frame of an IMAGE batch (tune settings here first)."""

    CATEGORY = "DaWasteh/Live Avatar"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "timing")
    FUNCTION = "swap"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "face_swap": ("DAW_FACESWAP",),
                "identity": ("DAW_FACE_IDENTITY",),
                "image": ("IMAGE",),
                **SWAP_TUNING_INPUTS,
                "background_mode": (BACKGROUND_MODES, {"default": "off", "tooltip": "needs a matting model in the loader"}),
            },
            "optional": {"background": ("IMAGE",)},
        }

    def swap(
        self,
        face_swap: FaceSwapEngine,
        identity: FaceIdentity,
        image: Any,
        mask_blur: float,
        crop_scale: float,
        color_match: float,
        keep_mouth: bool,
        shave: str,
        shave_extent: float,
        enhancer_blend: float,
        identity_strength: float,
        temporal_smoothing: float,
        mask_feather: float,
        glasses: str,
        background_mode: str,
        background: Any = None,
    ):
        frames = image_tensor_to_bgr_list(image)
        plate = image_tensor_to_bgr_list(background)[0] if background is not None else None
        outputs = []
        timings: list[SwapTimings] = []
        regions = _regions_for(keep_mouth)
        with face_swap.lock:
            face_swap.reset_tracking()
            if background_mode != "off" and face_swap.matter is None:
                raise RuntimeError("background_mode needs a matting model selected in the loader")
            for frame in frames:
                timing = SwapTimings()
                result = face_swap.swap_frame(
                    frame, identity, mask_blur=mask_blur, landmark_smoothing=0.0, enhancer_blend=enhancer_blend,
                    crop_scale=crop_scale, color_match=color_match, regions=regions, shave=shave, shave_extent=shave_extent,
                    identity_strength=identity_strength, temporal_smoothing=temporal_smoothing, mask_feather=mask_feather,
                    glasses=glasses, matte=background_mode != "off", timings=timing,
                )
                if background_mode != "off" and face_swap.last_alpha is not None:
                    result = composite_background(result, face_swap.last_alpha, _resize_background(plate, frame, background_mode))
                outputs.append(result)
                timings.append(timing)
        found = sum(1 for item in timings if item.face_found)
        count = max(1, len(timings))
        text = (
            f"{found}/{len(frames)} faces swapped · mean {sum(t.total_ms for t in timings) / count:.1f} ms "
            f"(detect {sum(t.detect_ms for t in timings) / count:.1f}, swap {sum(t.swap_ms for t in timings) / count:.1f}, "
            f"mask {sum(t.mask_ms for t in timings) / count:.1f}, enhance {sum(t.enhance_ms for t in timings) / count:.1f}, "
            f"matte {sum(t.matte_ms for t in timings) / count:.1f})"
        )
        return (bgr_list_to_image_tensor(outputs), text)


class DaWastehLiveFaceSwap:
    """Webcam → face swap (→ matting) → Spout, blocking until Interrupt (never Run (Instant))."""

    OUTPUT_NODE = True
    RETURN_TYPES = ()
    FUNCTION = "run"
    CATEGORY = "DaWasteh/Live Avatar"
    DESCRIPTION = (
        "Continuous DirectML face swap of the webcam feed into a Spout sender for OBS, optionally "
        "with person matting onto a clean background plate (Workflow 17). "
        "Run once normally and stop with Interrupt; it blocks other ComfyUI jobs while active."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "face_swap": ("DAW_FACESWAP",),
                "identity": ("DAW_FACE_IDENTITY",),
                "sender_name": ("STRING", {"default": "ComfyLiveFaceSwap"}),
                "sender_fps": ("INT", {"default": 30, "min": 1, "max": 60}),
                "cam_index": ("INT", {"default": 2, "min": 0, "max": 255}),
                "capture_backend": (["auto", "DirectShow", "Media Foundation"], {"default": "DirectShow"}),
                "capture_width": ("INT", {"default": 1280, "min": 320, "max": 4096}),
                "capture_height": ("INT", {"default": 720, "min": 240, "max": 4096}),
                "mirror": ("BOOLEAN", {"default": True}),
                **SWAP_TUNING_INPUTS,
                "landmark_smoothing": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 0.95, "step": 0.05}),
                "enhancer_every": ("INT", {"default": 1, "min": 1, "max": 10}),
                "parser_every": ("INT", {"default": 1, "min": 1, "max": 4, "tooltip": "re-parse the face regions only every n-th frame (2 lifts the frame rate when matting or the RVC voice service share the mask GPU)"}),
                "lookahead_frames": ("INT", {"default": 2, "min": 0, "max": 6, "tooltip": "delay the output by n camera frames and smooth the landmarks with the frames ahead (centred, no lag); ~40 ms per frame"}),
                "background_mode": (BACKGROUND_MODES, {"default": "off", "tooltip": "image = composite onto the clean plate (needs matting in the loader)"}),
                "max_frames": ("INT", {"default": 0, "min": 0, "max": 1000000}),
                "metrics_json_path": ("STRING", {"default": "live-face-swap/metrics.json"}),
            },
            "optional": {"background": ("IMAGE",)},
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> float:
        return float("NaN")

    def run(
        self,
        face_swap: FaceSwapEngine,
        identity: FaceIdentity,
        sender_name: str,
        sender_fps: int,
        cam_index: int,
        capture_backend: str,
        capture_width: int,
        capture_height: int,
        mirror: bool,
        mask_blur: float,
        crop_scale: float,
        color_match: float,
        keep_mouth: bool,
        shave: str,
        shave_extent: float,
        enhancer_blend: float,
        identity_strength: float,
        temporal_smoothing: float,
        mask_feather: float,
        glasses: str,
        landmark_smoothing: float,
        enhancer_every: int,
        parser_every: int,
        lookahead_frames: int,
        background_mode: str,
        max_frames: int,
        metrics_json_path: str = "",
        background: Any = None,
    ) -> tuple[()]:
        if not sys.platform.startswith("win"):
            raise RuntimeError("Spout output is supported on Windows only")
        import comfy.model_management as mm

        live = _live_nodes()
        capture_slot = live.LatestFrameSlot()
        output_slot = live.LatestFrameSlot()
        capture = live.CaptureWorker(
            capture_slot, cam_index, capture_width, capture_height, False, 0, 0, mirror, capture_backend,
            output_size=None,
        )
        metrics = live.LiveAvatarMetrics()
        metrics.start()
        spout = live.SpoutWorker(output_slot, sender_name, sender_fps, metrics)
        last_publish = time.monotonic()
        swap_ms: list[float] = []
        regions = _regions_for(keep_mouth)
        plate = image_tensor_to_bgr_list(background)[0] if background is not None else None
        plate_cache: np.ndarray | None = None
        lookahead = LookaheadBuffer(int(lookahead_frames))
        try:
            with face_swap.lock:
                face_swap.load()
                if background_mode != "off" and face_swap.matter is None:
                    raise RuntimeError("background_mode needs a matting model selected in the loader")
                face_swap.reset_tracking()
                capture.start()
                spout.start()
                sequence = 0
                last_capture_sequence = 0
                frames = 0
                while max_frames == 0 or frames < max_frames:
                    mm.throw_exception_if_processing_interrupted()
                    capture_slot.raise_if_error()
                    output_slot.raise_if_error()
                    item = capture_slot.get_after(sequence, 2.0)
                    if item is None:
                        continue
                    captured, sequence = item
                    if sequence > last_capture_sequence + 1:
                        metrics.dropped(sequence - last_capture_sequence - 1)
                    last_capture_sequence = sequence
                    bgr = captured.image if isinstance(captured, live.TimedFrame) else captured
                    timing = SwapTimings()
                    ready = lookahead.push(captured, bgr, face_swap.detect_face(bgr))
                    if ready is None:
                        continue
                    captured, bgr, landmarks = ready
                    swapped = face_swap.swap_frame(
                        bgr, identity,
                        mask_blur=mask_blur, landmark_smoothing=landmark_smoothing,
                        enhancer_blend=enhancer_blend, enhancer_every=enhancer_every,
                        crop_scale=crop_scale, color_match=color_match, regions=regions,
                        shave=shave, shave_extent=shave_extent, matte=background_mode != "off",
                        parser_every=parser_every, identity_strength=identity_strength,
                        temporal_smoothing=temporal_smoothing, mask_feather=mask_feather, glasses=glasses,
                        landmarks=landmarks, timings=timing,
                    )
                    if background_mode != "off" and face_swap.last_alpha is not None:
                        composite_started = time.perf_counter()
                        if plate_cache is None or plate_cache.shape != bgr.shape or background_mode == "blur":
                            plate_cache = _resize_background(plate, bgr, background_mode)
                        swapped = composite_background(swapped, face_swap.last_alpha, plate_cache)
                        timing.matte_ms = (time.perf_counter() - composite_started) * 1000.0
                        timing.total_ms += timing.matte_ms
                    swap_ms.append(timing.total_ms)
                    if len(swap_ms) > 600:
                        del swap_ms[:-600]
                    produced_at = time.monotonic()
                    output_slot.publish(live.TimedFrame(bgr_to_rgba(swapped), capture_time=getattr(captured, "capture_time", None), produced_time=produced_at))
                    metrics.produced(now=produced_at)
                    frames += 1
                    if metrics_json_path and produced_at - last_publish >= 1.0:
                        self._publish(metrics, metrics_json_path, swap_ms, timing)
                        last_publish = produced_at
        finally:
            capture_stopped = spout_stopped = False
            try:
                capture_stopped = capture.stop()
            except BaseException:
                LOGGER.exception("webcam worker cleanup failed")
            try:
                spout_stopped = spout.stop()
            except BaseException:
                LOGGER.exception("Spout worker cleanup failed")
            if metrics_json_path:
                self._publish(metrics, metrics_json_path, swap_ms, None)
            if not capture_stopped:
                LOGGER.error("webcam worker did not stop within the cleanup timeout")
            if not spout_stopped:
                LOGGER.error("Spout worker did not stop within the cleanup timeout")
        return ()

    @staticmethod
    def _publish(metrics: Any, destination: str, swap_ms: list[float], timing: SwapTimings | None) -> None:
        try:
            extra = {
                "swap_ms_mean": float(np.mean(swap_ms)) if swap_ms else None,
                "swap_ms_p95": float(np.percentile(swap_ms, 95)) if swap_ms else None,
                "last_face_found": bool(timing.face_found) if timing else None,
                "last_stage_ms": {
                    "detect": timing.detect_ms, "swap": timing.swap_ms, "mask": timing.mask_ms,
                    "enhance": timing.enhance_ms, "matte": timing.matte_ms,
                } if timing else None,
            }
            metrics.publish_json(destination, extra)
        except Exception as error:  # telemetry must never stop the transport
            LOGGER.warning("live face swap metrics not published: %s", error)


NODE_CLASS_MAPPINGS = {
    "DaWastehFaceSwapModelLoader": DaWastehFaceSwapModelLoader,
    "DaWastehFaceSwapIdentity": DaWastehFaceSwapIdentity,
    "DaWastehFaceSwapIdentityFromFolder": DaWastehFaceSwapIdentityFromFolder,
    "DaWastehWebcamSnapshot": DaWastehWebcamSnapshot,
    "DaWastehFaceSwapImage": DaWastehFaceSwapImage,
    "DaWastehLiveFaceSwap": DaWastehLiveFaceSwap,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "DaWastehFaceSwapModelLoader": "Face Swap Models · DirectML (DaWasteh)",
    "DaWastehFaceSwapIdentity": "Face Swap Identity from Images (DaWasteh)",
    "DaWastehFaceSwapIdentityFromFolder": "Face Swap Identity from Folder (DaWasteh)",
    "DaWastehWebcamSnapshot": "Webcam Snapshot / Clean Plate (DaWasteh)",
    "DaWastehFaceSwapImage": "Face Swap Image Preview (DaWasteh)",
    "DaWastehLiveFaceSwap": "Live Face Swap Webcam → Spout (DaWasteh)",
}
