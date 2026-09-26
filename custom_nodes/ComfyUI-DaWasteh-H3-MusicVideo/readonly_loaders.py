"""v1.2.6: memory-friendly drop-ins for UNETLoader and CLIPLoader (read-only file mapping).

On this Windows/ROCm system safetensors maps a checkpoint copy-on-write and Windows charges the whole file to the
commit limit (v1.2.4, h3_highres.py). A WAN 2.2 14B upscale run with the core loaders peaked at 90.7 of 105.4 GB
commit: the 14.3 GB model file and the 6.7 GB UMT5 file are charged on top of their VRAM copies. The read-only
mapping from h3_highres costs almost nothing and gives bit-identical weights (keys sorted like safetensors).
"""
from __future__ import annotations

import torch

import folder_paths
from comfy_api.latest import io

from . import h3_highres

CATEGORY = "DaWasteh/MiniMax H3/Video Upscale"
WEIGHT_DTYPES = ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"]


def _clip_types() -> list[str]:
    import nodes
    return list(nodes.CLIPLoader.INPUT_TYPES()["required"]["type"][0])


class DaWVUReadOnlyUNETLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWVUReadOnlyUNETLoader",
            display_name="VU · Diffusion-Modell laden (RAM-schonend)",
            category=CATEGORY,
            description=("Like 'Load Diffusion Model', but the file is mapped read-only: Windows does not charge the whole "
                         "checkpoint to the commit limit (WAN 14B: ~14 GB less)."),
            inputs=[
                io.Combo.Input("unet_name", options=folder_paths.get_filename_list("diffusion_models")),
                io.Combo.Input("weight_dtype", options=WEIGHT_DTYPES, default="default", advanced=True),
            ],
            outputs=[io.Model.Output("model")],
        )

    @classmethod
    def execute(cls, unet_name, weight_dtype) -> io.NodeOutput:
        options = {}
        if weight_dtype in ("fp8_e4m3fn", "fp8_e4m3fn_fast"):
            options["dtype"] = torch.float8_e4m3fn
            if weight_dtype == "fp8_e4m3fn_fast":
                options["fp8_optimizations"] = True
        elif weight_dtype == "fp8_e5m2":
            options["dtype"] = torch.float8_e5m2
        path = folder_paths.get_full_path_or_raise("diffusion_models", unet_name)
        return io.NodeOutput(h3_highres.load_diffusion_model_readonly(path, options))


class DaWVUReadOnlyCLIPLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWVUReadOnlyCLIPLoader",
            display_name="VU · Textencoder laden (RAM-schonend)",
            category=CATEGORY,
            description=("Like 'Load CLIP', but the file is mapped read-only (UMT5-XXL fp8: ~6.7 GB less commit charge)."),
            inputs=[
                io.Combo.Input("clip_name", options=folder_paths.get_filename_list("text_encoders")),
                io.Combo.Input("type", options=_clip_types(), default="wan"),
                io.Combo.Input("device", options=["default", "cpu"], default="default", advanced=True),
            ],
            outputs=[io.Clip.Output("clip")],
        )

    @classmethod
    def execute(cls, clip_name, type, device) -> io.NodeOutput:
        options = {}
        if device == "cpu":
            options["load_device"] = options["offload_device"] = torch.device("cpu")
        path = folder_paths.get_full_path_or_raise("text_encoders", clip_name)
        return io.NodeOutput(h3_highres.load_clip_readonly(path, type, options))


READONLY_NODES = [DaWVUReadOnlyUNETLoader, DaWVUReadOnlyCLIPLoader]
