"""v1.2.6 WAN video upscale: rebuilt workflow (WAN 2.2 A14B low-noise, WAN 2.1 compatible) in the v1.2.3 block frame."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = "Video Upscaling/WAN22_14B_LowNoise-Video-Upscale.json"
REPORT = ROOT / "performance/rdna4/video-upscale-wan-v126-validation.json"


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.build_video_upscale_wan_v126 import build_all
        cls.built = build_all()
        cls.shipped = json.loads((ROOT / "workflows" / PATH).read_text(encoding="utf-8"))
        cls.models = json.loads((ROOT / "tools/workflow_templates/v126/models.json").read_text(encoding="utf-8"))

    def nodes(self, kind: str) -> list[dict]:
        return [node for node in self.shipped["nodes"] if node["type"] == kind]

    def linked_from(self, target: dict, name: str) -> tuple[str, int]:
        link_id = next(slot["link"] for slot in target["inputs"] if slot["name"] == name)
        link = next(link for link in self.shipped["links"] if link[0] == link_id)
        source = next(node for node in self.shipped["nodes"] if node["id"] == link[1])
        return source["type"], link[2]

    def test_builder_is_deterministic_and_matches_the_shipped_file(self):
        from tools.build_video_upscale_wan_v126 import build_all
        self.assertEqual(set(self.built), {PATH})
        self.assertEqual(build_all(), self.built)
        self.assertEqual(self.built[PATH], self.shipped)

    def test_shared_block_frame_of_v123(self):
        for kind, count in (("DaWVUPlanner", 1), ("DaWVULoadBlock", 2), ("DaWVUSaveBlock", 2), ("DaWVUFinalize", 1),
                            ("PixaromaPauseImage", 1), ("PixaromaLoopStart", 1), ("PixaromaLoopEnd", 1),
                            ("PixaromaRunTimer", 1), ("DaWMultiGPUDeviceControl", 1)):
            self.assertEqual(len(self.nodes(kind)), count, kind)
        loop_start = self.nodes("PixaromaLoopStart")[0]
        self.assertEqual(self.linked_from(loop_start, "total"), ("DaWVUPlanner", 2))
        loads = sorted(self.nodes("DaWVULoadBlock"), key=lambda n: n["widgets_values"][1])
        self.assertEqual([n["widgets_values"][1:] for n in loads], [[0, "wan (4k+1)", 5], [1, "wan (4k+1)", 5]])
        self.assertEqual(self.linked_from(loads[1], "block_index"), ("PixaromaLoopStart", 6))
        self.assertEqual(self.nodes("DaWMultiGPUDeviceControl")[0]["widgets_values"], ["gpu:0", "gpu:0", "gpu:0"])

    def test_measured_settings(self):
        planner = self.nodes("DaWVUPlanner")[0]["widgets_values"]
        self.assertEqual(planner[3:9], [1.5, 7.0, 2.0, 10.0, 18.0, "wan22"])  # scenes up to 10 s stay one block
        # Denoise 0.3 (start sigma 0.69 at shift 5) re-drew faces and signs; 2 steps matched 4 steps at half the time.
        for sampler in self.nodes("KSampler"):
            self.assertEqual(sampler["widgets_values"], [20260926, "fixed", 2, 1.0, "euler", "simple", 0.15])
        # 832x480 tiles: finer detail and 43 instead of 95 s per step and window than the whole 2016x1152 frame.
        (tiles,) = self.nodes("DaWVUSpatialTiles")
        self.assertEqual(tiles["widgets_values"], [832, 480, 128])
        self.assertEqual(self.linked_from(tiles, "model"), ("ModelSamplingSD3", 0))
        (windows,) = self.nodes("WanContextWindowsManual")
        self.assertEqual(windows["widgets_values"][:4], [33, 8, "standard_static", 1])
        self.assertEqual(windows["widgets_values"][5], "pyramid")
        self.assertEqual(self.linked_from(windows, "model"), ("DaWVUSpatialTiles", 0))
        self.assertEqual(self.nodes("ModelSamplingSD3")[0]["widgets_values"], [5.0])
        self.assertEqual(self.nodes("LoraLoaderModelOnly")[0]["widgets_values"][1], 1.0)

    def test_wan_chain_per_block(self):
        (windows,) = self.nodes("WanContextWindowsManual")
        for sampler in self.nodes("KSampler"):
            self.assertEqual(self.linked_from(sampler, "model"), ("WanContextWindowsManual", 0))
            self.assertEqual(self.linked_from(sampler, "latent_image"), ("VAEEncodeTiled", 0))
        for resize in self.nodes("ResizeImageMaskNode"):
            self.assertEqual(self.linked_from(resize, "resize_type.width"), ("DaWVUPlanner", 3))
            self.assertEqual(self.linked_from(resize, "resize_type.height"), ("DaWVUPlanner", 4))
            self.assertEqual(resize["widgets_values"][-1], "lanczos")
        # The WAN VAE is causal: temporal tiles would restart it mid-block and show as a jump every tile.
        planner = self.nodes("DaWVUPlanner")[0]["widgets_values"]
        max_frames = round(planner[6] * 24) + 5 + 3  # longest block + lead-in + 4k+1 padding
        for kind in ("VAEEncodeTiled", "VAEDecodeTiled"):
            for node in self.nodes(kind):
                self.assertGreaterEqual(node["widgets_values"][2], max_frames, kind)
        # Read-only drop-ins: the core loaders charged the model and UMT5 files to the Windows commit limit.
        self.assertEqual((self.nodes("UNETLoader"), self.nodes("CLIPLoader")), ([], []))
        self.assertEqual(len(self.nodes("DaWVUReadOnlyUNETLoader")), 1)
        (clip,) = self.nodes("DaWVUReadOnlyCLIPLoader")
        self.assertEqual(clip["widgets_values"][1], "wan")
        for loader in ("DaWVUReadOnlyUNETLoader", "DaWVUReadOnlyCLIPLoader"):
            (node,) = self.nodes(loader)
            self.assertTrue(any(link[1] == node["id"] and link[5] in ("MODEL", "CLIP") for link in self.shipped["links"]))

    def test_model_widgets_match_the_pinned_manifest(self):
        shipped = {Path(entry["path"]).name for entry in self.models}
        used = set()
        for node in self.shipped["nodes"]:
            for value in node.get("widgets_values") or []:
                if isinstance(value, str) and value.endswith(".safetensors"):
                    used.add(value.split("\\")[-1])
        self.assertEqual(used, shipped)
        for entry in self.models:
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertEqual(len(entry["revision"]), 40)

    def test_no_private_test_media_is_shipped(self):
        raw = (ROOT / "workflows" / PATH).read_text(encoding="utf-8")
        for token in ("mvg_test", "Outro", "DaWasteh-Girl", "DaWasteh_Girl", "scene_0000", "sweep_2s"):
            self.assertNotIn(token, raw)


class HelperTests(unittest.TestCase):
    """Pure helpers of the shipped node sources (their modules need a ComfyUI runtime)."""

    @staticmethod
    def _functions(path: Path, names: set[str]) -> dict:
        import ast
        tree = ast.parse(path.read_text(encoding="utf-8"))
        keep = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        import importlib.util
        import math
        namespace = {"math": math}
        if importlib.util.find_spec("torch") is not None:
            import torch
            namespace["torch"] = torch
        exec(compile(ast.Module(body=keep, type_ignores=[]), str(path), "exec"), namespace)
        return namespace

    def test_lead_in_stays_inside_the_shot(self):
        lead_split = self._functions(ROOT / "custom_nodes/ComfyUI-DaWasteh-H3-MusicVideo/upscale_nodes.py", {"lead_split"})["lead_split"]
        self.assertEqual(lead_split(0, 5, [], False), (0, 5))            # video start: repeat the first frame
        self.assertEqual(lead_split(100, 5, [], False), (5, 0))          # inside a shot: real previous frames
        self.assertEqual(lead_split(100, 5, [98], False), (2, 3))        # never across a cut
        self.assertEqual(lead_split(100, 5, [100], True), (0, 5))        # block starts at a cut
        self.assertEqual(lead_split(100, 0, [50], False), (0, 0))        # off (H3, SeedVR2)

    def test_tiles_cover_the_frame_and_blend_back_exactly(self):
        import importlib.util
        if importlib.util.find_spec("torch") is None:
            self.skipTest("torch not installed (runs with the ComfyUI venv)")
        import torch
        ns = self._functions(ROOT / "custom_nodes/ComfyUI-DaWasteh-H3-MusicVideo/spatial_tiles.py", {"axis_tiles", "ramp", "tile_layout"})
        for height, width, count in ((144, 252, 9), (96, 168, 4), (60, 104, 1), (176, 312, 16)):  # 2016x1152, 1344x768, 832x480, 2496x1408
            tiles = ns["tile_layout"](height, width, 60, 104, 16)
            self.assertEqual(len(tiles), count)
            weight = torch.zeros(height, width)
            for y0, y1, x0, x1 in tiles:
                self.assertEqual((y0 % 2, x0 % 2), (0, 0))              # WAN patchifies 2x2 latent cells
                self.assertEqual((y1 - y0, x1 - x0), (min(60, height), min(104, width)))
                weight[y0:y1, x0:x1] += ns["ramp"](y1 - y0, y0 > 0, y1 < height, 16)[:, None] * ns["ramp"](x1 - x0, x0 > 0, x1 < width, 16)[None, :]
            self.assertGreater(float(weight.min()), 0.0)


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.2.6 GPU run")
class LiveEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.sha = staticmethod(lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest())

    def test_report_pins_shipped_workflow_sources_and_models(self):
        workflow = self.report["workflow"]
        self.assertEqual(workflow["path"], "workflows/" + PATH)
        self.assertEqual(workflow["sha256"], self.sha(workflow["path"]))
        for entry in self.report["sources"]:
            self.assertEqual(self.sha(entry["path"]), entry["sha256"], entry["path"])
        manifest = json.loads((ROOT / "tools/workflow_templates/v126/models.json").read_text(encoding="utf-8"))
        self.assertEqual([m["sha256"] for m in manifest], [m["sha256"] for m in self.report["model_verification"]["files"]])
        self.assertTrue(all(m["verified"] for m in self.report["model_verification"]["files"]))

    def test_pause_and_continue_produced_the_full_film_with_the_original_audio(self):
        runs = self.report["runs"]
        self.assertEqual((runs["pause"]["status"], runs["continue"]["status"]), ("success", "success"))
        self.assertNotIn("DaWVUFinalize", self.report["workflow"]["pause_node_classes"])
        self.assertIn("DaWVUFinalize", self.report["workflow"]["continue_node_classes"])
        film = self.report["final_film"]
        self.assertEqual(film["frames"], film["expected_frames"])
        self.assertEqual((film["width"], film["height"]), tuple(self.report["plan"]["target"]))
        self.assertTrue(film["audio_packets_identical"])

    def test_loop_run_renders_the_second_block_with_a_real_lead_in(self):
        loop = self.report["loop_run"]
        self.assertEqual((loop["runs"]["pause"]["status"], loop["runs"]["continue"]["status"]), ("success", "success"))
        self.assertIn("PixaromaLoopStart", loop["continue_node_classes"])
        self.assertEqual(loop["plan"]["blocks"], 2)
        self.assertEqual(loop["plan"]["lead_frames"], [5, 5])
        film = loop["final_film"]
        self.assertEqual(film["frames"], film["expected_frames"])
        self.assertTrue(film["audio_packets_identical"])

    def test_memory_run_at_the_music_video_default_resolution(self):
        run = self.report["memory_run"]
        self.assertEqual((run["runs"]["pause"]["status"], run["runs"]["continue"]["status"]), ("success", "success"))
        self.assertEqual(run["plan"]["blocks"], 1)                        # an 8.5 s scene stays one block
        self.assertEqual(run["plan"]["target"], [2496, 1408])             # 1664x928 x 1.5, snapped to 32 px
        self.assertEqual(run["final_film"]["frames"], run["final_film"]["expected_frames"])
        # Worst case measured (2496x1408, 209 frames incl. lead-in): 97.2 GB with the read-only loaders; the core loaders
        # stood at 93.5 GB before the decode already.
        self.assertLess(run["memory"]["commit_peak_gb"], run["memory"]["commit_limit_gb"])
        for key in ("loop_run",):
            self.assertLess(self.report[key]["memory"]["commit_peak_gb"], 90.0, key)
        self.assertLess(self.report["memory"]["commit_peak_gb"], 90.0)
        self.assertLess(self.report["runs"]["pause"]["seconds"], 1200)


if __name__ == "__main__":
    unittest.main()
