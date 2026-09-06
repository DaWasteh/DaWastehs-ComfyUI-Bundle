"""E16: kernel-level micro-benchmark on gfx1201 (Windows ROCm): which linear path is fastest?

bf16 torch.nn.functional.linear (hipBLASLt)  vs  comfy-kitchen HIP WMMA int8_linear (tensorwise / convrot)
vs  torch._scaled_mm fp8 e4m3.  Shapes chosen from DiT transformer blocks (hidden 3072/4096, MLP 4x).
Run on the idle GPU:  HIP_VISIBLE_DEVICES=1 python bench/kernel_microbench.py
"""
from __future__ import annotations

import json
import sys
import time

import torch
import comfy_kitchen as ck

dev = "cuda"
print("device", torch.cuda.get_device_name(0), "torch", torch.__version__, "hipblaslt pref", torch.backends.cuda.preferred_blas_library())


def bench(fn, iters=10, warm=3):
    for _ in range(warm):
        fn()
    torch.cuda.synchronize()
    s, e = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    s.record()
    for _ in range(iters):
        fn()
    e.record()
    torch.cuda.synchronize()
    return s.elapsed_time(e) / iters / 1000.0


results = []
for M in (4096, 16384):
    for K, N in ((3072, 3072), (3072, 12288), (12288, 3072), (4096, 4096), (4096, 16384)):
        x = torch.randn(M, K, device=dev, dtype=torch.bfloat16)
        w = torch.randn(N, K, device=dev, dtype=torch.bfloat16) * 0.02
        flops = 2.0 * M * K * N
        ref = torch.nn.functional.linear(x, w)
        row = {"M": M, "K": K, "N": N}
        t = bench(lambda: torch.nn.functional.linear(x, w)); row["bf16_tflops"] = flops / t / 1e12
        try:
            qw, sc = ck.quantize_int8_tensorwise(w)
            out = ck.int8_linear(x, qw, sc, None, torch.bfloat16, convrot=False)
            t = bench(lambda: ck.int8_linear(x, qw, sc, None, torch.bfloat16, convrot=False))
            row["int8_tensorwise_tflops"] = flops / t / 1e12
            row["int8_tensorwise_relerr"] = float((out.float() - ref.float()).norm() / ref.float().norm())
        except Exception as ex:
            row["int8_tensorwise_err"] = f"{type(ex).__name__}: {str(ex)[:100]}"
        try:
            qwc, scc = ck.quantize_int8_convrot_weight(w, 256)
            out = ck.int8_linear(x, qwc, scc, None, torch.bfloat16, convrot=True, convrot_groupsize=256)
            t = bench(lambda: ck.int8_linear(x, qwc, scc, None, torch.bfloat16, convrot=True, convrot_groupsize=256))
            row["int8_convrot_tflops"] = flops / t / 1e12
            row["int8_convrot_relerr"] = float((out.float() - ref.float()).norm() / ref.float().norm())
        except Exception as ex:
            row["int8_convrot_err"] = f"{type(ex).__name__}: {str(ex)[:100]}"
        try:
            xs = x.abs().amax().float() / 448.0
            ws = w.abs().amax().float() / 448.0
            xf = (x.float() / xs).to(torch.float8_e4m3fn)
            wf = (w.float() / ws).to(torch.float8_e4m3fn)
            def fp8():
                return torch._scaled_mm(xf, wf.t(), scale_a=xs.reshape(1, 1), scale_b=ws.reshape(1, 1), out_dtype=torch.bfloat16)
            out = fp8()
            t = bench(fp8)
            row["fp8_scaled_mm_tflops"] = flops / t / 1e12
            row["fp8_relerr"] = float((out.float() - ref.float()).norm() / ref.float().norm())
        except Exception as ex:
            row["fp8_err"] = f"{type(ex).__name__}: {str(ex)[:100]}"
        results.append(row)
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}), flush=True)
        del x, w, ref
        torch.cuda.empty_cache()

# attention: SDPA at video-like sequence lengths (heads 24, dim 128)
for L in (4096, 16384, 32768):
    q = torch.randn(1, 24, L, 128, device=dev, dtype=torch.bfloat16)
    k = torch.randn_like(q); v = torch.randn_like(q)
    row = {"sdpa_L": L}
    for name, ctx in (("flash", torch.nn.attention.sdpa_kernel(torch.nn.attention.SDPBackend.FLASH_ATTENTION)),
                      ("mem_eff", torch.nn.attention.sdpa_kernel(torch.nn.attention.SDPBackend.EFFICIENT_ATTENTION)),
                      ("auto", torch.nn.attention.sdpa_kernel([torch.nn.attention.SDPBackend.FLASH_ATTENTION, torch.nn.attention.SDPBackend.EFFICIENT_ATTENTION, torch.nn.attention.SDPBackend.MATH]))):
        try:
            with ctx:
                t = bench(lambda: torch.nn.functional.scaled_dot_product_attention(q, k, v), iters=5, warm=2)
            row[f"{name}_ms"] = t * 1000
            row[f"{name}_tflops"] = 4.0 * L * L * 128 * 24 / t / 1e12
        except Exception as ex:
            row[f"{name}_err"] = f"{type(ex).__name__}: {str(ex)[:80]}"
    try:
        if ck.int8_attention_is_available():
            t = bench(lambda: ck.int8_attention(q, k, v), iters=5, warm=2)
            row["ck_int8_attn_ms"] = t * 1000
            ref = torch.nn.functional.scaled_dot_product_attention(q, k, v)
            out = ck.int8_attention(q, k, v)
            row["ck_int8_attn_relerr"] = float((out.float() - ref.float()).norm() / ref.float().norm())
    except Exception as ex:
        row["ck_int8_attn_err"] = f"{type(ex).__name__}: {str(ex)[:80]}"
    results.append(row)
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}), flush=True)
    del q, k, v
    torch.cuda.empty_cache()

json.dump(results, open(sys.argv[1] if len(sys.argv) > 1 else "raw/E16_kernel_microbench.json", "w"), indent=1)
