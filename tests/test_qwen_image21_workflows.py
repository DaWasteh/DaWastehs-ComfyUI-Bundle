"""Qwen Image 2.1 contracts: UI graphs, model provenance and real-run evidence."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from tools import migrate_workflows_v092 as migration
from tools.build_qwen_image21_workflows import build_all, PATHS, SOURCES, ROOT, MARKER, MODEL, CLIP, VAE
from tools.rodent_layout import _topology_hash
from tools.validate_workflows import validate_graph


def node(workflow, kind):
    return next(n for n in workflow["nodes"] if n["type"] == kind)


def source(workflow, target, name):
    slot = next(i for i, s in enumerate(target["inputs"]) if s["name"] == name)
    link = next(l for l in workflow["links"] if l[3:5] == [target["id"], slot])
    return next(n for n in workflow["nodes"] if n["id"] == link[1]), link[2]


class QwenImage21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = build_all()

    def test_rebuild_exact_and_no_legacy_schema_mutation(self):
        before = copy.deepcopy(migration.OBJECT_INFO)
        self.assertEqual(build_all(), self.workflows)
        self.assertEqual(before, migration.OBJECT_INFO)
        for path, workflow in self.workflows.items():
            self.assertEqual(json.loads((ROOT / "workflows" / path).read_text(encoding="utf-8")), workflow)
        from tools import build_qwen_image21_workflows as builder
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "ROOT", Path(directory)):
            builder.main()
            for path in self.workflows:
                data = (Path(directory) / "workflows" / path).read_bytes()
                self.assertNotIn(b"\r\n", data)
                self.assertEqual(data, (ROOT / "workflows" / path).read_bytes())

    def test_flat_valid_rodent_timer_and_connected_gpu_control(self):
        for path, workflow in self.workflows.items():
            errors = []
            validate_graph(Path(path), "root", workflow, errors)
            self.assertEqual(errors, [])
            self.assertFalse(workflow.get("definitions", {}).get("subgraphs"))
            self.assertEqual(workflow["extra"]["dawasteh_rodent_layout"]["topology_sha256"], _topology_hash(workflow))
            kinds = [n["type"] for n in workflow["nodes"]]
            self.assertEqual(kinds.count("PixaromaRunTimer"), 1)
            self.assertEqual(kinds.count("DaWMultiGPUDeviceControl"), 1)
            for kind in ("SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"):
                n = node(workflow, kind)
                control, _ = source(workflow, n, "device")
                self.assertEqual(control["type"], "DaWMultiGPUDeviceControl")
                self.assertTrue(n["outputs"][0]["links"])
            self.assertEqual(node(workflow, "DaWMultiGPUDeviceControl")["widgets_values"], ["gpu:0"] * 3)

    def test_shared_local_models_and_official_sampler(self):
        for workflow in self.workflows.values():
            self.assertEqual(node(workflow, "UNETLoader")["widgets_values"], [MODEL, "default"])
            self.assertEqual(node(workflow, "CLIPLoader")["widgets_values"], [CLIP, "qwen_image", "default"])
            self.assertEqual(node(workflow, "VAELoader")["widgets_values"], [VAE])
            self.assertEqual(node(workflow, "KSampler")["widgets_values"], [0, "fixed", 25, 1.0, "euler", "simple", 1.0])
            for name, slot in (("positive", 0), ("negative", 1)):
                encoder, output = source(workflow, node(workflow, "KSampler"), name)
                self.assertEqual((encoder["type"], output), ("TextEncodeQwenImage21", slot))

    def test_edit_uses_reference_sized_latent_and_lazy_optional_canvas(self):
        workflow = self.workflows[PATHS["image_edit"]]
        switch = node(workflow, "ComfySwitchNode")
        self.assertEqual(switch["widgets_values"], [False])
        enc, slot = source(workflow, switch, "on_false")
        self.assertEqual((enc["type"], slot), ("TextEncodeQwenImage21", 2))
        self.assertEqual(enc["widgets_values"], ["", "", 0])
        self.assertEqual(source(workflow, switch, "on_true")[0]["type"], "EmptyLatentImage")
        for i in (1, 2):
            load, _ = source(workflow, enc, f"images.image_{i}")
            self.assertEqual(load["type"], "PixaromaLoadImage")
            self.assertEqual(load["mode"], 0)
            self.assertEqual(json.loads(load["properties"]["loadImagePixState"])["mode"], "off")
        self.assertFalse(any(s["name"] == "images" for s in enc["inputs"]))
        self.assertEqual(node(workflow, "QwenImage21Cache")["widgets_values"], ["auto", "default"])
        self.assertEqual(source(workflow, node(workflow, "KSampler"), "latent_image")[0]["id"], switch["id"])

    def test_t2i_resolution_and_lossless_embedded_output(self):
        workflow = self.workflows[PATHS["t2i"]]
        self.assertNotIn("QwenImage21Cache", [n["type"] for n in workflow["nodes"]])
        res = json.loads(node(workflow, "PixaromaResolution")["properties"]["resolutionState"])
        self.assertEqual((res["w"], res["h"], res["snap"]), (1024, 1024, 32))
        for workflow in self.workflows.values():
            state = json.loads(node(workflow, "PixaromaSaveImage")["properties"]["saveImageState"])
            self.assertEqual(state["format"], "png")
            self.assertTrue(state["saveOnRun"])
            self.assertTrue(state["embedWorkflow"])
            self.assertEqual(state["folder"], "")
            self.assertIn("%counter%", state["pattern"])
            self.assertIn("Research", json.dumps(workflow))

    def test_pinned_sources_models_and_public_inputs_only(self):
        for item in json.loads((SOURCES / "sources.json").read_text()):
            self.assertEqual(hashlib.sha256((SOURCES / item["file"]).read_bytes()).hexdigest(), item["sha256"])
        models = json.loads((SOURCES / "models.json").read_text())
        self.assertEqual(len(models), 3)
        for item in models:
            self.assertRegex(item["revision"], r"^[a-f0-9]{40}$")
            self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")
            self.assertGreater(item["size"], 0)
            self.assertNotIn("..", Path(item["path"]).parts)
        inputs = json.loads((SOURCES / "inputs.json").read_text())
        self.assertEqual({i["file"] for i in inputs}, {"portrait_model_denim.png", "clothing_light_blue_denim_shirt.png"})
        for item in inputs:
            self.assertRegex(item["url"], r"https://raw.githubusercontent.com/Comfy-Org/workflow_templates/[a-f0-9]{40}/input/")
            self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")

    def test_audit_sources_and_frontend_contract_hashes_are_pinned(self):
        report = json.loads((ROOT / "performance/rdna4/qwen-image21-v121-validation.json").read_text(encoding="utf-8"))
        contracts = json.loads((SOURCES / "frontend-contracts.json").read_text(encoding="utf-8"))
        for entry in report["sources"]:
            self.assertEqual(hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])
        for case, row in contracts.items():
            output = {k: {"class_type": v["class_type"], "inputs": v["inputs"]} for k, v in row["output"].items()}
            digest = hashlib.sha256(json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            record = next(r for r in report["runs"] if r["case"] == row["case"] and r["workflow"] == row["workflow"])
            self.assertEqual(record["api_contract_sha256"], digest, case)
            self.assertEqual(record["steps"], 25)
            self.assertEqual(record["status"], "success")

    def test_frontend_preserves_muted_reference_and_free_canvas(self):
        contracts = json.loads((SOURCES / "frontend-contracts.json").read_text(encoding="utf-8"))
        default = contracts["edit"]["output"]
        single = contracts["single"]["output"]
        self.assertIn("images.image_2", default["6"]["inputs"])
        self.assertNotIn("images.image_2", single["6"]["inputs"])
        self.assertNotIn("10", single)
        self.assertFalse(default["11"]["inputs"]["switch"])
        self.assertTrue(single["11"]["inputs"]["switch"])
        self.assertEqual(single["6"]["inputs"]["resolution"], 512)
        report = json.loads((ROOT / "performance/rdna4/qwen-image21-v121-validation.json").read_text(encoding="utf-8"))
        alpha = next(r for r in report["runs"] if r["case"] == "alpha")["outputs"][0]
        self.assertEqual((alpha["mode"], alpha["alpha_min"], alpha["alpha_max"]), ("RGBA", 0, 255))
        self.assertGreater(alpha["alpha_below_128_fraction"], 0.5)
        large = next(r for r in report["runs"] if r["case"] == "2k")["outputs"][0]
        self.assertEqual((large["width"], large["height"]), (2048, 2048))

    def test_live_default_evidence_matches_shipped_files(self):
        report = json.loads((ROOT / "performance/rdna4/qwen-image21-v121-validation.json").read_text(encoding="utf-8"))
        defaults = {r["workflow"]: r for r in report["runs"] if r["case"] == "default"}
        self.assertEqual(set(defaults), {"workflows/" + p for p in self.workflows})
        for path in self.workflows:
            record = defaults["workflows/" + path]
            self.assertEqual(record["status"], "success")
            self.assertTrue(record["executed_contract_matches_final"])
            self.assertEqual(record["workflow_sha256"], hashlib.sha256((ROOT / "workflows" / path).read_bytes()).hexdigest())
            self.assertTrue(record["outputs"])
            for output in record["outputs"]:
                self.assertGreater(output["size"], 0)
                self.assertTrue(output["workflow_metadata_matches"])
                self.assertTrue(output["prompt_metadata_matches"])
                self.assertGreater(output["rgb_stddev"], 5)


if __name__ == "__main__":
    unittest.main()
