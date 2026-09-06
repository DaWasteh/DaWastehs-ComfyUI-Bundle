"""Inspect a trained LoRA safetensors file (and optionally diff two of them).

  python bench/lora_check.py FILE [--diff OTHER]
Reports: tensor count, key families, dtypes, total params, non-finite count, all-zero tensors,
mean |w| per family, and (with --diff) how many tensors differ between two adapters.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict

import torch
from safetensors.torch import load_file


def stats(path):
    sd = load_file(path)
    fam = Counter(); zero = 0; nonfinite = 0; total = 0; absmean = defaultdict(list); dtypes = Counter()
    for k, t in sd.items():
        f = k.split(".")[-1] if "." in k else k
        fam[f] += 1
        dtypes[str(t.dtype)] += 1
        total += t.numel()
        tf = t.float()
        nonfinite += int((~torch.isfinite(tf)).sum())
        if tf.abs().max() == 0:
            zero += 1
        absmean[f].append(tf.abs().mean().item())
    return sd, {"tensors": len(sd), "families": dict(fam), "dtypes": dict(dtypes), "params": total,
                "non_finite": nonfinite, "all_zero_tensors": zero,
                "abs_mean_per_family": {k: sum(v) / len(v) for k, v in absmean.items()},
                "sample_keys": list(sd)[:4]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--diff")
    a = ap.parse_args()
    sd, s = stats(a.file)
    out = {"file": a.file, **s}
    if a.diff:
        sd2, s2 = stats(a.diff)
        common = [k for k in sd if k in sd2]
        differ = sum(1 for k in common if not torch.equal(sd[k], sd2[k]))
        maxd = max((float((sd[k].float() - sd2[k].float()).abs().max()) for k in common), default=0.0)
        out["diff"] = {"other": a.diff, "common": len(common), "tensors_differ": differ, "max_abs_diff": maxd,
                       "other_stats": {k: s2[k] for k in ("tensors", "params", "non_finite", "all_zero_tensors")}}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
