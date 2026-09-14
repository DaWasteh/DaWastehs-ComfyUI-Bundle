import hashlib
import json
from pathlib import Path
import unittest

from tools.build_workflows_v118 import build_all, SCHEMAS
from tools.install_models_v118 import model_files
from tools.validate_workflows import validate_graph
from tools.rodent_layout import _topology_hash

ROOT = Path(__file__).resolve().parents[1]


class WorkflowV118Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = build_all(json.loads(SCHEMAS.read_text(encoding="utf-8")))

    def test_builder_restores_legacy_schema_cache(self):
        import copy
        from tools import migrate_workflows_v092 as migration

        before = copy.deepcopy(migration.OBJECT_INFO)
        build_all(json.loads(SCHEMAS.read_text(encoding="utf-8")))
        self.assertEqual(migration.OBJECT_INFO, before)

    def test_checked_in_graphs_rebuild_exactly(self):
        audit = json.loads(
            (ROOT / "performance/rdna4/v118-validation.json").read_text(
                encoding="utf-8"
            )
        )
        records = {entry["workflow"]: entry for entry in audit["runs"]}
        self.assertEqual(len(records), 13)
        for path, workflow in self.workflows.items():
            entry = records["workflows/" + path]
            self.assertEqual(entry["status"], "success")
            self.assertTrue(entry["executed_contract_matches_final"])
            self.assertEqual(
                entry["workflow_sha256"],
                hashlib.sha256((ROOT / "workflows" / path).read_bytes()).hexdigest(),
            )
            self.assertEqual(
                json.loads((ROOT / "workflows" / path).read_text(encoding="utf-8")),
                workflow,
            )

    def test_thirteen_explicit_graphs_are_valid(self):
        self.assertEqual(len(self.workflows), 13)
        for path, w in self.workflows.items():
            with self.subTest(path=path):
                errors = []
                validate_graph(Path(path), "root", w, errors)
                self.assertEqual(errors, [])
                self.assertEqual(
                    sum(n["type"] == "PixaromaRunTimer" for n in w["nodes"]), 1
                )
                self.assertEqual(
                    sum(n["type"] == "DaWMultiGPUDeviceControl" for n in w["nodes"]), 1
                )
                self.assertEqual(
                    w["extra"]["dawasteh_rodent_layout"]["topology_sha256"],
                    _topology_hash(w),
                )
                self.assertFalse(w.get("definitions", {}).get("subgraphs"))

    def test_yue_is_private_and_duration_is_derived(self):
        for path, w in self.workflows.items():
            if not path.startswith("Music Generation/"):
                continue
            self.assertIn("PRIVATE", path)
            types = {n["type"] for n in w["nodes"]}
            self.assertIn("YuE2GenerateMusic", types)
            self.assertIn("EmptyYuE2LatentAudio", types)
            self.assertIn("CC-BY-NC-4.0", json.dumps(w, ensure_ascii=False))
            music = next(n for n in w["nodes"] if n["type"] == "YuE2GenerateMusic")
            latent = next(n for n in w["nodes"] if n["type"] == "EmptyYuE2LatentAudio")
            self.assertTrue(
                any(
                    link[1] == music["id"] and link[2] == 1 and link[3] == latent["id"]
                    for link in w["links"]
                )
            )

    def test_video_has_active_output_and_bounded_reference(self):
        for path, w in self.workflows.items():
            if not path.startswith("Controlled Video/"):
                continue
            save = next(n for n in w["nodes"] if n["type"] == "SaveWEBM")
            self.assertEqual(save["mode"], 0)
            self.assertEqual(save["widgets_values"][2], 16)
            self.assertEqual(w["extra"]["dawasteh_duration_seconds"]["fps"], 16)
        w = self.workflows[
            "Controlled Video/Cosmos_Predict2_2B-Video-Continuation.json"
        ]
        load = next(n for n in w["nodes"] if n["type"] == "DaWVideoFrames")
        self.assertEqual(load["widgets_values"][1:], [16, 848, 480, 5])
        self.assertEqual([slot["type"] for slot in load["outputs"]], ["IMAGE"])
        self.assertNotIn("VHS_LoadVideo", {n["type"] for n in w["nodes"]})

    def test_assets_use_real_cpu_collision_and_correct_conditioning(self):
        for path, w in self.workflows.items():
            if not path.startswith("Game Development/"):
                continue
            types = {n["type"] for n in w["nodes"]}
            self.assertIn("DaWCollisionProxy", types)
            self.assertNotIn(
                "VaeDecodeTextureTrellis", types
            ) if "Shape-Collision" in path else self.assertIn(
                "VaeDecodeTextureTrellis", types
            )
            if "TRELLIS2" in path:
                self.assertIn("Trellis2Conditioning", types)
                self.assertNotIn("LoadMoGeModel", types)
                self.assertNotIn("Pixal3DConditioning", types)
            if "MultiView" in path:
                self.assertIn("Pixal3DMultiViewConditioning", types)
                self.assertIn(
                    "pixal3d_multiview_int8_convrot.safetensors", json.dumps(w)
                )
                self.assertEqual(sum(n["type"] == "LoadImage" for n in w["nodes"]), 4)

    def test_sight_and_collision_share_budgeted_mesh_without_duplicate_links(self):
        for path, w in self.workflows.items():
            if not path.startswith("Game Development/"):
                continue
            nodes = {n["id"]: n for n in w["nodes"]}
            self.assertEqual(nodes[324]["widgets_values"][0], 12000)
            self.assertEqual(nodes[186]["widgets_values"][1], "midpoint")
            self.assertTrue(
                any(link[1] == 324 and link[3] == 186 for link in w["links"])
            )
            collision = next(n for n in w["nodes"] if n["type"] == "DaWCollisionProxy")
            self.assertTrue(
                any(
                    link[1] == 186 and link[3] == collision["id"] for link in w["links"]
                )
            )
            target_slots = [(link[3], link[4]) for link in w["links"]]
            self.assertEqual(len(target_slots), len(set(target_slots)))
            converter_link = next(
                link for link in w["links"] if link[3] == 322 and link[4] == 0
            )
            self.assertEqual(nodes[converter_link[1]]["type"], "MeshToFile3D")
            if "Shape-Collision" in path:
                self.assertTrue(
                    any(
                        link[1] == 186 and link[3] == converter_link[1]
                        for link in w["links"]
                    )
                )

    def test_cosmos_text_to_video_really_chains_both_models(self):
        w = self.workflows["Controlled Video/Cosmos_Predict2_2B-Text-to-Video.json"]
        nodes = {n["id"]: n for n in w["nodes"]}
        self.assertEqual(sum(n["type"] == "UNETLoader" for n in nodes.values()), 2)
        self.assertEqual(sum(n["type"] == "KSampler" for n in nodes.values()), 2)
        latent = nodes[28]
        start_slot = next(
            i
            for i, slot in enumerate(latent["inputs"])
            if slot["name"] == "start_image"
        )
        decoder_id = next(
            link[1] for link in w["links"] if link[3] == 28 and link[4] == start_slot
        )
        self.assertEqual(nodes[decoder_id]["type"], "VAEDecode")
        sampler_id = next(
            link[1] for link in w["links"] if link[3] == decoder_id and link[4] == 0
        )
        self.assertEqual(nodes[sampler_id]["type"], "KSampler")
        self.assertNotEqual(sampler_id, 3)

    def test_every_model_is_hash_and_revision_pinned(self):
        items = model_files()
        self.assertEqual(len(items), 15)
        self.assertEqual(len({i["path"] for i in items}), len(items))
        for item in items:
            self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(item["revision"], r"^[a-f0-9]{40}$")
            self.assertGreater(item["size"], 0)
            self.assertNotIn("..", Path(item["path"]).parts)

    def test_source_hashes(self):
        root = ROOT / "tools/workflow_templates/v118"
        for item in json.loads((root / "sources.json").read_text()):
            self.assertEqual(
                hashlib.sha256((root / item["file"]).read_bytes()).hexdigest(),
                item["sha256"],
            )


if __name__ == "__main__":
    unittest.main()
