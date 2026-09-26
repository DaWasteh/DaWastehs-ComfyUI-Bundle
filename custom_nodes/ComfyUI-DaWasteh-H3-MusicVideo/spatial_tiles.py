"""v1.2.6: spatial tiles for video diffusion models (MultiDiffusion, averaged at every step).

WAN 14B is trained at 480p/720p. Re-sampling a 2016x1152 frame in one piece draws detail at the model's native
scale, so the result looks like an enlarged 720p picture. Split into tiles of native size, every tile gets
native-scale detail; the tiles are denoised separately at every model call and their x0 predictions are
blended with linear ramps in the overlaps, so no seams survive the next step (MultiDiffusion). Each tile gets
its own positions (RoPE starts at 0), exactly as if the model rendered a video of the tile size.

The patch sits at ``apply_model`` and therefore composes with ComfyUI's context windows, which slice time one
level above. Tensors in the call that share the latent's spatial size (e.g. the I2V ``c_concat``) are sliced
with the tile; everything else (text, clip vision) is passed through unchanged.
"""
from __future__ import annotations

import math

import torch

import comfy.patcher_extension
from comfy_api.latest import io

CATEGORY = "DaWasteh/MiniMax H3/Video Upscale"
WRAPPER_KEY = "dawasteh_spatial_tiles"
SPATIAL_COMPRESSION = 8  # WAN 2.1 VAE; the tile size in the node is given in pixels


def axis_tiles(size: int, tile: int, overlap: int, multiple: int = 2) -> list[tuple[int, int]]:
    """Evenly spread windows of length `tile` over `size` with at least `overlap` shared cells, starts on `multiple`."""
    if size <= tile:
        return [(0, size)]
    count = math.ceil((size - overlap) / (tile - overlap))
    step = (size - tile) / (count - 1)
    starts = [min(size - tile, int(round(i * step / multiple)) * multiple) for i in range(count)]
    starts[-1] = size - tile
    return [(start, start + tile) for start in starts]


def ramp(length: int, low_edge: bool, high_edge: bool, overlap: int) -> torch.Tensor:
    """1 in the middle, linear ramps of `overlap` cells towards interior tile borders (never 0)."""
    weights = torch.ones(length)
    fade = min(overlap, length // 2)
    if fade > 0:
        up = (torch.arange(fade, dtype=torch.float32) + 0.5) / fade
        if low_edge:
            weights[:fade] = torch.minimum(weights[:fade], up)
        if high_edge:
            weights[-fade:] = torch.minimum(weights[-fade:], up.flip(0))
    return weights


def tile_layout(height: int, width: int, tile_h: int, tile_w: int, overlap: int) -> list[tuple[int, int, int, int]]:
    return [(y0, y1, x0, x1) for (y0, y1) in axis_tiles(height, tile_h, overlap) for (x0, x1) in axis_tiles(width, tile_w, overlap)]


class TileState:
    def __init__(self, tile_h: int, tile_w: int, overlap: int):
        self.tile_h, self.tile_w, self.overlap = tile_h, tile_w, overlap

    def apply_model(self, executor, x, t, c_concat=None, c_crossattn=None, control=None, transformer_options={}, **kwargs):
        height, width = int(x.shape[-2]), int(x.shape[-1])
        tiles = tile_layout(height, width, self.tile_h, self.tile_w, self.overlap)
        if len(tiles) == 1:
            return executor(x, t, c_concat, c_crossattn, control, transformer_options, **kwargs)
        out = None
        total = torch.zeros((height, width), dtype=torch.float32, device=x.device)
        for y0, y1, x0, x1 in tiles:
            def cut(value):
                if torch.is_tensor(value) and value.ndim == x.ndim and tuple(value.shape[-2:]) == (height, width):
                    return value[..., y0:y1, x0:x1]
                return value
            piece = executor(cut(x), t, cut(c_concat), c_crossattn, control, transformer_options,
                             **{key: cut(value) for key, value in kwargs.items()})
            weight = (ramp(y1 - y0, y0 > 0, y1 < height, self.overlap)[:, None]
                      * ramp(x1 - x0, x0 > 0, x1 < width, self.overlap)[None, :]).to(x.device)
            if out is None:
                out = torch.zeros(piece.shape[:-2] + (height, width), dtype=torch.float32, device=piece.device)
            out[..., y0:y1, x0:x1] += piece.float() * weight
            total[y0:y1, x0:x1] += weight
            del piece
        return (out / total).to(x.dtype)

    def prepare_sampling(self, executor, model, noise_shape, conds, *args, **kwargs):
        # Budget VRAM for one tile, not for the whole frame (the context-window wrapper does the same for time).
        shape = list(noise_shape)
        if len(shape) >= 4:
            shape[-2] = min(shape[-2], self.tile_h)
            shape[-1] = min(shape[-1], self.tile_w)
        return executor(model, shape, conds, *args, **kwargs)


class DaWVUSpatialTiles(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWVUSpatialTiles",
            display_name="VU · Räumliche Kacheln für Video-Modelle (MultiDiffusion)",
            category=CATEGORY,
            description=("Denoises large frames in overlapping tiles of the model's native size and blends them at "
                         "every step (MultiDiffusion). Gives native-scale detail at 1080p+ and needs VRAM for one tile "
                         "only. Composes with WAN Context Windows (time) - use both for long, large videos."),
            inputs=[
                io.Model.Input("model"),
                io.Int.Input("tile_width", default=832, min=256, max=4096, step=16,
                             tooltip="Tile width in pixels. WAN 14B: 832 (480p tiles, most detail) or 1280 (720p)."),
                io.Int.Input("tile_height", default=480, min=256, max=4096, step=16, tooltip="Tile height in pixels."),
                io.Int.Input("overlap", default=128, min=0, max=1024, step=16,
                             tooltip="Minimum overlap in pixels; tiles are spread evenly, so the real overlap is often larger."),
            ],
            outputs=[io.Model.Output("model")],
        )

    @classmethod
    def execute(cls, model, tile_width, tile_height, overlap) -> io.NodeOutput:
        cells = lambda px: max(2, int(px) // SPATIAL_COMPRESSION // 2 * 2)  # latent cells, even for the 2x2 patch
        state = TileState(cells(tile_height), cells(tile_width), max(0, int(overlap) // SPATIAL_COMPRESSION))
        model = model.clone()
        model.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.APPLY_MODEL, WRAPPER_KEY, state.apply_model)
        model.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.PREPARE_SAMPLING, WRAPPER_KEY, state.prepare_sampling)
        return io.NodeOutput(model)


TILE_NODES = [DaWVUSpatialTiles]
