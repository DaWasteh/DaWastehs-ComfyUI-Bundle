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
import logging
import sys
import threading
import time
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
}


@dataclass(frozen=True)
class SwapperSpec:
    file_name: str
    kind: str  # "inswapper" | "hyperswap"
    template: str
    size: int
    mean: float
    std: float
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
    ),
}

ENHANCERS: dict[str, EnhancerSpec] = {
    "gpen_bfr_256": EnhancerSpec("gpen_bfr_256.onnx", "arcface_128", 256, "GPEN non-commercial", "bad8bf0426873828df2dbf4e3b3d9ababba9da7965b8b72426569486f7ae5c25"),
    "gfpgan_1.4": EnhancerSpec("gfpgan_1.4.onnx", "ffhq_512", 512, "GFPGAN Apache-2.0", "accc4757b26bdb89b32b4d3500d4f79c9dff97c1dd7c7104bf9dcb95e3311385"),
}

DETECTOR_PACK = "buffalo_l"
DETECTOR_FILES = ("det_10g.onnx", "w600k_r50.onnx")
SWAPPER_SUBDIR = "insightface"
ENHANCER_SUBDIR = "facerestore_models"


# --------------------------------------------------------------------------- #
# Pure geometry / image helpers (unit-tested without any model)
# --------------------------------------------------------------------------- #
def estimate_affine(landmarks_5: np.ndarray, template: str, size: int) -> np.ndarray:
    """Affine matrix mapping five landmarks onto ``template`` scaled to ``size``."""
    import cv2

    if landmarks_5.shape != (5, 2):
        raise ValueError("five (x, y) landmarks are required")
    target = WARP_TEMPLATES[template] * float(size)
    matrix = cv2.estimateAffinePartial2D(
        landmarks_5.astype(np.float32), target, method=cv2.RANSAC, ransacReprojThreshold=100
    )[0]
    if matrix is None:
        raise ValueError("could not estimate the face alignment matrix")
    return matrix


def warp_face(frame: np.ndarray, landmarks_5: np.ndarray, template: str, size: int) -> tuple[np.ndarray, np.ndarray]:
    import cv2

    matrix = estimate_affine(landmarks_5, template, size)
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
    inverse_mask = cv2.warpAffine(mask, shifted, region_size).clip(0, 1)[..., None]
    inverse_crop = cv2.warpAffine(crop, shifted, region_size, borderMode=cv2.BORDER_REPLICATE)
    result = frame.copy()
    region = result[y1:y2, x1:x2].astype(np.float32)
    region = region * (1.0 - inverse_mask) + inverse_crop.astype(np.float32) * inverse_mask
    result[y1:y2, x1:x2] = np.clip(region, 0, 255).astype(frame.dtype)
    return result


def prepare_swapper_input(crop_bgr: np.ndarray, spec: SwapperSpec) -> np.ndarray:
    """BGR uint8 crop → normalised NCHW RGB float32 batch of one."""
    rgb = crop_bgr[:, :, ::-1].astype(np.float32) / 255.0
    rgb = (rgb - spec.mean) / spec.std
    return np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32)


def normalize_swapper_output(output_chw: np.ndarray, spec: SwapperSpec) -> np.ndarray:
    """Model CHW output → BGR uint8 crop."""
    rgb = output_chw.transpose(1, 2, 0)
    if spec.kind == "hyperswap":
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
    return np.ascontiguousarray(embedding / norm, dtype=np.float32)


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


def available_swappers(root: Path | None = None) -> list[str]:
    root = models_root() if root is None else root
    return [name for name, spec in SWAPPERS.items() if (root / SWAPPER_SUBDIR / spec.file_name).is_file()]


def available_enhancers(root: Path | None = None) -> list[str]:
    root = models_root() if root is None else root
    return [name for name, spec in ENHANCERS.items() if (root / ENHANCER_SUBDIR / spec.file_name).is_file()]


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


@dataclass
class SwapTimings:
    detect_ms: float = 0.0
    swap_ms: float = 0.0
    enhance_ms: float = 0.0
    total_ms: float = 0.0
    face_found: bool = False


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
    ) -> None:
        self.root = Path(root)
        self.swapper_name = swapper
        self.spec = SWAPPERS[swapper]
        self.enhancer_name = enhancer if enhancer and enhancer != "none" else None
        self.enhancer_spec = ENHANCERS[self.enhancer_name] if self.enhancer_name else None
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
    def _create_session(self, path: Path, fixed_dims: int | None = None) -> Any:
        import onnxruntime

        providers, options = directml_providers(self.dml_device_id)
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
        swapper_path = self.root / SWAPPER_SUBDIR / self.spec.file_name
        if not swapper_path.is_file():
            raise RuntimeError(f"swapper model is missing: {swapper_path}")
        self.detector = self._detector_factory()
        self.embedder = self._embedder_factory()
        self.swapper = self._session_factory(swapper_path)
        self._swapper_inputs = self._map_inputs(self.swapper)
        if self.spec.kind == "inswapper":
            self.emap = self._load_emap(swapper_path)
        if self.enhancer_spec is not None:
            enhancer_path = self.root / ENHANCER_SUBDIR / self.enhancer_spec.file_name
            if not enhancer_path.is_file():
                raise RuntimeError(f"enhancer model is missing: {enhancer_path}")
            self.enhancer = self._session_factory(enhancer_path)
            self._enhancer_inputs = self._map_inputs(self.enhancer)
        return self

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
        for image in images_bgr:
            bboxes, kpss = self.detector.detect(image)
            index = largest_face(bboxes, kpss, None)
            if index is None:
                continue
            embeddings.append(self.embedder.embed(image, np.asarray(kpss[index], dtype=np.float32)))
        if not embeddings:
            raise RuntimeError("no face was detected in the source image(s)")
        raw = average_embedding(embeddings)
        prepared = source_embedding_for(self.spec, raw, self.emap)
        fingerprint = hashlib.sha256(prepared.tobytes()).hexdigest()[:16]
        return FaceIdentity(prepared, len(embeddings), fingerprint)

    # -- per frame ----------------------------------------------------------
    def reset_tracking(self) -> None:
        self._previous_center = None
        self._previous_landmarks = None
        self._frame_index = 0

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
        timings: SwapTimings | None = None,
    ) -> np.ndarray:
        """Return a swapped BGR frame; the untouched frame when no face is present."""
        self.load()
        timings = timings if timings is not None else SwapTimings()
        started = time.perf_counter()
        bboxes, kpss = self.detector.detect(frame_bgr)
        timings.detect_ms = (time.perf_counter() - started) * 1000.0
        index = largest_face(bboxes, kpss, self._previous_center)
        if index is None:
            self._previous_center = None
            self._previous_landmarks = None
            timings.face_found = False
            timings.total_ms = (time.perf_counter() - started) * 1000.0
            return frame_bgr
        bbox = bboxes[index]
        self._previous_center = np.array([(bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5], dtype=np.float32)
        landmarks = smooth_landmarks(self._previous_landmarks, np.asarray(kpss[index], dtype=np.float32), landmark_smoothing)
        self._previous_landmarks = landmarks
        timings.face_found = True

        swap_started = time.perf_counter()
        crop, matrix = warp_face(frame_bgr, landmarks, self.spec.template, self.spec.size)
        feeds = {self._swapper_inputs["target"]: prepare_swapper_input(crop, self.spec)}
        if "source" in self._swapper_inputs:
            feeds[self._swapper_inputs["source"]] = identity.embedding
        output = self.swapper.run(None, feeds)[0][0]
        swapped_crop = normalize_swapper_output(output, self.spec)
        mask = create_box_mask(self.spec.size, mask_blur, mask_padding)
        result = paste_back(frame_bgr, swapped_crop, mask, matrix)
        timings.swap_ms = (time.perf_counter() - swap_started) * 1000.0

        self._frame_index += 1
        if self.enhancer is not None and enhancer_blend > 0.0 and (self._frame_index % max(1, int(enhancer_every))) == 0:
            enhance_started = time.perf_counter()
            result = self._enhance(result, landmarks, enhancer_blend, mask_blur)
            timings.enhance_ms = (time.perf_counter() - enhance_started) * 1000.0
        timings.total_ms = (time.perf_counter() - started) * 1000.0
        return result

    def _enhance(self, frame_bgr: np.ndarray, landmarks: np.ndarray, blend: float, mask_blur: float) -> np.ndarray:
        spec = self.enhancer_spec
        assert spec is not None
        crop, matrix = warp_face(frame_bgr, landmarks, spec.template, spec.size)
        feeds = {self._enhancer_inputs["target"]: prepare_enhancer_input(crop)}
        if "weight" in self._enhancer_inputs:
            feeds[self._enhancer_inputs["weight"]] = np.array([1.0], dtype=np.float64)
        output = self.enhancer.run(None, feeds)[0][0]
        enhanced_crop = normalize_enhancer_output(output)
        mask = create_box_mask(spec.size, mask_blur, (0, 0, 0, 0))
        pasted = paste_back(frame_bgr, enhanced_crop, mask, matrix)
        weight = float(np.clip(blend, 0.0, 1.0))
        if weight >= 1.0:
            return pasted
        return np.clip(frame_bgr.astype(np.float32) * (1.0 - weight) + pasted.astype(np.float32) * weight, 0, 255).astype(np.uint8)


_ENGINES: dict[tuple[Any, ...], FaceSwapEngine] = {}
_ENGINES_LOCK = threading.Lock()


def shared_engine(root: Path, swapper: str, enhancer: str | None, dml_device_id: int, det_size: int) -> FaceSwapEngine:
    key = (str(root), swapper, enhancer or "none", int(dml_device_id), int(det_size))
    with _ENGINES_LOCK:
        engine = _ENGINES.get(key)
        if engine is None:
            engine = FaceSwapEngine(root, swapper, enhancer, dml_device_id, det_size)
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
class DaWastehFaceSwapModelLoader:
    """Load detector, swapper and optional enhancer on one DirectML adapter."""

    CATEGORY = "DaWasteh/Live Avatar"
    RETURN_TYPES = ("DAW_FACESWAP",)
    RETURN_NAMES = ("face_swap",)
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        swappers = available_swappers() or list(SWAPPERS)
        enhancers = ["none", *(available_enhancers() or list(ENHANCERS))]
        return {
            "required": {
                "swapper": (swappers, {"default": swappers[0]}),
                "enhancer": (enhancers, {"default": "none"}),
                "dml_device_id": ("INT", {"default": 1, "min": 0, "max": 7, "tooltip": "DirectML adapter index; on this host 1 = R9700, 0 = RX 9070 XT"}),
                "det_size": ([320, 480, 640], {"default": 320}),
                "det_threshold": ("FLOAT", {"default": 0.5, "min": 0.1, "max": 0.95, "step": 0.05}),
            }
        }

    def load(self, swapper: str, enhancer: str, dml_device_id: int, det_size: int, det_threshold: float):
        engine = shared_engine(models_root(), swapper, enhancer, dml_device_id, int(det_size))
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
        return {"required": {"face_swap": ("DAW_FACESWAP",), "source_images": ("IMAGE",)}}

    def extract(self, face_swap: FaceSwapEngine, source_images: Any):
        frames = image_tensor_to_bgr_list(source_images)
        with face_swap.lock:
            identity = face_swap.identity_from_images(frames)
        summary = f"{identity.source_count}/{len(frames)} source faces averaged · {face_swap.swapper_name} · id {identity.fingerprint}"
        return (identity, summary)


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
                "mask_blur": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05}),
                "enhancer_blend": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
            }
        }

    def swap(self, face_swap: FaceSwapEngine, identity: FaceIdentity, image: Any, mask_blur: float, enhancer_blend: float):
        frames = image_tensor_to_bgr_list(image)
        outputs = []
        timings: list[SwapTimings] = []
        with face_swap.lock:
            face_swap.reset_tracking()
            for frame in frames:
                timing = SwapTimings()
                outputs.append(face_swap.swap_frame(frame, identity, mask_blur=mask_blur, landmark_smoothing=0.0, enhancer_blend=enhancer_blend, timings=timing))
                timings.append(timing)
        found = sum(1 for item in timings if item.face_found)
        mean_total = sum(item.total_ms for item in timings) / max(1, len(timings))
        mean_detect = sum(item.detect_ms for item in timings) / max(1, len(timings))
        mean_swap = sum(item.swap_ms for item in timings) / max(1, len(timings))
        mean_enh = sum(item.enhance_ms for item in timings) / max(1, len(timings))
        text = (
            f"{found}/{len(frames)} faces swapped · mean {mean_total:.1f} ms "
            f"(detect {mean_detect:.1f}, swap {mean_swap:.1f}, enhance {mean_enh:.1f})"
        )
        return (bgr_list_to_image_tensor(outputs), text)


class DaWastehLiveFaceSwap:
    """Webcam → face swap → Spout, blocking until Interrupt (never Run (Instant))."""

    OUTPUT_NODE = True
    RETURN_TYPES = ()
    FUNCTION = "run"
    CATEGORY = "DaWasteh/Live Avatar"
    DESCRIPTION = (
        "Continuous DirectML face swap of the webcam feed into a Spout sender for OBS. "
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
                "mask_blur": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05}),
                "landmark_smoothing": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 0.95, "step": 0.05}),
                "enhancer_blend": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
                "enhancer_every": ("INT", {"default": 1, "min": 1, "max": 10}),
                "max_frames": ("INT", {"default": 0, "min": 0, "max": 1000000}),
                "metrics_json_path": ("STRING", {"default": "live-face-swap/metrics.json"}),
            }
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
        landmark_smoothing: float,
        enhancer_blend: float,
        enhancer_every: int,
        max_frames: int,
        metrics_json_path: str = "",
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
        try:
            with face_swap.lock:
                face_swap.load()
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
                    swapped = face_swap.swap_frame(
                        bgr, identity,
                        mask_blur=mask_blur, landmark_smoothing=landmark_smoothing,
                        enhancer_blend=enhancer_blend, enhancer_every=enhancer_every, timings=timing,
                    )
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
            }
            metrics.publish_json(destination, extra)
        except Exception as error:  # telemetry must never stop the transport
            LOGGER.warning("live face swap metrics not published: %s", error)


NODE_CLASS_MAPPINGS = {
    "DaWastehFaceSwapModelLoader": DaWastehFaceSwapModelLoader,
    "DaWastehFaceSwapIdentity": DaWastehFaceSwapIdentity,
    "DaWastehFaceSwapImage": DaWastehFaceSwapImage,
    "DaWastehLiveFaceSwap": DaWastehLiveFaceSwap,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "DaWastehFaceSwapModelLoader": "Face Swap Models · DirectML (DaWasteh)",
    "DaWastehFaceSwapIdentity": "Face Swap Identity from Images (DaWasteh)",
    "DaWastehFaceSwapImage": "Face Swap Image Preview (DaWasteh)",
    "DaWastehLiveFaceSwap": "Live Face Swap Webcam → Spout (DaWasteh)",
}
