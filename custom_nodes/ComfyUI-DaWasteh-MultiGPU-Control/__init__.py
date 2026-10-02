"""Central device dropdowns for DaWasteh Multi-GPU ComfyUI workflows."""

import logging

from .nodes import comfy_entrypoint

try:
    from . import vram_guard

    vram_guard.apply()
except Exception as exc:  # never block node registration because of the guard
    logging.warning("[DaWasteh VRAM guard] not applied: %s", exc)

try:
    from . import compute_dtype

    compute_dtype.apply()
except Exception as exc:  # never block node registration because of the patch
    logging.warning("[DaWasteh compute dtype] not applied: %s", exc)

try:
    from . import readonly_load

    readonly_load.apply()
except Exception as exc:  # never block node registration because of the patch
    logging.warning("[DaWasteh read-only load] not applied: %s", exc)

try:
    from . import sam3_reload

    sam3_reload.apply()
except Exception as exc:  # never block node registration because of the patch
    logging.warning("[DaWasteh SAM3 reload] not applied: %s", exc)

try:
    from . import splat_inverse

    splat_inverse.apply()
except Exception as exc:  # never block node registration because of the patch
    logging.warning("[DaWasteh splat linalg] not applied: %s", exc)

WEB_DIRECTORY = "./web"

__all__ = ["comfy_entrypoint", "WEB_DIRECTORY"]
