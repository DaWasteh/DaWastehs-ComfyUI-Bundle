"""Read-only safetensors loading for every ComfyUI loader (v1.3.1).

On this Windows/ROCm setup ``safetensors.safe_open`` maps a file copy-on-write, and Windows charges the whole file to
the system commit the moment it is mapped (measured for v1.2.4: FastH3 22 GB -> +20.65 GiB). Every VRAM allocation is
charged to the commit as well. FLUX.2 dev FP8 mixed loads 35.5 GB of diffusion model plus 35.6 GB of Mistral text
encoder: one run pushed the system commit to 159 GiB on a 47 GB RAM machine, the range in which Windows crashed
(bug check 0x101) during the v1.3.1 gallery runs.

A plain read-only mapping (``mmap.ACCESS_READ``) plus ``torch.frombuffer`` costs no commit, the pages stay shared with
the file cache. The tensors hold exactly the same bytes, and the keys come sorted like ``safe_open(...).keys()``, so the
model receives identical weights in identical order (the order decides the VRAM layout and with it the GEMM kernels;
for v1.2.4 the sorted read-only loader gave bit-identical outputs). ComfyUI never writes into CPU weights of a loaded
model: loading assigns them, LoRA patches are computed on the GPU copy or as low-VRAM patches, unpatching restores the
original tensor object. Any error falls back to ComfyUI's own loader.

Environment:
    DAWASTEH_READONLY_SAFETENSORS=0         use ComfyUI's loader for everything
    DAWASTEH_READONLY_SAFETENSORS_MIN_GIB=1 files below this size keep ComfyUI's loader (default 1 GiB)
"""
from __future__ import annotations

import contextlib
import json
import logging
import mmap
import os
import struct
import sys
import warnings

GIB = 1024 ** 3
_STATE: dict = {}


def enabled() -> bool:
    return os.environ.get("DAWASTEH_READONLY_SAFETENSORS", "1").strip().lower() not in ("0", "false", "no", "off")


def min_bytes() -> int:
    try:
        return int(float(os.environ.get("DAWASTEH_READONLY_SAFETENSORS_MIN_GIB", "1")) * GIB)
    except ValueError:
        return GIB


def load_readonly(path: str, types: dict) -> tuple[dict, dict | None]:
    """safetensors -> (state dict of tensors viewing a read-only file mapping, metadata)."""
    import torch

    handle = open(path, "rb")
    view = data = None
    state_dict: dict = {}
    try:
        view = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        header_size = struct.unpack("<Q", view[:8])[0]
        header = json.loads(view[8:8 + header_size])
        data = memoryview(view)[8 + header_size:]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="The given buffer is not writable")
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
    return state_dict, header.get("__metadata__")


def _wants_readonly(ckpt, device, utils, memory_management) -> bool:
    if not isinstance(ckpt, (str, os.PathLike)) or not str(ckpt).lower().endswith((".safetensors", ".sft")):
        return False
    if device is not None and getattr(device, "type", str(device)) != "cpu":
        return False
    if getattr(memory_management, "aimdo_enabled", False) or getattr(utils, "DISABLE_MMAP", False):
        return False
    try:
        return os.path.getsize(ckpt) >= min_bytes()
    except OSError:
        return False


def _module_attr(module, name: str):
    """Read a module global without triggering module-level __getattr__ hooks (torch._classes raises there)."""
    try:
        return vars(module).get(name)
    except TypeError:  # None placeholders in sys.modules
        return None


def apply() -> int:
    """Route ComfyUI's load_torch_file through the read-only loader. Returns the number of patched references."""
    if not enabled():
        logging.info("[DaWasteh read-only load] disabled via DAWASTEH_READONLY_SAFETENSORS=0")
        return 0
    import comfy.memory_management
    import comfy.utils

    original = comfy.utils.load_torch_file
    if getattr(original, "dawasteh_readonly", False):
        return 0
    types = getattr(comfy.utils, "_TYPES", None)
    if not types:
        logging.warning("[DaWasteh read-only load] comfy.utils._TYPES missing, ComfyUI's loader stays")
        return 0

    def load_torch_file(ckpt, safe_load=False, device=None, return_metadata=False):
        if _wants_readonly(ckpt, device, comfy.utils, comfy.memory_management):
            try:
                sd, metadata = load_readonly(os.fspath(ckpt), types)
            except Exception as exc:  # broken header etc.: ComfyUI's loader raises its own readable error
                logging.warning("[DaWasteh read-only load] %s: %s; using ComfyUI's loader", ckpt, exc)
            else:
                _STATE["files"] = _STATE.get("files", 0) + 1
                annotate = getattr(getattr(comfy, "storage", None), "annotate_state_dict", None)
                if annotate is not None:
                    annotate(sd, ckpt)
                return (sd, metadata) if return_metadata else sd
        return original(ckpt, safe_load=safe_load, device=device, return_metadata=return_metadata)

    load_torch_file.dawasteh_readonly = True
    load_torch_file.dawasteh_original = original

    patched = 0
    for module in list(sys.modules.values()):  # also modules that did "from .utils import load_torch_file"
        if _module_attr(module, "load_torch_file") is original:
            with contextlib.suppress(Exception):
                setattr(module, "load_torch_file", load_torch_file)
                patched += 1
    logging.info("[DaWasteh read-only load] safetensors >= %.1f GiB load read-only (no commit charge), %d references",
                 min_bytes() / GIB, patched)
    return patched
