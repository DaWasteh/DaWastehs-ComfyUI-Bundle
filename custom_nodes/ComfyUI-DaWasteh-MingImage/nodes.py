"""v1.2.9 Ming Image nodes: official reference buckets, the official prompt rewriters through the local Qwen3.8 GGUF,
and layer-decomposition output handling. Sampling itself runs on ComfyUI's native Ming Image support."""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from comfy_api.latest import ComfyExtension, io

from .helpers import (ALPHA_MIN_SHARE, MAX_LAYERS, alpha_coverage, alpha_or_mask, bucket_size, composite_layers,
                      first_accepted, over_checkerboard, resolve_prompt, split_layer_frames)

CATEGORY = "DaWasteh/ming image"
TAG = "[DaWasteh Ming]"
PROMPTS = Path(__file__).resolve().parent / "prompts"
BACKEND = Path(__file__).resolve().parent.parent / "ComfyUI-DaWasteh-H3-MusicVideo" / "llm_backend.py"
TASKS = ["design", "transparent", "layers"]


def _backend():
    """The llama.cpp helper of the H3-MusicVideo pack (same GGUF, server binary and GPU as the MV 2 prompt writer)."""
    name = "dawasteh_mingimage_llm_backend"
    if name in sys.modules:
        return sys.modules[name]
    if not BACKEND.is_file():
        raise FileNotFoundError(f"{BACKEND} fehlt: der Prompt-Writer nutzt llm_backend.py aus ComfyUI-DaWasteh-H3-MusicVideo "
                                "(installiert der Bundle-Updater).")
    spec = importlib.util.spec_from_file_location(name, BACKEND)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[name] = module
    return module


def _llm_available(backend) -> bool:
    server = os.environ.get(backend.ENV_SERVER, "").strip().strip('"')
    return bool(backend.configured_gguf() and server and Path(server).is_file())


def _to_numpy(image: torch.Tensor) -> np.ndarray:
    return image.detach().float().cpu().numpy()


def _to_tensor(array: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(np.ascontiguousarray(array, dtype=np.float32))


class DaWMingReferenceSize(io.ComfyNode):
    """Official Ming reference preprocessing: nearest aspect bucket, bilinear resize without cropping."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMingReferenceSize",
            display_name="DaW Ming Reference Size",
            category=CATEGORY,
            description="Resizes the image to the official Ming Image working size: the entry of the 1024 (or 512) "
                        "bucket table whose height/width ratio is closest to the image, bilinear, no crop. Width and "
                        "height feed the empty latent, so the output has the reference's framing. Alpha is kept.",
            inputs=[
                io.Image.Input("image"),
                io.Combo.Input("bucket", options=["1024", "512"], default="1024",
                               tooltip="1024 = official quality setting (edit and layers); 512 = faster layer preview."),
            ],
            outputs=[io.Image.Output("image"), io.Int.Output("width"), io.Int.Output("height")],
        )

    @classmethod
    def execute(cls, image, bucket) -> io.NodeOutput:
        height, width = bucket_size(int(image.shape[1]), int(image.shape[2]), int(bucket))
        frames = []
        for frame in _to_numpy(image):
            channels = frame.shape[-1]
            pixels = (np.clip(frame, 0.0, 1.0) * 255.0).round().astype(np.uint8)
            mode = "RGBA" if channels == 4 else "RGB"
            resized = Image.fromarray(pixels[..., :4] if channels == 4 else pixels[..., :3], mode).resize(
                (width, height), Image.Resampling.BILINEAR)
            frames.append(np.asarray(resized, dtype=np.float32) / 255.0)
        return io.NodeOutput(_to_tensor(np.stack(frames)), width, height)


class DaWMingPromptWriter(io.ComfyNode):
    """Runs inclusionAI's released prompt rewriters with the local Qwen3.8 27B GGUF (llama.cpp on the second GPU)."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMingPromptWriter",
            display_name="DaW Ming Prompt Writer (Qwen3.8 GGUF)",
            category=CATEGORY,
            description="design / transparent: the official text-to-image rewriter turns a short request into the "
                        "Figma-style JSON caption Ming Image was trained on (transparent adds the official RGBA "
                        "prefix). layers: the official guided prompt turns a rough plan plus the image into the "
                        "per-layer specification; 'layers' outputs the count the latent needs. The GGUF runs through "
                        "llama.cpp from the start profile (same as the MV 2 prompt writer) and is stopped afterwards. "
                        "enhance off, or no GGUF configured: the text is used as it is.",
            inputs=[
                io.Combo.Input("task", options=TASKS, default="design"),
                io.String.Input("text", multiline=True, default="",
                                tooltip="design/transparent: what to create. layers: optional rough plan (one line per "
                                        "layer, front-most first); empty = only the layer count."),
                io.Boolean.Input("enhance", default=True, tooltip="Let Qwen3.8 27B write the prompt (official pipeline)."),
                io.Int.Input("layers", default=4, min=1, max=MAX_LAYERS,
                             tooltip="layers: number of layers when the plan does not state one."),
                io.Int.Input("seed", default=0, min=0, max=2**31 - 1, control_after_generate=False),
                io.Int.Input("max_tokens", default=4096, min=256, max=6144, advanced=True),
                io.Image.Input("image", optional=True, tooltip="layers: the flattened design (the enhancer looks at it)."),
                io.Int.Input("width", optional=True, default=0, min=0, max=16384, force_input=True,
                             tooltip="design/transparent: canvas width, so the caption matches the real format."),
                io.Int.Input("height", optional=True, default=0, min=0, max=16384, force_input=True),
            ],
            outputs=[io.String.Output("prompt"), io.Int.Output("layers")],
        )

    @classmethod
    def execute(cls, task, text, enhance, layers, seed, max_tokens, image=None, width=0, height=0) -> io.NodeOutput:
        if task == "layers" and enhance and image is None:
            logging.warning("%s layers: no image connected, the plan is used without the enhancer", TAG)

        def rewrite(user, system, accept):
            return cls._rewrite(user, system, image if task == "layers" else None, seed, max_tokens, accept)

        prompt, count = resolve_prompt(
            task, text, enhance, layers, rewrite=rewrite, has_image=image is not None, width=width, height=height,
            t2i_system=(PROMPTS / "t2i_rewriter_system_prompt.txt").read_text(encoding="utf-8"),
            layer_template=(PROMPTS / "layer_guided_prompt.txt").read_text(encoding="utf-8"))
        return io.NodeOutput(prompt, count)

    @staticmethod
    def _rewrite(user, system, image, seed, max_tokens, accept):
        """Start the GGUF server for this node run only; None = no LLM configured or no usable answer."""
        try:
            backend = _backend()
        except FileNotFoundError as error:
            logging.warning("%s %s", TAG, error)
            return None
        if not _llm_available(backend):
            logging.warning("%s no GGUF/llama-server in the start profile (%s, %s): prompt used without the enhancer",
                            TAG, backend.ENV_MODEL, backend.ENV_SERVER)
            return None
        with backend.LlamaServer(backend.configured_gguf()) as server:
            answer, rejected = first_accepted(
                lambda attempt_seed: server.generate(user, image=image, max_length=int(max_tokens), temperature=0.7,
                                                     seed=attempt_seed, system_prompt=system or ""),
                accept, seed)
        for text in rejected:
            logging.warning("%s enhancer answer rejected (%d characters, ends with %r)", TAG, len(text), text[-160:])
        if answer is None:
            logging.warning("%s enhancer gave no usable answer, prompt used without the enhancer", TAG)
        else:
            logging.info("%s enhancer answer: %d characters", TAG, len(answer))
        return answer


class DaWMingLayerSplit(io.ComfyNode):
    """Decoded layer frames -> the transparent layers, the model's composite and a back-to-front re-composite."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMingLayerSplit",
            display_name="DaW Ming Layer Split",
            category=CATEGORY,
            description="Input: the decoded frames of a Ming Image Layer latent (composite + layers, one image per "
                        "frame via LatentCutToBatch t/1). Outputs the RGBA layers (1 = front-most, last = background), "
                        "the model's composite, the layers stacked back to front on white (compare it with the input) "
                        "and a preview sheet with every layer on a checkerboard.",
            inputs=[io.Image.Input("frames")],
            outputs=[io.Image.Output("layers"), io.Image.Output("composite"), io.Image.Output("recomposed"),
                     io.Image.Output("sheet"), io.Int.Output("count")],
        )

    @classmethod
    def execute(cls, frames) -> io.NodeOutput:
        composite, layers = split_layer_frames(_to_numpy(frames))
        recomposed = composite_layers(layers)
        sheet = _sheet([over_checkerboard(layer) for layer in layers])
        logging.info("%s %d layers, transparent share per layer: %s", TAG, len(layers),
                     ", ".join(f"{alpha_coverage(layer):.2f}" for layer in layers))
        return io.NodeOutput(_to_tensor(layers), _to_tensor(composite[None, ..., :3]), _to_tensor(recomposed[None]),
                             _to_tensor(sheet[None]), int(len(layers)))


class DaWMingAlphaFallback(io.ComfyNode):
    """Real cutouts every time: Ming's alpha when it made one, else the background-removal mask (evaluated lazily)."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMingAlphaFallback",
            display_name="DaW Ming Alpha Fallback",
            category=CATEGORY,
            description="Ming Image writes real transparency only in some runs (it often paints white or a fake "
                        "checkerboard). Keeps Ming's alpha when at least min_share of the image is transparent; "
                        "otherwise the connected foreground mask (e.g. Remove Background / BiRefNet) becomes the alpha. "
                        "The mask branch is lazy: the removal model only runs when it is needed.",
            inputs=[
                io.Image.Input("images", tooltip="Decoded RGBA images from the Ming VAE."),
                io.Float.Input("min_share", default=ALPHA_MIN_SHARE, min=0.0, max=1.0, step=0.005,
                               tooltip="Transparent share (alpha < 0.05) from which Ming's own alpha is kept."),
                io.Mask.Input("mask", optional=True, lazy=True, tooltip="Foreground mask, 1 = subject."),
            ],
            outputs=[io.Image.Output("images"), io.String.Output("alpha_source")],
        )

    @classmethod
    def check_lazy_status(cls, images, min_share, mask=None):
        if mask is None and any(alpha_coverage(frame) < min_share for frame in _to_numpy(images)):
            return ["mask"]
        return []

    @classmethod
    def execute(cls, images, min_share, mask=None) -> io.NodeOutput:
        masks = None if mask is None else mask.detach().float().cpu().numpy()
        frames, sources = [], []
        for index, frame in enumerate(_to_numpy(images)):
            frame_mask = None if masks is None else masks[min(index, len(masks) - 1)]
            rgba, source = alpha_or_mask(frame, frame_mask, min_share)
            frames.append(rgba)
            sources.append(source)
        summary = ", ".join(sources)
        logging.info("%s alpha source: %s", TAG, summary)
        return io.NodeOutput(_to_tensor(np.stack(frames)), summary)


class DaWMingCheckerboard(io.ComfyNode):
    """RGBA preview: transparency becomes a visible checkerboard (the saved PNG keeps the real alpha)."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWMingCheckerboard",
            display_name="DaW Ming Alpha Checkerboard",
            category=CATEGORY,
            description="Composites RGBA images over a grey checkerboard for previews and comparisons. RGB input passes "
                        "through. Save the original image to keep the transparency.",
            inputs=[io.Image.Input("images")],
            outputs=[io.Image.Output("preview")],
        )

    @classmethod
    def execute(cls, images) -> io.NodeOutput:
        frames = [over_checkerboard(frame) for frame in _to_numpy(images)]
        return io.NodeOutput(_to_tensor(np.stack(frames)))


def _sheet(tiles: list[np.ndarray], tile: int = 512, columns: int = 3) -> np.ndarray:
    """Grid of RGB tiles (longest side `tile`) with 8 px white gaps."""
    thumbs = []
    for array in tiles:
        pixels = Image.fromarray((np.clip(array, 0, 1) * 255).round().astype(np.uint8))
        pixels.thumbnail((tile, tile), Image.Resampling.LANCZOS)
        thumbs.append(np.asarray(pixels, dtype=np.float32) / 255.0)
    columns = min(columns, len(thumbs))
    rows = -(-len(thumbs) // columns)
    cell_h = max(t.shape[0] for t in thumbs)
    cell_w = max(t.shape[1] for t in thumbs)
    gap = 8
    sheet = np.ones((rows * cell_h + (rows - 1) * gap, columns * cell_w + (columns - 1) * gap, 3), dtype=np.float32)
    for index, thumb in enumerate(thumbs):
        r, c = divmod(index, columns)
        y, x = r * (cell_h + gap), c * (cell_w + gap)
        sheet[y:y + thumb.shape[0], x:x + thumb.shape[1]] = thumb
    return sheet


class MingImageToolsExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [DaWMingReferenceSize, DaWMingPromptWriter, DaWMingLayerSplit, DaWMingAlphaFallback, DaWMingCheckerboard]


async def comfy_entrypoint() -> MingImageToolsExtension:
    return MingImageToolsExtension()
