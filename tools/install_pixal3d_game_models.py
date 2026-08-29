#!/usr/bin/env python3
"""Download and SHA-256 verify the six models used by v0.9.7 Pixal3D workflows.

Run this script with the target ComfyUI Python so its existing
``huggingface_hub``/``hf_xet`` installation can be reused. Downloads are written
through Hugging Face's local-dir cache and become visible under ``models/``
only after the library has completed each file.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

try:
    from tools.upgrade_v097 import MODEL_FILES
except ModuleNotFoundError:  # Direct execution from tools/
    from upgrade_v097 import MODEL_FILES


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_root(value: Path) -> Path:
    root = value.expanduser().resolve()
    models = root / "models"
    if not root.is_dir() or not models.is_dir():
        raise ValueError(f"ComfyUI root must already contain models/: {root}")
    return root


def target_path(models_root: Path, relative: str) -> Path:
    target = (models_root / Path(relative)).resolve()
    if models_root != target and models_root not in target.parents:
        raise ValueError(f"model path escapes models/: {relative}")
    return target


def verify(target: Path, expected_size: int, expected_sha256: str) -> tuple[bool, str]:
    if not target.is_file():
        return False, "missing"
    size = target.stat().st_size
    if size != expected_size:
        return False, f"size {size} != {expected_size}"
    digest = sha256_file(target)
    if digest != expected_sha256:
        return False, f"sha256 {digest} != {expected_sha256}"
    return True, digest


def install(comfy_root: Path, *, verify_only: bool = False) -> int:
    models_root = comfy_root / "models"
    failures = 0
    downloader = None
    if not verify_only:
        try:
            from huggingface_hub import hf_hub_download
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "huggingface_hub is missing. Run this installer with the ComfyUI venv Python."
            ) from exc
        downloader = hf_hub_download

    for index, item in enumerate(MODEL_FILES, 1):
        target = target_path(models_root, item["path"])
        valid, detail = verify(target, item["size"], item["sha256"])
        if valid:
            print(f"[{index}/{len(MODEL_FILES)}] OK   {item['path']}  {detail}")
            continue
        if verify_only:
            failures += 1
            print(f"[{index}/{len(MODEL_FILES)}] FAIL {item['path']}  {detail}")
            continue

        print(f"[{index}/{len(MODEL_FILES)}] GET  {item['repo']}/{item['path']} ({detail})")
        target.parent.mkdir(parents=True, exist_ok=True)
        downloaded = Path(
            downloader(repo_id=item["repo"], filename=item["path"], local_dir=models_root)
        ).resolve()
        if downloaded != target:
            raise RuntimeError(f"unexpected download target: {downloaded} != {target}")
        valid, detail = verify(target, item["size"], item["sha256"])
        if not valid:
            failures += 1
            print(f"[{index}/{len(MODEL_FILES)}] FAIL {item['path']}  {detail}")
        else:
            print(f"[{index}/{len(MODEL_FILES)}] OK   {item['path']}  {detail}")

    total = sum(item["size"] for item in MODEL_FILES)
    print(f"models={len(MODEL_FILES)} bytes={total} failures={failures} verify_only={verify_only}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comfy-root",
        type=Path,
        required=True,
        help="ComfyUI repository root containing models/ (for example L:/ComfyUI/ComfyUI)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not contact Hugging Face; verify existing files only.",
    )
    args = parser.parse_args()
    try:
        root = validate_root(args.comfy_root)
        return install(root, verify_only=args.verify_only)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
