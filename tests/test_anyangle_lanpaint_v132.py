"""v1.3.2 workflows: Qwen Image 2.1 with LanPaint (mask inpaint) and AnyAngle (camera angles from a coarse render)."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_anyangle_lanpaint_v132 import (ANYANGLE_LORA, ANYANGLE_PROMPT, MARKER, PATHS, ROOT, SETTINGS, SOURCES,
                                                build_all)
from tools.rodent_layout import _topology_hash
from tools.validate_workflows import validate_graph

REPORT = ROOT / "performance/rdna4/anyangle-lanpaint-v132-validation.json"
BS = "\\"
DEVICE_NODES = {"SelectModelDevice": "model", "SelectCLIPDevice": "clip", "SelectVAEDevice": "vae"}


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


def upstream(workflow, target, name):
    """Source of an input, looking through the device selectors the v0.9.2 migration inserts after loaders."""
    node, slot = source(workflow, target, name)
    while node["type"] in DEVICE_NODES:
        node, slot = source(workflow, node, DEVICE_NODES[node["type"]])
    return node, slot


def prompt_text(node):
    return node["properties"]["promptState"]["text"]


def widget(node, schemas, name):
    """Value of a widget by name (positional widgets_values; control_after_generate adds one slot after seeds)."""
    index = 0
    spec = schemas[node["type"]]["input"]
    for section in ("required", "optional"):
        for key, value in spec.get(section, {}).items():
            kind = value[0]
            config = value[1] if len(value) > 1 else {}
            is_widget = not config.get("forceInput") and (isinstance(kind, list) or kind in (
                "COMBO", "STRING", "INT", "FLOAT", "BOOLEAN", "COMFY_DYNAMICCOMBO_V3", "COLOR"))
            if not is_widget:
                continue
            if key == name:
                return node["widgets_values"][index]
            # the frontend gives every "seed" widget a control_after_generate companion, declared or not (LanPaint)
            index += 2 if config.get("control_after_generate") or key == "seed" else 1
    raise KeyError(name)


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = build_all()
        cls.schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
        cls.lanpaint = cls.built[PATHS["lanpaint_inpaint"]]
        cls.splat = cls.built[PATHS["anyangle_splat"]]
        cls.guide = cls.built[PATHS["anyangle_guide"]]
        cls.studio = cls.built[PATHS["anyangle_studio"]]

    def test_rebuild_is_exact_and_lf_only(self):
        self.assertEqual(set(self.built), set(PATHS.values()))
        self.assertEqual(build_all(), self.built)
        from tools import build_anyangle_lanpaint_v132 as builder
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "ROOT", Path(directory)):
            builder.main()
            for path in PATHS.values():
                data = (Path(directory) / "workflows" / path).read_bytes()
                self.assertNotIn(b"\r\n", data)
                self.assertEqual(data, (ROOT / "workflows" / path).read_bytes(), path)

    def test_flat_valid_rodent_timer_and_one_gpu_control(self):
        for key, path in PATHS.items():
            workflow = self.built[path]
            errors = []
            validate_graph(Path(path), "root", workflow, errors)
            self.assertEqual(errors, [], path)
            self.assertFalse(workflow.get("definitions", {}).get("subgraphs"))
            self.assertEqual(workflow["extra"]["dawasteh_rodent_layout"]["topology_sha256"], _topology_hash(workflow))
            self.assertEqual(len(nodes(workflow, "PixaromaRunTimer")), 1)
            self.assertEqual(one(workflow, "DaWMultiGPUDeviceControl")["widgets_values"], ["gpu:0"] * 3)
            self.assertEqual(workflow["extra"][MARKER]["kind"], key)
            titles = [n["title"] for n in workflow["nodes"] if n["type"] == "MarkdownNote"]
            self.assertTrue(any(t.startswith("START HIER") for t in titles), path)
            self.assertTrue(any(t.startswith("DOWNLOADS") for t in titles), path)

    def test_names_follow_the_scheme_and_name_the_helper(self):
        for path in PATHS.values():
            stem = Path(path).stem
            self.assertRegex(stem, r"^[A-Za-z0-9_.+&-]+$")
            self.assertTrue(stem.startswith("Qwen_Image_2_1_BF16+"), stem)
        self.assertIn("+LanPaint-Image+Mask-Inpaint", PATHS["lanpaint_inpaint"])
        self.assertIn("+AnyAngle_LoRA+TripoSplat-Image-to-4-Camera-Angles", PATHS["anyangle_splat"])

    # -- LanPaint -----------------------------------------------------------------------------------------------------
    def test_lanpaint_replaces_the_sampler_and_keeps_crop_guard_and_stitch(self):
        w = self.lanpaint
        self.assertEqual(nodes(w, "KSampler"), [])
        self.assertEqual(nodes(w, "SetLatentNoiseMask"), [])
        sampler = one(w, "LanPaint_KSampler")
        for name, value in SETTINGS["lanpaint_sampler"].items():
            self.assertEqual(widget(sampler, self.schemas, name), value, name)
        self.assertEqual((SETTINGS["lanpaint_sampler"]["steps"], SETTINGS["lanpaint_sampler"]["cfg"],
                          SETTINGS["lanpaint_sampler"]["LanPaint_NumSteps"]), (20, 4.0, 5))
        self.assertEqual(sampler["widgets_values"][:9], [0, "fixed", 20, 4.0, "euler", "simple", 1.0, 5, "Image First"])
        self.assertEqual(sampler["widgets_values"][-1], "🖼️ Image Inpainting")
        encode = one(w, "LanPaint_ImageEncode")
        guard = one(w, "DaWRequireMask")
        crop = one(w, "PixaromaInpaintCrop")
        self.assertEqual(source(w, encode, "image"), (guard, 0))
        self.assertEqual(source(w, encode, "mask"), (guard, 1))
        self.assertEqual(source(w, guard, "image"), (crop, 0))
        self.assertEqual(source(w, sampler, "latent_image"), (encode, 0))
        decode = one(w, "LanPaint_ImageDecode")
        self.assertEqual(source(w, decode, "samples"), (sampler, 0))
        self.assertEqual(source(w, decode, "image"), (guard, 0))  # merge inside the mask needs the original crop
        self.assertEqual(source(w, decode, "mask"), (guard, 1))
        self.assertEqual(widget(decode, self.schemas, "blend_overlap"), 9)
        stitch = one(w, "PixaromaInpaintStitch")
        self.assertEqual(source(w, stitch, "image"), (decode, 0))
        self.assertEqual(source(w, stitch, "crop_info"), (crop, 2))
        self.assertEqual(source(w, one(w, "PixaromaSaveImage"), "images"), (stitch, 0))

    def test_lanpaint_uses_the_qwen21_models_without_a_lora_and_a_real_negative(self):
        w = self.lanpaint
        self.assertEqual(nodes(w, "LoraLoaderModelOnly"), [])
        sampler = one(w, "LanPaint_KSampler")
        cache, _ = source(w, sampler, "model")
        self.assertEqual(cache["type"], "QwenImage21Cache")
        unet, _ = upstream(w, cache, "model")
        self.assertEqual(unet["widgets_values"][0], "Qwen" + BS + "qwen_image_2.1_bf16.safetensors")
        encode = one(w, "TextEncodeQwenImage21")
        self.assertEqual(source(w, sampler, "positive"), (encode, 0))
        self.assertEqual(source(w, sampler, "negative"), (encode, 1))
        self.assertEqual(widget(encode, self.schemas, "resolution"), 0)
        self.assertEqual(source(w, encode, "images.image_1")[0]["type"], "DaWRequireMask")
        negative, _ = source(w, encode, "negative_prompt")
        self.assertIn("low quality", prompt_text(negative))  # CFG 4 uses it

    # -- AnyAngle -----------------------------------------------------------------------------------------------------
    def test_anyangle_chains_use_the_lora_at_strength_one_and_the_recommended_sampler(self):
        for w, count in ((self.splat, 4), (self.guide, 1)):
            lora = one(w, "LoraLoaderModelOnly")
            self.assertEqual(lora["widgets_values"], [ANYANGLE_LORA, 1.0])
            self.assertEqual(upstream(w, lora, "model")[0]["widgets_values"][0], "Qwen" + BS + "qwen_image_2.1_bf16.safetensors")
            cache = one(w, "QwenImage21Cache")
            self.assertEqual(source(w, cache, "model"), (lora, 0))
            samplers = [s for s in nodes(w, "KSampler") if source(w, s, "model")[0] is cache]
            self.assertEqual(len(samplers), count)
            for sampler in samplers:
                for name, value in SETTINGS["anyangle_sampler"].items():
                    self.assertEqual(widget(sampler, self.schemas, name), value, name)
                encode, slot = source(w, sampler, "latent_image")
                self.assertEqual((encode["type"], slot), ("TextEncodeQwenImage21", 2))
                self.assertEqual(widget(encode, self.schemas, "resolution"), 1024)
                self.assertEqual(prompt_text(source(w, encode, "prompt")[0]), ANYANGLE_PROMPT)
                self.assertEqual(prompt_text(source(w, encode, "negative_prompt")[0]), "")

    def test_the_original_is_image_1_and_the_render_image_2(self):
        # measured 2026-10-02: with the render as image 1 (the order the model card describes) the view does not change
        self.assertEqual(ANYANGLE_PROMPT, "Change the camera angle from <image2> to <image1>.")
        load = one(self.splat, "PixaromaLoadImage")
        for encode in nodes(self.splat, "TextEncodeQwenImage21"):
            self.assertEqual(source(self.splat, encode, "images.image_1"), (load, 0))
            self.assertEqual(source(self.splat, encode, "images.image_2")[0]["type"], "RenderSplat")
        encode = one(self.guide, "TextEncodeQwenImage21")
        first, _ = source(self.guide, encode, "images.image_1")
        second, _ = source(self.guide, encode, "images.image_2")
        self.assertIn("ORIGINAL", first["title"])
        self.assertIn("GROBES RENDER", second["title"])
        self.assertEqual([first["widgets_values"][0], second["widgets_values"][0]],
                         ["character_fox.png", "character_fox_guide_left.png"])

    def test_four_cameras_orbit_around_the_original_view(self):
        cameras = nodes(self.splat, "CreateCameraInfo")
        front = SETTINGS["camera"]["front_yaw"]
        self.assertEqual(front, 90.0)  # measured: Render Splat's yaw 90 is the camera of the input image
        self.assertEqual([c["widgets_values"] for c in cameras], [
            ["orbit", front + offset, pitch, 2.3, 0.0, 0.0, 0.0, 0.0, 35.0, 1.0, "perspective"]
            for _, _, offset, pitch in SETTINGS["views"]])
        self.assertEqual([offset for _, _, offset, _ in SETTINGS["views"]], [45.0, 90.0, -45.0, 20.0])
        for camera in cameras:
            self.assertEqual([s["name"] for s in camera["inputs"]][:4], ["mode", "yaw", "pitch", "distance"])
        renders = nodes(self.splat, "RenderSplat")
        self.assertEqual(len(renders), 4)
        splat = one(self.splat, "VAEDecodeTripoSplat")
        for camera, render in zip(cameras, renders):
            self.assertEqual(source(self.splat, render, "camera_info"), (camera, 0))
            self.assertEqual(source(self.splat, render, "splat"), (splat, 0))
            self.assertEqual(render["widgets_values"], [1024, 1024, 1, 1.0, 2.0, 0.0, 0.0, "color", "#848484"])
        saves = [n["properties"]["saveImageState"] for n in nodes(self.splat, "PixaromaSaveImage")]
        self.assertEqual([json.loads(s)["pattern"] for s in saves],
                         [f"AnyAngle/{tag}_%counter%" for _, tag, _, _ in SETTINGS["views"]])

    def test_triposplat_chain_is_the_official_one(self):
        w = self.splat
        splat = one(w, "VAEDecodeTripoSplat")
        self.assertEqual(splat["widgets_values"][0], 262144)
        self.assertEqual(upstream(w, splat, "vae")[0]["widgets_values"][0], "TripoSplat" + BS + "triposplat_vae_decoder_fp16.safetensors")
        sampler, _ = source(w, splat, "samples")
        for name, value in SETTINGS["triposplat_sampler"].items():
            self.assertEqual(widget(sampler, self.schemas, name), value, name)
        self.assertEqual(upstream(w, sampler, "model")[0]["widgets_values"][0], "TripoSplat" + BS + "triposplat_fp16.safetensors")
        cond, _ = source(w, sampler, "positive")
        self.assertEqual(cond["type"], "TripoSplatConditioning")
        self.assertEqual(source(w, cond, "clip_vision")[0]["widgets_values"], ["dino_v3_vit_h.safetensors"])
        self.assertEqual(upstream(w, cond, "vae")[0]["widgets_values"][0], "FLUX2" + BS + "flux2-vae.safetensors")
        prep, _ = source(w, cond, "image")
        self.assertEqual(prep["widgets_values"], [1, 1024])
        mask, _ = source(w, prep, "mask")
        self.assertEqual(mask["type"], "RemoveBackground")
        self.assertEqual(source(w, mask, "bg_removal_model")[0]["widgets_values"], ["birefnet.safetensors"])
        self.assertEqual(source(w, prep, "image"), source(w, mask, "image"))

    def test_studio_workflow_follows_the_node_authors_wiring(self):
        w = self.studio
        studio = one(w, "AnyAngleStudioT8")
        self.assertEqual(studio["widgets_values"], [""])  # the scene is applied in the editor
        load = one(w, "LoadImage")  # the studio reads a directly connected core Load Image without an extra click
        self.assertEqual(source(w, studio, "reference_image"), (load, 0))
        lora = one(w, "AnyAngleOptionalLoRAT8")
        self.assertEqual(lora["widgets_values"], [ANYANGLE_LORA, 1.0])
        self.assertEqual(source(w, lora, "strength_model"), (studio, 3))
        encode = one(w, "TextEncodeQwenImage21")
        self.assertEqual(source(w, encode, "images.image_1"), (load, 0))
        self.assertEqual(source(w, encode, "images.image_2"), (studio, 0))
        self.assertEqual(source(w, encode, "prompt"), (studio, 1))
        sampler = one(w, "KSampler")
        self.assertEqual(source(w, sampler, "model")[0]["type"], "QwenImage21Cache")
        self.assertEqual(nodes(w, "LoraLoaderModelOnly"), [])

    def test_loaders_cap_camera_photos_at_4_megapixels(self):
        for w in (self.splat, self.guide):
            for load in nodes(w, "PixaromaLoadImage"):
                state = json.loads(load["properties"]["loadImagePixState"])
                self.assertEqual((state["mode"], state["max_mp"], state["allow_upscale"]), ("max_mp", 4.0, False))

    def test_notes_explain_handling_limits_and_downloads(self):
        def text(workflow):
            return "\n".join(n["widgets_values"][0] for n in workflow["nodes"] if n["type"] == "MarkdownNote")

        for needle in ("LanPaint_NumSteps", "CFG 4", "Wächter", "scraed/LanPaint", "docs/ANYANGLE_LANPAINT_V132.md"):
            self.assertIn(needle, text(self.lanpaint))
        for needle in ("90 = Originalkamera", "TripoSplat", "QI2.1_AnyAngle.safetensors", "dino_v3_vit_h.safetensors",
                       "triposplat_fp16.safetensors", "birefnet.safetensors", "Grenzen", "output/AnyAngle/"):
            self.assertIn(needle, text(self.splat))
        for needle in ("<image1>` = Original", "nicht tauschen", "character_fox_guide_left.png"):
            self.assertIn(needle, text(self.guide))
        for needle in ("Apply to node", "T8mars/Comfyui-Qwen-Image-2.1-MultiAngle-T8", "input/anyangle_studio/"):
            self.assertIn(needle, text(self.studio))


class ManifestTests(unittest.TestCase):
    def test_models_are_pinned_by_revision_size_and_sha256(self):
        models = json.loads((SOURCES / "models.json").read_text(encoding="utf-8"))
        self.assertEqual({Path(m["path"]).name for m in models}, {
            "QI2.1_AnyAngle.safetensors", "triposplat_fp16.safetensors", "triposplat_vae_decoder_fp16.safetensors",
            "dino_v3_vit_h.safetensors", "flux2-vae.safetensors", "birefnet.safetensors"})
        for model in models:
            self.assertRegex(model["revision"], r"^[0-9a-f]{40}$")
            self.assertRegex(model["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(model["size"], 100_000_000)
        lora = next(m for m in models if m["path"].endswith("QI2.1_AnyAngle.safetensors"))
        self.assertEqual((lora["repo_id"], lora["path"]), ("lilylilith/QI_2.1_AnyAngle", "loras/Qwen/QI2.1_AnyAngle.safetensors"))

    def test_archived_templates_match_their_hashes(self):
        for entry in json.loads((SOURCES / "sources.json").read_text(encoding="utf-8")):
            data = (SOURCES / entry["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"], entry["file"])

    def test_schemas_cover_every_node_type_of_the_graphs(self):
        schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
        for path, workflow in build_all().items():
            for node in workflow["nodes"]:
                if node["type"] not in ("MarkdownNote",):
                    self.assertIn(node["type"], schemas, (path, node["type"]))


class PackAndUpdaterTests(unittest.TestCase):
    def test_updater_tracks_lanpaint_and_the_studio_from_github_without_their_requirements(self):
        updater = (ROOT / "tools" / "update-comfyui-rdna4.ps1").read_text(encoding="utf-8-sig")
        block = updater[updater.index("$GitTrackedNodes = @("):]
        block = block[:block.index("\n)")]
        self.assertIn('@{ Name = "LanPaint"; Url = "https://github.com/scraed/LanPaint.git" }', block)
        self.assertIn('@{ Name = "ComfyUI-AnyAngle-Studio-T8"; '
                      'Url = "https://github.com/T8mars/Comfyui-Qwen-Image-2.1-MultiAngle-T8.git" }', block)
        # only the bundle's own packs get "pip install -r": the studio's requirements name the plain onnxruntime wheel
        self.assertEqual(len(re.findall(r'custom_nodes\\\$nodeName\\requirements\.txt', updater)), 1)
        self.assertNotIn("AnyAngle-Studio-T8\\requirements.txt", updater)

    def test_launcher_names_the_release(self):
        script = (ROOT / "tools" / "start-MultiGPU.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Launcher v1.3.2", script)

    def test_gallery_catalog_runs_the_new_workflows(self):
        catalog = (ROOT / "tools" / "examples" / "catalog_image.py").read_text(encoding="utf-8")
        for key in ("lanpaint_inpaint", "anyangle_splat", "anyangle_guide"):
            self.assertIn(PATHS[key], catalog)
        meta = (ROOT / "tools" / "examples" / "workflow_meta_image.py").read_text(encoding="utf-8")
        for path in PATHS.values():
            self.assertIn(Path(path).name, meta)


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.3.2 GPU runs")
class LiveEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.runs = {run["case"]: run for run in cls.report["runs"]}

    def test_report_matches_the_shipped_files_and_every_run_succeeded(self):
        for path in PATHS.values():
            self.assertEqual(self.report["workflows"][path]["sha256"],
                             hashlib.sha256((ROOT / "workflows" / path).read_bytes()).hexdigest(), path)
        self.assertGreaterEqual(len(self.report["runs"]), 8)
        for run in self.report["runs"]:
            self.assertEqual(run["status"], "success", run["case"])

    def test_every_workflow_ran_through_the_real_frontend(self):
        ran = {run["workflow"] for run in self.report["runs"]}
        self.assertEqual(ran, set(PATHS.values()))
        self.assertIn("headless Edge", self.report["frontend"])

    def test_models_were_verified_by_sha256(self):
        models = {m["path"]: m["sha256"] for m in json.loads((SOURCES / "models.json").read_text(encoding="utf-8"))}
        verified = {f["path"]: f["sha256"] for f in self.report["model_verification"]["files"] if f.get("matches_manifest")}
        for path in ("loras/Qwen/QI2.1_AnyAngle.safetensors", "diffusion_models/TripoSplat/triposplat_fp16.safetensors",
                     "vae/TripoSplat/triposplat_vae_decoder_fp16.safetensors", "clip_vision/dino_v3_vit_h.safetensors"):
            self.assertEqual(verified[path], models[path])

    def test_lanpaint_leaves_everything_outside_the_mask_untouched(self):
        for case, run in self.runs.items():
            if run["workflow"] == PATHS["lanpaint_inpaint"]:
                self.assertEqual(run["check"]["outside_changed_pixels"], 0, case)
                self.assertGreater(run["check"]["inside_changed_fraction"], 0.5, case)

    def test_four_angles_come_out_of_one_run_and_fit_the_r9700(self):
        for case, run in self.runs.items():
            if run["workflow"] == PATHS["anyangle_splat"]:
                self.assertEqual(run["check"]["saved_images"], 4, case)
                self.assertLess(run["memory"]["peak_vram_gib"], 32.0, case)

    def test_render_splat_needs_the_chunked_inverse_on_rocm(self):
        finding = next(f for f in self.report["findings"] if "Render Splat" in f["topic"])
        self.assertIn("hipErrorInvalidConfiguration", finding["observed"])
        self.assertIn("splat_inverse.py", finding["fix"])


if __name__ == "__main__":
    unittest.main()
