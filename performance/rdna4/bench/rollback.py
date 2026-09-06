"""Rollback helper for the RDNA4 optimisation pass.

Default is a dry run (preview). Pass --apply to execute. Every restore compares the
current file against the SHA-256 recorded when the benchmark started
(baseline_state/sha256_originals.txt); if the live file differs from BOTH the
original and the version this pass installed, it is left alone and reported
(protects later user edits).

Targets:
  1. L:\\ComfyUI\\start-MultiGPU.ps1        <- baseline_state/start-MultiGPU.ps1.orig
  2. L:\\ComfyUI\\ComfyUI\\comfy\\samplers.py  <- baseline_state/comfy_samplers.py.orig (only if changed)
  3. L:\\ComfyUI\\ComfyUI\\input\\lora_training\\_rdna4_bench  (benchmark dataset folder, removed)
  4. bench_state/ (benchmark SQLite DBs), optional
Repo workflow fixes are tracked by git; `git checkout -- workflows/` reverts them.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE.parent / "baseline_state"
LIVE = {
    "start-MultiGPU.ps1.orig": Path("L:/ComfyUI/start-MultiGPU.ps1"),
    "comfy_samplers.py.orig": Path("L:/ComfyUI/ComfyUI/comfy/samplers.py"),
    "windows_comfy_launcher.py.orig": Path("L:/ComfyUI/scripts/windows_comfy_launcher.py"),
}
DATASET = Path("L:/ComfyUI/ComfyUI/input/lora_training/_rdna4_bench")
DATASET_AUDIO = Path("L:/ComfyUI/ComfyUI/input/lora_training/_rdna4_bench_audio")  # v1.1.2 ACE voice trainer smoke set
INSTALLED_DIR = HERE.parent / "profiles" / "installed"  # copies of files this pass installed into L:\ComfyUI


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--remove-bench-db", action="store_true")
    a = ap.parse_args()
    originals = {}
    for line in (STATE / "sha256_originals.txt").read_text().splitlines():
        h, _, name = line.partition(" ")
        originals[name.strip("*").strip()] = h
    rc = 0
    for name, live in LIVE.items():
        orig = STATE / name
        cur = sha(live) if live.exists() else None
        if cur == sha(orig):
            print(f"[ok]      {live} == original")
            continue
        installed = INSTALLED_DIR / name.replace(".orig", "")
        if installed.exists() and cur == sha(installed):
            print(f"[restore] {live}  (currently the version installed by this pass)")
            if a.apply:
                shutil.copy2(orig, live)
        else:
            print(f"[SKIP]    {live} differs from original AND from anything this pass installed -> manual review")
            rc = 1
    if DATASET.exists():
        print(f"[remove]  {DATASET} ({sum(1 for _ in DATASET.iterdir())} files)")
        if a.apply:
            shutil.rmtree(DATASET)
    else:
        print(f"[ok]      {DATASET} absent")
    if DATASET_AUDIO.exists():
        print(f"[remove]  {DATASET_AUDIO} ({sum(1 for _ in DATASET_AUDIO.iterdir())} files)")
        if a.apply:
            shutil.rmtree(DATASET_AUDIO)
    else:
        print(f"[ok]      {DATASET_AUDIO} absent")
    if a.remove_bench_db:
        for db in (HERE / "bench_state").glob("*.db*"):
            print(f"[remove]  {db}")
            if a.apply:
                db.unlink()
    print("APPLIED" if a.apply else "DRY RUN (use --apply)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
