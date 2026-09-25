"""v1.2.4: MiniMax FastH3 at high resolution on Windows/ROCm.

Measured on the R9700 (1920x1088, extend scene with 209 H3 frames = 127,541 tokens, VSA 10 %, start profile
reserve-vram 4 + VRAM guard 3 GiB; ``docs/H3_MUSIC_VIDEO_V124.md``):

* safetensors maps a checkpoint copy-on-write. Windows charges the whole file to the commit limit at once
  (22 GB FastH3: +20.65 GiB). On this driver every VRAM allocation is charged as well, so FastH3 at 1920x1088
  reached the 103.6 GB commit limit (47 GB RAM + page file) in the first block of an extend scene; hipMalloc
  then fails and PyTorch reports an out-of-memory error. A read-only mapping costs +0.04 GiB.
* Scene 1 has no frozen frames and 175 H3 frames; every extend scene carries 22 more frames (209+), so the
  activations are ~20 % larger. That is why the first part worked and the loop failed.
* The block peak is the VSA attention (+10.7 GiB over the resident weights: 5.1 GiB fused QKV, gate, output).
  The unchunked MLP would be larger (~+12 GiB); in token chunks it drops below the attention.
* Step 2 then failed with "Tried to allocate 5.11 GiB ... 6.79 GiB reserved but unallocated": allocator
  fragmentation. ``max_split_size_mb`` keeps large cached blocks whole, releasing the cache before each step
  starts every step from a clean layout, and an activation reserve moves weights out of VRAM when needed.

Everything here is scoped: the read-only mapping is used by the MV 0 loader only, and the DiT changes only act
inside forwards of a model that carries the wrapper *and* has more than ``LARGE_TOKENS`` tokens. 864x480
(29k tokens) keeps the exact v1.2.2 code path.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import mmap
import os
import struct
import warnings

import torch

import comfy.model_management
import comfy.patcher_extension
import comfy.sd
import comfy.storage
import comfy.utils

TAG = "[DaWasteh H3 highres]"
GIB = 1024 ** 3
LARGE_TOKENS = 65536                    # 864x480x243 = 29k tokens: untouched; 1344x768x209 = 64k: untouched
MLP_CHUNK_TOKENS = 32768
# Measured peak over the resident weights (block start + VSA attention): 13.33 GiB at 127,541 tokens and
# 15.34 GiB at 148,188 tokens (1920x1088, 209 / 243 H3 frames) = 112 kB per token. 1.2 covers fragmentation;
# the first calibration (86.5 kB x 1.35) left 0.8 GiB at 243 frames and hit the guard in step 2.
ACTIVATION_BYTES_PER_TOKEN = 112_000
RESERVE_FACTOR = 1.2
# Off by default: releasing the cache before every step already prevents the fragmentation OOM, while
# max_split_size_mb:512 made a VSA step 1.8x slower (215.9 vs 122.7 s at 127k tokens; oversize blocks are
# re-allocated through hipMalloc on every use). Opt-in for experiments, e.g. DAWASTEH_H3_ALLOC_CONF=max_split_size_mb:512.
ALLOCATOR_SETTINGS = os.environ.get("DAWASTEH_H3_ALLOC_CONF", "").strip()
if ALLOCATOR_SETTINGS.lower() in ("none", "off", "0"):
    ALLOCATOR_SETTINGS = ""
WRAPPER_KEY = "dawasteh_h3_highres"

_ACTIVE: contextvars.ContextVar[bool] = contextvars.ContextVar("dawasteh_h3_highres", default=False)
_STATE = {"patched": False, "allocator": False}


def _log(message: str) -> None:
    logging.info("%s %s", TAG, message)


# ---------------------------------------------------------------------------------------------------------
# Read-only checkpoint mapping
# ---------------------------------------------------------------------------------------------------------

def load_state_dict_readonly(path: str) -> tuple[dict[str, torch.Tensor], dict]:
    """safetensors -> tensors that view a read-only file mapping (no commit charge, pages shared with the cache).

    ComfyUI never writes into CPU weights of a non-dynamic model: loading assigns them, LoRA patches are computed
    on the GPU copy (or as low-VRAM patches) and unpatching restores the original tensor object.
    """
    types = comfy.utils._TYPES
    handle = open(path, "rb")
    view = data = None
    state_dict: dict[str, torch.Tensor] = {}
    try:
        view = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        header_size = struct.unpack("<Q", view[:8])[0]
        header = json.loads(view[8:8 + header_size])
        data = memoryview(view)[8 + header_size:]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="The given buffer is not writable")
            # Sorted like safetensors' keys(): the order decides the VRAM layout, and with it which GEMM kernels
            # run. Header order gave the identical weights but 4e-6 different text-encoder outputs.
            for name in sorted(k for k in header if k != "__metadata__"):
                info = header[name]
                start, end = info["data_offsets"]
                dtype = types[info["dtype"]]
                if end > start:
                    tensor = torch.frombuffer(data[start:end], dtype=dtype).view(info["shape"])
                    tensor.untyped_storage()._dawasteh_mapping = (handle, view, data)
                else:
                    tensor = torch.empty(info["shape"], dtype=dtype)
                state_dict[name] = tensor
    except Exception:
        state_dict.clear()
        for release in (getattr(data, "release", None), getattr(view, "close", None), handle.close):
            if release is not None:
                with contextlib.suppress(Exception):  # a buffer still exported by a tensor keeps its mapping
                    release()
        raise
    comfy.storage.annotate_state_dict(state_dict, path)
    return state_dict, header.get("__metadata__") or {}


def load_diffusion_model_readonly(path: str, model_options: dict | None = None, disable_dynamic: bool = False):
    model_options = dict(model_options or {})
    state_dict, metadata = load_state_dict_readonly(path)
    model = comfy.sd.load_diffusion_model_state_dict(state_dict, model_options=model_options, metadata=metadata,
                                                     disable_dynamic=disable_dynamic)
    if model is None:
        raise RuntimeError(f"Could not detect the diffusion model type of {path}")
    model.cached_patcher_init = (load_diffusion_model_readonly, (path, model_options))
    return model


def load_clip_readonly(path: str, clip_type: str = "stable_diffusion", model_options: dict | None = None):
    """Text encoder from a read-only mapping. The 26 GB H3 encoder alone pushed the commit charge to 97.5 of
    103.6 GB in MV 3 (copy-on-write mapping + its VRAM copy), independent of the video resolution."""
    import folder_paths

    model_options = dict(model_options or {})
    ctype = getattr(comfy.sd.CLIPType, clip_type.upper(), comfy.sd.CLIPType.STABLE_DIFFUSION)
    state_dict, metadata = load_state_dict_readonly(path)
    if model_options.get("custom_operations", None) is None:
        state_dict, metadata = comfy.utils.convert_old_quants(state_dict, model_prefix="", metadata=metadata)
    embeddings = folder_paths.get_folder_paths("embeddings")
    clip = comfy.sd.load_text_encoder_state_dicts([state_dict], embedding_directory=embeddings, clip_type=ctype,
                                                  model_options=model_options)
    clip.patcher.cached_patcher_init = (comfy.sd.load_clip_model_patcher, ([path], embeddings, ctype, model_options))
    return clip


# ---------------------------------------------------------------------------------------------------------
# DiT patches (inactive unless a wrapped forward with many tokens is running)
# ---------------------------------------------------------------------------------------------------------

def _row_runs(row: torch.Tensor):
    """Per-token adaLN row indices -> contiguous (start, stop, index) runs, cached on the tensor.

    Frozen extend frames give the video stream two timesteps; ComfyUI then gathers a [tokens, hidden] fp32
    modulation tensor per call. The frozen frames are the first latent frames, so the rows form 2-3 runs and
    broadcasting one vector per run gives bit-identical results without the gather.
    """
    runs = getattr(row, "_dawasteh_runs", None)
    if runs is None:
        flat = row.reshape(-1)
        change = (torch.nonzero(flat[1:] != flat[:-1]).flatten() + 1).tolist()
        bounds = [0] + change + [flat.numel()]
        runs = False
        if len(bounds) <= 65:
            values = flat[torch.tensor(bounds[:-1], device=flat.device)].tolist()
            runs = [(a, b, int(v)) for a, b, v in zip(bounds[:-1], bounds[1:], values)]
        row._dawasteh_runs = runs
    return runs


def _expand_segments(segments):
    if not _ACTIVE.get():
        return segments
    out = []
    for a, b, row in segments:
        runs = _row_runs(row) if torch.is_tensor(row) else None
        if runs:
            out.extend((a + s, a + e, v) for s, e, v in runs)
        else:
            out.append((a, b, row))
    return out


def install_patches() -> bool:
    """Patch comfy.ldm.minimax.model once; returns False when the upstream structure changed."""
    if _STATE["patched"]:
        return True
    try:
        import comfy.ldm.minimax.model as h3
        scale_shift, gate, mlp_forward = h3._mod_scale_shift, h3._mod_gate, h3.MLP.forward
    except (ImportError, AttributeError) as exc:
        logging.warning("%s MiniMax H3 structure changed (%s); high-resolution patches disabled", TAG, exc)
        return False

    def _mod_scale_shift(h, shift, scale, segments):
        return scale_shift(h, shift, scale, _expand_segments(segments))

    def _mod_gate(x, gate_vecs, other, segments):
        return gate(x, gate_vecs, other, _expand_segments(segments))

    def _mlp(self, x):
        n = x.shape[-2]
        if not _ACTIVE.get() or n <= MLP_CHUNK_TOKENS:
            return mlp_forward(self, x)
        # SwiGLU is row-wise: token chunks cap the ffn*2 intermediate (7.3 GB at 127k tokens) without changing math.
        out = None
        for start in range(0, n, MLP_CHUNK_TOKENS):
            part = mlp_forward(self, x[..., start:start + MLP_CHUNK_TOKENS, :])
            if out is None:
                out = part.new_empty(x.shape[:-1] + part.shape[-1:])
            out[..., start:start + part.shape[-2], :] = part
            del part
        return out

    h3._mod_scale_shift, h3._mod_gate, h3.MLP.forward = _mod_scale_shift, _mod_gate, _mlp
    _STATE["patched"] = True
    return True


# ---------------------------------------------------------------------------------------------------------
# Per-forward memory management
# ---------------------------------------------------------------------------------------------------------

def token_count(video: torch.Tensor, audio: torch.Tensor, context: torch.Tensor | None) -> int:
    t, h, w = video.shape[-3:]
    tokens = t * ((h + 1) // 2) * ((w + 1) // 2) + int(audio.shape[-1])
    if context is not None and context.ndim >= 2:
        tokens += int(context.shape[-2])
    return int(tokens)


def activation_reserve(tokens: int) -> int:
    return int(tokens * ACTIVATION_BYTES_PER_TOKEN * RESERVE_FACTOR)


def _allocator_limit(device: torch.device) -> int:
    free, total = torch.cuda.mem_get_info(device)
    limit = torch.cuda.memory_reserved(device) + free
    try:
        fraction = float(torch.cuda.get_per_process_memory_fraction(device))
    except Exception:
        fraction = 1.0
    if 0.0 < fraction < 1.0:
        limit = min(limit, int(fraction * total))
    return limit


def _prepare_allocator() -> None:
    if _STATE["allocator"] or not ALLOCATOR_SETTINGS:
        return
    _STATE["allocator"] = True
    try:
        setter = getattr(torch._C, "_accelerator_setAllocatorSettings", None) or torch.cuda.memory._set_allocator_settings
        setter(ALLOCATOR_SETTINGS)
        _log(f"allocator: {ALLOCATOR_SETTINGS} (large cached blocks stay whole for the 5 GiB QKV buffers)")
    except Exception as exc:  # pragma: no cover - depends on the torch build
        logging.warning("%s could not set %s: %s", TAG, ALLOCATOR_SETTINGS, exc)


def ensure_activation_reserve(diffusion_model, device: torch.device, tokens: int) -> int:
    """Release the allocator cache and, if the VRAM left beside the resident weights is below the reserve,
    move weights to the offload device (they are streamed per layer like any partially loaded model)."""
    comfy.model_management.soft_empty_cache()
    need = activation_reserve(tokens)
    available = _allocator_limit(device) - torch.cuda.memory_allocated(device)
    if available >= need:
        return 0
    shortfall = need - available
    for loaded in list(comfy.model_management.current_loaded_models):
        patcher = loaded.model
        if getattr(getattr(patcher, "model", None), "diffusion_model", None) is diffusion_model:
            freed = patcher.partially_unload(patcher.offload_device, shortfall)
            comfy.model_management.soft_empty_cache()
            _log(f"{tokens} tokens need {need / GIB:.1f} GiB for activations, {available / GIB:.1f} GiB were free: "
                 f"moved {freed / GIB:.2f} GiB of weights out of VRAM")
            return int(freed)
    return 0


def _wrapper(executor, x, timestep, context, transformer_options, **kwargs):
    video, audio = x[0], x[1]
    if video.device.type != "cuda":
        return executor(x, timestep, context, transformer_options, **kwargs)
    tokens = token_count(video, audio, context)
    if tokens <= LARGE_TOKENS or not install_patches():
        return executor(x, timestep, context, transformer_options, **kwargs)
    _prepare_allocator()
    ensure_activation_reserve(executor.class_obj, video.device, tokens)
    token = _ACTIVE.set(True)
    try:
        return executor(x, timestep, context, transformer_options, **kwargs)
    finally:
        _ACTIVE.reset(token)


def attach(model):
    """Clone of ``model`` whose H3 forwards manage memory for high resolutions."""
    patched = model.clone()
    patched.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL, WRAPPER_KEY, _wrapper)
    return patched
