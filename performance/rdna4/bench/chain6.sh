#!/bin/bash
# E8 (comfy-kitchen INT8 attention) on WAN + H3, then E7 DynamicVRAM screening. Fresh server per profile.
source "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4/bench/lib.sh"
start_server E8_ckattn
H="E8: --use-ck-attention (INT8 QK attention, comfy-kitchen HIP), quality trade-off -> compare PSNR to baseline seeds"
run --prompt api/WAN22_I2V_14B_fixed.json --test-id VID-WAN22 --variant E8_ckattn --run-type cold --seed 1001 $SW --set "13.noise_seed=1001" --set "14.noise_seed=1001" --hypothesis "$H" --workload "$WW" $R --out raw/VID-WAN22 --timeout 1800
for s in 1002 1003; do guard; run --prompt api/WAN22_I2V_14B_fixed.json --test-id VID-WAN22 --variant E8_ckattn --run-type warm --seed $s $SW --set "13.noise_seed=$s" --set "14.noise_seed=$s" --hypothesis "$H" --workload "$WW" $R --out raw/VID-WAN22 --timeout 1800; done
start_server E8_ckattn
run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant E8_ckattn --run-type cold --seed 1001 --set "105:15.noise_seed=1001" --hypothesis "$H" --workload "$W_H3" $R --out raw/VID-H3 --timeout 2400
for s in 1002 1003; do guard; run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant E8_ckattn --run-type warm --seed $s --set "105:15.noise_seed=$s" --hypothesis "$H" --workload "$W_H3" $R --out raw/VID-H3 --timeout 2400; done
start_server E7_dynvram
H7="E7: DynamicVRAM (comfy-aimdo 0.5.2) re-test, screening with 900 s timeout"
run --prompt api/IMG_ZTurbo__E12_nounload_allgpu0.json --test-id IMG-ZT --variant E7_dynvram+E12 --run-type cold --seed 1001 --set "6.seed=1001" --hypothesis "$H7" --workload "$WZ" $R --out raw/IMG-ZT --timeout 900
for s in 1002 1003; do guard; run --prompt api/IMG_ZTurbo__E12_nounload_allgpu0.json --test-id IMG-ZT --variant E7_dynvram+E12 --run-type warm --seed $s --set "6.seed=$s" --hypothesis "$H7" --workload "$WZ" $R --out raw/IMG-ZT --timeout 900; done
start_server E7_dynvram
run --prompt api/WAN22_I2V_14B_fixed.json --test-id VID-WAN22 --variant E7_dynvram --run-type cold --seed 1001 $SW --set "13.noise_seed=1001" --set "14.noise_seed=1001" --hypothesis "$H7" --workload "$WW" $R --out raw/VID-WAN22 --timeout 900
for s in 1002 1003; do guard; run --prompt api/WAN22_I2V_14B_fixed.json --test-id VID-WAN22 --variant E7_dynvram --run-type warm --seed $s $SW --set "13.noise_seed=$s" --set "14.noise_seed=$s" --hypothesis "$H7" --workload "$WW" $R --out raw/VID-WAN22 --timeout 900; done
stop_server
echo CHAIN6_DONE
