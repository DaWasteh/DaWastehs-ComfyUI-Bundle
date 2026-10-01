#!/usr/bin/env python3
"""v1.3.1: rebuild the two text-to-image workflows whose checkpoints were filed as SDXL.

``moodyRealMix_zitV4DPO.safetensors`` holds only a Z-Image Turbo diffusion model (453 tensors, same key set as
``z_image_turbo_bf16``) and ``ultrarealFineTune_v4.safetensors`` only a FLUX.1-dev diffusion model (FP8 e4m3, same key
set as the FLUX.1 fp8 UNets). The old SDXL graphs asked the checkpoint for CLIP and VAE, which these files do not have,
so they could not run. Each fix starts from the tested base workflow of its architecture and swaps only the model
loader for ``CheckpointLoaderSimple`` (MODEL output only), so the files stay where they are.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

try:
    from tools.rodent_layout import refresh_topology_hashes
except ModuleNotFoundError:  # run from inside tools/
    from rodent_layout import refresh_topology_hashes

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / "workflows"

FIXES = [
    {
        "target": "Text to Image/SDXL_moodyRealMix_zitV4DPO-Text-to-Image.json",
        "base": "Text to Image/ZImage_turbo-Text-to-Image.json",
        "ckpt": "SDXL\\moodyRealMix_zitV4DPO.safetensors",
        "prefix": "WF_ZImage_Turbo_moodyRealMix_zitV4DPO",
        "settings": (
            "=== MoodyRealMix zitV4 (DPO) · Z-Image-Turbo-Finetune ===\n\n"
            "Kein SDXL-Modell: die Datei enthält nur ein Z-Image-Turbo-Diffusionsmodell (6B, BF16).\n"
            "Der Checkpoint-Loader liefert deshalb nur MODEL; Text-Encoder und VAE kommen aus eigenen Loadern.\n\n"
            "Steps: 8 (wie Z-Image Turbo). CFG: 1.0, Negativ wirkungslos.\n"
            "Sampler: res_multistep / simple. Auflösung: 1024+ (min. 512).\n\n"
            "Encoder: qwen_3_4b (CLIPLoader type 'lumina2'). VAE: FLUX/ae.safetensors."),
        "models": (
            "**MoodyRealMix zitV4 DPO (Z-Image-Turbo-Finetune)**\n\n"
            "- checkpoints: `SDXL/moodyRealMix_zitV4DPO.safetensors` (liegt im SDXL-Ordner, ist aber Z-Image Turbo)\n"
            "- text_encoders: `Qwen/qwen_3_4b.safetensors`\n"
            "- vae: `FLUX/ae.safetensors`\n\n**8 Steps, CFG 1.0.**"),
    },
    {
        "target": "Text to Image/SDXL_ultrarealFineTune_v4-Text-to-Image.json",
        "base": "Text to Image/FLUX1_dev_fp8-Text-to-Image.json",
        "ckpt": "SDXL\\ultrarealFineTune_v4.safetensors",
        "prefix": "WF_FLUX1_Dev_ultrarealFineTune_v4",
        "settings": (
            "=== UltraReal FineTune v4 · FLUX.1-dev-Finetune ===\n\n"
            "Kein SDXL-Modell: die Datei enthält nur ein FLUX.1-dev-Diffusionsmodell (12B, FP8 e4m3).\n"
            "Der Checkpoint-Loader liefert deshalb nur MODEL; clip_l + t5xxl und die FLUX-VAE kommen aus eigenen Loadern.\n\n"
            "Auflösung: 1024x1024 (oder 1216x832 / 832x1216).\n"
            "Steps 25, CFG 1 (distilliert), Guidance 3.5, euler / simple.\n"
            "ModelSamplingFlux: Breite/Höhe wie das Latent."),
        "models": (
            "**UltraReal FineTune v4 (FLUX.1-dev-Finetune, FP8)**\n\n"
            "- checkpoints: `SDXL/ultrarealFineTune_v4.safetensors` (liegt im SDXL-Ordner, ist aber FLUX.1 dev)\n"
            "- clip: `clip_l.safetensors` + `T5/t5xxl_fp8_e4m3fn.safetensors`\n"
            "- vae: `FLUX/ae.safetensors`"),
    },
]


def _note(nodes, prefix):
    for node in nodes:
        if node["type"] in ("Note", "MarkdownNote") and (node.get("title") or "").startswith(prefix):
            return node
    raise KeyError(prefix)


def _path(rel: str) -> Path:
    """Paths are the v1.3.0 names; after the v1.3.1 rename the files are found through the rename map.

    The map comes first: on a case-insensitive file system the old name of a case-only rename (FLUX1_dev_fp8 ->
    FLUX1_Dev_FP8) still "exists"."""
    renames = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
    return WF / renames.get(rel, rel)


def build(fix: dict, base: dict | None = None, old: dict | None = None) -> dict:
    """Finetune graph = base graph (``base``) with the finetune loader.

    Keeps the identity of the old file (``old``): its id and the provenance ``extra.dawasteh_dual_gpu.family`` /
    ``.source``, which name the workflow itself (v1.3.0 name), not the base graph it is rebuilt from."""
    base = base if base is not None else json.loads(_path(fix["base"]).read_text(encoding="utf-8"))
    old = old if old is not None else json.loads(_path(fix["target"]).read_text(encoding="utf-8"))
    wf = copy.deepcopy(base)
    wf["id"] = old["id"]
    identity = (old.get("extra") or {}).get("dawasteh_dual_gpu") or {}
    gpu = (wf.get("extra") or {}).get("dawasteh_dual_gpu")
    if isinstance(gpu, dict):
        gpu.update({key: identity[key] for key in ("family", "source") if key in identity})
    loader = next(n for n in wf["nodes"] if n["id"] == 1)
    assert loader["type"] == "UNETLoader", loader["type"]
    model_links = loader["outputs"][0]["links"]
    loader["type"] = "CheckpointLoaderSimple"
    loader["title"] = "Checkpoint (nur MODEL · Finetune)"
    loader["widgets_values"] = [fix["ckpt"]]
    loader["inputs"] = []
    loader["outputs"] = [
        {"name": "MODEL", "type": "MODEL", "links": model_links, "slot_index": 0},
        {"name": "CLIP", "type": "CLIP", "links": None},
        {"name": "VAE", "type": "VAE", "links": None},
    ]
    loader["properties"] = {**loader.get("properties", {}), "Node name for S&R": "CheckpointLoaderSimple"}
    _note(wf["nodes"], "⚙️ Einstellungen")["widgets_values"] = [fix["settings"]]
    _note(wf["nodes"], "📥 Modelle")["widgets_values"] = [fix["models"]]
    explain = next(n for n in wf["nodes"] if n["type"] in ("Note", "MarkdownNote")
                   and (n.get("title") or "").endswith("· Node 1"))
    explain["title"] = "Erklärung · Checkpoint (nur MODEL · Finetune) · Node 1"
    explain["widgets_values"] = [
        "# Erklärung · Checkpoint (nur MODEL · Finetune) · Node 1\n\n"
        "**Zweck:** Lädt das Finetune aus dem Checkpoint-Ordner. Die Datei enthält nur das Diffusionsmodell, "
        "deshalb bleiben die Ausgänge CLIP und VAE unverbunden.\n\n**Einstellbare Werte**\n"
        f"- `ckpt_name` = `{fix['ckpt']}` — Ein anderes Finetune derselben Architektur funktioniert genauso; "
        "SDXL-Checkpoints brauchen einen SDXL-Workflow."]
    save = next(n for n in wf["nodes"] if n["type"] == "SaveImage")
    save["widgets_values"] = [fix["prefix"]]
    for node in wf["nodes"]:
        if node["type"] in ("Note", "MarkdownNote") and "Speichern" in (node.get("title") or ""):
            text = node["widgets_values"][0]
            node["widgets_values"] = [text.replace(json.loads(json.dumps(base_prefix(base))), fix["prefix"])]
    refresh_topology_hashes(wf)  # the RODENT marker pins the loader and the note texts
    return wf


def base_prefix(base: dict) -> str:
    return next(n for n in base["nodes"] if n["type"] == "SaveImage")["widgets_values"][0]


PROMPT_MANIFEST = ROOT / "tools" / "pixaroma_prompt_manifest.json"


def sync_prompt_manifest(manifest: dict) -> bool:
    """The Pixaroma prompt targets of a rebuilt finetune are those of its base graph (same prompt nodes).

    tools/pixaroma_prompt_manifest.json keys the workflows by their current names; returns whether it changed."""
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    changed = False
    for fix in FIXES:
        target = entries["workflows/" + _path(fix["target"]).relative_to(WF).as_posix()]
        base = entries["workflows/" + _path(fix["base"]).relative_to(WF).as_posix()]
        if target.get("targets") != base.get("targets"):
            target["targets"] = copy.deepcopy(base.get("targets", []))
            changed = True
    return changed


def main() -> int:
    for fix in FIXES:
        wf = build(fix)
        target = _path(fix["target"])
        target.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote", target.relative_to(ROOT).as_posix())
    manifest = json.loads(PROMPT_MANIFEST.read_text(encoding="utf-8"))
    if sync_prompt_manifest(manifest):  # same one-line style as tools/integrate_pixaroma_prompts.py writes
        PROMPT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n",
                                   encoding="utf-8")
        print("updated", PROMPT_MANIFEST.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
