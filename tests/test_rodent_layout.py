from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.rodent_layout import RODENT_KEY, RODENT_VERSION, STAGE_COLORS, _topology_hash

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"


def graphs(workflow: dict):
    yield workflow
    for child in workflow.get("definitions", {}).get("subgraphs", []):
        yield from graphs(child)


def rect(values):
    x, y, width, height = values
    return float(x), float(y), float(x) + float(width), float(y) + float(height)


def overlaps(left, right):
    return left[0] < right[2] and left[2] > right[0] and left[1] < right[3] and left[3] > right[1]


class RodentLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = [
            (path, json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(WORKFLOWS.rglob("*.json"))
        ]

    def test_every_graph_is_marked_and_credits_nerdy_rodent(self):
        for path, workflow in self.items:
            for graph in graphs(workflow):
                marker = graph.get("extra", {}).get(RODENT_KEY, {})
                self.assertEqual(marker.get("version"), RODENT_VERSION, path.name)
                self.assertEqual(marker.get("method"), "RODENT Method", path.name)
                self.assertEqual(marker.get("credit"), "Nerdy Rodent", path.name)
                self.assertEqual(marker.get("algorithm"), "rodent-v1", path.name)
                self.assertEqual(marker.get("topology_sha256"), _topology_hash(graph), path.name)

    def test_standard_groups_have_stage_labels_and_palette(self):
        palette = set(STAGE_COLORS.values())
        for path, workflow in self.items:
            for graph in graphs(workflow):
                marker = graph["extra"][RODENT_KEY]
                if marker["exceptions"]:
                    continue
                for group in graph.get("groups", []):
                    title = str(group.get("title", ""))
                    self.assertRegex(title, r"^[RODENT][19] · ", path.name)
                    self.assertIn(group.get("color"), palette, path.name)
                    self.assertEqual(group.get("font_size"), 24, path.name)

    def test_standard_nodes_are_grid_aligned_and_belong_to_one_group(self):
        for path, workflow in self.items:
            for graph in graphs(workflow):
                marker = graph["extra"][RODENT_KEY]
                if marker["exceptions"]:
                    continue
                groups = [rect(group["bounding"]) for group in graph.get("groups", [])]
                for node in graph.get("nodes", []):
                    x, y = node.get("pos", [0, 0])[:2]
                    self.assertAlmostEqual(float(x) % 20.0, 0.0, places=5, msg=path.name)
                    self.assertAlmostEqual(float(y) % 20.0, 0.0, places=5, msg=path.name)
                    width, height = node.get("size", [280, 140])[:2]
                    cx = float(x) + float(width) / 2
                    cy = float(y) + float(height) / 2
                    memberships = sum(left <= cx <= right and top <= cy <= bottom for left, top, right, bottom in groups)
                    self.assertEqual(memberships, 1, f"{path.name}: node {node.get('id')}")

    def test_native_groups_do_not_overlap(self):
        for path, workflow in self.items:
            for graph in graphs(workflow):
                marker = graph["extra"][RODENT_KEY]
                if "pixaroma-group-demo-authored-geometry-preserved" in marker["exceptions"]:
                    continue
                groups = [(group.get("id"), rect(group["bounding"])) for group in graph.get("groups", [])]
                for index, (left_id, left_rect) in enumerate(groups):
                    for right_id, right_rect in groups[index + 1:]:
                        self.assertFalse(overlaps(left_rect, right_rect), f"{path.name}: groups {left_id}/{right_id}")

    def test_parameter_notes_are_collected_in_reference_modules(self):
        checked = 0
        for path, workflow in self.items:
            for graph in graphs(workflow):
                marker = graph["extra"][RODENT_KEY]
                if marker["exceptions"]:
                    continue
                notes = [node for node in graph.get("nodes", []) if node.get("properties", {}).get("dawasteh_generated_note")]
                if not notes:
                    continue
                checked += 1
                reference = next(group for group in graph["groups"] if group["title"] == "R9 · PARAMETER REFERENCE")
                bounds = rect(reference["bounding"])
                for note in notes:
                    x, y = note["pos"][:2]
                    width, height = note["size"][:2]
                    self.assertTrue(bounds[0] <= x + width / 2 <= bounds[2], path.name)
                    self.assertTrue(bounds[1] <= y + height / 2 <= bounds[3], path.name)
        self.assertGreater(checked, 200)


if __name__ == "__main__":
    unittest.main()
