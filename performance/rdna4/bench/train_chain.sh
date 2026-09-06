#!/bin/bash
# v1.1.2 · LoRA trainer validation chain. Every run: fresh bench server (v0.9.8 profile + repo VRAM
# guard through the probe), host-RAM watchdog on the server pid, identical workload:
# 3-image 1024^2 bench dataset, rank 16, batch 1, 2 optimizer updates x 4 accumulation (8 fwd/bwd).
# Usage: bash bench/train_chain.sh <spec>...   spec = ZI1 ZI2 SDXL1 SDXL2 FX2K1 FX2K2 FX11 FX12 BG1 BG2
source bench/lib.sh
PROFILE=v098_vramguard
guard_start() { RD=$(cat raw/server_current.txt); $PY bench/host_guard.py --run-dir "$RD" --log "$RD/host_guard.jsonl" --min-avail-gib 0 --min-commit-headroom-gib 6 & GUARD_PID=$!; }
guard_stop() { kill $GUARD_PID 2>/dev/null; wait $GUARD_PID 2>/dev/null; }
DS="lora_training/_rdna4_bench"
W_TR2="3-image bench dataset 1024^2, rank 16 bf16 LoRA, batch 1, 2 optimizer updates x 4 accumulation (8 fwd/bwd), AdamW 1e-4, MSE, grad ckpt"
# args: test-id prompt variant train-node dataset-node save-node depth extra-sets...
trun() {
  local tid=$1 prompt=$2 variant=$3 tn=$4 dn=$5 sn=$6 depth=$7; shift 7
  start_server $PROFILE; guard_start
  echo "### $tid $variant depth=$depth $(date +%H:%M:%S)"
  run --prompt "api/$prompt" --url http://127.0.0.1:8190 --test-id "$tid" --variant "$variant" --run-type validation \
      --hypothesis "VRAM guard + checkpoint_depth $depth" --workload "$W_TR2 depth$depth" $R --out "raw/$tid" --timeout 3000 \
      --set "$dn.folder=\"$DS\"" --set "$tn.steps=2" --set "$tn.grad_accumulation_steps=4" --set "$tn.checkpoint_depth=$depth" \
      --set "$sn.prefix=\"loras/rdna4_bench/${tid}_${variant}\"" "$@"
  guard_stop
  echo "host_guard: $(tail -1 $RD/host_guard.jsonl | cut -c1-300)"
  grep -a -E "Training LoRA|out of memory|OutOfMemory|Gradient checkpointing|loaded completely|Error|error" "$RD/server.log" | grep -v "DEPRECATION\|pin_memory" | tail -12
  stop_server
}
for spec in "$@"; do case $spec in
  ZI1)   trun TRAIN-ZI TRAIN_ZImage_bench.json guard_depth1 8 1 10 1 ;;
  ZI2)   trun TRAIN-ZI TRAIN_ZImage_bench.json guard_depth2 8 1 10 2 ;;
  SDXL1) trun TRAIN-SDXL TRAIN_SDXL.json guard_depth1 6 1 8 1 ;;
  SDXL2) trun TRAIN-SDXL TRAIN_SDXL.json guard_depth2 6 1 8 2 ;;
  FX2K1) trun TRAIN-FX2K4 TRAIN_FLUX2_Klein_4B_Base.json guard_depth1 8 1 10 1 ;;
  FX2K2) trun TRAIN-FX2K4 TRAIN_FLUX2_Klein_4B_Base.json guard_depth2 8 1 10 2 ;;
  FX11)  trun TRAIN-FX1 TRAIN_FLUX1_Dev.json guard_depth1 9 1 11 1 ;;
  FX12)  trun TRAIN-FX1 TRAIN_FLUX1_Dev.json guard_depth2 9 1 11 2 ;;
  BG1)   trun TRAIN-BOOGU TRAIN_Boogu_Image_Base.json guard_depth1 8 1 10 1 ;;
  BG2)   trun TRAIN-BOOGU TRAIN_Boogu_Image_Base.json guard_depth2 8 1 10 2 ;;
  *) echo "unknown spec $spec" ;;
esac; done
echo "### chain done $(date +%H:%M:%S)"
