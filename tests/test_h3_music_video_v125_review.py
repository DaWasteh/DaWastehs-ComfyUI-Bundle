"""v1.2.5 MV 5b scene review: takes, approval state, redo by cloning the scene chain, the waiting gate, graph + frontend."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo"
COMFY = Path(os.environ.get("COMFYUI_PATH", "L:/ComfyUI/ComfyUI"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mv2 = _load("dawasteh_mv2_v125_review_test", PACK / "mv2.py")
review = _load("dawasteh_review_v125_test", PACK / "review.py")


def _graph_utils():
    """ComfyUI's own GraphBuilder (pure Python) under its real module name, so review.py imports it unchanged."""
    if "comfy_execution.graph_utils" in sys.modules:
        return sys.modules["comfy_execution.graph_utils"]
    path = COMFY / "comfy_execution" / "graph_utils.py"
    if not path.is_file():
        return None
    package = sys.modules.setdefault("comfy_execution", types.ModuleType("comfy_execution"))
    module = _load("comfy_execution.graph_utils", path)
    package.graph_utils = module
    return module


def _render_key_helper():
    source = (PACK / "nodes_v2.py").read_text(encoding="utf-8")
    keep = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "_render_key"]
    namespace = {"mv2": mv2, "Any": object}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(PACK / "nodes_v2.py"), "exec"), namespace)
    return namespace["_render_key"]


render_key = _render_key_helper()


def scene_files(project: Path, index: int) -> dict[str, Path]:
    """Same layout as nodes_v2._scene_files."""
    return {"video": project / "scenes" / f"scene_{index:04d}.mp4",
            "tail": project / "scenes" / f"scene_{index:04d}_tail_latent.pt",
            "sheet": project / "scenes" / f"scene_{index:04d}_sheet.png",
            "preview": project / "preview" / f"scene_{index:04d}_with_audio.mp4"}


def write_take(files: dict[str, Path], label: str) -> None:
    for key, path in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{label}:{key}", encoding="utf-8")


class SeedAndStateTests(unittest.TestCase):
    def test_take_zero_keeps_the_planner_seed_and_later_takes_never_collide(self):
        base = 20260923
        self.assertEqual(mv2.take_seed(base, 7, 0), mv2.scene_seed(base, 7))
        seeds = [mv2.take_seed(base, index, take) for index in range(80) for take in range(6)]
        self.assertEqual(len(set(seeds)), len(seeds))
        self.assertTrue(all(0 <= s <= 0xFFFFFFFFFFFFFFFF for s in seeds))

    def test_new_seed_invalidates_the_scene_and_every_later_one(self):
        scenes = [{"prompt": f"p{i}", "seed": mv2.scene_seed(1, i), "gen_frames": 209, "prefix_frames": 22 if i else 0,
                   "audio_start_frame": i * 100, "frames": 150} for i in range(4)]
        manifest = {"scenes": scenes, "width": 1664, "height": 928, "render_nonce": 0, "seed": 1}
        before = [render_key(manifest, i) for i in range(4)]
        scenes[1]["seed"] = mv2.take_seed(1, 1, 1)
        after = [render_key(manifest, i) for i in range(4)]
        self.assertEqual(before[0], after[0])
        self.assertTrue(all(b != a for b, a in zip(before[1:], after[1:])))

    def test_tokens_and_review_state(self):
        plan = r"L:\ComfyUI\ComfyUI\output\DaWasteh_H3_MusicVideo_v2\Song_abc\plan.json"
        self.assertEqual(review.parse_token(f"{plan}|3|deadbeef"), (plan, 3))
        self.assertEqual(review.parse_token(f"{plan}|end"), (plan, None))
        self.assertTrue(review.needs_review({"review": "pending"}))
        self.assertFalse(review.needs_review({"review": "approved"}))
        self.assertFalse(review.needs_review({}), "scenes of pre-1.2.5 projects were accepted by the old gate")


class TakeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.files = scene_files(self.project, 2)
        write_take(self.files, "take0")
        self.scene = {"seed": 111, "render_key": "k0", "verified_frames": 168, "completed_at": 1.0, "review": "pending"}

    def tearDown(self):
        self._tmp.cleanup()

    def test_redo_archives_the_take_and_assigns_a_new_seed(self):
        take = review.start_new_take(self.scene, 2, self.files, self.project, lambda t: 1000 + t)
        self.assertEqual((take, self.scene["take"], self.scene["seed"]), (1, 1, 1001))
        for key in ("render_key", "verified_frames", "completed_at", "review"):
            self.assertNotIn(key, self.scene)
        self.assertFalse(any(p.exists() for p in self.files.values()), "the scene counts as not rendered")
        archived = review.take_files(self.project, 2, 0)
        self.assertEqual(archived["video"].read_text(encoding="utf-8"), "take0:video")
        self.assertEqual(self.scene["takes"]["0"], {"take": 0, "seed": 111, "render_key": "k0", "verified_frames": 168,
                                                    "completed_at": 1.0})
        # a second redo counts on from the highest take ever used
        write_take(self.files, "take1")
        self.scene.update({"render_key": "k1", "verified_frames": 168})
        self.assertEqual(review.start_new_take(self.scene, 2, self.files, self.project, lambda t: 1000 + t), 2)
        self.assertEqual(sorted(self.scene["takes"]), ["0", "1"])

    def test_choosing_an_earlier_take_restores_its_files_and_keys(self):
        review.start_new_take(self.scene, 2, self.files, self.project, lambda t: 1000 + t)
        write_take(self.files, "take1")
        self.scene.update({"render_key": "k1", "verified_frames": 168, "completed_at": 2.0, "review": "pending"})
        rows = review.review_takes(self.scene, 2, self.files, self.project)
        self.assertEqual([(r["take"], r["seed"], r["current"]) for r in rows], [(0, 111, False), (1, 1001, True)])
        review.restore_take(self.scene, 2, 0, self.files, self.project)
        self.assertEqual((self.scene["take"], self.scene["seed"], self.scene["render_key"]), (0, 111, "k0"))
        self.assertEqual(self.files["tail"].read_text(encoding="utf-8"), "take0:tail")
        self.assertEqual(review.take_files(self.project, 2, 1)["tail"].read_text(encoding="utf-8"), "take1:tail")
        self.assertEqual(list(self.scene["takes"]), ["1"])
        self.assertEqual(self.scene["takes"]["1"]["render_key"], "k1")
        # the current take is a no-op, an unknown or incomplete take is refused
        review.restore_take(self.scene, 2, 0, self.files, self.project)
        with self.assertRaises(KeyError):
            review.restore_take(self.scene, 2, 5, self.files, self.project)
        review.take_files(self.project, 2, 1)["tail"].unlink()
        with self.assertRaises(FileNotFoundError):
            review.restore_take(self.scene, 2, 1, self.files, self.project)
        self.assertEqual(self.scene["take"], 0)


class FakeDynamicPrompt:
    """The two DynamicPrompt calls review.py uses, over an API prompt plus ephemeral display ids."""

    def __init__(self, prompt: dict, display: dict | None = None):
        self.prompt, self.display = prompt, display or {}

    def get_node(self, node_id):
        return self.prompt[node_id]

    def get_display_node_id(self, node_id):
        while node_id in self.display:
            node_id = self.display[node_id]
        return node_id


def loop_round_prompt(prefix: str = "") -> dict:
    """API prompt of the shipped scene chain inside one loop round (ids as the Pixaroma loop engine clones them)."""
    p = prefix
    return {
        "1": {"class_type": "DaWMV2Planner", "inputs": {"song": "song.mp3"}},
        "2": {"class_type": "DaWMV2EncodeScenes", "inputs": {"plan": ["1", 0], "text_encoder": "te"}},
        "3": {"class_type": "DaWMV2LoadModel", "inputs": {"unet_name": "fast"}},
        "4": {"class_type": "BlockSparseAttention", "inputs": {"model": ["3", 0]}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "video"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": "audio"}},
        "7": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "8": {"class_type": "BasicScheduler", "inputs": {"model": ["4", 0], "steps": 8}},
        p + "20": {"class_type": "PixaromaLoopStart", "inputs": {"total": ["1", 2], "value1": "token", "start_index": 3}},
        p + "21": {"class_type": "DaWMV2SceneSetup", "inputs": {"plan": ["2", 0], "scene_index": [p + "20", 6],
                                                              "index_offset": 1, "vae": ["5", 0], "audio_vae": ["6", 0]}},
        p + "22": {"class_type": "RandomNoise", "inputs": {"noise_seed": [p + "21", 2]}},
        p + "23": {"class_type": "BasicGuider", "inputs": {"model": ["4", 0], "conditioning": [p + "21", 0]}},
        p + "24": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": [p + "22", 0], "guider": [p + "23", 0],
                                                                   "sampler": ["7", 0], "sigmas": ["8", 0],
                                                                   "latent_image": [p + "21", 1]}},
        p + "25": {"class_type": "DaWMV2SaveScene", "inputs": {"plan": ["2", 0], "scene_index": [p + "20", 6], "index_offset": 1,
                                                             "vae": ["5", 0], "latent": [p + "24", 0], "after": [p + "20", 0]}},
        p + "26": {"class_type": "DaWMV2ReviewScene", "inputs": {"scene": [p + "25", 0], "review": True}},
    }


class RedoCloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _graph_utils() is None:
            raise unittest.SkipTest(f"ComfyUI not found at {COMFY} (set COMFYUI_PATH)")

    def check_clone(self, prefix: str):
        prompt = loop_round_prompt(prefix)
        display = {prefix + n: n for n in ("20", "21", "22", "23", "24", "25", "26")} if prefix else {}
        dyn = FakeDynamicPrompt(prompt, display)
        self.assertEqual(sorted(review.scene_chain(dyn, prefix + "26")), sorted(prefix + n for n in ("21", "22", "23", "24", "25", "26")))
        graph, clone = review.clone_scene_chain(dyn, prefix + "26", take=2)
        nodes = graph.finalize()
        by_class = {node["class_type"]: (node_id, node) for node_id, node in nodes.items()}
        self.assertEqual(len(nodes), 6)
        self.assertNotIn("PixaromaLoopStart", by_class)
        setup_id, setup = by_class["DaWMV2SceneSetup"]
        self.assertEqual(setup["inputs"]["take"], 2, "cache-busting input for the new take")
        # links inside the chain point at the clones, everything shared stays on the original nodes
        self.assertEqual(setup["inputs"]["scene_index"], [prefix + "20", 6])
        self.assertEqual(setup["inputs"]["vae"], ["5", 0])
        sampler = by_class["SamplerCustomAdvanced"][1]
        self.assertEqual(sampler["inputs"]["latent_image"], [setup_id, 1])
        self.assertEqual(sampler["inputs"]["sigmas"], ["8", 0])
        self.assertEqual(by_class["BasicGuider"][1]["inputs"]["model"], ["4", 0])
        save_id, save = by_class["DaWMV2SaveScene"]
        self.assertEqual(save["inputs"]["after"], [prefix + "20", 0])
        review_id, review_node = by_class["DaWMV2ReviewScene"]
        self.assertEqual(review_node["inputs"], {"scene": [save_id, 0], "review": True})
        self.assertEqual(clone.out(0), [review_id, 0])
        # the clones show up on the canvas node they came from (the frontend finds MV 5b by this id)
        for node_id, node in nodes.items():
            self.assertEqual(node["override_display_id"], node_id.rsplit(".", 1)[-1])
        self.assertEqual(by_class["DaWMV2ReviewScene"][1]["override_display_id"], "26")

    def test_first_round_and_later_loop_rounds(self):
        self.check_clone("")
        self.check_clone("40.0.0.")   # ids the Pixaroma loop engine gives round 2

    def test_first_loop_round_leaves_scene_1_alone(self):
        """Round 0: Loop Start's value1 is scene 1's review token, so scene 1's whole chain is an ancestor of the
        loop review. Found live: cloning 'everything that depends on a Setup' re-ran scene 1's MV 5 and MV 5b."""
        prompt = loop_round_prompt()
        scene1 = {"10": ("DaWMV2SceneSetup", {"plan": ["2", 0], "scene_index": 0, "index_offset": 0, "vae": ["5", 0], "audio_vae": ["6", 0]}),
                  "11": ("RandomNoise", {"noise_seed": ["10", 2]}),
                  "12": ("BasicGuider", {"model": ["4", 0], "conditioning": ["10", 0]}),
                  "13": ("SamplerCustomAdvanced", {"noise": ["11", 0], "guider": ["12", 0], "sampler": ["7", 0], "sigmas": ["8", 0],
                                                   "latent_image": ["10", 1]}),
                  "14": ("DaWMV2SaveScene", {"plan": ["2", 0], "scene_index": 0, "index_offset": 0, "vae": ["5", 0],
                                             "latent": ["13", 0], "after": ["2", 0]}),
                  "15": ("DaWMV2ReviewScene", {"scene": ["14", 0], "review": True})}
        prompt.update({k: {"class_type": c, "inputs": i} for k, (c, i) in scene1.items()})
        prompt["20"]["inputs"]["value1"] = ["15", 0]
        del prompt["20"]["inputs"]["start_index"]
        dyn = FakeDynamicPrompt(prompt)
        self.assertEqual(sorted(review.scene_chain(dyn, "26")), ["21", "22", "23", "24", "25", "26"])
        self.assertEqual(sorted(review.scene_chain(dyn, "15")), ["10", "11", "12", "13", "14", "15"])
        nodes = review.clone_scene_chain(dyn, "26", take=1)[0].finalize()
        self.assertEqual(sorted(n["class_type"] for n in nodes.values()),
                         sorted(["DaWMV2SceneSetup", "RandomNoise", "BasicGuider", "SamplerCustomAdvanced", "DaWMV2SaveScene",
                                 "DaWMV2ReviewScene"]))
        save = next(n for n in nodes.values() if n["class_type"] == "DaWMV2SaveScene")
        self.assertEqual(save["inputs"]["after"], ["20", 0], "the original Loop Start, not a clone")

    def test_a_review_without_a_scene_setup_upstream_is_refused(self):
        prompt = {"1": {"class_type": "PixaromaPrompt", "inputs": {}},
                  "2": {"class_type": "DaWMV2ReviewScene", "inputs": {"scene": ["1", 0], "review": True}}}
        with self.assertRaises(RuntimeError):
            review.scene_chain(FakeDynamicPrompt(prompt), "2")


class GateTests(unittest.TestCase):
    def payload(self):
        return {"scene": 3, "total": 9, "take": 1, "takes": [{"take": 0}, {"take": 1}]}

    def start(self, gate, interrupt=None):
        events, result = [], {}

        def run():
            try:
                result["decision"] = gate.wait(self.payload(), lambda e, d: events.append((e, d)),
                                               interrupt or (lambda: None), poll=0.01)
            except Exception as exc:  # noqa: BLE001 - the interrupt test expects it
                result["error"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        for _ in range(500):
            if gate.pending():
                break
            time.sleep(0.01)
        return thread, events, result

    def test_decision_reaches_the_waiting_node(self):
        gate = review.ReviewGate()
        thread, events, result = self.start(gate)
        pending = gate.pending()
        self.assertEqual((pending["scene"], events[0][0]), (3, review.EVENT))
        self.assertEqual(gate.decide({"id": "wrong", "action": "continue"})[0], False)
        self.assertEqual(gate.decide({"id": pending["id"], "action": "delete"})[0], False)
        self.assertEqual(gate.decide({"id": pending["id"], "action": "continue", "take": 7})[0], False)
        self.assertEqual(gate.decide({"id": pending["id"], "action": "continue", "take": "0"}), (True, "ok"))
        thread.join(5)
        self.assertEqual(result["decision"], {"action": "continue", "take": 0})
        self.assertEqual(gate.pending(), {})
        self.assertEqual(events[-1], (review.EVENT_DONE, {"id": pending["id"]}))

    def test_cancel_in_comfyui_ends_the_wait(self):
        gate = review.ReviewGate()
        stop = threading.Event()

        def interrupt():
            if stop.is_set():
                raise InterruptedError("Processing interrupted")

        thread, events, result = self.start(gate, interrupt)
        stop.set()
        thread.join(5)
        self.assertIsInstance(result.get("error"), InterruptedError)
        self.assertEqual(gate.pending(), {})
        self.assertEqual(events[-1][0], review.EVENT_DONE)

    def test_rest_without_review_holds_for_this_prompt_only(self):
        gate = review.ReviewGate()
        gate.set_auto("plan.json", "prompt-a")
        self.assertTrue(gate.auto_active("plan.json", "prompt-a"))
        self.assertFalse(gate.auto_active("plan.json", "prompt-b"))
        self.assertFalse(gate.auto_active("other.json", "prompt-a"))
        self.assertFalse(gate.auto_active("plan.json", ""))


class WorkflowAndFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.build_h3_music_video_v122 import PATH, build_all
        cls.workflow = build_all()[PATH]

    def test_every_scene_is_reviewed_and_the_image_gate_is_gone(self):
        reviews = [n for n in self.workflow["nodes"] if n["type"] == "DaWMV2ReviewScene"]
        self.assertEqual(len(reviews), 2)
        self.assertTrue(all(n["widgets_values"] == [True] and n["mode"] == 0 for n in reviews))
        self.assertFalse([n for n in self.workflow["nodes"] if n["type"] == "PixaromaPauseImage"])
        schema = json.loads((ROOT / "tools/workflow_templates/v122/node-schemas.json").read_text(encoding="utf-8"))
        self.assertNotIn("PixaromaPauseImage", schema)
        self.assertEqual(schema["DaWMV2ReviewScene"]["input_order"]["required"], ["scene", "review"])

    def test_frontend_extension_is_shipped_and_matches_the_server(self):
        init = (PACK / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('WEB_DIRECTORY = "./web"', init)
        js = (PACK / "web" / "mv2_review.js").read_text(encoding="utf-8")
        for value in (review.EVENT, review.EVENT_DONE, review.ROUTE, "DaWMV2ReviewScene", *review.ACTIONS):
            self.assertIn(f'"{value}"', js)
        self.assertIn("dawmv2_review", (PACK / "nodes_v2.py").read_text(encoding="utf-8"))


class LiveEvidenceTests(unittest.TestCase):
    """The committed end-to-end run (real frontend, buttons clicked in the MV 5b widget) describes the shipped files."""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "performance/rdna4/h3-music-video-v125-review-validation.json").read_text(encoding="utf-8"))

    def test_report_pins_the_shipped_workflow_and_sources(self):
        import hashlib
        for entry in [self.report["workflow"], *self.report["sources"]]:
            self.assertEqual(hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest(), entry["sha256"], entry["path"])

    def test_every_decision_path_ran_through_the_widget(self):
        run = self.report["run"]
        self.assertEqual([a["action"] for a in run["decisions"]],
                         ["redo", "pick take 1 + continue", "cancel + queue again", "redo",
                          "tester cancel + server restart with the fix + queue again", "redo", "continue_all"])
        self.assertEqual(run["prompts"]["b"]["interrupted_in"], ["DaWMV2ReviewScene"])
        self.assertEqual(run["prompts"]["d"]["status"], "success")
        for shown in run["browser"]:
            self.assertGreaterEqual(shown["video"]["readyState"], 1, shown)
            self.assertEqual((shown["video"]["w"], shown["video"]["h"]), tuple(self.report["resolution"]))
            self.assertTrue(shown["toast"])
            self.assertEqual(len(shown["tabs"]), 0 if len(shown["takes"]) == 1 else len(shown["takes"]))
        scene1, scene2, scene3 = run["scenes"]
        self.assertEqual((scene1["take"], list(scene1["archived_takes"])), (0, ["1"]), "take 1 restored, take 2 archived")
        self.assertEqual((scene2["take"], sorted(scene2["archived_takes"])), (2, ["0", "1"]), "two redos inside the loop")
        self.assertEqual(scene3["take"], 0)
        self.assertTrue(all(s["review"] == "approved" and s["pictures_identical_in_film"] for s in run["scenes"]))
        self.assertTrue(all(t["differs_from_film"] for s in run["scenes"] for t in s["archived_takes"].values()))
        self.assertTrue(run["resume"]["shown_again_without_render"])
        self.assertTrue(run["fixed_loop_redo_only_clones_its_scene"])
        self.assertTrue(run["scene3_without_stop"])

    def test_final_film_is_complete_with_the_original_audio(self):
        film = self.report["run"]["film"]
        self.assertEqual(film["frames"], film["expected_frames"])
        self.assertTrue(film["audio_packets_identical"])
        self.assertLess(max(film["seam_ratios"]), 2.0)


if __name__ == "__main__":
    unittest.main()
