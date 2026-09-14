#!/usr/bin/env python3
"""Install the selected v1.1.8 RDNA4 models with pinned revisions and SHA-256.

YuE2 is CC-BY-NC-4.0: local/private noncommercial use only. Existing differing
files are never overwritten. Shared Pixal3D/TRELLIS VAEs are reused.
"""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

try:
    from tools.install_pixal3d_game_models import validate_root, target_path, verify
except ModuleNotFoundError:
    from install_pixal3d_game_models import validate_root, target_path, verify

MANIFEST = (
    Path(__file__).resolve().parent / "workflow_templates/v118/model-manifest.json"
)


def model_files():
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paths = [item["path"] for item in items]
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate model targets in manifest")
    return items


def install(root, verify_only=False, include_private_yue2=False):
    items = model_files()
    if not include_private_yue2:
        items = [i for i in items if i["repo"] != "Comfy-Org/YuE2"]
    failures = []
    for item in items:
        target = target_path(root / "models", item["path"])
        valid, detail = verify(target, item["size"], item["sha256"])
        if valid:
            print("OK", item["path"], flush=True)
            continue
        if verify_only or target.exists():
            failures.append((item["path"], detail))
            print("FAIL (not overwritten)", item["path"], detail, flush=True)
            continue
        from huggingface_hub import hf_hub_download

        source = item["source"]
        # Hub's local_dir preserves repository-relative layout and atomically
        # finalizes files. Cosmos repackages are root files, installed one level down.
        local_dir = root / "models" if source == item["path"] else target.parent
        relocated = (local_dir / source).resolve() != target
        if relocated:
            local_dir = (
                root
                / "models/.cache/v118-downloads"
                / item["repo"].replace("/", "--")
                / item["revision"]
            )
        print("GET", item["repo"], source, flush=True)
        result = Path(
            hf_hub_download(
                repo_id=item["repo"],
                filename=source,
                revision=item["revision"],
                local_dir=local_dir,
            )
        ).resolve()
        valid, detail = verify(result, item["size"], item["sha256"])
        if valid and relocated:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(
                result, target
            )  # atomic, refuses replacement; cache is on the same model volume
        elif not relocated and result != target:
            raise ValueError("Unexpected download target")
        if not valid:
            failures.append((item["path"], detail))
        print("OK" if valid else "FAIL", item["path"], flush=True)
    print(json.dumps({"files": len(items), "failures": failures}, indent=2))
    return int(bool(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--include-private-yue2",
        action="store_true",
        help="Explicitly include noncommercial YuE2; not licensed for monetized streaming",
    )
    args = parser.parse_args()
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
    return install(
        validate_root(args.comfy_root), args.verify_only, args.include_private_yue2
    )


if __name__ == "__main__":
    raise SystemExit(main())
