from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.generate_dual_gpu_workflows import BASE_LOADER_TYPES, CONTROL_ROLES, DEVICE_CONTROL_TYPE
from tools.migrate_workflows_v092 import (
    ADDITIONS,
    ALL_R9700,
    CURATED_PROFILES,
    DELETED_PATHS,
    DUAL_GPU_DIRECTORY,
    MIGRATION_KEY,
    MIGRATION_VERSION,
    migrate_collection,
    migrate_workflow,
)
from tools.consolidate_ace_autosongwriters_v093 import (
    SOURCE_WORKFLOWS as V093_SOURCE_WORKFLOWS,
    TARGET_WORKFLOWS as V093_TARGET_WORKFLOWS,
)
from tools.upgrade_v095 import addition_sources as v095_addition_sources
from tools.validate_workflows import git_baseline_workflow_paths, git_head_json

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
PINNED_TEMPLATES = ROOT / "tools" / "workflow_templates"
SELECTORS = {"SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"}
LAUNCHER = ROOT / "tools" / "start-MultiGPU.ps1"
CONTROL_NODE_DIR = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control"


def graphs(workflow: dict):
    yield workflow
    for graph in workflow.get("definitions", {}).get("subgraphs", []):
        yield from graphs(graph)


def paths() -> list[Path]:
    return sorted(WORKFLOWS.rglob("*.json"))


class DualGPUWorkflowTests(unittest.TestCase):
    def test_collection_has_one_central_control_per_workflow(self):
        self.assertEqual(len(paths()), 234)
        for path in paths():
            with self.subTest(path=path.relative_to(ROOT)):
                workflow = json.loads(path.read_text(encoding="utf-8"))
                controls = [node for node in workflow["nodes"] if node.get("type") == DEVICE_CONTROL_TYPE]
                self.assertEqual(len(controls), 1)
                self.assertFalse(any(
                    node.get("type") == DEVICE_CONTROL_TYPE
                    for graph in list(graphs(workflow))[1:]
                    for node in graph.get("nodes", [])
                ))
                self.assertEqual(workflow["extra"][MIGRATION_KEY]["version"], MIGRATION_VERSION)
                self.assertEqual(workflow["extra"]["dawasteh_dual_gpu"]["version"], 3)

    def test_defaults_are_r9700_unless_a_curated_split_is_retained(self):
        counts = {"all_r9700": 0, "curated_split": 0}
        for path in paths():
            key = path.relative_to(WORKFLOWS).as_posix()
            workflow = json.loads(path.read_text(encoding="utf-8"))
            control = next(node for node in workflow["nodes"] if node.get("type") == DEVICE_CONTROL_TYPE)
            defaults = workflow["extra"]["dawasteh_dual_gpu"]["defaults"]
            if key in CURATED_PROFILES:
                expected = CURATED_PROFILES[key][1]
                counts["curated_split"] += 1
            else:
                expected = ALL_R9700
                counts["all_r9700"] += 1
            self.assertEqual(defaults, expected, key)
            self.assertEqual(control["widgets_values"], [expected["MODEL"], expected["CLIP"], expected["VAE"]], key)
        self.assertEqual(counts, {"all_r9700": 202, "curated_split": 32})

    def test_every_selector_is_driven_by_the_root_control_or_subgraph_interface(self):
        selector_roles = {selector_type: role for role, (_, _, selector_type) in CONTROL_ROLES.items()}
        for path in paths():
            workflow = json.loads(path.read_text(encoding="utf-8"))
            control = next(node for node in workflow["nodes"] if node.get("type") == DEVICE_CONTROL_TYPE)
            for graph_index, graph in enumerate(graphs(workflow)):
                links = {
                    link[0] if isinstance(link, list) else link["id"]: link
                    for link in graph.get("links", [])
                }
                for selector in [node for node in graph.get("nodes", []) if node.get("type") in selector_roles]:
                    role = selector_roles[selector["type"]]
                    device = next(item for item in selector["inputs"] if item["name"] == "device")
                    link = links[device["link"]]
                    origin = link[1] if isinstance(link, list) else link["origin_id"]
                    origin_slot = link[2] if isinstance(link, list) else link["origin_slot"]
                    if graph_index == 0:
                        self.assertEqual((origin, origin_slot), (control["id"], CONTROL_ROLES[role][0]), path.name)
                    else:
                        self.assertEqual(origin, graph["inputNode"]["id"], path.name)
                        self.assertEqual(graph["inputs"][origin_slot]["name"], f"daw_{role}", path.name)

    def test_passive_controls_are_explicit_and_default_to_r9700(self):
        passive = 0
        for path in paths():
            workflow = json.loads(path.read_text(encoding="utf-8"))
            gpu = workflow["extra"]["dawasteh_dual_gpu"]
            if gpu["placement_support"] != "control-only-no-standard-model-objects":
                continue
            passive += 1
            self.assertEqual(gpu["connected_roles"], [], path.name)
            self.assertEqual(gpu["defaults"], ALL_R9700, path.name)
            control = next(node for node in workflow["nodes"] if node.get("type") == DEVICE_CONTROL_TYPE)
            self.assertTrue(all(not output.get("links") for output in control["outputs"]), path.name)
        self.assertGreater(passive, 0)

    def test_dual_gpu_folder_is_dissolved_and_redundant_h3_files_are_deleted(self):
        self.assertFalse(DUAL_GPU_DIRECTORY.exists())
        for key in DELETED_PATHS:
            self.assertFalse((WORKFLOWS / key).exists(), key)
        for addition in ADDITIONS:
            self.assertTrue((WORKFLOWS / addition.path).is_file(), addition.path)
        self.assertTrue((WORKFLOWS / "Reference to Video/MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json").is_file())

    def test_migration_is_idempotent(self):
        for path in paths():
            workflow = json.loads(path.read_text(encoding="utf-8"))
            key = path.relative_to(WORKFLOWS).as_posix()
            self.assertEqual(migrate_workflow(workflow, key), workflow, key)

    def test_head_lookup_normalizes_absolute_paths(self):
        path = (WORKFLOWS / "Text to Image/SD15_v1-5-pruned-emaonly-Text-to-Image.json").resolve()
        head = git_head_json(path)
        self.assertEqual(head["version"], 0.4)
        self.assertEqual(head["extra"][MIGRATION_KEY]["release"], "v0.9.2")

    def test_collection_membership_matches_the_declared_migration(self):
        baseline = git_baseline_workflow_paths()
        expected = {
            path for path in baseline
            if not path.startswith("workflows/Dual GPU - R9700 + RX 9070 XT/")
            and path not in {f"workflows/{key}" for key in DELETED_PATHS}
            and path not in {f"workflows/{key}" for key in V093_SOURCE_WORKFLOWS}
        }
        expected.update(f"workflows/{addition.path}" for addition in ADDITIONS)
        expected.update(f"workflows/{target.path}" for target in V093_TARGET_WORKFLOWS)
        expected.update(f"workflows/{target}" for target in v095_addition_sources())
        actual = {path.relative_to(ROOT).as_posix() for path in paths()}
        self.assertEqual(actual, expected)

    def test_custom_destination_cleanup_does_not_touch_repository_global_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "workflows"
            legacy = destination / DUAL_GPU_DIRECTORY.name
            legacy.mkdir(parents=True)
            (legacy / "stale.json").write_text("{}", encoding="utf-8")
            total, _changed, removed = migrate_collection(destination)
            self.assertEqual(total, len(ADDITIONS))
            self.assertEqual(removed, 1)
            self.assertFalse(legacy.exists())
            self.assertFalse(DUAL_GPU_DIRECTORY.exists())

    def test_official_template_snapshots_remain_pinned(self):
        expected_hashes = {
            "video_ltx2_5_t2v.json": "b8ab11a3cb349bf6dccd9ad09307213e0088d833d1867270d23e1f794bab6a9d",
            "video_ltx2_5_i2v.json": "bcd3239835e8e5bf287a664954c253c67cd31147a4a4193ef5975525e246a7a0",
            "video_ltx2_5_flf2v.json": "d93d8d6c63279e15c81d8e81595031449530628a5e4f3644b5ef53b3b345d113",
            "video_wan_animate2.json": "772a7dfce6d5b61b8f838ec0609211a0c9b1c04a7c64e26d05f0852f147edac7",
            "audio_minimax_music_3.json": "0322153265b3e785961511b7849f6659f46a8fa7e8cb66976e5279ff1774b228",
            "3d_pixal3d_trellis2_image_to_model.json": "594295ae20490b4ed990655686f2d0c15ba06732df5553bc22bda98966c40a97",
            "live_face_swap_directml.json": "b0a81c21bde4ba374c569b52135dc5db21dfd7fd7f69b7d704d7e9ae9e37bbda",
            "live_face_swap_directml_v100.json": "15775ccce5c264100dfbefe6ee8a130c50fae4979e3c71679f2062a489362c54",
            "live_person_swap_directml_v100.json": "0768c62731dd39fa18b8221ae44db86ee4eaed70f3adac1581572aaf5848beb3",
        }
        self.assertEqual({path.name for path in PINNED_TEMPLATES.glob("*.json")}, set(expected_hashes))
        for name, expected in expected_hashes.items():
            self.assertEqual(hashlib.sha256((PINNED_TEMPLATES / name).read_bytes()).hexdigest(), expected)

    def test_selectors_are_inserted_only_after_supported_standard_loaders(self):
        for path in paths():
            workflow = json.loads(path.read_text(encoding="utf-8"))
            for graph in graphs(workflow):
                nodes = {node.get("id"): node for node in graph.get("nodes", [])}
                links = {
                    link[0] if isinstance(link, list) else link["id"]: link
                    for link in graph.get("links", [])
                }
                for selector in [node for node in graph.get("nodes", []) if node.get("type") in SELECTORS]:
                    data_input = selector["inputs"][0]
                    link = links[data_input["link"]]
                    source_id = link[1] if isinstance(link, list) else link["origin_id"]
                    self.assertIn(nodes[source_id]["type"], BASE_LOADER_TYPES, path.name)

    def test_central_control_custom_node_exports_three_combo_outputs(self):
        source = (CONTROL_NODE_DIR / "nodes.py").read_text(encoding="utf-8")
        self.assertIn('node_id="DaWMultiGPUDeviceControl"', source)
        self.assertEqual(source.count("io.Combo.Output("), 3)
        self.assertIn('io.Combo.Input("model_device"', source)
        self.assertIn('io.Combo.Input("clip_device"', source)
        self.assertIn('io.Combo.Input("vae_device"', source)

    def test_versioned_launcher_exposes_both_gpus_with_the_v098_profile(self):
        script = LAUNCHER.read_text(encoding="utf-8-sig")
        for expected in (
            '$ErrorActionPreference = "Stop"',
            '$env:HIP_VISIBLE_DEVICES = "0,1"',
            '$env:CUDA_VISIBLE_DEVICES = "0,1"',
            '"--default-device", "0"',
            '"--port", "$Port"',
            '"--reserve-vram", "$ReserveVramGb"',
            # v0.9.8 measured defaults on the R9700 + RX 9070 XT host
            "$DisablePinnedMemory = $true",
            '$CacheMode = "ram"',
            "$PreferHipBlasLt = $true",
            "$UseComfyKitchenAttention = $false",
            "$FastFp8MatrixMult = $false",
            '$env:TORCH_BLAS_PREFER_HIPBLASLT = "1"',
            '"--cache-ram"',
            '"--use-ck-attention"',
            '"--fast", "fp8_matrix_mult"',
            # every profile switch keeps an explicit opposite branch
            '"--enable-dynamic-vram"',
            '"--disable-dynamic-vram"',
            '"--async-offload", "$AsyncOffloadStreams"',
            '"--disable-async-offload"',
            '"--disable-pinned-memory"',
            '"--cache-classic"',
        ):
            self.assertIn(expected, script)
        # The Windows single-GPU default of ComfyUI >= 0.34 must stay overridden.
        self.assertLess(script.index('$env:CUDA_VISIBLE_DEVICES = "0,1"'), script.index("$ComfyArgs = @("))


if __name__ == "__main__":
    unittest.main()
