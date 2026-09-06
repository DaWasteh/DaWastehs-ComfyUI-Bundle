"""Rebuild benchmark_results.csv from the raw per-run JSON records (single source of truth).

  python bench/rebuild_csv.py [--csv benchmark_results.csv]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path

FIELDS = ["run_id", "test_id", "variant", "run_type", "hypothesis", "workload", "seed", "status", "cached_nodes_n",
          "client_wall_s", "server_exec_s", "loader_nodes_s", "sampler_span_s", "s_per_step", "steps",
          "gpu0_peak_alloc_gib", "gpu0_peak_reserved_gib", "gpu1_peak_alloc_gib", "gpu1_peak_reserved_gib",
          "os_gpu_peak_gib", "host_ram_avail_before_gib", "host_ram_avail_after_gib", "swap_used_after_gib",
          "outputs", "attention", "argv", "env_hipblaslt", "record"]
LOADERS = ("UNETLoader", "CLIPLoader", "VAELoader", "CheckpointLoaderSimple", "DualCLIPLoader", "LoraLoaderModelOnly",
           "LoraLoader", "UnetLoaderGGUF", "CLIPLoaderGGUF", "LatentUpscaleModelLoader")


def row_from_record(r: dict, path: str) -> dict:
    step_stats = r.get("step_stats") or {}
    sampler_nodes = sorted(step_stats.items(), key=lambda kv: -(kv[1]["span_s"] or 0))
    main_sampler = sampler_nodes[0][1] if sampler_nodes else {}
    load_time = sum(nt["dur"] for nt in r.get("node_times", []) if nt.get("class_type") in LOADERS)
    mem0, mem1 = r.get("host_before", {}), r.get("host_after", {})
    return {
        "run_id": r["run_id"], "test_id": r["test_id"], "variant": r["variant"], "run_type": r["run_type"],
        "hypothesis": r.get("hypothesis", ""), "workload": r.get("workload", ""), "seed": r.get("seed"),
        "status": r["status"], "cached_nodes_n": len(r.get("cached_nodes") or []),
        "client_wall_s": round(r["client_wall_s"], 3),
        "server_exec_s": round(r["server_exec_s"], 3) if r.get("server_exec_s") else "",
        "loader_nodes_s": round(load_time, 3),
        "sampler_span_s": round(main_sampler.get("span_s", 0) or 0, 3),
        "s_per_step": round(main_sampler["s_per_step"], 4) if main_sampler.get("s_per_step") else "",
        "steps": main_sampler.get("max", ""),
        "gpu0_peak_alloc_gib": round((r.get("gpu0_peak_alloc") or 0) / 2**30, 3),
        "gpu0_peak_reserved_gib": round((r.get("gpu0_peak_reserved") or 0) / 2**30, 3),
        "gpu1_peak_alloc_gib": round((r.get("gpu1_peak_alloc") or 0) / 2**30, 3),
        "gpu1_peak_reserved_gib": round((r.get("gpu1_peak_reserved") or 0) / 2**30, 3),
        "os_gpu_peak_gib": json.dumps({k: round(v / 2**30, 2) for k, v in (r.get("os_gpu_dedicated_peak_bytes") or {}).items()}),
        "host_ram_avail_before_gib": round(mem0.get("ram_available", 0) / 2**30, 2),
        "host_ram_avail_after_gib": round(mem1.get("ram_available", 0) / 2**30, 2),
        "swap_used_after_gib": round(mem1.get("swap_used", 0) / 2**30, 2),
        "outputs": ";".join(o.get("path", o.get("filename", "")) for o in r.get("outputs", [])),
        "attention": r.get("attention_function"),
        "argv": " ".join((r.get("server_argv") or [])[1:]),
        "env_hipblaslt": (r.get("profile_env") or {}).get("TORCH_BLAS_PREFER_HIPBLASLT"),
        "record": path,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="benchmark_results.csv")
    a = ap.parse_args()
    rows = []
    for f in sorted(glob.glob("raw/*/*.json")):
        if f.endswith(".prompt.json") or "server_" in f:
            continue
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if "run_id" not in r:
            continue
        rows.append(row_from_record(r, f))
    rows.sort(key=lambda x: x["run_id"].rsplit("_", 1)[-1])
    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {a.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
