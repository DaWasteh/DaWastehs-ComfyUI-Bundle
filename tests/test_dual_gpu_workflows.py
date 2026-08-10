from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tools.generate_dual_gpu_workflows import CONTROL_ROLES, DEVICE_CONTROL_TYPE, FAMILIES, generate
from tools.validate_workflows import validate_graph


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "workflows" / "Dual GPU - R9700 + RX 9070 XT"
SELECTORS = {"SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"}
LAUNCHER = ROOT / "tools" / "start-MultiGPU.ps1"
CONTROL_NODE_DIR = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control"


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

    def test_one_central_control_drives_every_selector_and_dual_h3_director(self):
        selector_roles = {selector_type: role for role, (_, _, selector_type) in CONTROL_ROLES.items()}
        for family in FAMILIES:
            with self.subTest(family=family.name):
                workflow = json.loads((GENERATED / family.output).read_text(encoding="utf-8"))
                controls = [node for node in workflow["nodes"] if node["type"] == DEVICE_CONTROL_TYPE]
                self.assertEqual(len(controls), 1)
                control = controls[0]
                self.assertEqual(control["widgets_values"], ["gpu:0", "gpu:1", "gpu:1"])
                self.assertTrue(all(output.get("links") for output in control["outputs"]))
                self.assertEqual(workflow["extra"]["dawasteh_dual_gpu"]["version"], 2)

                for graph_index, graph in enumerate(graphs(workflow)):
                    links = {
                        link[0] if isinstance(link, list) else link["id"]: link
                        for link in graph.get("links", [])
                    }
                    for selector in [node for node in graph.get("nodes", []) if node.get("type") in selector_roles]:
                        role = selector_roles[selector["type"]]
                        device_input = next(item for item in selector["inputs"] if item["name"] == "device")
                        link = links[device_input["link"]]
                        origin = link[1] if isinstance(link, list) else link["origin_id"]
                        origin_slot = link[2] if isinstance(link, list) else link["origin_slot"]
                        if graph_index == 0:
                            self.assertEqual(origin, control["id"])
                            self.assertEqual(origin_slot, CONTROL_ROLES[role][0])
                        else:
                            self.assertEqual(origin, graph["inputNode"]["id"])
                            self.assertEqual(graph["inputs"][origin_slot]["name"], f"daw_{role}")

                subgraph_ids = {
                    graph["id"] for graph in workflow.get("definitions", {}).get("subgraphs", [])
                    if any(node.get("type") in selector_roles for node in graph.get("nodes", []))
                }
                for instance in [node for node in workflow["nodes"] if node.get("type") in subgraph_ids]:
                    for role, (slot, _, _) in CONTROL_ROLES.items():
                        input_item = next(item for item in instance["inputs"] if item["name"] == f"daw_{role}")
                        link = next(link for link in workflow["links"] if link[0] == input_item["link"])
                        self.assertEqual((link[1], link[2]), (control["id"], slot))

                if family.h3_director:
                    director = next(node for node in workflow["nodes"] if node["type"] == "DaWH3MusicVideoDirectorDualGPU")
                    for role, (slot, _, _) in CONTROL_ROLES.items():
                        input_item = next(item for item in director["inputs"] if item["name"] == role)
                        link = next(link for link in workflow["links"] if link[0] == input_item["link"])
                        self.assertEqual((link[1], link[2]), (control["id"], slot))

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

    def test_open_h3_variants_preserve_inputs_and_route_model_before_lora(self):
        cases = {
            "MiniMax-H3-FL2VA-DualGPU-All-Supported-Inputs.json": {
                "source": "MiniMax_H3_Spectrum_FL2VA_All_Supported_Inputs.json",
                "conditioning": "MiniMaxH3ImageToVideo",
                "required_inputs": {"first_frame", "last_frame", "prompt", "width", "height", "length"},
            },
            "MiniMax-H3-Ref2VA-DualGPU-All-Reference-Inputs.json": {
                "source": "MiniMax_H3_Spectrum_Ref2VA_All_Reference_Inputs.json",
                "conditioning": "MiniMaxH3ReferenceToVideo",
                "required_inputs": {"ref_images.ref_image_8", "ref_videos.ref_video_2", "ref_video_audios.ref_video_audio_2", "ref_audios.ref_audio_2", "prompt", "width", "height", "length"},
            },
        }
        for output, spec in cases.items():
            with self.subTest(workflow=output):
                workflow = json.loads((GENERATED / output).read_text(encoding="utf-8"))
                source = json.loads((ROOT / "workflows" / "Reference to Video" / spec["source"]).read_text(encoding="utf-8"))
                executable = lambda data: Counter(
                    node["type"] for node in data["nodes"]
                    if node["type"] not in SELECTORS | {DEVICE_CONTROL_TYPE, "MarkdownNote", "PixaromaRunTimer"}
                )
                self.assertEqual(executable(workflow), executable(source))

                by_id = {node["id"]: node for node in workflow["nodes"]}
                links = {link[0]: link for link in workflow["links"]}
                unet = next(node for node in by_id.values() if node["type"] == "UNETLoader")
                model_selector = next(node for node in by_id.values() if node["type"] == "SelectModelDevice")
                lora = next(node for node in by_id.values() if node["type"] == "LoraLoaderModelOnly")
                sigma = next(node for node in by_id.values() if node["type"] == "MiniMaxH3SigmaShift")
                self.assertEqual((links[model_selector["inputs"][0]["link"]][1], links[model_selector["inputs"][0]["link"]][3]), (unet["id"], model_selector["id"]))
                self.assertEqual((links[lora["inputs"][0]["link"]][1], links[lora["inputs"][0]["link"]][3]), (model_selector["id"], lora["id"]))
                self.assertEqual((links[sigma["inputs"][0]["link"]][1], links[sigma["inputs"][0]["link"]][3]), (lora["id"], sigma["id"]))
                self.assertEqual(lora["widgets_values"][1], 1.0)
                self.assertEqual(sigma["widgets_values"], [12.0, 4.0])
                scheduler = next(node for node in by_id.values() if node["type"] == "BasicScheduler")
                sampler = next(node for node in by_id.values() if node["type"] == "KSamplerSelect")
                self.assertEqual(scheduler["widgets_values"][:2], ["beta", 8])
                self.assertEqual(sampler["widgets_values"], ["euler"])

                conditioning = next(node for node in by_id.values() if node["type"] == spec["conditioning"])
                self.assertTrue(spec["required_inputs"].issubset({item["name"] for item in conditioning["inputs"]}))
                self.assertEqual(conditioning["widgets_values"][-1], "match" if spec["conditioning"] == "MiniMaxH3ReferenceToVideo" else 124)

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

    def test_central_control_custom_node_exports_three_combo_outputs(self):
        self.assertTrue((CONTROL_NODE_DIR / "__init__.py").is_file())
        source = (CONTROL_NODE_DIR / "nodes.py").read_text(encoding="utf-8")
        self.assertIn('node_id="DaWMultiGPUDeviceControl"', source)
        self.assertEqual(source.count("io.Combo.Output("), 3)
        self.assertIn('io.Combo.Input("model_device"', source)
        self.assertIn('io.Combo.Input("clip_device"', source)
        self.assertIn('io.Combo.Input("vae_device"', source)
        self.assertIn("return io.NodeOutput(str(model_device), str(clip_device), str(vae_device))", source)

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
