#!/usr/bin/env python3
"""Install/verify the pinned YuE2 trainer with the bundle's reviewed RDNA4 patch.

No dependency upgrades or model downloads. --upgrade replaces only a verified
v1.1.9 snapshot, with a backup outside custom_nodes; stop ComfyUI first.
The installed snapshot has no .git directory: generic git-pull updaters cannot
silently replace its validated backend. Reinstall explicitly for an upgrade.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools/workflow_templates/yue2-lora/trainer-manifest.json"
NODE_NAME = "ComfyUI-YuE2-Trainer"


def verify_node(folder, manifest):
    errors = []
    for name, digest in manifest["files"].items():
        path = folder / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(name)
    if errors:
        raise ValueError(f"Trainer files missing/different (not overwritten): {errors}")


def install(root, verify_only=False, upgrade=False):
    root = root.resolve()
    if not (root / "main.py").is_file() or not (root / "custom_nodes").is_dir():
        raise ValueError("Expected a ComfyUI root containing main.py and custom_nodes/")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    target = root / "custom_nodes" / NODE_NAME
    if verify_only and upgrade:
        raise ValueError("--verify-only and --upgrade are mutually exclusive")
    replacing = False
    if target.exists() or verify_only:
        try:
            verify_node(target, manifest)
        except ValueError:
            if not upgrade:
                raise
            previous = json.loads(MANIFEST.with_name("trainer-manifest-v119.json").read_text(encoding="utf-8"))
            verify_node(target, previous)  # Refuse modified/unknown installations.
            replacing = True
        else:
            print("OK", target)
            return
    # Staging is deliberately outside custom_nodes: ComfyUI must never import it.
    with tempfile.TemporaryDirectory(prefix=".yue2-install-", dir=root) as temp:
        staging = Path(temp) / NODE_NAME
        subprocess.run(["git", "clone", "--config", "core.autocrlf=false", "--config", "core.eol=lf",
                        "--no-checkout", manifest["repository"], str(staging)], check=True)
        subprocess.run(["git", "-C", str(staging), "checkout", "--detach", manifest["revision"]], check=True)
        subprocess.run(["git", "-C", str(staging), "apply", "--check", str(ROOT / manifest["patch"])], check=True)
        subprocess.run(["git", "-C", str(staging), "apply", str(ROOT / manifest["patch"])], check=True)
        verify_node(staging, manifest)
        # Copy tracked files only, excluding git metadata, before atomic publication.
        clean = Path(temp) / "snapshot"
        for name in manifest["files"]:
            destination = clean / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staging / name, destination)
        if replacing:
            # Preserve extras as well as tracked files, but never leave a second
            # importable trainer package inside custom_nodes.
            backup = root.parent / "backups" / f"yue2-trainer-v119-{uuid.uuid4().hex}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
            try:
                clean.rename(target)
            except BaseException:
                backup.rename(target)
                raise
            print("Backup:", backup)
        else:
            clean.rename(target)
    print("OK", target, "Restart ComfyUI; audio fallback: FFmpeg/imageio-ffmpeg (no torch upgrade).")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comfy-root", type=Path, required=True)
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--upgrade", action="store_true", help="Back up and upgrade an unmodified v1.1.9 trainer; stop ComfyUI first")
    a = p.parse_args()
    install(a.comfy_root, a.verify_only, a.upgrade)


if __name__ == "__main__":
    main()
