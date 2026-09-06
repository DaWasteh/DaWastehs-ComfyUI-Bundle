# shared helpers for benchmark chains (source this)
cd "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4"
PY="L:/ComfyUI/.venv/Scripts/python.exe"; R="--results benchmark_results.csv"
run() { $PY bench/run_bench.py "$@" 2>&1 | tail -1; }
stop_server() { for d in raw/server_*; do [ -f "$d/server.pid" ] && $PY bench/comfy_server.py stop --run-dir "$d"; done; sleep 3; }
start_server() { # $1 = profile name
  stop_server; local rd="raw/server_$1_$(date +%H%M%S)"
  $PY bench/comfy_server.py start --profile "profiles/$1.json" --run-dir "$rd" --port 8190 --startup-timeout 400 || { echo "SERVER START FAILED $1"; exit 2; }
  echo "$rd" > raw/server_current.txt; CUR_PROFILE="$1"; }
guard() { $PY bench/mem_guard.py || { echo "mem_guard -> restarting server ($CUR_PROFILE)"; start_server "$CUR_PROFILE"; }; }
WZ="1024x1024 8 steps res_multistep cfg1 Z-Image-Turbo bf16 + Qwen3-4B TE + FLUX ae"
WS="1024x1024 32 steps dpmpp_2m_sde_gpu karras cfg5 RealVisXL V4 fp16 + sdxl_vae"
WW="832x480 49 frames (3s@16fps) 4 steps (2 high + 2 low) euler simple cfg1 lightx2v LoRAs, Wan2.2 i2v 14B fp8_scaled x2 + UMT5 fp8 + wan_2.1_vae (fixed I2V graph), image 13_profile_left"
SW="--set 12.width=832 --set 12.height=480 --set 45.value=3.0 --set 10.image=13_profile_left_00001_.png"
W_LTX="1280x704-class 0.9MP 16:9, 73 frames (3s@24fps), 2-stage distilled (9+4 sigmas) euler_ancestral cfg1, LTX-2.5 22B INT8-ConvRot + Gemma4-12B INT8 TE + Gemma4-e2b enhancer + x2 latent upsampler + tiled VAE"
W_ACE="60 s stereo 48 kHz, 75 steps euler normal cfg4 shift3, ACE-Step 1.5 XL SFT bf16 + Qwen 0.6B/4B TE, LM audio codes on"
W_TR="Z-Image Base bf16 LoRA rank16 bf16, 8 optimizer updates x 4 accumulation (32 fwd/bwd), batch 1, grad ckpt depth1, AdamW 1e-4, 3-image bench dataset 1024^2"
W_H3="640x640 (0.4MP 1:1), 73 frames (3s@24fps), 20 steps res_multistep simple, no turbo LoRA, MiniMax H3 FL2VA INT8-ConvRot 21GB + Qwen3-VL-32B INT8 27GB TE + video VAE fp16 + audio VAE fp32, image 13_smile_closeup"
