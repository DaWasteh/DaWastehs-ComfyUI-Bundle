"""Access to the pinned Mira-Scene checkout (VAST-AI-Research, no license file yet: private use only).

The bundle updater places the checkout at <ComfyUI root>/third_party/Mira-Scene (commit PINNED_COMMIT); nothing of it is
copied into this repository. Only the parts that run on Windows/ROCm are imported:

- Mira-CCM's CCMVoxelPipeline (diffusers) for the canonical coordinate maps and the sparse voxel structure,
- UniDataset's crop_around_mask (the object crop of the CCM stage),
- infer_scripts/utils/solve_transform.py, scene_placement.py and 4_estimate_floor.py for the scene assembly.

spconv (sparse convolutions) and open3d are CUDA/Linux dependencies of unrelated code paths that are imported at module
level only; they get inert stand-ins so the dense CCM path can load. Mira's infer_scripts/utils is loaded under unique
module names because ComfyUI has its own top-level `utils` package.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import sys
import types
from pathlib import Path

TAG = "[DaWasteh Mira]"
PINNED_COMMIT = "18f42656f3b6f96ef61d9b291c93d1036bdaa016"
ENV_ROOT = "DAWASTEH_MIRA_SCENE_ROOT"
_MODULES: dict[str, types.ModuleType] = {}


def checkout_root() -> Path:
    """<ComfyUI root>/third_party/Mira-Scene, or the path in DAWASTEH_MIRA_SCENE_ROOT."""
    configured = os.environ.get(ENV_ROOT, "").strip().strip('"')
    if configured:
        return Path(configured)
    import folder_paths
    return Path(folder_paths.base_path).resolve().parent / "third_party" / "Mira-Scene"


def require_checkout() -> Path:
    root = checkout_root()
    if not (root / "Mira-CCM" / "src" / "miraccm").is_dir():
        raise FileNotFoundError(
            f"Mira-Scene-Code fehlt unter {root}. Der Bundle-Updater legt ihn an (git, Commit {PINNED_COMMIT[:7]}); "
            f"manuell: git clone https://github.com/VAST-AI-Research/Mira-Scene.git \"{root}\" und "
            f"git -C \"{root}\" checkout {PINNED_COMMIT}. Anderer Ort: Umgebungsvariable {ENV_ROOT}.")
    return root


def checkout_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _stub(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    module.__dawasteh_stub__ = True
    sys.modules[name] = module
    return module


def _install_stubs() -> None:
    try:
        import spconv.pytorch  # noqa: F401
    except ImportError:
        class SparseConvTensor:  # the dense CCM path never builds sparse tensors
            def __init__(self, *args, **kwargs):
                raise RuntimeError("spconv is not available; Mira's sparse modules are not used by the CCM stage")
        package = _stub("spconv")
        package.pytorch = _stub("spconv.pytorch", SparseConvTensor=SparseConvTensor)
    try:
        import open3d  # noqa: F401
    except ImportError:
        _stub("open3d")


def _load_file(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def modules() -> dict[str, types.ModuleType]:
    """Import once: pipeline class, crop helper, transform solver, placement backend, floor fit."""
    if _MODULES:
        return _MODULES
    root = require_checkout()
    commit = checkout_commit(root)
    if commit and commit != PINNED_COMMIT:
        logging.warning("%s checkout %s is at %s, the bundle was tested with %s", TAG, root, commit[:12], PINNED_COMMIT[:12])
    for path in (root / "Mira-CCM" / "src", root / "UniDataset" / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    _install_stubs()
    from miraccm.pipelines.shape_synthesis.pipeline_ccm_voxel import CCMVoxelPipeline
    from UniDataset.utils.img_and_mask_transforms import crop_around_mask
    scripts = root / "infer_scripts"
    _MODULES.update({
        "CCMVoxelPipeline": CCMVoxelPipeline,
        "crop_around_mask": crop_around_mask,
        "solve": _load_file("dawasteh_mira_solve_transform", scripts / "utils" / "solve_transform.py"),
        "placement": _load_file("dawasteh_mira_scene_placement", scripts / "utils" / "scene_placement.py"),
        "floor": _load_file("dawasteh_mira_estimate_floor", scripts / "4_estimate_floor.py"),
        "root": root,
        "commit": commit,
    })
    logging.info("%s code from %s (commit %s)", TAG, root, (commit or "?")[:12])
    return _MODULES
