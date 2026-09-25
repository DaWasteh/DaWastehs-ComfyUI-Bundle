"""v1.2.4 Qwen Image 2.1 background remover: official template, flat graph, pinned sources and real-run evidence."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_qwen_image21_background_removal_v124 import build_all, PATH, SOURCES, ROOT, TEMPLATE, MODEL, CLIP, VAE
from tools.rodent_layout import _topology_hash
from tools.validate_workflows import validate_graph

REPORT = ROOT / "performance/rdna4/qwen-image21-background-removal-v124-validation.json"


def nodes(workflow, kind):
    return [n for n in workflow["nodes"] if n["type"] == kind]


def source(workflow, target, name):
    slot = next(i for i, s in enumerate(target["inputs"]) if s["name"] == name)
    link = next(l for l in workflow["links"] if l[3:5] == [target["id"], slot])
    return next(n for n in workflow["nodes"] if n["id"] == link[1]), link[2]


class BackgroundRemoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = build_all()[PATH]

    def test_rebuild_is_exact_and_lf_only(self):
        self.assertEqual(build_all()[PATH], self.workflow)
        self.assertEqual(json.loads((ROOT / "workflows" / PATH).read_text(encoding="utf-8")), self.workflow)
        from tools import build_qwen_image21_background_removal_v124 as builder
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "ROOT", Path(directory)):
            builder.main()
            data = (Path(directory) / "workflows" / PATH).read_bytes()
        self.assertNotIn(b"\r\n", data)
        self.assertEqual(data, (ROOT / "workflows" / PATH).read_bytes())

    def test_flat_valid_rodent_timer_and_connected_gpu_control(self):
        errors = []
        validate_graph(Path(PATH), "root", self.workflow, errors)
        self.assertEqual(errors, [])
        self.assertFalse(self.workflow.get("definitions", {}).get("subgraphs"))
        self.assertEqual(self.workflow["extra"]["dawasteh_rodent_layout"]["topology_sha256"], _topology_hash(self.workflow))
        self.assertEqual(len(nodes(self.workflow, "PixaromaRunTimer")), 1)
        control = nodes(self.workflow, "DaWMultiGPUDeviceControl")
        self.assertEqual(len(control), 1)
        self.assertEqual(control[0]["widgets_values"], ["gpu:0"] * 3)
        for kind in ("SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"):
            selector = nodes(self.workflow, kind)[0]
            self.assertEqual(source(self.workflow, selector, "device")[0]["type"], "DaWMultiGPUDeviceControl")

    def test_official_instruction_models_and_sampler(self):
        template = json.loads((SOURCES / TEMPLATE).read_text(encoding="utf-8"))
        official = next(n for n in template["nodes"] if n["id"] == 459)["widgets_values"]
        prompt = next(n for n in nodes(self.workflow, "PixaromaPrompt") if n["title"].startswith("ANWEISUNG"))
        self.assertEqual(prompt["properties"]["promptState"]["text"], official[1])
        self.assertEqual(official[1], "Remove the background, and output a PNG image")
        self.assertEqual(nodes(self.workflow, "UNETLoader")[0]["widgets_values"], [MODEL, "default"])
        self.assertEqual(nodes(self.workflow, "CLIPLoader")[0]["widgets_values"], [CLIP, "qwen_image", "default"])
        self.assertEqual(nodes(self.workflow, "VAELoader")[0]["widgets_values"], [VAE])
        sampler = nodes(self.workflow, "KSampler")[0]
        self.assertEqual(sampler["widgets_values"], [0, "fixed", 25, 1.0, "euler", "simple", 1.0])
        encoder = nodes(self.workflow, "TextEncodeQwenImage21")[0]
        self.assertEqual(encoder["widgets_values"][2], 0)  # keep the input format (32 px grid)
        self.assertEqual(source(self.workflow, sampler, "latent_image"), (encoder, 2))
        load, _ = source(self.workflow, encoder, "images.image_1")
        self.assertEqual((load["type"], load["mode"]), ("PixaromaLoadImage", 0))
        self.assertEqual(json.loads(load["properties"]["loadImagePixState"])["mode"], "off")
        self.assertEqual(nodes(self.workflow, "QwenImage21Cache")[0]["widgets_values"], ["auto", "default"])

    def test_rgba_png_mask_png_and_compare(self):
        decode = nodes(self.workflow, "VAEDecode")[0]
        saves = {json.loads(n["properties"]["saveImageState"])["pattern"]: n for n in nodes(self.workflow, "PixaromaSaveImage")}
        self.assertEqual(set(saves), {"Qwen_Image_2_1/BG_Removed_%counter%", "Qwen_Image_2_1/BG_Mask_%counter%"})
        for save in saves.values():
            state = json.loads(save["properties"]["saveImageState"])
            self.assertEqual((state["format"], state["embedWorkflow"], state["saveOnRun"]), ("png", True, True))
        self.assertEqual(source(self.workflow, saves["Qwen_Image_2_1/BG_Removed_%counter%"], "images")[0]["id"], decode["id"])
        mask_image, _ = source(self.workflow, saves["Qwen_Image_2_1/BG_Mask_%counter%"], "images")
        invert, _ = source(self.workflow, mask_image, "mask")
        split, slot = source(self.workflow, invert, "mask")
        self.assertEqual((mask_image["type"], invert["type"], split["type"], slot), ("MaskToImage", "InvertMask", "SplitImageWithAlpha", 1))
        self.assertEqual(source(self.workflow, split, "image")[0]["id"], decode["id"])
        compare = nodes(self.workflow, "PixaromaCompare")[0]
        self.assertEqual(source(self.workflow, compare, "image1")[0]["type"], "PixaromaLoadImage")
        self.assertEqual(source(self.workflow, compare, "image2")[0]["id"], decode["id"])
        self.assertIn("Research", json.dumps(self.workflow))

    def test_pinned_template_and_public_example_input(self):
        for item in json.loads((SOURCES / "sources.json").read_text(encoding="utf-8")):
            self.assertEqual(hashlib.sha256((SOURCES / item["file"]).read_bytes()).hexdigest(), item["sha256"])
            self.assertRegex(item["url"], r"/blob/[a-f0-9]{40}/templates/")
        inputs = json.loads((SOURCES / "inputs.json").read_text(encoding="utf-8"))
        self.assertEqual([i["file"] for i in inputs], ["angry_broccoli.png"])
        self.assertRegex(inputs[0]["url"], r"https://raw.githubusercontent.com/Comfy-Org/workflow_templates/[a-f0-9]{40}/input/")
        self.assertEqual(nodes(self.workflow, "PixaromaLoadImage")[0]["widgets_values"][0], "angry_broccoli.png")


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.2.4 GPU run")
class LiveEvidenceTests(unittest.TestCase):
    def test_report_describes_the_shipped_file_and_real_alpha(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["workflow"]["sha256"], hashlib.sha256((ROOT / "workflows" / PATH).read_bytes()).hexdigest())
        cases = {r["case"]: r for r in report["runs"]}
        self.assertIn("default", cases)
        self.assertTrue(cases["default"]["executed_contract_matches_final"])
        # Documented limitation: the official instruction treats a whole collage as background; the START note's
        # collage instruction fixes it on the same image.
        empty = cases["character_sheet_local"]["outputs"]
        self.assertLessEqual(next(o for o in empty if o["kind"] == "removed")["alpha_max"], 8)
        for run in report["runs"]:
            self.assertEqual((run["status"], run["steps"]), ("success", 25))
            cut = next(o for o in run["outputs"] if o["kind"] == "removed")
            self.assertEqual(cut["mode"], "RGBA")
            self.assertTrue(cut["workflow_metadata_matches"])
            if run["case"] == "character_sheet_local":
                continue
            self.assertEqual((cut["alpha_min"], cut["alpha_max"]), (0, 255))
            self.assertGreater(cut["alpha_below_128_fraction"], 0.2)   # background actually removed
            self.assertLess(cut["alpha_below_128_fraction"], 0.95)     # subject kept
            mask = next(o for o in run["outputs"] if o["kind"] == "mask")
            self.assertEqual((mask["width"], mask["height"]), (cut["width"], cut["height"]))


if __name__ == "__main__":
    unittest.main()
