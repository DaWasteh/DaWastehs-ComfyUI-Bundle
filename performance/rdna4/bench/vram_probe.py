"""Isolated, watchdog-guarded GPU memory / backward-kernel probes (no ComfyUI involved).

Written after the two 2026-09-05 system freezes at `Training LoRA: 0/32`. Hypothesis: the
training step oversubscribed VRAM and the Windows/WDDM driver spilled GPU allocations into
host memory instead of raising an OOM, until the host ran out of (non-paged) memory
(`WinError 10055`, registry flush failures, hard freeze).

Every probe runs the GPU work in a CHILD process. The parent samples host memory twice a
second (psutil + GetPerformanceInfo: commit, kernel non-paged pool) and kills the child as
soon as available RAM, commit headroom or the non-paged pool cross a limit, or on timeout.

Modes (run on the small card, --device 1 = RX 9070 XT, by default):
  oversub   allocate + fill 512 MiB chunks past the card's total VRAM (bounded by --max-over-gib)
            -> tells whether hipMalloc fails cleanly (OOM) or spills into shared system memory
  cap       same, but with torch.cuda.set_per_process_memory_fraction(--fraction) first
            -> verifies the allocator cap raises OOM *before* the driver can spill
  sdpa_bwd  bf16 SDPA forward+backward for flash / efficient / math backends (small shapes)
  ckpt_bwd  torch.utils.checkpoint(use_reentrant=False) around an attention+MLP block, backward

Usage:
  python vram_probe.py oversub --device 1 --max-over-gib 2 --log raw/vram_probe_oversub.jsonl
  python vram_probe.py cap --device 1 --fraction 0.8 --log raw/vram_probe_cap.jsonl
  python vram_probe.py sdpa_bwd --device 1 --fraction 0.8 --log raw/vram_probe_sdpa.jsonl
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

GIB = 2**30
MIB = 2**20


class PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("CommitTotal", ctypes.c_size_t),
        ("CommitLimit", ctypes.c_size_t),
        ("CommitPeak", ctypes.c_size_t),
        ("PhysicalTotal", ctypes.c_size_t),
        ("PhysicalAvailable", ctypes.c_size_t),
        ("SystemCache", ctypes.c_size_t),
        ("KernelTotal", ctypes.c_size_t),
        ("KernelPaged", ctypes.c_size_t),
        ("KernelNonpaged", ctypes.c_size_t),
        ("PageSize", ctypes.c_size_t),
        ("HandleCount", wt.DWORD),
        ("ProcessCount", wt.DWORD),
        ("ThreadCount", wt.DWORD),
    ]


def perf_info() -> dict:
    pi = PERFORMANCE_INFORMATION()
    pi.cb = ctypes.sizeof(pi)
    ok = ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), pi.cb)
    if not ok:
        return {}
    ps = pi.PageSize
    return {
        "commit_total": pi.CommitTotal * ps,
        "commit_limit": pi.CommitLimit * ps,
        "phys_total": pi.PhysicalTotal * ps,
        "phys_avail": pi.PhysicalAvailable * ps,
        "kernel_paged": pi.KernelPaged * ps,
        "kernel_nonpaged": pi.KernelNonpaged * ps,
    }


def host_snapshot() -> dict:
    d = perf_info()
    return {
        "t": time.time(),
        "avail_gib": round(d.get("phys_avail", 0) / GIB, 2),
        "commit_gib": round(d.get("commit_total", 0) / GIB, 2),
        "commit_limit_gib": round(d.get("commit_limit", 0) / GIB, 2),
        "nonpaged_gib": round(d.get("kernel_nonpaged", 0) / GIB, 3),
        "paged_gib": round(d.get("kernel_paged", 0) / GIB, 3),
    }


# ----------------------------------------------------------------------------- child probes

def _emit(log, **kw):
    kw.setdefault("t", time.time())
    line = json.dumps(kw)
    print(line, flush=True)
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def child_alloc(args, log):
    import torch

    dev = torch.device(f"cuda:{args.device}")
    props = torch.cuda.get_device_properties(args.device)
    total = props.total_memory
    if args.mode == "cap":
        torch.cuda.set_per_process_memory_fraction(args.fraction, args.device)
    free0, _ = torch.cuda.mem_get_info(args.device)
    _emit(log, event="start", mode=args.mode, device=args.device, name=props.name, total_mib=total // MIB,
          free_mib=free0 // MIB, fraction=args.fraction if args.mode == "cap" else None, host=host_snapshot())
    chunk = args.chunk_mib * MIB
    limit = total + args.max_over_gib * GIB
    keep = []
    allocated = 0
    while allocated < limit:
        try:
            t = torch.empty(chunk, dtype=torch.uint8, device=dev)
            t.fill_(1)
            torch.cuda.synchronize(dev)
            keep.append(t)
            allocated += chunk
        except RuntimeError as e:  # torch.OutOfMemoryError is a RuntimeError subclass
            msg = str(e).splitlines()[0][:300]
            _emit(log, event="oom", allocated_mib=allocated // MIB, over_total_mib=(allocated - total) // MIB,
                  error=msg, host=host_snapshot())
            break
        free, _ = torch.cuda.mem_get_info(args.device)
        _emit(log, event="chunk", allocated_mib=allocated // MIB, over_total_mib=(allocated - total) // MIB,
              free_mib=free // MIB, reserved_mib=torch.cuda.memory_reserved(args.device) // MIB,
              host=host_snapshot())
    else:
        _emit(log, event="limit_reached_without_oom", allocated_mib=allocated // MIB,
              over_total_mib=(allocated - total) // MIB, host=host_snapshot())
    del keep
    torch.cuda.empty_cache()
    _emit(log, event="end", host=host_snapshot())


def child_sdpa(args, log):
    import torch
    import torch.nn.functional as F
    from torch.nn.attention import SDPBackend, sdpa_kernel

    dev = torch.device(f"cuda:{args.device}")
    torch.cuda.set_per_process_memory_fraction(args.fraction, args.device)
    B, H, L, D = 1, 24, args.seq, 128
    _emit(log, event="start", mode="sdpa_bwd", device=args.device, shape=[B, H, L, D], host=host_snapshot())
    for name, backend in (("flash", SDPBackend.FLASH_ATTENTION), ("efficient", SDPBackend.EFFICIENT_ATTENTION),
                          ("math", SDPBackend.MATH)):
        torch.manual_seed(0)
        q = torch.randn(B, H, L, D, device=dev, dtype=torch.bfloat16, requires_grad=True)
        k = torch.randn(B, H, L, D, device=dev, dtype=torch.bfloat16, requires_grad=True)
        v = torch.randn(B, H, L, D, device=dev, dtype=torch.bfloat16, requires_grad=True)
        torch.cuda.reset_peak_memory_stats(args.device)
        t0 = time.time()
        try:
            with sdpa_kernel(backend):
                out = F.scaled_dot_product_attention(q, k, v)
                loss = out.float().square().mean()
                loss.backward()
            torch.cuda.synchronize(dev)
            ok = all(torch.isfinite(x.grad).all().item() for x in (q, k, v))
            _emit(log, event="backend", backend=name, ok=ok, seconds=round(time.time() - t0, 3),
                  loss=loss.item(), grad_absmean=q.grad.float().abs().mean().item(),
                  peak_mib=torch.cuda.max_memory_allocated(args.device) // MIB, host=host_snapshot())
        except Exception as e:
            _emit(log, event="backend", backend=name, ok=False, error=str(e).splitlines()[0][:300],
                  seconds=round(time.time() - t0, 3), host=host_snapshot())
        del q, k, v
        torch.cuda.empty_cache()
    _emit(log, event="end", host=host_snapshot())


def child_ckpt(args, log):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.utils.checkpoint

    dev = torch.device(f"cuda:{args.device}")
    torch.cuda.set_per_process_memory_fraction(args.fraction, args.device)
    dim, heads, L = 3072, 24, args.seq

    class Block(nn.Module):
        def __init__(self):
            super().__init__()
            self.n1 = nn.RMSNorm(dim)
            self.qkv = nn.Linear(dim, 3 * dim, bias=False)
            self.o = nn.Linear(dim, dim, bias=False)
            self.n2 = nn.RMSNorm(dim)
            self.up = nn.Linear(dim, 4 * dim, bias=False)
            self.down = nn.Linear(4 * dim, dim, bias=False)

        def forward(self, x):
            h = self.n1(x)
            q, k, v = self.qkv(h).view(x.shape[0], L, 3, heads, dim // heads).permute(2, 0, 3, 1, 4)
            a = F.scaled_dot_product_attention(q, k, v).transpose(1, 2).reshape(x.shape[0], L, dim)
            x = x + self.o(a)
            return x + self.down(F.silu(self.up(self.n2(x))))

    torch.manual_seed(0)
    blocks = nn.ModuleList([Block() for _ in range(args.layers)]).to(dev, torch.bfloat16)
    blocks.requires_grad_(False).train()
    # LoRA-like trainable adapters on the o projections (small), like TrainLoraNode does
    loras = [(nn.Parameter(torch.zeros(dim, 16, device=dev, dtype=torch.bfloat16)),
              nn.Parameter(torch.randn(16, dim, device=dev, dtype=torch.bfloat16) * 0.01)) for _ in blocks]
    for b, (a, bb) in zip(blocks, loras):
        orig = b.o.forward
        b.o.forward = (lambda o, a=a, bb=bb: (lambda x: o(x) + (x @ bb.t()) @ a.t()))(orig)
    x = torch.randn(1, L, dim, device=dev, dtype=torch.bfloat16)
    _emit(log, event="start", mode="ckpt_bwd", device=args.device, layers=args.layers, seq=L, dim=dim,
          host=host_snapshot())
    for variant in ("per_block", "whole", "none"):
        torch.cuda.reset_peak_memory_stats(args.device)
        t0 = time.time()
        try:
            with torch.autocast("cuda", dtype=torch.bfloat16):
                if variant == "per_block":
                    h = x
                    for b in blocks:
                        h = torch.utils.checkpoint.checkpoint(b, h, use_reentrant=False)
                elif variant == "whole":
                    def run_all(h):
                        for b in blocks:
                            h = b(h)
                        return h
                    h = torch.utils.checkpoint.checkpoint(run_all, x, use_reentrant=False)
                else:
                    h = x
                    for b in blocks:
                        h = b(h)
                loss = h.float().square().mean()
            loss.backward()
            torch.cuda.synchronize(dev)
            g = loras[0][0].grad
            _emit(log, event="variant", variant=variant, ok=bool(g is not None and torch.isfinite(g).all()),
                  seconds=round(time.time() - t0, 3), loss=loss.item(),
                  peak_mib=torch.cuda.max_memory_allocated(args.device) // MIB, host=host_snapshot())
        except Exception as e:
            _emit(log, event="variant", variant=variant, ok=False, error=str(e).splitlines()[0][:300],
                  peak_mib=torch.cuda.max_memory_allocated(args.device) // MIB, host=host_snapshot())
        for a, bb in loras:
            a.grad = None
            bb.grad = None
        torch.cuda.empty_cache()
    _emit(log, event="end", host=host_snapshot())


# ----------------------------------------------------------------------------- parent watchdog

def parent(args) -> int:
    log = args.log
    if log:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, __file__, args.mode, "--child", *sys.argv[2:]]
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    start = host_snapshot()
    _emit(log, event="watchdog_start", mode=args.mode, min_avail_gib=args.min_avail_gib,
          min_commit_headroom_gib=args.min_commit_headroom_gib, max_nonpaged_gib=args.max_nonpaged_gib,
          timeout=args.timeout, host=start)
    proc = subprocess.Popen(cmd, env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    t0 = time.time()
    reason = None
    peak = {"min_avail_gib": start["avail_gib"], "max_commit_gib": start["commit_gib"],
            "max_nonpaged_gib": start["nonpaged_gib"]}
    while proc.poll() is None:
        time.sleep(0.5)
        h = host_snapshot()
        peak["min_avail_gib"] = min(peak["min_avail_gib"], h["avail_gib"])
        peak["max_commit_gib"] = max(peak["max_commit_gib"], h["commit_gib"])
        peak["max_nonpaged_gib"] = max(peak["max_nonpaged_gib"], h["nonpaged_gib"])
        headroom = h["commit_limit_gib"] - h["commit_gib"]
        if h["avail_gib"] < args.min_avail_gib:
            reason = f"host available RAM {h['avail_gib']} GiB < {args.min_avail_gib}"
        elif headroom < args.min_commit_headroom_gib:
            reason = f"commit headroom {headroom:.1f} GiB < {args.min_commit_headroom_gib}"
        elif h["nonpaged_gib"] > args.max_nonpaged_gib:
            reason = f"non-paged pool {h['nonpaged_gib']} GiB > {args.max_nonpaged_gib}"
        elif time.time() - t0 > args.timeout:
            reason = f"timeout {args.timeout}s"
        if reason:
            _emit(log, event="watchdog_kill", reason=reason, host=h)
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            break
    rc = proc.wait(timeout=30)
    _emit(log, event="watchdog_end", returncode=rc, killed=reason, seconds=round(time.time() - t0, 1),
          host_peaks=peak, host=host_snapshot())
    return 0 if rc == 0 and not reason else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["oversub", "cap", "sdpa_bwd", "ckpt_bwd"])
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--device", type=int, default=1)
    ap.add_argument("--fraction", type=float, default=0.8)
    ap.add_argument("--chunk-mib", type=int, default=512)
    ap.add_argument("--max-over-gib", type=float, default=2.0)
    ap.add_argument("--seq", type=int, default=4096)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--log", default=None)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--min-avail-gib", type=float, default=12.0)
    ap.add_argument("--min-commit-headroom-gib", type=float, default=8.0)
    ap.add_argument("--max-nonpaged-gib", type=float, default=6.0)
    args = ap.parse_args()
    if not args.child:
        return parent(args)
    log = args.log
    if args.mode in ("oversub", "cap"):
        child_alloc(args, log)
    elif args.mode == "sdpa_bwd":
        child_sdpa(args, log)
    else:
        child_ckpt(args, log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
