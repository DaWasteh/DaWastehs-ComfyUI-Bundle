from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from tools.migrate_workflows_v092 import ADDITIONS, build_addition, migrate_workflow
from tools.upgrade_v097 import (
    CREATURE_PATH,
    ENVIRONMENT_PATH,
    GAME_PATHS,
    MODEL_FILES,
    SOURCE_TEMPLATE,
    SOURCE_TEMPLATE_SHA256,
    UPGRADE_KEY,
    UPGRADE_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
TEMPLATES = ROOT / "tools" / "workflow_templates"


def load(path_key: str) -> dict:
    return json.loads((WORKFLOWS / Path(path_key)).read_text(encoding="utf-8"))


def links(workflow: dict) -> dict[int, list]:
    return {int(link[0]): link for link in workflow["links"]}


class V097GameDevelopmentTests(unittest.TestCase):
    def test_pinned_official_template_reconstructs_both_additions_exactly(self):
        additions = {addition.path: addition for addition in ADDITIONS if addition.path in GAME_PATHS}
        self.assertEqual(set(additions), GAME_PATHS)
        for path_key, addition in additions.items():
            with self.subTest(path=path_key):
                expected = migrate_workflow(build_addition(addition), path_key)
                current = load(path_key)
                self.assertEqual(expected, current)
                self.assertEqual(migrate_workflow(current, path_key), current)

    def test_source_template_and_model_manifest_are_content_pinned(self):
        source = TEMPLATES / SOURCE_TEMPLATE
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), SOURCE_TEMPLATE_SHA256)
        self.assertEqual(len(MODEL_FILES), 6)
        self.assertEqual(sum(item["size"] for item in MODEL_FILES), 9_950_408_908)
        self.assertEqual(len({item["path"] for item in MODEL_FILES}), 6)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in MODEL_FILES))
        self.assertEqual(
            {item["path"] for item in MODEL_FILES},
            {
                "diffusion_models/pixal3d_int8_convrot.safetensors",
                "clip_vision/dino_v3_L_naf_fp32.safetensors",
                "vae/trellis_2_shape_vae_bf16.safetensors",
                "vae/trellis_2_texture_vae_bf16.safetensors",
                "geometry_estimation/moge_2_vitl_normal_fp16.safetensors",
                "background_removal/birefnet.safetensors",
            },
        )

    def test_both_workflows_use_pixal_and_the_rocm_safe_udf_midpoint_profile(self):
        for path_key in sorted(GAME_PATHS):
            with self.subTest(path=path_key):
                workflow = load(path_key)
                types = [node["type"] for node in workflow["nodes"]]
                self.assertEqual(types.count("UNETLoader"), 1)
                self.assertEqual(types.count("Pixal3DConditioning"), 1)
                self.assertEqual(types.count("Trellis2Conditioning"), 0)
                self.assertEqual(types.count("RemeshMesh"), 1)
                self.assertEqual(types.count("DecimateMesh"), 1)
                self.assertEqual(types.count("GetMeshInfo"), 2)

                unet = next(node for node in workflow["nodes"] if node["type"] == "UNETLoader")
                self.assertEqual(unet["widgets_values"], ["pixal3d_int8_convrot.safetensors", "default"])
                upsample = next(node for node in workflow["nodes"] if node["type"] == "Trellis2UpsampleStage")
                self.assertEqual(upsample["widgets_values"], [1024])

                remesh = next(node for node in workflow["nodes"] if node["type"] == "RemeshMesh")
                self.assertEqual(remesh["widgets_values"][:8], [256, "udf", False, False, False, 1.0, 0.0, False])
                decimator = next(node for node in workflow["nodes"] if node["type"] == "DecimateMesh")
                self.assertEqual(decimator["widgets_values"][1], "midpoint")
                self.assertEqual(links(workflow)[decimator["inputs"][0]["link"]][1:5], [remesh["id"], 0, decimator["id"], 0])
                for bake_type in ("BakeNormalMapFromMesh", "BakeAmbientOcclusion"):
                    bake = next(node for node in workflow["nodes"] if node["type"] == bake_type)
                    high_poly = next(item for item in bake["inputs"] if item["name"] == "high_poly")
                    self.assertEqual(links(workflow)[high_poly["link"]][1], remesh["id"])
                budget = next(
                    node for node in workflow["nodes"]
                    if node["type"] == "PrimitiveInt" and node.get("title", "").startswith("GODOT TRIANGLE BUDGET")
                )
                budget_input = next(item for item in decimator["inputs"] if item["name"] == "target_face_count")
                self.assertEqual(links(workflow)[budget_input["link"]][1:5], [budget["id"], 0, decimator["id"], decimator["inputs"].index(budget_input)])
                final_info = next(
                    node for node in workflow["nodes"]
                    if node.get("title") == "FINAL GAME MESH INFO · tatsächliche Dreiecke prüfen"
                )
                self.assertEqual(links(workflow)[final_info["inputs"][0]["link"]][1:5], [decimator["id"], 0, final_info["id"], 0])
                first_normals = next(node for node in workflow["nodes"] if node.get("title", "").startswith("GAME NORMALS"))
                self.assertEqual(links(workflow)[first_normals["inputs"][0]["link"]][1:5], [final_info["id"], 0, first_normals["id"], 0])

                controls = [node for node in workflow["nodes"] if node["type"] == "DaWMultiGPUDeviceControl"]
                self.assertEqual(len(controls), 1)
                self.assertEqual(controls[0]["widgets_values"], ["gpu:0", "gpu:0", "gpu:0"])

                marker = workflow["extra"][UPGRADE_KEY]
                self.assertEqual(marker["version"], UPGRADE_VERSION)
                self.assertEqual(marker["release"], "v0.9.7")
                self.assertEqual(marker["model_downloads"], 6)
                self.assertEqual(marker["model_download_bytes"], 9_950_408_908)
                self.assertEqual(marker["generation_resolution"], 1024)
                self.assertEqual(marker["triangle_budget_semantics"], "upper bound; final GetMeshInfo reports the achieved count")
                self.assertEqual(marker["remesh"]["resolution"], 256)
                self.assertEqual(marker["remesh"]["sign_mode"], "udf")
                self.assertFalse(marker["remesh"]["qef"])
                self.assertEqual(marker["decimator"], "ComfyUI Core UDF remesh qef=false + DecimateMesh midpoint; no SDF/QEF or qem placement")
                self.assertEqual(marker["host_ram_policy"], "with --cache-classic restart ComfyUI before changing to another input image")

    def test_environment_profile_exports_a_single_12k_1k_pbr_glb(self):
        workflow = load(ENVIRONMENT_PATH)
        marker = workflow["extra"][UPGRADE_KEY]
        self.assertEqual(marker["triangle_budget_default"], 12_000)
        self.assertEqual(marker["texture_resolution_default"], 1_024)
        self.assertEqual(marker["uv_padding"], 4)
        self.assertEqual(marker["remesh"]["smooth_iters"], 2)
        self.assertEqual(marker["remesh"]["drop_small_components"], 0.002)
        self.assertIn("no collision", marker["truthful_output"])

        decimator = next(node for node in workflow["nodes"] if node["type"] == "DecimateMesh")
        self.assertEqual(decimator["widgets_values"], [12_000, "midpoint"])
        normals = [node["widgets_values"] for node in workflow["nodes"] if node["type"] == "MeshSmoothNormals"]
        self.assertEqual(normals, [[45.0], [45.0]])
        texture = next(node for node in workflow["nodes"] if node.get("title") == "PBR TEXTURE · 1024px")
        self.assertEqual(texture["widgets_values"], [1024, "fixed"])
        save = next(node for node in workflow["nodes"] if node["type"] == "Save3DAdvanced")
        self.assertEqual(save["widgets_values"][0], "GameDev/Pixal3D_Environment/environment_asset_12000")

    def test_creature_profile_is_truthful_about_rigging_and_uses_24k_2k(self):
        workflow = load(CREATURE_PATH)
        marker = workflow["extra"][UPGRADE_KEY]
        source = next(node for node in workflow["nodes"] if node["type"] == "LoadImage")
        self.assertEqual(source["widgets_values"][0], "DaPanda_00008_.png")
        self.assertEqual(marker["triangle_budget_default"], 24_000)
        self.assertEqual(marker["texture_resolution_default"], 2_048)
        self.assertEqual(marker["uv_padding"], 8)
        self.assertEqual(marker["remesh"]["smooth_iters"], 3)
        self.assertEqual(marker["remesh"]["drop_small_components"], 0.003)
        self.assertIn("no skeleton", marker["truthful_output"])
        self.assertIn("deformation-ready", marker["truthful_output"])

        decimator = next(node for node in workflow["nodes"] if node["type"] == "DecimateMesh")
        self.assertEqual(decimator["widgets_values"], [24_000, "midpoint"])
        normals = [node["widgets_values"] for node in workflow["nodes"] if node["type"] == "MeshSmoothNormals"]
        self.assertEqual(normals, [[180.0], [180.0]])
        save = next(node for node in workflow["nodes"] if node["type"] == "Save3DAdvanced")
        self.assertEqual(save["widgets_values"][0], "GameDev/Pixal3D_Creatures/humanoid_or_animal_24000")

        authored = "\n".join(
            str(node.get("widgets_values", [""])[0])
            for node in workflow["nodes"]
            if node["type"] == "MarkdownNote" and not node.get("properties", {}).get("dawasteh_generated_note")
        )
        self.assertIn("STATISCH und UNGERIGGT", authored)
        self.assertIn("retopologisieren", authored)
        self.assertIn("Hunyuan3D-Omni", authored)
        self.assertIn("DINOv3-Lizenz", authored)


if __name__ == "__main__":
    unittest.main()
