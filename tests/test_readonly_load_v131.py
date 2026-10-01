"""Read-only safetensors loading of the MultiGPU-Control pack (v1.3.1).

Measured on real files (2026-09-30, ComfyUI 0.37): identical tensors and key order as ComfyUI's load_torch_file;
FLUX.2 Klein 9B KV FP8 (9.1 GiB) charged 9.16 GiB commit through safe_open and 0.02 GiB read-only.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
safetensors_torch = pytest.importorskip("safetensors.torch")

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control" / "readonly_load.py"
TYPES = {"F16": torch.float16, "BF16": torch.bfloat16, "F32": torch.float32, "U8": torch.uint8, "I64": torch.int64,
         "F8_E4M3": torch.float8_e4m3fn}


def load_module():
    spec = importlib.util.spec_from_file_location("readonly_load_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def weights(tmp_path):
    sd = {"z.weight": torch.randn(4, 3, dtype=torch.float16), "a.bias": torch.randn(7, dtype=torch.bfloat16),
          "m.scale": torch.tensor([1.5]), "m.fp8": torch.randn(8).to(torch.float8_e4m3fn),
          "empty": torch.zeros(0, 5)}
    path = tmp_path / "model.safetensors"
    safetensors_torch.save_file(sd, str(path), metadata={"format": "pt", "note": "dawasteh"})
    return path, sd


def test_same_tensors_same_sorted_order_and_metadata(weights):
    path, sd = weights
    ro = load_module()
    loaded, metadata = ro.load_readonly(str(path), TYPES)
    assert list(loaded) == sorted(sd)  # safe_open(...).keys() order: decides the VRAM layout
    for name, tensor in sd.items():
        assert loaded[name].dtype == tensor.dtype and loaded[name].shape == tensor.shape
        assert torch.equal(loaded[name].view(torch.uint8) if tensor.element_size() == 1 else loaded[name],
                           tensor.view(torch.uint8) if tensor.element_size() == 1 else tensor)
    assert metadata == {"format": "pt", "note": "dawasteh"}


def test_apply_routes_big_cpu_safetensors_and_falls_back_otherwise(weights, monkeypatch, tmp_path):
    path, sd = weights
    calls = []

    def original(ckpt, safe_load=False, device=None, return_metadata=False):
        calls.append(ckpt)
        return ({"original": True}, None) if return_metadata else {"original": True}

    utils = types.ModuleType("comfy.utils")
    utils.load_torch_file, utils._TYPES, utils.DISABLE_MMAP = original, TYPES, False
    mm = types.ModuleType("comfy.memory_management")
    mm.aimdo_enabled = False
    comfy = types.ModuleType("comfy")
    comfy.utils, comfy.memory_management = utils, mm
    user = types.ModuleType("fake_clip_vision")  # a module that did "from .utils import load_torch_file"
    user.load_torch_file = original
    for name, module in (("comfy", comfy), ("comfy.utils", utils), ("comfy.memory_management", mm),
                         ("fake_clip_vision", user)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("DAWASTEH_READONLY_SAFETENSORS_MIN_GIB", "0")
    ro = load_module()
    assert ro.apply() >= 2
    assert user.load_torch_file is utils.load_torch_file
    loaded = utils.load_torch_file(str(path))
    assert list(loaded) == sorted(sd) and not calls
    loaded, metadata = utils.load_torch_file(str(path), return_metadata=True)
    assert metadata["note"] == "dawasteh"
    broken = tmp_path / "broken.safetensors"
    broken.write_bytes(b"\x10\x00\x00\x00\x00\x00\x00\x00{not json")
    assert utils.load_torch_file(str(broken)) == {"original": True}  # ComfyUI raises its own readable error
    assert utils.load_torch_file(str(tmp_path / "model.ckpt")) == {"original": True}
    monkeypatch.setenv("DAWASTEH_READONLY_SAFETENSORS_MIN_GIB", "1")
    assert utils.load_torch_file(str(path)) == {"original": True}  # small files keep ComfyUI's loader
    assert ro.apply() == 0  # idempotent


def test_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DAWASTEH_READONLY_SAFETENSORS", "0")
    assert load_module().apply() == 0
