# Pinned official workflow templates

These four files were copied byte-for-byte from `comfyui-workflow-templates-json 0.1.43`, installed with ComfyUI `0.32.0`, on 2026-08-13. They are committed so dual-GPU generation remains deterministic when the locally installed template package changes.

| Template | SHA-256 |
|---|---|
| `video_ltx2_5_t2v.json` | `b8ab11a3cb349bf6dccd9ad09307213e0088d833d1867270d23e1f794bab6a9d` |
| `video_ltx2_5_i2v.json` | `bcd3239835e8e5bf287a664954c253c67cd31147a4a4193ef5975525e246a7a0` |
| `video_ltx2_5_flf2v.json` | `d93d8d6c63279e15c81d8e81595031449530628a5e4f3644b5ef53b3b345d113` |
| `video_wan_animate2.json` | `772a7dfce6d5b61b8f838ec0609211a0c9b1c04a7c64e26d05f0852f147edac7` |

Upstream project: [Comfy-Org/workflow_templates](https://github.com/Comfy-Org/workflow_templates). The generated bundle workflows localize model paths, add the repository timer, official MODEL/CLIP/VAE selectors, one central DaWasteh device control, and generated parameter notes/layout.
