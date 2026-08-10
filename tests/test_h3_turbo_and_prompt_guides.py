from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from tools.generate_h3_prompt_enhancers import ENHANCERS, generate
from tools.integrate_h3_turbo_lora import (
    DIRECTOR_WORKFLOW,
    LORA_NAME,
    LORA_SHA256,
    VISIBLE_WORKFLOWS,
    integrate,
)


ROOT = Path(__file__).resolve().parents[1]
H3_DIR = ROOT / "workflows" / "Reference to Video"
PROMPT_DIR = ROOT / "workflows" / "Prompt Enhancer"


class H3TurboWorkflowTests(unittest.TestCase):
    def test_every_visible_h3_workflow_uses_recommended_turbo_path(self):
        for name in VISIBLE_WORKFLOWS:
            with self.subTest(workflow=name):
                workflow = json.loads((H3_DIR / name).read_text(encoding="utf-8"))
                nodes = workflow["nodes"]
                loras = [node for node in nodes if node.get("type") == "LoraLoaderModelOnly" and node.get("properties", {}).get("dawasteh_h3_turbo")]
                self.assertEqual(len(loras), 1)
                self.assertEqual(loras[0]["widgets_values"], [LORA_NAME, 1.0])
                sigma = next(node for node in nodes if node["type"] == "MiniMaxH3SigmaShift")
                sampler = next(node for node in nodes if node["type"] == "KSamplerSelect")
                scheduler = next(node for node in nodes if node["type"] == "BasicScheduler")
                self.assertEqual(sigma["widgets_values"], [12.0, 4.0])
                self.assertEqual(sampler["widgets_values"], ["euler"])
                self.assertEqual(scheduler["widgets_values"][:2], ["beta", 8])
                marker = workflow["extra"]["dawasteh_h3_turbo_lora"]
                self.assertEqual(marker["sha256"], LORA_SHA256)
                self.assertEqual(marker["sampling"]["steps"], 8)

    def test_visible_model_path_runs_unet_to_lora_to_sigma(self):
        for name in VISIBLE_WORKFLOWS:
            workflow = json.loads((H3_DIR / name).read_text(encoding="utf-8"))
            nodes = {node["id"]: node for node in workflow["nodes"]}
            links = {link[0]: link for link in workflow["links"]}
            unet = next(node for node in nodes.values() if node["type"] == "UNETLoader" and "minimax_h3_" in node["widgets_values"][0])
            lora = next(node for node in nodes.values() if node.get("properties", {}).get("dawasteh_h3_turbo"))
            sigma = next(node for node in nodes.values() if node["type"] == "MiniMaxH3SigmaShift")
            unet_link = links[lora["inputs"][0]["link"]]
            sigma_link = links[sigma["inputs"][0]["link"]]
            self.assertEqual((unet_link[1], unet_link[3]), (unet["id"], lora["id"]))
            self.assertEqual((sigma_link[1], sigma_link[3]), (lora["id"], sigma["id"]))

    def test_complete_song_director_serializes_quality_turbo_defaults(self):
        workflow = json.loads((H3_DIR / DIRECTOR_WORKFLOW).read_text(encoding="utf-8"))
        director = next(node for node in workflow["nodes"] if node["type"] == "DaWH3MusicVideoDirector")
        values = director["widgets_values"]
        self.assertEqual(values[12], 8)
        self.assertEqual(values[31:35], [12.0, 4.0, "euler", "beta"])
        self.assertEqual(workflow["extra"]["dawasteh_h3_turbo_lora"]["lora_name"], LORA_NAME)

    def test_turbo_integrator_is_idempotent_on_release_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in (*VISIBLE_WORKFLOWS, DIRECTOR_WORKFLOW):
                (target / name).write_bytes((H3_DIR / name).read_bytes())
            self.assertEqual(integrate(target), [])


class H3PromptGuideWorkflowTests(unittest.TestCase):
    def test_generators_are_deterministic_and_release_managed(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = generate(Path(directory))
            self.assertEqual(len(paths), 2)
            for path in paths:
                self.assertEqual(path.read_bytes(), (PROMPT_DIR / path.name).read_bytes())

    def test_enhancers_embed_the_supplied_guides_and_output_contract(self):
        for enhancer in ENHANCERS:
            with self.subTest(mode=enhancer.name):
                workflow = json.loads((PROMPT_DIR / enhancer.output).read_text(encoding="utf-8"))
                by_id = {node["id"]: node for node in workflow["nodes"]}
                instruction = by_id[1]["widgets_values"][0]
                self.assertIn("OFFICIAL MINIMAX GUIDE", instruction)
                self.assertIn("Return only the finished MiniMax H3 prompt", instruction)
                self.assertIn("USER REQUEST", instruction)
                for guide in enhancer.guides:
                    self.assertIn(guide.read_text(encoding="utf-8").splitlines()[0], instruction)
                self.assertEqual(by_id[4]["widgets_values"], [r"Qwen\qwen3.5_4b_bf16.safetensors", "stable_diffusion", "default"])
                self.assertEqual(by_id[2]["widgets_values"][1], 4096)
                sanitizer = next(node for node in workflow["nodes"] if node["type"] == "RegexReplace")
                regex_values = sanitizer["widgets_values"]
                cleaned = re.sub(
                    regex_values[1], regex_values[2], "[Shot 1] At 00:00.000, A woman walks.",
                    count=regex_values[6], flags=re.IGNORECASE | re.MULTILINE,
                )
                self.assertEqual(cleaned, "[Shot 1] A woman walks.")
                marker = workflow["extra"]["dawasteh_h3_prompt_guide"]
                self.assertEqual(len(marker["guides"]), len(enhancer.guides))
                self.assertEqual(marker["output_contract"], "final prompt only")


if __name__ == "__main__":
    unittest.main()
