#!/usr/bin/env python3
"""Deterministic v0.9.6 upgrade for the local Hunyuan3D game-asset workflow.

v0.9.5 introduced one static Hunyuan3D -> DecimateMesh GLB.  v0.9.6 keeps the
same installed checkpoint but replaces that single mutable branch with four
independent, silhouette-aware LOD branches, then adds UV0 and crease normals.
"""
from __future__ import annotations

import copy
from typing import Any

try:
    from tools.upgrade_v095 import (
        HUNYUAN_PATH,
        UPGRADE_KEY as V095_UPGRADE_KEY,
        UPGRADE_VERSION as V095_UPGRADE_VERSION,
    )
except ModuleNotFoundError:  # Direct execution
    from upgrade_v095 import (
        HUNYUAN_PATH,
        UPGRADE_KEY as V095_UPGRADE_KEY,
        UPGRADE_VERSION as V095_UPGRADE_VERSION,
    )


UPGRADE_KEY = "dawasteh_v096_game_dev"
UPGRADE_VERSION = 1

V096_OBJECT_INFO: dict[str, Any] = {
    "UnwrapMesh": {
        "display_name": "Unwrap Mesh UVs",
        "description": (
            "Generates and packs a UV atlas after mesh simplification. UV seams duplicate "
            "vertices without changing the triangle count."
        ),
        "input": {
            "required": {
                "mesh": ["MESH", {}],
                "segmenter": [["pec", "adaptive"]],
                "resolution": ["INT", {"default": 1024, "min": 0, "max": 8192, "step": 256}],
                "padding": ["INT", {"default": 1, "min": 0, "max": 16}],
                "weld_distance": ["FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.0001}],
            }
        },
        "input_order": {"required": ["mesh", "segmenter", "resolution", "padding", "weld_distance"]},
        "output": ["MESH"],
        "output_name": ["mesh"],
    },
    "MeshSmoothNormals": {
        "display_name": "Smooth Mesh Normals",
        "description": (
            "Adds per-vertex normals and keeps edges above the crease angle hard. "
            "Triangle count stays unchanged; split normals may increase vertex count."
        ),
        "input": {
            "required": {
                "mesh": ["MESH", {}],
                "crease_angle": ["FLOAT", {"default": 180.0, "min": 0.0, "max": 180.0, "step": 1.0}],
            }
        },
        "input_order": {"required": ["mesh", "crease_angle"]},
        "output": ["MESH"],
        "output_name": ["mesh"],
    },
}


def _next_node_id(workflow: dict[str, Any]) -> int:
    ids = [node.get("id") for node in workflow.get("nodes", []) if isinstance(node.get("id"), int)]
    return max([int(workflow.get("last_node_id", 0)), *ids], default=0) + 1


def _next_link_id(workflow: dict[str, Any]) -> int:
    ids = [link[0] for link in workflow.get("links", []) if isinstance(link, list) and link]
    return max([int(workflow.get("last_link_id", 0)), *ids], default=0) + 1


def _mark_refresh(*nodes: dict[str, Any]) -> None:
    for node in nodes:
        node.setdefault("properties", {})["dawasteh_refresh_generated_note"] = True


def _connect(
    workflow: dict[str, Any],
    source: dict[str, Any],
    source_slot: int,
    target: dict[str, Any],
    target_slot: int,
    kind: str,
) -> int:
    link_id = _next_link_id(workflow)
    workflow.setdefault("links", []).append([link_id, source["id"], source_slot, target["id"], target_slot, kind])
    source["outputs"][source_slot].setdefault("links", [])
    if source["outputs"][source_slot]["links"] is None:
        source["outputs"][source_slot]["links"] = []
    source["outputs"][source_slot]["links"].append(link_id)
    target["inputs"][target_slot]["link"] = link_id
    workflow["last_link_id"] = link_id
    return link_id


def _voxel_to_mesh_lod(
    template: dict[str, Any], node_id: int, title: str, threshold: float
) -> dict[str, Any]:
    node = copy.deepcopy(template)
    node["id"] = node_id
    node["pos"] = [0, 0]
    node["order"] = 0
    node["title"] = title
    node["inputs"][0]["link"] = None
    node["outputs"][0]["links"] = []
    node["widgets_values"] = ["surface net", threshold]
    return node


def _decimate_lod(
    template: dict[str, Any], node_id: int, target: int, title: str
) -> dict[str, Any]:
    node = copy.deepcopy(template)
    node["id"] = node_id
    node["pos"] = [0, 0]
    node["order"] = 0
    node["title"] = title
    node["inputs"][0]["link"] = None
    node["outputs"][0]["links"] = []
    node["widgets_values"] = [target, "midpoint"]
    node.setdefault("properties", {}).pop("dawasteh_refresh_generated_note", None)
    return node


def _unwrap_mesh(node_id: int, title: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "UnwrapMesh",
        "pos": [0, 0],
        "size": [360, 190],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "mesh", "name": "mesh", "type": "MESH", "link": None},
            {"localized_name": "segmenter", "name": "segmenter", "type": "COMBO", "widget": {"name": "segmenter"}, "link": None},
            {"localized_name": "resolution", "name": "resolution", "type": "INT", "widget": {"name": "resolution"}, "link": None},
            {"localized_name": "padding", "name": "padding", "type": "INT", "widget": {"name": "padding"}, "link": None},
            {"localized_name": "weld_distance", "name": "weld_distance", "type": "FLOAT", "widget": {"name": "weld_distance"}, "link": None},
        ],
        "outputs": [{"localized_name": "mesh", "name": "mesh", "type": "MESH", "slot_index": 0, "links": []}],
        "title": title,
        "properties": {"Node name for S&R": "UnwrapMesh", "cnr_id": "comfy-core", "ver": "0.34.0"},
        "widgets_values": ["pec", 256, 2, 0.0],
    }


def _smooth_normals(node_id: int, title: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "MeshSmoothNormals",
        "pos": [0, 0],
        "size": [340, 110],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "mesh", "name": "mesh", "type": "MESH", "link": None},
            {"localized_name": "crease_angle", "name": "crease_angle", "type": "FLOAT", "widget": {"name": "crease_angle"}, "link": None},
        ],
        "outputs": [{"localized_name": "mesh", "name": "mesh", "type": "MESH", "slot_index": 0, "links": []}],
        "title": title,
        "properties": {"Node name for S&R": "MeshSmoothNormals", "cnr_id": "comfy-core", "ver": "0.34.0"},
        "widgets_values": [60.0],
    }


def _save_glb_lod(
    template: dict[str, Any], node_id: int, title: str, prefix: str
) -> dict[str, Any]:
    node = copy.deepcopy(template)
    node["id"] = node_id
    node["pos"] = [0, 0]
    node["order"] = 0
    node["title"] = title
    node["inputs"][0]["link"] = None
    node["widgets_values"] = [prefix, ""]
    node.setdefault("properties", {}).pop("Last Time Model File", None)
    node["properties"].pop("Last Time Model Folder", None)
    node["properties"].pop("dawasteh_refresh_generated_note", None)
    return node


def _upgrade_hunyuan(workflow: dict[str, Any]) -> None:
    by_id = {node.get("id"): node for node in workflow.get("nodes", [])}
    expected = {
        8: "VAEDecodeHunyuan3D",
        9: "VoxelToMesh",
        10: "SaveGLB",
        11: "Note",
        12: "MarkdownNote",
        25: "VRAM_Debug",
        34: "DecimateMesh",
    }
    for node_id, node_type in expected.items():
        if by_id.get(node_id, {}).get("type") != node_type:
            raise ValueError(f"{HUNYUAN_PATH}: expected node {node_id} to be {node_type}")

    v095_marker = workflow.get("extra", {}).get(V095_UPGRADE_KEY, {})
    if v095_marker.get("version") != V095_UPGRADE_VERSION:
        raise ValueError(f"{HUNYUAN_PATH}: v0.9.5 predecessor marker is missing")

    # Drop the old generated note for node 34 so IDs 35+ are available to the
    # executable LOD graph. Presentation rebuilding regenerates every needed note.
    workflow["nodes"] = [
        node for node in workflow.get("nodes", [])
        if not (
            node.get("properties", {}).get("dawasteh_generated_note")
            and node.get("properties", {}).get("dawasteh_note_for") == 34
        )
    ]
    workflow["last_node_id"] = max(
        (node["id"] for node in workflow["nodes"] if isinstance(node.get("id"), int)),
        default=0,
    )

    links = {link[0]: link for link in workflow.get("links", [])}
    cleanup_link = by_id[34]["inputs"][0].get("link")
    save_link = by_id[10]["inputs"][0].get("link")
    if not isinstance(cleanup_link, int) or links.get(cleanup_link, [None] * 5)[1:5] != [25, 0, 34, 0]:
        raise ValueError(f"{HUNYUAN_PATH}: v0.9.5 cleanup -> decimator link changed")
    if not isinstance(save_link, int) or links.get(save_link, [None] * 5)[1:5] != [34, 0, 10, 0]:
        raise ValueError(f"{HUNYUAN_PATH}: v0.9.5 decimator -> SaveGLB link changed")

    lods = [
        {"label": "LOD0 HERO", "threshold": 0.60, "target": 5000,
         "prefix": "GameDev/Hunyuan3D_LowPoly/lod0_hero_5000"},
        {"label": "LOD1 GAME", "threshold": 0.58, "target": 2500,
         "prefix": "GameDev/Hunyuan3D_LowPoly/lod1_game_2500"},
        {"label": "LOD2 DISTANT", "threshold": 0.55, "target": 1200,
         "prefix": "GameDev/Hunyuan3D_LowPoly/lod2_distant_1200"},
        {"label": "LOD3 ULTRA", "threshold": 0.52, "target": 600,
         "prefix": "GameDev/Hunyuan3D_LowPoly/lod3_ultra_0600"},
    ]

    by_id[9]["title"] = "LOD0 HERO · Voxel-Mesh · threshold 0.60"
    by_id[9]["widgets_values"] = ["surface net", 0.60]
    by_id[34]["title"] = "LOD0 HERO · maximal 5.000 Dreiecke · midpoint"
    by_id[34]["widgets_values"] = [5000, "midpoint"]
    by_id[10]["title"] = "GODOT · LOD0 HERO · UV-GLB speichern"
    by_id[10]["widgets_values"] = [lods[0]["prefix"], ""]

    next_id = _next_node_id(workflow)
    if next_id != 35:
        raise ValueError(f"{HUNYUAN_PATH}: expected first v0.9.6 node id 35, got {next_id}")
    max_order = max((int(node.get("order", 0)) for node in workflow.get("nodes", [])), default=0)

    unwrap0 = _unwrap_mesh(next_id, "LOD0 HERO · UV 256px · 2px Padding")
    normals0 = _smooth_normals(next_id + 1, "LOD0 HERO · 60° Crease-Normalen")
    for node in (unwrap0, normals0):
        max_order += 1
        node["order"] = max_order
        workflow["nodes"].append(node)

    links[save_link][3] = unwrap0["id"]
    links[save_link][4] = 0
    unwrap0["inputs"][0]["link"] = save_link
    by_id[10]["inputs"][0]["link"] = None
    _connect(workflow, unwrap0, 0, normals0, 0, "MESH")
    _connect(workflow, normals0, 0, by_id[10], 0, "MESH")
    next_id += 2

    # Distinct thresholds produce distinct VoxelToMesh cache keys and separate mesh
    # objects. Lower thresholds thicken fragile silhouettes before each midpoint pass.
    for spec in lods[1:]:
        voxel_mesh = _voxel_to_mesh_lod(
            by_id[9], next_id,
            f"{spec['label']} · Voxel-Mesh · threshold {spec['threshold']:.2f}",
            spec["threshold"],
        )
        decimate = _decimate_lod(
            by_id[34], next_id + 1, spec["target"],
            f"{spec['label']} · maximal {spec['target']:,} Dreiecke · midpoint".replace(",", "."),
        )
        unwrap = _unwrap_mesh(next_id + 2, f"{spec['label']} · UV 256px · 2px Padding")
        normals = _smooth_normals(next_id + 3, f"{spec['label']} · 60° Crease-Normalen")
        save = _save_glb_lod(
            by_id[10], next_id + 4,
            f"GODOT · {spec['label']} · UV-GLB speichern",
            spec["prefix"],
        )
        for node in (voxel_mesh, decimate, unwrap, normals, save):
            max_order += 1
            node["order"] = max_order
            workflow["nodes"].append(node)

        _connect(workflow, by_id[8], 0, voxel_mesh, 0, "VOXEL")
        _connect(workflow, voxel_mesh, 0, decimate, 0, "MESH")
        _connect(workflow, decimate, 0, unwrap, 0, "MESH")
        _connect(workflow, unwrap, 0, normals, 0, "MESH")
        _connect(workflow, normals, 0, save, 0, "MESH")
        next_id += 5

    workflow["last_node_id"] = next_id - 1
    by_id[11]["title"] = "START HIER · Bild → echte Low-Poly-LOD-GLBs für Godot"
    by_id[11]["widgets_values"] = [
        "=== HUNYUAN3D 2.1 -> 2000er-LOW-POLY-LODs -> GODOT ===\n\n"
        "1) Ein einzelnes, zentriertes Objektbild mit sauberem oder transparentem Hintergrund wählen.\n"
        "2) Hunyuan3D läuft einmal mit shift 1 und 40 Schritten. Danach entstehen vier UNABHÄNGIGE "
        "Voxel-Meshes statt vier mutierender Decimate-Abzweige.\n"
        "3) LOD0/1 sind die eigentlichen Spielmodelle. LOD2 ist für Entfernung; LOD3 ist die aggressive "
        "Silhouette. Niedrigere Voxel-Schwellen verdicken dünne Teile kontrolliert, bevor midpoint reduziert.\n"
        "4) Jedes GLB erhält ein echtes 256px-UV-Layout und 60-Grad-Crease-Normalen. Gespeichert werden "
        "lod0_hero_5000, lod1_game_2500, lod2_distant_1200 und lod3_ultra_0600.\n\n"
        "50 Dreiecke sind für ein beliebiges erkennbares 3D-Objekt kein brauchbares Ziel. Dafür Billboard, "
        "Impostor oder bewusst prozedurale Primitive verwenden. Godot erzeugt aus einem GLB außerdem "
        "automatische bildschirmgrößenabhängige Mesh-LODs.\n\n"
        "WICHTIG: Die GLBs sind STATISCH, UV-ENTFALTET, ABER UNTEXTURIERT und UNGERIGGT. Vor Produktion "
        "in Blender Maßstab/Achsen, Silhouette, Material, Rig/Animation und Collision prüfen."
    ]
    by_id[12]["widgets_values"] = [
        "**Modellentscheidung**\n\n"
        "- Vorhanden: `models/checkpoints/Hunyuan3D/hunyuan_3d_v2.1.safetensors`\n"
        "- Verwendet: ComfyUI 0.34 Core `VoxelToMesh`, `DecimateMesh`, `UnwrapMesh`, "
        "`MeshSmoothNormals` und `SaveGLB`\n\n"
        "Kein neues Modell wurde benötigt. MeshAnything V2 wurde bewusst nicht installiert: maximal 1.600 "
        "Faces, keine offiziell unterstützte ComfyUI-/Windows-ROCm-Laufzeit und S-Lab-Lizenz nur für "
        "nichtkommerzielle Nutzung. Der Core-`qem`-Modus nutzt außerdem einen auf dieser Windows-ROCm-"
        "Installation fehlschlagenden `torch.linalg.solve`-Pfad; `midpoint` ist hier der live geprüfte Pfad."
    ]
    _mark_refresh(by_id[9], by_id[10], by_id[34])
    gpu = workflow.setdefault("extra", {}).setdefault("dawasteh_dual_gpu", {})
    gpu.update({
        "family": "Hunyuan3D 2.1 Low-Poly LOD Set for Godot",
        "source": f"workflows/{HUNYUAN_PATH}",
        "curated_split_default": False,
        "defaults": {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"},
    })
    workflow["extra"][UPGRADE_KEY] = {
        "version": UPGRADE_VERSION,
        "release": "v0.9.6",
        "source_requirement": "Hunyuan3D + robust low-poly LOD pipeline",
        "model_downloads": 0,
        "installed_checkpoint": "Hunyuan3D/hunyuan_3d_v2.1.safetensors",
        "decimator": "ComfyUI 0.34 core DecimateMesh midpoint",
        "target_face_counts": [spec["target"] for spec in lods],
        "voxel_thresholds": [spec["threshold"] for spec in lods],
        "uv_resolution": 256,
        "crease_angle_degrees": 60,
        "outputs": [spec["prefix"] for spec in lods],
        "model_decision": "no additional model; MeshAnything V2 unsupported here and non-commercial",
        "truthful_output": "four static, UV-unwrapped, untextured, unrigged GLB LOD intermediates",
    }


def upgrade_workflow(workflow: dict[str, Any], path_key: str) -> tuple[dict[str, Any], bool]:
    """Upgrade the v0.9.5 Hunyuan game workflow to v0.9.6."""
    upgraded = copy.deepcopy(workflow)
    if path_key != HUNYUAN_PATH:
        return upgraded, False
    marker = upgraded.get("extra", {}).get(UPGRADE_KEY, {})
    if marker.get("version") == UPGRADE_VERSION:
        return upgraded, False
    _upgrade_hunyuan(upgraded)
    return upgraded, True
