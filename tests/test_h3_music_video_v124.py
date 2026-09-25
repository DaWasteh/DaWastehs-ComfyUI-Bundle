"""v1.2.4 FastH3 music video: read-only model mapping, high-resolution DiT patches, LoRA-aware resume keys, graph."""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mv2 = _load("dawasteh_mv2_v124_test", PACK / "mv2.py")


# --- minimal stand-ins for the ComfyUI modules h3_highres imports (torch itself is real) -----------------------

def _upstream_h3():
    """comfy.ldm.minimax.model: the three functions h3_highres patches, verbatim semantics of ComfyUI 0.37."""
    h3 = types.ModuleType("comfy.ldm.minimax.model")

    def _mod_row(vecs, row, dtype):
        return vecs[row].to(dtype)

    def _mod_scale_shift(h, shift, scale, segments):
        for a, b, row in segments:
            h[a:b].mul_(1.0 + _mod_row(scale, row, h.dtype)).add_(_mod_row(shift, row, h.dtype))
        return h

    def _mod_gate(x, gate, other, segments):
        for a, b, row in segments:
            x[a:b].addcmul_(other[a:b], _mod_row(gate, row, x.dtype))
        return x

    class MLP(torch.nn.Module):
        def __init__(self, hidden, ffn):
            super().__init__()
            self.fc1 = torch.nn.Linear(hidden, ffn * 2, bias=False)
            self.fc2 = torch.nn.Linear(ffn, hidden, bias=False)

        def forward(self, x):
            a, b = self.fc1(x).chunk(2, dim=-1)
            return self.fc2(torch.nn.functional.silu(a) * b)

    h3._mod_row, h3._mod_scale_shift, h3._mod_gate, h3.MLP = _mod_row, _mod_scale_shift, _mod_gate, MLP
    return h3


@contextlib.contextmanager
def _comfy_stubs():
    import safetensors.torch  # noqa: F401 - part of every ComfyUI venv

    names = ["comfy", "comfy.model_management", "comfy.patcher_extension", "comfy.sd", "comfy.storage", "comfy.utils",
             "comfy.ldm", "comfy.ldm.minimax", "comfy.ldm.minimax.model"]
    saved = {n: sys.modules.get(n) for n in names}
    stubs = {n: types.ModuleType(n) for n in names}
    stubs["comfy.utils"]._TYPES = {"F32": torch.float32, "F16": torch.float16, "BF16": torch.bfloat16, "I8": torch.int8,
                                   "U8": torch.uint8, "I64": torch.int64}
    stubs["comfy.storage"].annotate_state_dict = lambda sd, path: None
    stubs["comfy.model_management"].soft_empty_cache = lambda: None
    stubs["comfy.model_management"].current_loaded_models = []
    stubs["comfy.patcher_extension"].WrappersMP = types.SimpleNamespace(DIFFUSION_MODEL="diffusion_model")
    stubs["comfy.ldm.minimax.model"] = _upstream_h3()
    for name in names[1:]:  # `import comfy.utils` resolves through the parent's attribute
        parent, _, child = name.rpartition(".")
        setattr(stubs[parent], child, stubs[name])
    sys.modules.update(stubs)
    try:
        yield stubs
    finally:
        for n, module in saved.items():
            if module is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = module


class HighResolutionTests(unittest.TestCase):
    def setUp(self):
        self._stubs = _comfy_stubs()
        self.stubs = self._stubs.__enter__()
        self.hr = _load("dawasteh_h3_highres_test", PACK / "h3_highres.py")
        self.h3 = self.stubs["comfy.ldm.minimax.model"]
        self.orig = (self.h3._mod_scale_shift, self.h3._mod_gate, self.h3.MLP.forward)
        self.assertTrue(self.hr.install_patches())

    def tearDown(self):
        self._stubs.__exit__(None, None, None)

    def test_readonly_mapping_matches_safetensors(self):
        import safetensors.torch
        tensors = {"a.weight": torch.randn(7, 5, dtype=torch.bfloat16), "b.weight": torch.randint(-128, 127, (3, 9), dtype=torch.int8),
                   "c.scale": torch.randn(4, dtype=torch.float32), "empty": torch.zeros(0, dtype=torch.float16)}
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "tiny.safetensors")
            safetensors.torch.save_file(tensors, path, metadata={"format": "pt", "note": "x"})
            sd, metadata = self.hr.load_state_dict_readonly(path)
            self.assertEqual(metadata, {"format": "pt", "note": "x"})
            self.assertEqual(set(sd), set(tensors))
            # safetensors' keys() order: the VRAM layout (and so the GEMM kernels) must match the core loaders
            self.assertEqual(list(sd), sorted(tensors))
            for key, value in tensors.items():
                self.assertEqual(sd[key].dtype, value.dtype, key)
                self.assertTrue(torch.equal(sd[key], value), key)
            del sd  # the mapping must be released with the tensors (Windows keeps the file locked otherwise)

    def test_readonly_text_encoder_matches_the_clip_loader_call(self):
        import enum
        import safetensors.torch
        calls = {}
        sd_stub = self.stubs["comfy.sd"]
        sd_stub.CLIPType = enum.Enum("CLIPType", "STABLE_DIFFUSION MINIMAX")

        class Clip:
            patcher = types.SimpleNamespace(cached_patcher_init=None)

        def load_text_encoder_state_dicts(state_dicts, embedding_directory=None, clip_type=None, model_options=None):
            calls.update(keys=sorted(state_dicts[0]), embeddings=embedding_directory, clip_type=clip_type, options=model_options)
            return Clip()

        sd_stub.load_text_encoder_state_dicts = load_text_encoder_state_dicts
        sd_stub.load_clip_model_patcher = object()
        self.stubs["comfy.utils"].convert_old_quants = lambda sd, model_prefix="", metadata=None: (sd, metadata)
        folder_paths = types.ModuleType("folder_paths")
        folder_paths.get_folder_paths = lambda kind: [f"/models/{kind}"]
        saved, sys.modules["folder_paths"] = sys.modules.get("folder_paths"), folder_paths
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = str(Path(directory) / "te.safetensors")
                safetensors.torch.save_file({"w": torch.ones(2, 2)}, path)
                clip = self.hr.load_clip_readonly(path, "minimax")
                self.assertEqual(calls, {"keys": ["w"], "embeddings": ["/models/embeddings"],
                                         "clip_type": sd_stub.CLIPType.MINIMAX, "options": {}})
                self.assertEqual(clip.patcher.cached_patcher_init[1], ([path], ["/models/embeddings"], sd_stub.CLIPType.MINIMAX, {}))
                del clip
        finally:
            if saved is None:
                sys.modules.pop("folder_paths", None)
            else:
                sys.modules["folder_paths"] = saved

    def test_segment_runs_are_bit_identical_to_the_per_token_gather(self):
        torch.manual_seed(0)
        hidden, n = 64, 600
        for vec_dtype in (torch.float32, torch.bfloat16):
            scale, shift, gate = (torch.randn(9, hidden, dtype=vec_dtype) for _ in range(3))
            h = torch.randn(n + 30, hidden, dtype=torch.bfloat16)
            other = torch.randn(n + 30, hidden, dtype=torch.bfloat16)
            rows = torch.tensor([3] * 150 + [0] * (n - 150))  # frozen extend frames first, then generated rows
            segments = [(0, 10, 4), (10, 10 + n, rows), (10 + n, n + 30, 5)]
            ref_ss = self.orig[0](h.clone(), shift, scale, segments)
            ref_gate = self.orig[1](h.clone(), gate, other, segments)
            token = self.hr._ACTIVE.set(True)
            try:
                self.assertTrue(torch.equal(self.h3._mod_scale_shift(h.clone(), shift, scale, segments), ref_ss))
                self.assertTrue(torch.equal(self.h3._mod_gate(h.clone(), gate, other, segments), ref_gate))
                self.assertEqual(self.hr._expand_segments(segments), [(0, 10, 4), (10, 160, 3), (160, 10 + n, 0), (10 + n, n + 30, 5)])
            finally:
                self.hr._ACTIVE.reset(token)
            # outside a wrapped high-resolution forward the upstream code path runs unchanged
            self.assertIs(self.hr._expand_segments(segments), segments)

    def test_mlp_token_chunks_match_the_full_pass(self):
        torch.manual_seed(1)
        mlp = self.h3.MLP(32, 48)
        x = torch.randn(self.hr.MLP_CHUNK_TOKENS * 2 + 77, 32)
        full = self.orig[2](mlp, x)
        token = self.hr._ACTIVE.set(True)
        try:
            chunked = mlp(x)
        finally:
            self.hr._ACTIVE.reset(token)
        torch.testing.assert_close(chunked, full, rtol=1e-5, atol=1e-6)
        self.assertTrue(torch.equal(mlp(x), full))  # inactive: exact upstream call

    def test_token_counts_and_reserve(self):
        def tokens(w, h, frames, text=1000):
            t = 2 if frames <= 5 else ((frames - 5) // 17) * 5 + 2
            video = torch.empty(1, 24, t, h // 16, w // 16, device="meta")
            audio = torch.empty(1, 32, 2, round(frames / 24 * 40), device="meta")
            return self.hr.token_count(video, audio, torch.empty(1, text, 8, device="meta"))
        self.assertLess(tokens(864, 480, 243), self.hr.LARGE_TOKENS)      # v1.2.2 default: untouched
        self.assertLess(tokens(1344, 768, 209), self.hr.LARGE_TOKENS)     # user's 1344x768 extend scenes: untouched
        self.assertGreater(tokens(1920, 1088, 175), self.hr.LARGE_TOKENS)  # 1920x1088 scene 1 already managed
        measured = tokens(1920, 1088, 209, text=713)
        self.assertEqual(62 * 34 * 60, 126480)
        self.assertAlmostEqual(measured, 127541, delta=10)                 # logged by the v1.2.4 probe
        gib = 1024 ** 3
        # measured peak over the resident weights: 13.33 GiB at 127,541 and 15.34 GiB at 148,188 tokens
        for count, peak in ((measured, 13.33), (tokens(1920, 1088, 243, text=713), 15.34)):
            reserve = self.hr.activation_reserve(count)
            self.assertGreater(reserve, (peak + 1.5) * gib, count)          # room for fragmentation
            self.assertLess(reserve, (peak + 4.0) * gib, count)


def _node_helpers() -> dict:
    source = (PACK / "nodes_v2.py").read_text(encoding="utf-8")
    keep = [node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name in {"_cond_key", "_model_prefix", "_render_key"}]
    namespace = {"mv2": mv2, "json": json, "Any": object}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(PACK / "nodes_v2.py"), "exec"), namespace)
    return namespace


N = _node_helpers()


class ResumeKeyTests(unittest.TestCase):
    def manifest(self, **extra):
        scenes = [{"prompt": f"p{i}", "seed": i, "gen_frames": 209, "prefix_frames": 22 if i else 0,
                   "audio_start_frame": i * 100, "frames": 150} for i in range(3)]
        return {"scenes": scenes, "width": 1920, "height": 1088, "render_nonce": 0, **extra}

    def test_v122_keys_are_unchanged_without_a_lora(self):
        scene = {"prompt": "hello"}
        self.assertEqual(N["_cond_key"](scene, "te"), mv2.stable_hash({"prompt": "hello", "te": "te", "v": 1}))
        m = self.manifest()
        s = m["scenes"][0]
        v122 = mv2.stable_hash({"prompt": s["prompt"], "seed": s["seed"], "w": 1920, "h": 1088, "gen": 209, "prefix": 0,
                                "audio": 0, "frames": 150, "previous": "", "nonce": 0})
        self.assertEqual(N["_render_key"](m, 0), v122)
        self.assertEqual(N["_model_prefix"](None), ("", ""))

    def test_lora_trigger_and_model_change_invalidate_scenes(self):
        info = {"model": "fast", "lora": "MiniMax H3\\h3-realism-people-t2v-i2v-r2v.safetensors", "strength": 0.8, "trigger": "r34l1sm"}
        prefix, key = N["_model_prefix"](json.dumps(info))
        self.assertEqual(prefix, "r34l1sm, ")
        self.assertNotEqual(N["_cond_key"]({"prompt": "x"}, "te", prefix), N["_cond_key"]({"prompt": "x"}, "te"))
        plain = self.manifest()
        with_lora = self.manifest(model_key=key, prompt_prefix=prefix)
        stronger = self.manifest(model_key=N["_model_prefix"](json.dumps({**info, "strength": 1.0}))[1], prompt_prefix=prefix)
        for i in range(3):
            keys = {N["_render_key"](m, i) for m in (plain, with_lora, stronger)}
            self.assertEqual(len(keys), 3, i)
        # no LoRA -> no trigger, even when the widget still holds one
        self.assertEqual(N["_model_prefix"](json.dumps({**info, "lora": None}))[0], "")


class WorkflowV124Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.build_h3_music_video_v122 import build_all, PATH, LORA, LORA_STRENGTH, TRIGGER
        cls.path, cls.lora, cls.strength, cls.trigger = PATH, LORA, LORA_STRENGTH, TRIGGER
        cls.workflow = build_all()[PATH]

    def node(self, kind):
        return [n for n in self.workflow["nodes"] if n["type"] == kind]

    def source(self, target, name):
        slot = next(i for i, s in enumerate(target["inputs"]) if s["name"] == name)
        link = next(l for l in self.workflow["links"] if l[3:5] == [target["id"], slot])
        return next(n for n in self.workflow["nodes"] if n["id"] == link[1]), link[2]

    def test_mv0_replaces_the_core_loader_and_feeds_the_encoder(self):
        self.assertFalse(self.node("UNETLoader"))
        loader = self.node("DaWMV2LoadModel")[0]
        self.assertEqual(loader["widgets_values"][1:4], [self.lora, self.strength, self.trigger])
        self.assertTrue(loader["widgets_values"][4])
        encoder = self.node("DaWMV2EncodeScenes")[0]
        self.assertEqual(self.source(encoder, "model_info"), (loader, 1))
        selector, slot = self.source(self.node("MiniMaxH3SigmaShift")[0], "model")
        self.assertEqual((selector["type"], slot), ("SelectModelDevice", 0))
        self.assertEqual(self.source(selector, "model"), (loader, 0))
        marker = self.workflow["extra"]["dawasteh_h3_music_video_v122"]
        self.assertEqual(marker["version"], 1)   # the release string is pinned by the newest release test

    def test_lora_is_pinned_in_the_download_manifest(self):
        models = json.loads((ROOT / "tools/workflow_templates/v122/models.json").read_text(encoding="utf-8"))
        lora = next(m for m in models if m["path"].startswith("loras/"))
        self.assertEqual(lora["repo_id"], "fal/MiniMax-H3-Realism-People-LoRA")
        self.assertEqual(lora["sha256"], "acc529601d2da117fb81179e76c56e488a3beab1171659d305f04fa3655b787e")
        self.assertRegex(lora["revision"], r"^[a-f0-9]{40}$")
        self.assertIn("h3-realism-people-t2v-i2v-r2v.safetensors", json.dumps(self.workflow))


REPORT = ROOT / "performance/rdna4/h3-music-video-v124-validation.json"


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.2.4 GPU run")
class LiveEvidenceV124Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.sha = staticmethod(lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest())

    def test_report_pins_the_shipped_workflow_and_sources(self):
        import hashlib
        import subprocess
        # v1.2.5 changed MV 2 (prompt model, section directions); this evidence describes the v1.2.4 files.
        released = lambda p: hashlib.sha256(subprocess.check_output(["git", "show", "v1.2.4:" + p], cwd=ROOT)).hexdigest()
        workflow = self.report["workflow"]
        self.assertEqual(workflow["sha256"], released(workflow["path"]))
        self.assertTrue(workflow["executed_contract_matches_final"])
        self.assertEqual(workflow["api_contract_sha256"], workflow["final_file_api_contract_sha256"])
        for entry in self.report["sources"]:
            self.assertEqual(entry["sha256"], released(entry["path"]), entry["path"])
        self.assertNotIn("PixaromaLoopStart", workflow["pause_node_classes"])
        self.assertIn("DaWMV2Finalize", workflow["continue_node_classes"])
        self.assertIn("DaWMV2LoadModel", workflow["pause_node_classes"])

    def test_1920x1088_extend_scenes_ran_without_oom(self):
        runs, memory, plan = self.report["runs"], self.report["memory"], self.report["plan"]
        self.assertEqual((runs["pause"]["status"], runs["continue"]["status"]), ("success", "success"))
        self.assertEqual((plan["width"], plan["height"]), (1920, 1088))
        self.assertEqual(plan["prompt_prefix"], "r34l1sm, ")
        self.assertEqual(len(runs["scenes"]), plan["scenes"])
        self.assertEqual(memory["out_of_memory_events"], 0)
        self.assertGreater(memory["commit_headroom_min_render_loop_gib"], 10.0)
        extend = [s for s in runs["scenes"] if s["continuity_frames"]]
        self.assertEqual(len(extend), plan["scenes"] - 1)
        self.assertTrue(any(s["h3_frames"] == 243 for s in extend))  # the largest extend clip is covered
        for scene in runs["scenes"]:
            self.assertEqual(scene["steps"], 8)

    def test_final_film_is_complete_with_the_original_audio(self):
        film = self.report["final_film"]
        self.assertEqual((film["width"], film["height"]), (1920, 1088))
        self.assertEqual(film["frames"], film["expected_frames"])
        self.assertTrue(film["audio_packets_identical"])
        self.assertLess(film["seam_ratio_median"], 1.5)


if __name__ == "__main__":
    unittest.main()
