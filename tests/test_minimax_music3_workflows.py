from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from tools.generate_minimax_music3_prompt_enhancer import build as build_enhancer
from tools.generate_minimax_music3_workflow import build as build_music
from tools.validate_workflows import graph_locator, validate_graph


ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "workflows" / "Music Generation" / "MiniMax_Music3_FP32-BF16-Text-to-Music.json"
DUAL = ROOT / "workflows" / "Dual GPU - R9700 + RX 9070 XT" / "MiniMax-Music3-DualGPU-Text-to-Music.json"
ENHANCER = ROOT / "workflows" / "Prompt Enhancer" / "MiniMax_Music3-Official-Skill-Caption-Enhancer.json"
SKILL = ROOT / "prompt-libraries" / "MiniMax-Music3-Official-Skill" / "SKILL.md"
ROUTER = ROOT / "prompt-libraries" / "MiniMax-Music3-Official-Skill" / "genre-router.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def graphs(workflow: dict):
    yield workflow
    for graph in workflow.get("definitions", {}).get("subgraphs", []):
        yield from graphs(graph)


def all_nodes(workflow: dict) -> list[dict]:
    return [node for graph in graphs(workflow) for node in graph.get("nodes", [])]


class MiniMaxMusic3WorkflowTests(unittest.TestCase):
    def test_single_gpu_workflow_is_deterministic_and_uses_downloaded_full_precision_models(self):
        workflow = load(MUSIC)
        self.assertEqual(workflow, build_music())
        nodes = all_nodes(workflow)
        by_type = {node["type"]: node for node in nodes}
        self.assertEqual(
            by_type["UNETLoader"]["widgets_values"][0],
            r"MiniMax Music 3\minimax_music3_dit_fp32.safetensors",
        )
        self.assertEqual(
            by_type["CLIPLoader"]["widgets_values"][0],
            r"MiniMax Music 3\minimax_music3_text_encoder_bf16.safetensors",
        )
        self.assertEqual(
            by_type["VAELoader"]["widgets_values"][0],
            r"MiniMax Music 3\minimax_music3_dav.safetensors",
        )
        self.assertIn("MiniMaxMusic3TextEncode", by_type)
        self.assertIn("EmptyMiniMaxMusic3LatentAudio", by_type)
        self.assertIn("SaveAudioAdvanced", by_type)
        self.assertEqual(sum(node["type"] == "PixaromaRunTimer" for node in workflow["nodes"]), 1)
        validation = workflow["extra"]["dawasteh_minimax_music3"]["validation"]
        self.assertEqual(validation["status"], "live-smoke-passed")
        self.assertIn("30 Euler/simple steps", validation["profile"])
        self.assertIn("7.988 second", validation["result"])
        self.assertNotIn("CUDAExecutionProvider", json.dumps(workflow))

    def test_dual_gpu_workflow_places_components_by_actual_full_precision_size(self):
        workflow = load(DUAL)
        control = next(node for node in workflow["nodes"] if node["type"] == "DaWMultiGPUDeviceControl")
        self.assertEqual(control["widgets_values"], ["gpu:1", "gpu:0", "gpu:1"])
        selectors = {node["type"]: node for node in all_nodes(workflow) if node["type"].startswith("Select") and node["type"].endswith("Device")}
        self.assertEqual(selectors["SelectModelDevice"]["widgets_values"], ["gpu:1"])
        self.assertEqual(selectors["SelectCLIPDevice"]["widgets_values"], ["gpu:0"])
        self.assertEqual(selectors["SelectVAEDevice"]["widgets_values"], ["gpu:1"])
        metadata = workflow["extra"]["dawasteh_dual_gpu"]
        self.assertEqual(metadata["family"], "MiniMax Music 3")
        self.assertIn("R9700 32 GB", metadata["default_clip_device"])
        self.assertIn("RX 9070 XT 16 GB", metadata["default_vae_device"])
        self.assertEqual(metadata["validation"]["status"], "live-smoke-passed")
        self.assertIn("CLIP cuda:0 R9700", metadata["validation"]["observed_placement"])

    def test_prompt_enhancer_is_deterministic_and_pins_the_official_skill(self):
        workflow = load(ENHANCER)
        self.assertEqual(workflow, build_enhancer())
        metadata = workflow["extra"]["dawasteh_minimax_music3_prompt_skill"]
        expected_hashes = {
            SKILL.relative_to(ROOT).as_posix(): hashlib.sha256(SKILL.read_bytes()).hexdigest(),
            ROUTER.relative_to(ROOT).as_posix(): hashlib.sha256(ROUTER.read_bytes()).hexdigest(),
        }
        self.assertEqual({item["path"]: item["sha256"] for item in metadata["sources"]}, expected_hashes)
        by_id = {node["id"]: node for node in workflow["nodes"]}
        instruction = by_id[1]["widgets_values"][0]
        self.assertIn("OFFICIAL MINIMAX MUSIC CAPTION REWRITER SKILL", instruction)
        self.assertIn("### Global Metadata", instruction)
        self.assertIn("### Vocal Details", instruction)
        self.assertIn("### Arrangement", instruction)
        self.assertIn("never quote, paraphrase, summarize, or reproduce lyric lines", instruction)
        self.assertEqual(by_id[9]["title"], "1 · YOUR MUSIC IDEA / CAPTION")
        self.assertEqual(by_id[11]["title"], "2 · OPTIONAL TAGGED LYRICS")
        for node_id in (9, 11):
            self.assertEqual(by_id[node_id]["widgets_values"], [""])
            self.assertEqual(by_id[node_id]["properties"]["promptState"]["text"], "")
        self.assertEqual(
            by_id[11]["properties"]["dawasteh_pixaroma_prompt_integration"]["target"],
            [12, "string_b"],
        )
        self.assertIn("intentionally narrows", instruction)
        self.assertEqual(by_id[4]["widgets_values"], [r"Qwen\qwen3.5_4b_bf16.safetensors", "stable_diffusion", "default"])
        links = {link[0]: link for link in workflow["links"]}
        self.assertEqual(links[4][1:5], [9, 0, 1, 1])
        self.assertEqual(links[7][1:5], [11, 0, 12, 1])
        self.assertEqual(links[2][1:5], [12, 0, 2, 4])

    def test_all_three_new_workflows_are_structurally_valid(self):
        for path in (MUSIC, DUAL, ENHANCER):
            with self.subTest(workflow=path.name):
                workflow = load(path)
                errors: list[str] = []
                for locator, graph in graph_locator(workflow):
                    validate_graph(path, locator, graph, errors)
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
