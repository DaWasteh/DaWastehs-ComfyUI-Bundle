"""v1.2.8 DaWasteh VisionTools pack: mask guard and 16-bit depth conversion (pure helpers, no ComfyUI import)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-VisionTools"


def helpers():
    spec = importlib.util.spec_from_file_location("vision_helpers_under_test", PACK / "helpers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MaskGuardTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_empty_and_faint_masks_stop_with_the_german_hint(self):
        for mask in (np.zeros((1, 64, 64), np.float32), np.full((1, 64, 64), 0.5, np.float32)):
            with self.assertRaises(ValueError) as caught:
                self.h.require_mask(mask, 16)
            self.assertIn("Keine Maske gemalt", str(caught.exception))
            self.assertIn("MASKE MALEN", str(caught.exception))

    def test_threshold_counts_only_painted_pixels(self):
        mask = np.zeros((1, 64, 64), np.float32)
        mask[0, :3, :5] = 1.0       # 15 painted pixels
        with self.assertRaises(ValueError):
            self.h.require_mask(mask, 16)
        mask[0, 3, 0] = 0.6         # 16th pixel, above 0.5
        self.assertEqual(self.h.require_mask(mask, 16), 16)
        self.assertEqual(self.h.require_mask(mask, 0), 16)   # min_pixels is clamped to 1

    def test_blurred_mask_edges_still_count(self):
        mask = np.zeros((1, 32, 32), np.float32)
        mask[0, 8:24, 8:24] = np.linspace(0.4, 1.0, 16, dtype=np.float32)[None, :]
        self.assertEqual(self.h.mask_pixels(mask), int((mask > 0.5).sum()))


class Depth16Tests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_full_range_rounding_and_clipping(self):
        image = np.stack([np.array([[-0.2, 0.0, 0.5, 1.0, 1.3]], np.float32)] * 3, axis=-1)
        gray = self.h.to_uint16_gray(image)
        self.assertEqual(gray.dtype, np.uint16)
        self.assertEqual(gray.tolist(), [[0, 0, 32768, 65535, 65535]])

    def test_sixteen_bit_keeps_steps_that_eight_bit_merges(self):
        ramp = np.linspace(0.0, 1.0, 4096, dtype=np.float32).reshape(64, 64, 1).repeat(3, axis=2)
        self.assertEqual(len(np.unique(self.h.to_uint16_gray(ramp))), 4096)
        self.assertEqual(len(np.unique(np.clip(ramp[..., 0] * 255.0, 0, 255).astype(np.uint8))), 256)

    def test_nan_and_wrong_shapes(self):
        self.assertEqual(self.h.to_uint16_gray(np.array([[np.nan]], np.float32)).tolist(), [[0]])
        with self.assertRaises(ValueError):
            self.h.to_uint16_gray(np.zeros((2, 4, 4, 3), np.float32))


class FakeBatchManager:
    def __init__(self, frames_per_batch=64):
        self.frames_per_batch, self.inputs, self.outputs, self.unique_id, self.resets = frames_per_batch, {}, {}, None, 0

    def reset(self):
        self.resets += 1
        self.inputs, self.outputs, self.unique_id = {}, {}, None


class StaleMetaBatchTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()
        self.prompt = {"4": {"class_type": "DaWLoadVideoBatches", "inputs": {"meta_batch": ["3", 0]}},
                       "3": {"class_type": "VHS_BatchManager", "inputs": {"frames_per_batch": 64}}}

    def test_fresh_run_closes_what_a_cancelled_run_left_open(self):
        manager = FakeBatchManager()
        manager.inputs["4"] = ("old generator",)
        manager.outputs["9"] = (1, "old ffmpeg writer")
        self.assertTrue(self.h.reset_stale_meta_batch(manager, self.prompt, "4"))
        self.assertEqual((manager.resets, manager.inputs, manager.outputs), (1, {}, {}))
        self.assertEqual((manager.frames_per_batch, manager.unique_id), (64, "3"))

    def test_requeued_prompts_and_clean_state_are_left_alone(self):
        manager = FakeBatchManager()
        manager.inputs["4"] = ("running generator",)
        requeued = {**self.prompt, "3": {"class_type": "VHS_BatchManager", "inputs": {"frames_per_batch": 64, "requeue": 2}}}
        self.assertFalse(self.h.reset_stale_meta_batch(manager, requeued, "4"))
        self.assertFalse(self.h.reset_stale_meta_batch(FakeBatchManager(), self.prompt, "4"))
        self.assertFalse(self.h.reset_stale_meta_batch(None, self.prompt, "4"))
        self.assertFalse(self.h.reset_stale_meta_batch(manager, {"4": {"inputs": {}}}, "4"))
        self.assertEqual(manager.resets, 0)


class PoseBoxTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_standing_person_gets_a_3_by_4_box_with_margin(self):
        box = {"x": 400.0, "y": 100.0, "width": 100.0, "height": 400.0, "label": "person", "score": 0.9}
        out = self.h.expand_pose_boxes([[box]], 1280, 720)[0][0]
        self.assertAlmostEqual(out["height"], 500.0)
        self.assertAlmostEqual(out["width"] / out["height"], 0.75)
        self.assertAlmostEqual(out["x"] + out["width"] / 2, 450.0)
        self.assertAlmostEqual(out["y"] + out["height"] / 2, 300.0)
        self.assertEqual((out["label"], out["score"]), ("person", 0.9))

    def test_wide_boxes_grow_in_height_and_edges_are_clipped(self):
        wide = self.h.expand_pose_boxes({"x": 0.0, "y": 600.0, "width": 800.0, "height": 100.0}, 1280, 720)
        self.assertEqual((wide["x"], wide["y"]), (0.0, 0.0))
        self.assertLessEqual(wide["x"] + wide["width"], 1280.0)
        self.assertLessEqual(wide["y"] + wide["height"], 720.0)
        self.assertEqual(self.h.expand_pose_boxes([[], []], 64, 64), [[], []])


class PackLayoutTests(unittest.TestCase):
    def test_v3_entrypoint_and_node_ids(self):
        source = (PACK / "nodes.py").read_text(encoding="utf-8")
        for node_id in ("DaWRequireMask", "DaWSaveDepth16", "DaWLoadVideoBatches", "DaWPoseBoxes"):
            self.assertIn(f'node_id="{node_id}"', source)
        self.assertIn("comfy_entrypoint", (PACK / "__init__.py").read_text(encoding="utf-8"))
        self.assertIn("must stay inside ComfyUI/output", source)


if __name__ == "__main__":
    unittest.main()
