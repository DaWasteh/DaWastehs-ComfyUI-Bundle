"""v1.2.9 workflows: Mira-Scene photo -> 3D scene (TRELLIS.2 per object) and the fast voxel layout preview."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_mira_scene_workflows_v129 import (DINO, INPUT, MOGE, OBJECTS, PATHS, PIPELINE, ROOT, SAM3, SETTINGS, SHAPE_VAE,
                                                   SOURCES, TEXTURE_VAE, TRELLIS, build_all)
from tools.rodent_layout import _topology_hash
from tools.validate_workflows import validate_graph

REPORT = ROOT / "performance/rdna4/mira-scene-v129-validation.json"
PACK = ROOT / "custom_nodes/ComfyUI-DaWasteh-MiraScene"
BS = "\\"


def nodes(workflow, kind):
    return [n for n in workflow["nodes"] if n["type"] == kind]


def one(workflow, kind):
    found = nodes(workflow, kind)
    assert len(found) == 1, (kind, len(found))
    return found[0]


def source(workflow, target, name):
    slot = next(i for i, s in enumerate(target["inputs"]) if s["name"] == name)
    link = next((item for item in workflow["links"] if item[3:5] == [target["id"], slot]), None)
    if link is None:
        return None
    return next(n for n in workflow["nodes"] if n["id"] == link[1]), link[2]


def upstream(workflow, target, name, skip=("SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice")):
    """Source of an input, looking through the device selectors the v0.9.2 migration inserts after loaders."""
    node, slot = source(workflow, target, name)
    while node["type"] in skip:
        node, slot = source(workflow, node, {"SelectModelDevice": "model", "SelectCLIPDevice": "clip", "SelectVAEDevice": "vae"}[node["type"]])
    return node, slot


def seeded(settings, *keys):
    """Widget values of a node whose seed gets ComfyUI's control_after_generate slot."""
    values = []
    for key in keys:
        values.append(settings[key])
        if key == "seed":
            values.append("fixed")
    return values


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = build_all()

    def test_rebuild_is_exact_and_lf_only(self):
        self.assertEqual(set(self.built), set(PATHS.values()))
        self.assertEqual(build_all(), self.built)
        from tools import build_mira_scene_workflows_v129 as builder
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "ROOT", Path(directory)):
            builder.main()
            for path in PATHS.values():
                data = (Path(directory) / "workflows" / path).read_bytes()
                self.assertNotIn(b"\r\n", data)
                self.assertEqual(data, (ROOT / "workflows" / path).read_bytes(), path)

    def test_flat_valid_rodent_timer_and_one_gpu_control(self):
        for path, workflow in self.built.items():
            with self.subTest(path=path):
                errors = []
                validate_graph(Path(path), "root", workflow, errors)
                self.assertEqual(errors, [])
                self.assertFalse(workflow.get("definitions", {}).get("subgraphs"))
                self.assertEqual(workflow["extra"]["dawasteh_rodent_layout"]["topology_sha256"], _topology_hash(workflow))
                self.assertEqual(len(nodes(workflow, "PixaromaRunTimer")), 1)
                self.assertEqual(one(workflow, "DaWMultiGPUDeviceControl")["widgets_values"], ["gpu:0"] * 3)
                self.assertEqual(workflow["extra"]["dawasteh_mira_scene_v129"]["kind"],
                                 next(k for k, v in PATHS.items() if v == path))
                notes = [n for n in workflow["nodes"] if n["type"] == "MarkdownNote"]
                self.assertTrue(any(n["title"].startswith("START HIER") for n in notes))
                downloads = next(n for n in notes if n["title"].startswith("DOWNLOADS"))["widgets_values"][0]
                self.assertIn("keine Lizenzdatei", downloads)   # Mira-Scene upstream has no license: private use only


class FrontTests(unittest.TestCase):
    """Both workflows share Mira's front: 518 px scene, SAM 3.1 objects + floor, clean masks, MoGe-2, Mira CCM."""

    @classmethod
    def setUpClass(cls):
        cls.built = build_all()

    def test_scene_square_and_sam3_objects_plus_floor(self):
        for path, w in self.built.items():
            with self.subTest(path=path):
                load = one(w, "PixaromaLoadImage")
                self.assertEqual(load["widgets_values"], [INPUT])
                prep = one(w, "DaWMiraPrepareImage")
                self.assertEqual(source(w, prep, "image"), (load, 0))
                self.assertEqual(one(w, "CheckpointLoaderSimple")["widgets_values"], [SAM3])
                objects, floor = nodes(w, "SAM3_Detect")
                self.assertEqual(objects["widgets_values"], [SETTINGS["sam3"]["threshold"], 2, True])     # one mask per object
                self.assertEqual(floor["widgets_values"], [SETTINGS["sam3_floor"]["threshold"], 2, False])  # one merged floor
                for detect in (objects, floor):
                    self.assertEqual(source(w, detect, "image"), (prep, 0))
                    self.assertEqual(upstream(w, detect, "model")[0]["type"], "CheckpointLoaderSimple")
                prompt = one(w, "PixaromaPrompt")
                self.assertEqual(prompt["properties"]["promptState"]["text"], OBJECTS)
                self.assertEqual(source(w, source(w, objects, "conditioning")[0], "text"), (prompt, 0))
                self.assertEqual(source(w, floor, "conditioning")[0]["widgets_values"], ["floor"])
                masks = one(w, "DaWMiraMasks")
                self.assertEqual(masks["widgets_values"], [SETTINGS["masks"]["min_area"], SETTINGS["masks"]["max_objects"]])
                self.assertEqual((source(w, masks, "masks"), source(w, masks, "floor")), ((objects, 0), (floor, 0)))
                self.assertIn((masks, 3), [source(w, n, "images") for n in nodes(w, "PreviewImage")])

    def test_moge_and_mira_ccm_on_the_same_scene(self):
        for path, w in self.built.items():
            with self.subTest(path=path):
                prep = one(w, "DaWMiraPrepareImage")
                moge = one(w, "MoGeInference")
                self.assertEqual(source(w, moge, "image"), (prep, 0))    # depth and CCM see the same 518 px pixels
                self.assertEqual(source(w, moge, "moge_model")[0]["widgets_values"], [MOGE])
                self.assertEqual(moge["widgets_values"], [9, 0.0, 4, True, True, 3])
                ccm = one(w, "DaWMiraCCM")
                self.assertEqual(ccm["widgets_values"], seeded(SETTINGS["ccm"], "seed", "steps", "guidance"))
                self.assertEqual(source(w, ccm, "mira_model")[0]["widgets_values"], [PIPELINE, "bf16"])
                self.assertEqual((source(w, ccm, "scene"), source(w, ccm, "hires")), ((prep, 0), (prep, 1)))
                self.assertEqual(source(w, ccm, "masks"), (one(w, "DaWMiraMasks"), 0))
        self.assertEqual(SETTINGS["ccm"], {"seed": 42, "steps": 30, "guidance": 3.0})   # Mira's inference defaults

    def test_assembly_and_glb_output(self):
        for key, path in PATHS.items():
            w = self.built[path]
            with self.subTest(key=key):
                assemble = one(w, "DaWMiraAssembleScene")
                self.assertEqual(assemble["widgets_values"], seeded(SETTINGS["assemble"], "upright", "snap_to_support", "add_floor", "seed"))
                self.assertEqual(source(w, assemble, "mira_ccm"), (one(w, "DaWMiraCCM"), 0))
                self.assertEqual(source(w, assemble, "moge_geometry"), (one(w, "MoGeInference"), 0))
                self.assertEqual(source(w, assemble, "floor"), (one(w, "DaWMiraMasks"), 1))
                save = one(w, "Save3DAdvanced")
                self.assertEqual(save["widgets_values"][0], "Mira_Scene/scene" if key == "scene" else "Mira_Scene/layout")
                self.assertEqual(source(w, save, "model_3d"), (assemble, 0))
                self.assertIn((assemble, 1), [source(w, n, "source") for n in nodes(w, "PreviewAny")])


class SceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        built = build_all()
        cls.scene = built[PATHS["scene"]]
        cls.layout = built[PATHS["layout"]]

    def test_trellis_runs_per_object_on_mira_voxels(self):
        w = self.scene
        trellis = one(w, "DaWMiraTrellisObjects")
        s = SETTINGS["trellis"]
        self.assertEqual(trellis["widgets_values"], seeded(s, "detail", "seed", "shape_steps", "detail_steps", "texture_steps", "cfg",
                                                           "remesh_resolution", "max_faces", "texture_size"))
        ccm = one(w, "DaWMiraCCM")
        self.assertEqual((source(w, trellis, "voxel"), source(w, trellis, "objects")), ((ccm, 1), (ccm, 2)))
        rescale, _ = source(w, trellis, "shape_model")
        self.assertEqual((rescale["type"], rescale["widgets_values"]), ("RescaleCFG", [SETTINGS["rescale_cfg"]]))
        override, _ = source(w, rescale, "model")
        self.assertEqual((override["type"], override["widgets_values"]), ("CFGOverride", [1.0, 0.769, 1.0]))
        unet = one(w, "UNETLoader")
        self.assertEqual(unet["widgets_values"], [TRELLIS, "default"])
        self.assertEqual(upstream(w, override, "model"), (unet, 0))
        self.assertEqual(upstream(w, trellis, "texture_model"), (unet, 0))    # texture stage without the CFG patches
        self.assertEqual(upstream(w, trellis, "clip_vision")[0]["widgets_values"], [DINO])
        self.assertEqual(upstream(w, trellis, "shape_vae")[0]["widgets_values"], [SHAPE_VAE])
        self.assertEqual(upstream(w, trellis, "texture_vae")[0]["widgets_values"], [TEXTURE_VAE])
        self.assertEqual(source(w, one(w, "DaWMiraAssembleScene"), "meshes"), (trellis, 0))
        objects = one(w, "SaveGLB")
        self.assertEqual((objects["widgets_values"], source(w, objects, "mesh")), (["Mira_Scene/objects/object"], (trellis, 0)))

    def test_layout_preview_has_no_trellis(self):
        types = {n["type"] for n in self.layout["nodes"]}
        for kind in ("DaWMiraTrellisObjects", "UNETLoader", "CLIPVisionLoader", "VAELoader", "SaveGLB"):
            self.assertNotIn(kind, types)
        self.assertIsNone(source(self.layout, one(self.layout, "DaWMiraAssembleScene"), "meshes"))


class ManifestTests(unittest.TestCase):
    def test_models_inputs_and_code_are_pinned(self):
        models = json.loads((SOURCES / "mira-models.json").read_text(encoding="utf-8"))
        for entry in models:
            self.assertRegex(entry["revision"], r"^[0-9a-f]{40}$")
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(entry["size"], 0)
        used = {value for workflow in build_all().values() for node in workflow["nodes"]
                if isinstance(node.get("widgets_values"), list) for value in node["widgets_values"] if isinstance(value, str)}
        pipeline = [e for e in models if e["repo_id"] == "Yang-Tian/Mira-Scene"]
        self.assertEqual({e["path"].split("/")[3] for e in pipeline if e["path"].count("/") > 3},
                         {"feature_extractor", "image_encoder", "scheduler", "transformer", "vae"})
        self.assertTrue(all(e["path"].startswith("diffusers/Mira-Scene/pipeline/") for e in pipeline))
        self.assertIn(PIPELINE, used)
        for entry in models:
            if entry not in pipeline:   # every other downloaded model is used by a shipped workflow
                self.assertIn(entry["path"].split("/", 1)[1].replace("/", BS), used, entry["path"])
        for item in json.loads((SOURCES / "mira-inputs.json").read_text(encoding="utf-8")):
            self.assertRegex(item["url"], r"https://raw.githubusercontent.com/Comfy-Org/workflow_templates/[a-f0-9]{40}/")
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")

    def test_updater_runtime_and_manifest_pin_the_same_commit(self):
        code = json.loads((SOURCES / "mira-code.json").read_text(encoding="utf-8"))
        self.assertRegex(code["commit"], r"^[0-9a-f]{40}$")
        self.assertTrue(code["license"].startswith("none"))
        updater = (ROOT / "tools/update-comfyui-rdna4.ps1").read_text(encoding="utf-8-sig")
        self.assertIn(f'$MiraSceneCommit = "{code["commit"]}"', updater)
        self.assertIn(f'$MiraSceneRepoUrl = "{code["repository"]}.git"', updater)
        runtime = (PACK / "mira_runtime.py").read_text(encoding="utf-8")
        self.assertIn(f'PINNED_COMMIT = "{code["commit"]}"', runtime)
        # nothing of the unlicensed repository is shipped: no copied module names inside the pack
        for path in PACK.rglob("*.py"):
            self.assertNotRegex(path.read_text(encoding="utf-8"), re.compile(r"^class CCMVoxelPipeline", re.M), path.name)


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.2.9 GPU run")
class LiveEvidenceTests(unittest.TestCase):
    def test_report_matches_the_shipped_files_and_every_run_succeeded(self):
        import subprocess
        from tools.workflow_names_v131 import old_key
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        built = build_all()
        for path in PATHS.values():
            # The evidence describes the files as released in v1.2.9 (v1.3.0 names). v1.3.1 renamed them and the notes
            # that name each other follow, so today's files are the builder's output instead.
            released = subprocess.check_output(["git", "show", f"v1.2.9:workflows/{old_key(path)}"], cwd=ROOT)
            self.assertEqual(report["workflows"][path]["sha256"], hashlib.sha256(released).hexdigest(), path)
            self.assertEqual(json.loads((ROOT / "workflows" / path).read_text(encoding="utf-8")), built[path], path)
        for name in ("nodes.py", "helpers.py", "mira_runtime.py"):
            self.assertEqual(report["pack"][name], hashlib.sha256((PACK / name).read_bytes()).hexdigest(), name)
        finals = [run for run in report["runs"] if run.get("final")]
        self.assertEqual({run["workflow"] for run in finals}, set(PATHS.values()))
        for run in report["runs"]:
            self.assertEqual(run["status"], run.get("expected_status", "success"), run["case"])

    def test_scenes_contain_every_object_and_a_floor(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        for run in (r for r in report["runs"] if r.get("final")):
            check = run["check"]
            self.assertEqual(check["objects_in_glb"], check["objects_kept"], run["case"])
            self.assertTrue(check["floor"], run["case"])
            self.assertLess(check["peak_commit_gib"], 90.0, run["case"])


if __name__ == "__main__":
    unittest.main()
