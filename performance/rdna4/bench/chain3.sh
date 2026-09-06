#!/bin/bash
# Post-crash-2 continuation: NO TrainLoraNode runs. H3 baseline, then LTX E2 experiments. Fresh server per block.
source "l:/GitHub/DaWastehs-ComfyUI-Bundle/performance/rdna4/bench/lib.sh"
start_server v098_baseline
run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant v098_baseline --run-type cold --seed 1001 --set "105:15.noise_seed=1001" --workload "$W_H3" $R --out raw/VID-H3 --timeout 3600
for s in 1002 1003; do guard; run --prompt api/H3_I2V_user_short.json --test-id VID-H3 --variant v098_baseline --run-type warm --seed $s --set "105:15.noise_seed=$s" --workload "$W_H3" $R --out raw/VID-H3 --timeout 3600; done
start_server v098_baseline
H="E2-LTX: text encoders on gpu:1 (16 GB) are deep-cloned and partially loaded (0.9 s/token enhancer, 96 s negative encode); place CLIP on gpu:0"
for v in E2_allgpu0 E2b_clip0_vae1; do
  guard; run --prompt api/LTX25_T2V_short__$v.json --test-id VID-LTX25 --variant $v --run-type cold --seed 1001 --set "405:339.noise_seed=1001" --set "405:338.noise_seed=1001" --hypothesis "$H" --workload "$W_LTX" $R --out raw/VID-LTX25 --timeout 3000
  for s in 1002 1003; do guard; run --prompt api/LTX25_T2V_short__$v.json --test-id VID-LTX25 --variant $v --run-type warm --seed $s --set "405:339.noise_seed=$s" --set "405:338.noise_seed=$s" --hypothesis "$H" --workload "$W_LTX" $R --out raw/VID-LTX25 --timeout 3000; done
  start_server v098_baseline
done
echo CHAIN3_DONE
