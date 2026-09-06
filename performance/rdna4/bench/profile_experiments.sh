#!/bin/bash
# Server-profile experiments: restart the bench server with a profile, run the workload set, stop.
# Usage: bash bench/profile_experiments.sh <profile> <set>[,<set>...]   sets: wan img ltx h3 ace train
cd "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4"
PY="L:/ComfyUI/.venv/Scripts/python.exe"
R="--results benchmark_results.csv"
P="$1"; SETS="$2"; TO="${3:-3600}"
run() { $PY bench/run_bench.py "$@" 2>&1 | tail -1; }
srv() { $PY bench/comfy_server.py "$@"; }

if [ -f raw/server_current/server.pid ]; then srv stop --run-dir raw/server_current; fi
for d in raw/server_*; do [ -f "$d/server.pid" ] && srv stop --run-dir "$d"; done
sleep 3
RD="raw/server_${P}_$(date +%H%M%S)"
srv start --profile "profiles/$P.json" --run-dir "$RD" --port 8190 --startup-timeout 400 || { echo "SERVER START FAILED $P"; exit 2; }
ln -sfn "$RD" raw/server_current 2>/dev/null
V="$P"
H="profile $P (see profiles/$P.json)"

WZ="1024x1024 8 steps res_multistep cfg1 Z-Image-Turbo bf16 + Qwen3-4B TE + FLUX ae"
WS="1024x1024 32 steps dpmpp_2m_sde_gpu karras cfg5 RealVisXL V4 fp16 + sdxl_vae"
WW="832x480 49 frames (3s@16fps) 4 steps (2 high + 2 low) euler simple cfg1 lightx2v LoRAs, Wan2.2 i2v 14B fp8_scaled x2 + UMT5 fp8 + wan_2.1_vae (fixed I2V graph), image 13_profile_left"
SW="--set 12.width=832 --set 12.height=480 --set 45.value=3.0 --set 10.image=13_profile_left_00001_.png"
W_LTX="1280x704-class 0.9MP 16:9, 73 frames (3s@24fps), 2-stage distilled (9+4 sigmas) euler_ancestral cfg1, LTX-2.5 22B INT8-ConvRot + Gemma4-12B INT8 TE + Gemma4-e2b enhancer + x2 latent upsampler + tiled VAE"
W_ACE="60 s stereo 48 kHz, 75 steps euler normal cfg4 shift3, ACE-Step 1.5 XL SFT bf16 + Qwen 0.6B/4B TE, LM audio codes on"
W_TR="Z-Image Base bf16 LoRA rank16 bf16, 8 optimizer updates x 4 accumulation (32 fwd/bwd), batch 1, grad ckpt depth1, AdamW 1e-4, 3-image bench dataset 1024^2"
W_H3="640x640 (0.4MP 1:1), 73 frames (3s@24fps), 20 steps res_multistep simple, no turbo LoRA, MiniMax H3 FL2VA INT8-ConvRot 21GB + Qwen3-VL-32B INT8 27GB TE + video VAE fp16 + audio VAE fp32, image 13_smile_closeup"

for S in ${SETS//,/ }; do
case "$S" in
  img)
    run --prompt api/IMG_ZTurbo.json --test-id IMG-ZT --variant $V --run-type cold --seed 1001 --set "6.seed=1001" --hypothesis "$H" --workload "$WZ" $R --out raw/IMG-ZT --timeout $TO
    for s in 1002 1003 1004; do run --prompt api/IMG_ZTurbo.json --test-id IMG-ZT --variant $V --run-type warm --seed $s --set "6.seed=$s" --hypothesis "$H" --workload "$WZ" $R --out raw/IMG-ZT --timeout $TO; done
    run --prompt api/IMG_SDXL.json --test-id IMG-SDXL --variant $V --run-type cold --seed 1001 --set "6.seed=1001" --hypothesis "$H" --workload "$WS" $R --out raw/IMG-SDXL --timeout $TO
    for s in 1002 1003 1004; do run --prompt api/IMG_SDXL.json --test-id IMG-SDXL --variant $V --run-type warm --seed $s --set "6.seed=$s" --hypothesis "$H" --workload "$WS" $R --out raw/IMG-SDXL --timeout $TO; done ;;
  wan)
    run --prompt api/WAN22_I2V_14B_fixed.json --test-id VID-WAN22 --variant $V --run-type cold --seed 1001 $SW --set "13.noise_seed=1001" --set "14.noise_seed=1001" --hypothesis "$H" --workload "$WW" $R --out raw/VID-WAN22 --timeout $TO
    for s in 1002 1003 1004; do run --prompt api/WAN22_I2V_14B_fixed.json --test-id VID-WAN22 --variant $V --run-type warm --seed $s $SW --set "13.noise_seed=$s" --set "14.noise_seed=$s" --hypothesis "$H" --workload "$WW" $R --out raw/VID-WAN22 --timeout $TO; done ;;
  ltx)
    run --prompt api/LTX25_T2V_short.json --test-id VID-LTX25 --variant $V --run-type cold --seed 1001 --set "405:339.noise_seed=1001" --set "405:338.noise_seed=1001" --hypothesis "$H" --workload "$W_LTX" $R --out raw/VID-LTX25 --timeout $TO
    for s in 1002 1003; do run --prompt api/LTX25_T2V_short.json --test-id VID-LTX25 --variant $V --run-type warm --seed $s --set "405:339.noise_seed=$s" --set "405:338.noise_seed=$s" --hypothesis "$H" --workload "$W_LTX" $R --out raw/VID-LTX25 --timeout $TO; done ;;
  ace)
    run --prompt api/ACE_XL_SFT_short.json --test-id MUS-ACE --variant $V --run-type cold --seed 1001 --set "109.value=1001" --hypothesis "$H" --workload "$W_ACE" $R --out raw/MUS-ACE --timeout $TO
    for s in 1002 1003; do run --prompt api/ACE_XL_SFT_short.json --test-id MUS-ACE --variant $V --run-type warm --seed $s --set "109.value=$s" --hypothesis "$H" --workload "$W_ACE" $R --out raw/MUS-ACE --timeout $TO; done ;;
  train)
    run --prompt api/TRAIN_ZImage_bench.json --test-id TRAIN-ZI --variant $V --run-type cold --seed 42 --hypothesis "$H" --workload "$W_TR" $R --out raw/TRAIN-ZI --timeout $TO
    run --prompt api/TRAIN_ZImage_bench.json --test-id TRAIN-ZI --variant $V --run-type warm --seed 43 --set "8.seed=43" --hypothesis "$H" --workload "$W_TR" $R --out raw/TRAIN-ZI --timeout $TO ;;
  h3)
    run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant $V --run-type cold --seed 1001 --set "105:15.noise_seed=1001" --hypothesis "$H" --workload "$W_H3" $R --out raw/VID-H3 --timeout $TO
    for s in 1002 1003; do run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant $V --run-type warm --seed $s --set "105:15.noise_seed=$s" --hypothesis "$H" --workload "$W_H3" $R --out raw/VID-H3 --timeout $TO; done ;;
esac
done
echo "PROFILE_DONE $P"
