#!/bin/bash
cd "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4"
PY="L:/ComfyUI/.venv/Scripts/python.exe"; R="--results benchmark_results.csv"
run() { $PY bench/run_bench.py "$@" 2>&1 | tail -1; }
W_LTX="1280x704-class 0.9MP 16:9, 73 frames (3s@24fps), 2-stage distilled (9+4 sigmas) euler_ancestral cfg1, LTX-2.5 22B INT8-ConvRot + Gemma4-12B INT8 TE + Gemma4-e2b enhancer + x2 latent upsampler + tiled VAE"
H="E2-LTX: text encoders on gpu:1 (16 GB) are deep-cloned and partially loaded (0.9 s/token enhancer, 96 s negative encode); place CLIP on gpu:0"
for v in E2_allgpu0 E2b_clip0_vae1; do
  run --prompt api/LTX25_T2V_short__$v.json --test-id VID-LTX25 --variant $v --run-type cold --seed 1001 --set "405:339.noise_seed=1001" --set "405:338.noise_seed=1001" --hypothesis "$H" --workload "$W_LTX" $R --out raw/VID-LTX25 --timeout 3000
  for s in 1002 1003; do run --prompt api/LTX25_T2V_short__$v.json --test-id VID-LTX25 --variant $v --run-type warm --seed $s --set "405:339.noise_seed=$s" --set "405:338.noise_seed=$s" --hypothesis "$H" --workload "$W_LTX" $R --out raw/VID-LTX25 --timeout 3000; done
done
echo LTX_EXPERIMENTS_DONE
