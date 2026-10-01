#!/usr/bin/env python3
"""Rebuild the v1.2.9 Mira-Scene workflows (flat RODENT graphs); no runtime/model writes.

Mira-Scene (VAST-AI-Research) reconstructs an editable 3D scene from one photo. The ComfyUI port keeps Mira's stages and
uses ComfyUI's native models where Mira calls external projects:

- segmentation: SAM 3.1 with a text list of objects plus "floor" (Mira: SAM3 + a VLM) -> DaWMiraMasks,
- depth: MoGe-2 (one of Mira's depth backends),
- canonical coordinate maps + object voxels: Mira-CCM through the pinned Mira-Scene checkout (DaWMiraCCM),
- meshes: TRELLIS.2 on Mira's voxel structure (Mira's trellis2 backend), one object after the other,
- scene: DaWMiraAssembleScene with Mira's transform solver, floor fit and support placement.

Two workflows: the full scene with textured meshes and a fast layout preview with Mira's voxel shapes.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

try:
    from tools.build_workflows_v118 import Graph
    from tools import migrate_workflows_v092 as migration
    from tools.generate_dual_gpu_workflows import install_run_timer
    from tools.refine_workflows import refine_workflow
    from tools.rodent_layout import apply_rodent_layout
    from tools.workflow_names_v131 import original_name
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout
    from workflow_names_v131 import original_name

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v129"
MARKER = "dawasteh_mira_scene_v129"
RELEASE = "v1.2.9"
BS = "\\"
PATHS = {
    "scene": "Image to 3D-Mesh/Mira_Scene+TRELLIS2_INT8-Image-to-3D-Scene.json",
    "layout": "Image to 3D-Mesh/Mira_Scene-Image-to-3D-Layout-Preview.json",
}
SAM3 = "SAM3" + BS + "sam3.1_multiplex_fp16.safetensors"
MOGE = "moge_2_vitl_normal_fp16.safetensors"
PIPELINE = "Mira-Scene" + BS + "pipeline"
TRELLIS = "trellis_2_int8_convrot.safetensors"
DINO = "dino_v3_vit_l.safetensors"
SHAPE_VAE = "trellis_2_shape_vae_bf16.safetensors"
TEXTURE_VAE = "trellis_2_texture_vae_bf16.safetensors"
INPUT = "modern_living_room.png"
OBJECTS = "sofa, coffee table, television, potted plant:4, lamp:3"
# Measured on the R9700 (docs/MIRA_SCENE_V129.md); the tests pin these values.
SETTINGS = {
    "sam3": {"threshold": 0.5, "refine_iterations": 2},
    "sam3_floor": {"threshold": 0.4, "refine_iterations": 2},
    "masks": {"min_area": 0.002, "max_objects": 12},
    "moge": {"resolution_level": 9, "fov_x_degrees": 0.0, "batch_size": 4, "force_projection": True, "apply_mask": True,
             "refine_steps": 3},
    "ccm": {"seed": 42, "steps": 30, "guidance": 3.0},
    "trellis": {"detail": "1024", "seed": 42, "shape_steps": 20, "detail_steps": 12, "texture_steps": 12, "cfg": 7.5,
                "remesh_resolution": 384, "max_faces": 60000, "texture_size": 1024},
    "cfg_override": {"cfg": 1.0, "start_percent": 0.769, "end_percent": 1.0},
    "rescale_cfg": 0.5,
    "assemble": {"upright": "auto", "snap_to_support": True, "add_floor": True, "seed": 42},
}


def _pixaroma_load(g: Graph, title: str, image: str) -> dict:
    load = g.add("PixaromaLoadImage", title, image=image)
    load["properties"]["loadImagePixState"] = json.dumps({"version": 1, "mode": "off", "snap": 0})
    load["size"] = [480, 620]
    return load


def _front(g: Graph) -> dict:
    """Photo -> 518 px scene, SAM3 objects + floor, clean masks, MoGe-2, Mira CCM. Returns the relevant nodes."""
    load = _pixaroma_load(g, "1 · FOTO · Raum oder Szene (genutzt wird das mittige Quadrat)", INPUT)
    prep = g.add("DaWMiraPrepareImage", "SZENE · mittiges Quadrat → 518 px (Mira) + Hochauflösung für die Objekte",
                 max_hires=2048)
    g.connect(load, 0, prep, "image")
    sam = g.add("CheckpointLoaderSimple", "SAM 3.1 · Objekte per Text finden", ckpt_name=SAM3)
    objects = g.prompt("2 · OBJEKTE · englisch, kommagetrennt · plant:3 = bis zu 3 Stück", OBJECTS)
    encode = g.add("CLIPTextEncode", "SAM3 · Objektliste")
    g.connect(sam, 1, encode, "clip")
    g.connect(objects, 0, encode, "text")
    floor_text = g.add("CLIPTextEncode", "SAM3 · Boden", text="floor")
    g.connect(sam, 1, floor_text, "clip")
    detect = g.add("SAM3_Detect", "OBJEKTE FINDEN · je Begriff die sichersten Treffer", individual_masks=True, **SETTINGS["sam3"])
    detect_floor = g.add("SAM3_Detect", "BODEN FINDEN · Schwerkraft + Bodenebene", individual_masks=False, **SETTINGS["sam3_floor"])
    for node, cond in ((detect, encode), (detect_floor, floor_text)):
        g.connect(sam, 0, node, "model")
        g.connect(prep, 0, node, "image")
        g.connect(cond, 0, node, "conditioning")
    masks = g.add("DaWMiraMasks", "MASKEN · Dubletten, Überlappungen, Mini-Masken bereinigen", **SETTINGS["masks"])
    g.connect(prep, 0, masks, "scene")
    g.connect(detect, 0, masks, "masks")
    g.connect(detect_floor, 0, masks, "floor")
    preview = g.add("PreviewImage", "KONTROLLE · erkannte Objekte (Farben) + Boden (schraffiert)")
    g.connect(masks, 3, preview, "images")
    moge_model = g.add("LoadMoGeModel", "MOGE-2 · metrische Tiefe", model_name=MOGE)
    moge = g.add("MoGeInference", "TIEFE · Kamerapunkte der 518-px-Szene", **SETTINGS["moge"])
    g.connect(moge_model, 0, moge, "moge_model")
    g.connect(prep, 0, moge, "image")
    mira = g.add("DaWMiraLoadCCM", "MIRA-SCENE · CCM-Modell (kanonische Koordinaten + Voxel)", pipeline=PIPELINE, dtype="bf16")
    ccm = g.add("DaWMiraCCM", "MIRA · Koordinaten + Voxel je Objekt (30 Schritte, Guidance 3)", **SETTINGS["ccm"])
    for src, slot, field in [(mira, 0, "mira_model"), (prep, 0, "scene"), (masks, 0, "masks"), (prep, 1, "hires")]:
        g.connect(src, slot, ccm, field)
    ccm_preview = g.add("PreviewImage", "KONTROLLE · kanonische Koordinaten (glatter Farbverlauf = sichere Lage)")
    g.connect(ccm, 3, ccm_preview, "images")
    return {"prep": prep, "masks": masks, "moge": moge, "ccm": ccm}


def _assemble(g: Graph, front: dict, meshes: dict | None, prefix: str, title: str) -> dict:
    assemble = g.add("DaWMiraAssembleScene", title, **SETTINGS["assemble"])
    g.connect(front["ccm"], 0, assemble, "mira_ccm")
    g.connect(front["moge"], 0, assemble, "moge_geometry")
    g.connect(front["masks"], 1, assemble, "floor")
    if meshes is not None:
        g.connect(meshes, 0, assemble, "meshes")
    save = g.add("Save3DAdvanced", "3 · SPEICHERN · Szene als GLB (Y oben, Boden bei 0, Fotokamera)",
                 filename_prefix=prefix, viewport_state="", width=1024, height=1024)
    save["size"] = [720, 760]
    g.connect(assemble, 0, save, "model_3d")
    report = g.add("PreviewAny", "BERICHT · Größe, aufrecht, Auflage je Objekt (Meter)")
    g.connect(assemble, 1, report, "source")
    return assemble


def finish(g: Graph, key: str) -> dict:
    path = PATHS[key]
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v129:" + original_name(path)))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {
        "version": 1,
        "kind": key,
        "code_manifest": "tools/workflow_templates/v129/mira-code.json",
        "model_manifest": "tools/workflow_templates/v129/mira-models.json",
        "validation_report": "performance/rdna4/mira-scene-v129-validation.json",
    }
    refine_workflow(g.w, g.schemas)
    before = copy.deepcopy(migration.OBJECT_INFO)
    try:
        migration.OBJECT_INFO.update(g.schemas)
        result = migration.migrate_workflow(g.w, path)
    finally:
        migration.OBJECT_INFO.clear()
        migration.OBJECT_INFO.update(before)
    for node in result["nodes"]:
        if node["type"] == "MarkdownNote":
            text = node.get("widgets_values", [""])[0]
            lines = sum(max(1, (len(line) + 79) // 80) for line in text.splitlines())
            node["size"] = [680, max(620, 160 + lines * 22)]
    apply_rodent_layout(result, path)
    return result


def _model_lines(names: set[str]) -> str:
    lines, pipeline = [], []
    for entry in json.loads((SOURCES / "mira-models.json").read_text(encoding="utf-8")):
        url = f"https://huggingface.co/{entry['repo_id']}/resolve/{entry['revision']}/{entry['source_path']}"
        if entry["repo_id"] == "Yang-Tian/Mira-Scene":
            pipeline.append(entry)
            continue
        if Path(entry["path"]).name in names:
            lines.append(f"- [{Path(entry['source_path']).name}]({url}) → `ComfyUI/models/{entry['path']}` "
                         f"({entry['size'] / 2**30:.2f} GiB)")
    total = sum(e["size"] for e in pipeline) / 2**30
    lines.insert(0, f"- Mira-Scene CCM-Pipeline ([Yang-Tian/Mira-Scene](https://huggingface.co/Yang-Tian/Mira-Scene/tree/"
                    f"{pipeline[0]['revision']}/pipeline), Ordner `pipeline/`, {len(pipeline)} Dateien, {total:.2f} GiB) → "
                    "`ComfyUI/models/diffusers/Mira-Scene/pipeline/` (mit `model_index.json`, `transformer/`, `vae/`, "
                    "`image_encoder/`, `scheduler/`, `feature_extractor/`)")
    for entry in json.loads((SOURCES / "mira-inputs.json").read_text(encoding="utf-8")):
        lines.append(f"- [{entry['file']}]({entry['url']}) → `ComfyUI/input/{entry['file']}` (Beispiel)")
    code = json.loads((SOURCES / "mira-code.json").read_text(encoding="utf-8"))
    return ("# Benötigte Dateien\n\n" + "\n\n".join(lines) +
            f"\n\n**Mira-Scene-Code:** der Bundle-Updater legt `{code['repository']}` auf Commit `{code['commit'][:12]}` unter "
            "`L:\\ComfyUI\\third_party\\Mira-Scene` ab (git). Das Repository hat noch **keine Lizenzdatei** (Issue #4): nur "
            "privat nutzen; im Bundle ist davon nichts kopiert. Knoten: ComfyUI-DaWasteh-MiraScene (Bundle-Updater).\n")


def build_scene(schemas: dict) -> dict:
    g = Graph(schemas)
    front = _front(g)
    unet = g.add("UNETLoader", "TRELLIS.2 · INT8 ConvRot · R9700", unet_name=TRELLIS)
    override = g.add("CFGOverride", "TRELLIS FORM · CFG ab 77 % aus (wie TRELLIS2-PBR)", **SETTINGS["cfg_override"])
    g.connect(unet, 0, override, "model")
    rescale = g.add("RescaleCFG", "TRELLIS FORM · RescaleCFG 0,5", multiplier=SETTINGS["rescale_cfg"])
    g.connect(override, 0, rescale, "model")
    dino = g.add("CLIPVisionLoader", "DINOv3 · Bildmerkmale für TRELLIS.2", clip_name=DINO)
    shape_vae = g.add("VAELoader", "TRELLIS.2 · Form-VAE", vae_name=SHAPE_VAE)
    texture_vae = g.add("VAELoader", "TRELLIS.2 · Textur-VAE", vae_name=TEXTURE_VAE)
    trellis = g.add("DaWMiraTrellisObjects", "TRELLIS.2 · Mesh + PBR-Textur je Objekt, nacheinander (Miras Voxel statt Stufe 1)",
                    **SETTINGS["trellis"])
    for src, slot, field in [(rescale, 0, "shape_model"), (unet, 0, "texture_model"), (dino, 0, "clip_vision"),
                             (shape_vae, 0, "shape_vae"), (texture_vae, 0, "texture_vae"), (front["ccm"], 1, "voxel"),
                             (front["ccm"], 2, "objects")]:
        g.connect(src, slot, trellis, field)
    crops = g.add("PreviewImage", "KONTROLLE · Objekt-Ausschnitte (Eingabe für TRELLIS.2)")
    g.connect(front["ccm"], 2, crops, "images")
    _assemble(g, front, trellis, "Mira_Scene/scene", "SZENE · Objekte platzieren (Mira-Solver, Schwerkraft, Bodenkontakt)")
    objects = g.add("SaveGLB", "SPEICHERN · jedes Objekt einzeln als GLB (kanonisch, 1 Einheit Würfel)",
                    filename_prefix="Mira_Scene/objects/object")
    g.connect(trellis, 0, objects, "mesh")
    g.note(f"START HIER · Mira-Scene · Foto → 3D-Szene · {RELEASE}", SCENE_NOTE)
    g.note("DOWNLOADS · Modelle / Code / Zielordner", _model_lines({Path(p).name for p in (SAM3, MOGE, TRELLIS, DINO, SHAPE_VAE, TEXTURE_VAE)}))
    return finish(g, "scene")


def build_layout(schemas: dict) -> dict:
    g = Graph(schemas)
    front = _front(g)
    _assemble(g, front, None, "Mira_Scene/layout", "LAYOUT · Miras Voxelformen platzieren (ohne TRELLIS, schnell)")
    g.note(f"START HIER · Mira-Scene · Layout-Vorschau · {RELEASE}", LAYOUT_NOTE)
    g.note("DOWNLOADS · Modelle / Code / Zielordner", _model_lines({Path(p).name for p in (SAM3, MOGE)}))
    return finish(g, "layout")


COMMON = """**So arbeitet der Graph (wie Mira-Scene, auf ComfyUIs eigenen Modellen):** SAM 3.1 findet die Objekte aus der
Liste und den Boden, der Masken-Knoten macht daraus überlappungsfreie Instanzen. MoGe-2 schätzt für jeden Pixel einen
Punkt im Raum (metrisch). Miras CCM-Modell sagt für jedes Objekt voraus, **welcher Punkt des Objekts** in jedem Pixel zu
sehen ist (kanonische Koordinaten) und wie das ganze Objekt als 64³-Voxel aussieht, auch verdeckte Teile. Aus Koordinaten
und Tiefe folgt je Objekt Größe, Drehung und Position (RANSAC); die Bodenebene gibt die Schwerkraft vor, aufrechte Objekte
werden senkrecht gestellt und auf Boden oder Unterlage gesetzt.

**Objektliste:** englische Begriffe, kommagetrennt; `plant:3` erlaubt bis zu 3 Pflanzen (ohne Zahl: die sicherste eine).
Nur was in der Liste steht, wird rekonstruiert. KONTROLLE zeigt die gefundenen Objekte farbig: fehlt etwas, Begriff
ändern (z. B. `couch` statt `sofa`) oder am Objekt-Knoten `threshold` senken. Höchstens 12 Objekte (`max_objects`).
**Bild:** Innenräume und Außenszenen mit sichtbarem Boden; Mira nutzt das **mittige Quadrat** des Fotos.
Ohne Boden (`floor` nicht gefunden) gilt die Kamera-Hochachse, Objekte stehen dann auf dem tiefsten Punkt.
"""

SCENE_NOTE = """# Mira-Scene · aus einem Foto eine bearbeitbare 3D-Szene

Jedes erkannte Objekt wird ein eigenes, texturiertes 3D-Modell (TRELLIS.2) und an seiner Stelle im Raum platziert.

1. **FOTO** (Knoten 1) wählen.
2. **OBJEKTE** (Knoten 2): was rekonstruiert werden soll, z. B. `sofa, coffee table, lamp:2, potted plant:3`.
3. **Queue**. Ergebnis: **output/Mira_Scene/scene_*.glb** (alle Objekte + Boden + Fotokamera, Y oben, Boden bei y = 0,
   Meter) und **output/Mira_Scene/objects/object_*.glb** (jedes Objekt einzeln). BERICHT listet Größe und Auflage je Objekt.

Tipp: erst den Workflow **Mira_Scene-Image-to-3D-Layout-Preview** laufen lassen (ca. 1–2 min): Er zeigt, ob Objekte und Boden
richtig erkannt und platziert werden, bevor TRELLIS.2 minutenlang rechnet.

""" + COMMON + """
**TRELLIS.2** erzeugt jedes Objekt auf Miras Voxelform (statt TRELLIS' eigener erster Stufe), nacheinander statt im
Batch: Ein Batch polstert alle Objekte auf das größte auf (Wohnzimmer mit Sofa: 92 s statt 16 s pro Schritt).
`detail` 1024 = Miras Kaskade, 512 = schneller und gröber. Verdeckte Teile ergänzt TRELLIS nach Bild und Voxelform;
Miras eigene Gemini-Nachzeichnung der Objekte (Cloud) ist nicht enthalten.
Bedienung und Messwerte: `docs/MIRA_SCENE_V129.md`.
"""

LAYOUT_NOTE = """# Mira-Scene · Layout-Vorschau (schnell, ohne TRELLIS.2)

Gleiche Erkennung und Platzierung wie der Szenen-Workflow, aber jedes Objekt als farbige Voxelform aus Miras
CCM-Modell. Dauert ca. 1–2 Minuten und zeigt, ob Objekte, Größen und Boden stimmen.

1. **FOTO** und **OBJEKTE** wie im Szenen-Workflow eintragen, **Queue**.
2. Ergebnis: **output/Mira_Scene/layout_*.glb**; BERICHT mit Größe, Aufrecht-Winkel und Auflage je Objekt.
3. Passt alles, dieselbe Objektliste in **Mira_Scene+TRELLIS2_INT8-Image-to-3D-Scene** verwenden.

""" + COMMON + """
Bedienung und Messwerte: `docs/MIRA_SCENE_V129.md`.
"""

BUILDERS = {"scene": build_scene, "layout": build_layout}


def build_all() -> dict[str, dict]:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    return {PATHS[key]: builder(schemas) for key, builder in BUILDERS.items()}


def main() -> None:
    for path, workflow in build_all().items():
        target = ROOT / "workflows" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
