#!/bin/bash
# E1/E2 on image workflows (same server, same seeds as baseline warm runs 1002-1004).
cd "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4"
PY="L:/ComfyUI/.venv/Scripts/python.exe"
R="--results benchmark_results.csv"
run() { $PY bench/run_bench.py "$@" 2>&1 | tail -1; }
WZ="1024x1024 8 steps res_multistep cfg1 Z-Image-Turbo bf16 + Qwen3-4B TE + FLUX ae"
WS="1024x1024 32 steps dpmpp_2m_sde_gpu karras cfg5 RealVisXL V4 fp16 + sdxl_vae"
for v in E1_nounload E1b_noop E2_allgpu0 E12_nounload_allgpu0; do
  H="E1: VRAM_Debug unload_all_models costs a reload per run; E2: CLIP/VAE on gpu:1 forces deepclone + dead-model gc"
  run --prompt api/IMG_ZTurbo__$v.json --test-id IMG-ZT --variant $v --run-type cold --seed 1001 --set "6.seed=1001" --hypothesis "$H" --workload "$WZ" $R --out raw/IMG-ZT --timeout 1800
  for s in 1002 1003 1004; do run --prompt api/IMG_ZTurbo__$v.json --test-id IMG-ZT --variant $v --run-type warm --seed $s --set "6.seed=$s" --hypothesis "$H" --workload "$WZ" $R --out raw/IMG-ZT --timeout 1800; done
done
for v in E2_allgpu0; do
  run --prompt api/IMG_SDXL__$v.json --test-id IMG-SDXL --variant $v --run-type cold --seed 1001 --set "6.seed=1001" --hypothesis "E2 all on gpu:0" --workload "$WS" $R --out raw/IMG-SDXL --timeout 1800
  for s in 1002 1003 1004; do run --prompt api/IMG_SDXL__$v.json --test-id IMG-SDXL --variant $v --run-type warm --seed $s --set "6.seed=$s" --hypothesis "E2 all on gpu:0" --workload "$WS" $R --out raw/IMG-SDXL --timeout 1800; done
done
# baseline warm repeat after experiments (drift check)
for s in 1002 1003; do run --prompt api/IMG_ZTurbo.json --test-id IMG-ZT --variant v098_baseline --run-type warm-repeat --seed $s --set "6.seed=$s" --workload "$WZ" $R --out raw/IMG-ZT --timeout 1800; done
echo IMG_EXPERIMENTS_DONE
