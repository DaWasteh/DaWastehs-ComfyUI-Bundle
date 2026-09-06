"""Per-process VRAM cap against the Windows/WDDM host-memory spill on ROCm.

Measured on 2026-09-06 (``performance/rdna4/raw/vram_probe/``, torch 2.13+rocm10.1, HIP 7.16,
RX 9070 XT): the HIP caching allocator never raised an out-of-memory error on Windows. Past the
card's dedicated VRAM the driver silently backed every further GPU allocation with host RAM
(0.5 GiB of host memory per 512 MiB chunk, starting about 2 GiB before the VRAM was exhausted)
and kept going. That is the mechanism behind the two full-system freezes of 2026-09-05 at
``Training LoRA: 0/32``: the backward pass of the whole-model checkpoint needed more than the
32 GB of the R9700, nothing raised, and the host ran out of memory (``WinError 10055``).

``torch.cuda.set_per_process_memory_fraction`` makes the caching allocator raise
``torch.OutOfMemoryError`` *before* the driver can spill. ComfyUI already handles that
exception (frees models, retries, tiled VAE fallbacks), so a runaway job now fails with a
readable error instead of taking the machine down.

The cap is computed per device from the memory that is actually free when ComfyUI starts, so
a foreign resident process (for example the AutoTuner llama-server on the R9700) is respected.

Environment:
    DAWASTEH_VRAM_GUARD=0                disable the guard entirely
    DAWASTEH_VRAM_GUARD_RESERVE_GIB=3    VRAM left untouched per device (default 3 GiB)
    DAWASTEH_VRAM_GUARD_MAX_FRACTION=0.95  never allow more than this share of the total VRAM
"""
from __future__ import annotations

import logging
import os

GIB = 1024 ** 3
_APPLIED: list[dict] = []


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logging.warning("[DaWasteh VRAM guard] ignoring %s=%r (not a number)", name, raw)
        return default


def enabled() -> bool:
    return os.environ.get("DAWASTEH_VRAM_GUARD", "1").strip().lower() not in ("0", "false", "off", "no")


def plan(free: int, total: int, reserve_gib: float, max_fraction: float) -> float:
    """Return the allocator fraction for one device (pure function, unit-tested)."""
    allowed = min(max_fraction * total, free - reserve_gib * GIB)
    fraction = allowed / total if total > 0 else 0.0
    return max(0.05, min(max_fraction, fraction))


def apply(force: bool = False) -> list[dict]:
    """Apply the cap on every visible CUDA/HIP device once. Returns what was applied."""
    if _APPLIED and not force:
        return list(_APPLIED)
    if not enabled():
        logging.info("[DaWasteh VRAM guard] disabled via DAWASTEH_VRAM_GUARD=0")
        return []
    try:
        import torch
    except Exception as exc:  # pragma: no cover - torch always present inside ComfyUI
        logging.warning("[DaWasteh VRAM guard] torch unavailable: %s", exc)
        return []
    if not torch.cuda.is_available():
        return []
    reserve_gib = _env_float("DAWASTEH_VRAM_GUARD_RESERVE_GIB", 3.0)
    max_fraction = _env_float("DAWASTEH_VRAM_GUARD_MAX_FRACTION", 0.95)
    _APPLIED.clear()
    for index in range(torch.cuda.device_count()):
        try:
            free, total = torch.cuda.mem_get_info(index)
            fraction = plan(free, total, reserve_gib, max_fraction)
            torch.cuda.set_per_process_memory_fraction(fraction, index)
            rec = {
                "device": index,
                "name": torch.cuda.get_device_name(index),
                "total_gib": round(total / GIB, 2),
                "free_gib": round(free / GIB, 2),
                "fraction": round(fraction, 4),
                "allowed_gib": round(fraction * total / GIB, 2),
                "reserve_gib": reserve_gib,
            }
            _APPLIED.append(rec)
            logging.info(
                "[DaWasteh VRAM guard] cuda:%d %s: allocator capped at %.2f GiB of %.2f GiB (fraction %.3f, "
                "%.2f GiB free at start, %.1f GiB reserve)",
                index, rec["name"], rec["allowed_gib"], rec["total_gib"], fraction, rec["free_gib"], reserve_gib,
            )
        except Exception as exc:
            logging.warning("[DaWasteh VRAM guard] could not cap device %d: %s", index, exc)
    return list(_APPLIED)


def status() -> list[dict]:
    return list(_APPLIED)
