from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from tools.migrate_workflows_v092 import migrate_workflow
from tools.upgrade_v095 import HUNYUAN_PATH
from tools.upgrade_v096 import UPGRADE_KEY, UPGRADE_VERSION, upgrade_workflow


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / Path(HUNYUAN_PATH)


def load() -> dict:
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def by_id(workflow: dict) -> dict[int, dict]:
    return {node["id"]: node for node in workflow["nodes"]}


class V096GameDevelopmentTests(unittest.TestCase):
    def test_v095_release_reconstructs_current_v096_exactly(self):
        previous = json.loads(
            subprocess.check_output(
                ["git", "show", f"v0.9.5:workflows/{HUNYUAN_PATH}"],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
            )
        )
        self.assertEqual(migrate_workflow(previous, HUNYUAN_PATH), load())

    def test_upgrade_is_idempotent(self):
        workflow = load()
        upgraded, changed = upgrade_workflow(workflow, HUNYUAN_PATH)
        self.assertFalse(changed)
        self.assertEqual(upgraded, workflow)
        marker = workflow["extra"][UPGRADE_KEY]
        self.assertEqual(marker["version"], UPGRADE_VERSION)
        self.assertEqual(marker["release"], "v0.9.6")
        self.assertEqual(marker["model_downloads"], 0)

    def test_hunyuan_workflow_exports_independent_uv_unwrapped_lod_ladder(self):
        workflow = load()
        nodes = by_id(workflow)
        links = {link[0]: link for link in workflow["links"]}

        voxel_meshes = [node for node in workflow["nodes"] if node["type"] == "VoxelToMesh"]
        decimators = [node for node in workflow["nodes"] if node["type"] == "DecimateMesh"]
        unwraps = [node for node in workflow["nodes"] if node["type"] == "UnwrapMesh"]
        normals = [node for node in workflow["nodes"] if node["type"] == "MeshSmoothNormals"]
        saves = [node for node in workflow["nodes"] if node["type"] == "SaveGLB"]

        self.assertEqual([node["widgets_values"] for node in voxel_meshes], [
            ["surface net", 0.60],
            ["surface net", 0.58],
            ["surface net", 0.55],
            ["surface net", 0.52],
        ])
        self.assertEqual([node["widgets_values"] for node in decimators], [
            [5000, "midpoint"],
            [2500, "midpoint"],
            [1200, "midpoint"],
            [600, "midpoint"],
        ])
        self.assertEqual([node["widgets_values"] for node in unwraps], [["pec", 256, 2, 0.0]] * 4)
        self.assertEqual([node["widgets_values"] for node in normals], [[60.0]] * 4)
        self.assertEqual([node["widgets_values"][0] for node in saves], [
            "GameDev/Hunyuan3D_LowPoly/lod0_hero_5000",
            "GameDev/Hunyuan3D_LowPoly/lod1_game_2500",
            "GameDev/Hunyuan3D_LowPoly/lod2_distant_1200",
            "GameDev/Hunyuan3D_LowPoly/lod3_ultra_0600",
        ])

        # Every save is Save <- normals <- unwrap <- decimate. LOD1-3 use
        # independent VoxelToMesh nodes so in-place simplification cannot leak.
        for index, save in enumerate(saves):
            normal = nodes[links[save["inputs"][0]["link"]][1]]
            unwrap = nodes[links[normal["inputs"][0]["link"]][1]]
            decimator = nodes[links[unwrap["inputs"][0]["link"]][1]]
            source = nodes[links[decimator["inputs"][0]["link"]][1]]
            self.assertEqual(normal["type"], "MeshSmoothNormals")
            self.assertEqual(unwrap["type"], "UnwrapMesh")
            self.assertEqual(decimator["type"], "DecimateMesh")
            if index == 0:
                self.assertEqual(source["id"], 25)
                self.assertEqual(source["type"], "VRAM_Debug")
            else:
                self.assertEqual(source["type"], "VoxelToMesh")
                voxel_link = links[source["inputs"][0]["link"]]
                self.assertEqual(voxel_link[1:5], [8, 0, source["id"], 0])

    def test_v096_marker_and_truthful_notes(self):
        workflow = load()
        nodes = by_id(workflow)
        marker = workflow["extra"][UPGRADE_KEY]
        self.assertEqual(marker["target_face_counts"], [5000, 2500, 1200, 600])
        self.assertEqual(marker["voxel_thresholds"], [0.60, 0.58, 0.55, 0.52])
        self.assertEqual(marker["uv_resolution"], 256)
        self.assertEqual(marker["crease_angle_degrees"], 60)
        self.assertIn("no additional model", marker["model_decision"])

        setup = nodes[11]["widgets_values"][0]
        model_decision = nodes[12]["widgets_values"][0]
        self.assertIn("vier UNABHÄNGIGE", setup)
        self.assertIn("50 Dreiecke", setup)
        self.assertIn("UV-ENTFALTET, ABER UNTEXTURIERT", setup)
        self.assertIn("MeshAnything V2", model_decision)
        self.assertIn("nicht installiert", model_decision)


if __name__ == "__main__":
    unittest.main()
