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
