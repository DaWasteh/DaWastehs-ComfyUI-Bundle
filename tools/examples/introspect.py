"""List the user-facing knobs of every workflow: prompts, sizes, seeds, media loaders and outputs.

Usage: python tools/examples/introspect.py <object_info.json> [filter] > table.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTE_TYPES = {"MarkdownNote", "Note", "PixaromaNote", "PixaromaLabel"}
LOADERS = {"LoadImage", "LoadAudio", "LoadVideo", "PixaromaLoadImage", "VHS_LoadVideo", "AILab_LoadImage",
           "LoadImageMask", "VHS_LoadAudioUpload", "LoadImageOutput", "Load3D"}
OUTPUT_HINT = ("Save", "Preview", "VideoCombine", "ShowText", "PreviewAny", "Compare")


def widget_names(info: dict, node: dict) -> list[str]:
    spec = info.get(node["type"])
    if not spec:
        return []
    names = []
    order = spec.get("input_order") or {}
    inputs = spec.get("input") or {}
    for section in ("required", "optional"):
        keys = order.get(section) or list((inputs.get(section) or {}).keys())
        for key in keys:
            desc = (inputs.get(section) or {}).get(key)
            if desc is None:
                continue
            kind = desc[0]
            opts = desc[1] if len(desc) > 1 and isinstance(desc[1], dict) else {}
            if opts.get("forceInput"):
                continue
            if isinstance(kind, list) or kind in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO") or (
                    isinstance(kind, str) and kind.startswith("COMFY_") and False):
                names.append(key)
                if key in ("seed", "noise_seed") or opts.get("control_after_generate"):
                    names.append("control_after_generate")
    return names


def nodes_of(wf: dict):
    for n in wf.get("nodes", []):
        yield "", n
    for sg in (wf.get("definitions") or {}).get("subgraphs") or []:
        for n in sg.get("nodes", []):
            yield sg.get("name") or sg.get("id"), n


def describe(info: dict, path: Path) -> list[str]:
    wf = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for sg, n in nodes_of(wf):
        t = n["type"]
        if t in NOTE_TYPES:
            continue
        wv = n.get("widgets_values")
        names = widget_names(info, n)
        vals = {}
        if isinstance(wv, list):
            for i, v in enumerate(wv):
                key = names[i] if i < len(names) else f"#{i}"
                vals[key] = v
        elif isinstance(wv, dict):
            vals = wv
        interesting = {}
        for k, v in vals.items():
            if k in ("seed", "noise_seed", "width", "height", "steps", "cfg", "text", "value", "image", "audio", "video",
                     "file", "megapixels", "resolution", "duration", "seconds", "length", "frames", "batch_size",
                     "denoise", "sampler_name", "scheduler", "prompt", "lyrics", "tags", "frame_rate", "fps",
                     "filename_prefix", "upscale_by", "scale_by", "shift", "guidance", "num_frames", "size"):
                interesting[k] = v if not isinstance(v, str) else v[:70].replace("\n", " ")
        mode = n.get("mode", 0)
        flag = {0: "", 2: " [MUTED]", 4: " [BYPASS]"}.get(mode, f" [mode{mode}]")
        is_loader = t in LOADERS
        is_output = any(h in t for h in OUTPUT_HINT) or (info.get(t, {}).get("output_node"))
        prompt = ""
        if t == "PixaromaPrompt":
            prompt = ((n.get("properties") or {}).get("promptState") or {}).get("text", "")[:70].replace("\n", " ")
        if interesting or is_loader or is_output or prompt or t == "PixaromaPrompt":
            tag = "LOAD " if is_loader else ("OUT  " if is_output else "     ")
            sgp = f"[{sg}] " if sg else ""
            title = n.get("title") or ""
            extra = f" prompt='{prompt}'" if prompt else ""
            lines.append(f"  {tag}{sgp}{n['id']} {t} '{title}'{flag} {json.dumps(interesting, ensure_ascii=False)}{extra}")
    return lines


def main() -> int:
    info = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    flt = sys.argv[2] if len(sys.argv) > 2 else ""
    for path in sorted((ROOT / "workflows").rglob("*.json")):
        rel = path.relative_to(ROOT / "workflows").as_posix()
        if flt and flt not in rel:
            continue
        print(rel)
        for line in describe(info, path):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
