"""v1.2.9 workflows: Ming Image 0.1 Design text to image, transparent RGBA, image edit and Design-Layer decomposition."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_ming_image_workflows_v129 import (CLIP, CLIP_LAYER, PATHS, ROOT, SETTINGS, SOURCES, UNET, UNET_LAYER, VAE,
                                                   build_all)
from tools.rodent_layout import _topology_hash
from tools.validate_workflows import validate_graph

REPORT = ROOT / "performance/rdna4/ming-image-v129-validation.json"
BS = "\\"


def nodes(workflow, kind):
    return [n for n in workflow["nodes"] if n["type"] == kind]


def one(workflow, kind):
    found = nodes(workflow, kind)
    assert len(found) == 1, (kind, len(found))
    return found[0]


def source(workflow, target, name):
    slot = next(i for i, s in enumerate(target["inputs"]) if s["name"] == name)
    link = next(item for item in workflow["links"] if item[3:5] == [target["id"], slot])
    return next(n for n in workflow["nodes"] if n["id"] == link[1]), link[2]


def upstream(workflow, target, name, skip=("SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice")):
    """Source of an input, looking through the device selectors the v0.9.2 migration inserts after loaders."""
    node, slot = source(workflow, target, name)
    while node["type"] in skip:
        node, slot = source(workflow, node, {"SelectModelDevice": "model", "SelectCLIPDevice": "clip", "SelectVAEDevice": "vae"}[node["type"]])
    return node, slot


def sampler_values(settings):
    return [settings["seed"], "fixed", settings["steps"], settings["cfg"], settings["sampler_name"], settings["scheduler"],
            settings["denoise"]]


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = build_all()

    def test_rebuild_is_exact_and_lf_only(self):
        self.assertEqual(set(self.built), set(PATHS.values()))
        self.assertEqual(build_all(), self.built)
        from tools import build_ming_image_workflows_v129 as builder
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "ROOT", Path(directory)):
            builder.main()
            for path in PATHS.values():
                data = (Path(directory) / "workflows" / path).read_bytes()
                self.assertNotIn(b"\r\n", data)
                self.assertEqual(data, (ROOT / "workflows" / path).read_bytes(), path)

    def test_flat_valid_rodent_timer_and_one_gpu_control(self):
        for path, workflow in self.built.items():
            with self.subTest(path=path):
                errors = []
                validate_graph(Path(path), "root", workflow, errors)
                self.assertEqual(errors, [])
                self.assertFalse(workflow.get("definitions", {}).get("subgraphs"))
                self.assertEqual(workflow["extra"]["dawasteh_rodent_layout"]["topology_sha256"], _topology_hash(workflow))
                self.assertEqual(len(nodes(workflow, "PixaromaRunTimer")), 1)
                control = one(workflow, "DaWMultiGPUDeviceControl")
                self.assertEqual(control["widgets_values"], ["gpu:0"] * 3)
                self.assertEqual(workflow["extra"]["dawasteh_ming_image_v129"]["kind"],
                                 next(k for k, v in PATHS.items() if v == path))
                self.assertTrue(any(n["type"] == "MarkdownNote" and n["title"].startswith("START HIER") for n in workflow["nodes"]))

    def test_models_sampler_and_shift(self):
        for key, path in PATHS.items():
            w = self.built[path]
            layer = key == "layers"
            with self.subTest(key=key):
                # read-only mappings: the core loaders pushed 2048x2048 to 96.6 of 97.4 GB commit (77.3 GB read-only)
                self.assertFalse(nodes(w, "UNETLoader") or nodes(w, "CLIPLoader"))
                self.assertEqual(one(w, "DaWVUReadOnlyUNETLoader")["widgets_values"], [UNET_LAYER if layer else UNET, "default"])
                self.assertEqual(one(w, "DaWVUReadOnlyCLIPLoader")["widgets_values"],
                                 [CLIP_LAYER if layer else CLIP, "qwen_image", "default"])
                self.assertEqual(one(w, "VAELoader")["widgets_values"], [VAE])
                sampler = one(w, "KSampler")
                self.assertEqual(sampler["widgets_values"], sampler_values(SETTINGS["layer_sampler" if layer else "sampler"]))
                shift, _ = source(w, sampler, "model")
                # timestep multiplier 1 like Ming's own model sampling; ModelSamplingSD3 (x1000) produced pure noise
                self.assertEqual((shift["type"], shift["widgets_values"]), ("ModelSamplingAuraFlow", [SETTINGS["shift"], "flow"]))
                self.assertEqual(upstream(w, shift, "model")[0]["type"], "DaWVUReadOnlyUNETLoader")
                negative, _ = source(w, sampler, "negative")
                self.assertEqual(negative["type"], "ConditioningZeroOut")
                self.assertEqual(source(w, negative, "conditioning"), source(w, sampler, "positive"))
        self.assertEqual(SETTINGS["sampler"]["steps"], 12)
        self.assertEqual((SETTINGS["sampler"]["cfg"], SETTINGS["layer_sampler"]["cfg"]), (1.0, 2.0))


class TextToImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = build_all()
        cls.t2i = built[PATHS["t2i"]]
        cls.alpha = built[PATHS["transparent"]]

    def test_prompt_writer_feeds_encoder_preview_and_knows_the_canvas(self):
        for w, task, size in ((self.t2i, "design", SETTINGS["t2i_size"]), (self.alpha, "transparent", SETTINGS["transparent_size"])):
            writer = one(w, "DaWMingPromptWriter")
            self.assertEqual(writer["widgets_values"][0], task)
            self.assertEqual(writer["widgets_values"][2:], [True, 4, 0, SETTINGS["writer_tokens"]])
            self.assertEqual(source(w, writer, "text")[0]["type"], "PixaromaPrompt")
            resolution = one(w, "PixaromaResolution")
            self.assertEqual(source(w, writer, "width"), (resolution, 0))
            self.assertEqual(source(w, writer, "height"), (resolution, 1))
            state = json.loads(resolution["properties"]["resolutionState"])
            self.assertEqual((state["w"], state["h"], state["snap"]), (size, size, 32))
            encode = one(w, "CLIPTextEncode")
            self.assertEqual(source(w, encode, "text"), (writer, 0))
            self.assertIn((writer, 0), [source(w, n, "source") for n in nodes(w, "PreviewAny")])
            empty = one(w, "EmptyLatentImage")
            self.assertEqual(source(w, empty, "width"), (resolution, 0))

    def test_design_saves_rgb_and_transparent_saves_rgba(self):
        save = one(self.t2i, "PixaromaSaveImage")
        self.assertEqual(json.loads(save["properties"]["saveImageState"])["pattern"], "Ming_Image/Design_%counter%")
        rgb, slot = source(self.t2i, save, "images")
        self.assertEqual((rgb["type"], slot), ("SplitImageWithAlpha", 0))
        save = one(self.alpha, "PixaromaSaveImage")
        state = json.loads(save["properties"]["saveImageState"])
        self.assertEqual((state["pattern"], state["format"]), ("Ming_Image/Transparent_%counter%", "png"))
        fallback = one(self.alpha, "DaWMingAlphaFallback")   # Ming's alpha when present, else BiRefNet (lazy)
        self.assertEqual(fallback["widgets_values"], [SETTINGS["alpha_min_share"]])
        decode = one(self.alpha, "VAEDecode")
        self.assertEqual(source(self.alpha, fallback, "images"), (decode, 0))
        mask, _ = source(self.alpha, fallback, "mask")
        self.assertEqual(mask["type"], "RemoveBackground")
        self.assertEqual(source(self.alpha, mask, "image")[0]["type"], "SplitImageWithAlpha")
        self.assertEqual(one(self.alpha, "LoadBackgroundRemovalModel")["widgets_values"], ["birefnet.safetensors"])
        self.assertEqual(next(s for s in fallback["inputs"] if s["name"] == "mask").get("shape"), 7)
        self.assertEqual(source(self.alpha, save, "images"), (fallback, 0))
        self.assertEqual(source(self.alpha, one(self.alpha, "DaWMingCheckerboard"), "images"), (fallback, 0))
        self.assertIn((fallback, 1), [source(self.alpha, n, "source") for n in nodes(self.alpha, "PreviewAny")])


class EditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = build_all()[PATHS["edit"]]

    def test_one_reference_at_the_official_bucket_sets_the_latent(self):
        size = one(self.w, "DaWMingReferenceSize")
        self.assertEqual(size["widgets_values"], [SETTINGS["bucket"]])
        base = one(self.w, "PixaromaLoadImage")   # one image like the official pipeline (two: image 2 came back)
        self.assertEqual(source(self.w, size, "image"), (base, 0))
        encode = one(self.w, "TextEncodeMingImageEdit")
        self.assertEqual(source(self.w, encode, "images.image_1"), (size, 0))
        self.assertEqual([s["name"] for s in encode["inputs"] if s["name"].startswith("images")], ["images.image_1"])
        self.assertEqual(upstream(self.w, encode, "vae")[0]["type"], "VAELoader")
        empty = one(self.w, "EmptyLatentImage")
        self.assertEqual((source(self.w, empty, "width"), source(self.w, empty, "height")), ((size, 1), (size, 2)))
        self.assertFalse(any(slot["name"] == "images" for slot in encode["inputs"]))

    def test_saved_rgb_and_compared(self):
        save = one(self.w, "PixaromaSaveImage")
        self.assertEqual(json.loads(save["properties"]["saveImageState"])["pattern"], "Ming_Image/Edit_%counter%")
        self.assertEqual(source(self.w, save, "images")[0]["type"], "SplitImageWithAlpha")
        compare = one(self.w, "PixaromaCompare")
        self.assertEqual(source(self.w, compare, "image1")[0]["type"], "DaWMingReferenceSize")


class LayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = build_all()[PATHS["layers"]]

    def test_writer_count_drives_the_layered_latent(self):
        size = one(self.w, "DaWMingReferenceSize")
        writer = one(self.w, "DaWMingPromptWriter")
        self.assertEqual(writer["widgets_values"][:4], ["layers", "", True, SETTINGS["layers"]])
        self.assertEqual(source(self.w, writer, "image"), (size, 0))
        encode = one(self.w, "TextEncodeMingImageEdit")
        self.assertEqual(source(self.w, encode, "prompt"), (writer, 0))
        self.assertEqual(source(self.w, encode, "images.image_1"), (size, 0))
        empty = one(self.w, "EmptyQwenImageLayeredLatentImage")
        self.assertEqual(source(self.w, empty, "layers"), (writer, 1))
        self.assertEqual((source(self.w, empty, "width"), source(self.w, empty, "height")), ((size, 1), (size, 2)))

    def test_every_frame_is_decoded_as_its_own_image(self):
        cut = one(self.w, "LatentCutToBatch")
        self.assertEqual(cut["widgets_values"], ["t", 1])
        self.assertEqual(source(self.w, cut, "samples")[0]["type"], "KSampler")
        decode = one(self.w, "VAEDecode")
        self.assertEqual(source(self.w, decode, "samples"), (cut, 0))
        split = one(self.w, "DaWMingLayerSplit")
        self.assertEqual(source(self.w, split, "frames"), (decode, 0))
        save = one(self.w, "PixaromaSaveImage")
        state = json.loads(save["properties"]["saveImageState"])
        self.assertEqual((state["pattern"], state["format"]), ("Ming_Image/Layers/Layer_%counter%", "png"))
        self.assertEqual(source(self.w, save, "images"), (split, 0))
        self.assertEqual(source(self.w, one(self.w, "PreviewImage"), "images"), (split, 3))
        compare = one(self.w, "PixaromaCompare")
        self.assertEqual(source(self.w, compare, "image2"), (split, 2))


class ManifestTests(unittest.TestCase):
    def test_models_inputs_and_sources_are_pinned(self):
        models = json.loads((SOURCES / "models.json").read_text(encoding="utf-8"))
        for entry in models:
            self.assertIn(entry["repo_id"], ("Comfy-Org/Ming-Image", "Comfy-Org/BiRefNet"))
            self.assertRegex(entry["revision"], r"^[0-9a-f]{40}$")
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(entry["size"], 0)
        used = {value for workflow in build_all().values() for node in workflow["nodes"]
                if isinstance(node.get("widgets_values"), list) for value in node["widgets_values"] if isinstance(value, str)}
        for entry in models:  # every downloaded model is used by a shipped workflow
            self.assertIn(entry["path"].split("/", 1)[1].replace("/", BS), used, entry["path"])
        for item in json.loads((SOURCES / "sources.json").read_text(encoding="utf-8")):
            path = SOURCES / item["file"] if (SOURCES / item["file"]).is_file() else ROOT / item["file"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"], item["file"])
            self.assertRegex(item["url"], r"/blob/[a-f0-9]{40}/")
        for item in json.loads((SOURCES / "inputs.json").read_text(encoding="utf-8")):
            self.assertRegex(item["url"], r"https://raw.githubusercontent.com/inclusionAI/Ming-Image/[a-f0-9]{40}/")
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")


class LauncherTests(unittest.TestCase):
    def test_llama_server_follows_the_newest_hip_build(self):
        script = (ROOT / "tools" / "start-MultiGPU.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('$LlamaServerExe = "auto"', script)
        self.assertIn('$LlamaBuildRoot = "L:\\LAB\\ai-local"', script)
        self.assertIn("'^b(\\d+)_hip_llama\\.cpp$'", script)
        self.assertIn("Sort-Object { [int]($_.Name -replace '^b(\\d+)_hip_llama\\.cpp$', '$1') } -Descending", script)
        self.assertLess(script.index("$NewestLlamaBuild = "), script.index("(Test-Path -LiteralPath $PromptLlmGguf) -and"))
        self.assertNotRegex(script, r"\$LlamaServerExe = \"[^\"]*_hip_llama\.cpp")   # no hard-coded build any more


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.2.9 GPU run")
class LiveEvidenceTests(unittest.TestCase):
    def test_report_matches_the_shipped_files_and_every_run_succeeded(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        for path in PATHS.values():
            self.assertEqual(report["workflows"][path]["sha256"],
                             hashlib.sha256((ROOT / "workflows" / path).read_bytes()).hexdigest(), path)
        finals = [run for run in report["runs"] if run.get("final")]
        self.assertEqual({run["workflow"] for run in finals}, set(PATHS.values()))
        for run in report["runs"]:
            self.assertEqual(run["status"], run.get("expected_status", "success"), run["case"])

    def test_outputs_have_the_expected_channels_and_layer_count(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        for run in (r for r in report["runs"] if r.get("final")):
            check = run["check"]
            if run["workflow"] == PATHS["transparent"]:
                self.assertEqual(check["mode"], "RGBA")
                self.assertGreater(check["transparent_share"], 0.1)
            elif run["workflow"] == PATHS["layers"]:
                self.assertEqual(check["layer_files"], check["layers_requested"])
                self.assertTrue(all(mode == "RGBA" for mode in check["modes"]))
            else:
                self.assertEqual(check["mode"], "RGB")


if __name__ == "__main__":
    unittest.main()
