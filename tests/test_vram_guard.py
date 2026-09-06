"""Unit tests for the per-process VRAM guard of the MultiGPU-Control node pack (v1.1.2)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control" / "vram_guard.py"
GIB = 1024 ** 3


def _load():
    spec = importlib.util.spec_from_file_location("vram_guard_under_test", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plan_keeps_reserve_below_total():
    g = _load()
    total = 32 * GIB
    free = 32 * GIB
    fraction = g.plan(free, total, reserve_gib=3.0, max_fraction=0.95)
    assert fraction == pytest.approx(29 / 32)


def test_plan_respects_foreign_resident_process():
    g = _load()
    total = 32 * GIB
    free = 20 * GIB  # e.g. llama-server holding 12 GiB
    fraction = g.plan(free, total, reserve_gib=3.0, max_fraction=0.95)
    assert fraction == pytest.approx(17 / 32)


def test_plan_never_exceeds_max_fraction_and_has_floor():
    g = _load()
    total = 16 * GIB
    assert g.plan(16 * GIB, total, reserve_gib=0.0, max_fraction=0.95) == pytest.approx(0.95)
    assert g.plan(1 * GIB, total, reserve_gib=3.0, max_fraction=0.95) == pytest.approx(0.05)


def test_env_toggle(monkeypatch):
    g = _load()
    monkeypatch.setenv("DAWASTEH_VRAM_GUARD", "0")
    assert g.enabled() is False
    assert g.apply(force=True) == []
    monkeypatch.setenv("DAWASTEH_VRAM_GUARD", "1")
    assert g.enabled() is True


def test_env_float_ignores_garbage(monkeypatch):
    g = _load()
    monkeypatch.setenv("DAWASTEH_VRAM_GUARD_RESERVE_GIB", "abc")
    assert g._env_float("DAWASTEH_VRAM_GUARD_RESERVE_GIB", 3.0) == 3.0
    monkeypatch.setenv("DAWASTEH_VRAM_GUARD_RESERVE_GIB", "2.5")
    assert g._env_float("DAWASTEH_VRAM_GUARD_RESERVE_GIB", 3.0) == 2.5


def test_pack_init_applies_guard_source():
    src = (ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control" / "__init__.py").read_text(encoding="utf-8")
    assert "vram_guard.apply()" in src
    assert "comfy_entrypoint" in src


def test_start_script_documents_guard_env():
    script = (ROOT / "tools" / "start-MultiGPU.ps1").read_text(encoding="utf-8")
    assert "DAWASTEH_VRAM_GUARD" in script
    assert "DAWASTEH_VRAM_GUARD_RESERVE_GIB" in script
