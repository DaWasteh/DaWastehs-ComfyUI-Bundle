"""Keep the model's own compute dtypes when ComfyUI's Select Model Device moves a model (v1.3.1).

ComfyUI's core node ``SelectModelDevice`` (``comfy_extras/nodes_multigpu.py``, upstream #14108) re-derives the compute
dtype after retargeting a model with ``unet_manual_cast(weight_dtype, device)`` but without the model's
``supported_inference_dtypes``. For FP8 weights that always yields float16, also for models that only run in
bfloat16 or float32. Qwen Image (Edit) overflows in float16: every value becomes NaN and the saved image is black
(measured 2026-09-30 with Qwen Image Edit 2509 FP8 behind the bundle's device control; ComfyUI's loader had chosen
bfloat16 for the same model a moment earlier). The patch only corrects dtypes a model does not support: when ComfyUI's
choice is not in ``supported_inference_dtypes``, it picks from that list like the loader in ``comfy/sd.py`` does. Models
that support float16 (FLUX, FLUX.2, Krea 2, WAN ...) keep ComfyUI's choice.
Reported upstream: https://github.com/Comfy-Org/ComfyUI/issues/16682

Environment:
    DAWASTEH_COMPUTE_DTYPE_FIX=0   leave ComfyUI's behaviour unchanged
"""
from __future__ import annotations

import logging
import os
import sys

TARGET = "_force_supported_compute_dtype"


def enabled() -> bool:
    return os.environ.get("DAWASTEH_COMPUTE_DTYPE_FIX", "1").strip().lower() not in ("0", "false", "no", "off")


def supported_dtypes(patcher) -> list | None:
    config = getattr(getattr(patcher, "model", None), "model_config", None)
    dtypes = getattr(config, "supported_inference_dtypes", None)
    return list(dtypes) if dtypes else None


def force_supported_compute_dtype(patcher, device) -> None:
    """Drop-in for ``nodes_multigpu._force_supported_compute_dtype`` that honours the model's dtypes."""
    import comfy.model_management

    weight_dtype = patcher.model_dtype()
    cast_dtype = comfy.model_management.unet_manual_cast(weight_dtype, device)
    if cast_dtype is None:
        return
    supported = supported_dtypes(patcher)
    if supported and cast_dtype not in supported:
        cast_dtype = comfy.model_management.unet_manual_cast(weight_dtype, device, supported)
        if cast_dtype is None:
            return
    logging.info("Select Model Device: using %s compute dtype on %s (model weight dtype was %s, model supports %s).",
                 cast_dtype, device, weight_dtype, supported)
    patcher.set_model_compute_dtype(cast_dtype)


force_supported_compute_dtype.dawasteh_patch = True


def _module_attr(module, name: str):
    """Read a module global without triggering module-level __getattr__ hooks (torch._classes raises there)."""
    try:
        return vars(module).get(name)
    except TypeError:  # None placeholders in sys.modules
        return None


def apply() -> int:
    """Patch every loaded copy of the core multigpu nodes module. Returns the number of patched modules."""
    if not enabled():
        logging.info("[DaWasteh compute dtype] disabled via DAWASTEH_COMPUTE_DTYPE_FIX=0")
        return 0
    patched = 0
    for module in list(sys.modules.values()):
        original = _module_attr(module, TARGET)
        if original is None or _module_attr(module, "SelectModelDeviceNode") is None:
            continue
        if not getattr(original, "dawasteh_patch", False):
            setattr(module, TARGET, force_supported_compute_dtype)
        patched += 1
    if patched:
        logging.info("[DaWasteh compute dtype] Select Model Device keeps the model's supported compute dtypes")
    return patched
