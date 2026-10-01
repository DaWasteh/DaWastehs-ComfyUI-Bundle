"""Select Model Device keeps the model's supported compute dtypes (MultiGPU-Control pack, v1.3.1)."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control" / "compute_dtype.py"
FP16, BF16, FP32, FP8 = "float16", "bfloat16", "float32", "float8_e4m3fn"


def unet_manual_cast(weight_dtype, device, supported_dtypes=(FP16, BF16, FP32)):
    """ComfyUI's choice on a GPU that supports fp16 and bf16 (comfy.model_management.unet_manual_cast)."""
    if weight_dtype in (FP16, BF16, FP32):
        return None
    return next(d for d in supported_dtypes if d in (FP16, BF16, FP32))


class Patcher:
    def __init__(self, weight_dtype, supported):
        config = types.SimpleNamespace(supported_inference_dtypes=supported) if supported is not None else None
        self.model = types.SimpleNamespace(model_config=config)
        self.weight_dtype = weight_dtype
        self.compute_dtype = "unchanged"

    def model_dtype(self):
        return self.weight_dtype

    def set_model_compute_dtype(self, dtype):
        self.compute_dtype = dtype


@pytest.fixture
def mod(monkeypatch):
    comfy = types.ModuleType("comfy")
    comfy.model_management = types.SimpleNamespace(unet_manual_cast=unet_manual_cast)
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(sys.modules, "comfy.model_management", comfy.model_management)
    spec = importlib.util.spec_from_file_location("compute_dtype_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fp8_qwen_image_computes_in_bf16_not_fp16(mod):
    patcher = Patcher(FP8, [BF16, FP32])  # QwenImage.supported_inference_dtypes
    mod.force_supported_compute_dtype(patcher, "cuda:0")
    assert patcher.compute_dtype == BF16


def test_models_that_support_fp16_keep_comfyuis_choice(mod):
    patcher = Patcher(FP8, [BF16, FP16, FP32])  # Flux, Flux2, Krea2
    mod.force_supported_compute_dtype(patcher, "cuda:0")
    assert patcher.compute_dtype == FP16


def test_native_dtypes_stay_untouched_and_unknown_models_keep_comfy_default(mod):
    patcher = Patcher(BF16, [BF16, FP32])
    mod.force_supported_compute_dtype(patcher, "cuda:0")
    assert patcher.compute_dtype == "unchanged"
    patcher = Patcher(FP8, None)
    mod.force_supported_compute_dtype(patcher, "cuda:0")
    assert patcher.compute_dtype == FP16


def test_apply_patches_the_core_module_once_and_can_be_disabled(mod, monkeypatch):
    core = types.ModuleType("fake_nodes_multigpu")
    core.SelectModelDeviceNode = object
    core._force_supported_compute_dtype = lambda patcher, device: None
    monkeypatch.setitem(sys.modules, "fake_nodes_multigpu", core)
    monkeypatch.setenv("DAWASTEH_COMPUTE_DTYPE_FIX", "0")
    assert mod.apply() == 0
    monkeypatch.delenv("DAWASTEH_COMPUTE_DTYPE_FIX")
    assert mod.apply() >= 1
    assert core._force_supported_compute_dtype is mod.force_supported_compute_dtype
    assert mod.apply() >= 1  # idempotent
    assert core._force_supported_compute_dtype is mod.force_supported_compute_dtype
