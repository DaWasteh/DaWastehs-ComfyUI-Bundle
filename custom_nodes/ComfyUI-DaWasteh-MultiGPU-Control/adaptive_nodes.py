"""Adaptive, model-aware image and video loaders for ComfyUI."""
from __future__ import annotations

import hashlib
import os
from typing import Optional

import comfy.utils
import folder_paths
import nodes as core_nodes
from comfy_api.latest import ComfyExtension, Input, InputImpl, Types, io
from typing_extensions import override

from .adaptive_profiles import (
    AUTO_PROFILE,
    DETECTED_OPTIONS,
    FALLBACK_PROFILE,
    PROFILE_OPTIONS,
    QUALITY_SCALES,
    resolve_profile,
    target_dimensions,
)


CATEGORY = "DaWasteh/media"


def _resize_images(images, width: int, height: int):
    if images is None or images.ndim != 4 or images.shape[0] == 0:
        raise ValueError("The selected media contains no decodable image frames")
    if images.shape[2] == width and images.shape[1] == height:
        return images
    method = "area" if width <= images.shape[2] and height <= images.shape[1] else "lanczos"
    return comfy.utils.common_upscale(
        images.movedim(-1, 1), width, height, method, "disabled"
    ).movedim(1, -1)


def _resize_mask(mask, width: int, height: int):
    if mask is None or mask.ndim != 3:
        return mask
    if mask.shape[2] == width and mask.shape[1] == height:
        return mask
    return comfy.utils.common_upscale(
        mask.unsqueeze(1), width, height, "bilinear", "disabled"
    ).squeeze(1)


def _selection(source_width: int, source_height: int, model_profile: str, detected_profile: str, quality: str):
    effective, detected = resolve_profile(model_profile, detected_profile)
    width, height = target_dimensions(source_width, source_height, effective, quality)
    mode = "auto-detected" if model_profile == AUTO_PROFILE and detected else (
        "auto-fallback" if model_profile == AUTO_PROFILE else "manual"
    )
    info = (
        f"{mode}: {effective}; quality={quality}; "
        f"source={source_width}x{source_height}; output={width}x{height}; "
        "crop=disabled"
    )
    return effective, width, height, info


class AdaptiveVideo(Input.Video):
    """Lazy video wrapper that scales frames only when a consumer decodes them."""

    def __init__(self, source: Input.Video, width: int, height: int):
        self._source = source
        self._width = int(width)
        self._height = int(height)

    def get_components(self) -> Types.VideoComponents:
        components = self._source.get_components()
        return Types.VideoComponents(
            images=_resize_images(components.images, self._width, self._height),
            alpha=_resize_images(components.alpha, self._width, self._height) if components.alpha is not None else None,
            audio=components.audio,
            frame_rate=components.frame_rate,
            metadata=components.metadata,
        )

    def get_dimensions(self) -> tuple[int, int]:
        return self._width, self._height

    def get_bit_depth(self) -> int:
        return self._source.get_bit_depth()

    def get_duration(self) -> float:
        return self._source.get_duration()

    def get_frame_count(self) -> int:
        return self._source.get_frame_count()

    def get_frame_rate(self):
        return self._source.get_frame_rate()

    def get_active_trim_window(self) -> tuple[float, float]:
        return self._source.get_active_trim_window()

    def save_to(
        self,
        path,
        format=Types.VideoContainer.AUTO,
        codec=Types.VideoCodec.AUTO,
        metadata: Optional[dict] = None,
        bit_depth: int | None = None,
        crf: float | None = None,
    ):
        video = InputImpl.VideoFromComponents(self.get_components(), bit_depth=self.get_bit_depth())
        return video.save_to(
            path,
            format=format,
            codec=codec,
            metadata=metadata,
            bit_depth=bit_depth,
            crf=crf,
        )

    def as_trimmed(
        self,
        start_time: float | None = None,
        duration: float | None = None,
        strict_duration: bool = False,
    ) -> Input.Video | None:
        normalized_start = 0.0 if start_time is None else float(start_time)
        normalized_duration = 0.0 if duration is None else float(duration)
        trimmed = self._source.as_trimmed(normalized_start, normalized_duration, strict_duration)
        return None if trimmed is None else AdaptiveVideo(trimmed, self._width, self._height)


class DaWAdaptiveLoadImage(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        input_dir = folder_paths.get_input_directory()
        os.makedirs(input_dir, exist_ok=True)
        files = folder_paths.filter_files_content_types(
            [name for name in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, name))],
            ["image"],
        )
        return io.Schema(
            node_id="DaWAdaptiveLoadImage",
            display_name="Adaptive Load Image · Model Resolution",
            category=CATEGORY,
            description=(
                "Detects the connected model in the browser, selects a model-native pixel budget, "
                "and scales without cropping. Choose a profile manually when auto detection is ambiguous."
            ),
            inputs=[
                io.Combo.Input("image", options=sorted(files), upload=io.UploadType.image),
                io.Combo.Input("model_profile", options=PROFILE_OPTIONS, default=AUTO_PROFILE),
                io.Combo.Input("quality", options=list(QUALITY_SCALES), default="Model native (100%)"),
                io.Combo.Input(
                    "detected_profile",
                    options=DETECTED_OPTIONS,
                    default="Not detected",
                    advanced=True,
                    tooltip="Updated automatically from downstream graph connections by the included frontend extension.",
                ),
            ],
            outputs=[
                io.Image.Output("image"),
                io.Mask.Output("mask"),
                io.Int.Output("width"),
                io.Int.Output("height"),
                io.String.Output("model_profile"),
                io.String.Output("info"),
            ],
        )

    @classmethod
    def execute(cls, image: str, model_profile: str, quality: str, detected_profile: str):
        loaded, mask = core_nodes.LoadImage().load_image(image)
        source_height, source_width = int(loaded.shape[1]), int(loaded.shape[2])
        effective, width, height, info = _selection(
            source_width, source_height, model_profile, detected_profile, quality
        )
        output = _resize_images(loaded, width, height)
        output_mask = _resize_mask(mask, width, height)
        print(f"[DaWasteh Adaptive Media] image {info}")
        return io.NodeOutput(output, output_mask, width, height, effective, info)

    @classmethod
    def fingerprint_inputs(cls, image: str, model_profile: str, quality: str, detected_profile: str):
        path = folder_paths.get_annotated_filepath(image)
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(f"|{model_profile}|{quality}|{detected_profile}".encode("utf-8"))
        return digest.hexdigest()

    @classmethod
    def validate_inputs(cls, image: str, **_kwargs):
        return True if folder_paths.exists_annotated_filepath(image) else f"Invalid image file: {image}"


class DaWAdaptiveLoadVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        input_dir = folder_paths.get_input_directory()
        os.makedirs(input_dir, exist_ok=True)
        files = folder_paths.filter_files_content_types(
            [name for name in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, name))],
            ["video"],
        )
        return io.Schema(
            node_id="DaWAdaptiveLoadVideo",
            display_name="Adaptive Load Video · Model Resolution",
            category=CATEGORY,
            description=(
                "Loads video lazily, preserves audio/FPS, and scales decoded frames to the connected "
                "model's resolution without cropping. Manual model and lower draft qualities remain selectable."
            ),
            inputs=[
                io.Combo.Input("file", options=sorted(files), upload=io.UploadType.video),
                io.Combo.Input("model_profile", options=PROFILE_OPTIONS, default=AUTO_PROFILE),
                io.Combo.Input("quality", options=list(QUALITY_SCALES), default="Model native (100%)"),
                io.Combo.Input(
                    "detected_profile",
                    options=DETECTED_OPTIONS,
                    default="Not detected",
                    advanced=True,
                    tooltip="Updated automatically from downstream graph connections by the included frontend extension.",
                ),
            ],
            outputs=[
                io.Video.Output("video"),
                io.Int.Output("width"),
                io.Int.Output("height"),
                io.Float.Output("fps"),
                io.Float.Output("duration"),
                io.String.Output("model_profile"),
                io.String.Output("info"),
            ],
        )

    @classmethod
    def execute(cls, file: str, model_profile: str, quality: str, detected_profile: str):
        path = folder_paths.get_annotated_filepath(file)
        source = InputImpl.VideoFromFile(path)
        source_width, source_height = source.get_dimensions()
        effective, width, height, info = _selection(
            source_width, source_height, model_profile, detected_profile, quality
        )
        video = AdaptiveVideo(source, width, height)
        fps = float(source.get_frame_rate())
        duration = float(source.get_duration())
        print(f"[DaWasteh Adaptive Media] video {info}; fps={fps:.6g}; duration={duration:.3f}s")
        return io.NodeOutput(video, width, height, fps, duration, effective, info)

    @classmethod
    def fingerprint_inputs(cls, file: str, model_profile: str, quality: str, detected_profile: str):
        path = folder_paths.get_annotated_filepath(file)
        stat = os.stat(path)
        return f"{stat.st_mtime_ns}:{stat.st_size}:{model_profile}:{quality}:{detected_profile}"

    @classmethod
    def validate_inputs(cls, file: str, **_kwargs):
        return True if folder_paths.exists_annotated_filepath(file) else f"Invalid video file: {file}"


class DaWAdaptiveMediaExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [DaWAdaptiveLoadImage, DaWAdaptiveLoadVideo]


async def comfy_entrypoint() -> DaWAdaptiveMediaExtension:
    return DaWAdaptiveMediaExtension()
