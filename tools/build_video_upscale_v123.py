#!/usr/bin/env python3
"""Rebuild the three v1.2.3 video-upscale workflows (Nerdy Rodent's MiniMax H3 upscale methods).

1. MMH3 Ultimate Upscale (PlagueKind): tiled/chunked second FastH3 pass at the target size
2. Latent Upscaler 3D (LBH-123-AI): learned latent upscale + short FastH3 re-sample
3. SeedVR2 3B INT8 (ComfyUI native): one-step restoration upscale

All three share the DaW block frame: planner -> block 1 -> Pixaroma approval gate -> Pixaroma loop -> final film
with the original audio stream-copied.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

try:
    from tools.build_workflows_v118 import Graph
    from tools import migrate_workflows_v092 as migration
    from tools.generate_dual_gpu_workflows import install_central_device_control, insert_device_selectors, install_run_timer
    from tools.refine_workflows import refine_workflow
    from tools.rodent_layout import apply_rodent_layout
    from tools.build_h3_music_video_v122 import MODEL, VIDEO_VAE, AUDIO_VAE, TEXT_ENCODER, SAMPLING, _block_sparse
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_central_device_control, insert_device_selectors, install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout
    from build_h3_music_video_v122 import MODEL, VIDEO_VAE, AUDIO_VAE, TEXT_ENCODER, SAMPLING, _block_sparse

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v123"
MARKER = "dawasteh_video_upscale_v123"
BS = "\\"
# Top level of latent_upscale_models/: PlagueKind's model-based params node does not look into subfolders.
LATENT_UPSCALER = "minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"
SEEDVR2_MODEL = "SeedVR2" + BS + "seedvr2_3b_int8_convrot.safetensors"
SEEDVR2_VAE = "SeedVR2" + BS + "seedvr2_ema_vae_fp16.safetensors"
DEVICES = {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"}
H3_ALIGN, SEEDVR2_ALIGN = "h3 (17k+5)", "seedvr2 (4k+1)"
PROMPT = ("integrated_multimodal_description: [Shot 1] Live-action, cinematic video in high detail with sharp focus, natural "
          "matte skin texture with visible pores and fine hair strands. The people, places, clothing, camera framing and "
          "actions stay exactly as in the original footage; only resolution, texture and fine detail improve.\n\n"
          "overall_soundscape: Faint ambient sound of the location.\n\nnon_diegetic_music: The original soundtrack.")

METHODS = {
    "ultimate": {
        "path": "Video Upscaling/MiniMax_H3-Ultimate-Upscale-FastH3.json",
        "title": "MiniMax H3 Ultimate Upscale · FastH3 · PlagueKind",
        "blocks": (7.0, 2.0, 10.0), "align": H3_ALIGN,
        "sampling": {"scheduler": "linear_quadratic", "steps": 4, "denoise": 0.25},
    },
    "latent3d": {
        "path": "Video Upscaling/MiniMax_H3-Latent-Upscaler-3D-FastH3.json",
        "title": "MiniMax H3 Latent Upscaler 3D · FastH3 · LBH-123-AI",
        "blocks": (4.0, 2.0, 4.45), "align": H3_ALIGN,
        "sampling": {"scheduler": "beta", "steps": 2, "denoise": 0.25},
    },
    "seedvr2": {
        "path": "Video Upscaling/SeedVR2_3B_INT8-Video-Upscale.json",
        "title": "SeedVR2 3B INT8 Video Upscale · ComfyUI nativ",
        "blocks": (7.0, 2.0, 10.0), "align": SEEDVR2_ALIGN,
        "sampling": {"steps": 1, "denoise": 1.0},
    },
}


def _dyn(g: Graph, kind: str, title: str, values: list) -> dict:
    """Node with a dynamic combo: the frontend serialises the selected key followed by its sub-widget values."""
    node = g.add(kind, title)
    node["widgets_values"] = list(values)
    return node


def _h3_models(g: Graph, sampling: dict):
    unet = g.add("UNETLoader", "FASTH3 · MiniMax H3 8-Step V2 · INT8 ConvRot · R9700", unet_name=MODEL)
    shift = g.add("MiniMaxH3SigmaShift", "FASTH3 · Sigma-Shift Video 10 / Audio 3", shift_video=10.0, shift_audio=3.0)
    attention = g.add("ModelAttentionBackend", "FASTH3 · Comfy Kitchen Attention", attention=SAMPLING["attention"])
    sparse = _block_sparse(g)
    g.connect(unet, 0, shift, "model")
    g.connect(shift, 0, attention, "model")
    g.connect(attention, 0, sparse, "model")
    vae = g.add("VAELoader", "VAE · MiniMax H3 Video", vae_name=VIDEO_VAE)
    audio_vae = g.add("VAELoader", "VAE · MiniMax H3 Audio", vae_name=AUDIO_VAE)
    prompt = g.prompt("PROMPT · was im Video zu sehen ist (Englisch, MiniMax-Format)", PROMPT)
    cond = g.add("DaWH3PromptOnce", "H3-TEXTENCODER · Prompt einmal encodiert, danach frei", text_encoder=TEXT_ENCODER)
    g.connect(prompt, 0, cond, "prompt")
    sampler = g.add("KSamplerSelect", "SAMPLER · euler", sampler_name="euler")
    sigmas = g.add("BasicScheduler", f"SCHEDULER · {sampling['scheduler']} · {sampling['steps']} Schritte · Denoise {sampling['denoise']}",
                   scheduler=sampling["scheduler"], steps=sampling["steps"], denoise=sampling["denoise"])
    g.connect(sparse, 0, sigmas, "model")
    return sparse, vae, audio_vae, cond, sampler, sigmas


def _block_chain(g: Graph, method: str, label: str, plan, planner, shared: dict, *, index_source=None, offset=0):
    load = g.add("DaWVULoadBlock", f"{label} · Block laden · Frames + Originalton", block_index=0, index_offset=offset,
                 frame_alignment=METHODS[method]["align"])
    g.connect(plan, 0, load, "plan")
    if method in ("ultimate", "latent3d"):
        model, vae, audio_vae, cond, sampler, sigmas = (shared[k] for k in ("model", "vae", "audio_vae", "cond", "sampler", "sigmas"))
        av = g.add("DaWH3VideoToAVLatent", f"{label} · Video + Originalton → H3-AV-Latent")
        for src, slot, name in ((vae, 0, "vae"), (audio_vae, 0, "audio_vae"), (load, 0, "images"), (load, 1, "audio")):
            g.connect(src, slot, av, name)
        noise = g.add("RandomNoise", f"{label} · Rauschen", noise_seed=20260924)
        if method == "ultimate":
            up = g.add("MMH3UltimateUpscale", f"{label} · MMH3 Ultimate Upscale · zweiter FastH3-Durchgang", cfg=1.0)
            for src, slot, name in ((model, 0, "model"), (cond, 0, "conditioning"), (av, 0, "latent"), (noise, 0, "noise"),
                                    (sampler, 0, "sampler"), (sigmas, 0, "sigmas"), (shared["up_param"], 0, "latent_upscale_param"),
                                    (shared["t_param"], 0, "temporal_split_param"), (shared["s_param"], 0, "spatial_split_param")):
                g.connect(src, slot, up, name)
            latent = up
        else:
            split = g.add("LTXVSeparateAVLatent", f"{label} · Video- und Audio-Latent trennen")
            g.connect(av, 0, split, "av_latent")
            lat3d = _dyn(g, "MinimaxH3LatentUpscaler3D", f"{label} · Latent Upscaler 3D · gelerntes Modell",
                         [LATENT_UPSCALER, "target dimensions", 1280, 704, 32, True, True, "rocm", "bf16"])
            g.connect(split, 0, lat3d, "latent")
            g.connect(planner, 3, lat3d, "mode.width")
            g.connect(planner, 4, lat3d, "mode.height")
            join = g.add("LTXVConcatAVLatent", f"{label} · hochskaliertes Video + Original-Audio-Latent")
            g.connect(lat3d, 0, join, "video_latent")
            g.connect(split, 1, join, "audio_latent")
            guider = g.add("BasicGuider", f"{label} · Guider · CFG 1")
            g.connect(model, 0, guider, "model")
            g.connect(cond, 0, guider, "conditioning")
            latent = g.add("SamplerCustomAdvanced", f"{label} · FastH3 Nachschärfen · 2 Schritte")
            for src, slot, name in ((noise, 0, "noise"), (guider, 0, "guider"), (sampler, 0, "sampler"), (sigmas, 0, "sigmas"), (join, 0, "latent_image")):
                g.connect(src, slot, latent, name)
        decode = g.add("VAEDecode", f"{label} · H3-Video-VAE dekodieren")
        g.connect(latent, 0, decode, "samples")
        g.connect(vae, 0, decode, "vae")
        images = decode
    else:
        model, vae = shared["model"], shared["vae"]
        resize = _dyn(g, "ResizeImageMaskNode", f"{label} · auf Zielgröße (Lanczos)", ["scale dimensions", 1280, 704, "disabled", "lanczos"])
        # Match-type slots are stored resolved, as the frontend saves them (official SeedVR2 template).
        resize["inputs"][0]["type"] = "IMAGE,MASK"
        resize["outputs"][0]["type"] = "IMAGE"
        g.connect(load, 0, resize, "input")
        g.connect(planner, 3, resize, "resize_type.width")
        g.connect(planner, 4, resize, "resize_type.height")
        pre = g.add("SeedVR2Preprocess", f"{label} · SeedVR2 vorbereiten")
        g.connect(resize, 0, pre, "resized_images")
        encode = g.add("VAEEncodeTiled", f"{label} · SeedVR2-VAE Encode · Kachel 1024", tile_size=1024, overlap=128, temporal_size=64, temporal_overlap=8)
        g.connect(pre, 0, encode, "pixels")
        g.connect(vae, 0, encode, "vae")
        chunk = _dyn(g, "SeedVR2TemporalChunk", f"{label} · zeitlich aufteilen (auto)", [2, "auto"])
        g.connect(encode, 0, chunk, "latent")
        condition = g.add("SeedVR2Conditioning", f"{label} · SeedVR2 Conditioning")
        g.connect(model, 0, condition, "model")
        g.connect(chunk, 0, condition, "vae_conditioning")
        sample = g.add("KSampler", f"{label} · SeedVR2 · 1 Schritt", seed=3130459, steps=1, cfg=1.0, sampler_name="euler", scheduler="simple", denoise=1.0)
        for src, slot, name in ((model, 0, "model"), (condition, 0, "positive"), (condition, 1, "negative"), (chunk, 0, "latent_image")):
            g.connect(src, slot, sample, name)
        merge = g.add("SeedVR2TemporalMerge", f"{label} · Chunks zusammenführen")
        g.connect(sample, 0, merge, "latents")
        g.connect(chunk, 1, merge, "temporal_overlap")
        decode = g.add("VAEDecodeTiled", f"{label} · SeedVR2-VAE Decode · Kachel 512", tile_size=512, overlap=128, temporal_size=64, temporal_overlap=8)
        g.connect(merge, 0, decode, "samples")
        g.connect(vae, 0, decode, "vae")
        post = g.add("SeedVR2PostProcessing", f"{label} · SeedVR2 Nachbearbeitung", color_correction_method="none")
        g.connect(decode, 0, post, "images")
        g.connect(resize, 0, post, "original_resized_images")
        images = post
    save = g.add("DaWVUSaveBlock", f"{label} · Block speichern + Vorschau mit Originalton", block_index=0, index_offset=offset)
    g.connect(plan, 0, save, "plan")
    g.connect(images, 0, save, "images")
    if index_source is not None:
        g.connect(index_source[0], index_source[1], load, "block_index")
        g.connect(index_source[0], index_source[1], save, "block_index")
    return save


def build(method: str, schemas: dict) -> dict:
    spec = METHODS[method]
    g = Graph(schemas)
    target, low, high = spec["blocks"]
    planner = g.add("DaWVUPlanner", "VU 1 · Video wählen · Blöcke an Schnitten · Zielgröße ×1,5",
                    video="video.mp4", project_name="Upscale", scale=1.5, target_block_seconds=target, min_block_seconds=low,
                    max_block_seconds=high, method_tag=method)
    plan_view = g.add("PixaromaShowText", "BLOCKPLAN · Blöcke, Schnitte, Zielgröße")
    g.connect(planner, 5, plan_view, "source")
    shared: dict = {}
    if method in ("ultimate", "latent3d"):
        model, vae, audio_vae, cond, sampler, sigmas = _h3_models(g, spec["sampling"])
        shared.update(model=model, vae=vae, audio_vae=audio_vae, cond=cond, sampler=sampler, sigmas=sigmas)
        if method == "ultimate":
            # Learned 3D latent upscale instead of Rodent's bicubic: at denoise 0.25 the bicubic latent kept visible blocks
            # and FastH3 turned them into invented objects (glasses, caps, glitch lines) on the finished test video.
            up = g.add("MMH3LatentUpscaleWithModelParams", "ULTIMATE · Zielgröße aus dem Planer · gelerntes 3D-Upscale-Modell",
                       model_name=LATENT_UPSCALER, device="cuda", precision="bf16")
            g.connect(planner, 3, up, "width")
            g.connect(planner, 4, up, "height")
            tparam = g.add("MMH3TemporalSplitParams", "ULTIMATE · zeitliche Chunks 136 / Überlappung 17 / Anker 1,0",
                           chunk_length=136, temporal_overlap=17, anchor_strength=1.0)
            sparam = g.add("MMH3SpatialSplitParams", "ULTIMATE · räumliche Kacheln auto · Token-Budget 70000",
                           tile_size_mode="auto", tile_width=864, tile_height=480, spatial_w_overlap=128, spatial_h_overlap=128,
                           fade_width=32, fade_height=32, min_tile_size=352, overlap_mode="earlier", overlap_blend="linear",
                           joint_steps=True, token_budget=70000)
            g.connect(planner, 3, sparam, "upscale_width")
            g.connect(planner, 4, sparam, "upscale_height")
            shared.update(up_param=up, t_param=tparam, s_param=sparam)
    else:
        shared["model"] = g.add("UNETLoader", "SEEDVR2 · 3B INT8 ConvRot", unet_name=SEEDVR2_MODEL)
        shared["vae"] = g.add("VAELoader", "SEEDVR2 · EMA-VAE fp16", vae_name=SEEDVR2_VAE)

    first = _block_chain(g, method, "BLOCK 1", planner, planner, shared)
    gate = g.add("PixaromaPauseImage", "FREIGABE · Block 1 prüfen → Continue skaliert den Rest")
    gate["widgets_values"] = [""]
    gate["properties"]["pauseImageState"] = {"gate": "pause"}
    gate["size"] = [420, 520]
    g.connect(first, 1, gate, "image")
    loop_start = g.add("PixaromaLoopStart", "LOOP START · Runden = Blöcke − 1 (aus dem Plan)", total=2)
    g.connect(planner, 2, loop_start, "total")
    g.connect(gate, 0, loop_start, "value1")
    loop_save = _block_chain(g, method, "LOOP", planner, planner, shared, index_source=(loop_start, 6), offset=1)
    g.connect(loop_start, 0, loop_save, "after")
    loop_end = g.add("PixaromaLoopEnd", "LOOP END · nächster Block / Ende")
    g.connect(loop_save, 0, loop_end, "value1")
    g.connect(loop_start, 5, loop_end, "loop")
    final = g.add("DaWVUFinalize", "VU 4 · HOCHSKALIERTES VIDEO · Originalton unverändert")
    g.connect(planner, 0, final, "plan")
    g.connect(loop_end, 0, final, "after")
    g.note(f"START HIER · {spec['title']} · v1.2.3", START_NOTES[method])
    g.note("ABLAUF · Blöcke, Freigabe, Fortsetzen, Vergleich der drei Methoden", FLOW_NOTE)
    lines = []
    for entry in json.loads((SOURCES / "models.json").read_text(encoding="utf-8")):
        if method in entry["methods"]:
            url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
            lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}`")
    packs = {"ultimate": "- Node-Pack [PlagueKind-Nodes](https://github.com/PlagueKind/Comfyui-PlagueKind-Nodes) (vom Updater mitgepflegt)\n",
             "latent3d": "- Node-Pack [Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) (vom Updater mitgepflegt)\n",
             "seedvr2": "- SeedVR2-Nodes sind im ComfyUI-Core enthalten.\n"}[method]
    g.note("DOWNLOADS · Modelle / Node-Packs", "# Benötigte Dateien\n\n" + "\n\n".join(lines) + "\n\n" + packs)
    return finish(g, schemas, method)


def finish(g: Graph, schemas: dict, method: str) -> dict:
    path = METHODS[method]["path"]
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v123:" + path))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {"version": 1, "method": method, "source_manifest": "tools/workflow_templates/v123/models.json",
                            "video": "https://www.youtube.com/watch?v=fjWeg8so8y0",
                            "validation_report": "performance/rdna4/video-upscale-v123-validation.json"}
    refine_workflow(g.w, schemas)
    before = copy.deepcopy(migration.OBJECT_INFO)
    try:
        migration.OBJECT_INFO.update(schemas)
        inserted = insert_device_selectors(g.w, DEVICES)
        install_central_device_control(g.w, path, h3_director=False, devices=DEVICES)
        g.w["extra"].setdefault("dawasteh_dual_gpu", {}).update({
            "version": 3, "scope": "collection-wide optional GPU placement", "family": "Video Upscaling",
            "source": f"workflows/{path}", "server": "127.0.0.1:8188", "backend": "ROCm/HIP", "selector_count": inserted,
            "curated_split_default": False, "defaults": dict(DEVICES),
            "execution": "device placement only; the H3 text encoder is loaded and released inside the prompt node",
        })
        g.w["extra"][migration.MIGRATION_KEY] = {"version": migration.MIGRATION_VERSION, "release": "v0.9.2",
                                                 "dual_gpu_folder_dissolved": True, "rodent_method": True, "rodent_credit": "Nerdy Rodent"}
        migration._ensure_parameter_notes(g.w)
        migration._normalize_counters(g.w)
        g.w = migration.migrate_workflow(g.w, path)
    finally:
        migration.OBJECT_INFO.clear()
        migration.OBJECT_INFO.update(before)
    for node in g.w["nodes"]:
        if node["type"] == "MarkdownNote":
            text = node.get("widgets_values", [""])[0]
            lines = sum(max(1, (len(line) + 79) // 80) for line in text.splitlines())
            node["size"] = [680, max(620, 160 + lines * 22)]
    apply_rodent_layout(g.w, path)
    return g.w


COMMON_START = """
1. **VU 1** · Video wählen oder hochladen (jede Länge; Unterordner in `input/` werden angezeigt).
   Ein fertiges Video aus `output/` direkt verwenden: vollständigen Pfad in `video_path_override` eintragen.
2. `scale` (Standard ×1,5) bestimmt die Zielgröße; sie wird auf 32 px gerundet (864×480 → 1280×704).
3. **Run**: Block 1 wird hochskaliert und mit Originalton gezeigt, das Gate *FREIGABE* hält an.
4. **Continue** skaliert alle weiteren Blöcke; das fertige Video landet unter
   `output/video/DaWasteh_VideoUpscale/`. Der Originalton wird unverändert übernommen (`-c:a copy`).
"""
START_NOTES = {
    "ultimate": "# MiniMax H3 Ultimate Upscale · FastH3\n\nMethode 1 aus Nerdy Rodents Video „MiniMax H3 Ultimate Upscaling“: "
                "PlagueKinds **MMH3 Ultimate Upscale** rechnet das Video als zweiten FastH3-Durchgang in der Zielgröße neu – "
                "in zeitlichen Chunks mit Anker zum Vorgänger-Chunk und bei Bedarf in räumlichen Kacheln. **Die meisten neuen "
                "Details**, verändert das Bild aber am stärksten.\n" + COMMON_START +
                "\n**Zwei Abweichungen von Rodent, beide am fertigen Testvideo gemessen:**\n\n"
                "- **Denoise 0,25** statt 0,45: Mit FastH3s Sigma-Shift 10 startet 0,45 bei 97,5 % Rauschen und erfindet die "
                "Szene bei fertigen Videos neu. 0,45 passt nur für Latents, die gerade mit demselben Prompt erzeugt wurden.\n"
                "- **Gelerntes 3D-Upscale-Modell** (`MMH3 Latent Upscale with Model Params`, gleiches Pack) statt bicubic: "
                "Bei 0,25 blieb das bicubisch vergrößerte Latent blockig, FastH3 machte daraus Brillen, Kappen und "
                "Glitch-Linien. Mit dem Modell bleibt das Bild sauber und bekommt trotzdem neue Details.\n\n"
                "Den PROMPT so schreiben, dass er beschreibt, was im Video zu sehen ist.\n",
    "latent3d": "# MiniMax H3 Latent Upscaler 3D · FastH3\n\nMethode 2 aus Nerdy Rodents Video: LBH-123-AIs gelerntes **Latent-"
                "Upscale-Modell (3D)** vergrößert nur das Video-Latent, das Original-Audio-Latent bleibt, danach schärft "
                "FastH3 mit **2 Schritten (beta)** nach. **Bleibt am nächsten am Original** und ist am schnellsten.\n" + COMMON_START +
                "\nBlöcke höchstens 4,45 s (107 Frames = 17·6+5, gerade Latent-Länge): Das Nachschärfen läuft ohne Kacheln "
                "in einem Durchgang. Gemessen auf der R9700: 108 Frames werden auf 124 aufgefüllt, FastH3 lädt dann nur "
                "teilweise (27 statt 12 s/Schritt). Denoise 0,25 (Start-Sigma 0,68) statt Rodents 0,4.\n",
    "seedvr2": "# SeedVR2 3B INT8 · Video-Upscale\n\nMethode 3 aus Nerdy Rodents Video: **SeedVR2** (nativ im ComfyUI-Core) "
               "restauriert in einem einzigen Schritt. **Schärfer, aber praktisch keine neuen Details** – ideal als letzter "
               "Durchgang, auch nach Methode 1 oder 2. Kein Prompt nötig.\n" + COMMON_START +
               "\nKacheln: Encode 1024, Decode 512. Gemessen auf der R9700 (1280×704, 167 Frames): Decode 512 und 640 gleich "
               "schnell, 768 etwas schneller, fordert aber 8,65 GiB am Stück an und lief im Dauerlauf nach zwei Blöcken "
               "in den VRAM-Guard (Fragmentierung). Das gekachelte VAE-Decoding ist der größte Zeitblock.\n",
}
FLOW_NOTE = """# Wie die Upscale-Workflows arbeiten

**Blöcke:** Der Planer teilt das Video in Blöcke. Grenzen liegen bevorzugt auf **harten Schnitten** (Bildsprung deutlich
über der Bewegung in der Umgebung), sonst auf ruhigen Frames. So fallen unabhängig neu berechnete Blöcke nicht auf.
Jeder Block wird auf das Raster der Methode aufgefüllt (H3 17k+5, SeedVR2 4k+1) und nach dem Hochskalieren wieder
exakt gekürzt: das Ergebnis hat genau so viele Frames wie das Original.

**Originalton:** Die H3-Methoden bekommen den echten Ton als Audio-Latent (fixiert), das Ergebnis trägt am Ende die
unveränderte Tonspur der Quelldatei.

**Fortsetzen:** Fertige Blöcke werden bei einem erneuten Lauf übersprungen (auch nach Absturz). Nach Änderungen an
Denoise/Schritten `resume_existing_blocks` ausschalten oder `method_tag` ändern.

**Vergleich (Rodent):** Ultimate Upscale = meiste neue Details, stärkste Veränderung · Latent Upscaler 3D = nah am
Original, sehr schnell · SeedVR2 = schärfer, keine neuen Details, gut als letzter Schritt.
"""


def build_all() -> dict[str, dict]:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    return {spec["path"]: build(method, schemas) for method, spec in METHODS.items()}


def main() -> None:
    for path, workflow in build_all().items():
        target = ROOT / "workflows" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
