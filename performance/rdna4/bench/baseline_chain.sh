#!/bin/bash
# Sequential baselines for LTX 2.5, ACE-Step, LoRA training, MiniMax H3 (short forms). Serial GPU use only.
cd "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4"
PY="L:/ComfyUI/.venv/Scripts/python.exe"
R="--results benchmark_results.csv"
run() { $PY bench/run_bench.py "$@" 2>&1 | tail -1; }
W_LTX="1280x704-class 0.9MP 16:9, 73 frames (3s@24fps), 2-stage distilled (9+4 sigmas) euler_ancestral cfg1, LTX-2.5 22B INT8-ConvRot + Gemma4-12B INT8 TE + Gemma4-e2b enhancer + x2 latent upsampler + tiled VAE"
run --prompt api/LTX25_T2V_short.json --test-id VID-LTX25 --variant v098_baseline --run-type cold --seed 1001 --set "405:339.noise_seed=1001" --set "405:338.noise_seed=1001" --workload "$W_LTX" $R --out raw/VID-LTX25 --timeout 3000
for s in 1002 1003; do run --prompt api/LTX25_T2V_short.json --test-id VID-LTX25 --variant v098_baseline --run-type warm --seed $s --set "405:339.noise_seed=$s" --set "405:338.noise_seed=$s" --workload "$W_LTX" $R --out raw/VID-LTX25 --timeout 3000; done
W_ACE="60 s stereo 48 kHz, 75 steps euler normal cfg4 shift3, ACE-Step 1.5 XL SFT bf16 + Qwen 0.6B/4B TE, LM audio codes on"
run --prompt api/ACE_XL_SFT_short.json --test-id MUS-ACE --variant v098_baseline --run-type cold --seed 1001 --set "109.value=1001" --workload "$W_ACE" $R --out raw/MUS-ACE --timeout 3000
for s in 1002 1003; do run --prompt api/ACE_XL_SFT_short.json --test-id MUS-ACE --variant v098_baseline --run-type warm --seed $s --set "109.value=$s" --workload "$W_ACE" $R --out raw/MUS-ACE --timeout 3000; done
W_TR="Z-Image Base bf16 LoRA rank16 bf16, 8 optimizer updates x 4 accumulation (32 fwd/bwd), batch 1, grad ckpt depth1, AdamW 1e-4, 3-image bench dataset 1024^2"
run --prompt api/TRAIN_ZImage_bench.json --test-id TRAIN-ZI --variant v098_baseline --run-type cold --seed 42 --workload "$W_TR" $R --out raw/TRAIN-ZI --timeout 3000
run --prompt api/TRAIN_ZImage_bench.json --test-id TRAIN-ZI --variant v098_baseline --run-type warm --seed 43 --set "8.seed=43" --workload "$W_TR" $R --out raw/TRAIN-ZI --timeout 3000
W_H3="640x640 (0.4MP 1:1), 73 frames (3s@24fps), 20 steps res_multistep simple, no turbo LoRA, MiniMax H3 FL2VA INT8-ConvRot 21GB + Qwen3-VL-32B INT8 27GB TE + video VAE fp16 + audio VAE fp32, image 13_smile_closeup"
run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant v098_baseline --run-type cold --seed 1001 --set "105:15.noise_seed=1001" --workload "$W_H3" $R --out raw/VID-H3 --timeout 3600
for s in 1002 1003; do run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant v098_baseline --run-type warm --seed $s --set "105:15.noise_seed=$s" --workload "$W_H3" $R --out raw/VID-H3 --timeout 3600; done
echo CHAIN_DONE
