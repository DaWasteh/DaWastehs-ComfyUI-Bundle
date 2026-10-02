"""Batched linear algebra in ComfyUI's gaussian-splat nodes works on ROCm for any number of splats (v1.3.2).

``comfy_extras/nodes_gaussian_splat.py`` (Render Splat, Splat to Mesh, Transform Splat) inverts one 3x3 covariance per
gaussian in a single batched ``torch.linalg.inv`` call. On this ROCm stack (PyTorch 2.13 + ROCm 10.1, RDNA4) the batched
solver kernel is launched with one grid block per matrix and fails above 65 535 matrices with
``hipErrorInvalidConfiguration`` (measured 2026-10-02: 60 000 ok, 70 000 fails). A TripoSplat reconstruction has 262 144
gaussians by default, so every render of it died in ``Render Splat``; the same limit applies to the batched ``eigh`` and
``det`` of Transform Splat. The patch gives those modules a ``torch`` whose ``linalg.inv``/``eigh``/``det`` split a large
batch into chunks of 32 768 matrices and concatenate the results. Same numbers, same dtype, same device; CUDA builds are
left untouched.

Environment:
    DAWASTEH_SPLAT_LINALG_FIX=0   leave ComfyUI's behaviour unchanged
    DAWASTEH_SPLAT_LINALG_CHUNK   matrices per kernel launch (default 32768)
"""
from __future__ import annotations

import logging
import os
import sys

MARKERS = ("RenderSplat", "SplatToMesh", "TransformSplat")
DEFAULT_CHUNK = 32768
CHUNKED = ("inv", "eigh", "det", "cholesky", "pinv")


def enabled() -> bool:
    return os.environ.get("DAWASTEH_SPLAT_LINALG_FIX", "1").strip().lower() not in ("0", "false", "no", "off")


def chunk_size() -> int:
    try:
        return max(1, int(os.environ.get("DAWASTEH_SPLAT_LINALG_CHUNK", DEFAULT_CHUNK)))
    except ValueError:
        return DEFAULT_CHUNK


def needs_chunking(tensor, chunk: int) -> bool:
    """True for a batch of matrices on a HIP device that is larger than one kernel launch can take."""
    if getattr(tensor, "ndim", 0) < 3 or not getattr(tensor, "is_cuda", False):
        return False
    batch = 1
    for size in tensor.shape[:-2]:
        batch *= int(size)
    return batch > chunk


def chunked(function, tensor, chunk: int, *args, **kwargs):
    """Apply ``function`` to ``tensor`` in batches of at most ``chunk`` matrices; tuples (eigh) are concatenated per item."""
    import torch

    lead = tuple(tensor.shape[:-2])
    flat = tensor.reshape(-1, *tensor.shape[-2:])
    parts = [function(piece, *args, **kwargs) for piece in flat.split(chunk)]
    if isinstance(parts[0], tuple):
        return tuple(torch.cat([part[i] for part in parts]).reshape(*lead, *parts[0][i].shape[1:]) for i in range(len(parts[0])))
    return torch.cat(parts).reshape(*lead, *parts[0].shape[1:])


class ChunkedLinalg:
    """``torch.linalg`` with batch-chunked solvers; everything else is passed through."""

    dawasteh_patch = True

    def __init__(self, linalg, chunk: int):
        self._linalg = linalg
        self._chunk = chunk

    def __getattr__(self, name):
        attr = getattr(self._linalg, name)
        if name not in CHUNKED:
            return attr

        def call(tensor, *args, **kwargs):
            if needs_chunking(tensor, self._chunk):
                return chunked(attr, tensor, self._chunk, *args, **kwargs)
            return attr(tensor, *args, **kwargs)

        return call


class TorchProxy:
    """The ``torch`` module as seen by the splat nodes: identical except for ``linalg``."""

    dawasteh_patch = True

    def __init__(self, torch_module, chunk: int):
        self._torch = torch_module
        self.linalg = ChunkedLinalg(torch_module.linalg, chunk)

    def __getattr__(self, name):
        return getattr(self._torch, name)


def _module_attr(module, name: str):
    """Read a module global without triggering module-level __getattr__ hooks (torch._classes raises there)."""
    try:
        return vars(module).get(name)
    except TypeError:  # None placeholders in sys.modules
        return None


def is_rocm() -> bool:
    try:
        import torch
    except Exception:
        return False
    return bool(getattr(getattr(torch, "version", None), "hip", None))


def apply(force: bool = False) -> int:
    """Patch every loaded copy of the core gaussian-splat module. Returns the number of patched modules."""
    if not enabled():
        logging.info("[DaWasteh splat linalg] disabled via DAWASTEH_SPLAT_LINALG_FIX=0")
        return 0
    if not force and not is_rocm():
        return 0
    import torch

    chunk = chunk_size()
    patched = 0
    for module in list(sys.modules.values()):
        if not any(_module_attr(module, marker) is not None for marker in MARKERS):
            continue
        current = _module_attr(module, "torch")
        if current is None:
            continue
        if not getattr(current, "dawasteh_patch", False):
            setattr(module, "torch", TorchProxy(current if current is torch else torch, chunk))
        patched += 1
    if patched:
        logging.info("[DaWasteh splat linalg] Render Splat / Splat to Mesh invert their covariances in chunks of %d on ROCm", chunk)
    return patched
