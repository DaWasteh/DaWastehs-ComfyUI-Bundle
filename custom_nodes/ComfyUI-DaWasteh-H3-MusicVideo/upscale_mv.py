"""v1.2.7 optional upscale inside the FastH3 music video (MV 5c).

After MV 5b has accepted a scene, MV 5c upscales exactly that take before the next scene is rendered. One node
switches the upscale on or off and picks one of the four live-tested methods of the Video Upscaling folder:

    SeedVR2 3B INT8 (v1.2.3) · WAN 2.2 A14B low-noise + lightx2v (v1.2.6)
    · H3 Latent Upscaler 3D + FastH3 (v1.2.3) · MMH3 Ultimate Upscale + FastH3 (v1.2.3)

MV 5c expands into the method's node chain (the same core and pack nodes with the same settings as the standalone
workflows) between two internal nodes: Upscale Source (frames of the accepted take plus lead-in and padding, the
song audio, the scene's own H3 conditioning) and Upscale Save (drops lead-in and padding, stores the scene under
upscaled/<method>_<W>x<H>/ with a preview that carries the song audio). The H3 methods re-sample with the running
FastH3 chain. SeedVR2 and WAN load their models in an internal node that hands every scene the same objects: with
--cache-classic each expansion has its own output cache, so ordinary loader nodes would keep one model copy per
scene in RAM (--cache-ram, the start profile's default, is keyed by inputs and would share them).

A rejected take never reaches MV 5c, because MV 5b only passes accepted scenes on. MV 6 joins the original scenes
and, when MV 5c was on, the upscaled scenes into a second film plus an optional side-by-side comparison.

No ComfyUI import at module level: the tests load this file on its own.
"""
from __future__ import annotations

import gc
from pathlib import Path
from typing import Any

FPS = 24
UPSCALE_CRF = 14.0   # same as VU 3 (upscale_nodes.DaWVUSaveBlock)
COMPARE_OFF = "aus"
COMPARE_OPTIONS = ["nebeneinander", COMPARE_OFF]
SEEDVR2, WAN22, LATENT3D, ULTIMATE = "seedvr2", "wan22", "latent3d", "ultimate"
BS = "\\"

# Settings of the standalone workflows (tools/build_video_upscale_v123.py and _wan_v126.py); the tests pin them
# against those builders. "version" goes into the resume key: bump it whenever a method's settings change.
SEEDVR2_FILES = {"model": "SeedVR2" + BS + "seedvr2_3b_int8_convrot.safetensors", "vae": "SeedVR2" + BS + "seedvr2_ema_vae_fp16.safetensors"}
WAN_FILES = {"model": "WAN" + BS + "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
             "lora": "WAN" + BS + "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors",
             "text_encoder": "UMT5" + BS + "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
             "vae": "WAN" + BS + "wan_2.1_vae.safetensors"}
LATENT_UPSCALER = "minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"   # top level of latent_upscale_models/
WAN_PROMPT = ("Cinematic live-action video in high detail with sharp focus, natural matte skin texture with visible pores, "
              "fine individual hair strands, crisp fabric texture, clean edges, realistic light. The people, places, clothing, "
              "camera framing and motion stay exactly as in the original footage; only resolution, texture and fine detail improve.")
WAN_NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
                "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")

METHODS: dict[str, dict[str, Any]] = {
    SEEDVR2: {
        "label": "SeedVR2 3B · scharf, bei ×2 malerisch",
        "align": "seedvr2 (4k+1)", "lead": 0, "h3": False, "version": 2,
        "encode_tile": (1024, 128, 64, 8), "decode_tile": (512, 128, 64, 8), "chunk_overlap": 2,
        "sampler": {"seed": 3130459, "steps": 1, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
        # v1.2.7: "lab" instead of v1.2.3's "none". Measured at x2 (960x544 -> 1920x1088, bit-identical chain
        # otherwise): colour error 3.0 -> 1.96, PSNR to Lanczos 26.3 -> 28.9 dB; "none" left magenta/red smears.
        "color_correction": "lab",
        "files": [("diffusion_models", SEEDVR2_FILES["model"]), ("vae", SEEDVR2_FILES["vae"])],
        "classes": ["SeedVR2Preprocess", "SeedVR2TemporalChunk", "SeedVR2Conditioning", "SeedVR2TemporalMerge",
                    "SeedVR2PostProcessing", "ResizeImageMaskNode", "VAEEncodeTiled", "VAEDecodeTiled", "KSampler"],
        "pack": "SeedVR2-Nodes im ComfyUI-Core (ComfyUI aktualisieren)",
    },
    WAN22: {
        "label": "WAN 2.2 Low-Noise · treu + neue Details (Standard)",
        "align": "wan (4k+1)", "lead": 5, "h3": False, "version": 1,
        "shift": 5.0, "lora_strength": 1.0,
        "tiles": {"tile_width": 832, "tile_height": 480, "overlap": 128},
        "windows": {"context_length": 33, "context_overlap": 8, "context_schedule": "standard_static", "fuse_method": "pyramid"},
        "encode_tile": (512, 64, 4096, 4), "decode_tile": (512, 64, 4096, 4),
        "sampler": {"seed": 20260926, "steps": 2, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 0.15},
        "files": [("diffusion_models", WAN_FILES["model"]), ("loras", WAN_FILES["lora"]),
                  ("text_encoders", WAN_FILES["text_encoder"]), ("vae", WAN_FILES["vae"])],
        "classes": ["ModelSamplingSD3", "WanContextWindowsManual", "DaWVUSpatialTiles", "ResizeImageMaskNode",
                    "VAEEncodeTiled", "VAEDecodeTiled", "KSampler"],
        "pack": "WAN-Nodes im ComfyUI-Core (ComfyUI aktualisieren)",
    },
    LATENT3D: {
        "label": "H3 Latent Upscaler 3D · am schnellsten, zeichnet Mimik neu",
        "align": "h3 (17k+5)", "lead": 0, "h3": True, "version": 1,
        "noise_seed": 20260924, "sampler_name": "euler",
        "schedule": {"scheduler": "beta", "steps": 2, "denoise": 0.25},
        "upscaler": {"align": 32, "enable_temporal_chunking": True, "force_unload": True, "device": "rocm", "precision": "bf16"},
        "files": [("latent_upscale_models", LATENT_UPSCALER)],
        "classes": ["MinimaxH3LatentUpscaler3D", "LTXVSeparateAVLatent", "LTXVConcatAVLatent", "BasicGuider", "RandomNoise",
                    "KSamplerSelect", "BasicScheduler", "SamplerCustomAdvanced", "VAEDecode", "DaWH3VideoToAVLatent"],
        "pack": "Node-Pack Comfyui_Minimax_h3_latent_Upscaler (LBH-123-AI, vom Updater mitgepflegt)",
    },
    ULTIMATE: {
        "label": "H3 Ultimate Upscale · zeichnet am freiesten neu",
        "align": "h3 (17k+5)", "lead": 0, "h3": True, "version": 1,
        "noise_seed": 20260924, "sampler_name": "euler", "cfg": 1.0,
        "schedule": {"scheduler": "linear_quadratic", "steps": 4, "denoise": 0.25},
        "upscale_param": {"device": "cuda", "precision": "bf16"},
        "temporal": {"chunk_length": 136, "temporal_overlap": 17, "anchor_strength": 1.0},
        "spatial": {"tile_size_mode": "auto", "tile_width": 864, "tile_height": 480, "grid_rows": 2, "grid_cols": 2,
                    "spatial_w_overlap": 128, "spatial_h_overlap": 128, "fade_width": 32, "fade_height": 32,
                    "min_tile_size": 352, "overlap_mode": "earlier", "overlap_blend": "linear", "joint_steps": True,
                    "token_budget": 70000},
        "files": [("latent_upscale_models", LATENT_UPSCALER)],
        "classes": ["MMH3UltimateUpscale", "MMH3LatentUpscaleWithModelParams", "MMH3TemporalSplitParams",
                    "MMH3SpatialSplitParams", "RandomNoise", "KSamplerSelect", "BasicScheduler", "VAEDecode", "DaWH3VideoToAVLatent"],
        "pack": "Node-Pack PlagueKind-Nodes (vom Updater mitgepflegt)",
    },
}
# WAN first: the default. Measured on a 960x544 scene -> 1920x1088 (docs/H3_MUSIC_VIDEO_V127.md): WAN keeps faces and
# mouth shapes (lip sync), the H3 methods re-draw expressions, SeedVR2 paints at x2.
LABELS = [METHODS[key]["label"] for key in (WAN22, SEEDVR2, LATENT3D, ULTIMATE)]
MODEL_METHODS = [SEEDVR2, WAN22]   # the two methods with their own models (module cache)


def method_key(value: str) -> str:
    """Combo label (or a bare key from a script) -> method key."""
    for key, spec in METHODS.items():
        if value in (key, spec["label"]):
            return key
    raise ValueError(f"Unknown upscale method {value!r}; choose one of {LABELS}")


def target_for(width: int, height: int, long_side: int) -> tuple[int, int]:
    """Upscaled size: the long side becomes `long_side` (never smaller than the render), both sides on the
    32-px grid of the H3 upscaler (960x544 -> 1920x1088, 1280x704 -> 1920x1056)."""
    scale = max(1.0, int(long_side) / max(int(width), int(height)))
    return (max(32, int(round(width * scale / 32)) * 32), max(32, int(round(height * scale / 32)) * 32))


def tag_for(method: str, width: int, height: int) -> str:
    return f"{method}_{int(width)}x{int(height)}"


def upscale_key(scene: dict[str, Any], method: str, width: int, height: int) -> str:
    """Changes when the accepted take (render key), the method, its settings or the size change."""
    import json
    import hashlib
    payload = {"render": scene.get("render_key"), "method": method, "size": [int(width), int(height)],
               "v": METHODS[method]["version"]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def upscaled_files(project: Path, index: int, tag: str) -> dict[str, Path]:
    root = Path(project) / "upscaled" / tag
    return {"video": root / f"scene_{index:04d}.mp4", "sheet": root / f"scene_{index:04d}_sheet.png",
            "preview": root / "preview" / f"scene_{index:04d}_with_audio.mp4"}


def upscaled_done(project: Path, scene: dict[str, Any], tag: str, key: str) -> bool:
    record = (scene.get("upscaled") or {}).get(tag) or {}
    return (record.get("key") == key and record.get("verified_frames") == scene["frames"]
            and upscaled_files(project, scene["index"], tag)["video"].is_file())


def lead_frames(method: str, index: int, previous_frames: int) -> tuple[int, int]:
    """(real frames from the end of the previous scene, copies of the first frame) for the method's lead-in.
    Scenes continue each other (extend), so the previous scene's last frames are the true predecessors."""
    lead = int(METHODS[method]["lead"])
    real = min(lead, int(previous_frames)) if index > 0 else 0
    return real, lead - real


def missing_requirements(method: str, class_names, find_file) -> list[str]:
    """Node classes and model files the method needs but the installation lacks (human readable)."""
    spec = METHODS[method]
    problems = [f"Node {name} fehlt ({spec['pack']})" for name in spec["classes"] if name not in class_names]
    problems += [f"Modell fehlt: models/{folder}/{name.replace(BS, '/')}" for folder, name in spec["files"]
                 if not find_file(folder, name)]
    return problems


# ---------------------------------------------------------------------------
# Expansion: the method's node chain between Source and Save
# ---------------------------------------------------------------------------

def build_chain(graph, method: str, source, models, links: dict[str, list], width: int, height: int):
    """Adds the method's nodes to `graph` (a comfy_execution GraphBuilder) and returns the output slot with the
    upscaled frames. `source` outputs: 0 images, 1 audio, 2 conditioning, 3 lead; `models` (SeedVR2/WAN only):
    0 model, 1 vae, 2 positive, 3 negative; `links` holds MV 5c's FastH3 model/vae/audio_vae links."""
    spec = METHODS[method]
    if method in (SEEDVR2, WAN22):
        resize = graph.node("ResizeImageMaskNode", input=source.out(0), resize_type="scale dimensions",
                            scale_method="lanczos", **{"resize_type.width": width, "resize_type.height": height,
                                                       "resize_type.crop": "disabled"})
        tile, overlap, t_size, t_overlap = spec["encode_tile"]
        if method == SEEDVR2:
            pre = graph.node("SeedVR2Preprocess", resized_images=resize.out(0))
            encode = graph.node("VAEEncodeTiled", pixels=pre.out(0), vae=models.out(1), tile_size=tile, overlap=overlap,
                                temporal_size=t_size, temporal_overlap=t_overlap)
            chunk = graph.node("SeedVR2TemporalChunk", latent=encode.out(0), temporal_overlap=spec["chunk_overlap"],
                               chunking_mode="auto")
            cond = graph.node("SeedVR2Conditioning", model=models.out(0), vae_conditioning=chunk.out(0))
            sample = graph.node("KSampler", model=models.out(0), positive=cond.out(0), negative=cond.out(1),
                                latent_image=chunk.out(0), **spec["sampler"])
            merge = graph.node("SeedVR2TemporalMerge", latents=sample.out(0), temporal_overlap=chunk.out(1))
            tile, overlap, t_size, t_overlap = spec["decode_tile"]
            decode = graph.node("VAEDecodeTiled", samples=merge.out(0), vae=models.out(1), tile_size=tile, overlap=overlap,
                                temporal_size=t_size, temporal_overlap=t_overlap)
            post = graph.node("SeedVR2PostProcessing", images=decode.out(0), original_resized_images=resize.out(0),
                              color_correction_method=spec["color_correction"])
            return post.out(0)
        shift = graph.node("ModelSamplingSD3", model=models.out(0), shift=spec["shift"])
        tiles = graph.node("DaWVUSpatialTiles", model=shift.out(0), **spec["tiles"])
        windows = graph.node("WanContextWindowsManual", model=tiles.out(0), context_stride=1, closed_loop=False,
                             freenoise=True, retain_first_frame=False, split_conds_to_windows=False, **spec["windows"])
        encode = graph.node("VAEEncodeTiled", pixels=resize.out(0), vae=models.out(1), tile_size=tile, overlap=overlap,
                            temporal_size=t_size, temporal_overlap=t_overlap)
        sample = graph.node("KSampler", model=windows.out(0), positive=models.out(2), negative=models.out(3),
                            latent_image=encode.out(0), **spec["sampler"])
        tile, overlap, t_size, t_overlap = spec["decode_tile"]
        decode = graph.node("VAEDecodeTiled", samples=sample.out(0), vae=models.out(1), tile_size=tile, overlap=overlap,
                            temporal_size=t_size, temporal_overlap=t_overlap)
        return decode.out(0)

    model, vae, audio_vae = links["model"], links["vae"], links["audio_vae"]
    av = graph.node("DaWH3VideoToAVLatent", vae=vae, audio_vae=audio_vae, images=source.out(0), audio=source.out(1))
    noise = graph.node("RandomNoise", noise_seed=spec["noise_seed"])
    sampler = graph.node("KSamplerSelect", sampler_name=spec["sampler_name"])
    sigmas = graph.node("BasicScheduler", model=model, **spec["schedule"])
    if method == LATENT3D:
        split = graph.node("LTXVSeparateAVLatent", av_latent=av.out(0))
        upscale = graph.node("MinimaxH3LatentUpscaler3D", latent=split.out(0), model_name=LATENT_UPSCALER,
                             mode="target dimensions", **{"mode.width": width, "mode.height": height}, **spec["upscaler"])
        join = graph.node("LTXVConcatAVLatent", video_latent=upscale.out(0), audio_latent=split.out(1))
        guider = graph.node("BasicGuider", model=model, conditioning=source.out(2))
        latent = graph.node("SamplerCustomAdvanced", noise=noise.out(0), guider=guider.out(0), sampler=sampler.out(0),
                            sigmas=sigmas.out(0), latent_image=join.out(0))
    else:
        param = graph.node("MMH3LatentUpscaleWithModelParams", model_name=LATENT_UPSCALER, width=width, height=height,
                           **spec["upscale_param"])
        temporal = graph.node("MMH3TemporalSplitParams", **spec["temporal"])
        spatial = graph.node("MMH3SpatialSplitParams", upscale_width=width, upscale_height=height, **spec["spatial"])
        latent = graph.node("MMH3UltimateUpscale", model=model, conditioning=source.out(2), latent=av.out(0),
                            noise=noise.out(0), sampler=sampler.out(0), sigmas=sigmas.out(0), cfg=spec["cfg"],
                            latent_upscale_param=param.out(0), temporal_split_param=temporal.out(0),
                            spatial_split_param=spatial.out(0))
    decode = graph.node("VAEDecode", samples=latent.out(0), vae=vae)
    return decode.out(0)


WIDGET_TYPES = ("INT", "FLOAT", "BOOLEAN", "STRING", "COMBO")


def fill_defaults(nodes, input_types) -> list[str]:
    """Give every expanded node the schema default of each required widget the chain leaves out, as the frontend
    does for a saved workflow (a core update added `split_conds_to_windows` to WanContextWindowsManual, and an
    expansion without it fails validation). `input_types(class_type)` is the node's INPUT_TYPES(); returns the
    filled 'Class.input' names."""
    filled = []
    for node in nodes:
        for name, spec in input_types(node.class_type).get("required", {}).items():
            if name in node.inputs or not spec:
                continue
            kind, options = spec[0], (spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {})
            if isinstance(kind, list) and kind:
                value = options.get("default", kind[0])
            elif kind in WIDGET_TYPES and ("default" in options or options.get("options")):
                value = options.get("default", (options.get("options") or [None])[0])
            else:
                continue
            node.inputs[name] = value
            filled.append(f"{node.class_type}.{name}")
    return filled


# ---------------------------------------------------------------------------
# SeedVR2 / WAN models: loaded once per run
# ---------------------------------------------------------------------------
# The models are held WEAKLY: they live exactly as long as ComfyUI's own output cache keeps an output of
# 'MV 5c · intern · Modelle' (the whole run; with --cache-ram until RAM pressure or 'Free model and node cache').
# Scenes of one run share one copy, and nothing stays behind a method change or after the run. The WAN prompt
# conditioning (a few MB) is kept strongly, so a reload never needs UMT5 again.

_CACHE: dict[str, Any] = {"key": None, "refs": None, "conditioning": {}}


def release_upscale_models() -> None:
    """Forget the cached SeedVR2/WAN models (MV 6 at the end of a run, MV 5c switched off)."""
    _CACHE.update(key=None, refs=None)
    _CACHE["conditioning"].clear()


def _alive() -> tuple | None:
    refs = _CACHE["refs"]
    objects = tuple(ref() for ref in refs) if refs else None
    return objects if objects and all(o is not None for o in objects) else None


def load_upscale_models(method: str):
    """(model, vae, positive, negative) for SeedVR2 or WAN, loaded read-only (h3_highres mapping: the files are
    not charged to the Windows commit limit) and shared by every scene of the run."""
    import weakref

    spec = METHODS[method]
    key = (method, spec["version"])
    alive = _alive() if _CACHE["key"] == key else None
    if alive:
        return (*alive, *_CACHE["conditioning"].get(key, (None, None)))
    import comfy.model_management
    import folder_paths
    import nodes as comfy_nodes
    from . import h3_highres

    path = lambda folder, name: folder_paths.get_full_path_or_raise(folder, name)
    positive = negative = None
    if method == SEEDVR2:
        model = h3_highres.load_diffusion_model_readonly(path("diffusion_models", SEEDVR2_FILES["model"]))
        vae = comfy_nodes.VAELoader().load_vae(SEEDVR2_FILES["vae"])[0]
    elif method == WAN22:
        model = h3_highres.load_diffusion_model_readonly(path("diffusion_models", WAN_FILES["model"]))
        model = comfy_nodes.LoraLoaderModelOnly().load_lora_model_only(model, WAN_FILES["lora"], spec["lora_strength"])[0]
        if key not in _CACHE["conditioning"]:
            clip = h3_highres.load_clip_readonly(path("text_encoders", WAN_FILES["text_encoder"]), "wan")
            encoder = comfy_nodes.CLIPTextEncode()
            _CACHE["conditioning"][key] = (encoder.encode(clip, WAN_PROMPT)[0], encoder.encode(clip, WAN_NEGATIVE)[0])
            del clip, encoder   # only the conditioning stays; the 6.7 GB UMT5 is freed right away
            gc.collect()
            comfy.model_management.cleanup_models()
            comfy.model_management.soft_empty_cache()
        positive, negative = _CACHE["conditioning"][key]
        vae = comfy_nodes.VAELoader().load_vae(WAN_FILES["vae"])[0]
    else:
        raise ValueError(f"{method} re-samples with the FastH3 chain and loads no models of its own")
    _CACHE.update(key=key, refs=(weakref.ref(model), weakref.ref(vae)))
    return model, vae, positive, negative


def unload_cached_from_vram() -> None:
    """After a scene: SeedVR2/WAN leave the GPU so FastH3 loads completely for the next scene (a resident
    5 GB VAE already made ComfyUI load FastH3 only partially, v1.2.2)."""
    alive = _alive()
    if not alive:
        return
    import comfy.model_management
    for item in alive:
        patcher = getattr(item, "patcher", item)
        if patcher is not None and hasattr(patcher, "is_clone"):
            comfy.model_management.unload_model_and_clones(patcher)
    comfy.model_management.soft_empty_cache()


# ---------------------------------------------------------------------------
# MV 6: the upscaled film and the comparison
# ---------------------------------------------------------------------------

def join_upscaled(plan: str, manifest: dict[str, Any], ffmpeg: str, stamp: str, suffix: str, folder: Path,
                  silent_original: Path, comparison: bool, run_command, count_video_frames) -> dict[str, Any]:
    """Second film from the upscaled scenes with the original audio stream-copied, and (optional) the original
    film scaled up next to the upscale. Raises when an accepted scene has no upscale of the current setting."""
    setting = manifest["upscale"]
    method, tag = setting["method"], setting["tag"]
    width, height = setting["size"]
    project = Path(plan).parent
    missing = [s["index"] + 1 for s in manifest["scenes"]
               if not upscaled_done(project, s, tag, upscale_key(s, method, width, height))]
    if missing:
        raise RuntimeError(f"MV 6: scenes {missing[:20]} have no upscale '{tag}'. The original film is written; "
                           f"run the workflow again (MV 5c upscales the missing scenes, nothing is re-rendered).")
    sizes = {tuple(s["upscaled"][tag]["size"]) for s in manifest["scenes"]}
    if len(sizes) != 1:
        raise RuntimeError(f"Upscaled scenes have different sizes {sorted(sizes)}")
    w, h = next(iter(sizes))
    concat = project / "concat_upscaled.txt"
    concat.write_text("".join(f"file '{upscaled_files(project, s['index'], tag)['video'].as_posix()}'\n"
                              for s in manifest["scenes"]), encoding="utf-8")
    silent = project / "upscaled" / tag / "joined_video_silent.mp4"
    run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                 "-an", "-c:v", "copy", str(silent)], timeout=7200)
    frames = count_video_frames(ffmpeg, str(silent))
    final = Path(folder) / f"{manifest['project_name']}_{stamp}_upscale_{method}_{w}x{h}.{suffix}"
    audio = ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy"] + (["-movflags", "+faststart"] if suffix == "mp4" else [])
    run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", manifest["source_audio"],
                 *audio, str(final)], timeout=7200)
    result = {"upscaled": str(final), "upscaled_frames": frames, "size": [w, h], "comparison": "", "method": method}
    if comparison:
        compare = Path(folder) / f"{manifest['project_name']}_{stamp}_vergleich_original_vs_{method}.{suffix}"
        graph = (f"[0:v]scale={w}:{h}:flags=lanczos,setsar=1[original];[1:v]setsar=1[upscaled];"
                 f"[original][upscaled]hstack=inputs=2[v]")
        run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent_original), "-i", str(silent),
                     "-i", manifest["source_audio"], "-filter_complex", graph, "-map", "[v]", "-map", "2:a:0",
                     "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy",
                     *(["-movflags", "+faststart"] if suffix == "mp4" else []), str(compare)], timeout=14400)
        result["comparison"] = str(compare)
    return result

