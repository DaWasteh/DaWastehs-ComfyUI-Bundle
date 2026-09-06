"""Central device dropdowns for DaWasteh Multi-GPU ComfyUI workflows."""

import logging

from .nodes import comfy_entrypoint

try:
    from . import vram_guard

    vram_guard.apply()
except Exception as exc:  # never block node registration because of the guard
    logging.warning("[DaWasteh VRAM guard] not applied: %s", exc)

WEB_DIRECTORY = "./web"

__all__ = ["comfy_entrypoint", "WEB_DIRECTORY"]
