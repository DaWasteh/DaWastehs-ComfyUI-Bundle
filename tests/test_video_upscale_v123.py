"""v1.2.3 video upscaling: block planning helpers and the three rebuilt Nerdy Rodent upscale workflows."""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo"
spec = importlib.util.spec_from_file_location("dawasteh_mv2_upscale_test", PACK / "mv2.py")
assert spec is not None and spec.loader is not None
mv2 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mv2  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(mv2)


def _shipped_helpers() -> dict:
    """The pure planning helpers, compiled from the shipped node source (which itself needs a ComfyUI runtime)."""
    source = (PACK / "upscale_nodes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    keep = [node for node in tree.body
            if (isinstance(node, ast.FunctionDef) and node.name in {"align_count", "target_size", "plan_blocks", "_render_key"})
            or (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "") in {"FPS", "ALIGN_MODES", "BLOCK_FIELDS"} for t in node.targets))]
    namespace = {"np": np, "mv2": mv2}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(PACK / "upscale_nodes.py"), "exec"), namespace)
    return namespace


H = _shipped_helpers()
METHOD_FILES = {
    "ultimate": "Video Upscaling/MiniMax_H3-Ultimate-Upscale-FastH3.json",
    "latent3d": "Video Upscaling/MiniMax_H3-Latent-Upscaler-3D-FastH3.json",
    "seedvr2": "Video Upscaling/SeedVR2_3B_INT8-Video-Upscale.json",
}


class PlanningTests(unittest.TestCase):
    def test_alignment_pads_to_the_model_grid(self):
        for frames in range(5, 400):
            h3 = H["align_count"](frames, "h3 (17k+5)")
            self.assertEqual((h3 - 5) % 17, 0)
            self.assertTrue(0 <= h3 - frames < 17)
            sv = H["align_count"](frames, "seedvr2 (4k+1)")
            self.assertEqual((sv - 1) % 4, 0)
            self.assertTrue(0 <= sv - frames < 4)
            self.assertEqual(H["align_count"](frames, "none"), frames)
        self.assertEqual(H["ALIGN_MODES"], ["h3 (17k+5)", "seedvr2 (4k+1)", "none"])

    def test_target_size_is_on_the_32_px_grid(self):
        self.assertEqual(H["target_size"](864, 480, 1.5), (1280, 704))
        self.assertEqual(H["target_size"](480, 864, 1.5), (704, 1280))
        self.assertEqual(H["target_size"](608, 352, 2.0), (1216, 704))
        self.assertEqual(H["target_size"](10, 10, 0.1), (32, 32))

    def _motion(self, total: int, cuts: list[int], seed: int = 3) -> np.ndarray:
        rng = np.random.default_rng(seed)
        motion = rng.uniform(3.0, 9.0, total).astype(np.float32)
        motion[0] = 0.0
        # Busy stretch: a global threshold alone would flag it, the local test must not.
        if total > 1540:
            motion[1500:1540] = rng.uniform(20.0, 26.0, 40)
        for cut in cuts:
            motion[cut] = 60.0
        return motion

    def test_blocks_cover_every_frame_and_start_on_hard_cuts(self):
        total, cuts = 2160, [500, 1201, 1900]
        for target, low, high in ((4.0, 2.0, 4.45), (7.0, 2.0, 10.0)):
            settings = mv2.SplitSettings(target, low, high, 0)
            blocks, found = H["plan_blocks"](self._motion(total, cuts), total, settings, 18.0)
            self.assertEqual(found, cuts)
            self.assertEqual(blocks[0][0], 0)
            self.assertEqual(blocks[-1][1], total)
            for (a, b), (c, _) in zip(blocks, blocks[1:]):
                self.assertEqual(b, c)
            for a, b in blocks:
                self.assertLessEqual(b - a, int(round(high * 24)))
                self.assertGreaterEqual(b - a, int(round(low * 24)))
            starts = {a for a, _ in blocks}
            self.assertTrue(set(cuts) <= starts, (target, blocks))

    def test_render_key_survives_the_save_bookkeeping(self):
        # v1.2.3 E2E regression: the key hashed the whole block dict, which SaveBlock then extends, so no block
        # ever counted as finished (Finalize refused, resume re-rendered everything).
        manifest = {"key": "abc", "render_nonce": 0, "target_width": 1280, "target_height": 704,
                    "blocks": [{"index": 0, "start_frame": 0, "end_frame": 102, "frames": 102, "starts_at_cut": False}]}
        before = H["_render_key"](manifest, 0)
        manifest["blocks"][0].update({"render_key": before, "verified_frames": 102, "size": [1280, 704], "completed_at": 1.0})
        self.assertEqual(H["_render_key"](manifest, 0), before)
        manifest["render_nonce"] = 5
        self.assertNotEqual(H["_render_key"](manifest, 0), before)

    def test_short_video_is_one_block(self):
        blocks, _ = H["plan_blocks"](self._motion(200, []), 200, mv2.SplitSettings(7.0, 2.0, 10.0, 0), 18.0)
        self.assertEqual(blocks, [(0, 200)])


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.build_video_upscale_v123 import build_all
        cls.built = build_all()
        cls.shipped = {key: json.loads((ROOT / "workflows" / key).read_text(encoding="utf-8")) for key in METHOD_FILES.values()}
        cls.models = json.loads((ROOT / "tools/workflow_templates/v123/models.json").read_text(encoding="utf-8"))

    def nodes(self, method: str, kind: str) -> list[dict]:
        return [node for node in self.shipped[METHOD_FILES[method]]["nodes"] if node["type"] == kind]

    def linked_from(self, method: str, target: dict, name: str) -> tuple[str, int]:
        workflow = self.shipped[METHOD_FILES[method]]
        link_id = next(slot["link"] for slot in target["inputs"] if slot["name"] == name)
        link = next(link for link in workflow["links"] if link[0] == link_id)
        source = next(node for node in workflow["nodes"] if node["id"] == link[1])
        return source["type"], link[2]

    def test_builder_is_deterministic_and_matches_the_shipped_files(self):
        from tools.build_video_upscale_v123 import build_all
        self.assertEqual(set(self.built), set(METHOD_FILES.values()))
        self.assertEqual(build_all(), self.built)
        for key, workflow in self.built.items():
            self.assertEqual(workflow, self.shipped[key], key)

    def test_every_workflow_has_the_shared_block_frame(self):
        for method in METHOD_FILES:
            with self.subTest(method=method):
                for kind, count in (("DaWVUPlanner", 1), ("DaWVULoadBlock", 2), ("DaWVUSaveBlock", 2), ("DaWVUFinalize", 1),
                                    ("PixaromaPauseImage", 1), ("PixaromaLoopStart", 1), ("PixaromaLoopEnd", 1),
                                    ("PixaromaRunTimer", 1), ("DaWMultiGPUDeviceControl", 1)):
                    self.assertEqual(len(self.nodes(method, kind)), count, kind)
                loop_start = self.nodes(method, "PixaromaLoopStart")[0]
                self.assertEqual(self.linked_from(method, loop_start, "total"), ("DaWVUPlanner", 2))
                loads = sorted(self.nodes(method, "DaWVULoadBlock"), key=lambda n: n["widgets_values"][1])
                self.assertEqual([n["widgets_values"][1] for n in loads], [0, 1])
                self.assertEqual(self.linked_from(method, loads[1], "block_index"), ("PixaromaLoopStart", 6))
                control = self.nodes(method, "DaWMultiGPUDeviceControl")[0]
                self.assertEqual(control["widgets_values"], ["gpu:0", "gpu:0", "gpu:0"])

    def test_measured_method_settings(self):
        planners = {m: self.nodes(m, "DaWVUPlanner")[0]["widgets_values"] for m in METHOD_FILES}
        self.assertEqual(planners["ultimate"][3:9], [1.5, 7.0, 2.0, 10.0, 18.0, "ultimate"])
        self.assertEqual(planners["latent3d"][3:9], [1.5, 4.0, 2.0, 4.45, 18.0, "latent3d"])
        self.assertEqual(planners["seedvr2"][3:9], [1.5, 7.0, 2.0, 10.0, 18.0, "seedvr2"])
        # Denoise 0.25, not Rodent's 0.45/0.4: with FastH3's shift 10 those start at 97 %/85 % noise on finished footage.
        self.assertEqual(self.nodes("ultimate", "BasicScheduler")[0]["widgets_values"], ["linear_quadratic", 4, 0.25])
        self.assertEqual(self.nodes("latent3d", "BasicScheduler")[0]["widgets_values"], ["beta", 2, 0.25])
        # Learned 3D latent upscale inside Ultimate: bicubic at denoise 0.25 turned latent blocks into invented objects.
        self.assertEqual(self.nodes("ultimate", "MMH3LatentUpscaleParams"), [])
        (model_up,) = self.nodes("ultimate", "MMH3LatentUpscaleWithModelParams")
        self.assertEqual(model_up["widgets_values"], ["minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors", 1280, 704, "cuda", "bf16"])
        self.assertEqual(self.linked_from("ultimate", model_up, "width"), ("DaWVUPlanner", 3))
        for up in self.nodes("latent3d", "MinimaxH3LatentUpscaler3D"):
            self.assertEqual(up["widgets_values"][1:], ["target dimensions", 1280, 704, 32, True, True, "rocm", "bf16"])
            self.assertEqual(self.linked_from("latent3d", up, "mode.width"), ("DaWVUPlanner", 3))
            self.assertEqual(self.linked_from("latent3d", up, "mode.height"), ("DaWVUPlanner", 4))
        for resize in self.nodes("seedvr2", "ResizeImageMaskNode"):
            self.assertEqual(resize["widgets_values"], ["scale dimensions", 1280, 704, "disabled", "lanczos"])
            self.assertEqual(self.linked_from("seedvr2", resize, "resize_type.width"), ("DaWVUPlanner", 3))
        self.assertEqual({n["widgets_values"][0] for n in self.nodes("seedvr2", "VAEEncodeTiled")}, {1024})
        self.assertEqual({n["widgets_values"][0] for n in self.nodes("seedvr2", "VAEDecodeTiled")}, {512})
        for load in self.nodes("seedvr2", "DaWVULoadBlock"):
            self.assertEqual(load["widgets_values"][2], "seedvr2 (4k+1)")
        self.assertEqual(self.nodes("seedvr2", "PixaromaPrompt"), [])

    def test_model_widgets_match_the_pinned_manifest(self):
        shipped = {Path(entry["path"]).name for entry in self.models}
        for method in METHOD_FILES:
            for node in self.shipped[METHOD_FILES[method]]["nodes"]:
                for value in node.get("widgets_values") or []:
                    if isinstance(value, str) and value.endswith(".safetensors"):
                        self.assertIn(value.split("\\")[-1], shipped, (method, node["type"]))
        for entry in self.models:
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertEqual(len(entry["revision"]), 40)
            self.assertTrue(set(entry["methods"]) <= set(METHOD_FILES))

    def test_no_private_test_media_is_shipped(self):
        for key in METHOD_FILES.values():
            raw = (ROOT / "workflows" / key).read_text(encoding="utf-8")
            for token in ("mvg_test", "Outro", "DaWasteh-Girl", "DaWasteh_Girl"):
                self.assertNotIn(token, raw, key)


class LiveEvidenceTests(unittest.TestCase):
    """The committed end-to-end evidence must describe exactly the shipped files."""

    @classmethod
    def setUpClass(cls):
        import hashlib
        cls.sha = staticmethod(lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest())
        cls.report = json.loads((ROOT / "performance/rdna4/video-upscale-v123-validation.json").read_text(encoding="utf-8"))

    def test_report_pins_shipped_workflows_sources_and_models(self):
        self.assertEqual(set(self.report["methods"]), set(METHOD_FILES))
        for method, entry in self.report["methods"].items():
            self.assertEqual(entry["workflow"]["path"], "workflows/" + METHOD_FILES[method])
            self.assertEqual(entry["workflow"]["sha256"], self.sha(entry["workflow"]["path"]), method)
        for entry in self.report["sources"]:
            self.assertEqual(self.sha(entry["path"]), entry["sha256"], entry["path"])
        manifest = json.loads((ROOT / "tools/workflow_templates/v123/models.json").read_text(encoding="utf-8"))
        self.assertEqual([m["sha256"] for m in manifest], [m["sha256"] for m in self.report["model_verification"]["files"]])

    def test_every_method_produced_the_full_film_with_the_original_audio(self):
        for method, entry in self.report["methods"].items():
            with self.subTest(method=method):
                runs = entry["runs"]
                self.assertEqual((runs["pause"]["status"], runs["continue"]["status"]), ("success", "success"))
                self.assertNotIn("DaWVUFinalize", entry["workflow"]["pause_node_classes"])
                self.assertIn("DaWVUFinalize", entry["workflow"]["continue_node_classes"])
                film = entry["final_film"]
                self.assertEqual(film["frames"], film["expected_frames"])
                self.assertEqual((film["width"], film["height"]), (1280, 704))
                self.assertTrue(film["audio_packets_identical"])
                self.assertEqual(entry["plan"]["blocks"], len(entry["plan"]["block_seconds"]))
                max_frames = round((4.45 if method == "latent3d" else 10.0) * 24)  # 107 = 17*6+5 for Latent 3D
                self.assertLessEqual(round(max(entry["plan"]["block_seconds"]) * 24), max_frames)


if __name__ == "__main__":
    unittest.main()
