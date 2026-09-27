"""v1.2.9 DaWasteh Ming Image pack: buckets, prompt writer logic and layer output (pure helpers, no ComfyUI import)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MingImage"
SOURCES = ROOT / "tools" / "workflow_templates" / "v129"


def helpers():
    spec = importlib.util.spec_from_file_location("ming_helpers_under_test", PACK / "helpers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def official_process_ratio(ori_h, ori_w, table):
    """Reference implementation of Ming-Image bailingmm_utils.get_closest_ratio (keys are h/w)."""
    ratio = ori_h / ori_w
    key = min(table.keys(), key=lambda k: abs(float(k) - ratio))
    return tuple(table[key])


class BucketTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_matches_the_official_closest_ratio_rule(self):
        for bucket, table in ((1024, self.h.ASPECT_RATIO_1024), (512, self.h.ASPECT_RATIO_512)):
            for height, width in ((1024, 1024), (1080, 1920), (1920, 1080), (768, 512), (3000, 2000), (500, 2000), (4000, 900)):
                self.assertEqual(self.h.bucket_size(height, width, bucket), official_process_ratio(height, width, table))

    def test_known_sizes_and_32px_grid(self):
        self.assertEqual(self.h.bucket_size(1024, 1024, 1024), (1024, 1024))
        self.assertEqual(self.h.bucket_size(1080, 1920, 1024), (720, 1280))
        self.assertEqual(self.h.bucket_size(512, 768, 512), (416, 608))    # h/w 0.667 -> key 0.68
        for table in (self.h.ASPECT_RATIO_512, self.h.ASPECT_RATIO_1024):
            for h, w in table.values():
                self.assertEqual((h % 16, w % 16), (0, 0))   # EmptyQwenImageLayeredLatentImage steps in 16 px

    def test_rejects_empty_images(self):
        with self.assertRaises(ValueError):
            self.h.bucket_size(0, 10, 1024)


class PromptWriterTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()
        self.t2i_system = (PACK / "prompts" / "t2i_rewriter_system_prompt.txt").read_text(encoding="utf-8")
        self.layer_template = (PACK / "prompts" / "layer_guided_prompt.txt").read_text(encoding="utf-8")
        self.calls = []

    def resolve(self, task, text, enhance=True, layers=4, answer=None, **kw):
        def rewrite(user, system, accept):
            self.calls.append((user, system))
            return answer if answer is not None and accept(answer) else None
        return self.h.resolve_prompt(task, text, enhance, layers, rewrite=rewrite, t2i_system=self.t2i_system,
                                     layer_template=self.layer_template, **kw)

    def test_official_prompt_files_are_pinned(self):
        pinned = {Path(e["file"]).name: e["sha256"] for e in json.loads((SOURCES / "sources.json").read_text(encoding="utf-8"))}
        for name in ("t2i_rewriter_system_prompt.txt", "layer_guided_prompt.txt"):
            data = (PACK / "prompts" / name).read_bytes()
            self.assertNotIn(b"\r\n", data)
            self.assertEqual(hashlib.sha256(data).hexdigest(), pinned[name])
        self.assertEqual(self.layer_template.count("{spec}"), 1)
        self.assertTrue(self.t2i_system.startswith("You are a senior visual designer"))
        self.assertIn("MIT License", (PACK / "prompts" / "LICENSE-Ming-Image.txt").read_text(encoding="utf-8"))

    def test_design_uses_the_json_caption_and_tells_the_canvas(self):
        caption = {"canvas_settings": {"aspect_ratio": "1:1"}, "layers": [{"description": "x"}]}
        prompt, _ = self.resolve("design", "Poster \"SEEFEST\"", answer="```json\n" + json.dumps(caption) + "\n```",
                                 width=2048, height=2048)
        self.assertEqual(json.loads(prompt), caption)
        user, system = self.calls[0]
        self.assertEqual(system, self.t2i_system)
        self.assertTrue(user.startswith("Poster \"SEEFEST\""))
        self.assertIn("Canvas: 2048 × 2048 px, aspect ratio 1:1.", user)

    def test_design_falls_back_to_the_text_without_usable_json(self):
        prompt, _ = self.resolve("design", "  A poster  ", answer="not json")
        self.assertEqual(prompt, "A poster")
        prompt, _ = self.resolve("design", "A poster", enhance=False, answer="{}")
        self.assertEqual(prompt, "A poster")
        self.assertEqual(len(self.calls), 1)   # enhance off never starts the LLM
        with self.assertRaises(ValueError):
            self.resolve("design", "   ")

    def test_transparent_prefix_is_first_and_single(self):
        caption = json.dumps({"canvas_settings": {}, "layers": []})
        prompt, _ = self.resolve("transparent", "A fox sticker", answer=caption)
        self.assertTrue(prompt.startswith(self.h.ALPHA_PREFIX + "\n{"))
        self.assertIn(self.h.ALPHA_HINT, self.calls[0][0])
        prompt, _ = self.resolve("transparent", "A fox sticker", enhance=False)
        self.assertEqual(prompt, self.h.ALPHA_PREFIX + "\nA fox sticker")
        self.assertEqual(self.h.with_alpha_prefix(prompt), prompt)

    def test_layers_without_enhancer_use_the_official_default_request(self):
        prompt, count = self.resolve("layers", "", enhance=False, layers=5)
        self.assertEqual((prompt, count), ("Decompose this image into 5 layers.", 5))
        prompt, count = self.resolve("layers", "Layer 1: text\nLayer 2: background", enhance=False, layers=2)
        self.assertEqual(prompt, "Decompose this image into 2 layers.\nLayer 1: text\nLayer 2: background")
        official = (ROOT / "tools/workflow_templates/v129/layer_decompose_5layers.txt")
        if official.is_file():
            text = official.read_text(encoding="utf-8")
            self.assertEqual(self.resolve("layers", text, enhance=False, layers=2), (text, 5))

    def test_layers_enhancer_count_comes_from_the_specification(self):
        answer = ("Decompose this image into 3 layers with the following specifications:\n\nNumber of layers: 3\n"
                  "Layer 1: \"SALE\" in red.\nLayer 2: white card.\nLayer 3: blue background.")
        prompt, count = self.resolve("layers", "text, card, background", layers=6, answer=answer, has_image=True)
        self.assertEqual((prompt, count), (answer, 3))
        user, system = self.calls[0]
        self.assertIsNone(system)
        self.assertIn("Decompose this image into 6 layers.\ntext, card, background", user)
        self.assertNotIn("{spec}", user)
        # the enhancer needs the image; without one the plan is used as it is
        self.calls.clear()
        prompt, count = self.resolve("layers", "", layers=2, answer=answer, has_image=False)
        self.assertEqual((prompt, count, self.calls), ("Decompose this image into 2 layers.", 2, []))

    def test_layer_answers_must_be_complete(self):
        good = "Number of layers: 2\nLayer 1: a\nLayer 2: b"
        self.assertTrue(self.h.valid_layer_answer(good))
        self.assertFalse(self.h.valid_layer_answer("Number of layers: 3\nLayer 1: a\nLayer 2: b"))   # truncated
        self.assertFalse(self.h.valid_layer_answer("Layer 1: a"))
        self.assertFalse(self.h.valid_layer_answer("Number of layers: 13\n" + "\n".join(f"Layer {i}: x" for i in range(1, 14))))
        with self.assertRaises(ValueError):
            self.resolve("layers", "Decompose this image into 20 layers.", enhance=False)

    def test_retry_with_seed_plus_1000(self):
        seeds = []

        def generate(seed):
            seeds.append(seed)
            return "bad" if seed == 7 else "```\ngood\n```"
        answer, rejected = self.h.first_accepted(generate, lambda out: out == "good", 7)
        self.assertEqual((answer, rejected, seeds), ("good", ["bad"], [7, 1007]))
        answer, rejected = self.h.first_accepted(lambda seed: "bad", lambda out: out == "good", 0)
        self.assertEqual((answer, rejected), (None, ["bad", "bad"]))

    def test_canvas_note(self):
        self.assertEqual(self.h.canvas_note(0, 1024), "")
        self.assertEqual(self.h.canvas_note(1280, 720), "\n\nCanvas: 1280 × 720 px, aspect ratio 16:9.")
        self.assertEqual(self.h.canvas_note(1664, 928), "\n\nCanvas: 1664 × 928 px, aspect ratio 1.79:1.")


class LayerOutputTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_split_drops_the_composite_and_keeps_order(self):
        frames = np.zeros((4, 8, 8, 4), np.float32)
        for i in range(4):
            frames[i, ..., 0] = i / 4
        composite, layers = self.h.split_layer_frames(frames)
        self.assertEqual(composite[0, 0, 0], 0.0)
        self.assertEqual([float(layer[0, 0, 0]) for layer in layers], [0.25, 0.5, 0.75])
        rgb_composite, rgb_layers = self.h.split_layer_frames(np.ones((2, 4, 4, 3), np.float32))
        self.assertEqual(rgb_layers.shape, (1, 4, 4, 4))
        self.assertTrue(np.all(rgb_layers[..., 3] == 1.0))
        with self.assertRaises(ValueError):
            self.h.split_layer_frames(np.ones((1, 4, 4, 4), np.float32))

    def test_recomposite_front_layer_wins(self):
        background = np.zeros((4, 4, 4), np.float32)
        background[..., 2] = 1.0
        background[..., 3] = 1.0
        front = np.zeros((4, 4, 4), np.float32)
        front[:2, :, 0] = 1.0
        front[:2, :, 3] = 1.0
        out = self.h.composite_layers(np.stack([front, background]))
        self.assertTrue(np.allclose(out[0, 0], [1, 0, 0]))
        self.assertTrue(np.allclose(out[3, 0], [0, 0, 1]))
        empty = np.zeros((1, 2, 2, 4), np.float32)
        self.assertTrue(np.allclose(self.h.composite_layers(empty), 1.0))   # nothing -> white

    def test_alpha_fallback_keeps_real_alpha_and_otherwise_uses_the_mask(self):
        rgba = np.ones((32, 32, 4), np.float32)
        mask = np.zeros((32, 32), np.float32)
        mask[8:24, 8:24] = 1.0
        out, source = self.h.alpha_or_mask(rgba, mask)             # opaque Ming output -> BiRefNet mask
        self.assertEqual(source, "mask")
        self.assertTrue(np.array_equal(out[..., 3], mask))
        self.assertTrue(np.array_equal(out[..., :3], rgba[..., :3]))
        own = rgba.copy()
        own[:4, :, 3] = 0.0                                          # 12.5 % transparent from the model itself
        out, source = self.h.alpha_or_mask(own, mask)
        self.assertEqual(source, "ming")
        self.assertTrue(np.array_equal(out, own))
        self.assertEqual(self.h.alpha_or_mask(rgba, None)[1], "opaque")
        self.assertEqual(self.h.alpha_or_mask(rgba[..., :3], mask)[0].shape, (32, 32, 4))
        with self.assertRaises(ValueError):
            self.h.alpha_or_mask(rgba, np.zeros((16, 16), np.float32))
        self.assertIn(self.h.ALPHA_PREFIX, ("transparent canvas, not white, not checkerboard",))

    def test_checkerboard_and_alpha_share(self):
        rgba = np.zeros((64, 64, 4), np.float32)
        rgba[:32, :, :3] = 0.2
        rgba[:32, :, 3] = 1.0
        preview = self.h.over_checkerboard(rgba)
        self.assertTrue(np.allclose(preview[:32], 0.2))
        self.assertEqual(len(np.unique(np.round(preview[32:, :, 0], 3))), 2)
        self.assertAlmostEqual(self.h.alpha_coverage(rgba), 0.5)
        self.assertEqual(self.h.alpha_coverage(rgba[..., :3]), 0.0)


class JsonPromptTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_schema_check(self):
        self.assertIsNone(self.h.json_prompt('{"layers": []}'))
        self.assertIsNone(self.h.json_prompt('{"canvas_settings": {}, "layers": [}'))    # truncated
        text = self.h.json_prompt('Here: {"canvas_settings": {"a": 1}, "layers": [{"description": "\\"SALE\\""}]} done')
        self.assertEqual(json.loads(text)["layers"][0]["description"], '"SALE"')
        self.assertTrue(re.match(r"^\{\n  \"canvas_settings\"", text))


if __name__ == "__main__":
    unittest.main()
