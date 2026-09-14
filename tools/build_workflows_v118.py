#!/usr/bin/env python3
"""Build explicit, flat RODENT graphs from pinned official model workflows.

No model downloads, runtime writes, or GPU execution. Generated files are
unvalidated until the separate live test report proves their execution.
"""

from __future__ import annotations
import argparse
import copy
import json
import uuid
from pathlib import Path

try:
    from tools import migrate_workflows_v092 as migration
    from tools.generate_dual_gpu_workflows import install_run_timer
    from tools.refine_workflows import refine_workflow
    from tools.rodent_layout import apply_rodent_layout
    from tools.integrate_duration_seconds import (
        _install_explicit_control,
        DurationSpec,
        DURATION_KEY,
    )
    from tools.upgrade_v097 import (
        specialize_game_asset_template,
        ENVIRONMENT_PATH,
        _rebuild_link_references,
    )
except ModuleNotFoundError:  # Direct execution from tools/.
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout
    from integrate_duration_seconds import (
        _install_explicit_control,
        DurationSpec,
        DURATION_KEY,
    )
    from upgrade_v097 import (
        specialize_game_asset_template,
        ENVIRONMENT_PATH,
        _rebuild_link_references,
    )

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v118"
SCHEMAS = SOURCES / "node-schemas.json"
STYLE = "English, cinematic industrial rock, warm male vocal, 96 BPM, analog synthesizers, distorted guitar, driving drums, mysterious underground laboratory atmosphere"
LYRICS = "[Verse]\nThrough the tunnels, past the light\nWe keep moving through the night\n[Chorus]\nHold the line and find the way\nWe will see another day"
PHYSICS = "A locked-off camera observes a red rubber ball falling onto a concrete floor, bouncing twice with decreasing height and settling naturally. Consistent gravity, continuous motion, stable scene geometry, realistic soft lighting."


class Graph:
    def __init__(self, schemas, workflow=None):
        self.schemas = schemas
        self.w = (
            copy.deepcopy(workflow)
            if workflow
            else {
                "nodes": [],
                "links": [],
                "groups": [],
                "config": {},
                "extra": {},
                "version": 0.4,
            }
        )

    def add(self, kind, title=None, **values):
        schema = self.schemas[kind]
        nid = max([0] + [int(n["id"]) for n in self.w["nodes"]]) + 1
        n = {
            "id": nid,
            "type": kind,
            "title": title or schema.get("display_name", kind),
            "pos": [0, 0],
            "size": [420, 260],
            "flags": {},
            "order": nid,
            "mode": 0,
            "inputs": [],
            "outputs": [],
            "properties": {"Node name for S&R": kind},
            "widgets_values": [],
        }
        for section in ("required", "optional"):
            for name, spec in schema.get("input", {}).get(section, {}).items():
                typ = spec[0]
                cfg = spec[1] if len(spec) > 1 else {}
                widget = not cfg.get("forceInput") and (
                    isinstance(typ, list)
                    or typ
                    in (
                        "COMBO",
                        "STRING",
                        "INT",
                        "FLOAT",
                        "BOOLEAN",
                        "COMFY_DYNAMICCOMBO_V3",
                        "LOAD_3D",
                        "COLOR",
                    )
                )
                slot = {
                    "name": name,
                    "type": "COMBO" if isinstance(typ, list) else typ,
                    "link": None,
                }
                if section == "optional":
                    slot["shape"] = 7
                if widget:
                    options = typ if isinstance(typ, list) else cfg.get("options", [])
                    default = cfg.get(
                        "default",
                        options[0]
                        if options
                        else {
                            "STRING": "",
                            "INT": 0,
                            "FLOAT": 0.0,
                            "BOOLEAN": False,
                        }.get(typ, ""),
                    )
                    if isinstance(default, dict):
                        default = default["key"]
                    n["widgets_values"].append(values.pop(name, default))
                    if cfg.get("control_after_generate"):
                        n["widgets_values"].append("fixed")
                    slot["widget"] = {"name": name}
                n["inputs"].append(slot)
        if values:
            raise ValueError((kind, values))
        for i, typ in enumerate(schema.get("output", [])):
            n["outputs"].append(
                {
                    "name": schema.get("output_name", schema["output"])[i],
                    "type": typ,
                    "links": [],
                }
            )
        self.w["nodes"].append(n)
        return n

    def connect(self, source, slot, target, name):
        if not any(x["name"] == name for x in target.get("inputs", [])):
            target.setdefault("inputs", []).append(
                {
                    "name": name,
                    "type": source["outputs"][slot]["type"],
                    "widget": {"name": name},
                    "link": None,
                }
            )
        input_slot = next(
            i for i, x in enumerate(target["inputs"]) if x["name"] == name
        )
        old = target["inputs"][input_slot].get("link")
        self.w["links"] = [link for link in self.w["links"] if link[0] != old]
        lid = max([0] + [link[0] for link in self.w["links"]]) + 1
        self.w["links"].append(
            [
                lid,
                source["id"],
                slot,
                target["id"],
                input_slot,
                source["outputs"][slot]["type"],
            ]
        )
        _rebuild_link_references(self.w)

    def prompt(self, title, text):
        n = self.add("PixaromaPrompt", title)
        n["properties"].update(
            {
                "cnr_id": "ComfyUI-Pixaroma",
                "promptState": {
                    "text": text,
                    "order": "mine",
                    "sep": "\n",
                    "accent": None,
                    "showExpanded": True,
                },
            }
        )
        n["widgets_values"] = [""]
        n["size"] = [480, 360]
        return n

    def note(self, title, text):
        n = {
            "id": max([0] + [int(n["id"]) for n in self.w["nodes"]]) + 1,
            "type": "MarkdownNote",
            "title": title,
            "pos": [0, 0],
            "size": [680, 620],
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": [],
            "outputs": [],
            "properties": {"Node name for S&R": "MarkdownNote"},
            "widgets_values": [text],
        }
        self.w["nodes"].append(n)

    def finish(self, path, family, inputs):
        install_run_timer(self.w)
        self.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v118:" + path))
        self.w["revision"] = 0
        self.w.setdefault("extra", {})["dawasteh_v118"] = {
            "version": 1,
            "family": family,
            "inputs": inputs,
            "validation": "live-tested",
            "validation_report": "performance/rdna4/v118-validation.json",
            "source_manifest": "tools/workflow_templates/v118/sources.json",
        }
        note_schemas = copy.deepcopy(self.schemas)
        # LOAD_3D is a persisted frontend viewport widget. The historical note
        # mapper predates it; treating it as text here keeps width/height aligned
        # without changing old workflow generations or runtime node schemas.
        for schema in note_schemas.values():
            for section in schema.get("input", {}).values():
                for spec in section.values():
                    if isinstance(spec, list) and spec[0] == "LOAD_3D":
                        spec[0] = "STRING"
        refine_workflow(self.w, note_schemas)
        previous_schemas = migration.OBJECT_INFO.copy()
        try:
            migration.OBJECT_INFO.update(note_schemas)
            result = migration.migrate_workflow(self.w, path)
        finally:
            # Older deterministic generators share this cache. New schemas must
            # not leak into their notes or depend on test/import execution order.
            migration.OBJECT_INFO.clear()
            migration.OBJECT_INFO.update(previous_schemas)
        for n in result["nodes"]:
            if n["type"] == "MarkdownNote":
                text = n.get("widgets_values", [""])[0]
                lines = sum(
                    max(1, (len(line) + 79) // 80) for line in text.splitlines()
                )
                n["size"] = [680, max(620, 160 + lines * 22)]
        apply_rodent_layout(result, path)
        return result


def yue(schemas, mode):
    g = Graph(schemas)
    ck = g.add(
        "CheckpointLoaderSimple",
        "YuE2 3B INT8 · NUR PRIVAT",
        ckpt_name="yue2_3b_int8_convrot.safetensors",
    )
    style = g.prompt("STYLE · Genre / Sprache / Stimme / Instrumente", STYLE)
    lyrics = g.prompt("LYRICS · eigene Texte mit [Verse] / [Chorus]", LYRICS)
    music = g.add(
        "YuE2GenerateMusic",
        max_duration=120.0,
        mode="melody" if mode == "Audio-Cover" else "full",
    )
    for n, field in [(ck, "clip"), (style, "style"), (lyrics, "lyrics")]:
        g.connect(n, 1 if n is ck else 0, music, field)
    if mode == "Text-to-Music":
        abc = g.add(
            "YuE2GenerateABC", "ABC PLAN · full oder melody", max_abc_tokens=8192
        )
        g.connect(ck, 1, abc, "clip")
        g.connect(style, 0, abc, "style")
        g.connect(lyrics, 0, abc, "lyrics")
    elif mode == "Audio-Cover":
        audio = g.add(
            "LoadAudio",
            "REFERENZ · eigene/freigegebene Musik",
            audio="v118_private_reference.flac",
        )
        enc = g.add(
            "AudioEncoderLoader", audio_encoder_name="sheetsage2_bf16.safetensors"
        )
        abc = g.add("SheetSage2AudioToABC", mode="melody")
        g.connect(audio, 0, abc, "audio")
        g.connect(enc, 0, abc, "audio_encoder")
    else:
        abc = g.prompt("ABC · eigene Partitur oder leer = ohne Planung", "")
    g.connect(abc, 0, music, "abc")
    preview = g.add("PreviewAny", "ABC · Kontrolle")
    g.connect(abc, 0, preview, "source")
    seconds = g.add("PreviewAny", "TATSÄCHLICHE GENERIERTE SEKUNDEN")
    g.connect(music, 1, seconds, "source")
    empty = g.add("EmptyYuE2LatentAudio")
    g.connect(music, 1, empty, "seconds")
    neg = g.add("ConditioningZeroOut")
    g.connect(music, 0, neg, "conditioning")
    sampler = g.add(
        "KSampler",
        steps=32,
        cfg=1.0,
        sampler_name="dpm_2",
        scheduler="sgm_uniform",
        denoise=1.0,
    )
    for n, slot, name in [
        (ck, 0, "model"),
        (music, 0, "positive"),
        (neg, 0, "negative"),
        (empty, 0, "latent_image"),
    ]:
        g.connect(n, slot, sampler, name)
    decode = g.add("VAEDecodeAudio")
    g.connect(ck, 2, decode, "vae")
    g.connect(sampler, 0, decode, "samples")
    save = g.add(
        "SaveAudioAdvanced", filename_prefix="Music/PRIVATE_YuE2/" + mode, format="flac"
    )
    g.connect(decode, 0, save, "audio")
    g.note(
        "START HIER · YuE2 / PRIVAT / KEIN STREAMING",
        "**CC-BY-NC-4.0: nur nichtkommerziell.** Für Bastis komplett privates HalfLife3-Projekt; Streaming-Musik weiter mit ACE-Step. Kein Voice-Cloning und kein Echtzeit-Streaming: die gesamte Audiodatei wird nach der Queue ausgegeben.\n\nStyle beschreibt Klang, Sprache, Tempo und Stimme; Lyrics enthalten nur singbaren Text/Abschnitts-Tags. Eigene ABC-Notation kann im ABC-Workflow eingegeben oder leer gelassen werden (Modus off). Im Text-Workflow erzeugt der ABC-Node Melodie/Akkorde. Cover überträgt symbolische Melodie, nicht die Identität der Referenzstimme. Bei Cover beide mode-Felder zusammen auf melody/full setzen.\n\nMax Duration ist eine OBERGRENZE, keine exakte Länge. Standard 120s; für schnelle Vorabtests auf 30s reduzieren und für längere Stücke schrittweise erhöhen. Seed und Sampling sind sichtbar. INT8, SDPA, kein torch.compile. Native Vorlage: Comfy-Org/workflow_templates v0.11.60.\n\nNur eigene oder ausreichend lizenzierte Referenzen laden. Private Songideen werden nicht im öffentlichen Repository veröffentlicht.",
    )
    path = f"Music Generation/YuE2_3B_INT8-PRIVATE-{mode}.json"
    return path, g.finish(path, "YuE2", mode)


def cosmos(schemas, mode):
    image_only = mode == "Text-to-Image"
    source = SOURCES / (
        "cosmos_predict2_2b_t2i_example.json"
        if image_only
        else "cosmos_predict2_2b_i2v_example.json"
    )
    w = json.loads(source.read_text())
    w["nodes"] = [n for n in w["nodes"] if n["type"] not in ("SaveAnimatedWEBP",)]
    kept = {n["id"] for n in w["nodes"]}
    w["links"] = [link for link in w["links"] if link[1] in kept and link[3] in kept]
    _rebuild_link_references(w)
    g = Graph(schemas, w)
    nodes = {n["id"]: n for n in g.w["nodes"]}
    nodes[15]["widgets_values"] = ["WAN\\wan_2.1_vae.safetensors"]
    nodes[3]["widgets_values"] = [118, "fixed", 30, 4, "euler", "simple", 1]
    nodes[6]["widgets_values"] = [""]
    nodes[7]["widgets_values"] = [""]
    prompt = g.prompt("PHYSICS PROMPT · sichtbare Bewegung, keine Simulation", PHYSICS)
    g.connect(prompt, 0, nodes[6], "text")
    negative = g.prompt("NEGATIV · optional", "")
    g.connect(negative, 0, nodes[7], "text")
    if image_only:
        nodes[27]["widgets_values"] = ["Physics/Cosmos2/Text-to-Image"]
    else:
        nodes[31]["widgets_values"] = ["Physics/Cosmos2/" + mode, "vp9", 16, 24]
        nodes[31]["mode"] = 0
        nodes[29]["widgets_values"] = ["v118_physics_start.png", "image"]
        nodes[29]["title"] = "STARTBILD · Ausgangsszene"
        if mode == "First-Last-Frame":
            end = g.add(
                "LoadImage", "ENDBILD · ähnliche Szene", image="v118_physics_end.png"
            )
            g.connect(end, 0, nodes[28], "end_image")
        elif mode == "Video-Continuation":
            video = g.add(
                "DaWVideoFrames",
                "VIDEO · maximal 5 Referenzframes @16fps · OHNE AUDIO",
                video="v118_physics_reference.mp4",
                fps=16,
                width=848,
                height=480,
                frame_limit=5,
            )
            g.connect(video, 0, nodes[28], "start_image")
            g.w["nodes"].remove(nodes[29])
        elif mode == "Text-to-Video":
            # The requested family uses its dedicated text-to-image model first.
            model = g.add(
                "UNETLoader",
                "TEXT→STARTBILD · Cosmos2 2B",
                unet_name="cosmos_predict2_2B_t2i.safetensors",
                weight_dtype="default",
            )
            empty = g.add("EmptySD3LatentImage", width=848, height=480, batch_size=1)
            sampler = g.add(
                "KSampler",
                seed=118,
                steps=30,
                cfg=4,
                sampler_name="euler",
                scheduler="simple",
                denoise=1,
            )
            for n, slot, name in [
                (model, 0, "model"),
                (nodes[6], 0, "positive"),
                (nodes[7], 0, "negative"),
                (empty, 0, "latent_image"),
            ]:
                g.connect(n, slot, sampler, name)
            dec = g.add("VAEDecode")
            g.connect(sampler, 0, dec, "samples")
            g.connect(nodes[15], 0, dec, "vae")
            g.connect(dec, 0, nodes[28], "start_image")
            g.w["nodes"].remove(nodes[29])
    g.note(
        "START HIER · Cosmos Predict2 2B / Physik-VIDEO",
        "Cosmos erzeugt Pixel/Videos mit physikalisch orientierten Bewegungen, KEINE Simulation, keine Collision, keine Kraft-/Materialdaten. Für echte Game-Physik die separaten GamePhysics-Ausgaben benutzen.\n\n2B statt 14B begrenzt VRAM/RAM. Video: offizielles 480p/16fps-Modell, 848×480, 93 Frames, 30 Euler/simple-Schritte. Das ergibt 5,8125s Containerdauer. Auflösung/FPS nicht beliebig ändern: Gewichte sind darauf trainiert.\n\nEingaben: Text→Bild, Bild→Video, Start+Endbild, kurzer Videoanfang→Fortsetzung; Text→Video kombiniert den T2I- mit dem Video2World-Checkpoint. Video-Referenz wird auf 16fps und maximal fünf Frames begrenzt; keine Audioübernahme. Start/End müssen dieselbe Szene zeigen, Übergänge sind nicht garantiert. First/Last ist experimentell: In der lokalen Sichtprüfung trat Farbkippen am Ende auf; Text→Video zeigte kleine Geisterfragmente. Erfolgreiche Ausführung bedeutet keine physikalische Qualitätsgarantie.\n\nWICHTIG: oldt5_xxl ist T5 1.0; vorhandenes Flux-T5 1.1 ist kein Ersatz. Predict2 verwendet WAN 2.1 VAE, NICHT Cosmos CV8. NVIDIA Open Model License und Modell-Nutzungsbedingungen prüfen. Quelle: comfyanonymous/ComfyUI_examples/cosmos_predict2.",
    )
    path = (
        f"Text to Image/Cosmos_Predict2_2B-{mode}.json"
        if image_only
        else f"Controlled Video/Cosmos_Predict2_2B-{mode}.json"
    )
    if not image_only:
        if not any(x["name"] == "length" for x in nodes[28]["inputs"]):
            nodes[28]["inputs"].append(
                {
                    "name": "length",
                    "type": "INT",
                    "widget": {"name": "length"},
                    "link": None,
                }
            )
        _install_explicit_control(
            g.w, path, DurationSpec(16, 4, 5, ((28, "length"),), 93 / 16)
        )
        g.w["extra"][DURATION_KEY] = {
            "version": 1,
            "unit": "seconds",
            "mode": "explicit-seconds-to-model-valid-frames",
            "fps": 16,
            "frame_alignment": "4n+1",
            "targets": ["28.length"],
        }
    return path, g.finish(path, "Cosmos Predict2", mode)


def asset(schemas, family, mode):
    source = ROOT / "tools/workflow_templates/3d_pixal3d_trellis2_image_to_model.json"
    w = specialize_game_asset_template(
        json.loads(source.read_text(encoding="utf-8-sig")), ENVIRONMENT_PATH
    )
    g = Graph(schemas, w)
    nodes = {n["id"]: n for n in g.w["nodes"]}
    for n in g.w["nodes"]:
        if n["type"] in ("MarkdownNote", "Note", "PixaromaNote"):
            n["widgets_values"] = [""]
    g.w["nodes"] = [
        n
        for n in g.w["nodes"]
        if n["type"] not in ("MarkdownNote", "Note", "PixaromaNote")
    ]
    g.w["extra"] = {}
    nodes[122]["widgets_values"] = ["v118_asset.png", "image"]
    if family == "TRELLIS2":
        nodes[319]["widgets_values"] = ["trellis_2_int8_convrot.safetensors", "default"]
        nodes[319]["title"] = "TRELLIS.2 INT8 · R9700"
        nodes[15]["widgets_values"] = ["dino_v3_vit_l.safetensors"]
        cond = g.add("Trellis2Conditioning")
        g.connect(nodes[15], 0, cond, "clip_vision_model")
        g.connect(nodes[312], 0, cond, "image")
        # TRELLIS expects its own framing, not Pixal's 1.1 crop.
        nodes[312]["widgets_values"] = [1024, 1024, 1.0, 0, "#000000"]
    elif mode == "MultiView-PBR-Collision":
        nodes[319]["widgets_values"] = [
            "pixal3d_multiview_int8_convrot.safetensors",
            "default",
        ]
        cond = g.add(
            "Pixal3DMultiViewConditioning",
            "VIEWS · kalibriert, gleiche Skala, 90° Abstand",
            fov=20.0,
        )
        g.connect(nodes[15], 0, cond, "clip_vision_model")
        for view in ("front", "left", "back", "right"):
            load = g.add(
                "LoadImage",
                view.upper() + " · schwarzer Hintergrund / gleiches Framing",
                image=f"v118_asset_{view}.png",
            )
            g.connect(load, 0, cond, view)
    else:
        cond = nodes[298]
    if cond is not nodes[298]:
        for link in list(g.w["links"]):
            if link[1] == 298:
                target = nodes[link[3]]
                g.connect(cond, link[2], target, target["inputs"][link[4]]["name"])
    prefix = f"GameDev/{family}/{mode}/asset"
    nodes[322]["widgets_values"] = [prefix, "", 1024, 1024]
    nodes[322]["title"] = "SICHTMESH · " + (
        "untexturiertes GLB" if mode == "Shape-Collision" else "PBR-GLB"
    )
    if mode == "Shape-Collision":
        # Untextured export uses simplified game mesh, skipping texture/UV baking.
        conv = g.add("MeshToFile3D")
        g.connect(nodes[186], 0, conv, "mesh")
        g.connect(conv, 0, nodes[322], "model_3d")
    collision = g.add(
        "DaWCollisionProxy",
        "ECHTE COLLISION · CPU / Godot 4",
        filename_prefix=prefix + "_collision",
    )
    g.connect(nodes[186], 0, collision, "mesh")
    show = g.add("PreviewAny", "COLLISION REPORT · Pfad / Dreiecke / Fallback")
    g.connect(collision, 1, show, "source")
    conv = g.add("MeshToFile3D", "Collision→GLB")
    g.connect(collision, 0, conv, "mesh")
    save = g.add(
        "Save3DAdvanced",
        "COLLISION-MESH · separat vom Sichtmesh",
        filename_prefix=prefix + "_collision",
        viewport_state="",
        width=512,
        height=512,
    )
    g.connect(conv, 0, save, "model_3d")
    # Keep ancestors of actual outputs only; removed providers must not load.
    keep = {nodes[322]["id"], collision["id"], show["id"], save["id"]}
    while True:
        more = {link[1] for link in g.w["links"] if link[3] in keep}
        if more <= keep:
            break
        keep |= more
    g.w["nodes"] = [n for n in g.w["nodes"] if n["id"] in keep]
    g.w["links"] = [
        link for link in g.w["links"] if link[1] in keep and link[3] in keep
    ]
    _rebuild_link_references(g.w)
    g.note(
        "START HIER · " + family + " / " + mode,
        "Ein statisches Asset pro Lauf. Shape erzeugt untexturierte Geometrie; PBR zusätzlich Base Color, Metallic/Roughness, Normal und AO. 1024³ statt ungeprüftem 1536³; AMD-sicherer 256³-UDF-Remesh, QEF AUS, midpoint, maximal 12.000 Sichtmesh-Dreiecke. Textur 1024px. Frei einstellbar, aber höhere Budgets erst separat testen.\n\nBild: vollständiges einzelnes Objekt, ruhiges Licht, keine Nachbarobjekte. Vorhandene Alpha-Maske: Background-Switch ausschalten; sonst BiRefNet. MultiView: eigener MultiView-Checkpoint, Front/links/hinten/rechts in 90°-Abständen, gleiche Skala, schwarzer Hintergrund, FOV 20° für kalibrierte Render. Unbenötigte Ansichten am Conditioning-Eingang TRENNEN. Das sind Anforderungen an deine Eingabebilder, keine automatisch geprüften Kamera-/Skalengarantien. Kein beliebiges Fotobatch, keine erfundene Mehransicht!\n\nCollision: separates CPU-Convex-Hull oder Box, max. 128 Vertices; zu komplexe Hüllen fallen ausdrücklich auf eine konservative Box zurück. Ergebnis enthält GLB plus echte Godot-4-.tscn mit CollisionShape3D und StaticBody3D/RigidBody3D. Das Sichtmesh selbst bleibt ohne Rig.\n\nEine konvexe Hülle verschließt Türen/Innenräume und Zwischenräume von Beinen. Nur für massive Props, nicht begehbare Gebäude oder artikulierte Figuren. Solche Assets brauchen manuelle Compound-Collider. Keine automatische Physiksimulation aus einem Foto. Achsen/Einheiten bleiben erhalten; Maßstab und Sichtmesh-Ausrichtung vor Nutzung prüfen. RigidBody-Masse ist manuell, nicht aus dem Bild geschätzt.\n\nRODENT: Nerdy Rodent; DaWasteh-Touch: zentrale GPU-Wahl, Timer, Parameterreferenz, klare Eingaben und getrennte Spielausgaben. Pixaroma-Vorlagen geprüft; neuraler Graph und AMD-Remesh stammen aus dem gepinnten offiziellen Core-Template/v0.9.7. MIT-Gewichte; DINOv3 unter Meta-Lizenz. GPU0 R9700, keine Gaming-GPU nötig.",
    )
    path = f"Game Development/{family}_INT8-{mode}.json"
    return path, g.finish(path, family, mode)


def build_all(schemas):
    result = {}
    for mode in ("Text-to-Music", "ABC-to-Music", "Audio-Cover"):
        p, w = yue(schemas, mode)
        result[p] = w
    for mode in (
        "Text-to-Image",
        "Image-to-Video",
        "First-Last-Frame",
        "Video-Continuation",
        "Text-to-Video",
    ):
        p, w = cosmos(schemas, mode)
        result[p] = w
    for family in ("TRELLIS2", "Pixal3D"):
        for mode in ("Shape-Collision", "PBR-Collision") + (
            ("MultiView-PBR-Collision",) if family == "Pixal3D" else ()
        ):
            p, w = asset(schemas, family, mode)
            result[p] = w
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schemas", type=Path, default=SCHEMAS)
    parser.add_argument("--destination", type=Path, default=ROOT / "workflows")
    args = parser.parse_args()
    schemas = json.loads(args.schemas.read_text(encoding="utf-8"))
    for path, workflow in build_all(schemas).items():
        dest = args.destination / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(workflow, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(dest)


if __name__ == "__main__":
    main()
