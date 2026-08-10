from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.generate_dual_gpu_workflows import FAMILIES, generate
from tools.validate_workflows import validate_graph


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "workflows" / "Dual GPU - R9700 + RX 9070 XT"
SELECTORS = {"SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"}
LAUNCHER = ROOT / "tools" / "start-MultiGPU.ps1"


def graphs(workflow: dict):
    yield workflow
    for graph in workflow.get("definitions", {}).get("subgraphs", []):
        yield from graphs(graph)


def selectors(workflow: dict) -> list[dict]:
    return [node for graph in graphs(workflow) for node in graph.get("nodes", []) if node.get("type") in SELECTORS]


class DualGPUWorkflowTests(unittest.TestCase):
    def test_generator_is_deterministic_and_release_managed(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = generate(Path(directory))
            self.assertEqual(len(generated), len(FAMILIES))
            for path in generated:
                self.assertEqual(path.read_bytes(), (GENERATED / path.name).read_bytes())

    def test_every_family_has_correct_device_placement(self):
        self.assertEqual({path.name for path in GENERATED.glob("*.json")}, {family.output for family in FAMILIES})
        for family in FAMILIES:
            with self.subTest(family=family.name):
                workflow = json.loads((GENERATED / family.output).read_text(encoding="utf-8"))
                marker = workflow["extra"]["dawasteh_dual_gpu"]
                self.assertEqual(marker["family"], family.name)
                self.assertEqual(marker["server"], "127.0.0.1:8188")
                if family.h3_director:
                    node_types = [node["type"] for node in workflow["nodes"]]
                    self.assertIn("DaWH3MusicVideoDirectorDualGPU", node_types)
                    self.assertNotIn("DaWH3MusicVideoDirector", node_types)
                    continue
                placed = selectors(workflow)
                self.assertGreaterEqual(len(placed), 3)
                self.assertIn("SelectModelDevice", {node["type"] for node in placed})
                self.assertIn("SelectCLIPDevice", {node["type"] for node in placed})
                for node in placed:
                    expected = "gpu:0" if node["type"] == "SelectModelDevice" else "gpu:1"
                    self.assertEqual(node["widgets_values"], [expected])

    def test_selector_links_are_structurally_complete(self):
        for family in FAMILIES:
            if family.h3_director:
                continue
            workflow = json.loads((GENERATED / family.output).read_text(encoding="utf-8"))
            for index, graph in enumerate(graphs(workflow)):
                placed = [node for node in graph.get("nodes", []) if node.get("type") in SELECTORS]
                if not placed:
                    continue
                with self.subTest(family=family.name, graph=index):
                    node_ids = {node["id"] for node in graph["nodes"]}
                    node_ids.update(
                        endpoint["id"] for key in ("inputNode", "outputNode")
                        if isinstance((endpoint := graph.get(key)), dict) and "id" in endpoint
                    )
                    link_ids = {
                        link[0] if isinstance(link, list) else link["id"]
                        for link in graph["links"]
                    }
                    self.assertEqual(len(link_ids), len(graph["links"]))
                    for node in placed:
                        self.assertIn(node["inputs"][0]["link"], link_ids)
                        self.assertTrue(node["outputs"][0]["links"])
                        self.assertTrue(set(node["outputs"][0]["links"]).issubset(link_ids))
                    for link in graph["links"]:
                        source = link[1] if isinstance(link, list) else link["origin_id"]
                        target = link[3] if isinstance(link, list) else link["target_id"]
                        self.assertIn(source, node_ids)
                        self.assertIn(target, node_ids)

    def test_custom_model_objects_remain_excluded(self):
        sources = {family.source for family in FAMILIES}
        self.assertFalse(any("YuE" in source for source in sources))
        self.assertFalse(any("HeartMuLa" in source for source in sources))
        self.assertFalse(any("MOSS-TTS" in source or "QwenTTS" in source for source in sources))

    def test_validator_rejects_slots_types_interfaces_and_missing_counters(self):
        graph = {
            "last_node_id": 2,
            "last_link_id": 1,
            "extra": {"dawasteh_workflow_refinement": {"generated_notes": 0}},
            "nodes": [
                {
                    "id": 1, "type": "PixaromaPrompt", "pos": [0, 0], "size": [100, 100],
                    "inputs": [], "outputs": [{"type": "STRING", "links": [1]}], "properties": {},
                },
                {
                    "id": 2, "type": "PixaromaShowText", "pos": [200, 0], "size": [100, 100],
                    "inputs": [{"type": "STRING", "link": 1}], "outputs": [], "properties": {},
                },
            ],
            "links": [[1, 1, 0, 2, 0, "STRING"]],
        }
        errors: list[str] = []
        validate_graph(Path("synthetic.json"), "root", graph, errors)
        self.assertEqual(errors, [])

        malformed = copy.deepcopy(graph)
        malformed["links"][0][2] = 1
        malformed["nodes"][1]["inputs"][0]["link"] = None
        malformed["links"][0] = malformed["links"][0][:5]
        malformed.pop("last_link_id")
        errors = []
        validate_graph(Path("synthetic.json"), "root", malformed, errors)
        joined = "\n".join(errors)
        self.assertIn("source slot missing", joined)
        self.assertIn("absent from target input", joined)
        self.assertIn("type missing", joined)
        self.assertIn("last_link_id missing", joined)

        dictionary_link = copy.deepcopy(graph)
        dictionary_link["links"] = [{"id": 1, "origin_id": 1, "target_id": 2, "type": "STRING"}]
        errors = []
        validate_graph(Path("synthetic.json"), "root", dictionary_link, errors)
        joined = "\n".join(errors)
        self.assertIn("source slot missing", joined)
        self.assertIn("target slot missing", joined)

        root_with_state = copy.deepcopy(graph)
        root_with_state["state"] = {"lastNodeId": 2, "lastLinkId": 1}
        root_with_state.pop("last_link_id")
        errors = []
        validate_graph(Path("synthetic.json"), "root", root_with_state, errors)
        self.assertIn("last_link_id missing", "\n".join(errors))

        interface_graph = copy.deepcopy(graph)
        interface_graph.update({
            "inputNode": {"id": -10}, "outputNode": {"id": -20},
            "inputs": [{"name": "text", "type": "STRING"}],
            "outputs": [{"name": "text", "type": "STRING"}],
            "state": {"lastNodeId": 2, "lastLinkId": 1},
        })
        interface_graph["links"][0][1:3] = [-10, 999]
        errors = []
        validate_graph(Path("synthetic.json"), "subgraph", interface_graph, errors)
        self.assertIn("inputNode source slot missing", "\n".join(errors))

        missing_state = copy.deepcopy(interface_graph)
        missing_state.pop("state")
        errors = []
        validate_graph(Path("synthetic.json"), "subgraph", missing_state, errors)
        self.assertIn("subgraph state missing", "\n".join(errors))

        null_endpoint = copy.deepcopy(graph)
        null_endpoint["links"][0][1] = None
        errors = []
        validate_graph(Path("synthetic.json"), "root", null_endpoint, errors)
        self.assertIn("endpoint missing", "\n".join(errors))

    def test_versioned_launcher_exposes_both_gpus_conservatively(self):
        script = LAUNCHER.read_text(encoding="utf-8-sig")
        self.assertIn('$ErrorActionPreference = "Stop"', script)
        self.assertIn('$env:HIP_VISIBLE_DEVICES = "0,1"', script)
        self.assertIn('$env:CUDA_VISIBLE_DEVICES = "0,1"', script)
        self.assertIn('"--default-device", "0"', script)
        self.assertIn('"--port", "$Port"', script)
        self.assertIn('"--disable-dynamic-vram"', script)
        self.assertIn('"--disable-async-offload"', script)
        self.assertIn('"--disable-pinned-memory"', script)
        self.assertIn('"--cache-classic"', script)
        batch = (ROOT / "tools" / "start-MultiGPU.bat").read_text(encoding="utf-8")
        self.assertIn("chcp 65001", batch)
        self.assertIn("start-MultiGPU.ps1", batch)


if __name__ == "__main__":
    unittest.main()
