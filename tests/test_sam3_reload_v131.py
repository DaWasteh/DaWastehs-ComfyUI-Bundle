"""SAM3 CLIP-only reload fix of the MultiGPU-Control pack (v1.3.1).

Reproduced 2026-09-30 with sam3.1_multiplex_fp16: load_checkpoint_clip_patcher failed with "'NoneType' object has no
attribute 'keys'"; with the patch the SAM3 text encoder (354M parameters) loads.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control" / "sam3_reload.py"


class Base:  # comfy.supported_models_base.BASE answers unknown attributes with None
    def __getattr__(self, name):
        return None


class SAM3(Base):
    def process_clip_state_dict(self, state_dict):
        clip_keys = getattr(self, "_clip_stash", {})
        return {k.replace("detector.backbone.language_backbone.", ""): v for k, v in clip_keys.items()}

    def process_unet_state_dict(self, state_dict):
        self._clip_stash = {k: state_dict.pop(k) for k in list(state_dict) if "language_backbone" in k and "resizer" not in k}
        return state_dict


def load(monkeypatch):
    models = types.ModuleType("comfy.supported_models")
    models.SAM3 = type("SAM3", (SAM3,), {"process_clip_state_dict": SAM3.process_clip_state_dict})
    comfy = types.ModuleType("comfy")
    comfy.supported_models = models
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(sys.modules, "comfy.supported_models", models)
    spec = importlib.util.spec_from_file_location("sam3_reload_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, models.SAM3


def checkpoint():
    return {"detector.backbone.language_backbone.encoder.w": 1, "detector.backbone.language_backbone.resizer.w": 2,
            "detector.image.w": 3}


def test_clip_only_reload_collects_the_text_encoder(monkeypatch):
    module, sam3 = load(monkeypatch)
    assert module.apply()
    sd = checkpoint()
    assert sam3().process_clip_state_dict(sd) == {"encoder.w": 1}
    assert "detector.backbone.language_backbone.encoder.w" not in sd


def test_normal_load_keeps_the_stash_from_the_image_model(monkeypatch):
    module, sam3 = load(monkeypatch)
    module.apply()
    config, sd = sam3(), checkpoint()
    config.process_unet_state_dict(sd)
    assert config.process_clip_state_dict(sd) == {"encoder.w": 1}
    assert not module.apply()  # idempotent


def test_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DAWASTEH_SAM3_RELOAD_FIX", "0")
    module, sam3 = load(monkeypatch)
    assert not module.apply()
