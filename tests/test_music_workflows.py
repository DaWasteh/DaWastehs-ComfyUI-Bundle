from __future__ import annotations

import json
import math
import re
import unittest
from pathlib import Path


ROOT = Path("workflows") / "Music Generation"
COT_PATH = ROOT / "YuE_7B_FP16-Tags+Lyrics-to-Song.json"
ICL_PATH = ROOT / "YuE_7B_ICL_FP16-Voice+Lyrics-to-Song.json"
HEART_PATH = ROOT / "HeartMuLa_3B_HappyNewYear-Tags+Lyrics-to-Song.json"
YUE_INT8_PATH = ROOT / "YuE_7B_INT8-Tags+Lyrics-to-Song.json"
ACE_INT8_PATH = ROOT / "ACE_Step1_5_XL_SFT_INT8-Tags+Lyrics-to-Song.json"
STABLE_INT8_PATH = ROOT / "StableAudio3_Medium_INT8+Qwen3_5_2B-Text-to-Audio.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def nodes(workflow: dict) -> dict[int, dict]:
    return {node["id"]: node for node in workflow["nodes"]}


def lyric_sections(text: str) -> list[tuple[str, str]]:
    return re.findall(r"\[(\w+)\](.*?)(?=\[|\Z)", text, re.DOTALL)


class MusicWorkflowTests(unittest.TestCase):
    def test_both_yue_workflows_have_exact_duration_capacity(self):
        for path in (COT_PATH, ICL_PATH):
            with self.subTest(workflow=path.name):
                workflow = load(path)
                values = nodes(workflow)[2]["widgets_values"]
                parsed_sections = len(lyric_sections(values[1]))
                required_sections = math.ceil(values[5] * 100 / values[9])

                self.assertEqual(values[3], "randomize")  # seed UI state; prevents index drift
                self.assertEqual(parsed_sections, 20)
                self.assertEqual(values[4], 20)  # maximum enabled lyric sections
                self.assertEqual(values[5], 540.0)  # target duration
                self.assertEqual(values[9], 3000)  # 30 seconds/section at 100 codec IDs/s
                self.assertLessEqual(required_sections, min(values[4], parsed_sections))
                self.assertGreaterEqual(values[4] * values[9], 600 * 100)

        cot_values = nodes(load(COT_PATH))[2]["widgets_values"]
        self.assertFalse(cot_values[10])  # dual-track prompt
        self.assertFalse(cot_values[11])  # single-track audio prompt

    def test_yue_icl_uses_reference_audio_and_icl_checkpoint(self):
        workflow = load(ICL_PATH)
        by_id = nodes(workflow)
        self.assertTrue(by_id[1]["widgets_values"][0].endswith("YuE-s1-7B-anneal-en-icl"))
        self.assertEqual(by_id[13]["type"], "LoadAudio")
        self.assertEqual(by_id[13]["outputs"][0]["links"], [6])
        reference_input = by_id[2]["inputs"][1]
        self.assertEqual(
            {key: reference_input[key] for key in ("name", "type", "link")},
            {"name": "reference_audio", "type": "AUDIO", "link": 6},
        )
        self.assertFalse(by_id[2]["widgets_values"][10])
        self.assertTrue(by_id[2]["widgets_values"][11])
        self.assertIn("Ohne Input-Voice", by_id[8]["widgets_values"][0])
        self.assertEqual(sum(node["type"] == "PixaromaRunTimer" for node in workflow["nodes"]), 1)

    def test_heartmula_documents_context_limit_and_no_fake_reference(self):
        workflow = load(HEART_PATH)
        by_id = nodes(workflow)
        self.assertEqual(by_id[3]["widgets_values"][2], 300.0)
        self.assertNotIn("reference_audio", {item["name"] for item in by_id[3]["inputs"]})
        documentation = by_id[14]["widgets_values"][0]
        self.assertIn("keinen Audio-Encoder-Eingang", documentation)
        self.assertIn("bis 600 Sekunden", documentation)
        self.assertIn("`29.76` Sekunden", documentation)

    def test_int8_music_workflows_use_real_quantized_models(self):
        yue = load(YUE_INT8_PATH)
        yue_nodes = nodes(yue)
        self.assertEqual(yue_nodes[1]["widgets_values"][2], "int8")
        self.assertTrue(yue_nodes[1]["widgets_values"][0].endswith("YuE-s1-7B-anneal-en-cot-int8"))
        self.assertTrue(yue_nodes[3]["widgets_values"][0].endswith("YuE-s2-1B-general-int8"))

        ace = load(ACE_INT8_PATH)
        ace_loader = nodes(ace)[104]
        self.assertEqual(
            ace_loader["widgets_values"],
            ["ACE\\acestep_v1.5_xl_sft_int8_convrot.safetensors", "default"],
        )
        self.assertIn("hrktxz/ACE_Step_1.5_ComfyUI_int8_convrot", ace_loader["properties"]["models"][0]["url"])

        stable = load(STABLE_INT8_PATH)
        subgraph = stable["definitions"]["subgraphs"][0]
        stable_loader = nodes(subgraph)[25]
        self.assertEqual(
            stable_loader["widgets_values"][0],
            "StableAudio\\stable_audio_3_medium_int8_convrot.safetensors",
        )
        self.assertNotIn("models", stable_loader["properties"])
        self.assertIn("192 DiT-Linear-Layer", nodes(stable)[56]["widgets_values"][0])

        for workflow in (yue, ace, stable):
            self.assertEqual(sum(node["type"] == "PixaromaRunTimer" for node in workflow["nodes"]), 1)

    def test_distributable_custom_node_patches_include_required_guards(self):
        yue_patch = Path("tools/patches/ComfyUI_YuE-Windows-RDNA4-longform-ICL.patch").read_text(
            encoding="utf-8"
        )
        heart_patch = Path("tools/patches/ComfyUI-HeartMuLa-600s-context.patch").read_text(
            encoding="utf-8"
        )
        for token in (
            "target_duration_seconds",
            "min_new_tokens=segment_new_tokens",
            '"reference_audio": ("AUDIO",)',
            "YuE audio/reference prompting requires an ICL Stage-1 checkpoint",
            "Keeping pre-dispatched",
            "Skipping unsupported CPU offload",
        ):
            self.assertIn(token, yue_patch)
        self.assertIn('max=600.0', heart_patch)
        self.assertIn("validate_duration_context", heart_patch)
        self.assertNotIn("decode_duration", heart_patch)


if __name__ == "__main__":
    unittest.main()
