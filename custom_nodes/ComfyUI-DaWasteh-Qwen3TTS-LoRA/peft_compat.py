"""Keep PEFT 0.19 from rejecting ComfyUI's older, unused torchao build (process-wide).

PEFT >= 0.19 probes its torchao LoRA dispatcher for every target layer and raises
``ImportError("Found an incompatible version of torchao ...")`` when torchao < 0.16 is installed
instead of returning ``False``. The ComfyUI venv carries torchao 0.9.0 (required by
ComfyUI-HeartMuLa), so every PEFT-based trainer in the process fails to inject LoRA layers:
this node pack's Qwen3-TTS trainer, and third-party ones such as ``fl-acestep-training``,
which swallows the exception as "Error: PEFT not installed" (reproduced 2026-09-06,
``performance/rdna4/REPORT.md`` §9).

Only the torchao dispatcher is disabled; the shared torchao package stays untouched and PEFT
continues to its standard ``torch.nn.Linear`` dispatcher. Importing this module has no side
effect; call :func:`disable_incompatible_torchao_dispatcher` (idempotent, safe without peft).
"""
from __future__ import annotations

import logging

_STATE = {"applied": None}


def torchao_needs_shim() -> bool:
    try:
        import torchao
        from packaging.version import Version

        return Version(torchao.__version__) < Version("0.16.0")
    except Exception:
        return False


def disable_incompatible_torchao_dispatcher() -> bool:
    """Return True when the dispatcher was (or already is) disabled, False when nothing was needed/possible."""
    if _STATE["applied"] is not None:
        return _STATE["applied"]
    applied = False
    try:
        if torchao_needs_shim():
            import peft.import_utils as import_utils
            import peft.tuners.lora.torchao as peft_torchao

            peft_torchao.is_torchao_available = lambda: False
            import_utils.is_torchao_available = lambda: False
            applied = True
            logging.info("[DaWasteh peft_compat] PEFT torchao dispatcher disabled (torchao < 0.16 installed)")
    except (ImportError, AttributeError) as exc:
        logging.debug("[DaWasteh peft_compat] not applied: %s", exc)
    _STATE["applied"] = applied
    return applied
