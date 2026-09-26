"""v1.2.7 MV 5c: optional upscale of every accepted music-video scene (four methods), upscaled film + comparison."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo"
COMFY = Path(os.environ.get("COMFYUI_PATH", "L:/ComfyUI/ComfyUI"))
sys.path.insert(0, str(ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


up = _load("dawasteh_upscale_mv_v127_test", PACK / "upscale_mv.py")


def _graph_utils():
    """ComfyUI's own GraphBuilder (pure Python) under its real module name."""
    if "comfy_execution.graph_utils" in sys.modules:
        return sys.modules["comfy_execution.graph_utils"]
    path = COMFY / "comfy_execution" / "graph_utils.py"
    if not path.is_file():
        return None
    package = sys.modules.setdefault("comfy_execution", types.ModuleType("comfy_execution"))
    module = _load("comfy_execution.graph_utils", path)
    package.graph_utils = module
    return module


def _schemas() -> dict:
    merged = {}
    for folder in ("v123", "v126", "v122"):
        merged.update(json.loads((ROOT / "tools/workflow_templates" / folder / "node-schemas.json").read_text(encoding="utf-8")))
    return merged


class MethodTests(unittest.TestCase):
    def test_four_methods_in_a_fixed_order_and_labels_map_back(self):
        self.assertEqual([up.method_key(label) for label in up.LABELS], [up.WAN22, up.SEEDVR2, up.LATENT3D, up.ULTIMATE])
        for key in up.METHODS:
            self.assertEqual(up.method_key(key), key)   # scripts may pass the bare key
        with self.assertRaises(ValueError):
            up.method_key("Real-ESRGAN")
        self.assertEqual(up.MODEL_METHODS, [up.SEEDVR2, up.WAN22])
        self.assertEqual({k for k, s in up.METHODS.items() if s["h3"]}, {up.LATENT3D, up.ULTIMATE})

    def test_target_size_follows_the_long_side_on_the_32px_grid(self):
        self.assertEqual(up.target_for(960, 544, 1920), (1920, 1088))
        self.assertEqual(up.target_for(1280, 704, 1920), (1920, 1056))
        self.assertEqual(up.target_for(1664, 928, 1920), (1920, 1056))
        self.assertEqual(up.target_for(544, 960, 1920), (1088, 1920))   # portrait
        self.assertEqual(up.target_for(1920, 1088, 1280), (1920, 1088))   # never smaller than the render
        for w, h in (up.target_for(864, 480, 1920), up.target_for(1216, 672, 2560)):
            self.assertEqual((w % 32, h % 32), (0, 0))

    def test_resume_key_follows_take_method_size_and_settings(self):
        scene = {"index": 2, "frames": 130, "render_key": "a"}
        base = up.upscale_key(scene, up.SEEDVR2, 1920, 1088)
        self.assertEqual(base, up.upscale_key(dict(scene), up.SEEDVR2, 1920, 1088))
        self.assertNotEqual(base, up.upscale_key({**scene, "render_key": "b"}, up.SEEDVR2, 1920, 1088))   # other take
        self.assertNotEqual(base, up.upscale_key(scene, up.WAN22, 1920, 1088))
        self.assertNotEqual(base, up.upscale_key(scene, up.SEEDVR2, 1920, 1056))
        old = up.METHODS[up.SEEDVR2]["version"]
        try:
            up.METHODS[up.SEEDVR2]["version"] = old + 1
            self.assertNotEqual(base, up.upscale_key(scene, up.SEEDVR2, 1920, 1088))
        finally:
            up.METHODS[up.SEEDVR2]["version"] = old

    def test_done_needs_key_frames_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            scene = {"index": 1, "frames": 179, "render_key": "r"}
            tag, key = up.tag_for(up.WAN22, 1920, 1088), up.upscale_key(scene, up.WAN22, 1920, 1088)
            self.assertEqual(tag, "wan22_1920x1088")
            self.assertFalse(up.upscaled_done(project, scene, tag, key))
            scene["upscaled"] = {tag: {"key": key, "verified_frames": 179}}
            self.assertFalse(up.upscaled_done(project, scene, tag, key), "no file yet")
            video = up.upscaled_files(project, 1, tag)["video"]
            video.parent.mkdir(parents=True)
            video.write_bytes(b"mp4")
            self.assertTrue(up.upscaled_done(project, scene, tag, key))
            self.assertFalse(up.upscaled_done(project, {**scene, "frames": 180}, tag, key))
            self.assertFalse(up.upscaled_done(project, scene, tag, "other"))
            self.assertEqual(video, project / "upscaled" / "wan22_1920x1088" / "scene_0001.mp4")

    def test_lead_in_uses_the_previous_scene_or_repeats_the_first_frame(self):
        self.assertEqual(up.lead_frames(up.WAN22, 0, 0), (0, 5))
        self.assertEqual(up.lead_frames(up.WAN22, 1, 152), (5, 0))
        self.assertEqual(up.lead_frames(up.WAN22, 1, 3), (3, 2))
        for method in (up.SEEDVR2, up.LATENT3D, up.ULTIMATE):
            self.assertEqual(up.lead_frames(method, 4, 150), (0, 0))

    def test_missing_packs_and_models_are_named(self):
        problems = up.missing_requirements(up.ULTIMATE, {"RandomNoise"}, lambda folder, name: False)
        self.assertTrue(any("MMH3UltimateUpscale" in p and "PlagueKind" in p for p in problems))
        self.assertIn("Modell fehlt: models/latent_upscale_models/" + up.LATENT_UPSCALER, problems)
        everything = {c for spec in up.METHODS.values() for c in spec["classes"]}
        for method in up.METHODS:
            self.assertEqual(up.missing_requirements(method, everything, lambda folder, name: True), [])

    def test_schema_defaults_fill_only_missing_widgets(self):
        node = types.SimpleNamespace(class_type="X", inputs={"model": ["1", 0], "a": 5})
        schema = {"required": {"model": ["MODEL", {}], "a": ["INT", {"default": 1}], "b": ["BOOLEAN", {"default": False}],
                               "c": [["x", "y"], {}], "d": ["COMBO", {"options": ["p", "q"]}], "e": ["LATENT", {}]}}
        self.assertEqual(up.fill_defaults([node], lambda kind: schema), ["X.b", "X.c", "X.d"])
        self.assertEqual(node.inputs, {"model": ["1", 0], "a": 5, "b": False, "c": "x", "d": "p"})


class ModelCacheTests(unittest.TestCase):
    def test_models_are_held_weakly_and_the_wan_conditioning_strongly(self):
        import gc
        import weakref

        class Loaded:
            pass

        model, vae = Loaded(), Loaded()
        try:
            up._CACHE.update(key=(up.WAN22, 1), refs=(weakref.ref(model), weakref.ref(vae)))
            up._CACHE["conditioning"][(up.WAN22, 1)] = ("positive", "negative")
            self.assertEqual(up._alive(), (model, vae))
            del model   # ComfyUI dropped its cached output (end of run, RAM pressure, 'Free model and node cache')
            gc.collect()
            self.assertIsNone(up._alive(), "no copy survives outside ComfyUI's cache")
            self.assertIn((up.WAN22, 1), up._CACHE["conditioning"], "a reload does not need UMT5 again")
        finally:
            up.release_upscale_models()
        self.assertEqual((up._CACHE["refs"], up._CACHE["conditioning"]), (None, {}))


class SameSettingsAsTheStandaloneWorkflowsTests(unittest.TestCase):
    """MV 5c must upscale exactly like the live-tested workflows in Video Upscaling/."""

    def test_seedvr2_and_h3_methods_match_v123(self):
        from tools import build_video_upscale_v123 as v123
        self.assertEqual((up.SEEDVR2_FILES["model"], up.SEEDVR2_FILES["vae"], up.LATENT_UPSCALER),
                         (v123.SEEDVR2_MODEL, v123.SEEDVR2_VAE, v123.LATENT_UPSCALER))
        for method in (up.LATENT3D, up.ULTIMATE):
            self.assertEqual(up.METHODS[method]["schedule"], {k: v123.METHODS[method]["sampling"][k] for k in ("scheduler", "steps", "denoise")})
            self.assertEqual(up.METHODS[method]["align"], v123.METHODS[method]["align"])
        self.assertEqual(up.METHODS[up.SEEDVR2]["align"], v123.METHODS["seedvr2"]["align"])
        shipped = {}
        for method, spec in v123.METHODS.items():
            workflow = json.loads((ROOT / "workflows" / spec["path"]).read_text(encoding="utf-8"))
            shipped[method] = {n["type"]: n["widgets_values"] for n in workflow["nodes"] if (n.get("title") or "").startswith("LOOP")
                               or n["type"].startswith("MMH3")}
        s = up.METHODS[up.SEEDVR2]
        self.assertEqual(shipped["seedvr2"]["VAEEncodeTiled"], list(s["encode_tile"]))
        self.assertEqual(shipped["seedvr2"]["VAEDecodeTiled"], list(s["decode_tile"]))
        self.assertEqual(shipped["seedvr2"]["SeedVR2TemporalChunk"], [s["chunk_overlap"], "auto"])
        k = s["sampler"]
        self.assertEqual(shipped["seedvr2"]["KSampler"], [k["seed"], "fixed", k["steps"], k["cfg"], k["sampler_name"], k["scheduler"], k["denoise"]])
        # the one deliberate deviation: colour correction "lab" (measured at x2, see upscale_mv.METHODS)
        self.assertEqual((shipped["seedvr2"]["SeedVR2PostProcessing"], s["color_correction"]), (["none"], "lab"))
        u = up.METHODS[up.ULTIMATE]
        self.assertEqual(shipped["ultimate"]["MMH3TemporalSplitParams"], list(u["temporal"].values()))
        spatial = shipped["ultimate"]["MMH3SpatialSplitParams"]
        self.assertEqual(spatial[2:], list(u["spatial"].values()))
        self.assertEqual(shipped["ultimate"]["MMH3LatentUpscaleWithModelParams"][3:], [u["upscale_param"]["device"], u["upscale_param"]["precision"]])
        self.assertEqual(shipped["ultimate"]["MMH3UltimateUpscale"], [u["cfg"]])
        latent = shipped["latent3d"]["MinimaxH3LatentUpscaler3D"]
        self.assertEqual(latent[0], up.LATENT_UPSCALER)
        self.assertEqual(latent[4:], list(up.METHODS[up.LATENT3D]["upscaler"].values()))
        for method in (up.LATENT3D, up.ULTIMATE):
            self.assertEqual(shipped[method]["RandomNoise"][0], up.METHODS[method]["noise_seed"])

    def test_wan_matches_v126(self):
        from tools import build_video_upscale_wan_v126 as v126
        s, w = v126.SETTINGS, up.METHODS[up.WAN22]
        self.assertEqual((up.WAN_FILES["model"], up.WAN_FILES["lora"], up.WAN_FILES["text_encoder"], up.WAN_FILES["vae"]),
                         (v126.MODEL, v126.LORA, v126.TEXT_ENCODER, v126.VAE))
        self.assertEqual((up.WAN_PROMPT, up.WAN_NEGATIVE), (v126.PROMPT, v126.NEGATIVE))
        self.assertEqual((w["shift"], w["lora_strength"], w["lead"], w["align"]), (s["shift"], s["lora_strength"], s["lead_frames"], v126.ALIGN))
        self.assertEqual((w["tiles"], w["windows"], w["sampler"]), (s["tiles"], s["windows"], s["sampler"]))
        self.assertEqual(w["encode_tile"], (*s["encode_tile"], *s["temporal_tile"]))
        self.assertEqual(w["decode_tile"], (*s["decode_tile"], *s["temporal_tile"]))


class ChainTests(unittest.TestCase):
    """The expansion MV 5c returns: every required input present (after the schema defaults), links in place."""

    @classmethod
    def setUpClass(cls):
        cls.gu = _graph_utils()
        if cls.gu is None:
            raise unittest.SkipTest(f"ComfyUI not found at {COMFY} (set COMFYUI_PATH)")
        cls.schemas = _schemas()

    def expand(self, method: str):
        graph = self.gu.GraphBuilder(prefix="9.0.0.")
        source = graph.node("DaWMV2UpscaleSource", scene="plan|2|key", method=method)
        models = graph.node("DaWMV2UpscaleModels", method=method) if method in up.MODEL_METHODS else None
        links = {"model": ["15", 0], "vae": ["71", 0], "audio_vae": ["72", 0]}
        images = up.build_chain(graph, method, source, models, links, 1920, 1088)
        save = graph.node("DaWMV2UpscaleSave", scene="plan|2|key", images=images, lead=source.out(3), method=method,
                          width=1920, height=1088, key="k", started=1.0)
        filled = up.fill_defaults(graph.nodes.values(),
                                  lambda kind: self.schemas[kind]["input"] if kind in self.schemas else {"required": {}})
        return graph.finalize(), save, filled

    def check_required(self, nodes):
        for node_id, node in nodes.items():
            schema = self.schemas.get(node["class_type"])
            if schema is None:
                continue   # MV 5c internals (not in the saved schema files)
            for name in schema["input"].get("required", {}):
                self.assertIn(name, node["inputs"], (node["class_type"], name))

    def classes(self, nodes):
        return sorted(n["class_type"] for n in nodes.values())

    def test_seedvr2_chain(self):
        nodes, save, _ = self.expand(up.SEEDVR2)
        self.check_required(nodes)
        by = {n["class_type"]: n for n in nodes.values()}
        self.assertEqual(set(self.classes(nodes)) - {"DaWMV2UpscaleSource", "DaWMV2UpscaleModels", "DaWMV2UpscaleSave"},
                         set(up.METHODS[up.SEEDVR2]["classes"]))
        resize = by["ResizeImageMaskNode"]["inputs"]
        self.assertEqual((resize["resize_type"], resize["resize_type.width"], resize["resize_type.height"], resize["scale_method"]),
                         ("scale dimensions", 1920, 1088, "lanczos"))
        self.assertEqual(by["SeedVR2TemporalChunk"]["inputs"]["chunking_mode"], "auto")
        self.assertEqual(by["KSampler"]["inputs"]["denoise"], 1.0)
        self.assertNotIn(["15", 0], [v for n in nodes.values() for v in n["inputs"].values()], "SeedVR2 never touches FastH3")

    def test_wan_chain_has_tiles_windows_and_every_required_widget(self):
        nodes, _, filled = self.expand(up.WAN22)
        self.check_required(nodes)
        by = {n["class_type"]: n for n in nodes.values()}
        self.assertEqual(by["DaWVUSpatialTiles"]["inputs"]["tile_width"], 832)
        windows = by["WanContextWindowsManual"]["inputs"]
        self.assertEqual((windows["context_length"], windows["context_overlap"], windows["split_conds_to_windows"]), (33, 8, False))
        self.assertEqual(by["KSampler"]["inputs"]["denoise"], 0.15)
        self.assertEqual(by["KSampler"]["inputs"]["model"][0], [k for k, n in nodes.items() if n["class_type"] == "WanContextWindowsManual"][0])

    def test_h3_chains_reuse_the_running_fasth3_and_the_scene_prompt(self):
        for method in (up.LATENT3D, up.ULTIMATE):
            nodes, _, _ = self.expand(method)
            self.check_required(nodes)
            by = {n["class_type"]: (k, n) for k, n in nodes.items()}
            source_id = by["DaWMV2UpscaleSource"][0]
            self.assertNotIn("DaWMV2UpscaleModels", by)
            self.assertEqual(by["DaWH3VideoToAVLatent"][1]["inputs"]["vae"], ["71", 0])
            self.assertEqual(by["DaWH3VideoToAVLatent"][1]["inputs"]["audio_vae"], ["72", 0])
            self.assertEqual(by["BasicScheduler"][1]["inputs"]["model"], ["15", 0])
            self.assertEqual(by["VAEDecode"][1]["inputs"]["vae"], ["71", 0])
            if method == up.LATENT3D:
                inputs = by["MinimaxH3LatentUpscaler3D"][1]["inputs"]
                self.assertEqual((inputs["mode"], inputs["mode.width"], inputs["mode.height"]), ("target dimensions", 1920, 1088))
                self.assertEqual(by["BasicGuider"][1]["inputs"], {"model": ["15", 0], "conditioning": [source_id, 2]})
            else:
                inputs = by["MMH3UltimateUpscale"][1]["inputs"]
                self.assertEqual((inputs["model"], inputs["conditioning"]), (["15", 0], [source_id, 2]))
                self.assertEqual(by["MMH3LatentUpscaleWithModelParams"][1]["inputs"]["width"], 1920)

    def test_save_gets_the_lead_in_and_the_upscaled_frames(self):
        for method in up.METHODS:
            nodes, save, _ = self.expand(method)
            source_id = next(k for k, n in nodes.items() if n["class_type"] == "DaWMV2UpscaleSource")
            self.assertEqual(nodes[save.id]["inputs"]["lead"], [source_id, 3])
            self.assertIn(nodes[save.id]["inputs"]["images"][0], nodes)


class JoinTests(unittest.TestCase):
    def make_project(self, tmp: Path, done=(0, 1, 2)):
        manifest = {"project_name": "Song", "source_audio": str(tmp / "source_audio.mp3"),
                    "upscale": {"enabled": True, "method": up.SEEDVR2, "size": [1920, 1088], "tag": "seedvr2_1920x1088"},
                    "scenes": []}
        for index in range(3):
            scene = {"index": index, "frames": 100 + index, "render_key": f"r{index}"}
            if index in done:
                scene["upscaled"] = {"seedvr2_1920x1088": {"key": up.upscale_key(scene, up.SEEDVR2, 1920, 1088),
                                                           "verified_frames": scene["frames"], "size": [1920, 1088]}}
                video = up.upscaled_files(tmp, index, "seedvr2_1920x1088")["video"]
                video.parent.mkdir(parents=True, exist_ok=True)
                video.write_bytes(b"mp4")
            manifest["scenes"].append(scene)
        return manifest

    def test_upscaled_film_and_comparison_with_the_original_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest = self.make_project(tmp)
            calls = []
            result = up.join_upscaled(str(tmp / "plan.json"), manifest, "ffmpeg", "20260926-120000", "mp4", tmp / "films",
                                      tmp / "joined_video_silent.mp4", True, lambda cmd, timeout: calls.append(cmd),
                                      lambda ffmpeg, path: 303)
            concat = (tmp / "concat_upscaled.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(concat), 3)
            self.assertTrue(concat[0].endswith("upscaled/seedvr2_1920x1088/scene_0000.mp4'"))
            mux, compare = calls[1], calls[2]
            self.assertEqual(mux[-1], str(tmp / "films" / "Song_20260926-120000_upscale_seedvr2_1920x1088.mp4"))
            self.assertIn("-c:a", mux)
            self.assertEqual(mux[mux.index("-c:a") + 1], "copy")
            graph = compare[compare.index("-filter_complex") + 1]
            self.assertIn("scale=1920:1088:flags=lanczos", graph)
            self.assertIn("hstack=inputs=2", graph)
            self.assertEqual(compare[compare.index("-c:a") + 1], "copy")
            self.assertEqual((result["upscaled_frames"], result["size"]), (303, [1920, 1088]))
            self.assertTrue(result["comparison"].endswith("_vergleich_original_vs_seedvr2.mp4"))

    def test_missing_upscale_is_reported_not_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest = self.make_project(tmp, done=(0, 2))
            with self.assertRaisesRegex(RuntimeError, r"scenes \[2\]"):
                up.join_upscaled(str(tmp / "plan.json"), manifest, "ffmpeg", "s", "mp4", tmp, tmp / "x.mp4", False,
                                 lambda cmd, timeout: None, lambda ffmpeg, path: 0)


class WorkflowV127Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.build_h3_music_video_v122 import PATH, RELEASE, build_all
        cls.path, cls.release = PATH, RELEASE
        cls.workflow = build_all()[PATH]
        cls.nodes = {n["id"]: n for n in cls.workflow["nodes"]}
        cls.links = {l[0]: l for l in cls.workflow["links"]}

    def source(self, node, name):
        slot = next(i for i in node["inputs"] if i["name"] == name)
        link = self.links[slot["link"]]
        return self.nodes[link[1]], link[2]

    def test_shipped_file_is_the_build_and_the_release_is_marked(self):
        shipped = json.loads((ROOT / "workflows" / self.path).read_text(encoding="utf-8"))
        self.assertEqual(shipped, self.workflow)
        self.assertEqual(self.workflow["extra"]["dawasteh_h3_music_video_v122"]["release"], "v1.2.7")

    def test_one_switch_feeds_both_upscale_nodes_behind_the_reviews(self):
        settings = [n for n in self.nodes.values() if n["type"] == "DaWMV2UpscaleSettings"]
        scenes = [n for n in self.nodes.values() if n["type"] == "DaWMV2UpscaleScene"]
        self.assertEqual((len(settings), len(scenes)), (1, 2))
        self.assertEqual(settings[0]["widgets_values"], [True, up.LABELS[0], 1920])
        for node in scenes:
            self.assertEqual(self.source(node, "upscale")[0]["id"], settings[0]["id"])
            self.assertEqual(self.source(node, "scene")[0]["type"], "DaWMV2ReviewScene")
            self.assertEqual(self.source(node, "model")[0]["type"], "BlockSparseAttention")
            vae, audio = self.source(node, "vae")[0], self.source(node, "audio_vae")[0]
            self.assertEqual({vae["type"], audio["type"]}, {"SelectVAEDevice"})
            self.assertNotEqual(vae["id"], audio["id"])
        start = next(n for n in self.nodes.values() if n["type"] == "PixaromaLoopStart")
        end = next(n for n in self.nodes.values() if n["type"] == "PixaromaLoopEnd")
        self.assertEqual(self.source(start, "value1")[0]["type"], "DaWMV2UpscaleScene")
        self.assertEqual(self.source(end, "value1")[0]["type"], "DaWMV2UpscaleScene")
        self.assertNotEqual(self.source(start, "value1")[0]["id"], self.source(end, "value1")[0]["id"])
        final = next(n for n in self.nodes.values() if n["type"] == "DaWMV2Finalize")
        self.assertEqual(final["widgets_values"], ["auto", "nebeneinander"])

    def test_the_users_size_list_is_shipped(self):
        sizes = next(n for n in self.nodes.values() if n["type"] == "PixaromaSizes")
        for state in (sizes["widgets_values"][0], json.loads(sizes["properties"]["sizesState"])):
            self.assertEqual(state["sizes"][state["selected"]], [960, 544])
            self.assertEqual((state["w"], state["h"]), (960, 544))
            self.assertIn([1280, 704], state["sizes"])
            self.assertIn([1664, 928], state["sizes"])
            # Pixaroma's pairKey is "short x long": these two keys star 960x544 and 1280x704
            self.assertTrue({"544x960", "704x1280"} <= set(state["starred"]))

    def test_schema_file_and_notes(self):
        schema = json.loads((ROOT / "tools/workflow_templates/v122/node-schemas.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["DaWMV2UpscaleSettings"]["input_order"]["required"], ["upscale", "method", "target_long_side"])
        self.assertEqual(schema["DaWMV2UpscaleSettings"]["input"]["required"]["method"][1]["options"], up.LABELS)
        self.assertEqual(schema["DaWMV2UpscaleScene"]["input_order"], {"required": ["scene", "upscale"],
                                                                       "optional": ["model", "vae", "audio_vae"],
                                                                       "hidden": ["unique_id", "dynprompt"]})
        self.assertIn("comparison", schema["DaWMV2Finalize"]["input_order"]["optional"])
        notes = "\n".join(n["widgets_values"][0] for n in self.workflow["nodes"] if n["type"] == "MarkdownNote")
        for text in ("MV 5c", "Verworfene Takes", "nebeneinander", "seedvr2_3b_int8_convrot", "wan2.2_t2v_low_noise_14B",
                     up.LATENT_UPSCALER):
            self.assertIn(text, notes, text)

    def test_nodes_are_registered(self):
        source = (PACK / "nodes_v2.py").read_text(encoding="utf-8")
        for name in ("DaWMV2UpscaleSettings", "DaWMV2UpscaleScene", "DaWMV2UpscaleSource", "DaWMV2UpscaleModels",
                     "DaWMV2UpscaleSave"):
            self.assertIn(f'node_id="{name}"', source)
            self.assertIn(name, source[source.index("V2_NODES = ["):])


class LiveEvidenceTests(unittest.TestCase):
    """The committed live runs (method comparison, SeedVR2 A/B, end-to-end through the real frontend) describe the
    shipped files."""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "performance/rdna4/h3-music-video-v127-upscale-validation.json").read_text(encoding="utf-8"))

    def test_report_pins_the_shipped_workflow_and_sources(self):
        import hashlib
        for entry in [self.report["workflow"], *self.report["sources"]]:
            self.assertEqual(hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest(), entry["sha256"], entry["path"])

    def test_all_four_methods_ran_and_wan_is_the_measured_default(self):
        methods = self.report["method_comparison"]["methods"]
        self.assertEqual(sorted(methods), sorted(f"{m}_1920x1088" for m in up.METHODS))
        self.assertTrue(all(row["frames"] == 130 and row["seconds"] > 0 for row in methods.values()))
        self.assertEqual(up.method_key(up.LABELS[0]), up.WAN22)
        self.assertIn("default", methods["wan22_1920x1088"]["verdict"])
        seed = self.report["seedvr2"]
        self.assertIn("bit-identical", seed["mv5c_vs_v123_graph"])
        self.assertLess(seed["color_correction_x2"]["lab"]["chroma_error"], seed["color_correction_x2"]["none"]["chroma_error"])
        self.assertEqual((seed["color_correction_x2"]["shipped"], up.METHODS[up.SEEDVR2]["color_correction"]), ("lab", "lab"))

    def test_only_accepted_takes_were_upscaled_each_before_the_next_scene(self):
        run = self.report["end_to_end"]
        self.assertEqual(run["setting"]["method"], up.WAN22)
        clicks = [d["click"] for d in run["decisions"]]
        self.assertEqual(len(clicks), 5)
        self.assertTrue(clicks[0].endswith("Neu rendern") and clicks[3].endswith("Neu rendern"))
        self.assertTrue(all(o["upscale_before_next_review"] for o in run["ordering"]))
        for scene in run["scenes"]:
            self.assertEqual(scene["upscaled_take"], scene["take"], scene)
            self.assertEqual(scene["frames"], scene["expected"])
            self.assertTrue(scene["upscale_is_the_accepted_take"], scene)
        scene1, _, scene3 = run["scenes"]
        self.assertEqual((scene1["take"], list(scene1["archived"])), (1, ["0"]), "redo: take 2 accepted, take 1 rejected")
        self.assertEqual((scene3["take"], list(scene3["archived"])), (0, ["1"]), "earlier take restored and upscaled")

    def test_three_films_with_the_original_audio(self):
        films = self.report["end_to_end"]["films"]
        expected = films["expected_frames"]
        for name in ("original", "upscaled", "comparison"):
            self.assertEqual(films[name]["frames"], expected, name)
            self.assertTrue(films[name]["audio_packets_identical"], name)
        self.assertEqual(films["original"]["size"], [960, 544])
        self.assertEqual(films["upscaled"]["size"], [1920, 1088])
        self.assertEqual(films["comparison"]["size"], [3840, 1088])


if __name__ == "__main__":
    unittest.main()
