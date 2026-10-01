"""Build examples/ (per-workflow folders with README.md, screenshot, inputs and outputs) and the gallery data of the
GitHub Pages site from the staged runs of runner.py.

  L:/ComfyUI/.venv/Scripts/python.exe tools/examples/build_gallery.py [--only substring]

Media: images become WebP (full resolution, quality 86) plus a small thumbnail; the output of each workflow's main
example keeps ComfyUI's workflow metadata inside its full-resolution WebP (loadable by drag and drop). Videos stay
MP4/H.264 (re-encoded only when large or not H.264), audio stays MP3 (other formats are converted), 3D models
stay GLB (meshopt + WebP textures for the web viewer, geometry unchanged).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import CATALOG  # noqa: E402
from workflow_meta import META  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WF_DIR = ROOT / "workflows"
EXAMPLES = ROOT / "examples"
WORK = Path("L:/ComfyUI/tmp/examples-v131")
RUNS = WORK / "runs"
MODELS = Path("L:/ComfyUI/ComfyUI/models")
RENAMES = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
INVERSE = {v: k for k, v in RENAMES.items()}
REPO = "DaWasteh/DaWastehs-ComfyUI-Bundle"
GIB = 2**30

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # pragma: no cover
    from runner import FFMPEG as _RUNNER_FFMPEG  # the ComfyUI venv's imageio-ffmpeg binary
    FFMPEG = shutil.which("ffmpeg") or _RUNNER_FFMPEG

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
# UI text of housekeeping nodes (free-memory readouts, timers) is not an example output
NOISE_TEXT_TYPES = {"VRAM_Debug", "PixaromaRunTimer", "DaWMultiGPUDeviceControl"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".gif"}
AUDIO_EXT = {".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a"}
MODEL_EXT = {".glb", ".gltf"}
GPU_TOTAL = {"AMD Radeon AI PRO R9700": 31.9, "AMD Radeon RX 9070 XT": 15.9}
GPU_SHORT = {"AMD Radeon AI PRO R9700": "R9700", "AMD Radeon RX 9070 XT": "RX 9070 XT"}

# Same prompts, seed and size across quantisations or variants of one model (shown on the quant page).
FAMILIES = [
    ("flux1-dev", "FLUX.1 dev · FP8 vs. GGUF Q6_K vs. abliterated Q8_0", "1024 × 1024",
     ["Text to Image/FLUX1_dev_fp8-Text-to-Image.json", "Text to Image/FLUX1_dev_Q6_K-Text-to-Image.json",
      "Text to Image/FLUX1_dev_abliterated_Q8-Text-to-Image.json"],
     "Dasselbe FLUX.1-dev-Grundmodell in drei Dateiformaten; die abliterated-Version ist zusätzlich nachtrainiert und hat eine LoRA."),
    ("flux1-finetunes", "FLUX.1-Finetunes", "1024 × 1024",
     ["Text to Image/FLUX1_dev_fp8-Text-to-Image.json", "Text to Image/SDXL_ultrarealFineTune_v4-Text-to-Image.json",
      "Text to Image/FLUX1_EclecticEuphoria_Libre_v2-Text-to-Image.json",
      "Text to Image/FLUX1_EclecticEuphoria_Distilled_v2-Text-to-Image.json",
      "Text to Image/FLUX1_Kontext_dev-Text-to-Image.json"],
     "FLUX.1 dev im Vergleich zu Community-Finetunes und zu Kontext dev ohne Eingabebild."),
    ("flux2-klein-9b", "FLUX.2 Klein 9B · KV FP8 vs. GGUF Q6_K vs. DARE-Merge BF16", "1024 × 1024",
     ["Text to Image/FLUX2_Klein_9b_kv_fp8-Text-to-Image.json", "Text to Image/FLUX2_Klein_9b_Q6_K-Text-to-Image.json",
      "Text to Image/FLUX2_Klein_9b_dare_merged-Text-to-Image.json"],
     "Klein 9B als offizielles FP8, als GGUF Q6_K und als Community-Merge in BF16 – jeweils 8 Schritte."),
    ("flux2-klein-4b", "FLUX.2 Klein 4B · destilliert vs. Base", "1024 × 1024",
     ["Text to Image/FLUX2_Klein_4b-Text-to-Image.json", "Text to Image/FLUX2_Klein_base_4b-Text-to-Image.json"],
     "Destilliertes Klein 4B (4 Schritte) gegen das Basismodell (24 Schritte)."),
    ("flux2-dev", "FLUX.2 dev · FP8 mixed vs. FP8 mixed v2 vs. GGUF Q6_K", "1024 × 1024",
     ["Text to Image/FLUX2_dev_fp8mixed-Text-to-Image.json", "Text to Image/FLUX2_dev_fp8mixed_v2-Text-to-Image.json",
      "Text to Image/FLUX2_dev_Q6_K-Text-to-Image.json"],
     "Das 32B-Modell in zwei FP8-mixed-Fassungen und als GGUF Q6_K (mit FP8-Text-Encoder)."),
    ("krea2", "Krea 2 · Raw BF16 vs. Turbo FP8 vs. Raw + Turbo-LoRA", "1024 × 1024",
     ["Text to Image/Krea2_raw-Text-to-Image.json", "Text to Image/Krea2_turbo-Low-VRAM-Text-to-Image.json",
      "Text to Image/Krea2_turbo_via_LoRA-Text-to-Image.json",
      "Text to Image/Krea2_turbo-Extra-Pass-Text-to-Image.json"],
     "Krea 2 als langsames Raw-Modell, als Turbo in FP8, als Raw mit Turbo-LoRA und Turbo mit Extra-Durchgang."),
    ("zimage", "Z-Image · Base vs. Turbo vs. MoodyRealMix", "1024 × 1024",
     ["Text to Image/ZImage_base-Text-to-Image.json", "Text to Image/ZImage_turbo-Text-to-Image.json",
      "Text to Image/SDXL_moodyRealMix_zitV4DPO-Text-to-Image.json"],
     "Z-Image Base (40 Schritte, CFG 4), Turbo (8 Schritte) und ein Turbo-Finetune."),
    ("boogu", "Boogu · Base vs. Turbo-LoRA", "1024 × 1024",
     ["Text to Image/Boogu_image_base-Text-to-Image.json", "Text to Image/Boogu_turbo_via_LoRA-Text-to-Image.json"],
     "50 Schritte mit CFG gegen 4 Schritte mit Turbo-LoRA."),
    ("longcat", "LongCat Image · Base vs. Turbo", "1024 × 1024",
     ["Text to Image/LongCat_image-Text-to-Image.json", "Text to Image/LongCat_image_turbo-Text-to-Image.json"],
     "20 Schritte mit CFG gegen die destillierte 4-Schritt-Variante."),
    ("anima", "Anima · Base vs. Hoseki Lustrous Mix", "1024 × 1024",
     ["Text to Image/Anima_base_v1-Text-to-Image.json", "Text to Image/Anima_hosekiLustrousmix_v10-Text-to-Image.json"],
     "Basismodell gegen Community-Finetune."),
    ("ltx23-t2v", "LTX-2.3 22B · dev GGUF Q8_0 vs. dev MXFP8 vs. distilled FP8 vs. distilled MXFP8", None,
     ["Text to Video/LTX23_dev_Q8_GGUF-Text-to-Video.json", "Text to Video/LTX23_dev_mxfp8-Text-to-Video.json",
      "Text to Video/LTX23_distilled_fp8-Text-to-Video.json", "Text to Video/LTX23_distilled_mxfp8-Text-to-Video.json"],
     "Gleicher Prompt und Seed; dev mit 28 Schritten und CFG 3, distilled mit 8 Schritten und CFG 1.",
     [("fox", "Fuchs im Schnee")]),
    ("wan22-i2v", "WAN 2.2 I2V 14B · FP8 + LightX2V-LoRA vs. GGUF Q8_0 (LightX2V eingebacken)", None,
     ["Text+Image to Video/WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json",
      "Text+Image to Video/WAN22_i2v_14B_Q8_GGUF_lightx2v-Text+Image-to-Video.json"],
     "Gleiches Startbild, gleicher Prompt und Seed, jeweils 4 Schritte.", [("lake", "Bergsee")]),
    ("ace-xl", "ACE-Step 1.5 XL SFT · BF16 vs. INT8", None,
     ["Music Generation/ACE-Step1_5_XL_SFT-Music-Generation.json",
      "Music Generation/ACE-Step1_5_XL_SFT_INT8_ConvRot-Music-Generation.json"],
     "Gleiche Tags, gleicher Songtext, gleicher Seed.", [("pop", "Pop · englisch"), ("rock", "Indie-Rock · deutsch")]),
    ("stable-audio3", "Stable Audio 3 Medium · FP32 vs. INT8", None,
     ["Music Generation/StableAudio3_Medium-Audio-Generation.json",
      "Music Generation/StableAudio3_Medium_INT8_ConvRot-Audio-Generation.json"],
     "Gleiche Beschreibung, Länge und Seed.", [("orchestra", "Musik · Orchester"), ("rain", "Geräusch · Regen")]),
    ("klein-inpaint", "FLUX.2 Klein · 4B BF16 vs. 9B KV FP8 · Inpainting", None,
     ["Image Inpainting/FLUX2_Klein_4B-Inpaint.json", "Image Inpainting/FLUX2_Klein_9B_KV-Inpaint.json"],
     "Gleiches Bild, gleiche Haar-Maske, gleicher Prompt und Seed.", [("hair", "Haarfarbe · Maske")]),
    ("yue-7b", "YuE 7B · FP16 vs. INT8", None,
     ["Music Generation/YuE_7B-FP16_R9700-Music-Generation.json", "Music Generation/YuE_7B-INT8_R9700-Music-Generation.json"],
     "Gleiche Genre-Tags, gleicher Songtext, gleicher Seed.", [("pop", "Pop · englisch")]),
]

QUANT_TOKENS = [
    (r"iq4_xs", "IQ4_XS (GGUF)"), (r"q8_0", "Q8_0 (GGUF)"), (r"(?<![a-z])q8(?![a-z0-9])", "Q8_0 (GGUF)"),
    (r"q6_k", "Q6_K (GGUF)"), (r"q5_k_m", "Q5_K_M (GGUF)"), (r"mxfp8", "MXFP8"), (r"fp8mixed|fp8_mixed", "FP8 mixed"),
    (r"fp4_mixed|fp4", "FP4 mixed"), (r"int8", "INT8"), (r"fp8", "FP8"), (r"bf16", "BF16"), (r"fp16", "FP16"),
    (r"fp32", "FP32"),
]
DTYPE_LABEL = {"BF16": "BF16", "F16": "FP16", "F32": "FP32", "F8_E4M3": "FP8", "F8_E5M2": "FP8 (E5M2)", "I8": "INT8"}
ROLE = {
    "UNETLoader": "Diffusionsmodell", "UnetLoaderGGUF": "Diffusionsmodell", "DaWVUReadOnlyUNETLoader": "Diffusionsmodell",
    "CheckpointLoaderSimple": "Modell", "ImageOnlyCheckpointLoader": "Modell", "DaWMV2LoadModel": "Diffusionsmodell",
    "CLIPLoader": "Text-Encoder / LLM", "DualCLIPLoader": "Text-Encoder", "DaWVUReadOnlyCLIPLoader": "Text-Encoder",
    "DualCLIPLoaderGGUF": "Text-Encoder", "LTXAVTextEncoderLoader": "Text-Encoder", "DaWMV2EncodeScenes": "Text-Encoder",
    "DaWH3PromptOnce": "Text-Encoder", "VAELoader": "VAE", "VAELoaderKJ": "VAE", "LTXVAudioVAELoader": "Audio-VAE",
    "LoraLoaderModelOnly": "LoRA", "LoraLoader": "LoRA", "UpscaleModelLoader": "Upscaler",
    "LatentUpscaleModelLoader": "Latent-Upscaler", "CLIPVisionLoader": "Vision-Encoder", "ModelPatchLoader": "Modell-Patch",
    "AudioEncoderLoader": "Audio-Encoder", "IPAdapterModelLoader": "IP-Adapter", "ControlNetLoader": "ControlNet",
    "LoadMoGeModel": "Tiefenschätzung", "LoadBackgroundRemovalModel": "Freisteller", "LoadDA3Model": "Tiefenschätzung",
    "MelBandRoFormerModelLoader": "Quellentrennung", "MMAudioSuiteModelLoader": "Video→Audio",
    "MMAudioSuiteFeatureUtilsLoader": "Hilfsmodelle", "UltralyticsDetectorProvider": "Detektor",
    "MinimaxH3LatentUpscaler3D": "Latent-Upscaler", "MMH3LatentUpscaleWithModelParams": "Latent-Upscaler",
    "YuE2TrainingDataset": "Modell", "YuE2LoRATrainer": "Modell", "YUE_Stage_A_Loader": "Modell",
}
MODEL_RE = re.compile(r"\.(safetensors|gguf|ckpt|pt|pth|bin|sft)$", re.I)


# ------------------------------------------------------------------------------------------------------------ utils
def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.+-]+", "_", text).strip("_")


def wid(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def old_of(rel: str) -> str:
    return INVERSE.get(rel, rel)


def new_of(old: str) -> str:
    return RENAMES.get(old, old)


_model_index: dict[str, Path] | None = None


def model_index() -> dict[str, Path]:
    global _model_index
    if _model_index is None:
        _model_index = {}
        for root, _dirs, files in os.walk(MODELS):
            for f in files:
                _model_index.setdefault(f, Path(root) / f)
    return _model_index


_dtype_cache: dict[str, str | None] = {}


def dtype_of(path: Path) -> str | None:
    key = str(path)
    if key in _dtype_cache:
        return _dtype_cache[key]
    label = None
    try:
        with open(path, "rb") as fh:
            n = struct.unpack("<Q", fh.read(8))[0]
            header = json.loads(fh.read(n))
        count: dict[str, int] = {}
        for k, v in header.items():
            if k == "__metadata__":
                continue
            size = 1
            for s in v["shape"]:
                size *= s
            count[v["dtype"]] = count.get(v["dtype"], 0) + size
        top = max(count, key=count.get)
        label = DTYPE_LABEL.get(top, top)
    except Exception:
        label = None
    _dtype_cache[key] = label
    return label


def quant_of(name: str, path: Path | None) -> str | None:
    low = name.lower()
    for pattern, label in QUANT_TOKENS:
        if re.search(pattern, low):
            return label
    if path and path.suffix == ".safetensors":
        return dtype_of(path)
    return None


def workflow_models(wf: dict) -> list[dict]:
    seen, out = set(), []
    nodes = list(wf.get("nodes", []))
    for sg in (wf.get("definitions") or {}).get("subgraphs") or []:
        nodes += sg.get("nodes", [])
    for node in nodes:
        if node.get("mode", 0) in (2, 4):
            continue
        values = node.get("widgets_values")
        values = values if isinstance(values, list) else list(values.values()) if isinstance(values, dict) else []
        for v in values:
            if not isinstance(v, str) or not MODEL_RE.search(v):
                continue
            name = v.replace("\\", "/").split("/")[-1]
            if name in seen:
                continue
            seen.add(name)
            path = model_index().get(name)
            out.append({"name": name, "role": ROLE.get(node["type"], "Modell"), "quant": quant_of(name, path),
                        "gib": round(path.stat().st_size / GIB, 2) if path else None})
    return out


SAMPLER_KEYS = {"KSampler": ["steps", "cfg", "sampler_name", "scheduler", "denoise"],
                "KSamplerAdvanced": ["steps", "cfg", "sampler_name", "scheduler"],
                "BasicScheduler": ["scheduler", "steps", "denoise"], "KSamplerSelect": ["sampler_name"],
                "CFGGuider": ["cfg"], "ModelSamplingAuraFlow": ["shift"], "ModelSamplingSD3": ["shift"],
                "FluxGuidance": ["guidance"]}
WIDGET_ORDER = {"KSampler": ["seed", "control", "steps", "cfg", "sampler_name", "scheduler", "denoise"],
                "KSamplerAdvanced": ["add_noise", "seed", "control", "steps", "cfg", "sampler_name", "scheduler"],
                "BasicScheduler": ["scheduler", "steps", "denoise"], "KSamplerSelect": ["sampler_name"],
                "CFGGuider": ["cfg"], "ModelSamplingAuraFlow": ["shift"], "ModelSamplingSD3": ["shift", "multiplier"],
                "FluxGuidance": ["guidance"], "CLIPTextEncodeFlux": ["clip_l", "t5xxl", "guidance"]}


def workflow_settings(wf: dict) -> dict:
    """Sampler settings and negative prompt of simple (single-sampler, top-level) workflows."""
    found: dict[str, list] = {}
    negative = None
    for node in wf.get("nodes", []):
        if node.get("mode", 0) in (2, 4):
            continue
        t, title, values = node["type"], node.get("title") or "", node.get("widgets_values")
        if t in WIDGET_ORDER and isinstance(values, list):
            named = dict(zip(WIDGET_ORDER[t], values))
            for key in SAMPLER_KEYS.get(t, []) + (["guidance"] if t == "CLIPTextEncodeFlux" and "Positiv" in title else []):
                if key in named:
                    found.setdefault(key, []).append(named[key])
        if re.search(r"negativ", title, re.I):
            text = ""
            if t == "CLIPTextEncode" and isinstance(values, list) and values:
                text = values[0]
            elif t == "PixaromaPrompt":
                text = ((node.get("properties") or {}).get("promptState") or {}).get("text", "")
            if isinstance(text, str) and text.strip():
                negative = text.strip()
    out = {k: v[0] for k, v in found.items() if len(set(map(str, v))) == 1}
    if negative:
        out["negative"] = negative
    return out


def primary_quant(new_name: str) -> str | None:
    model_part = new_name.split("-")[0]
    for token in ("IQ4_XS", "Q8_0", "Q6_K", "MXFP8", "FP8mixed_V2", "FP8mixed", "FP8", "INT8", "BF16", "FP16", "FP32"):
        if re.search(rf"(^|_){re.escape(token)}(_|\+|$)", model_part):
            return {"FP8mixed_V2": "FP8 mixed v2", "FP8mixed": "FP8 mixed", "Q8_0": "GGUF Q8_0", "Q6_K": "GGUF Q6_K",
                    "IQ4_XS": "GGUF IQ4_XS"}.get(token, token)
    return None


def kind_of(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in MODEL_EXT:
        return "model"
    return None


def newer(src: Path, dst: Path) -> bool:
    return not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime


def ffprobe_codec(path: Path) -> str:
    res = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True, errors="replace")
    m = re.search(r"Video: (\w+)", res.stderr)
    return m.group(1) if m else ""


# ------------------------------------------------------------------------------------------------------------ media
def comfy_exif(im: Image.Image) -> bytes | None:
    """ComfyUI's WebP metadata layout (comfy_api SaveImage helpers): EXIF Model = "prompt:<json>", Make and the tags
    below it = "<key>:<json>" for the extra PNG info (workflow). The frontend loads such a WebP by drag and drop."""
    prompt, workflow = im.info.get("prompt"), im.info.get("workflow")
    if not (prompt or workflow):
        return None
    exif = Image.Exif()
    if prompt:
        exif[0x0110] = "prompt:" + prompt
    if workflow:
        exif[0x010F] = "workflow:" + workflow
    return exif.tobytes()


def put_image(src: Path, dst_dir: Path, stem: str, original: bool, max_side: int | None = None) -> dict:
    """Full-resolution WebP (q86) plus thumbnail. The main example of a workflow keeps ComfyUI's workflow metadata in
    the WebP (drag and drop into ComfyUI) and serves as the original; a PNG copy would cost ~1.5 MB per image."""
    webp = dst_dir / f"{stem}.webp"
    thumb = dst_dir / "thumbs" / f"{stem}.webp"
    with Image.open(src) as im:
        im.load()
        w, h = im.size
        exif = comfy_exif(im) if original else None
        has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        if im.mode.startswith("I;16") or im.mode == "I":  # 16-bit PNG (depth maps): scale, a plain convert clips to white
            work = im.convert("I").point(lambda v: v * (1 / 256)).convert("L").convert("RGB")
        else:
            work = im.convert("RGBA" if has_alpha else "RGB")
        if newer(src, webp) or (exif and b"workflow:" not in webp.read_bytes()[:1 << 22]):
            big = work
            if max_side and max(w, h) > max_side:
                big = work.copy()
                big.thumbnail((max_side, max_side), Image.LANCZOS)
            extra = {"exif": exif} if exif else {}
            big.save(webp, "WEBP", quality=86, method=6, **extra)
        if newer(src, thumb):
            thumb.parent.mkdir(exist_ok=True)
            t = work.copy()
            t.thumbnail((420, 420), Image.LANCZOS)
            t.save(thumb, "WEBP", quality=72, method=6)
    info = {"kind": "image", "src": webp.name, "thumb": f"thumbs/{thumb.name}", "w": w, "h": h}
    if original:
        info["original"] = webp.name
        info["original_label"] = (f"Volle Auflösung ({w}×{h}, WebP"
                                  + (" mit Workflow – per Drag & Drop in ComfyUI ladbar)" if exif else ")"))
    return info


def put_video(src: Path, dst_dir: Path, stem: str) -> dict:
    dst = dst_dir / f"{stem}.mp4"
    poster = dst_dir / "thumbs" / f"{stem}.webp"
    if newer(src, dst):
        codec = ffprobe_codec(src)
        if src.suffix.lower() == ".mp4" and codec == "h264" and src.stat().st_size <= 9 * 2**20:
            shutil.copy2(src, dst)
        else:
            subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-c:v", "libx264",
                            "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p",
                            "-vf", "scale='min(1280,iw)':-2", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                            str(dst)], check=True)
    if newer(dst, poster):
        poster.parent.mkdir(exist_ok=True)
        tmp = poster.with_suffix(".png")
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", "0.5", "-i", str(dst),
                        "-frames:v", "1", str(tmp)], check=True)
        with Image.open(tmp) as im:
            im = im.convert("RGB")
            im.thumbnail((420, 420), Image.LANCZOS)
            im.save(poster, "WEBP", quality=72)
        tmp.unlink()
    return {"kind": "video", "src": dst.name, "thumb": f"thumbs/{poster.name}", "poster": f"thumbs/{poster.name}"}


def put_audio(src: Path, dst_dir: Path, stem: str) -> dict:
    dst = dst_dir / f"{stem}.mp3"
    if newer(src, dst):
        if src.suffix.lower() == ".mp3" and src.stat().st_size <= 6 * 2**20:
            shutil.copy2(src, dst)
        else:
            subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vn",
                            "-c:a", "libmp3lame", "-b:a", "192k", str(dst)], check=True)
    return {"kind": "audio", "src": dst.name}


def put_model(src: Path, dst_dir: Path, stem: str) -> dict:
    """GLB for the web viewer: exact geometry, meshopt-compressed and quantised, textures as WebP (gltf-transform,
    ~6x smaller; model-viewer decodes both). Falls back to a plain copy without Node.js."""
    dst = dst_dir / f"{stem}{src.suffix.lower()}"
    if newer(src, dst):
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        ok = False
        if npx and src.suffix.lower() == ".glb":
            res = subprocess.run([npx, "-y", "@gltf-transform/cli@4", "optimize", str(src), str(dst), "--compress",
                                  "meshopt", "--texture-compress", "webp", "--texture-size", "2048", "--simplify",
                                  "false"], capture_output=True, text=True, errors="replace")
            ok = res.returncode == 0 and dst.exists() and dst.stat().st_size > 0
        if not ok:
            shutil.copy2(src, dst)
    return {"kind": "model", "src": dst.name, "compressed": dst.stat().st_size < src.stat().st_size}


def put_media(src: Path, dst_dir: Path, stem: str, original: bool) -> dict | None:
    kind = kind_of(src.name)
    if kind == "image":
        return put_image(src, dst_dir, stem, original)
    if kind == "video":
        return put_video(src, dst_dir, stem)
    if kind == "audio":
        return put_audio(src, dst_dir, stem)
    if kind == "model":
        return put_model(src, dst_dir, stem)
    return None


# ------------------------------------------------------------------------------------------------------------ build
def measure(result: dict) -> dict:
    mem = result.get("memory") or {}
    vram, llm = [], 0.0
    for key, value in (mem.get("gpu_dedicated_by_process_gib") or {}).items():
        proc, _, gpu = key.partition("@")
        if gpu not in GPU_TOTAL:
            continue
        if "llama" in proc:
            llm = max(llm, value)
            continue
        vram.append({"gpu": GPU_SHORT[gpu], "gib": value, "total": GPU_TOTAL[gpu]})
    torch_peaks = {GPU_SHORT.get(d["name"], d["name"]): d for d in mem.get("torch", [])}
    for v in vram:
        peak = torch_peaks.get(v["gpu"]) or {}
        v["torch_gib"] = peak.get("max_reserved_gib")
        v["alloc_gib"] = peak.get("max_allocated_gib")
    vram.sort(key=lambda v: v["gpu"] != "R9700")
    return {"seconds": result.get("seconds"), "exec_seconds": result.get("exec_seconds"), "vram": vram,
            "llm_vram_gib": round(llm, 2) if llm else None, "ram_gib": mem.get("peak_process_rss_gib"),
            "commit_gib": mem.get("peak_process_private_gib")}


STAGE_TYPES = re.compile(r"Sampler|Detailer|UltimateSDUpscale", re.I)


def pass_depths(wf: dict, files: list[dict]) -> dict[str, int]:
    """Image/video outputs saved after different numbers of sampler stages -> {node id: pass number}.

    Pass number = sampler/detailer nodes upstream of the output (a subgraph that contains one counts as one). Outputs
    after the same stages (cutout + mask, concept + texture) are parallel products, not passes; outputs without any
    stage (crops, face crops) get no pass either."""
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    subgraphs = {g["id"]: g for g in (wf.get("definitions") or {}).get("subgraphs") or []}
    parents: dict[int, set[int]] = {}
    for link in wf.get("links") or []:
        parents.setdefault(link[3], set()).add(link[1])

    def is_stage(node_id: int) -> bool:
        node = nodes.get(node_id) or {}
        sub = subgraphs.get(node.get("type"))
        if sub is not None:
            return any(STAGE_TYPES.search(n.get("type", "")) for n in sub.get("nodes", []))
        return bool(STAGE_TYPES.search(node.get("type", "")))

    def stages(node_id: int) -> int:
        seen, todo = {node_id}, [node_id]
        while todo:
            for p in parents.get(todo.pop(), ()):
                if p not in seen:
                    seen.add(p)
                    todo.append(p)
        return sum(is_stage(n) for n in seen if n != node_id)

    counts = {}
    for f in files:
        node = f["node"].split(":")[0]
        if kind_of(f["file"]) not in ("image", "video") or not node.isdigit():
            continue
        counts[f["node"]] = stages(int(node))
    levels = sorted({c for c in counts.values() if c > 0})
    if len(levels) < 2:
        return {}
    return {n: levels.index(c) + 1 for n, c in counts.items() if c > 0}


def output_order(run: Path, files: list[dict], passes: dict[str, int]) -> list[dict]:
    """Final pass first, then the earlier passes; otherwise the largest rendered image first; 3D: the visual mesh
    before its collision mesh, LOD0 before LOD1 ..."""
    def key(item):
        i, f = item
        name = f"{f.get('node_title') or ''} {f['file']}".lower()
        pixels = 0
        if kind_of(f["file"]) == "image" and (run / f["file"]).exists():
            with Image.open(run / f["file"]) as im:
                pixels = im.width * im.height
        lod = re.search(r"lod(\d)", name)
        return ("collision" in name, int(lod.group(1)) if lod else 0, -passes.get(f["node"], 0), -pixels, i)
    return [f for _, f in sorted(enumerate(files), key=key)]


KIND_LABEL = {"image": "Bild", "video": "Video", "audio": "Audio", "model": "3D-Modell"}


def example_order(examples: list) -> list:
    """Per idea (text to image): the highest resolution first, then descending; other examples keep their order."""
    first = {}
    for i, ex in enumerate(examples):
        first.setdefault(ex.params.get("idea") or ex.key, i)

    def key(item):
        i, ex = item
        pixels = int(ex.params.get("width") or 0) * int(ex.params.get("height") or 0)
        return (first[ex.params.get("idea") or ex.key], -pixels, i)
    return [ex for _, ex in sorted(enumerate(examples), key=key)]


def empty_image(path: Path) -> bool:
    """A transparent layer without a single opaque pixel (Ming layer decomposition pads with empty layers)."""
    if kind_of(path.name) != "image":
        return False
    with Image.open(path) as im:
        if im.mode not in ("RGBA", "LA"):
            return False
        return im.getchannel("A").getextrema()[1] < 128


def example_outputs(ex, result: dict, dst_dir: Path, main: bool, wf: dict) -> list[dict]:
    run = RUNS / slug(ex.workflow.removesuffix(".json")) / slug(ex.key)
    files = [f for f in result.get("outputs") or [] if (run / f["file"]).exists() and not empty_image(run / f["file"])]
    passes = {}
    if ex.show:  # explicit selection, in the listed order
        pick = lambda f: next((i for i, n in enumerate(ex.show) if n in (f["node"], f["node"].split(":")[-1])), None)
        files = sorted((f for f in files if pick(f) is not None), key=pick)
        passes = pass_depths(wf, files)
    else:
        saved = [f for f in files if f["type"] == "output"]
        files = saved or files
        passes = pass_depths(wf, files)
        files = output_order(run, files, passes)
    last = max(passes.values(), default=0)
    out = []
    per_node: dict[str, int] = {}
    for i, f in enumerate(files):
        src = run / f["file"]
        if not src.exists():
            continue
        # named after the output node (not the position), so a re-sorted gallery never reuses an older file
        k = per_node.get(f["node"], 0)
        same_node = sum(g["node"] == f["node"] for g in files)
        node = slug(f["node"].replace(":", "-"))
        stem = slug(ex.key) + (f"__n{node}" + (f"-{k + 1}" if same_node > 1 else "") if len(files) > 1 else "")
        info = put_media(src, dst_dir, stem, original=main and i == 0)
        if not info:
            continue
        caption = ex.captions.get(f["node"]) if ex.captions else None
        if isinstance(caption, list):  # one caption per file of that node
            k = per_node.get(f["node"], 0)
            caption = caption[k] if k < len(caption) else None
        per_node[f["node"]] = per_node.get(f["node"], 0) + 1
        explicit = bool(caption)  # a caption from the catalog names the output itself (scene, object), not a pass
        caption = caption or f.get("node_title") or ""
        if f["node"] in passes and not explicit:
            label = "Final" if passes[f["node"]] == last else f"Pass {passes[f['node']]}"
            caption = f"{label} · {caption}" if caption else label
        elif not caption and len(files) > 1:
            caption = f"{KIND_LABEL.get(info.get('kind'), 'Datei')} {len(out) + 1}"
        info["caption"] = caption
        out.append(info)
    return out


def example_inputs(ex, dst_dir: Path) -> list[dict]:
    out = []
    for asset, name in ex.uploads.items():
        src = WORK / "assets" / asset
        if not src.exists():
            continue
        stem = "input_" + slug(Path(name).stem)
        info = put_media(src, dst_dir, stem, original=False)
        if info:
            info["caption"] = ex.input_captions.get(name, name) if ex.input_captions else name
            out.append(info)
    for text_in in ex.text_inputs:
        out.append({"kind": "text", **text_in})
    return out


def build(only: str = "") -> dict:
    by_old: dict[str, list] = {}
    for ex in CATALOG:
        if ex.group == "asset":
            continue
        by_old.setdefault(ex.workflow, []).append(ex)
    system = {}
    sys_file = WORK / "system.json"
    if sys_file.exists():
        system = json.loads(sys_file.read_text(encoding="utf-8"))
    workflows = []
    for path in sorted(WF_DIR.rglob("*.json")):
        rel = path.relative_to(WF_DIR).as_posix()
        old = old_of(rel)
        new = new_of(old)
        category, new_name = new.split("/")[0], Path(new).stem
        meta = META.get(old, {})
        wf_json = json.loads(path.read_text(encoding="utf-8"))
        dst_dir = EXAMPLES / category / new_name
        rel_dir = f"{category}/{new_name}"
        entry = {"id": wid(new_name), "name": new_name, "old_name": Path(old).stem, "file": new, "category": category,
                 "dir": rel_dir, "title": meta.get("title") or new_name, "summary": meta.get("summary", ""),
                 "inputs": meta.get("inputs", []), "outputs": meta.get("outputs", []), "note": meta.get("note", ""),
                 "models": workflow_models(wf_json), "quant": primary_quant(new_name), "examples": []}
        if only and only not in old and only not in new:
            workflows.append(entry)
            continue
        examples = example_order(by_old.get(old, []))
        defaults = workflow_settings(wf_json)
        main_done = False
        for ex in examples:
            res_path = RUNS / slug(ex.workflow.removesuffix(".json")) / slug(ex.key) / "result.json"
            if not res_path.exists():
                continue
            result = json.loads(res_path.read_text(encoding="utf-8"))
            if result.get("status") != "success":
                continue
            dst_dir.mkdir(parents=True, exist_ok=True)
            is_main = ex.shot and not main_done
            params = {k: v for k, v in ex.params.items() if k != "idea"}
            if ex.group == "t2i" or ex.use_defaults:
                for k, v in defaults.items():
                    params.setdefault(k, v)
            item = {"key": ex.key, "title": ex.title, "idea": ex.params.get("idea"), "group": ex.group,
                    "variant": ex.variant or (f"{ex.params['width']} × {ex.params['height']}"
                                              if ex.group == "t2i" else None),
                    "params": params, "changes": ex.changes or None,
                    "measure": measure(result), "outputs": example_outputs(ex, result, dst_dir, is_main, wf_json),
                    "inputs": example_inputs(ex, dst_dir),
                    "texts": [{"title": t.get("title") or t.get("type") or "Text", "text": t["text"]}
                              for k, t in (result.get("texts") or {}).items()
                              if t.get("type") not in NOISE_TEXT_TYPES
                              and (not ex.show_texts or k in ex.show_texts or k.split(":")[-1] in ex.show_texts)]}
            entry["examples"].append(item)
            if is_main:
                main_done = True
                shot = res_path.parent / "workflow.png"
                if shot.exists():
                    entry["shot"] = put_screenshot(shot, dst_dir)
                entry["main"] = ex.key
                first = item["outputs"][0] if item["outputs"] else None
                if first and first.get("thumb"):
                    entry["thumb"] = first["thumb"]
                m = item["measure"]
                entry["stats"] = {"seconds": m["exec_seconds"] or m["seconds"],
                                  "vram_gib": round(sum(v["gib"] for v in m["vram"] if v["gib"] > 0.3), 1) or None,
                                  "ram_gib": m["ram_gib"]}
        if not entry["examples"]:
            shot = WORK / "shots" / (slug(old.removesuffix(".json")) + ".png")
            if shot.exists():
                dst_dir.mkdir(parents=True, exist_ok=True)
                entry["shot"] = put_screenshot(shot, dst_dir)
        kinds = [o["kind"] for e in entry["examples"] for o in e["outputs"]]
        entry["kind"] = max(set(kinds), key=kinds.count) if kinds else "none"
        workflows.append(entry)
        if entry["examples"] or entry.get("shot"):
            write_readme(entry, dst_dir)
    return finish(workflows, system)


def put_screenshot(src: Path, dst_dir: Path) -> dict:
    full = dst_dir / "workflow.webp"
    preview = dst_dir / "workflow-preview.webp"
    thumb = dst_dir / "thumbs" / "workflow.webp"
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        if newer(src, full):
            im.save(full, "WEBP", quality=82, method=6)
        if newer(src, preview):
            p = im.copy()
            p.thumbnail((1800, 1800), Image.LANCZOS)
            p.save(preview, "WEBP", quality=80, method=6)
        if newer(src, thumb):
            thumb.parent.mkdir(exist_ok=True)
            t = im.copy()
            t.thumbnail((420, 420), Image.LANCZOS)
            t.save(thumb, "WEBP", quality=72, method=6)
    return {"src": full.name, "preview": preview.name, "thumb": f"thumbs/{thumb.name}", "w": w, "h": h}


def fmt_gib(v) -> str:
    return "–" if v is None else f"{v:.1f} GiB".replace(".", ",")


def fmt_s(v) -> str:
    if v is None:
        return "–"
    return f"{v:.0f} s" if v < 60 else f"{int(v // 60)} min {int(v % 60)} s"


def md_link(path: str) -> str:
    return path.replace(" ", "%20").replace("&", "%26").replace("+", "%2B")


def write_readme(e: dict, dst_dir: Path) -> None:
    depth = "../../../"
    lines = [f"# {e['title']}", "",
             f"**Workflow-Datei:** [`workflows/{e['file']}`]({md_link(depth + 'workflows/' + e['file'])})  ",
             f"**Kategorie:** {e['category']} · **Eingabe → Ausgabe:** {' + '.join(e['inputs']) or '–'} → "
             f"{' + '.join(e['outputs']) or '–'}" + (f" · **Quant:** {e['quant']}" if e.get("quant") else ""), ""]
    if e["old_name"] != e["name"]:
        lines += [f"Bis v1.3.0 hieß der Workflow `{e['old_name']}.json`.", ""]
    if e["summary"]:
        lines += [e["summary"], ""]
    lines += [f"Interaktiv mit Zoom, Vergleichen und Kopier-Buttons: "
              f"<https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/#/w/{e['id']}>", ""]
    if e.get("note"):
        lines += [f"> {e['note']}", ""]
    if e["models"]:
        lines += ["## Modelle", "", "| Rolle | Datei | Quant | Größe |", "|---|---|---|---:|"]
        lines += [f"| {m['role']} | `{m['name']}` | {m['quant'] or '–'} | {fmt_gib(m['gib'])} |" for m in e["models"]]
        lines.append("")
    if e.get("shot"):
        lines += ["## Workflow in ComfyUI", "",
                  "Screenshot nach dem Hauptbeispiel (Eingaben und Ergebnis im Workflow, Erklärungstafeln ausgeblendet):",
                  "", f"[![Workflow]({e['shot']['preview']})]({e['shot']['src']})", ""]
    if e["examples"]:
        lines += ["## Beispiele", ""]
    for ex in e["examples"]:
        head = ex["title"] + (f" · {ex['variant']}" if ex.get("variant") else "")
        lines += [f"### {head}", ""]
        prompt = ex["params"].get("prompt")
        if prompt:
            lines += ["Prompt:", "", "```text", prompt, "```", ""]
        if ex["params"].get("negative"):
            lines += ["Negativ:", "", "```text", ex["params"]["negative"], "```", ""]
        rows = [(k, v) for k, v in ex["params"].items() if k not in ("prompt", "negative") and not isinstance(v, (dict, list))]
        m = ex["measure"]
        rows += [("Dauer (Ausführung)", fmt_s(m["exec_seconds"] or m["seconds"]))]
        rows += [(f"VRAM {v['gpu']} (belegt / PyTorch-Spitze)", f"{fmt_gib(v['gib'])} / {fmt_gib(v.get('alloc_gib'))}")
                 for v in m["vram"] if v["gib"] > 0.3]
        if m.get("llm_vram_gib"):
            rows.append(("VRAM llama-server (RX 9070 XT)", fmt_gib(m["llm_vram_gib"])))
        rows.append(("RAM (ComfyUI-Prozess)", fmt_gib(m["ram_gib"])))
        lines += ["| Einstellung | Wert |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows] + [""]
        if ex.get("changes"):
            lines += [ex["changes"], ""]
        for i in ex["inputs"]:
            if i["kind"] == "image":
                lines.append(f"Eingabe · {i['caption']}: ![{i['caption']}]({md_link(i['thumb'])}) ([Datei]({md_link(i['src'])}))  ")
            elif i["kind"] == "text":
                lines += [f"Eingabe · {i.get('caption', 'Text')}:", "", "```text", i.get("text", ""), "```"]
            else:
                lines.append(f"Eingabe · {i['caption']}: [{i['src']}]({md_link(i['src'])})  ")
        for o in ex["outputs"]:
            cap = o.get("caption") or "Ausgabe"
            if o["kind"] == "image":
                orig = f" · [{o['original_label']}]({md_link(o['original'])})" if o.get("original") else ""
                lines.append(f"Ausgabe · {cap}: [![{cap}]({md_link(o['thumb'])})]({md_link(o['src'])}){orig}  ")
            else:
                lines.append(f"Ausgabe · {cap}: [{o['src']}]({md_link(o['src'])})  ")
        for t in ex["texts"]:
            lines += ["", f"{t['title']}:", "", "```text", t["text"], "```"]
        lines.append("")
    (dst_dir / "README.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def finish(workflows: list[dict], system: dict) -> dict:
    ids = [w["id"] for w in workflows]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"duplicate workflow ids: {dupes}")
    by_old = {old_of(w["file"]): w for w in workflows}
    families = []
    for fam in FAMILIES:
        fid, name, variant, members, note = fam[:5]
        keys = fam[5] if len(fam) > 5 else None
        present = [by_old[m]["id"] for m in members if m in by_old and by_old[m]["examples"]]
        if len(present) >= 2:
            entry = {"id": fid, "name": name, "variant": variant, "members": present, "note": note}
            if keys:
                entry["keys"] = [{"key": k, "title": t} for k, t in keys]
            families.append(entry)
    from catalog import T2I_IDEAS
    cats = {}
    for w in workflows:
        c = cats.setdefault(w["category"], {"name": w["category"], "count": 0, "examples": 0})
        c["count"] += 1
        c["examples"] += len(w["examples"])
    order = ["Text to Image", "Image Editing", "Image Inpainting", "Image Outpainting", "Image Fusion", "Image Upscaling",
             "Image Utilities", "Character & Consistency", "Text to Video", "Text+Image to Video", "Reference to Video",
             "Audio to Video", "Controlled Video", "Character Animation", "Talking Video", "Video Editing",
             "Video Upscaling", "Video to Audio", "Music Generation", "Voice Design", "Vocal Separation",
             "Audio to Image", "Image to 3D-Mesh", "Game Development", "Pose & Depth", "Prompt Enhancer",
             "Prompt Tools", "Batch Processing", "Live Avatar", "LoRA Generation", "Pixaroma Node Demos",
             "Templates & Tests", "NSFW"]
    categories = sorted(cats.values(), key=lambda c: order.index(c["name"]) if c["name"] in order else 99)
    rank = {c["name"]: i for i, c in enumerate(categories)}
    workflows.sort(key=lambda w: (rank[w["category"]], not w["examples"], w["name"].lower()))
    inputs = sorted({i for w in workflows for i in w["inputs"]})
    outputs = sorted({o for w in workflows for o in w["outputs"]})
    data = {"version": "v1.3.1", "generated": dt.date.today().isoformat(), "repo": REPO, "branch": "main",
            "system": system, "categories": categories, "io_inputs": inputs, "io_outputs": outputs,
            "ideas": [{"id": i["id"], "title": i["title"], "text": i["text"], "tags": i["tags"]} for i in T2I_IDEAS],
            "families": families, "workflows": workflows}
    js = "window.GALLERY = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (EXAMPLES / "assets" / "gallery-data.js").write_text(js, encoding="utf-8")
    write_index(workflows, categories)
    return data


def write_index(workflows: list[dict], categories: list[dict]) -> None:
    lines = ["# Beispiele zu allen Workflows", "",
             "Interaktive Übersicht mit Suche, Zoom, Vergleichen und Kopier-Buttons: "
             "**<https://dawasteh.github.io/DaWastehs-ComfyUI-Bundle/>** (lokal: `examples/index.html` öffnen).", "",
             "Jeder Ordner enthält einen Screenshot des Workflows in ComfyUI (mit Eingabe und Ergebnis), die Ausgaben, "
             "eine `README.md` mit Prompts, Einstellungen, Dauer und RAM/VRAM-Bedarf. Bilder liegen in voller Auflösung "
             "als WebP vor; beim Hauptbeispiel steckt der komplette Workflow darin (Datei in ComfyUI ziehen).", ""]
    for c in categories:
        lines += [f"## {c['name']}", "", "| Workflow | Eingabe → Ausgabe | Beispiele |", "|---|---|---:|"]
        for w in workflows:
            if w["category"] != c["name"]:
                continue
            name = f"[{w['name']}]({md_link(w['dir'])}/README.md)" if (w["examples"] or w.get("shot")) else w["name"]
            lines.append(f"| {name}<br>{w['title']} | {' + '.join(w['inputs']) or '–'} → {' + '.join(w['outputs']) or '–'} "
                         f"| {len(w['examples']) or '–'} |")
        lines.append("")
    (EXAMPLES / "README.md").write_text("\n".join(lines), encoding="utf-8")


MEDIA_KEYS = ("src", "thumb", "poster", "original", "preview")


def referenced_files(data: dict) -> set[Path]:
    """Every file below examples/<category>/<workflow>/ the gallery data points to, plus each README.md."""
    keep: set[Path] = set()

    def walk(value, base: Path):
        if isinstance(value, dict):
            for k, v in value.items():
                if k in MEDIA_KEYS and isinstance(v, str):
                    keep.add((base / v).resolve())
                else:
                    walk(v, base)
        elif isinstance(value, list):
            for v in value:
                walk(v, base)

    for w in data["workflows"]:
        base = EXAMPLES / w["dir"]
        keep.add((base / "README.md").resolve())
        walk(w, base)
    return keep


def prune(data: dict) -> int:
    """Delete files of earlier builds (renamed outputs, replaced examples) that the gallery no longer references."""
    keep = referenced_files(data)
    categories = {w["category"] for w in data["workflows"]}
    removed = 0
    for category in sorted(categories):
        root = EXAMPLES / category
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file() and path.resolve() not in keep:
                path.unlink()
                removed += 1
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    for path in sorted(EXAMPLES.iterdir()):  # category folders of workflows that no longer exist
        if path.is_dir() and path.name != "assets" and path.name not in categories:
            shutil.rmtree(path)
            removed += 1
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--prune", action="store_true", help="delete files the gallery no longer references")
    args = ap.parse_args()
    data = build(args.only)
    n = sum(len(w["examples"]) for w in data["workflows"])
    print(f"{len(data['workflows'])} workflows, {n} examples, {len(data['families'])} families")
    if args.prune:
        if args.only:
            raise SystemExit("--prune needs a full build (no --only)")
        print(f"pruned {prune(data)} unreferenced files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
