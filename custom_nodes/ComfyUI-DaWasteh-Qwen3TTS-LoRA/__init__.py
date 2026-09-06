"""ComfyUI nodes for Qwen3-TTS LoRA training and inference."""

import logging

from .nodes import Qwen3TTSLoRAInference, Qwen3TTSLoRATrain

# v1.1.2: apply the PEFT/torchao compatibility shim once at load time so that every PEFT-based
# trainer in this ComfyUI process (also third-party ones such as fl-acestep-training) can inject
# LoRA layers although the venv carries torchao 0.9.0 (see peft_compat.py).
try:
    from .peft_compat import disable_incompatible_torchao_dispatcher

    disable_incompatible_torchao_dispatcher()
except Exception as exc:  # never block node registration
    logging.warning("[DaWasteh peft_compat] not applied: %s", exc)

NODE_CLASS_MAPPINGS = {
    "DaWastehQwen3TTSLoRATrain": Qwen3TTSLoRATrain,
    "DaWastehQwen3TTSLoRAInference": Qwen3TTSLoRAInference,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DaWastehQwen3TTSLoRATrain": "Qwen3-TTS LoRA Train (DaWasteh)",
    "DaWastehQwen3TTSLoRAInference": "Qwen3-TTS LoRA Voice (DaWasteh)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
