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

## Adaptive Load Image / Load Video

The same pack also provides:

- **Adaptive Load Image · Model Resolution**
- **Adaptive Load Video · Model Resolution**

The included browser extension follows downstream graph connections, displays the detected model profile in the node title, and keeps a manual profile dropdown. Model-native quality can be reduced to 75%, 50%, or 35% for drafts. Scaling preserves the full source aspect ratio, rounds to the model grid, and never crops. Video decoding remains lazy while audio, FPS, duration, and bit depth are preserved.

Automatic profiles cover SD 1.5, SDXL/FLUX, Qwen Image, Wan 2.x/Wan Animate 2, LTX Video, Hunyuan Video, SCAIL 2, and MiniMax H3. Unknown graphs use the documented general 1024 fallback until a manual profile is selected. Graphs connected to multiple detected model families are shown as ambiguous and also require a manual choice.

Tested with ComfyUI 0.33.0 at commit `7fe8a613`. The pack uses ComfyUI's current V3 `comfy_api.latest` interface and should be updated together with ComfyUI through the bundle updater.
