"""Continuous, latest-frame LivePortrait output node.

Torch work deliberately remains in ComfyUI's execution thread. Only camera I/O
and Spout presentation use worker threads, each owning its native resource.
"""
from __future__ import annotations

import atexit
import copy
import importlib
import json
import logging
import os
import tempfile
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


import numpy as np

LOGGER = logging.getLogger(__name__)

LIVE_AVATAR_MULTIVIEW_PREFIXES = (
    "13_front_full_body",
    "13_left_profile_full_body",
    "13_rear_full_body",
    "13_right_profile_full_body",
)


def latest_live_avatar_output(prefix: str, output_root: str | Path | None = None) -> Path:
    """Resolve the newest semantic Workflow-13 PNG without accepting arbitrary paths."""
    if prefix not in LIVE_AVATAR_MULTIVIEW_PREFIXES:
        raise ValueError("unsupported LiveAvatar output prefix")
    if output_root is None:
        import folder_paths
        output_root = folder_paths.get_output_directory()
    directory = Path(output_root).resolve() / "LiveAvatar"
    if not directory.is_dir() or directory.is_symlink():
        raise FileNotFoundError(f"LiveAvatar output directory is missing or unsafe: {directory}")
    candidates = []
    for candidate in directory.glob(f"{prefix}_*.png"):
        if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size <= 0:
            continue
        resolved = candidate.resolve()
        try:
            resolved.relative_to(directory)
        except ValueError:
            continue
        candidates.append(resolved)
    if not candidates:
        raise FileNotFoundError(f"no generated Workflow-13 output exists for {prefix!r}")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


class DaWastehLatestLiveAvatarOutput:
    """Load the newest corrected Workflow-13 view for Workflow 14."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prefix": (list(LIVE_AVATAR_MULTIVIEW_PREFIXES),)}}

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "source_file")
    FUNCTION = "load"
    CATEGORY = "DaWasteh/Live Avatar"

    @classmethod
    def IS_CHANGED(cls, prefix: str) -> str:
        path = latest_live_avatar_output(prefix)
        stat = path.stat()
        return f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}"

    def load(self, prefix: str):
        path = latest_live_avatar_output(prefix)
        from nodes import LoadImage
        image, mask = LoadImage().load_image(f"LiveAvatar/{path.name} [output]")
        return image, mask, str(path)


class DaWastehWorkflow12Preflight:
    """Fail-closed configuration check; this node never starts a service."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config_path": ("STRING", {"default": "L:/ComfyUI/config/live-avatar-12.json"})}}
    RETURN_TYPES = ("BOOLEAN", "STRING", "STRING")
    RETURN_NAMES = ("ready", "status", "launch_command")
    OUTPUT_NODE = True
    FUNCTION = "check"
    CATEGORY = "DaWasteh/Live Avatar"
    def check(self, config_path: str):
        # Works both as a ComfyUI package and in direct unittest loading.
        import importlib.util
        spec = importlib.util.spec_from_file_location("dawasteh_preflight", Path(__file__).with_name("preflight.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.workflow12_preflight(config_path)
        values = (result["ready"], result["status"], result["launch_command"])
        return {"ui": {"text": [result["status"]]}, "result": values}


@dataclass
class TimedFrame:
    image: np.ndarray
    capture_time: float | None = None
    produced_time: float | None = None

@dataclass
class LiveAvatarMetrics:
    """Thread-safe bounded transport truth: production is never presentation."""
    sample_limit: int = 4096
    ai_frames: int = 0; presented_frames: int = 0; unique_presentations: int = 0; duplicate_presentations: int = 0; dropped_capture_frames: int = 0
    capture_to_spout_ms: list[float] = field(default_factory=list); unique_intervals_ms: list[float] = field(default_factory=list)
    _started: float | None = None; _last_ai: float | None = None; _lock: threading.Lock = field(default_factory=threading.Lock)
    def _add(self, values, value):
        values.append(value)
        if len(values)>self.sample_limit: del values[:len(values)-self.sample_limit]
    def start(self, now=None):
        with self._lock:
            if self._started is None:self._started=time.monotonic() if now is None else now
    def reset(self, now=None):
        with self._lock:
            self.ai_frames = self.presented_frames = self.unique_presentations = 0
            self.duplicate_presentations = self.dropped_capture_frames = 0
            self.capture_to_spout_ms.clear(); self.unique_intervals_ms.clear()
            self._started = time.monotonic() if now is None else now
            self._last_ai = None
    def produced(self, capture_time=None, now=None):
        now=time.monotonic() if now is None else now
        with self._lock:
            if self._started is None:self._started=now
            self.ai_frames+=1
            if self._last_ai is not None:self._add(self.unique_intervals_ms,(now-self._last_ai)*1000)
            self._last_ai=now
    def presented(self, unique, frame=None, now=None):
        now=time.monotonic() if now is None else now
        with self._lock:
            if self._started is None:self._started=now
            self.presented_frames+=1
            if unique:
                self.unique_presentations+=1
                if frame and frame.capture_time is not None:self._add(self.capture_to_spout_ms,(now-frame.capture_time)*1000)
            else:self.duplicate_presentations+=1
    def dropped(self,count):
        with self._lock:self.dropped_capture_frames+=max(0,count)
    @staticmethod
    def _percentile(v,p): return None if not v else sorted(v)[round((len(v)-1)*p)]
    def snapshot(self, now=None):
        with self._lock:
            now=time.monotonic() if now is None else now; elapsed=max(0,(now-(self._started if self._started is not None else now)))
            return {"ai_frames":self.ai_frames,"presented_frames":self.presented_frames,"unique_presentations":self.unique_presentations,"duplicate_presentations":self.duplicate_presentations,"dropped_capture_frames":self.dropped_capture_frames,"elapsed_seconds":elapsed,"ai_fps":self.ai_frames/elapsed if elapsed else 0,"presentation_fps":self.presented_frames/elapsed if elapsed else 0,"capture_to_spout_ms":{x:self._percentile(self.capture_to_spout_ms,p) for x,p in (("p50",.5),("p95",.95),("p99",.99))},"unique_frame_interval_ms":{x:self._percentile(self.unique_intervals_ms,p) for x,p in (("p50",.5),("p95",.95),("p99",.99))}}
    def publish_json(self,destination,extra=None):
        configured_root = os.environ.get("DAWASTEH_LIVE_AVATAR_LOG_ROOT")
        if configured_root:
            root = Path(configured_root).resolve()
        else:
            try:
                import folder_paths
                root = Path(folder_paths.base_path).resolve().parent / "logs"
            except (ImportError, AttributeError):
                root = (Path.cwd() / "logs").resolve()
        candidate = Path(str(destination).strip())
        dest = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if dest.suffix.lower() != ".json" or (dest != root and root not in dest.parents):
            raise ValueError(f"metrics_json_path must be a JSON file under {root}")
        dest.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=dest.parent,prefix='.metrics-',suffix='.tmp')
        payload = self.snapshot()
        if extra: payload.update(extra)
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(payload,f);f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)


_METRICS_WARNING_KEYS: set[tuple[str, str, str]] = set()
_METRICS_WARNING_LOCK = threading.Lock()


def _publish_metrics_best_effort(metrics: LiveAvatarMetrics, destination: str) -> bool:
    """Keep optional telemetry failures from terminating the image transport."""
    try:
        metrics.publish_json(destination)
        return True
    except Exception as error:
        key = (str(destination), type(error).__name__, str(error))
        with _METRICS_WARNING_LOCK:
            first_occurrence = key not in _METRICS_WARNING_KEYS
            _METRICS_WARNING_KEYS.add(key)
        if first_occurrence:
            print(f"LiveAvatar metrics disabled for {destination!r}: {error}", file=sys.stderr)
        return False


class DaWastehVRMLiveAvatarLauncher:
    """Non-blocking launcher for the localhost-only browser VRM application."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"port": ("INT", {"default": 8188, "min": 1, "max": 65535})},
            "optional": {
                "model": ("STRING", {"default": "dawasteh-img00031-highrealism-local-v5.vrm"}),
                "follow_framing": ("BOOLEAN", {"default": True}),
                "chroma": ("BOOLEAN", {"default": False}),
                "presentation": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("vrm_live_url",)
    OUTPUT_NODE = True
    FUNCTION = "open"
    CATEGORY = "DaWasteh/Live Avatar"

    def open(
        self,
        port: int = 8188,
        model: str = "dawasteh-img00031-highrealism-local-v5.vrm",
        follow_framing: bool = True,
        chroma: bool = False,
        presentation: bool = False,
    ):
        from urllib.parse import urlencode
        from .vrm_server import app_url

        query = {
            "follow": "1" if follow_framing else "0",
            "chroma": "1" if chroma else "0",
            "present": "1" if presentation else "0",
        }
        if model.strip():
            query["model"] = Path(model.strip()).name
        url = f"{app_url(int(port))}?{urlencode(query)}"
        return {"ui": {"text": [url]}, "result": (url,)}


@dataclass
class LatestFrameSlot:
    """One-element mailbox whose publishers overwrite stale frames."""

    frame: Any = None
    metrics: LiveAvatarMetrics | None = None
    metrics_path: str = ""
    sequence: int = 0
    closed: bool = False
    error: BaseException | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    ready: threading.Condition = field(init=False)

    def __post_init__(self) -> None:
        self.ready = threading.Condition(self.lock)

    def publish(self, frame: Any) -> int:
        with self.ready:
            if self.closed:
                return self.sequence
            self.frame = frame
            self.sequence += 1
            self.ready.notify_all()
            return self.sequence

    def get_after(self, sequence: int, timeout: float) -> tuple[Any, int] | None:
        with self.ready:
            self.ready.wait_for(
                lambda: self.closed or self.error is not None or self.sequence > sequence,
                timeout,
            )
            self._raise_locked()
            if self.sequence <= sequence:
                return None
            return self.frame, self.sequence

    def latest(self) -> tuple[Any, int] | None:
        with self.lock:
            self._raise_locked()
            if self.sequence == 0:
                return None
            return self.frame, self.sequence

    def fail(self, error: BaseException) -> None:
        with self.ready:
            self.error = error
            self.ready.notify_all()

    def raise_if_error(self) -> None:
        with self.lock:
            self._raise_locked()

    def _raise_locked(self) -> None:
        if self.error is not None:
            raise RuntimeError("live-avatar worker failed") from self.error

    def close(self) -> None:
        with self.ready:
            self.closed = True
            self.ready.notify_all()


def square_roi(frame: np.ndarray, offset_x: int = 0, offset_y: int = 0) -> np.ndarray:
    """Return a validated centered square crop with clamped pixel offsets."""

    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] < 3:
        raise ValueError("camera frame must be HxWxC")
    height, width = frame.shape[:2]
    side = min(height, width)
    left = (width - side) // 2 + int(offset_x)
    top = (height - side) // 2 + int(offset_y)
    left = min(max(left, 0), width - side)
    top = min(max(top, 0), height - side)
    return frame[top : top + side, left : left + side, :3]


def rgba_from_rgb_and_mask(rgb: np.ndarray, load_image_mask: np.ndarray) -> np.ndarray:
    """Match JoinImageWithAlpha: output alpha equals ``1 - LoadImage MASK``."""

    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise ValueError("rgb must be HxWx3")
    if load_image_mask.shape != rgb.shape[:2]:
        raise ValueError("mask dimensions must match RGB")
    alpha = np.clip(1.0 - load_image_mask, 0.0, 1.0)[..., None]
    return np.concatenate((np.clip(rgb[..., :3], 0.0, 1.0), alpha), axis=-1)


def composite_rgba_bchw(face_mask: Any, warped: Any, static_background: Any, alpha: Any) -> Any:
    """Blend BCHW tensors and append a B1HW alpha channel."""

    tensors = (face_mask, warped, static_background, alpha)
    if any(getattr(tensor, "ndim", None) != 4 for tensor in tensors):
        raise ValueError("composite inputs must be four-dimensional BCHW tensors")
    if face_mask.shape != warped.shape or warped.shape != static_background.shape:
        raise ValueError("RGB composite tensors must have identical BCHW shapes")
    if face_mask.shape[1] != 3 or alpha.shape[1] != 1:
        raise ValueError("composite expects three RGB channels and one alpha channel")
    if alpha.shape[0] != face_mask.shape[0] or alpha.shape[2:] != face_mask.shape[2:]:
        raise ValueError("alpha dimensions must match the RGB batch and spatial dimensions")
    composite = (face_mask * warped + static_background).clamp(0, 1)
    return __import__("torch").cat((composite, alpha.clamp(0, 1)), dim=1)


def _loaded_liveportrait_nodes() -> Any:
    """Reuse ComfyUI's loaded LivePortraitKJ module instead of duplicating it."""

    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if not module_file or not hasattr(module, "_transform_img_kornia"):
            continue
        path = Path(module_file)
        if path.name == "nodes.py" and path.parent.name == "ComfyUI-LivePortraitKJ":
            return module
    try:
        return importlib.import_module("custom_nodes.ComfyUI-LivePortraitKJ.nodes")
    except ModuleNotFoundError as error:
        if error.name in {
            "custom_nodes",
            "custom_nodes.ComfyUI-LivePortraitKJ",
            "custom_nodes.ComfyUI-LivePortraitKJ.nodes",
        }:
            raise RuntimeError("ComfyUI-LivePortraitKJ must be installed before this node") from error
        raise RuntimeError(f"LivePortraitKJ dependency failed to import: {error.name}") from error


class CaptureWorker:
    def __init__(
        self,
        slot: LatestFrameSlot,
        cam_index: int,
        width: int,
        height: int,
        square_crop: bool,
        offset_x: int,
        offset_y: int,
        mirror: bool,
        backend: str = "auto",
        auto_face_crop: bool = False,
        face_crop_scale: float = 2.0,
        face_crop_smoothing: float = 0.72,
        output_size: tuple[int, int] | None = (256, 256),
    ) -> None:
        self.slot = slot
        self.output_size = output_size
        self.cam_index = cam_index
        self.width = width
        self.height = height
        self.square_crop = square_crop
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.mirror = mirror
        self.backend = backend
        self.auto_face_crop = bool(auto_face_crop)
        self.face_crop_scale = float(face_crop_scale)
        self.face_crop_smoothing = float(face_crop_smoothing)
        self._face_crop_state: np.ndarray | None = None
        self._face_crop_misses = 0
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name="DaWastehLiveAvatarCapture",
            daemon=True,
        )
        self.cap: Any = None
        self.started = False

    def start(self) -> None:
        if self.started:
            raise RuntimeError("capture worker already started")
        self.thread.start()
        self.started = True

    def stop(self, timeout: float = 3.0) -> bool:
        self.stop_event.set()
        self.slot.close()
        if not self.started:
            return True
        self.thread.join(timeout=timeout)
        return not self.thread.is_alive()

    def _tracked_face_roi(self, frame: np.ndarray, cv2: Any, detector: Any) -> np.ndarray:
        """Return a smoothed square face/head ROI, falling back safely after lost tracking."""
        height, width = frame.shape[:2]
        scale = min(1.0, 640.0 / max(width, height))
        detect_frame = frame if scale == 1.0 else cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2GRAY)
        detections = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(detections):
            x, y, face_width, face_height = max(detections, key=lambda item: int(item[2]) * int(item[3]))
            x, y, face_width, face_height = (float(value) / scale for value in (x, y, face_width, face_height))
            target = np.array(
                [x + face_width * 0.5, y + face_height * 0.52, max(face_width, face_height) * self.face_crop_scale],
                dtype=np.float64,
            )
            if self._face_crop_state is None:
                self._face_crop_state = target
            else:
                keep = min(max(self.face_crop_smoothing, 0.0), 0.95)
                self._face_crop_state = keep * self._face_crop_state + (1.0 - keep) * target
            self._face_crop_misses = 0
        elif self._face_crop_state is not None:
            self._face_crop_misses += 1
            if self._face_crop_misses > 30:
                self._face_crop_state = None

        if self._face_crop_state is None:
            return square_roi(frame, self.offset_x, self.offset_y)
        center_x, center_y, requested_side = self._face_crop_state
        side = max(64, min(int(round(requested_side)), width, height))
        left = int(round(center_x - side * 0.5 + self.offset_x))
        top = int(round(center_y - side * 0.5 + self.offset_y))
        left = min(max(left, 0), width - side)
        top = min(max(top, 0), height - side)
        return frame[top : top + side, left : left + side, :3]

    def _run(self) -> None:
        detector = None
        try:
            import cv2

            if self.backend == "DirectShow":
                if not hasattr(cv2, "CAP_DSHOW"):
                    raise RuntimeError("DirectShow was requested but this OpenCV build has no CAP_DSHOW")
                self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
            elif self.backend == "Media Foundation":
                if not hasattr(cv2, "CAP_MSMF"):
                    raise RuntimeError("Media Foundation was requested but this OpenCV build has no CAP_MSMF")
                self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_MSMF)
            else:
                self.cap = cv2.VideoCapture(self.cam_index)
            if not self.cap.isOpened():
                raise RuntimeError(f"could not open webcam index {self.cam_index} with backend {self.backend}")
            if self.auto_face_crop:
                cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
                detector = cv2.CascadeClassifier(cascade_path)
                if detector.empty():
                    raise RuntimeError(f"could not load OpenCV face tracker: {cascade_path}")
            width_set = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            height_set = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            if self.backend != "auto" and (width_set is False or height_set is False):
                raise RuntimeError(f"camera rejected requested {self.width}x{self.height} resolution")
            if self.backend != "auto" and hasattr(self.cap, "get"):
                actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                if actual_width > 0 and actual_height > 0 and (actual_width, actual_height) != (self.width, self.height):
                    raise RuntimeError(f"camera negotiated {actual_width}x{actual_height}, expected {self.width}x{self.height}")
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1000)

            while not self.stop_event.is_set():
                ok, frame = self.cap.read()
                if not ok:
                    raise RuntimeError("failed to capture webcam frame")
                if self.auto_face_crop:
                    frame = self._tracked_face_roi(frame, cv2, detector)
                elif self.square_crop:
                    frame = square_roi(frame, self.offset_x, self.offset_y)
                if self.mirror:
                    frame = cv2.flip(frame, 1)
                if self.output_size is not None:
                    frame = cv2.resize(frame, self.output_size, interpolation=cv2.INTER_AREA)
                self.slot.publish(TimedFrame(frame, capture_time=time.monotonic()))
        except BaseException as error:
            if not self.stop_event.is_set():
                self.slot.fail(error)
        finally:
            if self.cap is not None:
                self.cap.release()
                self.cap = None


class SpoutWorker:
    def __init__(self, slot: LatestFrameSlot, sender_name: str, fps: int, metrics: LiveAvatarMetrics | None = None) -> None:
        self.slot = slot
        self.sender_name = sender_name
        self.delay = 1.0 / fps
        self.metrics = metrics
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name="DaWastehLiveAvatarSpout",
            daemon=True,
        )
        self.sender: Any = None
        self.started = False

    def start(self) -> None:
        if self.started:
            raise RuntimeError("Spout worker already started")
        self.thread.start()
        self.started = True

    def stop(self, timeout: float = 3.0) -> bool:
        self.stop_event.set()
        self.slot.close()
        if not self.started:
            return True
        self.thread.join(timeout=timeout)
        return not self.thread.is_alive()

    def healthy(self) -> bool:
        return self.started and self.thread.is_alive() and not self.stop_event.is_set()

    def _run(self) -> None:
        try:
            if not sys.platform.startswith("win"):
                raise RuntimeError("Spout is only available on Windows")
            import SpoutGL
            from OpenGL import GL

            self.sender = SpoutGL.SpoutSender()
            self.sender.setSenderName(self.sender_name)
            latest = None
            next_tick = time.monotonic()
            last_metrics_publish = 0.0
            while not self.stop_event.is_set():
                wait = max(0.0, next_tick - time.monotonic())
                if self.stop_event.wait(wait):
                    break
                item = self.slot.latest()
                unique = False
                if item is not None:
                    payload, sequence = item
                    unique = sequence != getattr(self, "_sent_sequence", 0)
                    if unique:
                        self._sent_sequence = sequence
                        latest = payload if isinstance(payload, TimedFrame) else TimedFrame(payload)
                if latest is not None:
                    image = np.ascontiguousarray(latest.image, dtype=np.uint8)
                    height, width = image.shape[:2]
                    self.sender.sendImage(image, width, height, GL.GL_RGBA, False, 0)
                    self.sender.setFrameSync(self.sender_name)
                    if self.metrics is not None:
                        now = time.monotonic()
                        self.metrics.presented(unique, latest, now)
                        with self.slot.lock:
                            metrics_path = self.slot.metrics_path
                        if metrics_path and now - last_metrics_publish >= 1.0:
                            _publish_metrics_best_effort(self.metrics, metrics_path)
                            last_metrics_publish = now
                # Advance from the schedule, not from completion: avoid cumulative drift.
                next_tick += self.delay
                if next_tick < time.monotonic() - self.delay:
                    next_tick = time.monotonic() + self.delay
        except BaseException as error:
            if not self.stop_event.is_set():
                self.slot.fail(error)
        finally:
            if self.sender is not None:
                self.sender.releaseSender()
                self.sender = None


_PERSISTENT_SPOUTS: dict[str, tuple[LatestFrameSlot, SpoutWorker]] = {}
_PERSISTENT_SPOUTS_LOCK = threading.Lock()


def _persistent_spout(sender_name: str, fps: int) -> LatestFrameSlot:
    """Return a healthy sender mailbox, replacing failed/dead workers atomically."""
    retired: tuple[LatestFrameSlot, SpoutWorker] | None = None
    with _PERSISTENT_SPOUTS_LOCK:
        existing = _PERSISTENT_SPOUTS.get(sender_name)
        if existing is not None:
            slot, worker = existing
            try:
                slot.raise_if_error()
            except RuntimeError:
                retired = _PERSISTENT_SPOUTS.pop(sender_name)
            else:
                if worker.healthy() and abs(worker.delay - (1.0 / fps)) < 1e-9:
                    return slot
                retired = _PERSISTENT_SPOUTS.pop(sender_name)
        if retired is not None and not retired[1].stop():
            _PERSISTENT_SPOUTS[sender_name] = retired
            raise RuntimeError(
                f"persistent Spout sender {sender_name!r} did not stop; refusing an overlapping replacement"
            )
        metrics = LiveAvatarMetrics()
        metrics.start()
        slot = LatestFrameSlot(metrics=metrics)
        worker = SpoutWorker(slot, sender_name, fps, metrics)
        worker.start()
        _PERSISTENT_SPOUTS[sender_name] = (slot, worker)
        return slot


def _stop_persistent_spouts() -> None:
    with _PERSISTENT_SPOUTS_LOCK:
        workers = list(_PERSISTENT_SPOUTS.values())
        _PERSISTENT_SPOUTS.clear()
    for _, worker in workers:
        try:
            worker.stop()
        except BaseException:
            LOGGER.exception("persistent Spout cleanup failed")


atexit.register(_stop_persistent_spouts)


class DaWastehCachedOpenPose:
    """OpenPose preprocessor that keeps the three annotator models resident."""

    def __init__(self) -> None:
        self._model: Any = None
        self._model_device: str | None = None
        self.openpose_dicts: list[dict[str, Any]] = []

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
            },
            "optional": {
                "detect_hand": (["enable", "disable"], {"default": "enable"}),
                "detect_body": (["enable", "disable"], {"default": "enable"}),
                "detect_face": (["enable", "disable"], {"default": "enable"}),
                "resolution": ("INT", {"default": 512, "min": 64, "max": 16384, "step": 64}),
                "scale_stick_for_xinsr_cn": (["disable", "enable"], {"default": "disable"}),
                "diagnostic_json": (["disable", "enable"], {"default": "disable"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "POSE_KEYPOINT")
    RETURN_NAMES = ("IMAGE", "POSE_KEYPOINT")
    FUNCTION = "estimate_pose"
    CATEGORY = "DaWasteh/Live Avatar"
    DESCRIPTION = (
        "OpenPose body/hand/face preprocessing with persistent model weights. "
        "Use for webcam loops where comfyui_controlnet_aux would reload all three models every frame."
    )

    def _get_model(self) -> Any:
        import comfy.model_management as model_management
        from custom_controlnet_aux.open_pose import OpenposeDetector

        device = model_management.get_torch_device()
        device_key = str(device)
        if self._model is None:
            started = time.perf_counter()
            self._model = OpenposeDetector.from_pretrained().to(device)
            self._model_device = device_key
            LOGGER.info(
                "Cached OpenPose body/hand/face models on %s in %.3f seconds",
                device_key,
                time.perf_counter() - started,
            )
        elif self._model_device != device_key:
            self._model.to(device)
            self._model_device = device_key
        return self._model

    def estimate_pose(
        self,
        image: Any,
        detect_hand: str = "enable",
        detect_body: str = "enable",
        detect_face: str = "enable",
        resolution: int = 512,
        scale_stick_for_xinsr_cn: str = "disable",
        diagnostic_json: str = "disable",
        **_: Any,
    ) -> dict[str, Any]:
        import comfy.utils
        import torch

        model = self._get_model()
        include_hand = detect_hand == "enable"
        include_body = detect_body == "enable"
        include_face = detect_face == "enable"
        xinsr_stick_scaling = scale_stick_for_xinsr_cn == "enable"
        self.openpose_dicts = []
        outputs: list[Any] = []
        progress = comfy.utils.ProgressBar(int(image.shape[0]))

        with torch.inference_mode():
            for tensor_image in image:
                np_image = np.asarray(tensor_image.cpu() * 255.0, dtype=np.uint8)
                pose_image, pose_dict = model(
                    np_image,
                    output_type="np",
                    detect_resolution=int(resolution),
                    include_hand=include_hand,
                    include_body=include_body,
                    include_face=include_face,
                    image_and_json=True,
                    xinsr_stick_scaling=xinsr_stick_scaling,
                )
                outputs.append(torch.from_numpy(pose_image.astype(np.float32) / 255.0))
                self.openpose_dicts.append(pose_dict)
                progress.update(1)

        out = torch.stack(outputs, dim=0)
        result = {"result": (out, self.openpose_dicts)}
        if diagnostic_json == "enable":
            result["ui"] = {"openpose_json": [json.dumps(self.openpose_dicts, separators=(",", ":"))]}
        return result


class DaWastehPersistentSpout:
    """Publish the latest IMAGE continuously so OBS does not lose the sender between prompts."""

    OUTPUT_NODE = True
    RETURN_TYPES = ()
    FUNCTION = "publish"
    CATEGORY = "DaWasteh/Live Avatar"
    DESCRIPTION = (
        "Keeps the latest RGBA frame on a named Spout sender between Run (Instant) prompts. "
        "The sender remains alive until ComfyUI exits."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "images": ("IMAGE",),
                "sender_name": ("STRING", {"default": "ComfyLiveAvatar"}),
                "sender_fps": ("INT", {"default": 30, "min": 1, "max": 60}),
            },
            "optional": {
                "metrics_json_path": ("STRING", {"default": ""}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> float:
        return float("NaN")

    def publish(
        self,
        images: Any,
        sender_name: str,
        sender_fps: int,
        metrics_json_path: str = "",
    ) -> tuple[()]:
        import torch

        if not sys.platform.startswith("win"):
            raise RuntimeError("Persistent Spout output is supported on Windows only")
        if not isinstance(images, torch.Tensor) or images.ndim != 4 or images.shape[0] < 1:
            raise ValueError("images must be a non-empty BHWC tensor")
        frame = images[0].detach().float().clamp(0, 1)
        if frame.shape[-1] not in (3, 4):
            raise ValueError("images must have RGB or RGBA channels")
        transferred = frame.mul(255).round().byte().cpu().numpy()
        if transferred.shape[-1] == 4:
            rgba = np.ascontiguousarray(transferred)
        else:
            alpha = np.full((*transferred.shape[:2], 1), 255, dtype=np.uint8)
            rgba = np.ascontiguousarray(np.concatenate((transferred, alpha), axis=2))
        slot = _persistent_spout(str(sender_name), int(sender_fps))
        produced_at = time.monotonic()
        metrics_path = str(metrics_json_path).strip()
        channel_metrics = getattr(slot, "metrics", None)
        with slot.lock:
            metrics_changed = metrics_path != slot.metrics_path
            slot.metrics_path = metrics_path
        if channel_metrics is not None and metrics_changed:
            channel_metrics.reset(now=produced_at)
        slot.publish(rgba)
        if channel_metrics is not None:
            channel_metrics.produced(now=produced_at)
            if metrics_path:
                _publish_metrics_best_effort(channel_metrics, metrics_path)
        return ()


class DaWastehContinuousLiveAvatar:
    """Face-only experimental live output that blocks ComfyUI until interrupted."""

    OUTPUT_NODE = True
    RETURN_TYPES = ()
    FUNCTION = "run"
    CATEGORY = "DaWasteh/Live Avatar"
    DESCRIPTION = (
        "Face-only continuous LivePortrait sender. Run once normally, then use Interrupt "
        "to stop; never use Run (Instant). It blocks other ComfyUI jobs while active."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "pipeline": ("LIVEPORTRAITPIPE",),
                "crop_info": ("CROPINFO",),
                "source_image": ("IMAGE",),
                "source_mask": ("MASK",),
                "sender_name": ("STRING", {"default": "ComfyLiveAvatarFast"}),
                "sender_fps": ("INT", {"default": 30, "min": 1, "max": 60}),
                "cam_index": ("INT", {"default": 1, "min": 0, "max": 255}),
                "capture_width": ("INT", {"default": 960, "min": 256, "max": 4096}),
                "capture_height": ("INT", {"default": 540, "min": 256, "max": 4096}),
                "square_crop": ("BOOLEAN", {"default": True}),
                "crop_offset_x": ("INT", {"default": 0, "min": -2048, "max": 2048}),
                "crop_offset_y": ("INT", {"default": 0, "min": -2048, "max": 2048}),
                "mirror": ("BOOLEAN", {"default": True}),
                "delta_multiplier": (
                    "FLOAT",
                    {"default": 0.75, "min": 0.1, "max": 2.0, "step": 0.01},
                ),
                "stitching": ("BOOLEAN", {"default": True}),
                "lip_zero": ("BOOLEAN", {"default": False}),
                "lip_zero_threshold": (
                    "FLOAT",
                    {"default": 0.03, "min": 0.001, "max": 1.0, "step": 0.001},
                ),
                "max_frames": ("INT", {"default": 0, "min": 0, "max": 100000}),
                "metrics_json_path": ("STRING", {"default": ""}),
                "capture_backend": (["auto", "DirectShow", "Media Foundation"], {"default": "auto"}),
                "auto_face_crop": ("BOOLEAN", {"default": False}),
                "face_crop_scale": ("FLOAT", {"default": 2.0, "min": 1.2, "max": 4.0, "step": 0.05}),
                "face_crop_smoothing": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 0.95, "step": 0.01}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> float:
        return float("NaN")

    @staticmethod
    def _restore_cfg(cfg: Any, saved: dict[str, Any]) -> None:
        for key in set(vars(cfg)) - set(saved):
            delattr(cfg, key)
        for key, value in saved.items():
            setattr(cfg, key, value)

    def run(
        self,
        pipeline: Any,
        crop_info: dict[str, Any],
        source_image: Any,
        source_mask: Any,
        sender_name: str,
        sender_fps: int,
        cam_index: int,
        capture_width: int,
        capture_height: int,
        square_crop: bool,
        crop_offset_x: int,
        crop_offset_y: int,
        mirror: bool,
        delta_multiplier: float,
        stitching: bool,
        lip_zero: bool,
        lip_zero_threshold: float,
        max_frames: int,
        metrics_json_path: str = "",
        capture_backend: str = "auto",
        auto_face_crop: bool = False,
        face_crop_scale: float = 2.0,
        face_crop_smoothing: float = 0.72,
    ) -> tuple[()]:
        import cv2
        import torch
        import torch.nn.functional as torch_functional
        import comfy.model_management as mm

        if not sys.platform.startswith("win"):
            raise RuntimeError("Continuous Spout output is supported on Windows only")

        kj = _loaded_liveportrait_nodes()
        transform = kj._transform_img_kornia
        cfg = pipeline.live_portrait_wrapper.cfg
        saved_cfg = copy.copy(vars(cfg))
        capture_slot = LatestFrameSlot()
        output_slot = LatestFrameSlot()
        capture = CaptureWorker(
            capture_slot,
            cam_index,
            capture_width,
            capture_height,
            square_crop,
            crop_offset_x,
            crop_offset_y,
            mirror,
            capture_backend,
            auto_face_crop,
            face_crop_scale,
            face_crop_smoothing,
        )
        metrics = LiveAvatarMetrics()
        metrics.start()
        spout = SpoutWorker(output_slot, sender_name, sender_fps, metrics)
        last_metrics_publish = time.monotonic()

        try:
            device = mm.get_torch_device()
            source_rgb = source_image[..., :3].permute(0, 3, 1, 2).contiguous().to(device)
            height, width = source_rgb.shape[2:]

            alpha = (1.0 - source_mask.to(device)).clamp(0, 1).unsqueeze(1)
            if alpha.shape[2:] != (height, width):
                alpha = torch_functional.interpolate(
                    alpha,
                    size=(height, width),
                    mode="bilinear",
                    align_corners=False,
                )

            mask_path = Path(kj.script_directory) / "liveportrait" / "utils" / "resources" / "mask_template.png"
            mask_image = cv2.imread(str(mask_path), cv2.IMREAD_COLOR)
            if mask_image is None:
                raise RuntimeError(f"could not load LivePortrait blend mask: {mask_path}")
            mask_bhwc = torch.from_numpy(mask_image).unsqueeze(0).float().div(255)
            face_mask = transform(
                mask_bhwc,
                crop_info["crop_info_list"][0]["M_c2o"],
                (width, height),
                device,
            ).clamp(0, 1)
            static_background = (1.0 - face_mask) * source_rgb

            cfg.flag_stitching = stitching
            cfg.flag_lip_zero = lip_zero
            cfg.lip_zero_threshold = lip_zero_threshold
            cfg.flag_eye_retargeting = False
            cfg.eyes_retargeting_multiplier = 1.0
            cfg.flag_lip_retargeting = False
            cfg.lip_retargeting_multiplier = 1.0
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
                if sequence > last_capture_sequence + 1: metrics.dropped(sequence - last_capture_sequence - 1)
                last_capture_sequence = sequence
                bgr = captured.image if isinstance(captured, TimedFrame) else captured
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                driving = (
                    torch.from_numpy(rgb)
                    .to(device=device, dtype=torch.float32)
                    .div(255)
                    .unsqueeze(0)
                    .permute(0, 3, 1, 2)
                    .contiguous()
                )
                if cfg.flag_use_half_precision:
                    driving = driving.half()

                out = pipeline.execute(
                    driving,
                    crop_info,
                    None,
                    delta_multiplier,
                    "single_frame",
                    3e-6,
                    "constant",
                )
                if not out.get("out_list") or not out["out_list"][0]:
                    continue
                generated_bhwc = (
                    torch.clamp(out["out_list"][0]["out"], 0, 1)
                    .permute(0, 2, 3, 1)
                    .contiguous()
                )
                warped = transform(
                    generated_bhwc,
                    crop_info["crop_info_list"][0]["M_c2o"],
                    (width, height),
                    device,
                )
                rgba_bchw = composite_rgba_bchw(face_mask, warped, static_background, alpha)
                rgba = rgba_bchw[0].permute(1, 2, 0).mul(255).byte().cpu().numpy()
                produced_at=time.monotonic()
                output_slot.publish(TimedFrame(rgba, capture_time=getattr(captured, "capture_time", None), produced_time=produced_at))
                metrics.produced(now=produced_at)
                if metrics_json_path and time.monotonic() - last_metrics_publish >= 1.0:
                    metrics.publish_json(metrics_json_path)
                    last_metrics_publish = time.monotonic()
                frames += 1
        finally:
            capture_stopped = False
            spout_stopped = False
            try:
                capture_stopped = capture.stop()
            except BaseException:
                LOGGER.exception("webcam worker cleanup failed")
            try:
                spout_stopped = spout.stop()
            except BaseException:
                LOGGER.exception("Spout worker cleanup failed")
            finally:
                if metrics_json_path:
                    try:
                        metrics.publish_json(metrics_json_path)
                    except OSError:
                        LOGGER.exception("could not publish final LiveAvatar metrics")
                self._restore_cfg(cfg, saved_cfg)
            if not capture_stopped:
                LOGGER.error("webcam worker did not stop within the cleanup timeout")
            if not spout_stopped:
                LOGGER.error("Spout worker did not stop within the cleanup timeout")
        return ()
