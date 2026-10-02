"""Gaussian-splat linear algebra runs in chunks on ROCm (MultiGPU-Control pack, v1.3.2)."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control" / "splat_inverse.py"


@pytest.fixture
def mod():
    spec = importlib.util.spec_from_file_location("splat_inverse_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_splat_module(name="comfy_extras.nodes_gaussian_splat_fake"):
    module = types.ModuleType(name)
    module.torch = torch
    module.RenderSplat = type("RenderSplat", (), {})
    return module


def batch(n, seed=0):
    g = torch.Generator().manual_seed(seed)
    a = torch.rand(n, 3, 3, generator=g, dtype=torch.float64)
    return a @ a.transpose(1, 2) + torch.eye(3, dtype=torch.float64)  # symmetric positive definite


def test_chunked_inverse_matches_the_single_call(mod):
    a = batch(1000)
    expected = torch.linalg.inv(a)
    got = mod.chunked(torch.linalg.inv, a, 128)
    assert torch.allclose(got, expected)
    assert got.shape == expected.shape and got.dtype == expected.dtype


def test_chunked_eigh_returns_both_parts_and_keeps_leading_dims(mod):
    a = batch(300).reshape(10, 30, 3, 3)
    values, vectors = mod.chunked(torch.linalg.eigh, a, 64)
    exp_values, exp_vectors = torch.linalg.eigh(a)
    assert torch.allclose(values, exp_values) and torch.allclose(vectors.abs(), exp_vectors.abs())
    assert values.shape == (10, 30, 3) and vectors.shape == (10, 30, 3, 3)


def test_only_large_batches_on_the_gpu_are_chunked(mod):
    small = batch(10)
    assert not mod.needs_chunking(small, 4)  # CPU tensors never need it: the kernel limit is a HIP property
    assert not mod.needs_chunking(torch.eye(3), 1)

    class Fake:
        ndim, is_cuda, shape = 3, True, (70000, 3, 3)

    assert mod.needs_chunking(Fake(), 32768)
    Fake.shape = (60000, 3, 3)
    assert not mod.needs_chunking(Fake(), 65535)


def test_proxy_passes_everything_else_through(mod):
    proxy = mod.TorchProxy(torch, 8)
    assert proxy.cat is torch.cat and proxy.float32 is torch.float32 and proxy.linalg.cross is torch.linalg.cross
    a = batch(20)
    assert torch.allclose(proxy.linalg.inv(a), torch.linalg.inv(a))
    assert torch.allclose(proxy.linalg.det(a), torch.linalg.det(a))


def test_apply_patches_only_the_splat_modules_and_is_idempotent(mod, monkeypatch):
    splat = fake_splat_module()
    other = types.ModuleType("some.other.module")
    other.torch = torch
    monkeypatch.setitem(sys.modules, splat.__name__, splat)
    monkeypatch.setitem(sys.modules, other.__name__, other)
    assert mod.apply(force=True) == 1
    assert isinstance(splat.torch, mod.TorchProxy) and other.torch is torch
    first = splat.torch
    assert mod.apply(force=True) == 1 and splat.torch is first  # no proxy of a proxy


def test_apply_is_a_no_op_outside_rocm_and_when_disabled(mod, monkeypatch):
    splat = fake_splat_module("comfy_extras.nodes_gaussian_splat_fake2")
    monkeypatch.setitem(sys.modules, splat.__name__, splat)
    monkeypatch.setattr(mod, "is_rocm", lambda: False)
    assert mod.apply() == 0 and splat.torch is torch
    monkeypatch.setenv("DAWASTEH_SPLAT_LINALG_FIX", "0")
    assert mod.apply(force=True) == 0 and splat.torch is torch


def test_pack_init_registers_the_patch():
    source = (ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control" / "__init__.py").read_text(encoding="utf-8")
    assert "splat_inverse.apply()" in source
