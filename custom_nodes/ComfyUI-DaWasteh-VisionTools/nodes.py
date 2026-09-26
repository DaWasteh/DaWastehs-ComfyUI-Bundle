"""v1.2.8 vision tools: mask guard for the Qwen Image 2.1 mask edit, 16-bit depth PNG export, safe meta-batch video loader."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image

import folder_paths
from comfy_api.latest import ComfyExtension, io, ui

from .helpers import expand_pose_boxes, require_mask, reset_stale_meta_batch, to_uint16_gray

CATEGORY = "DaWasteh/vision"


class DaWRequireMask(io.ComfyNode):
    """Stops the prompt with a clear message instead of silently returning the unchanged image."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWRequireMask",
            display_name="DaW Require Painted Mask",
            category=CATEGORY,
            description="Passes image and mask through unchanged. Stops the run with a clear message when (almost) nothing "
                        "is painted: an empty inpaint mask keeps every latent pixel, so the result would silently equal "
                        "the input image. Route the image through this node too, so encoders and VAEs only start after "
                        "the check.",
            inputs=[
                io.Image.Input("image"),
                io.Mask.Input("mask"),
                io.Int.Input("min_pixels", default=16, min=1, max=1_000_000,
                             tooltip="Minimum number of painted pixels (value > 0.5) in the cropped mask."),
            ],
            outputs=[io.Image.Output("image"), io.Mask.Output("mask")],
        )

    @classmethod
    def execute(cls, image, mask, min_pixels) -> io.NodeOutput:
        require_mask(mask.detach().cpu().numpy(), min_pixels)
        return io.NodeOutput(image, mask)


class DaWSaveDepth16(io.ComfyNode):
    """8-bit depth maps band into 256 steps; 3D displacement and compositing want the full float precision."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWSaveDepth16",
            display_name="DaW Save 16-bit Depth PNG",
            category=CATEGORY,
            description="Saves the first channel of each image as a 16-bit greyscale PNG (0..65535) in ComfyUI/output, "
                        "with the workflow in the PNG metadata. Feed a normalised depth render (white = near).",
            is_output_node=True,
            inputs=[
                io.Image.Input("images"),
                io.String.Input("filename_prefix", default="Depth/Depth16"),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
        )

    @classmethod
    def execute(cls, images, filename_prefix) -> io.NodeOutput:
        prefix = filename_prefix.replace("\\", "/")
        if Path(prefix).is_absolute() or ":" in prefix or ".." in prefix.split("/"):
            raise ValueError("filename_prefix must stay inside ComfyUI/output")
        output = folder_paths.get_output_directory()
        height, width = int(images.shape[1]), int(images.shape[2])
        directory, filename, counter, subfolder, _ = folder_paths.get_save_image_path(prefix, output, width, height)
        os.makedirs(directory, exist_ok=True)
        metadata = ui.ImageSaveHelper._create_png_metadata(cls)
        results = []
        for batch_index, frame in enumerate(images):
            gray = to_uint16_gray(frame.detach().cpu().numpy())
            name = f"{filename.replace('%batch_num%', str(batch_index))}_{counter:05}_.png"
            Image.fromarray(gray).save(os.path.join(directory, name), pnginfo=metadata, compress_level=4)
            results.append(ui.SavedResult(name, subfolder, io.FolderType.output))
            counter += 1
        return io.NodeOutput(ui=ui.SavedImages(results))


class DaWPoseBoxes(io.ComfyNode):
    """Person boxes in the pose model's aspect ratio (MMPose top-down crop) instead of a sideways-squeezed crop."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWPoseBoxes",
            display_name="DaW Pose Boxes (3:4 crop)",
            category=CATEGORY,
            description="Grows RT-DETR person boxes around their centre to the 3:4 aspect SDPose runs at (768x1024) plus a "
                        "margin, clipped to the image. SDPose Keypoint Extractor stretches boxes without keeping the "
                        "aspect ratio, so a standing person would be squeezed about 2x sideways.",
            inputs=[
                io.BoundingBox.Input("bboxes", force_input=True),
                io.Image.Input("image"),
                io.Float.Input("scale", default=1.25, min=1.0, max=2.0, step=0.05, tooltip="Margin around the person."),
            ],
            outputs=[io.BoundingBox.Output("bboxes")],
        )

    @classmethod
    def execute(cls, bboxes, image, scale) -> io.NodeOutput:
        return io.NodeOutput(expand_pose_boxes(bboxes, int(image.shape[2]), int(image.shape[1]), 0.75, scale))


def _video_files() -> list[str]:
    directory = folder_paths.get_input_directory()
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    return sorted(folder_paths.filter_files_content_types(files, ["video"])) or ["video.mp4"]


def _has_audio(path: str) -> bool:
    import av

    with av.open(path) as container:
        return bool(container.streams.audio)


class DaWLoadVideoBatches(io.ComfyNode):
    """VHS Load Video with meta batches, safe for silent videos and for the run after a cancelled/failed one."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWLoadVideoBatches",
            display_name="DaW Load Video (Meta-Batch, safe)",
            category=CATEGORY,
            description="Loads a video in original size and frame rate through VideoHelperSuite. With a VHS Meta Batch "
                        "Manager the prompt re-queues itself per batch, so RAM stays bounded for any length. Silent videos "
                        "give no audio (VHS' lazy audio map would fail when ComfyUI scans the linked output), and a run "
                        "after a cancelled or failed one never continues the old video.",
            inputs=[
                io.Combo.Input("video", options=_video_files(), upload=io.UploadType.video),
                io.Custom("VHS_BatchManager").Input("meta_batch", optional=True),
                io.Int.Input("skip_first_frames", default=0, min=0, max=10_000_000,
                             tooltip="Start later: number of frames to skip."),
                io.Int.Input("frame_load_cap", default=0, min=0, max=10_000_000,
                             tooltip="Maximum number of frames to process, 0 = up to the end."),
            ],
            outputs=[io.Image.Output("images"), io.Int.Output("frame_count"), io.Audio.Output("audio"),
                     io.Float.Output("fps")],
            hidden=[io.Hidden.unique_id, io.Hidden.prompt],
        )

    @classmethod
    def validate_inputs(cls, video, **kwargs):
        if not folder_paths.exists_annotated_filepath(video):
            return f"Invalid video file: {video}"
        return True

    @classmethod
    def fingerprint_inputs(cls, video, **kwargs):
        path = folder_paths.get_annotated_filepath(video)
        stat = os.stat(path)
        return (stat.st_mtime_ns, stat.st_size)

    @classmethod
    def execute(cls, video, skip_first_frames, frame_load_cap, meta_batch=None) -> io.NodeOutput:
        import nodes

        loader = nodes.NODE_CLASS_MAPPINGS.get("VHS_LoadVideo")
        if loader is None:
            raise RuntimeError("ComfyUI-VideoHelperSuite (VHS_LoadVideo) is required")
        unique_id = cls.hidden.unique_id
        if reset_stale_meta_batch(meta_batch, cls.hidden.prompt, unique_id):
            logging.info("[DaWasteh VisionTools] closed a meta batch left open by a cancelled or failed run")
        images, count, audio, info = loader().load_video(
            video=video, force_rate=0, custom_width=0, custom_height=0, frame_load_cap=frame_load_cap,
            skip_first_frames=skip_first_frames, select_every_nth=1, format="None", meta_batch=meta_batch,
            unique_id=unique_id)
        if not _has_audio(folder_paths.get_annotated_filepath(video)):
            audio = None
        return io.NodeOutput(images, count, audio, float(info["loaded_fps"]))


class VisionToolsExtension(ComfyExtension):
    async def get_node_list(self):
        return [DaWRequireMask, DaWSaveDepth16, DaWLoadVideoBatches, DaWPoseBoxes]


async def comfy_entrypoint():
    return VisionToolsExtension()
