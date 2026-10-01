"""SAM3 text encoder on another GPU: let ComfyUI's CLIP-only reload find its weights (v1.3.1).

``SelectCLIPDevice`` moves a CLIP to another GPU by reloading it from the checkpoint (``deepclone_multigpu`` ->
``load_checkpoint_clip_patcher``, ``output_model=False``). For SAM3/SAM 3.1 checkpoints the text encoder weights are
only collected while the image model is processed (``SAM3.process_unet_state_dict`` fills ``_clip_stash``); the
CLIP-only reload skips that step. ``SAM3.process_clip_state_dict`` then reads ``getattr(self, "_clip_stash", {})``, but
the model-config base class answers every unknown attribute with ``None`` (``BASE.__getattr__``), so the reload failed
with "'NoneType' object has no attribute 'keys'" (SCAIL 2 character animation with the text encoders on the RX 9070 XT,
measured 2026-09-30). The patch collects the stash from the checkpoint exactly like ``process_unet_state_dict`` when it
is missing; the normal load path is unchanged. Reported upstream: https://github.com/Comfy-Org/ComfyUI/issues/16675

Environment:
    DAWASTEH_SAM3_RELOAD_FIX=0   leave ComfyUI's behaviour unchanged
"""
from __future__ import annotations

import logging
import os


def enabled() -> bool:
    return os.environ.get("DAWASTEH_SAM3_RELOAD_FIX", "1").strip().lower() not in ("0", "false", "no", "off")


def stash_from_checkpoint(state_dict: dict) -> dict:
    """The keys SAM3.process_unet_state_dict moves into ``_clip_stash``."""
    return {k: state_dict.pop(k) for k in list(state_dict.keys()) if "language_backbone" in k and "resizer" not in k}


def apply() -> bool:
    if not enabled():
        logging.info("[DaWasteh SAM3 reload] disabled via DAWASTEH_SAM3_RELOAD_FIX=0")
        return False
    import comfy.supported_models

    sam3 = getattr(comfy.supported_models, "SAM3", None)
    original = vars(sam3).get("process_clip_state_dict") if sam3 is not None else None
    if original is None or getattr(original, "dawasteh_patch", False):
        return False

    def process_clip_state_dict(self, state_dict):
        if vars(self).get("_clip_stash") is None:  # CLIP-only reload: process_unet_state_dict did not run
            self._clip_stash = stash_from_checkpoint(state_dict)
        return original(self, state_dict)

    process_clip_state_dict.dawasteh_patch = True
    sam3.process_clip_state_dict = process_clip_state_dict
    logging.info("[DaWasteh SAM3 reload] SAM3 text encoder can be moved to another GPU")
    return True
