#!/usr/bin/env python3
"""Deterministic Pixal3D game-asset additions for v0.9.7.

The pinned official ComfyUI Pixal3D/TRELLIS.2 template is narrowed to the
Pixal3D branch and specialized for two Godot use cases.  The shipped graphs use
only ComfyUI-Core nodes, the permissively distributed Pixal3D INT8 ConvRot
weights, an AMD-tested 256³ UDF remesh with QEF disabled, and the midpoint
decimator. They avoid the locally failing SDF/QEF and QEM-placement paths and
produce one textured game mesh; Godot can build screen-size LODs at import time.
"""
from __future__ import annotations

import copy
from typing import Any


UPGRADE_KEY = "dawasteh_v097_game_dev"
UPGRADE_VERSION = 1
SOURCE_TEMPLATE = "3d_pixal3d_trellis2_image_to_model.json"
SOURCE_TEMPLATE_SHA256 = "594295ae20490b4ed990655686f2d0c15ba06732df5553bc22bda98966c40a97"

ENVIRONMENT_PATH = "Game Development/Pixal3D_INT8-Buildings-and-Environment-PBR-for-Godot.json"
CREATURE_PATH = "Game Development/Pixal3D_INT8-Humanoids-and-Animals-PBR-for-Godot.json"
GAME_PATHS = {ENVIRONMENT_PATH, CREATURE_PATH}

MODEL_FILES = [
    {
        "repo": "Comfy-Org/Pixal3D",
        "path": "diffusion_models/pixal3d_int8_convrot.safetensors",
        "size": 5_584_555_824,
        "sha256": "4621eac3b715484f79303c7152af641fe0b2b14f4d0e3d394fd6922d00f955ec",
    },
    {
        "repo": "Comfy-Org/Pixal3D",
        "path": "clip_vision/dino_v3_L_naf_fp32.safetensors",
        "size": 1_215_214_176,
        "sha256": "4ad2ec4e0879a5b5b04cd97325cc37da954a7b6edca5170b86510f17f2b2290f",
    },
    {
        "repo": "Comfy-Org/Pixal3D",
        "path": "vae/trellis_2_shape_vae_bf16.safetensors",
        "size": 1_095_844_024,
        "sha256": "de0cb4949a76c59ee5c091a995a69bcc8c51d5aeda939f0c641a50d2a72341f4",
    },
    {
        "repo": "Comfy-Org/Pixal3D",
        "path": "vae/trellis_2_texture_vae_bf16.safetensors",
        "size": 948_461_364,
        "sha256": "714e5ebf094a610e12a8e3b5175c18a62f37f6ea4218acb6073644456b73ab0e",
    },
    {
        "repo": "Comfy-Org/MoGe",
        "path": "geometry_estimation/moge_2_vitl_normal_fp16.safetensors",
        "size": 661_859_924,
        "sha256": "cb1a692d03235671e959e81360d7b4d9f44aefadb1f852d6ca6aa17799d5e31f",
    },
    {
        "repo": "Comfy-Org/BiRefNet",
        "path": "background_removal/birefnet.safetensors",
        "size": 444_473_596,
        "sha256": "9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154",
    },
]


# Narrow current-Core schemas used to generate useful parameter notes without
# replacing the historical collection-wide object-info snapshot.
V097_OBJECT_INFO: dict[str, Any] = {
    "LoadMoGeModel": {
        "display_name": "Load MoGe Model",
        "description": "Loads the local MoGe camera/geometry estimator used to recover the source-image field of view.",
        "input": {"required": {"model_name": [["moge_2_vitl_normal_fp16.safetensors"]]}},
        "input_order": {"required": ["model_name"]},
        "output": ["MOGE_MODEL"],
        "output_name": ["moge_model"],
    },
    "MoGeInference": {
        "display_name": "MoGe Camera Estimation",
        "description": "Estimates image geometry and camera projection so Pixal3D can align visible pixels with the generated surface.",
        "input": {"required": {
            "moge_model": ["MOGE_MODEL", {"forceInput": True}],
            "image": ["IMAGE", {"forceInput": True}],
            "resolution_level": ["INT", {"default": 9, "min": 0, "max": 9, "tooltip": "0 is fastest; 9 keeps the most camera-estimation detail."}],
            "fov_x_degrees": ["FLOAT", {"default": 0.0, "tooltip": "0 lets MoGe recover the horizontal field of view."}],
            "batch_size": ["INT", {"default": 1, "min": 1, "max": 64}],
            "force_projection": ["BOOLEAN", {"default": True}],
            "apply_mask": ["BOOLEAN", {"default": True}],
        }},
        "input_order": {"required": ["moge_model", "image", "resolution_level", "fov_x_degrees", "batch_size", "force_projection", "apply_mask"]},
        "output": ["MOGE_GEOMETRY"],
        "output_name": ["geometry"],
    },
    "MoGeGeometryToFOV": {
        "display_name": "MoGe Geometry to FOV",
        "description": "Extracts the horizontal camera field of view expected by Pixal3D conditioning.",
        "input": {"required": {
            "moge_geometry": ["MOGE_GEOMETRY", {"forceInput": True}],
            "axis": [["vertical", "horizontal", "diagonal"]],
            "unit": [["degrees", "radians"]],
        }},
        "input_order": {"required": ["moge_geometry", "axis", "unit"]},
        "output": ["FLOAT", "FLOAT"],
        "output_name": ["fov", "focal_length"],
    },
    "LoadBackgroundRemovalModel": {
        "display_name": "Load BiRefNet",
        "description": "Loads the permissive BiRefNet foreground extractor used for a clean single-asset silhouette.",
        "input": {"required": {"bg_removal_name": [["birefnet.safetensors"]]}},
        "input_order": {"required": ["bg_removal_name"]},
        "output": ["BACKGROUND_REMOVAL"],
        "output_name": ["background_removal"],
    },
    "RemoveBackground": {
        "display_name": "Remove Background",
        "description": "Separates the asset from its background. Disable the surrounding switch when the source already has a correct alpha mask.",
        "input": {"required": {
            "bg_removal_model": ["BACKGROUND_REMOVAL", {"forceInput": True}],
            "image": ["IMAGE", {"forceInput": True}],
        }},
        "input_order": {"required": ["bg_removal_model", "image"]},
        "output": ["MASK"],
        "output_name": ["mask"],
    },
    "ImageCropToMask": {
        "display_name": "Crop Asset to Mask",
        "description": "Centers the complete silhouette on a square canvas with Pixal3D's required margin.",
        "input": {"required": {
            "images": ["IMAGE", {"forceInput": True}],
            "masks": ["MASK", {"forceInput": True}],
            "width": ["INT", {"default": 1024}],
            "height": ["INT", {"default": 1024}],
            "pad_factor": ["FLOAT", {"default": 1.1, "min": 1.0, "max": 2.0}],
            "grow_mask": ["INT", {"default": 0, "min": -32, "max": 32}],
            "background": ["COLOR", {"default": "#000000"}],
        }},
        "input_order": {"required": ["images", "masks", "width", "height", "pad_factor", "grow_mask", "background"]},
        "output": ["IMAGE"],
        "output_name": ["image"],
    },
    "Pixal3DConditioning": {
        "display_name": "Pixal3D Pixel-Aligned Conditioning",
        "description": "Encodes DINOv3/NAF image features and camera projection for view-aligned Pixal3D shape and PBR generation.",
        "input": {"required": {
            "clip_vision_model": ["CLIP_VISION", {"forceInput": True}],
            "image": ["IMAGE", {"forceInput": True}],
            "camera_angle_x": ["FLOAT", {"default": 49.13, "tooltip": "Horizontal source-camera FOV in degrees; normally supplied by MoGe."}],
        }},
        "input_order": {"required": ["clip_vision_model", "image", "camera_angle_x"]},
        "output": ["CONDITIONING", "CONDITIONING"],
        "output_name": ["positive", "negative"],
    },
    "VaeDecodeStructureTrellis2": {
        "display_name": "Decode Sparse Structure",
        "description": "Decodes the first Pixal3D latent into a coarse occupancy volume for shape generation.",
        "input": {"required": {
            "samples": ["LATENT", {"forceInput": True}],
            "vae": ["VAE", {"forceInput": True}],
            "resolution": [["32", "64"]],
        }},
        "input_order": {"required": ["samples", "vae", "resolution"]},
        "output": ["VOXEL"],
        "output_name": ["voxel"],
    },
    "Trellis2ShapeStage": {
        "display_name": "Pixal3D Shape Stage",
        "description": "Builds the sparse shape latent from the coarse occupancy and pixel-aligned conditioning.",
        "input": {"required": {
            "positive": ["CONDITIONING", {"forceInput": True}],
            "negative": ["CONDITIONING", {"forceInput": True}],
            "voxel": ["VOXEL", {"forceInput": True}],
        }},
        "input_order": {"required": ["positive", "negative", "voxel"]},
        "output": ["CONDITIONING", "CONDITIONING", "LATENT"],
        "output_name": ["positive", "negative", "latent"],
    },
    "Trellis2UpsampleStage": {
        "display_name": "Pixal3D Shape Upsample",
        "description": "Raises sparse shape resolution. The AMD game profiles use 1024 instead of 1536 to control VRAM and processing time.",
        "input": {"required": {
            "positive": ["CONDITIONING", {"forceInput": True}],
            "negative": ["CONDITIONING", {"forceInput": True}],
            "shape_latent": ["LATENT", {"forceInput": True}],
            "vae": ["VAE", {"forceInput": True}],
            "target_resolution": ["INT", {"default": 1024, "min": 1024, "max": 2048, "step": 128}],
        }},
        "input_order": {"required": ["positive", "negative", "shape_latent", "vae", "target_resolution"]},
        "output": ["CONDITIONING", "CONDITIONING", "LATENT"],
        "output_name": ["positive", "negative", "latent"],
    },
    "VaeDecodeShapeTrellis": {
        "display_name": "Decode Pixal3D Mesh",
        "description": "Decodes the refined sparse shape latent into the high-detail reference mesh used for simplification and map baking.",
        "input": {"required": {
            "samples": ["LATENT", {"forceInput": True}],
            "vae": ["VAE", {"forceInput": True}],
        }},
        "input_order": {"required": ["samples", "vae"]},
        "output": ["MESH", "SHAPE_SUBDIVIDES"],
        "output_name": ["mesh", "shape_subdivides"],
    },
    "Trellis2TextureStage": {
        "display_name": "Pixal3D PBR Texture Stage",
        "description": "Creates the sparse PBR texture latent aligned to the generated shape.",
        "input": {"required": {
            "positive": ["CONDITIONING", {"forceInput": True}],
            "negative": ["CONDITIONING", {"forceInput": True}],
            "shape_latent": ["LATENT", {"forceInput": True}],
        }},
        "input_order": {"required": ["positive", "negative", "shape_latent"]},
        "output": ["CONDITIONING", "CONDITIONING", "LATENT"],
        "output_name": ["positive", "negative", "latent"],
    },
    "VaeDecodeTextureTrellis": {
        "display_name": "Decode Pixal3D PBR Voxels",
        "description": "Decodes base color, metallic and roughness attributes while preserving alignment with the shape surface.",
        "input": {"required": {
            "samples": ["LATENT", {"forceInput": True}],
            "vae": ["VAE", {"forceInput": True}],
            "shape_subdivides": ["SHAPE_SUBDIVIDES", {"forceInput": True}],
        }},
        "input_order": {"required": ["samples", "vae", "shape_subdivides"]},
        "output": ["VOXEL"],
        "output_name": ["voxel_colors"],
    },
    "BakeTextureFromVoxel": {
        "display_name": "Bake Pixal3D PBR Textures",
        "description": "Back-projects generated PBR attributes from the high-detail reference mesh onto the simplified UV mesh.",
        "input": {"required": {
            "mesh": ["MESH", {"forceInput": True}],
            "voxel_colors": ["VOXEL", {"forceInput": True}],
            "texture_size": ["INT", {"default": 1024, "min": 64, "max": 8192}],
        }, "optional": {"reference_mesh": ["MESH", {"forceInput": True}]}},
        "input_order": {"required": ["mesh", "voxel_colors", "texture_size"], "optional": ["reference_mesh"]},
        "output": ["IMAGE", "IMAGE", "IMAGE"],
        "output_name": ["base_color", "metallic", "roughness"],
    },
    "BakeNormalMapFromMesh": {
        "display_name": "Bake Normal Map",
        "description": "Bakes high-detail surface normals onto the simplified game mesh.",
        "input": {"required": {
            "low_poly": ["MESH", {"forceInput": True}],
            "high_poly": ["MESH", {"forceInput": True}],
            "resolution": ["INT", {"default": 1024}],
            "cage_distance": ["FLOAT", {"default": 0.05}],
            "ignore_backfaces": ["BOOLEAN", {"default": True}],
        }},
        "input_order": {"required": ["low_poly", "high_poly", "resolution", "cage_distance", "ignore_backfaces"]},
        "output": ["IMAGE"],
        "output_name": ["normal_map"],
    },
    "BakeAmbientOcclusion": {
        "display_name": "Bake Ambient Occlusion",
        "description": "Bakes local ambient occlusion from the high-detail reference onto the simplified mesh.",
        "input": {"required": {
            "low_poly": ["MESH", {"forceInput": True}],
            "high_poly": ["MESH", {"forceInput": True}],
            "resolution": ["INT", {"default": 1024}],
            "samples": ["INT", {"default": 32, "min": 4, "max": 1024}],
            "max_distance": ["FLOAT", {"default": 0.71}],
            "strength": ["FLOAT", {"default": 1.0}],
            "bias": ["FLOAT", {"default": 0.01}],
        }},
        "input_order": {"required": ["low_poly", "high_poly", "resolution", "samples", "max_distance", "strength", "bias"]},
        "output": ["IMAGE"],
        "output_name": ["occlusion"],
    },
    "ApplyTextureToMesh": {
        "display_name": "Apply PBR Maps to Mesh",
        "description": "Embeds the baked base-color, metallic, roughness, AO and normal maps into the final GLB material.",
        "input": {"required": {
            "mesh": ["MESH", {"forceInput": True}],
            "base_color": ["IMAGE", {"forceInput": True}],
        }, "optional": {
            "metallic": ["IMAGE", {"forceInput": True}],
            "roughness": ["IMAGE", {"forceInput": True}],
            "occlusion": ["IMAGE", {"forceInput": True}],
            "normal_map": ["IMAGE", {"forceInput": True}],
        }},
        "input_order": {"required": ["mesh", "base_color"], "optional": ["metallic", "roughness", "occlusion", "normal_map"]},
        "output": ["MESH"],
        "output_name": ["mesh"],
    },
}


def _by_id(workflow: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(node["id"]): node for node in workflow.get("nodes", []) if isinstance(node.get("id"), int)}


def _rebuild_link_references(workflow: dict[str, Any]) -> None:
    nodes = _by_id(workflow)
    for node in nodes.values():
        for item in node.get("inputs", []) or []:
            item["link"] = None
        for item in node.get("outputs", []) or []:
            item["links"] = []
    for link in workflow.get("links", []) or []:
        link_id, source_id, source_slot, target_id, target_slot = link[:5]
        if source_id not in nodes or target_id not in nodes:
            raise ValueError(f"dangling link {link_id}: {source_id}->{target_id}")
        source_outputs = nodes[source_id].get("outputs", []) or []
        target_inputs = nodes[target_id].get("inputs", []) or []
        if not 0 <= int(source_slot) < len(source_outputs):
            raise ValueError(f"link {link_id}: source slot out of range")
        if not 0 <= int(target_slot) < len(target_inputs):
            raise ValueError(f"link {link_id}: target slot out of range")
        source_outputs[source_slot].setdefault("links", []).append(link_id)
        target_inputs[target_slot]["link"] = link_id


def _connect(
    workflow: dict[str, Any], source_id: int, source_slot: int,
    target_id: int, target_slot: int, kind: str,
) -> None:
    link_id = max(
        [int(workflow.get("last_link_id", 0)), *[int(link[0]) for link in workflow.get("links", [])]],
        default=0,
    ) + 1
    workflow.setdefault("links", []).append([link_id, source_id, source_slot, target_id, target_slot, kind])
    workflow["last_link_id"] = link_id


def _set_widgets(node: dict[str, Any], values: list[Any], **named: Any) -> None:
    node["widgets_values"] = values
    if named:
        node["widgets_values_named"] = named


def _budget_node(template: dict[str, Any], node_id: int, target: int, title: str) -> dict[str, Any]:
    node = copy.deepcopy(template)
    node["id"] = node_id
    node["pos"] = [0, 0]
    node["order"] = 0
    node["title"] = title
    node["outputs"][0]["links"] = []
    _set_widgets(node, [target, "fixed"], value=target, fixed="fixed")
    return node


def _specialization(path_key: str) -> dict[str, Any]:
    if path_key == ENVIRONMENT_PATH:
        return {
            "family": "Pixal3D INT8 Buildings and Environment PBR for Godot",
            "kind": "buildings and environment assets",
            "budget": 12_000,
            "texture": 1_024,
            "padding": 4,
            "crease": 45.0,
            "ao_samples": 32,
            "remesh_smooth": 2,
            "remesh_drop_small": 0.002,
            "input": "viking_wolf_rune_axe.png",
            "output": "GameDev/Pixal3D_Environment/environment_asset_12000",
            "budget_title": "GODOT TRIANGLE BUDGET · 12.000 · Gebäude/Umgebung",
            "guide": (
                "=== PIXAL3D -> GEBÄUDE / UMGEBUNGSASSET -> PBR-GLB FÜR GODOT ===\n\n"
                "1) Ein EINZELNES freigestelltes Asset laden: Gebäudemodul, Fels, Baum, Kiste, Laterne usw. "
                "Keine komplette Straßenszene und keine Nachbarobjekte. Eine ruhige Dreiviertelansicht mit sichtbarer Seite/Dachfläche funktioniert besser als reine Frontansicht.\n"
                "2) Hintergrundentfernung eingeschaltet lassen; bei einer bereits korrekten Alpha-Maske den grünen Switch ausschalten.\n"
                "3) Pixal3D erzeugt bei 1024³ Form und PBR-Material. Ein auf der R9700 geprüfter 256³-UDF-Remesh normalisiert die Rohgeometrie mit QEF AUS; danach reduziert `midpoint` auf höchstens 12.000 Dreiecke, UV-entfaltet und backt auf 1024px. Der FINAL-GAME-MESH-INFO-Node zeigt die tatsächlich erreichte Zahl.\n"
                "4) Das Ergebnis liegt unter output/GameDev/Pixal3D_Environment/ und enthält eine PBR-Oberfläche.\n\n"
                "BUDGET-STARTWERTE: kleine/repetitive Props 4k-8k, normales Gebäudemodul 8k-16k, einzigartiges nahes Gebäude 16k-30k. Nicht blind erhöhen: Silhouette, tatsächliche Bildschirmgröße, Materialzahl und Overdraw zählen mehr. "
                "Für Bäume breite Blattgruppen statt tausender Einzelblätter verwenden.\n\n"
                "GODOT: GLB als Szene importieren, meshes/generate_lods aktiviert lassen, Collision separat und viel gröber erzeugen. Wiederholte Props über MultiMeshInstance3D instanzieren. Das GLB ist kein fertiges begehbares Level und besitzt keine automatisch sinnvolle Collision.\n\n"
                "RAM-SICHERHEIT: Ein Asset pro Server-Session ist der zuverlässige Batch-Start. Bei `--cache-classic` bleiben millionenfache Zwischenmeshes im Host-RAM; vor einem anderen Eingabebild ComfyUI neu starten."
            ),
            "truth": "one static PBR-textured environment GLB; no collision or modular level semantics",
        }
    if path_key == CREATURE_PATH:
        return {
            "family": "Pixal3D INT8 Humanoids and Animals PBR for Godot",
            "kind": "humanoids and animals",
            "budget": 24_000,
            "texture": 2_048,
            "padding": 8,
            "crease": 180.0,
            "ao_samples": 64,
            "remesh_smooth": 3,
            "remesh_drop_small": 0.003,
            "input": "DaPanda_00008_.png",
            "output": "GameDev/Pixal3D_Creatures/humanoid_or_animal_24000",
            "budget_title": "GODOT TRIANGLE BUDGET · 24.000 · Humanoid/Tier",
            "guide": (
                "=== PIXAL3D -> HUMANOID / TIER -> PBR-GLB FÜR GODOT ===\n\n"
                "1) Humanoid: vollständige neutrale A- oder T-Pose, beide Hände/Füße sichtbar, Arme und Beine klar getrennt, ruhiges Licht, keine Bodenschatten. Tier: neutral stehend, Beine und Schwanz getrennt sichtbar, seitliche Dreiviertelansicht.\n"
                "2) Hintergrundentfernung eingeschaltet lassen; bei einer bereits korrekten Alpha-Maske den grünen Switch ausschalten. Verdeckte Rückseiten werden aus EINEM Bild plausibel erfunden und müssen kontrolliert werden.\n"
                "3) Pixal3D erzeugt bei 1024³ Form und PBR-Material. Ein auf der R9700 geprüfter 256³-UDF-Remesh normalisiert die Rohgeometrie mit QEF AUS; danach reduziert `midpoint` auf höchstens 24.000 Dreiecke, normalisiert weich, UV-entfaltet und backt auf 2048px. Der FINAL-GAME-MESH-INFO-Node zeigt die tatsächlich erreichte Zahl.\n"
                "4) Das Ergebnis liegt unter output/GameDev/Pixal3D_Creatures/.\n\n"
                "BUDGET-STARTWERTE: einfacher NPC/Tier 12k-18k, normal nah sichtbar 18k-28k, einzelner Hero 28k-40k. Erst Silhouette, Gesicht, Hände/Pfoten und Gelenkbereiche prüfen; danach reduzieren. Für viele Figuren Materialzahl, Skinning und Schatten mitbudgetieren.\n\n"
                "WICHTIG: Ausgabe ist STATISCH und UNGERIGGT. Generative Dreiecks-Topologie ist nicht automatisch deformationstauglich. Vor Animation in Blender retopologisieren, Gelenkloops prüfen, Skeleton/Skin-Weights erzeugen und erst dann nach Godot exportieren. Godots Import-LODs ersetzen kein sauberes Rig.\n\n"
                "RAM-SICHERHEIT: Ein Asset pro Server-Session ist der zuverlässige Batch-Start. Bei `--cache-classic` bleiben millionenfache Zwischenmeshes im Host-RAM; vor einem anderen Eingabebild ComfyUI neu starten."
            ),
            "truth": "one static PBR-textured creature GLB; no skeleton, weights, animation, or deformation-ready topology",
        }
    raise ValueError(f"unsupported v0.9.7 path: {path_key}")


def specialize_game_asset_template(workflow: dict[str, Any], path_key: str) -> dict[str, Any]:
    """Return a deterministic Pixal3D-only Godot workflow for one v0.9.7 path."""
    if path_key not in GAME_PATHS:
        return copy.deepcopy(workflow)

    result = copy.deepcopy(workflow)
    spec = _specialization(path_key)
    nodes = _by_id(result)
    expected = {
        15: "CLIPVisionLoader", 40: "UNETLoader", 55: "LoadMoGeModel",
        92: "VaeDecodeShapeTrellis", 93: "VaeDecodeTextureTrellis",
        117: "VAELoader", 118: "VAELoader", 122: "LoadImage",
        147: "BakeTextureFromVoxel", 186: "DecimateMesh",
        193: "LoadBackgroundRemovalModel", 196: "UnwrapMesh",
        224: "BakeNormalMapFromMesh", 233: "BakeAmbientOcclusion",
        238: "MeshSmoothNormals", 241: "RemeshMesh", 252: "PaintMesh",
        260: "MeshSmoothNormals", 288: "PrimitiveInt", 298: "Pixal3DConditioning",
        299: "Trellis2Conditioning", 313: "MarkdownNote", 316: "PrimitiveBoolean",
        317: "MarkdownNote", 318: "ComfySwitchNode", 319: "UNETLoader",
        322: "Save3DAdvanced", 323: "Preview3DAdvanced",
    }
    for node_id, node_type in expected.items():
        if nodes.get(node_id, {}).get("type") != node_type:
            raise ValueError(f"{path_key}: pinned template node {node_id} is not {node_type}")

    # Remove vanilla TRELLIS.2 selection, its missing checkpoint, and the
    # in-place vertex-color preview branch. Keep the required geometry-remesh
    # stage, but replace its high-resolution defaults with the tested AMD UDF profile.
    removed_ids = {40, 252, 282, 299, 314, 315, 316, 318, 323}
    result["nodes"] = [node for node in result.get("nodes", []) if node.get("id") not in removed_ids]
    result["links"] = [
        link for link in result.get("links", [])
        if int(link[0]) != 1060  # DecimateMesh -> normals; route through final GetMeshInfo below.
        and int(link[1]) not in removed_ids
        and int(link[3]) not in removed_ids
    ]

    # Direct Pixal3D model and conditioning wiring.
    _connect(result, 319, 0, 199, 0, "MODEL")
    _connect(result, 319, 0, 279, 0, "MODEL")
    _connect(result, 319, 0, 12, 0, "MODEL")
    _connect(result, 298, 0, 3, 1, "CONDITIONING")
    _connect(result, 298, 0, 91, 0, "CONDITIONING")
    _connect(result, 298, 1, 3, 2, "CONDITIONING")
    _connect(result, 298, 1, 91, 1, "CONDITIONING")

    # The pinned official links keep GetMeshInfo -> Remesh -> Decimate and use
    # the normalized remesh as the normal/AO high-poly reference. The raw
    # Pixal shape remains the reference for voxel-to-texture back-projection.

    # One visible control is the authoritative final triangle ceiling.
    next_node_id = max(int(result.get("last_node_id", 0)), *[int(n["id"]) for n in result["nodes"]]) + 1
    budget = _budget_node(nodes[288], next_node_id, spec["budget"], spec["budget_title"])
    budget["order"] = max(int(node.get("order", 0)) for node in result["nodes"]) + 1
    result["nodes"].append(budget)

    final_info_id = next_node_id + 1
    final_info = copy.deepcopy(nodes[202])
    final_info["id"] = final_info_id
    final_info["pos"] = [0, 0]
    final_info["order"] = budget["order"] + 1
    final_info["title"] = "FINAL GAME MESH INFO · tatsächliche Dreiecke prüfen"
    for item in final_info.get("inputs", []) or []:
        item["link"] = None
    for item in final_info.get("outputs", []) or []:
        item["links"] = []
    result["nodes"].append(final_info)
    result["last_node_id"] = final_info_id

    decimate_inputs = _by_id(result)[186].setdefault("inputs", [])
    if not any(item.get("name") == "target_face_count" for item in decimate_inputs):
        decimate_inputs.append({
            "name": "target_face_count",
            "type": "INT",
            "widget": {"name": "target_face_count"},
            "link": None,
        })
    target_slot = next(
        index for index, item in enumerate(decimate_inputs)
        if item.get("name") == "target_face_count"
    )
    _connect(result, next_node_id, 0, 186, target_slot, "INT")
    _connect(result, 186, 0, final_info_id, 0, "MESH")
    _connect(result, final_info_id, 0, 238, 0, "MESH")

    nodes = _by_id(result)
    nodes[122]["title"] = "STARTBILD · einzelnes freigestelltes Asset"
    _set_widgets(nodes[122], [spec["input"], "image"], image=spec["input"], upload="image")
    nodes[319]["title"] = "Pixal3D INT8 ConvRot · Open Weights · R9700"
    _set_widgets(nodes[319], ["pixal3d_int8_convrot.safetensors", "default"], unet_name="pixal3d_int8_convrot.safetensors", weight_dtype="default")
    nodes[94]["title"] = "GAME DETAIL · Shape 1024³ statt 1536³"
    _set_widgets(nodes[94], [1024], target_resolution=1024)
    nodes[241]["title"] = "AMD-SAFE REMESH · 256³ UDF · QEF aus"
    _set_widgets(
        nodes[241],
        [256, "udf", False, False, False, 1.0, 0.0, False, spec["remesh_smooth"], spec["remesh_drop_small"], 20_000_000],
        resolution=256,
        sign_mode="udf",
        qef=False,
        drop_inverted_components=False,
        drop_enclosed_components=False,
        band=1.0,
        project_back=0.0,
        fix_poles=False,
        smooth_iters=spec["remesh_smooth"],
        drop_small_components=spec["remesh_drop_small"],
        precluster_max_verts=20_000_000,
    )
    nodes[186]["title"] = f"GAME MESH · maximal {spec['budget']:,} Dreiecke · midpoint".replace(",", ".")
    _set_widgets(nodes[186], [spec["budget"], "midpoint"], target_face_count=spec["budget"], placement_mode="midpoint")
    nodes[238]["title"] = f"GAME NORMALS · {spec['crease']:g}° Crease"
    _set_widgets(nodes[238], [spec["crease"]], crease_angle=spec["crease"])
    nodes[260]["title"] = f"FINAL NORMALS · {spec['crease']:g}° Crease"
    _set_widgets(nodes[260], [spec["crease"]], crease_angle=spec["crease"])
    nodes[288]["title"] = f"PBR TEXTURE · {spec['texture']}px"
    _set_widgets(nodes[288], [spec["texture"], "fixed"], value=spec["texture"], fixed="fixed")
    _set_widgets(
        nodes[196], ["pec", spec["texture"], spec["padding"], 0.0002],
        segmenter="pec", resolution=spec["texture"], padding=spec["padding"], weld_distance=0.0002,
    )
    _set_widgets(nodes[147], [spec["texture"]], texture_size=spec["texture"])
    _set_widgets(nodes[224], [spec["texture"], 0.05, True], resolution=spec["texture"], cage_distance=0.05, ignore_backfaces=True)
    _set_widgets(
        nodes[233], [spec["texture"], spec["ao_samples"], 0.71, 1, 0.01],
        resolution=spec["texture"], samples=spec["ao_samples"], max_distance=0.71, strength=1, bias=0.01,
    )
    _set_widgets(nodes[261], [spec["texture"]], resolution=spec["texture"])
    nodes[322]["title"] = "GODOT · PBR-GLB speichern"
    _set_widgets(
        nodes[322], [spec["output"], "", 1024, 1024],
        filename_prefix=spec["output"], viewport_state="", width=1024, height=1024,
    )

    nodes[250]["title"] = "Pixal3D Sampling-Hinweis"
    nodes[250]["widgets_values"] = [
        "Die CFG-Override-/Rescale-Werte entsprechen dem offiziellen Pixal3D-Core-Template. "
        "Für den ersten Qualitätsvergleich nicht zusammen mit Auflösung, Schritten und Budget ändern."
    ]
    nodes[313]["title"] = "START HIER · Pixal3D Game Asset für Godot"
    nodes[313]["widgets_values"] = [spec["guide"]]
    nodes[317]["title"] = "Modellentscheidung · Open Weights, Lizenz und Grenzen"
    nodes[317]["widgets_values"] = [
        "**Warum Pixal3D statt Hunyuan3D 2.1?**\n\n"
        "Pixal3D (SIGGRAPH 2026) nutzt eine TRELLIS.2-Basis, pixel-ausgerichtete Kamerakonditionierung und erzeugt neben höher aufgelöster Form direkt Base Color, Metallic und Roughness. "
        "Das ist für sichtnahe Godot-Assets der größere praktische Qualitätssprung als nur ein weiterer Hunyuan-Shape-Checkpoint.\n\n"
        "**Bewusst nicht installiert:** TRELLIS.2 ist die weniger bildtreue Baseline desselben Core-Graphen; Hunyuan3D-Omni bietet Pose/BBox/Point/Voxel-Kontrolle, aber keinen gepflegten ComfyUI-/Windows-ROCm-Pfad und kein gleichwertiges PBR-Endergebnis; Step1X-3D bleibt CUDA-orientiert und führt ComfyUI noch als offene Roadmap.\n\n"
        "**Lokale Gewichte (9,27 GiB):** `pixal3d_int8_convrot`, DINOv3+NAF, Shape-VAE, Texture-VAE, MoGe 2 und BiRefNet. Alle sechs Dateien sind im Installer SHA-256-gepinnt.\n\n"
        "**Lizenzstand bei Erstellung:** Pixal3D, MoGe und BiRefNet sind in den offiziellen Repositories MIT-markiert. Der eingebettete DINOv3-Encoder unterliegt Metas eigener DINOv3-Lizenz; diese gewährt eine weltweite, gebührenfreie Nutzung einschließlich kommerzieller Nutzung, enthält aber Weitergabe-, Trade-Control- und Nutzungsbedingungen. Keine Rechtsberatung: vor Veröffentlichung die verlinkten aktuellen Originaltexte prüfen.\n\n"
        "Quellen: https://github.com/TencentARC/Pixal3D · https://docs.comfy.org/tutorials/3d/pixal3d · https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md\n\n"
        "**Technische Grenze:** Das Ergebnis bleibt ein aus einer Ansicht generiertes statisches Asset. Rückseiten, Innenräume, Maßstab, modulare Anschlüsse, Collision und bei Figuren Rig/Deformation müssen im 3D-Editor kontrolliert werden. Der notwendige 256³-UDF-Remesh lief mit QEF AUS auf der R9700 stabil und verhindert die sonst fragmentierte Pixal-Rohgeometrie. SDF/QEF und die QEM-optimale Vertex-Platzierung bleiben wegen lokaler HIP-Fehler aus; die Vereinfachung verwendet `midpoint`."
    ]

    # The authored note no longer advertises or requires the removed TRELLIS.2 checkpoint.
    result.setdefault("extra", {})[UPGRADE_KEY] = {
        "version": UPGRADE_VERSION,
        "release": "v0.9.7",
        "family": spec["family"],
        "asset_kind": spec["kind"],
        "source_template": SOURCE_TEMPLATE,
        "source_template_sha256": SOURCE_TEMPLATE_SHA256,
        "selected_model": "Comfy-Org/Pixal3D pixal3d_int8_convrot.safetensors",
        "model_downloads": len(MODEL_FILES),
        "model_download_bytes": sum(item["size"] for item in MODEL_FILES),
        "model_files": copy.deepcopy(MODEL_FILES),
        "generation_resolution": 1024,
        "triangle_budget_default": spec["budget"],
        "triangle_budget_semantics": "upper bound; final GetMeshInfo reports the achieved count",
        "texture_resolution_default": spec["texture"],
        "uv_padding": spec["padding"],
        "remesh": {
            "resolution": 256,
            "sign_mode": "udf",
            "qef": False,
            "smooth_iters": spec["remesh_smooth"],
            "drop_small_components": spec["remesh_drop_small"],
        },
        "decimator": "ComfyUI Core UDF remesh qef=false + DecimateMesh midpoint; no SDF/QEF or qem placement",
        "output_prefix": spec["output"],
        "truthful_output": spec["truth"],
        "host_ram_policy": "with --cache-classic restart ComfyUI before changing to another input image",
        "godot_lods": "use meshes/generate_lods at import; workflow exports one source mesh",
    }
    result["extra"]["dawasteh_dual_gpu"] = {
        "family": spec["family"],
        "source": f"workflows/{path_key}",
        "curated_split_default": False,
        "defaults": {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"},
    }

    _rebuild_link_references(result)
    result["last_link_id"] = max(int(link[0]) for link in result.get("links", []))
    return result
