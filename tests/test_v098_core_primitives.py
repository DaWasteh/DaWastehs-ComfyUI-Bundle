from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from tools.migrate_workflows_v092 import migrate_workflow
from tools.upgrade_v098 import REMOVED_PACK, REPLACEMENTS, TARGET_PATHS, UPGRADE_KEY, UPGRADE_VERSION, upgrade_workflow


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"


def load(path_key: str) -> dict:
    return json.loads((WORKFLOWS / Path(path_key)).read_text(encoding="utf-8"))


def by_id(workflow: dict) -> dict[int, dict]:
    return {node["id"]: node for node in workflow["nodes"]}


def previous_release(path_key: str) -> dict:
    return json.loads(
        subprocess.check_output(
            ["git", "show", f"v0.9.7:workflows/{path_key}"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
    )


class V098CorePrimitiveTests(unittest.TestCase):
    def test_v097_release_reconstructs_current_workflows_exactly(self):
        for path_key in sorted(TARGET_PATHS):
            with self.subTest(path=path_key):
                self.assertEqual(migrate_workflow(previous_release(path_key), path_key), load(path_key))

    def test_upgrade_is_idempotent_and_scoped(self):
        for path_key in sorted(TARGET_PATHS):
            with self.subTest(path=path_key):
                workflow = load(path_key)
                upgraded, changed = upgrade_workflow(workflow, path_key)
                self.assertFalse(changed)
                self.assertEqual(upgraded, workflow)
        untouched = "Text to Image/ZImage_turbo-Text-to-Image.json"
        workflow = load(untouched)
        upgraded, changed = upgrade_workflow(workflow, untouched)
        self.assertFalse(changed)
        self.assertEqual(upgraded, workflow)
        self.assertNotIn(UPGRADE_KEY, upgraded.get("extra", {}))

    def test_no_workflow_still_depends_on_the_removed_pack(self):
        for path in sorted(WORKFLOWS.rglob("*.json")):
            workflow = json.loads(path.read_text(encoding="utf-8-sig"))
            graphs = [workflow, *(workflow.get("definitions", {}).get("subgraphs", []) or [])]
            for graph in graphs:
                for node in graph.get("nodes", []):
                    self.assertNotIn(node.get("type"), REPLACEMENTS, f"{path}: node {node.get('id')}")
                    self.assertNotEqual(node.get("properties", {}).get("cnr_id"), REMOVED_PACK, f"{path}: node {node.get('id')}")

    def test_replacements_preserve_values_links_and_positions(self):
        for path_key in sorted(TARGET_PATHS):
            with self.subTest(path=path_key):
                before = by_id(previous_release(path_key))
                after = load(path_key)
                marker = after["extra"][UPGRADE_KEY]
                self.assertEqual(marker["version"], UPGRADE_VERSION)
                self.assertEqual(marker["removed_pack"], REMOVED_PACK)
                self.assertGreaterEqual(len(marker["replaced"]), 1)
                current = by_id(after)
                for entry in marker["replaced"]:
                    old = before[entry["id"]]
                    new = current[entry["id"]]
                    self.assertEqual(old["type"], entry["from"])
                    self.assertEqual(new["type"], entry["to"])
                    self.assertEqual(new["type"], REPLACEMENTS[entry["from"]]["type"])
                    self.assertEqual(new["properties"]["cnr_id"], "comfy-core")
                    self.assertEqual([slot["links"] for slot in old["outputs"]], [slot["links"] for slot in new["outputs"]])
                    self.assertEqual([slot["type"] for slot in old["outputs"]], [slot["type"] for slot in new["outputs"]])
                    self.assertEqual(len(new["inputs"]), 1)
                    self.assertEqual(new["inputs"][0]["name"], "value")
                    self.assertIsNone(new["inputs"][0]["link"])
                    if new["type"] == "PrimitiveInt":
                        self.assertEqual(new["widgets_values"], [old["widgets_values"][0], old["widgets_values"][1]])
                    else:
                        self.assertEqual(new["widgets_values"], [old["widgets_values"][0]])
                    note = next(
                        node for node in after["nodes"]
                        if node.get("properties", {}).get("dawasteh_note_for") == entry["id"]
                    )
                    self.assertIn(f"Node {entry['id']}", note["title"])
                    self.assertNotIn("Image Saver", note["title"])
                    self.assertNotIn("Image Saver", note["widgets_values"][0])
                    self.assertNotIn("dawasteh_refresh_generated_note", new["properties"])


if __name__ == "__main__":
    unittest.main()
