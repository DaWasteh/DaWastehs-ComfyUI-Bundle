"""v1.2.8 workflows: Qwen Image 2.1 mask inpaint, pose (SDPose) and depth (Depth Anything 3) from images and videos."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_vision_workflows_v128 import PATHS, ROOT, SOURCES, SETTINGS, build_all
from tools.rodent_layout import _topology_hash
from tools.validate_workflows import validate_graph

REPORT = ROOT / "performance/rdna4/vision-workflows-v128-validation.json"
BS = "\\"


def nodes(workflow, kind):
    return [n for n in workflow["nodes"] if n["type"] == kind]


def one(workflow, kind):
    found = nodes(workflow, kind)
    assert len(found) == 1, (kind, len(found))
    return found[0]


def source(workflow, target, name):
    slot = next(i for i, s in enumerate(target["inputs"]) if s["name"] == name)
    link = next(l for l in workflow["links"] if l[3:5] == [target["id"], slot])
    return next(n for n in workflow["nodes"] if n["id"] == link[1]), link[2]


def upstream(workflow, target, name, skip=("SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice")):
    """Source of an input, looking through the device selectors the v0.9.2 migration inserts after loaders."""
    node, slot = source(workflow, target, name)
    while node["type"] in skip:
        node, slot = source(workflow, node, {"SelectModelDevice": "model", "SelectCLIPDevice": "clip", "SelectVAEDevice": "vae"}[node["type"]])
    return node, slot


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = build_all()

    def test_rebuild_is_exact_and_lf_only(self):
        self.assertEqual(set(self.built), set(PATHS.values()))
        self.assertEqual(build_all(), self.built)
        from tools import build_vision_workflows_v128 as builder
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
                self.assertEqual(workflow["extra"]["dawasteh_vision_v128"]["kind"],
                                 next(k for k, v in PATHS.items() if v == path))
                self.assertTrue(any(n["type"] == "MarkdownNote" and n["title"].startswith("START HIER") for n in workflow["nodes"]))


class QwenInpaintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = build_all()[PATHS["qwen_inpaint"]]

    def test_same_local_qwen_21_profile_as_v121(self):
        from tools import build_qwen_image21_workflows as v121
        self.assertEqual(one(self.w, "UNETLoader")["widgets_values"], [v121.MODEL, "default"])
        self.assertEqual(one(self.w, "CLIPLoader")["widgets_values"], [v121.CLIP, "qwen_image", "default"])
        self.assertEqual(one(self.w, "VAELoader")["widgets_values"], [v121.VAE])
        self.assertEqual(one(self.w, "KSampler")["widgets_values"], [0, "fixed", 25, 1.0, "euler", "simple", 1.0])
        self.assertEqual(one(self.w, "QwenImage21Cache")["widgets_values"], ["auto", "default"])

    def test_mask_flows_from_image_or_editor_through_the_guard_into_the_noise_mask(self):
        load = one(self.w, "LoadImage")
        crop = one(self.w, "PixaromaInpaintCrop")
        self.assertEqual(source(self.w, crop, "image"), (load, 0))
        self.assertEqual(source(self.w, crop, "mask"), (load, 1))
        c = SETTINGS["inpaint_crop"]
        self.assertEqual(crop["widgets_values"][:9], [c["size_mode"], c["target"], c["multiple"], c["context_px"], c["mask_grow"],
                                                      c["mask_blur"], c["softness"], c["blend_mode"], c["invert_mask"]])
        self.assertEqual(c["multiple"], 32)  # TextEncodeQwenImage21 resolution 0 rounds to 32 px: latent and reference align
        guard = one(self.w, "DaWRequireMask")
        self.assertEqual(source(self.w, guard, "image"), (crop, 0))
        self.assertEqual(source(self.w, guard, "mask"), (crop, 1))
        self.assertEqual(guard["widgets_values"], [16])
        masked = one(self.w, "SetLatentNoiseMask")
        self.assertEqual(source(self.w, masked, "mask"), (guard, 1))
        encode = one(self.w, "VAEEncode")  # behind the guard: no encoder/VAE work before the check
        self.assertEqual(source(self.w, encode, "pixels"), (guard, 0))
        self.assertEqual(source(self.w, masked, "samples"), (encode, 0))
        sampler = one(self.w, "KSampler")
        self.assertEqual(source(self.w, sampler, "latent_image"), (masked, 0))

    def test_crop_is_the_reference_and_the_model_uses_differential_diffusion(self):
        guard = one(self.w, "DaWRequireMask")
        text = one(self.w, "TextEncodeQwenImage21")
        self.assertEqual(text["widgets_values"][2], 0)
        self.assertEqual(source(self.w, text, "images.image_1"), (guard, 0))
        sampler = one(self.w, "KSampler")
        cache, _ = source(self.w, sampler, "model")
        self.assertEqual(cache["type"], "QwenImage21Cache")
        soft, _ = source(self.w, cache, "model")
        self.assertEqual((soft["type"], soft["widgets_values"]), ("DifferentialDiffusion", [1.0]))
        self.assertEqual(upstream(self.w, soft, "model")[0]["type"], "UNETLoader")

    def test_stitch_pastes_rgb_back_and_everything_is_saved_and_compared(self):
        crop = one(self.w, "PixaromaInpaintCrop")
        stitch = one(self.w, "PixaromaInpaintStitch")
        rgb, slot = source(self.w, stitch, "image")
        self.assertEqual((rgb["type"], slot), ("SplitImageWithAlpha", 0))
        self.assertEqual(source(self.w, rgb, "image")[0]["type"], "VAEDecode")
        self.assertEqual(source(self.w, stitch, "crop_info"), (crop, 2))
        self.assertEqual(stitch["widgets_values"], [-1, "from crop", "off"])
        save = one(self.w, "PixaromaSaveImage")
        state = json.loads(save["properties"]["saveImageState"])
        self.assertEqual((state["pattern"], state["format"], state["embedWorkflow"]), ("Qwen_Image_2_1/Inpaint_%counter%", "png", True))
        self.assertEqual(source(self.w, save, "images"), (stitch, 0))
        compare = one(self.w, "PixaromaCompare")
        self.assertEqual(source(self.w, compare, "image1")[0]["type"], "LoadImage")
        self.assertEqual(source(self.w, compare, "image2"), (stitch, 0))
        self.assertIn("Research", json.dumps(self.w))


class PoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = build_all()
        cls.image = built[PATHS["pose_image"]]
        cls.video = built[PATHS["pose_video"]]

    def test_detector_crops_feed_sdpose_and_the_drawer(self):
        for w in (self.image, self.video):
            ckpt = one(w, "CheckpointLoaderSimple")
            self.assertEqual(ckpt["widgets_values"], ["SDPose" + BS + "sdpose_wholebody_fp16.safetensors"])
            detector = one(w, "UNETLoader")
            self.assertEqual(detector["widgets_values"], ["SDPose" + BS + "rt_detr_v4-x-hgnet_fp16.safetensors", "default"])
            detect = one(w, "RTDETR_detect")
            self.assertEqual(detect["widgets_values"], [0.5, "person", 1])
            self.assertEqual(upstream(w, detect, "model")[0]["id"], detector["id"])
            extract = one(w, "SDPoseKeypointExtractor")
            self.assertEqual(upstream(w, extract, "model"), (ckpt, 0))
            self.assertEqual(upstream(w, extract, "vae"), (ckpt, 2))
            boxes = one(w, "DaWPoseBoxes")  # unsquashed 3:4 crops instead of the extractor's stretch
            self.assertEqual(boxes["widgets_values"], [1.25])
            self.assertEqual(source(w, boxes, "bboxes"), (detect, 0))
            self.assertEqual(source(w, extract, "bboxes"), (boxes, 0))
            self.assertEqual(source(w, one(w, "DrawBBoxes"), "bboxes"), (boxes, 0))
            draw = one(w, "SDPoseDrawKeypoints")
            self.assertEqual(draw["widgets_values"], [True, True, True, True, 4, 2, 0.5, True])
            self.assertEqual(source(w, draw, "keypoints"), (extract, 0))
            blend = one(w, "ImageBlend")
            self.assertEqual(blend["widgets_values"], [1.0, "screen"])
            self.assertEqual(source(w, blend, "image2"), (draw, 0))

    def test_image_saves_pose_map_and_openpose_json(self):
        save = one(self.image, "PixaromaSaveImage")
        self.assertEqual(json.loads(save["properties"]["saveImageState"])["pattern"], "Pose/Pose_%counter%")
        self.assertEqual(source(self.image, save, "images")[0]["type"], "SDPoseDrawKeypoints")
        keypoints = one(self.image, "SavePoseKpsAsJsonFile")
        self.assertEqual(keypoints["widgets_values"], ["Pose/Pose_Keypoints"])
        self.assertEqual(source(self.image, keypoints, "pose_kps")[0]["type"], "SDPoseKeypointExtractor")
        self.assertEqual(one(self.image, "PixaromaLoadImage")["widgets_values"][0], "dancer.png")


class DepthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = build_all()
        cls.image = built[PATHS["depth_image"]]
        cls.video = built[PATHS["depth_video"]]

    def test_depth_anything_3_mono_large(self):
        for w, key in ((self.image, "depth_image"), (self.video, "depth_video")):
            self.assertEqual(one(w, "LoadDA3Model")["widgets_values"],
                             ["DepthAnything3" + BS + "depth_anything_3_mono_large.safetensors", "default"])
            s = SETTINGS[key]
            self.assertEqual(one(w, "DA3Inference")["widgets_values"], [s["resolution"], s["resize_method"], "mono"])

    def test_image_saves_8_bit_16_bit_and_compares(self):
        renders = {tuple(n["widgets_values"]): n for n in nodes(self.image, "DA3Render")}
        self.assertEqual(set(renders), {("depth", "v2_style", False), ("depth", "min_max", True), ("depth_colored", "v2_style", False)})
        save = one(self.image, "PixaromaSaveImage")
        self.assertEqual(json.loads(save["properties"]["saveImageState"])["pattern"], "Depth/Depth_%counter%")
        self.assertEqual(source(self.image, save, "images"), (renders[("depth", "v2_style", False)], 0))
        save16 = one(self.image, "DaWSaveDepth16")
        self.assertEqual(save16["widgets_values"], ["Depth/Depth16"])
        self.assertEqual(source(self.image, save16, "images"), (renders[("depth", "min_max", True)], 0))
        for render in renders.values():
            self.assertEqual([s["name"] for s in render["inputs"] if "widget" in s],
                             ["output", "output.normalization", "output.apply_sky_clip"])


class VideoFrameTests(unittest.TestCase):
    def test_meta_batch_frame_keeps_size_fps_and_audio(self):
        built = build_all()
        for key in ("pose_video", "depth_video"):
            w = built[PATHS[key]]
            with self.subTest(key=key):
                batch = one(w, "VHS_BatchManager")
                self.assertEqual(batch["widgets_values"], [SETTINGS["frames_per_batch"]])
                load = one(w, "DaWLoadVideoBatches")  # VHS loader, safe for silent videos and after cancelled runs
                self.assertEqual(load["widgets_values"][1:], [0, 0])
                self.assertEqual(source(w, load, "meta_batch"), (batch, 0))
                self.assertFalse(nodes(w, "VHS_LoadVideo"))
                combines = nodes(w, "VHS_VideoCombine")
                self.assertEqual(sorted(c["widgets_values"]["save_output"] for c in combines), [False, True])
                for combine in combines:
                    self.assertEqual(source(w, combine, "meta_batch"), (batch, 0))
                    self.assertEqual(source(w, combine, "frame_rate"), (load, 3))
                    self.assertEqual(source(w, combine, "audio"), (load, 2))
                    v = combine["widgets_values"]
                    self.assertEqual((v["format"], v["pix_fmt"], v["crf"], v["pingpong"]), ("video/h264-mp4", "yuv420p", SETTINGS["crf"], False))
                saved = next(c for c in combines if c["widgets_values"]["save_output"])
                self.assertEqual(saved["widgets_values"]["filename_prefix"], {"pose_video": "Pose/Pose_Video", "depth_video": "Depth/Depth_Video"}[key])


class ManifestTests(unittest.TestCase):
    def test_models_inputs_and_templates_are_pinned(self):
        models = json.loads((SOURCES / "models.json").read_text(encoding="utf-8"))
        for entry in models:
            self.assertRegex(entry["revision"], r"^[0-9a-f]{40}$")
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(entry["size"], 0)
        used = {value for workflow in build_all().values() for node in workflow["nodes"]
                if isinstance(node.get("widgets_values"), list) for value in node["widgets_values"] if isinstance(value, str)}
        for entry in models:  # every downloaded model is used by a shipped workflow
            self.assertIn(entry["path"].split("/", 1)[1].replace("/", BS), used, entry["path"])
        for item in json.loads((SOURCES / "sources.json").read_text(encoding="utf-8")):
            self.assertEqual(hashlib.sha256((SOURCES / item["file"]).read_bytes()).hexdigest(), item["sha256"])
            self.assertRegex(item["url"], r"/blob/[a-f0-9]{40}/templates/")
        for item in json.loads((SOURCES / "inputs.json").read_text(encoding="utf-8")):
            self.assertRegex(item["url"], r"https://raw.githubusercontent.com/Comfy-Org/workflow_templates/[a-f0-9]{40}/input/")
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.2.8 GPU run")
class LiveEvidenceTests(unittest.TestCase):
    def test_report_matches_the_shipped_files_and_every_run_succeeded(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        for path in PATHS.values():
            self.assertEqual(report["workflows"][path]["sha256"],
                             hashlib.sha256((ROOT / "workflows" / path).read_bytes()).hexdigest(), path)
        for run in report["runs"]:
            self.assertEqual(run["status"], run.get("expected_status", "success"), run["case"])

    def test_inpaint_keeps_every_pixel_outside_the_mask(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        checked = [r for r in report["runs"] if r.get("check", {}).get("outside_max_abs_diff") is not None]
        self.assertGreaterEqual(len(checked), 4)
        for run in checked:
            self.assertEqual(run["check"]["outside_max_abs_diff"], 0, run["case"])
            self.assertEqual(run["check"]["size"], run["check"]["source_size"], run["case"])
            self.assertGreater(run["check"]["inside_mean_abs_diff"], 5, run["case"])

    def test_videos_keep_frames_fps_and_audio(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        videos = [r for r in report["runs"] if r.get("video")]
        self.assertGreaterEqual(len(videos), 3)
        for run in videos:
            out, src = run["video"], run["source"]
            self.assertEqual((out["frames"], out["width"], out["height"]), (src["frames"], src["width"], src["height"]), run["case"])
            self.assertAlmostEqual(out["fps"], src["fps"], places=2)
            self.assertEqual(bool(out["audio"]), bool(src["audio"]), run["case"])


if __name__ == "__main__":
    unittest.main()
