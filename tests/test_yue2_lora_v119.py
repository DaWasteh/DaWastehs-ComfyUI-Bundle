"""Static contracts plus opt-in tests of the exact installed, hash-pinned backend."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from tools import build_yue2_lora_workflows as builder
from tools.install_yue2_lora_model import MODEL, install
from tools.install_yue2_lora_node import MANIFEST, verify_node
from tools.rodent_layout import _topology_hash
from tools.validate_workflows import validate_graph

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_exact_rebuild_valid_graphs_and_honest_metadata(self):
        for path, workflow in builder.build_all().items():
            with self.subTest(path=path):
                self.assertEqual(json.loads((ROOT / "workflows" / path).read_text(encoding="utf-8")), workflow)
                errors = []
                validate_graph(Path(path), "root", workflow, errors)
                self.assertEqual(errors, [])
                self.assertEqual(sum(n["type"] == "PixaromaRunTimer" for n in workflow["nodes"]), 1)
                self.assertEqual(sum(n["type"] == "DaWMultiGPUDeviceControl" for n in workflow["nodes"]), 1)
                self.assertEqual(workflow["extra"]["dawasteh_rodent_layout"]["topology_sha256"], _topology_hash(workflow))
                self.assertTrue(workflow["extra"]["dawasteh_yue2_lora"]["experimental"])
                self.assertNotIn("dawasteh_v118", workflow["extra"])
                self.assertIn("PRIVATE", path)
                self.assertIn("CC-BY-NC-4.0", json.dumps(workflow))

    def test_shared_schemas_not_mutated(self):
        from tools import migrate_workflows_v092 as migration
        import copy
        before = copy.deepcopy(migration.OBJECT_INFO)
        builder.build_all()
        self.assertEqual(before, migration.OBJECT_INFO)

    def test_real_training_gpu_links_and_amd_defaults(self):
        w = builder.build_all()[builder.TRAIN_PATH]
        nodes = {n["id"]: n for n in w["nodes"]}
        for node in nodes.values():
            if node["type"] not in {"YuE2TrainingDataset", "YuE2LoRATrainer"}:
                continue
            slot = next(s for s in node["inputs"] if s["name"] == "device")
            link = next(l for l in w["links"] if l[0] == slot["link"])
            self.assertEqual(nodes[link[1]]["type"], "DaWMultiGPUDeviceControl")
            self.assertEqual(link[2], 2 if node["type"] == "YuE2TrainingDataset" else 0)
            self.assertIn(builder.CHECKPOINT, node["widgets_values"])
        trainer = next(n for n in nodes.values() if n["type"] == "YuE2LoRATrainer")
        self.assertIn("adamw", trainer["widgets_values"])
        self.assertNotIn("adamw_8bit", trainer["widgets_values"])
        self.assertEqual(trainer["widgets_values"][2], 100)

    def test_inference_lora_is_in_sampler_ancestry_duration_derived(self):
        w = builder.build_all()[builder.MUSIC_PATH]
        nodes = {n["id"]: n for n in w["nodes"]}
        by_type = {n["type"]: n for n in nodes.values()}
        sampler = by_type["KSampler"]
        model_slot = next(s for s in sampler["inputs"] if s["name"] == "model")
        link = next(l for l in w["links"] if l[0] == model_slot["link"])
        self.assertEqual(nodes[link[1]]["type"], "LoraLoaderModelOnly")
        lora = nodes[link[1]]
        link = next(l for l in w["links"] if l[0] == lora["inputs"][0]["link"])
        self.assertEqual(nodes[link[1]]["type"], "SelectModelDevice")
        self.assertNotIn("YuE2GenerateABC", by_type)
        self.assertEqual(by_type["YuE2GenerateMusic"]["widgets_values"][2], "")
        latent = by_type["EmptyYuE2LatentAudio"]
        seconds = next(s for s in latent["inputs"] if s["name"] == "seconds")
        link = next(l for l in w["links"] if l[0] == seconds["link"])
        self.assertEqual((nodes[link[1]]["type"], link[2]), ("YuE2GenerateMusic", 1))

    def test_frontend_seed_alignment_and_device_socket_contract(self):
        contracts = json.loads((ROOT / "tools/workflow_templates/yue2-lora/frontend-contracts.json").read_text(encoding="utf-8"))
        actual = contracts[builder.TRAIN_PATH]["2"]["inputs"]
        self.assertEqual({k: actual[k] for k in ("seed", "optimizer", "lr_scheduler", "warmup_steps", "grad_accum", "ema_decay", "live_curve")},
                         {"seed": 119, "optimizer": "adamw", "lr_scheduler": "cosine", "warmup_steps": 10, "grad_accum": 1, "ema_decay": 0.99, "live_curve": True})
        schemas = json.loads(builder.SCHEMAS.read_text(encoding="utf-8"))
        self.assertTrue(schemas["YuE2LoRATrainer"]["input"]["required"]["seed"][1]["control_after_generate"])
        for kind in ("YuE2TrainingDataset", "YuE2LoRATrainer"):
            self.assertEqual(schemas[kind]["input"]["optional"]["device"][0], "COMBO")

    def test_historical_v119_evidence_matches_executed_contracts(self):
        report = json.loads((ROOT / "performance/rdna4/yue2-lora-v119-validation.json").read_text(encoding="utf-8"))
        contracts = json.loads((ROOT / "tools/workflow_templates/yue2-lora/frontend-contracts.json").read_text(encoding="utf-8"))
        def canonical(data):
            if isinstance(data, dict):
                return {k: canonical(v) for k, v in data.items()}
            if isinstance(data, list):
                return [canonical(v) for v in data]
            return int(data) if isinstance(data, float) and data.is_integer() else data
        def digest(data):
            return hashlib.sha256(json.dumps(canonical(data), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        for entry in report["workflows"]:
            # Historical graph hashes belong to v1.1.9. Current bytes are
            # verified separately against the v1.2.0 release evidence.
            self.assertRegex(entry["sha256"], r"^[a-f0-9]{64}$")
            self.assertEqual(digest(contracts[entry["path"].removeprefix("workflows/")]), entry["frontend_contract_sha256"])
        for entry in report["runs"]:
            self.assertEqual(entry["status"], "success")
            import copy
            prompt = copy.deepcopy(contracts[entry["workflow"].removeprefix("workflows/")])
            for override in entry["overrides"]:
                node = prompt[override["node_id"]]
                self.assertEqual(node["class_type"], override["class_type"])
                self.assertEqual(node["inputs"][override["input"]], override["default"])
                node["inputs"][override["input"]] = override["executed"]
            self.assertEqual(digest(prompt), entry["executed_prompt_sha256"])
        historical_manifest = MANIFEST.with_name("trainer-manifest-v119.json")
        self.assertEqual(hashlib.sha256(historical_manifest.read_bytes()).hexdigest(), report["trainer"]["manifest_sha256"])
        self.assertRegex(report["trainer"]["patch_sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(report["inspection"]["baseline_restored_pcm_identical"])
        self.assertTrue(report["inspection"]["ema_changes_pcm"])
        self.assertTrue(report["queue_idle"])

    def test_model_opt_in_and_no_overwrite(self):
        self.assertEqual(MODEL["size"], 7799983228)
        self.assertRegex(MODEL["sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(MODEL["revision"], r"^[a-f0-9]{40}$")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "models" / MODEL["path"]
            target.parent.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "accept-noncommercial"):
                install(root)
            with self.assertRaisesRegex(ValueError, "Not overwritten"):
                install(root, verify_only=True)
            target.write_bytes(b"existing user file")
            with self.assertRaisesRegex(ValueError, "Not overwritten"):
                install(root, accept_noncommercial=True)
            self.assertEqual(target.read_bytes(), b"existing user file")

    def test_node_verifier_and_license_provenance(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertRegex(manifest["revision"], r"^[a-f0-9]{40}$")
        self.assertIn("LICENSE", manifest["files"])
        self.assertIn("trainer_core/yue2_ref/licenses/LICENSE", manifest["files"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nodes.py").write_bytes(b"test")
            good = {"files": {"nodes.py": hashlib.sha256(b"test").hexdigest()}}
            verify_node(root, good)
            (root / "nodes.py").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "not overwritten"):
                verify_node(root, good)


@unittest.skipUnless(os.environ.get("YUE2_TRAINER_ROOT"), "set YUE2_TRAINER_ROOT to test the pinned installed trainer")
class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = Path(os.environ["YUE2_TRAINER_ROOT"])
        verify_node(folder, json.loads(MANIFEST.read_text()))
        spec = importlib.util.spec_from_file_location("tested_yue2_trainer", folder / "__init__.py", submodule_search_locations=[str(folder)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = package
        spec.loader.exec_module(package)
        from tested_yue2_trainer.trainer_core import data, lora, convert, native_ckpt
        from tested_yue2_trainer import nodes
        cls.data, cls.lora, cls.convert, cls.native, cls.nodes = data, lora, convert, native_ckpt, nodes

    def test_bom_caption_and_empty_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                self.data.scan_folder(root)
            (root / "a.wav").touch()
            (root / "a.txt").write_text("piano", encoding="utf-8-sig")
            self.assertEqual(self.data.scan_folder(root)[0][1], "piano")

    def test_invalid_latents_rejected(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.npy"
            np.save(path, np.full((25, 64), np.nan))
            item = self.data.DatasetItem(path, "", path, 25, 0)
            with self.assertRaisesRegex(ValueError, "Invalid latent cache"):
                self.data.load_clip_latents(item)

    def test_fused_native_lora_delta_matches_three_projections(self):
        import torch
        torch.manual_seed(119)
        parts = {name: (torch.randn(2, 5), torch.randn(n, 2))
                 for name, n in zip(self.convert.QKV_ORDER, [4, 2, 2])}
        down, up = self.convert._fuse_group(parts, self.convert.QKV_ORDER, 0.75)
        expected = torch.cat([u @ d for d, u in parts.values()]) * 0.75
        torch.testing.assert_close(up @ down, expected)

    def test_adapter_initially_zero_then_real_gradient_update(self):
        import torch
        base = torch.nn.Linear(5, 4)
        base.requires_grad_(False)
        lora = self.lora.LoRALinear(base, 2, 2, 0)
        x = torch.randn(3, 5)
        original = base.weight.detach().clone()
        torch.testing.assert_close(lora(x), base(x))
        optimizer = torch.optim.AdamW([p for p in lora.parameters() if p.requires_grad], lr=1e-3)
        lora(x).square().mean().backward()
        optimizer.step()
        self.assertGreater(lora.lora_up.weight.abs().sum().item(), 0)
        torch.testing.assert_close(base.weight, original)

    def test_quantized_native_checkpoint_rejected(self):
        import torch
        from safetensors.torch import save_file
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "int8.safetensors"
            save_file({self.native.TOKENIZER_KEY: torch.zeros(4, dtype=torch.uint8),
                       self.native.TE_PREFIX + "embed_tokens.weight": torch.zeros(2, 2),
                       self.native.DM_PREFIX + "model.layers.0.self_attn.qkv_proj.weight": torch.zeros(4, 4, dtype=torch.int8),
                       self.native.VAE_PREFIX + "decoder.weight": torch.zeros(2, 2)}, path)
            self.assertFalse(self.native.is_native_yue2_checkpoint(path))

    def test_patch_safety_guards_present(self):
        import inspect
        self.assertIn("torch.enable_grad()", inspect.getsource(self.nodes.YuE2LoRATrainer.train))
        self.assertIn("FileExistsError", inspect.getsource(self.nodes.YuE2LoRATrainer.train))
        self.assertIn("comfy.model_management", inspect.getsource(self.nodes._unload_comfy_models))
        self.assertTrue(self.nodes.YuE2TrainingDataset.IS_CHANGED() != self.nodes.YuE2TrainingDataset.IS_CHANGED())


if __name__ == "__main__":
    unittest.main()
