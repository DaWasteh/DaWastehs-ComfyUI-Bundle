"""v1.2.10: Qwen Image 2.1 edit graphs cap camera photos in the loader instead of VAE-encoding 45 MP (GPU crash)."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest

from tools import build_qwen_image21_background_removal_v124 as v124
from tools.build_qwen_image21_workflows import LOAD_CAP_STATE, PATHS, ROOT, build_all

COMFY = Path(os.environ.get("COMFYUI_PATH", "L:/ComfyUI/ComfyUI"))
PIXAROMA_RESIZE = COMFY / "custom_nodes/ComfyUI-Pixaroma/nodes/_resize_helpers.py"
REPORT = ROOT / "performance/rdna4/qwen-image21-camera-photo-v1210-validation.json"
EDIT, REMOVER = PATHS["image_edit"], v124.PATH


def loaders(workflow):
    return [n for n in workflow["nodes"] if n["type"] == "PixaromaLoadImage"]


class LoaderCapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {**build_all(), **v124.build_all()}

    def test_every_qwen21_reference_loader_shrinks_only(self):
        self.assertEqual(LOAD_CAP_STATE["mode"], "max_mp")
        self.assertEqual(LOAD_CAP_STATE["max_mp"], 4.0)          # 2048², the model's native 2K budget
        self.assertIs(LOAD_CAP_STATE["allow_upscale"], False)     # small images stay byte-identical
        self.assertEqual(LOAD_CAP_STATE["snap"], 32)             # TextEncodeQwenImage21 grid: no second resize
        for path in (EDIT, REMOVER):
            found = loaders(self.workflows[path])
            self.assertEqual(len(found), 2 if path == EDIT else 1, path)
            for load in found:
                self.assertEqual(json.loads(load["properties"]["loadImagePixState"]), LOAD_CAP_STATE, path)
            encoder = next(n for n in self.workflows[path]["nodes"] if n["type"] == "TextEncodeQwenImage21")
            self.assertEqual(encoder["widgets_values"][2], 0)

    def test_notes_warn_against_switching_the_cap_off(self):
        for path in (EDIT, REMOVER):
            text = json.dumps(self.workflows[path], ensure_ascii=False)
            self.assertIn("4 MP (2048²", text, path)
            self.assertIn("hipErrorLaunchFailure", text, path)


@unittest.skipUnless(PIXAROMA_RESIZE.is_file(), "needs the installed ComfyUI-Pixaroma pack")
class PixaromaResizeTests(unittest.TestCase):
    """Runs Pixaroma's own resize code with the shipped state (it only needs PIL)."""

    @classmethod
    def setUpClass(cls):
        from PIL import Image
        spec = importlib.util.spec_from_file_location("pixaroma_resize_helpers", PIXAROMA_RESIZE)
        cls.helpers = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.helpers)
        cls.Image = Image

    def resize(self, width, height, pixels=None):
        rgb = pixels or self.Image.new("RGB", (8, 8))
        return self.helpers._resize_frame(rgb, self.Image.new("L", rgb.size), dict(LOAD_CAP_STATE), width, height)

    def test_45_mp_camera_photo_becomes_2k_on_the_encoder_grid(self):
        _, _, w, h = self.resize(5464, 8192)  # Canon JPG 8192x5464 after EXIF rotation (orientation 8)
        self.assertEqual((w, h), (1664, 2496))
        self.assertLessEqual(w * h, 2048 * 2048)
        # TextEncodeQwenImage21 at resolution 0 rounds to multiples of 32: same size, so it does not resize again
        self.assertEqual((round(w / 32) * 32, round(h / 32) * 32), (w, h))

    def test_images_within_the_budget_pass_through_untouched(self):
        for size in ((896, 1152), (1024, 1024), (2048, 2048), (512, 512)):
            image = self.Image.new("RGB", size)
            out, _, w, h = self.resize(*size, pixels=image)
            self.assertIs(out, image, size)
            self.assertEqual((w, h), size)


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.2.10 GPU run")
class LiveEvidenceTests(unittest.TestCase):
    def test_report_pins_the_shipped_files_and_the_camera_photo_run(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        for path in (EDIT, REMOVER):
            digest = hashlib.sha256((ROOT / "workflows" / path).read_bytes()).hexdigest()
            self.assertEqual(report["workflows"]["workflows/" + path], digest, path)
        for entry in report["sources"]:
            self.assertEqual(hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest(), entry["sha256"], entry["path"])
        runs ={r["case"]: r for r in report["runs"]}
        self.assertEqual(set(runs), {"edit_default", "remover_default", "edit_camera_photo_45mp", "remover_camera_photo_45mp"})
        for run in runs.values():
            self.assertEqual((run["status"], run["steps"]), ("success", 25), run["case"])
            self.assertTrue(run["executed_contract_matches_final"], run["case"])
        for case in ("edit_camera_photo_45mp", "remover_camera_photo_45mp"):
            self.assertEqual((runs[case]["input"]["width"], runs[case]["input"]["height"]), (5464, 8192))
            out = runs[case]["outputs"][0]
            self.assertEqual((out["width"], out["height"]), (1664, 2496), case)
        edit = runs["edit_default"]["outputs"][0]
        self.assertEqual((edit["width"], edit["height"]), (896, 1152))  # official example: loader leaves it alone


if __name__ == "__main__":
    unittest.main()
