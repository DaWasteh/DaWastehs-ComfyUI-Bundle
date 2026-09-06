"""RDNA4 benchmark probe.

Loaded ONLY by the benchmark ComfyUI instance via extra_model_paths
(`custom_nodes:` entry in bench/extra_model_paths_bench.yaml). It never touches
the production custom_nodes folder.

Endpoints (loopback only, read-only except the explicit resets):
  GET  /rdna4/info        -> backend facts (attention fn, flags, ck backends, ...)
  GET  /rdna4/mem         -> torch allocator stats per device + host RAM + pid
  POST /rdna4/mem/reset   -> torch.cuda.reset_peak_memory_stats on all devices
  GET  /rdna4/trace       -> per-node start timestamps + progress ticks
                             (collected by wrapping PromptServer.send_sync)
  POST /rdna4/trace/reset -> clear the trace buffer
"""
from __future__ import annotations

import logging
import os
import threading
import time

import torch
from aiohttp import web

import comfy.model_management as mm
import server

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

_log = logging.getLogger("rdna4_bench_probe")
_lock = threading.Lock()
_trace: list[dict] = []
_MAX_TRACE = 200000


def _dev_stats(i: int) -> dict:
    free, total = torch.cuda.mem_get_info(i)
    return {
        "index": i,
        "name": torch.cuda.get_device_name(i),
        "allocated": torch.cuda.memory_allocated(i),
        "reserved": torch.cuda.memory_reserved(i),
        "max_allocated": torch.cuda.max_memory_allocated(i),
        "max_reserved": torch.cuda.max_memory_reserved(i),
        "free": free,
        "total": total,
    }


def _host() -> dict:
    try:
        import psutil

        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        p = psutil.Process(os.getpid())
        return {
            "ram_total": vm.total,
            "ram_available": vm.available,
            "swap_used": sw.used,
            "process_rss": p.memory_info().rss,
        }
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


async def mem(_req):
    return web.json_response(
        {
            "t": time.time(),
            "pid": os.getpid(),
            "devices": [_dev_stats(i) for i in range(torch.cuda.device_count())],
            "host": _host(),
        }
    )


async def mem_reset(_req):
    for i in range(torch.cuda.device_count()):
        torch.cuda.reset_peak_memory_stats(i)
    return web.json_response({"ok": True})


_ARG_KEYS = (
    "use_pytorch_cross_attention", "use_ck_attention", "use_flash_attention", "use_sage_attention",
    "disable_dynamic_vram", "enable_dynamic_vram", "async_offload", "disable_async_offload",
    "disable_pinned_memory", "reserve_vram", "cache_ram", "cache_classic", "cache_none", "cache_lru",
    "fast", "fp16_unet", "bf16_unet", "fp8_e4m3fn_unet", "force_channels_last", "force_non_blocking",
    "disable_cuda_malloc", "cuda_malloc", "highvram", "gpu_only", "lowvram", "disable_smart_memory",
    "default_device", "cuda_device", "supports_fp8_compute", "enable_triton_backend", "disable_triton_backend",
    "fp16_intermediates", "mmap_torch_files", "disable_mmap", "fast_disk", "vram_headroom",
    "disable_comfy_compiler", "disable_cuda_graphs", "high_ram", "preview_method",
)
_ENV_KEYS = (
    "HIP_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES", "TORCH_BLAS_PREFER_HIPBLASLT",
    "DISABLE_ADDMM_CUDA_LT", "TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "PYTORCH_TUNABLEOP_ENABLED",
    "OMP_NUM_THREADS", "HSA_OVERRIDE_GFX_VERSION", "PYTORCH_HIP_ALLOC_CONF", "PYTORCH_CUDA_ALLOC_CONF",
    "TORCH_ROCM_FA_PREFER_CK", "HIPBLASLT_TENSILE_LIBPATH", "MIOPEN_FIND_MODE", "GPU_MAX_HW_QUEUES",
)


async def info(_req):
    import comfy.cli_args
    import comfy.ldm.modules.attention as attn

    a = comfy.cli_args.args
    out = {
        "pid": os.getpid(),
        "torch": torch.__version__,
        "hip": torch.version.hip,
        "devices": [
            {
                "index": i,
                "name": torch.cuda.get_device_name(i),
                "arch": torch.cuda.get_device_properties(i).gcnArchName,
                "total": torch.cuda.get_device_properties(i).total_memory,
            }
            for i in range(torch.cuda.device_count())
        ],
        "attention_function": getattr(attn.optimized_attention, "__name__", str(attn.optimized_attention)),
        "attention_masked_function": getattr(attn.optimized_attention_masked, "__name__", None),
        "ENABLE_PYTORCH_ATTENTION": mm.ENABLE_PYTORCH_ATTENTION,
        "pytorch_attention_flash": mm.pytorch_attention_flash_attention(),
        "vram_state": str(mm.vram_state),
        "NUM_STREAMS": getattr(mm, "NUM_STREAMS", None),
        "MAX_PINNED_MEMORY": getattr(mm, "MAX_PINNED_MEMORY", None),
        "EXTRA_RESERVED_VRAM": getattr(mm, "EXTRA_RESERVED_VRAM", None),
        "SUPPORT_FP8_OPS": getattr(mm, "SUPPORT_FP8_OPS", None),
        "supports_fp8_compute": mm.supports_fp8_compute(),
        "sdp": {
            "flash": torch.backends.cuda.flash_sdp_enabled(),
            "mem_efficient": torch.backends.cuda.mem_efficient_sdp_enabled(),
            "math": torch.backends.cuda.math_sdp_enabled(),
        },
        "preferred_blas": str(torch.backends.cuda.preferred_blas_library()),
        "env": {k: os.environ.get(k) for k in _ENV_KEYS},
        "args": {k: getattr(a, k, None) for k in _ARG_KEYS},
    }
    try:
        out["args"]["fast"] = [str(x) for x in (a.fast or [])]
    except Exception:
        pass
    try:
        out["args"]["preview_method"] = str(a.preview_method)
    except Exception:
        pass
    try:
        import comfy.memory_management as cmm

        out["aimdo_enabled"] = cmm.aimdo_enabled
    except Exception as e:  # pragma: no cover
        out["aimdo_enabled"] = f"err {e}"
    try:
        import comfy_kitchen as ck

        out["comfy_kitchen_backends"] = {
            k: (v if isinstance(v, (str, bool, int, dict, list)) else str(v)) for k, v in ck.list_backends().items()
        }
        out["comfy_kitchen_int8_attention_available"] = bool(ck.int8_attention_is_available())
    except Exception as e:  # pragma: no cover
        out["comfy_kitchen_backends"] = f"err {e}"
    return web.json_response(out)


async def trace(_req):
    with _lock:
        data = list(_trace)
    return web.json_response({"events": data})


async def trace_reset(_req):
    with _lock:
        _trace.clear()
    return web.json_response({"ok": True})


def _install_trace_hook():
    inst = server.PromptServer.instance
    if inst is None or getattr(inst, "_rdna4_hooked", False):
        return
    orig = inst.send_sync

    def send_sync(event, data, sid=None):
        try:
            if event in ("executing", "execution_start", "execution_success", "execution_error",
                         "execution_cached", "executed", "execution_interrupted"):
                rec = {"t": time.time(), "event": event}
                if isinstance(data, dict):
                    rec["node"] = data.get("node")
                    rec["display_node"] = data.get("display_node")
                    rec["prompt_id"] = data.get("prompt_id")
                    if event == "execution_cached":
                        rec["nodes"] = data.get("nodes")
                    if event == "execution_error":
                        rec["exception_message"] = data.get("exception_message")
                        rec["node_type"] = data.get("node_type")
                with _lock:
                    if len(_trace) < _MAX_TRACE:
                        _trace.append(rec)
            elif event == "progress":
                rec = {"t": time.time(), "event": "progress"}
                if isinstance(data, dict):
                    rec["node"] = data.get("node")
                    rec["value"] = data.get("value")
                    rec["max"] = data.get("max")
                    rec["prompt_id"] = data.get("prompt_id")
                with _lock:
                    if len(_trace) < _MAX_TRACE:
                        _trace.append(rec)
        except Exception:  # never break the server because of the probe
            pass
        return orig(event, data, sid)

    inst.send_sync = send_sync
    inst._rdna4_hooked = True


def _register():
    inst = server.PromptServer.instance
    if inst is None:
        _log.warning("rdna4_bench_probe: PromptServer not ready")
        return
    inst.routes.get("/rdna4/mem")(mem)
    inst.routes.post("/rdna4/mem/reset")(mem_reset)
    inst.routes.get("/rdna4/info")(info)
    inst.routes.get("/rdna4/trace")(trace)
    inst.routes.post("/rdna4/trace/reset")(trace_reset)
    _install_trace_hook()
    _log.info("rdna4_bench_probe: routes registered")


_register()
