from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from tools.migrate_workflows_v092 import migrate_workflow
from tools.upgrade_v095 import (
    ADDITION_SOURCES,
    HUNYUAN_PATH,
    TEXTURE_PATH,
    UPGRADE_KEY,
    UPGRADE_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"


def load(path_key: str) -> dict:
    return json.loads((WORKFLOWS / Path(path_key)).read_text(encoding="utf-8"))


def by_id(workflow: dict) -> dict[int, dict]:
    return {node["id"]: node for node in workflow["nodes"]}


class V095GameDevelopmentTests(unittest.TestCase):
    def test_v094_sources_reconstruct_both_additions_exactly(self):
        for target, source in ADDITION_SOURCES.items():
            with self.subTest(target=target):
                previous = json.loads(
                    subprocess.check_output(
                        ["git", "show", f"v0.9.4:workflows/{source}"],
                        cwd=ROOT,
                        text=True,
                        encoding="utf-8",
                    )
                )
                self.assertEqual(migrate_workflow(previous, target), load(target))

    def test_game_additions_are_idempotent_and_use_no_new_model_download(self):
        for target in (TEXTURE_PATH, HUNYUAN_PATH):
            with self.subTest(target=target):
                workflow = load(target)
                self.assertEqual(migrate_workflow(workflow, target), workflow)
                marker = workflow["extra"][UPGRADE_KEY]
                self.assertEqual(marker["version"], UPGRADE_VERSION)
                self.assertEqual(marker["release"], "v0.9.5")
                self.assertEqual(marker["model_downloads"], 0)
                controls = [node for node in workflow["nodes"] if node["type"] == "DaWMultiGPUDeviceControl"]
                self.assertEqual(len(controls), 1)
                self.assertEqual(controls[0]["widgets_values"], ["gpu:0", "gpu:0", "gpu:0"])

    def test_texture_workflow_uses_installed_flux2_stack_and_exports_source_game_and_preview(self):
        workflow = load(TEXTURE_PATH)
        nodes = by_id(workflow)
        self.assertEqual(nodes[1]["widgets_values"], ["FLUX\\flux-2-klein-4b.safetensors", "default"])
        self.assertEqual(nodes[2]["widgets_values"], ["Qwen\\qwen_3_4b.safetensors", "flux2", "default"])
        self.assertEqual(nodes[5]["widgets_values"], [1024, 1024, 1])
        self.assertEqual(nodes[6]["widgets_values"][2:6], [4, 1, "euler", "simple"])
        small = next(node for node in workflow["nodes"] if node.get("title") == "GAME TEXTURE · Area-Downscale auf 128px")
        quantize = next(node for node in workflow["nodes"] if node["type"] == "ImageQuantize")
        preview = next(node for node in workflow["nodes"] if node.get("title") == "NEAREST PREVIEW · 1024px")
        self.assertEqual(small["widgets_values"], ["area", 128, 128, "disabled"])
        self.assertEqual(quantize["widgets_values"], [32, "bayer-4"])
        self.assertEqual(preview["widgets_values"], ["nearest-exact", 1024, 1024, "disabled"])
        prefixes = {node["widgets_values"][0] for node in workflow["nodes"] if node["type"] == "SaveImage"}
        self.assertEqual(
            prefixes,
            {
                "GameDev/PS1_Texture_Concept/source_1024",
                "GameDev/PS1_Texture_Concept/game_128",
                "GameDev/PS1_Texture_Concept/nearest_preview_1024",
            },
        )
        setup = nodes[10]["widgets_values"][0]
        self.assertIn("kein automatisch passendes UV-Atlas", setup)
        self.assertIn("Filter AUS", setup)

    def test_hunyuan_workflow_preserves_v095_addition_provenance(self):
        workflow = load(HUNYUAN_PATH)
        nodes = by_id(workflow)
        marker = workflow["extra"][UPGRADE_KEY]

        self.assertEqual(nodes[1]["widgets_values"][0], "Hunyuan3D\\hunyuan_3d_v2.1.safetensors")
        self.assertEqual(nodes[3]["type"], "ModelSamplingAuraFlow")
        self.assertEqual(nodes[3]["widgets_values"], [1])
        self.assertEqual(marker["release"], "v0.9.5")
        self.assertEqual(marker["target_face_count"], 5000)
        self.assertEqual(marker["truthful_output"], "static, untextured, unrigged GLB intermediate")


if __name__ == "__main__":
    unittest.main()
