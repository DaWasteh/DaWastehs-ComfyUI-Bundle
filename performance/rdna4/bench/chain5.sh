#!/bin/bash
# Regression of the optimized workflow copies (converted from the real UI files) on the baseline profile.
source "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4/bench/lib.sh"
start_server v098_baseline
H="regression: optimized workflow copy (E1 no-unload / E2 placement / B1 fix) converted from performance/rdna4/workflows"
run --prompt api/opt/ACE_XL_SFT_opt.json --test-id MUS-ACE --variant opt_copy --run-type cold --seed 1001 --set "94.duration=60" --set "98.seconds=60" --set "109.value=1001" --hypothesis "$H" --workload "$W_ACE" $R --out raw/MUS-ACE --timeout 2400
for s in 1002 1003; do guard; run --prompt api/opt/ACE_XL_SFT_opt.json --test-id MUS-ACE --variant opt_copy --run-type warm --seed $s --set "94.duration=60" --set "98.seconds=60" --set "109.value=$s" --hypothesis "$H" --workload "$W_ACE" $R --out raw/MUS-ACE --timeout 2400; done
start_server v098_baseline
run --prompt api/opt/WAN22_I2V_14B_opt.json --test-id VID-WAN22 --variant opt_copy --run-type cold --seed 1001 $SW --set "13.noise_seed=1001" --set "14.noise_seed=1001" --hypothesis "$H" --workload "$WW" $R --out raw/VID-WAN22 --timeout 2400
for s in 1002 1003; do guard; run --prompt api/opt/WAN22_I2V_14B_opt.json --test-id VID-WAN22 --variant opt_copy --run-type warm --seed $s $SW --set "13.noise_seed=$s" --set "14.noise_seed=$s" --hypothesis "$H" --workload "$WW" $R --out raw/VID-WAN22 --timeout 2400; done
start_server v098_baseline
WF2="1024x1024 4 steps euler simple cfg1 FLUX.2 Klein 4B bf16 + Qwen3-4B TE + flux2 vae"
run --prompt api/IMG_FLUX2K4.json --test-id IMG-FLUX2K4 --variant v098_baseline --run-type cold --seed 1001 --set "6.seed=1001" --workload "$WF2" $R --out raw/IMG-FLUX2K4 --timeout 1200
for s in 1002 1003 1004; do guard; run --prompt api/IMG_FLUX2K4.json --test-id IMG-FLUX2K4 --variant v098_baseline --run-type warm --seed $s --set "6.seed=$s" --workload "$WF2" $R --out raw/IMG-FLUX2K4 --timeout 1200; done
start_server v098_baseline
run --prompt api/opt/IMG_FLUX2K4_opt.json --test-id IMG-FLUX2K4 --variant opt_copy --run-type cold --seed 1001 --set "6.seed=1001" --hypothesis "$H" --workload "$WF2" $R --out raw/IMG-FLUX2K4 --timeout 1200
for s in 1002 1003 1004; do guard; run --prompt api/opt/IMG_FLUX2K4_opt.json --test-id IMG-FLUX2K4 --variant opt_copy --run-type warm --seed $s --set "6.seed=$s" --hypothesis "$H" --workload "$WF2" $R --out raw/IMG-FLUX2K4 --timeout 1200; done
stop_server
echo CHAIN5_DONE
