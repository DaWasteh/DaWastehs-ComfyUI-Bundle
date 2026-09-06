"""Aggregate benchmark_results.csv + raw records into markdown tables.

  python bench/summarize.py [--csv benchmark_results.csv] [--test IMG-ZT] [--nodes]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def fnum(x):
    try:
        return float(x)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="benchmark_results.csv")
    ap.add_argument("--test", default=None)
    ap.add_argument("--nodes", action="store_true", help="print per-node median durations")
    ap.add_argument("--include-cached", action="store_true")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    groups = defaultdict(list)
    for r in rows:
        if a.test and r["test_id"] != a.test:
            continue
        if r["status"] != "success":
            continue
        rt = r["run_type"]
        if rt.startswith("warm") and not a.include_cached:
            # skip fully cached runs (sampler never ran)
            if not r.get("sampler_span_s") or float(r["sampler_span_s"]) == 0:
                continue
        groups[(r["test_id"], r["variant"], "cold" if rt == "cold" else "warm")].append(r)
    print("| test | variant | type | n | wall s median | min..max | sampler s | s/step | gpu0 peak alloc GiB | gpu0 reserved | host avail after GiB |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    base = {}
    for key in sorted(groups):
        rs = groups[key]
        wall = [float(r["client_wall_s"]) for r in rs]
        samp = [fnum(r["sampler_span_s"]) or 0 for r in rs]
        sps = [fnum(r["s_per_step"]) for r in rs if fnum(r["s_per_step"])]
        g0 = [fnum(r["gpu0_peak_alloc_gib"]) or 0 for r in rs]
        g0r = [fnum(r["gpu0_peak_reserved_gib"]) or 0 for r in rs]
        ha = [fnum(r["host_ram_avail_after_gib"]) or 0 for r in rs]
        med = statistics.median(wall)
        if key[1] == "v098_baseline":
            base[(key[0], key[2])] = med
        rel = ""
        b = base.get((key[0], key[2]))
        if b and key[1] != "v098_baseline":
            rel = f" ({(1 - med / b) * 100:+.0f}% / x{b / med:.2f})"
        print(f"| {key[0]} | {key[1]} | {key[2]} | {len(rs)} | {med:.1f}{rel} | {min(wall):.1f}..{max(wall):.1f} | "
              f"{statistics.median(samp):.1f} | {statistics.median(sps):.3f} | {max(g0):.1f} | {max(g0r):.1f} | {min(ha):.1f} |"
              if sps else
              f"| {key[0]} | {key[1]} | {key[2]} | {len(rs)} | {med:.1f}{rel} | {min(wall):.1f}..{max(wall):.1f} | {statistics.median(samp):.1f} | - | {max(g0):.1f} | {max(g0r):.1f} | {min(ha):.1f} |")
    if a.nodes:
        print()
        for key in sorted(groups):
            per = defaultdict(list)
            for r in groups[key]:
                rec = json.load(open(r["record"], encoding="utf-8"))
                for nt in rec["node_times"]:
                    per[(str(nt["node"]), nt["class_type"])].append(nt["dur"])
            top = sorted(((statistics.median(v), k) for k, v in per.items()), reverse=True)[:8]
            print(f"{key}: " + ", ".join(f"{k[1]}#{k[0]} {m:.1f}s" for m, k in top if m >= 0.3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
