#!/bin/bash
# Server-profile experiments (fresh server per profile, memory guard between runs).
source "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4/bench/lib.sh"
wan_set() { V="$1"; H="$2"; TO="${3:-2400}"
  run --prompt api/WAN22_I2V_14B_fixed.json --test-id VID-WAN22 --variant $V --run-type cold --seed 1001 $SW --set "13.noise_seed=1001" --set "14.noise_seed=1001" --hypothesis "$H" --workload "$WW" $R --out raw/VID-WAN22 --timeout $TO
  for s in 1002 1003 1004; do guard; run --prompt api/WAN22_I2V_14B_fixed.json --test-id VID-WAN22 --variant $V --run-type warm --seed $s $SW --set "13.noise_seed=$s" --set "14.noise_seed=$s" --hypothesis "$H" --workload "$WW" $R --out raw/VID-WAN22 --timeout $TO; done; }
img_set() { V="$1"; H="$2"; TO="${3:-1200}"
  run --prompt api/IMG_ZTurbo__E12_nounload_allgpu0.json --test-id IMG-ZT --variant "${V}+E12" --run-type cold --seed 1001 --set "6.seed=1001" --hypothesis "$H" --workload "$WZ" $R --out raw/IMG-ZT --timeout $TO
  for s in 1002 1003 1004; do guard; run --prompt api/IMG_ZTurbo__E12_nounload_allgpu0.json --test-id IMG-ZT --variant "${V}+E12" --run-type warm --seed $s --set "6.seed=$s" --hypothesis "$H" --workload "$WZ" $R --out raw/IMG-ZT --timeout $TO; done
  run --prompt api/IMG_SDXL__E2_allgpu0.json --test-id IMG-SDXL --variant "${V}+E2" --run-type cold --seed 1001 --set "6.seed=1001" --hypothesis "$H" --workload "$WS" $R --out raw/IMG-SDXL --timeout $TO
  for s in 1002 1003 1004; do guard; run --prompt api/IMG_SDXL__E2_allgpu0.json --test-id IMG-SDXL --variant "${V}+E2" --run-type warm --seed $s --set "6.seed=$s" --hypothesis "$H" --workload "$WS" $R --out raw/IMG-SDXL --timeout $TO; done; }
flux_set() { V="$1"; H="$2"; TO="${3:-1200}"; WF="1024x1024 FLUX.1-dev fp8 (legacy fp8_e4m3fn unet, no quant metadata) + t5xxl fp8 + clip_l, E12 prompt (no unload, all gpu:0)"
  FLUX_SEED1001="--set 7.seed=1001"
  run --prompt api/IMG_FLUX1fp8__E12.json --test-id IMG-FLUX1FP8 --variant $V --run-type cold --seed 1001 $FLUX_SEED1001 --hypothesis "$H" --workload "$WF" $R --out raw/IMG-FLUX1FP8 --timeout $TO
  for s in 1002 1003 1004; do guard; run --prompt api/IMG_FLUX1fp8__E12.json --test-id IMG-FLUX1FP8 --variant $V --run-type warm --seed $s $(echo "$FLUX_SEED1001" | sed "s/1001/$s/g") --hypothesis "$H" --workload "$WF" $R --out raw/IMG-FLUX1FP8 --timeout $TO; done; }
h3_set() { V="$1"; H="$2"; TO="${3:-3600}"
  run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant $V --run-type cold --seed 1001 --set "105:15.noise_seed=1001" --hypothesis "$H" --workload "$W_H3" $R --out raw/VID-H3 --timeout $TO
  for s in 1002 1003; do guard; run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant $V --run-type warm --seed $s --set "105:15.noise_seed=$s" --hypothesis "$H" --workload "$W_H3" $R --out raw/VID-H3 --timeout $TO; done; }
start_server v098_baseline; flux_set v098_baseline "reference for E4 on the baseline profile"
start_server E3_reserve1;   wan_set E3_reserve1 "E3: reserve-vram 1 -> both 14B fp8 models (2x13.6 GB) resident, no reload per run"
start_server E4_fp8mm;      flux_set E4_fp8mm "E4: --fast fp8_matrix_mult (torch._scaled_mm) for legacy fp8 checkpoints; fp8_scaled models already use native fp8 (SUPPORT_FP8_OPS=True)"
start_server E14_cacheclassic; wan_set E14_cacheclassic "E14: --cache-classic avoids RAM-pressure eviction of loader outputs"
start_server E9_hipblas;    img_set E9_hipblas "E9: classic hipBLAS vs hipBLASLt on gfx1201"
start_server E15_expseg;    wan_set E15_expseg "E15: expandable_segments allocator"
start_server E8_ckattn;     wan_set E8_ckattn "E8: comfy-kitchen INT8 attention (quality trade-off, compare PSNR)"; h3_set E8_ckattn "E8 on MiniMax H3 (sampling-bound, 6 s/step)"
start_server E7_dynvram;    img_set E7_dynvram "E7: DynamicVRAM (aimdo 0.5.2) re-test" 900; wan_set E7_dynvram "E7: DynamicVRAM re-test" 900
stop_server
echo CHAIN4_DONE
