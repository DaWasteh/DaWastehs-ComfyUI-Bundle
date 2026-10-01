# DaWasteh Multi-GPU Device Control

Adds one central ComfyUI node with three linkable device dropdowns:

- `model_device` — diffusion/UNET placement
- `clip_device` — CLIP and text-encoder placement
- `vae_device` — image, video, and audio VAE placement

The node returns `COMBO` values and deliberately delegates the real placement to ComfyUI's official `Select Model Device`, `Select CLIP Device`, and `Select VAE Device` nodes.

## Defaults for Pandaking

```text
model_device = gpu:0  # AMD Radeon AI PRO R9700 · 32 GB
clip_device  = gpu:1  # AMD Radeon RX 9070 XT · 16 GB
vae_device   = gpu:1  # AMD Radeon RX 9070 XT · 16 GB
```

Change the three dropdowns before queuing a workflow. Every connected selector follows the central values, including selectors inside exposed subgraphs. `default` restores the loader's original placement. `cpu` is available for MODEL and CLIP diagnostics but is intentionally not offered for VAE, matching ComfyUI's official selector.

The node does not pool VRAM and does not make graph branches execute in parallel.

## Compute dtype after Select Model Device (v1.3.1)

ComfyUI's core **Select Model Device** re-derives the compute dtype after moving a model but ignores the dtypes the model supports: FP8 weights always got float16. Qwen Image (Edit) overflows in float16 and saves a black image. The pack patches that function at start-up (`compute_dtype.py`): if ComfyUI's choice is not supported by the model, it picks from the model's own list (bfloat16 for Qwen Image), exactly like ComfyUI's loader. Models that support float16 (FLUX, FLUX.2, Krea 2, WAN …) are unchanged. `DAWASTEH_COMPUTE_DTYPE_FIX=0` disables the patch. Reported upstream as [ComfyUI #16682](https://github.com/Comfy-Org/ComfyUI/issues/16682).

## Read-only model loading (v1.3.1)

On Windows/ROCm, ComfyUI's safetensors loading maps every file copy-on-write, and Windows charges the whole file to the system commit at once, on top of every VRAM allocation. FLUX.2 dev FP8 mixed with the bf16 Mistral encoder (2 × 33 GiB) drove the commit to 159 GiB on a 47 GB machine. The pack routes `load_torch_file` for safetensors of 1 GiB and more through a read-only mapping (`readonly_load.py`): identical tensors in identical (sorted) order – measured byte-identical on real files – but no commit charge (Klein 9B KV FP8: 9.16 GiB → 0.02 GiB). Any error falls back to ComfyUI's loader. `DAWASTEH_READONLY_SAFETENSORS=0` disables it, `DAWASTEH_READONLY_SAFETENSORS_MIN_GIB` changes the threshold.

## SAM3 text encoder on another GPU (v1.3.1)

Select CLIP Device moves a CLIP by reloading it from the checkpoint. For SAM3 / SAM 3.1 the text encoder weights are only collected while the image model is processed, and the model-config base class answers the missing attribute with `None`: the reload failed with "'NoneType' object has no attribute 'keys'". `sam3_reload.py` collects them from the checkpoint in that case; the normal load path is unchanged. `DAWASTEH_SAM3_RELOAD_FIX=0` disables it. Reported upstream as [ComfyUI #16675](https://github.com/Comfy-Org/ComfyUI/issues/16675).

## Adaptive Load Image / Load Video

The same pack also provides:

- **Adaptive Load Image · Model Resolution**
- **Adaptive Load Video · Model Resolution**

The included browser extension follows downstream graph connections, displays the detected model profile in the node title, and keeps a manual profile dropdown. Model-native quality can be reduced to 75%, 50%, or 35% for drafts. Scaling preserves the full source aspect ratio, rounds to the model grid, and never crops. Video decoding remains lazy while audio, FPS, duration, and bit depth are preserved.

Automatic profiles cover SD 1.5, SDXL/FLUX, Qwen Image, Wan 2.x/Wan Animate 2, LTX Video, Hunyuan Video, SCAIL 2, and MiniMax H3. Unknown graphs use the documented general 1024 fallback until a manual profile is selected. Graphs connected to multiple detected model families are shown as ambiguous and also require a manual choice.

Tested with ComfyUI 0.33.0 at commit `7fe8a613`. The pack uses ComfyUI's current V3 `comfy_api.latest` interface and should be updated together with ComfyUI through the bundle updater.
