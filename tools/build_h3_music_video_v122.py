#!/usr/bin/env python3
"""Rebuild the FastH3 complete-song music-video workflow (v1.2.2, extended in v1.2.4/v1.2.5/v1.2.7); no runtime/model writes.

Flat RODENT graph: Pixaroma inputs -> DaW MV2 planner / prompt writer / one-time encoder ->
scene 1 -> MV 5b review -> MV 5c upscale -> Pixaroma loop over the remaining scenes (extend, MV 5b review and
MV 5c upscale after every scene) -> original film + upscaled film + comparison, original audio stream-copied.

v1.2.4: MV 0 loads FastH3 read-only with an optional realism LoRA (trigger word into MV 3, model signature
into the resume keys) and keeps extend scenes at up to 1920x1088 inside VRAM and the Windows commit limit.
v1.2.5: MV 2 "auto" writes with the GGUF model of the start profile (Qwen3.8 27B through llama.cpp on gpu:1,
started only while prompts are written) and falls back to Qwen3.5 4B inside ComfyUI. MV 5b replaces the
Pixaroma image gate: every new scene is shown as video with the song audio and waits for Weiter / Neu rendern.
v1.2.7: MV 5c upscales every accepted take before the next scene (one switch node: off, SeedVR2, WAN 2.2, H3 Latent
Upscaler 3D or H3 Ultimate Upscale); MV 6 also writes the upscaled film and a side-by-side comparison. The size list
gets the user's favourites 960x544 and 1280x704 (both reach ~1920 px wide on the 32-px grid); 960x544 is selected.
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
    from tools.upgrade_v113 import MARKER_KEY as V113_MARKER_KEY, MARKER_VERSION as V113_MARKER_VERSION
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_central_device_control, insert_device_selectors, install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout
    from upgrade_v113 import MARKER_KEY as V113_MARKER_KEY, MARKER_VERSION as V113_MARKER_VERSION

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v122"
PATH = "Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json"
MARKER = "dawasteh_h3_music_video_v122"
BS = "\\"
MODEL = "MiniMax H3" + BS + "fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors"
TEXT_ENCODER = "MiniMax H3" + BS + "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
VIDEO_VAE = "MiniMax H3" + BS + "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE = "MiniMax H3" + BS + "minimax_h3_audio_vae_fp32.safetensors"
LLM = "auto (GGUF aus dem Startprofil, sonst Qwen3.5 4B)"   # llm_backend.AUTO
LORA = "MiniMax H3" + BS + "h3-realism-people-t2v-i2v-r2v.safetensors"
LORA_STRENGTH = 0.8
TRIGGER = "r34l1sm"
RELEASE = "v1.2.7"
DEVICES = {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"}  # measured v1.2.2 placement (migrate_workflows_v092)
SAMPLING = {"steps": 8, "sampler": "res_multistep", "scheduler": "simple", "shift_video": 10.0, "shift_audio": 3.0,
            "attention": "comfy kitchen attention", "sparse": "vsa", "keep_percent": 10.0}

LYRICS_PLACEHOLDER = """[Verse 1]
Erste Zeile der Strophe
Zweite Zeile der Strophe

[Chorus]
Refrain-Zeile eins
Refrain-Zeile zwei

[Guitar Solo]

[Outro]
Letzte Zeile"""
IDEA_EXAMPLE = ("The singer from the character sheet walks through a futuristic, ruined city street, enters a house, "
                "picks something up in a room, climbs through a roof hatch onto the roof, and the song ends with a "
                "drone flight over the dystopian landscape.")
# v1.2.7: the user's own list from the live workflow (2026-09-26): 1280x704 added, 960x544 selected, 960x544 and
# 1280x704 starred (Pixaroma stores stars orientation-free as "short x long")
SIZES_STATE = {
    "version": 1,
    "sizes": [[864, 480], [960, 544], [1056, 608], [1152, 640], [1216, 672], [1280, 704], [1280, 736], [1344, 768],
              [1376, 768], [1504, 832], [1664, 928], [1824, 1024], [1920, 1088]],
    "selected": 1, "orientation": "landscape", "snap": 32, "accent": None, "collapsed": False,
    "starred": ["1664x928", "928x1664", "1920x1088", "1088x1920", "864x480", "544x960", "704x1280"], "w": 960, "h": 544,
}
UPSCALE = {"upscale": True, "method": "WAN 2.2 Low-Noise · treu + neue Details (Standard)", "target_long_side": 1920}


def _block_sparse(g: Graph) -> dict:
    node = g.add("BlockSparseAttention", "FASTH3 · VSA Sparse Attention · 10 % (trainiertes FastH3-Muster)")
    # Dynamic-combo sub-widget (keep_percent) follows its selector, exactly as the frontend serialises it.
    node["widgets_values"] = ["vsa", SAMPLING["keep_percent"], 0.2, 1.0, "", 12288, 256, "exact_kv_and_rows", False]
    node["size"] = [420, 300]
    return node


def _scene_chain(g: Graph, label: str, plan, model, sampler, sigmas, vae, audio_vae, *, index_source=None, offset=0):
    setup = g.add("DaWMV2SceneSetup", f"{label} · Szene vorbereiten · Song-Audio fixiert" + (" + Extend" if offset else ""),
                  scene_index=0, index_offset=offset)
    noise = g.add("RandomNoise", f"{label} · Rauschen · Seed pro Szene aus dem Plan")
    guider = g.add("BasicGuider", f"{label} · Guider · CFG 1 (FastH3 destilliert)")
    sample = g.add("SamplerCustomAdvanced", f"{label} · FastH3 Sampling · {SAMPLING['steps']} Schritte")
    save = g.add("DaWMV2SaveScene", f"{label} · Szene speichern + Vorschau mit Originalton", scene_index=0, index_offset=offset)
    for src, slot, dst, name in [
        (plan, 0, setup, "plan"), (vae, 0, setup, "vae"), (audio_vae, 0, setup, "audio_vae"),
        (setup, 2, noise, "noise_seed"), (model, 0, guider, "model"), (setup, 0, guider, "conditioning"),
        (noise, 0, sample, "noise"), (guider, 0, sample, "guider"), (sampler, 0, sample, "sampler"),
        (sigmas, 0, sample, "sigmas"), (setup, 1, sample, "latent_image"),
        (plan, 0, save, "plan"), (vae, 0, save, "vae"), (sample, 0, save, "latent"),
    ]:
        g.connect(src, slot, dst, name)
    if index_source is not None:
        g.connect(index_source[0], index_source[1], setup, "scene_index")
        g.connect(index_source[0], index_source[1], save, "scene_index")
    return setup, save


def _review(g: Graph, title: str, save):
    """v1.2.5 MV 5b: the scene as video with the original audio; the run waits for Weiter / Neu rendern."""
    review = g.add("DaWMV2ReviewScene", title, review=True)
    review["size"] = [560, 640]
    g.connect(save, 0, review, "scene")
    return review


def _upscale(g: Graph, title: str, review, settings, model, vae, audio_vae):
    """v1.2.7 MV 5c: upscales the take MV 5b has accepted before the next scene is rendered."""
    node = g.add("DaWMV2UpscaleScene", title)
    node["size"] = [480, 420]
    for src, name in ((review, "scene"), (settings, "upscale"), (model, "model"), (vae, "vae"), (audio_vae, "audio_vae")):
        g.connect(src, 0, node, name)
    return node


def build(schemas: dict) -> dict:
    g = Graph(schemas)
    # --- Origin inputs ---------------------------------------------------------------------------
    lyrics = g.prompt("LYRICS · Songtext mit [Verse]/[Chorus] (oder [mm:ss.xx]-Zeitstempel)", LYRICS_PLACEHOLDER)
    idea = g.prompt("VIDEOIDEE · Story, Look, Orte, Stimmung (Deutsch oder Englisch)", IDEA_EXAMPLE)
    sizes = g.add("PixaromaSizes", "VIDEOFORMAT · ★ 960×544 / 1280×704 + Upscale · Hochformat per Klick")
    sizes["widgets_values"] = [copy.deepcopy(SIZES_STATE)]
    sizes["properties"]["sizesState"] = json.dumps(SIZES_STATE, separators=(",", ":"))
    sizes["size"] = [260, 480]
    characters = []
    for k in range(1, 4):
        load = g.add("PixaromaLoadImage", f"CHARAKTER {k} · Sheet (optional · Strg+M zum Aktivieren)", image=f"character_sheet_{k}.png")
        load["mode"] = 2  # muted: an absent optional sheet must not block prompt validation
        load["properties"]["loadImagePixState"] = json.dumps({"version": 1, "mode": "off", "snap": 0})
        load["size"] = [380, 560]
        characters.append(load)

    # --- Planning ----------------------------------------------------------------------------------
    planner = g.add("DaWMV2Planner", "MV 1 · Song + Lyrics → Dauer, Timing, Szenenplan", song="song.mp3",
                    project_name="Music_Video")
    g.connect(lyrics, 0, planner, "lyrics")
    g.connect(idea, 0, planner, "video_idea")
    g.connect(sizes, 0, planner, "width")
    g.connect(sizes, 1, planner, "height")
    plan_view = g.add("PixaromaShowText", "SZENENPLAN · Längen, Abschnitte, Lyrics je Szene")
    g.connect(planner, 3, plan_view, "source")
    writer = g.add("DaWMV2PromptWriter", "MV 2 · MiniMax-Prompts · Qwen3.8 27B / Qwen3.5 (Idee + Lyrics + Charaktere)", llm=LLM)
    g.connect(planner, 0, writer, "plan")
    for k, load in enumerate(characters, 1):
        g.connect(load, 0, writer, f"character_{k}")
    prompt_view = g.add("PixaromaShowText", "PROMPTS · alle Szenen im MiniMax-Format")
    g.connect(writer, 1, prompt_view, "source")
    encoder = g.add("DaWMV2EncodeScenes", "MV 3 · H3-Textencoder · alle Szenen einmal, danach freigegeben",
                    text_encoder=TEXT_ENCODER)
    g.connect(writer, 0, encoder, "plan")

    # --- Model chain (FastH3 profile as tested locally) ------------------------------------------
    unet = g.add("DaWMV2LoadModel", "MV 0 · FASTH3 + REALISMUS-LORA · RAM-schonend · bis 1920×1088", unet_name=MODEL,
                 lora_name=LORA, lora_strength=LORA_STRENGTH, trigger_word=TRIGGER, high_resolution_memory=True)
    g.connect(unet, 1, encoder, "model_info")
    shift = g.add("MiniMaxH3SigmaShift", "FASTH3 · Sigma-Shift Video 10 / Audio 3", shift_video=10.0, shift_audio=3.0)
    attention = g.add("ModelAttentionBackend", "FASTH3 · Comfy Kitchen Attention", attention=SAMPLING["attention"])
    sparse = _block_sparse(g)
    g.connect(unet, 0, shift, "model")
    g.connect(shift, 0, attention, "model")
    g.connect(attention, 0, sparse, "model")
    vae = g.add("VAELoader", "VAE · MiniMax H3 Video", vae_name=VIDEO_VAE)
    audio_vae = g.add("VAELoader", "VAE · MiniMax H3 Audio", vae_name=AUDIO_VAE)
    sampler = g.add("KSamplerSelect", "SAMPLER · res_multistep", sampler_name=SAMPLING["sampler"])
    sigmas = g.add("BasicScheduler", "SCHEDULER · simple · 8 Schritte", scheduler=SAMPLING["scheduler"], steps=SAMPLING["steps"], denoise=1.0)
    g.connect(sparse, 0, sigmas, "model")

    # --- Upscale switch (v1.2.7): one node for scene 1 and the loop -------------------------------------
    upscale = g.add("DaWMV2UpscaleSettings", "MV 5c · UPSCALE AN/AUS + METHODE · nach jeder Freigabe", **UPSCALE)
    upscale["size"] = [460, 200]

    # --- Scene 1 + review + upscale ---------------------------------------------------------------------
    _, first_save = _scene_chain(g, "SZENE 1", encoder, sparse, sampler, sigmas, vae, audio_vae)
    g.connect(encoder, 0, first_save, "after")
    first_review = _review(g, "SZENE 1 · PRÜFEN · Video mit Originalton → Weiter / Neu rendern", first_save)
    first_upscale = _upscale(g, "SZENE 1 · HOCHSKALIEREN (MV 5c) · nur der freigegebene Take", first_review, upscale,
                             sparse, vae, audio_vae)

    # --- Remaining scenes: Pixaroma loop, one extend + review + upscale per round --------------------------
    loop_start = g.add("PixaromaLoopStart", "LOOP START · Runden = Szenen − 1 (aus dem Plan)", total=2)
    g.connect(planner, 2, loop_start, "total")
    g.connect(first_upscale, 0, loop_start, "value1")
    _, loop_save = _scene_chain(g, "LOOP", encoder, sparse, sampler, sigmas, vae, audio_vae,
                                index_source=(loop_start, 6), offset=1)
    g.connect(loop_start, 0, loop_save, "after")
    loop_review = _review(g, "LOOP · PRÜFEN · jede weitere Szene → Weiter / Neu rendern", loop_save)
    loop_upscale = _upscale(g, "LOOP · HOCHSKALIEREN (MV 5c) · jede freigegebene Szene vor der nächsten", loop_review,
                            upscale, sparse, vae, audio_vae)
    loop_end = g.add("PixaromaLoopEnd", "LOOP END · nächste Szene / Ende")
    g.connect(loop_upscale, 0, loop_end, "value1")
    g.connect(loop_start, 5, loop_end, "loop")
    final = g.add("DaWMV2Finalize", "MV 6 · FERTIGES MUSIKVIDEO · Original + Upscale + Vergleich · Originalton unverändert")
    g.connect(encoder, 0, final, "plan")
    g.connect(loop_end, 0, final, "after")

    g.note("START HIER · Song → Musikvideo · FastH3 · v1.2.7", START_NOTE)
    g.note("ABLAUF · Planung, Freigabe, Upscale, Extend-Schleife, Fortsetzen", FLOW_NOTE)
    g.note("UPSCALE · MV 5c · vier Methoden im Vergleich", UPSCALE_NOTE)
    model_lines = []
    for entry in json.loads((SOURCES / "models.json").read_text(encoding="utf-8")):
        url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
        model_lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}`")
    g.note("DOWNLOADS · Modelle / Zielordner", "# Benötigte Dateien\n\n" + "\n\n".join(model_lines) +
           "\n\n# Nur für MV 5c (je nach gewählter Methode)\n\n" + "\n\n".join(_upscale_model_lines()) + DOWNLOAD_TAIL)
    return finish(g, schemas)


def _upscale_model_lines() -> list[str]:
    """Files MV 5c needs beyond FastH3 and the H3 VAEs, from the v1.2.3 / v1.2.6 upscale manifests."""
    own = {entry["path"] for entry in json.loads((SOURCES / "models.json").read_text(encoding="utf-8"))}
    labels = {"seedvr2": "SeedVR2", "latent3d": "H3 Latent 3D + H3 Ultimate"}
    lines = []
    for folder in ("v123", "v126"):
        for entry in json.loads((ROOT / "tools/workflow_templates" / folder / "models.json").read_text(encoding="utf-8")):
            used = [labels[m] for m in entry.get("methods", []) if m in labels] if folder == "v123" else ["WAN 2.2"]
            if used and entry["path"] not in own:
                url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
                lines.append(f"- {used[0]}: [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}`")
    return lines


def finish(g: Graph, schemas: dict) -> dict:
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v122:" + PATH))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {
        "version": 1,
        "release": RELEASE,
        "model": MODEL,
        "lora": {"name": LORA, "strength": LORA_STRENGTH, "trigger": TRIGGER},
        "sampling": SAMPLING,
        "source_manifest": "tools/workflow_templates/v122/models.json",
        "validation_report": "performance/rdna4/h3-music-video-v124-validation.json",
        "validation_report_v122": "performance/rdna4/h3-music-video-v122-validation.json",
        "replaces": "v0.8.x-v1.2.1 DaWH3MusicVideoDirectorDualGPU one-node director",
    }
    refine_workflow(g.w, schemas)
    before = copy.deepcopy(migration.OBJECT_INFO)
    try:
        migration.OBJECT_INFO.update(schemas)
        inserted = insert_device_selectors(g.w, DEVICES)
        install_central_device_control(g.w, PATH, h3_director=False, devices=DEVICES)
        g.w["extra"].setdefault("dawasteh_dual_gpu", {}).update({
            "version": 3, "scope": "collection-wide optional GPU placement", "family": "MiniMax FastH3 Music Video",
            "source": f"workflows/{PATH}", "server": "127.0.0.1:8188", "backend": "ROCm/HIP", "selector_count": inserted,
            "curated_split_default": True, "defaults": dict(DEVICES),
            "execution": "device placement only; text models are loaded and released inside MV 2 / MV 3",
        })
        g.w["extra"][migration.MIGRATION_KEY] = {
            "version": migration.MIGRATION_VERSION, "release": "v0.9.2", "dual_gpu_folder_dissolved": True,
            "rodent_method": True, "rodent_credit": "Nerdy Rodent",
        }
        # FastH3 already runs the vendor sampling that v1.1.3 enforces (shift_audio 3, res_multistep, simple).
        g.w["extra"][V113_MARKER_KEY] = {"version": V113_MARKER_VERSION}
        migration._ensure_parameter_notes(g.w)
        migration._normalize_counters(g.w)
        # Same layer stack as every migrated collection file (duration contract, v0.9.4-v0.9.8 upgrades).
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


START_NOTE = """# Song → komplettes Musikvideo · MiniMax FastH3 · v1.2.7

1. **MV 1** · Song wählen oder hochladen (MP3/WAV/FLAC/M4A/OGG, jede Länge).
2. **LYRICS** einfügen – am besten mit `[Verse 1]`, `[Chorus]` …; `[mm:ss.xx]`-Zeitstempel werden direkt übernommen.
3. **VIDEOIDEE** in eigenen Worten (Deutsch oder Englisch): Story, Orte, Look, Stimmung. Zeilen wie
   `Chorus - …` oder `Verse 2: …` gelten gezielt für diesen Songabschnitt (Ort, Kleidung, Handlung).
4. Optional **bis zu 3 Charaktersheets**: Loader mit **Strg+M** aktivieren, Bild wählen. Charakter 1 ist die Sängerin/der Sänger.
5. **VIDEOFORMAT** im Pixaroma-Sizes-Node wählen. Favoriten (★): **960×544** (Standard) und **1280×704** – beide
   landen mit dem Upscale (MV 5c) bei ~1920 px Breite. Ohne Upscale **1664×928**: ab 1344×768 abwärts zeigen Gesicht
   und Lippen erste Artefakte, 1920×1088 dauert fast doppelt so lange. Sampling pro 7-s-Szene auf der R9700:
   960×544 ≈ 2 min, 1280×704 ≈ 4–5 min, 1664×928 ≈ 8–15 min.
6. **MV 0 · Realismus-LoRA**: standardmäßig fal *Realism People* bei **0,8** mit Triggerwort `r34l1sm`
   (wird automatisch vor jeden Szenen-Prompt gesetzt). `lora_name = none` = reines FastH3.
7. **MV 5c · UPSCALE**: eine Node für das ganze Video – **aus** oder eine der vier Methoden (Standard **WAN 2.2**,
   dazu SeedVR2, H3 Latent Upscaler 3D, H3 Ultimate) und die Ziel-Langseite (Standard 1920: 960×544 → 1920×1088).
8. **Run**. Erst wird geplant, dann Szene 1 gerendert. Nach **jeder** Szene hält der Lauf am Node
   **PRÜFEN (MV 5b)**: Er spielt die Szene **mit Originalton** ab.
   - **✓ Weiter** → MV 5c skaliert genau diesen Take hoch, dann wird die nächste Szene per Extend gerendert.
   - **↻ Neu rendern** → dieselbe Szene mit neuem Seed noch einmal, im selben Lauf. Alle Takes bleiben als
     Reiter wählbar; **Take N nehmen + weiter** übernimmt einen früheren Take.
   - **⏩ Rest ohne Prüfung** → alle weiteren Szenen dieses Laufs ohne Halt (z. B. über Nacht).
   Verworfene Takes werden nie hochskaliert. Am Ende legt MV 6 unter `output/video/DaWasteh_MusicVideo/` das
   **Original**, den **Upscale** und ein **Vergleichsvideo** (links Original, rechts Upscale) ab – alle mit Originalton.
   Ohne Zwischenstopp von Anfang an: beide PRÜFEN-Nodes auf **durchrendern** stellen.

**Lippensynchron:** Jede Szene bekommt den echten Songausschnitt fest in den Audio-Strom von H3 (nicht verrauscht,
nur das Bild wird erzeugt). Am Ende wird die Originaldatei **unverändert** (`-c:a copy`) unter das Video gelegt.

**Abwechslung:** Der Prompt Writer (MV 2, `auto`) schreibt pro Songabschnitt eigene Orte in Story-Reihenfolge,
pro Szene 1–3 Shots mit Schnitten, wechselnden Einstellungsgrößen und Kamerabewegungen. Jede Szene hat einen eigenen Seed.

Bedienung und Grenzen: `docs/H3_MUSIC_VIDEO_V122.md`; LoRA, 1920×1088 und Speicher: `docs/H3_MUSIC_VIDEO_V124.md`;
Prompt Writer mit Qwen3.8 27B und Szenen-Prüfung (MV 5b): `docs/H3_MUSIC_VIDEO_V125.md`;
Upscale nach jeder Freigabe (MV 5c): `docs/H3_MUSIC_VIDEO_V127.md`.
"""

FLOW_NOTE = """# Wie der Workflow arbeitet

**MV 1 · Planer** misst die Songdauer, erkennt Tempo/Energie und richtet die Lyrics mit lokalem
**Whisper small** zeitlich aus. Daraus entstehen Szenen mit **unterschiedlichen Längen** (Standard 4–9 s,
Ziel 7 s), bevorzugt an Abschnitts- und Zeilengrenzen. Die Anzahl ergibt sich aus der Songlänge:
30 s ≈ 5 Szenen, 90 s ≈ 12, 600 s ≈ 80. Ohne Lyrics plant er rein nach Beats und Energie.
Bis 9 s passt FastH3 bei 864×480 vollständig in den VRAM; längere Szenen oder größere Formate laden es
teilweise (im Log: `loaded partially`). Ab ~65 000 Tokens (z. B. 1920×1088) hält MV 0 vor jedem Schritt
genug VRAM für die Aktivierungen frei; die Extend-Szenen laufen dadurch ohne OOM.

**MV 0 · Modell** bildet FastH3 schreibgeschützt ab: Windows verbucht die 22-GB-Datei dann nicht auf das
Commit-Limit (RAM + Auslagerungsdatei). Genau das lief bei 1920×1088 in den Extend-Szenen über und wurde als
„out of memory“ gemeldet. Eine andere LoRA, Stärke oder ein anderes Triggerwort rendert die Szenen neu,
statt alte Ergebnisse fortzusetzen.

**MV 2 · Prompt Writer** (`auto`) startet das GGUF-Modell aus dem Startprofil (Qwen3.8 27B über llama.cpp auf
gpu:1, 12,5 GiB VRAM) bzw. ohne Eintrag Qwen3.5 4B – jeweils nur so lange, wie Prompts fehlen, danach ist der
Speicher wieder frei. Ablauf: Charaktersheets → Textbeschreibung,
Produktionsbibel (Stil, Orte je Abschnitt, Musik), dann pro Szene die Handlung. Ergebnis: MiniMax-Format
`integrated_multimodal_description / overall_soundscape / non_diegetic_music` mit `<d>[English] …</d>`-Lyrics.

**MV 3 · H3-Textencoder** encodiert **alle** Szenen-Prompts einmal und gibt den 26-GB-Encoder danach komplett frei.
In der Render-Schleife bleibt nur FastH3 geladen.

**Szene 1 → PRÜFEN → HOCHSKALIEREN → LOOP (Szene → PRÜFEN → HOCHSKALIEREN)**: Jede weitere Szene friert die letzten
22 Frames der Vorgängerszene (des Originals, nicht des Upscales) am
Anfang ein (nahtloser Extend) und fixiert den passenden Songausschnitt im Audio-Strom. Die Pixaroma-Schleife läuft
`Szenen − 1` Runden; die Rundenzahl kommt automatisch aus dem Plan. **Neu rendern** hängt die Kette
Szene vorbereiten → Sampling → Speichern → Prüfen für dieselbe Szene noch einmal ein (neuer Seed), die Schleife zählt
erst nach **Weiter** weiter. Verworfene Takes liegen unter `takes/` im Projektordner.

**MV 5c · Hochskalieren** bekommt nur, was MV 5b freigegeben hat, und skaliert es vor der nächsten Szene hoch
(`upscaled/<Methode>_<B>x<H>/` im Projektordner). Die Extend-Kette bleibt beim Original; der Upscale ist eine
zweite Fassung jeder Szene. Einstellungen und Messwerte: Notiz **UPSCALE**.

**Fortsetzen:** Alles liegt unter `output/DaWasteh_H3_MusicVideo_v2/<Projekt>`. Ein erneuter Run mit gleichen Eingaben
überspringt fertige Szenen ohne Sampling – auch nach Absturz oder Neustart. Freigegebene Szenen laufen ohne Halt
durch; eine Szene, die beim Abbruch noch auf Prüfung wartete, wird sofort wieder gezeigt (ohne neu zu rendern).
`resume_existing_scenes = aus` rendert bewusst alles neu. Fertige Upscales werden ebenso übersprungen; eine andere
Methode oder Zielgröße skaliert nur die fertigen Szenen neu (eigener Ordner, frühere Upscales bleiben).

**FastH3-Grenzen:** FastH3 ist nur für Text-to-Video+Audio destilliert. Charaktersheets werden deshalb als Text
beschrieben (nicht als Ref2VA-Bild eingespeist); die Identität trägt der Extend über die eingefrorenen Frames.
"""

UPSCALE_NOTE = """# MV 5c · Upscale nach jeder Freigabe

Eine Node (**MV 5c · UPSCALE AN/AUS + METHODE**) schaltet den Upscale für das ganze Video: **aus** oder eine der
vier Methoden aus `Video Upscaling/` – dieselben Nodes und Einstellungen wie dort. Hochskaliert wird genau der Take,
den du in MV 5b mit **Weiter** freigibst, noch bevor die nächste Szene gerendert wird. Verworfene Takes
(**Neu rendern**) kommen nie bei MV 5c an.

Gemessen an einer 5,4-s-Szene, 960×544 → 1920×1088, R9700 (Nachweis und Bilder: `docs/H3_MUSIC_VIDEO_V127.md`):

| Methode | Ergebnis | Zeit pro Szene | ≈ 90-s-Song |
|---|---|---|---|
| **WAN 2.2 Low-Noise** (Standard) | bleibt am Original (Gesicht, Mundform, Pose), neue Haut-, Haar- und Stoffdetails | 12,9 min | 3,6 h |
| **SeedVR2 3B** | scharfe Kanten, wirkt bei ×2 gemalt (Haarspitzen, Hautflecken) | 8,2 min | 2,3 h |
| **H3 Latent Upscaler 3D** | am schnellsten und sehr scharf, zeichnet aber Mimik und Pose neu (Lippensync prüfen) | 4,9 min | 1,4 h |
| **H3 Ultimate Upscale** | zweiter FastH3-Durchgang in Kacheln, zeichnet am freiesten neu | 7,6 min | 2,1 h |

Dazu kommt das Rendern selbst (960×544: ≈ 2 min pro Szene). Alle vier rechnen in der Zielgröße; 1280×704 →
1920×1056 kostet beim Upscale deshalb etwa gleich viel, nur das Rendern dauert länger.

- Die beiden **H3-Methoden** rechnen mit dem laufenden FastH3 (inkl. LoRA) und dem **eigenen Prompt der Szene** nach –
  kein zweites großes Modell im Speicher. **SeedVR2** und **WAN** laden ihre Modelle einmal pro Lauf.
- **Ziel-Langseite** 1920 (Standard): 960×544 → 1920×1088, 1280×704 → 1920×1056, 1664×928 → 1920×1056.
- Methode oder Zielgröße wechseln geht jederzeit: Ein neuer Run rendert keine Szene neu, sondern skaliert nur die
  fertigen Szenen (eigener Ordner je Methode und Größe, frühere Upscales bleiben erhalten).
- **MV 6** schreibt das Original, den Upscale (beide mit unverändertem Originalton) und bei
  `comparison = nebeneinander` ein Vergleichsvideo: links das Original (Lanczos auf Zielgröße), rechts der Upscale.
"""

DOWNLOAD_TAIL = """

Qwen3.5 4B (`models/text_encoders/Qwen/qwen3.5_4b_bf16.safetensors`, Rückfall für MV 2) und Whisper small werden
aus den bereits vorhandenen Bundle-Installationen genutzt. Optional für MV 2: ein Qwen3.8-27B-GGUF plus
`llama-server` (HIP oder Vulkan), eingetragen in `start-MultiGPU.ps1` (`$PromptLlmGguf`, `$LlamaServerExe`). Whisper lädt beim ersten Planer-Lauf ggf. ~460 MB nach `~/.cache/whisper`.

Kein Cloud-API-Aufruf. Lizenz FastH3/MiniMax H3: siehe MiniMax-H3-Modellkarte (MiniMax Model License).
"""


def main() -> None:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    workflow = build(schemas)
    target = ROOT / "workflows" / PATH
    target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(target)


def build_all() -> dict[str, dict]:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    return {PATH: build(schemas)}


if __name__ == "__main__":
    main()
