#!/usr/bin/env python3
"""Rebuild the v1.2.6 WAN video-upscale workflow (WAN 2.2 A14B low-noise expert, WAN 2.1 T2V 14B compatible).

Lanczos to the target size -> WAN VAE encode -> 2 steps of the low-noise expert + lightx2v LoRA at denoise 0.15 in
native-size spatial tiles (DaWVUSpatialTiles, MultiDiffusion) and temporal context windows -> WAN VAE decode.
Each block carries a 5-frame lead-in that is rendered along and dropped. Same DaW block frame as v1.2.3:
planner -> block 1 -> Pixaroma approval gate -> Pixaroma loop -> final film with the original audio stream-copied.
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
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_central_device_control, insert_device_selectors, install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v126"
MARKER = "dawasteh_video_upscale_v126"
RELEASE = "v1.2.6"
BS = "\\"
PATH = "Video Upscaling/WAN22_14B_LowNoise-Video-Upscale.json"
TITLE = "WAN 2.2 Video Upscale · A14B Low-Noise · lightx2v"
MODEL = "WAN" + BS + "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors"
LORA = "WAN" + BS + "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"
TEXT_ENCODER = "UMT5" + BS + "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE = "WAN" + BS + "wan_2.1_vae.safetensors"
DEVICES = {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"}
ALIGN = "wan (4k+1)"
# Measured on the R9700 (see docs/VIDEO_UPSCALE_WAN_V126.md); the tests pin these values.
SETTINGS = {
    "scale": 1.5, "blocks": (7.0, 2.0, 10.0), "method_tag": "wan22", "lead_frames": 5,
    "shift": 5.0, "lora_strength": 1.0,
    "sampler": {"seed": 20260926, "steps": 2, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 0.15},
    "tiles": {"tile_width": 832, "tile_height": 480, "overlap": 128},
    "windows": {"context_length": 33, "context_overlap": 8, "context_schedule": "standard_static", "fuse_method": "pyramid"},
    "encode_tile": (512, 64), "decode_tile": (512, 64), "temporal_tile": (4096, 4),
}
PROMPT = ("Cinematic live-action video in high detail with sharp focus, natural matte skin texture with visible pores, "
          "fine individual hair strands, crisp fabric texture, clean edges, realistic light. The people, places, clothing, "
          "camera framing and motion stay exactly as in the original footage; only resolution, texture and fine detail improve.")
NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
            "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")


def _dyn(g: Graph, kind: str, title: str, values: list) -> dict:
    """Node with a dynamic combo: the frontend serialises the selected key followed by its sub-widget values."""
    node = g.add(kind, title)
    node["widgets_values"] = list(values)
    return node


def _models(g: Graph) -> dict:
    s = SETTINGS
    # Read-only mapping: the core loaders let Windows charge the 14.3 GB model and the 6.7 GB UMT5 file to the commit
    # limit on top of their VRAM copies (v1.2.4); with them the 2016x1152 run peaked at 90.7 of 105.4 GB.
    unet = g.add("DaWVUReadOnlyUNETLoader", "WAN · 2.2 T2V A14B Low-Noise fp8 · RAM-schonend (WAN 2.1 T2V 14B passt ebenso)",
                 unet_name=MODEL)
    lora = g.add("LoraLoaderModelOnly", f"WAN · lightx2v 4-Step-LoRA (low noise) · Stärke {s['lora_strength']:g}",
                 lora_name=LORA, strength_model=s["lora_strength"])
    g.connect(unet, 0, lora, "model")
    shift = g.add("ModelSamplingSD3", f"WAN · Shift {s['shift']:g}", shift=s["shift"])
    g.connect(lora, 0, shift, "model")
    t = s["tiles"]
    tiles = g.add("DaWVUSpatialTiles", f"WAN · räumliche Kacheln {t['tile_width']}×{t['tile_height']} · Überlappung {t['overlap']}", **t)
    g.connect(shift, 0, tiles, "model")
    w = s["windows"]
    windows = g.add("WanContextWindowsManual",
                    f"WAN · zeitliche Fenster {w['context_length']} Frames · Überlappung {w['context_overlap']} ({w['fuse_method']})",
                    context_length=w["context_length"], context_overlap=w["context_overlap"],
                    context_schedule=w["context_schedule"], fuse_method=w["fuse_method"])
    g.connect(tiles, 0, windows, "model")
    clip = g.add("DaWVUReadOnlyCLIPLoader", "WAN · UMT5-XXL fp8 Textencoder · RAM-schonend", clip_name=TEXT_ENCODER, type="wan")
    prompt = g.prompt("PROMPT · was im Video zu sehen ist + gewünschte Bildqualität (Englisch)", PROMPT)
    positive = g.add("CLIPTextEncode", "WAN · Prompt (positiv)")
    g.connect(clip, 0, positive, "clip")
    g.connect(prompt, 0, positive, "text")
    negative = g.add("CLIPTextEncode", "WAN · Negativ-Prompt (nur bei CFG > 1 wirksam)", text=NEGATIVE)
    g.connect(clip, 0, negative, "clip")
    vae = g.add("VAELoader", "WAN · 2.1-VAE (für 2.2 A14B und 2.1 14B)", vae_name=VAE)
    return {"model": windows, "positive": positive, "negative": negative, "vae": vae}


def _block_chain(g: Graph, label: str, plan, planner, shared: dict, *, index_source=None, offset=0):
    s = SETTINGS
    load = g.add("DaWVULoadBlock", f"{label} · Block laden · {s['lead_frames']} Frames Vorlauf", block_index=0, index_offset=offset,
                 frame_alignment=ALIGN, lead_frames=s["lead_frames"])
    g.connect(plan, 0, load, "plan")
    resize = _dyn(g, "ResizeImageMaskNode", f"{label} · auf Zielgröße (Lanczos)", ["scale dimensions", 1280, 704, "disabled", "lanczos"])
    # Match-type slots are stored resolved, as the frontend saves them.
    resize["inputs"][0]["type"] = "IMAGE,MASK"
    resize["outputs"][0]["type"] = "IMAGE"
    g.connect(load, 0, resize, "input")
    g.connect(planner, 3, resize, "resize_type.width")
    g.connect(planner, 4, resize, "resize_type.height")
    (tile, overlap), (t_size, t_overlap) = s["encode_tile"], s["temporal_tile"]
    encode = g.add("VAEEncodeTiled", f"{label} · WAN-VAE Encode · Kachel {tile}", tile_size=tile, overlap=overlap,
                   temporal_size=t_size, temporal_overlap=t_overlap)
    g.connect(resize, 0, encode, "pixels")
    g.connect(shared["vae"], 0, encode, "vae")
    k = s["sampler"]
    sample = g.add("KSampler", f"{label} · WAN Low-Noise · {k['steps']} Schritte · Denoise {k['denoise']:g}",
                   seed=k["seed"], steps=k["steps"], cfg=k["cfg"], sampler_name=k["sampler_name"], scheduler=k["scheduler"],
                   denoise=k["denoise"])
    for src, name in ((shared["model"], "model"), (shared["positive"], "positive"), (shared["negative"], "negative"), (encode, "latent_image")):
        g.connect(src, 0, sample, name)
    tile, overlap = s["decode_tile"]
    decode = g.add("VAEDecodeTiled", f"{label} · WAN-VAE Decode · Kachel {tile}", tile_size=tile, overlap=overlap,
                   temporal_size=t_size, temporal_overlap=t_overlap)
    g.connect(sample, 0, decode, "samples")
    g.connect(shared["vae"], 0, decode, "vae")
    save = g.add("DaWVUSaveBlock", f"{label} · Block speichern + Vorschau mit Originalton", block_index=0, index_offset=offset)
    g.connect(plan, 0, save, "plan")
    g.connect(decode, 0, save, "images")
    if index_source is not None:
        g.connect(index_source[0], index_source[1], load, "block_index")
        g.connect(index_source[0], index_source[1], save, "block_index")
    return save


def build(schemas: dict) -> dict:
    s = SETTINGS
    g = Graph(schemas)
    target, low, high = s["blocks"]
    planner = g.add("DaWVUPlanner", f"VU 1 · Video wählen · Blöcke an Schnitten · Zielgröße ×{s['scale']:g}".replace(".", ","),
                    video="video.mp4", project_name="Upscale", scale=s["scale"], target_block_seconds=target,
                    min_block_seconds=low, max_block_seconds=high, method_tag=s["method_tag"])
    plan_view = g.add("PixaromaShowText", "BLOCKPLAN · Blöcke, Schnitte, Zielgröße")
    g.connect(planner, 5, plan_view, "source")
    shared = _models(g)
    first = _block_chain(g, "BLOCK 1", planner, planner, shared)
    gate = g.add("PixaromaPauseImage", "FREIGABE · Block 1 prüfen → Continue skaliert den Rest")
    gate["widgets_values"] = [""]
    gate["properties"]["pauseImageState"] = {"gate": "pause"}
    gate["size"] = [420, 520]
    g.connect(first, 1, gate, "image")
    loop_start = g.add("PixaromaLoopStart", "LOOP START · Runden = Blöcke − 1 (aus dem Plan)", total=2)
    g.connect(planner, 2, loop_start, "total")
    g.connect(gate, 0, loop_start, "value1")
    loop_save = _block_chain(g, "LOOP", planner, planner, shared, index_source=(loop_start, 6), offset=1)
    g.connect(loop_start, 0, loop_save, "after")
    loop_end = g.add("PixaromaLoopEnd", "LOOP END · nächster Block / Ende")
    g.connect(loop_save, 0, loop_end, "value1")
    g.connect(loop_start, 5, loop_end, "loop")
    final = g.add("DaWVUFinalize", "VU 4 · HOCHSKALIERTES VIDEO · Originalton unverändert")
    g.connect(planner, 0, final, "plan")
    g.connect(loop_end, 0, final, "after")
    g.note(f"START HIER · {TITLE} · {RELEASE}", START_NOTE)
    g.note("WAN 2.1 / 2.2 · welche Modelle passen", MODELS_NOTE)
    g.note("ABLAUF · Blöcke, Freigabe, Fortsetzen", FLOW_NOTE)
    lines = []
    for entry in json.loads((SOURCES / "models.json").read_text(encoding="utf-8")):
        url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
        lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}`")
    g.note("DOWNLOADS · Modelle", "# Benötigte Dateien\n\n" + "\n\n".join(lines) +
           "\n\nAlle Nodes sind im ComfyUI-Core bzw. im DaWasteh-Bundle enthalten.\n")
    return finish(g, schemas)


def finish(g: Graph, schemas: dict) -> dict:
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v126:" + PATH))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {"version": 1, "release": RELEASE, "method": "wan22_low_noise",
                            "source_manifest": "tools/workflow_templates/v126/models.json",
                            "validation_report": "performance/rdna4/video-upscale-wan-v126-validation.json"}
    refine_workflow(g.w, schemas)
    before = copy.deepcopy(migration.OBJECT_INFO)
    try:
        migration.OBJECT_INFO.update(schemas)
        inserted = insert_device_selectors(g.w, DEVICES)
        install_central_device_control(g.w, PATH, h3_director=False, devices=DEVICES)
        g.w["extra"].setdefault("dawasteh_dual_gpu", {}).update({
            "version": 3, "scope": "collection-wide optional GPU placement", "family": "Video Upscaling",
            "source": f"workflows/{PATH}", "server": "127.0.0.1:8188", "backend": "ROCm/HIP", "selector_count": inserted,
            "curated_split_default": False, "defaults": dict(DEVICES),
            "execution": "device placement only; model, UMT5 and VAE on the R9700",
        })
        g.w["extra"][migration.MIGRATION_KEY] = {"version": migration.MIGRATION_VERSION, "release": "v0.9.2",
                                                 "dual_gpu_folder_dissolved": True, "rodent_method": True, "rodent_credit": "Nerdy Rodent"}
        migration._ensure_parameter_notes(g.w)
        migration._normalize_counters(g.w)
        g.w = migration.migrate_workflow(g.w, PATH)
    finally:
        migration.OBJECT_INFO.clear()
        migration.OBJECT_INFO.update(before)
    for node in g.w["nodes"]:
        if node["type"] == "MarkdownNote":
            text = node.get("widgets_values", [""])[0]
            lines = sum(max(1, (len(line) + 79) // 80) for line in text.splitlines())
            node["size"] = [680, max(620, 160 + lines * 22)]
    apply_rodent_layout(g.w, PATH)
    return g.w


START_NOTE = """# WAN 2.2 Video Upscale · A14B Low-Noise · lightx2v

Vergrößert ein fertiges Video mit Lanczos auf die Zielgröße und lässt dann den **Low-Noise-Experten von WAN 2.2 A14B**
mit der lightx2v-LoRA **2 Schritte bei Denoise 0,15** nachrechnen. Der Low-Noise-Experte ist für die letzte, feine Phase
trainiert: Er ergänzt Haut-, Haar-, Stoff- und Fassadendetails und lässt Komposition, Personen und Bewegung stehen.

1. **VU 1** · Video wählen oder hochladen (jede Länge; Unterordner in `input/` werden angezeigt).
   Ein fertiges Video aus `output/` direkt verwenden: vollständigen Pfad in `video_path_override` eintragen.
2. `scale` (Standard ×1,5) bestimmt die Zielgröße; sie wird auf 32 px gerundet (1344×768 → 2016×1152).
3. **PROMPT** beschreibt, was im Video zu sehen ist, und die gewünschte Bildqualität (Englisch).
4. **Run**: Block 1 wird hochskaliert und mit Originalton gezeigt, das Gate *FREIGABE* hält an.
5. **Continue** skaliert alle weiteren Blöcke; das fertige Video landet unter
   `output/video/DaWasteh_VideoUpscale/`. Der Originalton wird unverändert übernommen (`-c:a copy`).

**Denoise** im KSampler: 0,10 = am treuesten (Schildtexte bleiben), **0,15 = Standard**,
0,20 = mehr neue Details, 0,30 zeichnet Gesichter und Schilder neu (Start-σ 0,69) – nicht für fertige Videos.
2 statt 4 Schritte: im Test gleiche Abweichung zur Quelle, halbe Zeit.
"""
MODELS_NOTE = """# WAN 2.1 und 2.2 · Modelle tauschen

Der Graph ist für alle WAN-14B-Textmodelle gleich; nur Modell und LoRA ändern sich (VAE und Textencoder bleiben).

| Modell | Diffusion-Modell | LoRA | VAE |
|---|---|---|---|
| **WAN 2.2 A14B (Standard)** | `wan2.2_t2v_low_noise_14B_fp8_scaled` | `wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise` | `wan_2.1_vae` |
| WAN 2.1 T2V 14B | `wan2.1_t2v_14B_fp8_scaled` | `lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16` | `wan_2.1_vae` |

- WAN 2.1 (live getestet): Modell aus `Comfy-Org/Wan_2.1_ComfyUI_repackaged`, LoRA aus `Kijai/WanVideo_comfy` (`Lightx2v/`).
  Treuer als 2.2 (Augenfarbe, Schrift bleiben), aber weniger neue Details.
- Der **High-Noise-Experte** von WAN 2.2 ist nicht nötig: Er formt in den ersten Schritten die grobe Szene, die beim
  Upscaling schon feststeht.
- Ohne LoRA: CFG 3–5 und 8–10 Schritte; dann wirkt auch der Negativ-Prompt. Deutlich langsamer.

# Kacheln, Fenster, Vorlauf

- **Räumliche Kacheln 832×480** (MultiDiffusion, bei jedem Schritt überblendet): WAN 14B ist auf 480p/720p trainiert.
  Im ganzen 2016×1152-Bild zeichnet es Details in seinem eigenen Maßstab (wirkt wie vergrößertes 720p); in Kacheln
  nativer Größe entstehen feinere Details, und es ist 2,2× schneller (43 statt 95 s pro Schritt und Fenster).
- **Zeitliche Fenster 33 Frames**, 8 überlappend: lange Blöcke ohne Speicherwachstum.
- **5 Frames Vorlauf**: Das erste Latent steht bei WAN für einen einzelnen Frame, der Blockanfang wurde stärker neu
  gezeichnet (Sprung nach Frame 0). Der Vorlauf wird mitgerechnet und verworfen; innerhalb einer Einstellung sind es
  echte vorherige Frames, an einem Schnitt der wiederholte erste Frame.
"""
FLOW_NOTE = """# Wie der WAN-Upscale arbeitet

**Blöcke:** Der Planer teilt das Video in Blöcke (Ziel 7 s, höchstens 10 s). Grenzen liegen bevorzugt auf **harten
Schnitten**, sonst auf ruhigen Frames: Jeder Block wird unabhängig neu berechnet, an einem Schnitt fällt das nicht auf.
Jeder Block wird auf das WAN-Raster 4k+1 aufgefüllt und bekommt 5 Frames Vorlauf; beides wird nach dem Hochskalieren
wieder abgeschnitten, das Ergebnis hat genau so viele Frames wie das Original.

**Originalton:** Das fertige Video trägt die unveränderte Tonspur der Quelldatei (`-c:a copy`).

**Fortsetzen:** Fertige Blöcke werden bei einem erneuten Lauf übersprungen (auch nach Absturz). Nach Änderungen an
Denoise/Schritten `resume_existing_blocks` ausschalten oder `method_tag` ändern.

**Rechenzeit (R9700):** bei 2016×1152 rund 2,4 min pro Sekunde Video (6,3-s-Szene in 15 min). Die Ziel-Langseite
möglichst bis ~2500 px halten; für 1920×1088-Quellen `scale` 1,25.

**Vergleich:** SeedVR2 (v1.2.3) = am treuesten, kaum neue Details · WAN 2.1 = treu mit etwas Detail · WAN 2.2 = die
meisten neuen Details (Haut, Haar, Stoff, Fassaden), verändert kleine unnatürliche Details der Quelle.
"""


def build_all() -> dict[str, dict]:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    return {PATH: build(schemas)}


def main() -> None:
    for path, workflow in build_all().items():
        target = ROOT / "workflows" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
