"""v1.1.2 LoRA trainer migration: per-block gradient checkpointing, idempotence and markers."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import upgrade_v111 as v111
from tools import upgrade_v112 as up

WORKFLOWS = Path("workflows")


def load(rel: str) -> dict:
    return json.loads((WORKFLOWS / rel).read_text(encoding="utf-8"))


class UpgradeV112Tests(unittest.TestCase):
    def test_checked_in_collection_is_in_v112_form_and_idempotent(self):
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            wf = load(rel)
            self.assertEqual(up.apply(wf, rel), wf, rel)
            self.assertEqual(up.apply(up.apply(wf, rel), rel), wf, rel)

    def test_targets_are_the_five_core_trainers_plus_measured_placements_and_carry_the_marker(self):
        self.assertEqual(up.targets(), v111.TRAIN | up.E2_REMAINING)
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            marker = load(rel).get("extra", {}).get(up.MARKER_KEY, {}).get("version")
            self.assertEqual(marker == up.MARKER_VERSION, rel in up.targets(), rel)

    def test_trainers_checkpoint_per_block(self):
        for rel in up.TRAIN_DEPTH2:
            wf = load(rel)
            node = next(n for n in wf["nodes"] if n["type"] == "TrainLoraNode")
            names = [i["name"] for i in node["inputs"] if i.get("widget")]
            idx = up.train_widget_index(node, "checkpoint_depth")
            self.assertIsNotNone(idx, rel)
            self.assertEqual(node["widgets_values"][idx], up.CHECKPOINT_DEPTH, rel)
            # gradient checkpointing itself stays on, and the v1.1.1 control_after_generate value is intact
            self.assertIs(node["widgets_values"][up.train_widget_index(node, "gradient_checkpointing")], True, rel)
            self.assertEqual(node["widgets_values"][names.index("seed") + 1], "fixed", rel)

    def test_apply_rebuilds_v112_from_the_v111_form(self):
        for rel in up.TRAIN_DEPTH2:
            wf = load(rel)
            older = json.loads(json.dumps(wf))
            node = next(n for n in older["nodes"] if n["type"] == "TrainLoraNode")
            node["widgets_values"][up.train_widget_index(node, "checkpoint_depth")] = 1
            older["extra"].pop(up.MARKER_KEY, None)
            self.assertNotEqual(older, wf)
            self.assertEqual(up.apply(older, rel), wf, rel)

    def test_measured_placements_are_all_gpu0(self):
        for rel in up.E2_REMAINING:
            wf = load(rel)
            ctl = next(n for n in wf["nodes"] if n["type"] == "DaWMultiGPUDeviceControl")
            self.assertEqual(ctl["widgets_values"], up.ALL_GPU0, rel)
            self.assertEqual(wf["extra"]["dawasteh_dual_gpu"]["defaults"], {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"}, rel)
            older = json.loads(json.dumps(wf))
            next(n for n in older["nodes"] if n["type"] == "DaWMultiGPUDeviceControl")["widgets_values"] = ["gpu:0", "gpu:1", "gpu:1"]
            older["extra"]["dawasteh_dual_gpu"]["defaults"] = {"MODEL": "gpu:0", "CLIP": "gpu:1", "VAE": "gpu:1"}
            older["extra"].pop(up.MARKER_KEY, None)
            self.assertEqual(up.apply(older, rel), wf, rel)

    def test_widget_index_handles_both_serialisations(self):
        node = {
            "inputs": [{"name": n, "widget": {"name": n}} for n in ("batch_size", "seed", "checkpoint_depth")],
            "widgets_values": [1, 42, "fixed", 1],
        }
        self.assertEqual(up.train_widget_index(node, "checkpoint_depth"), 3)
        node["widgets_values"] = [1, 42, 1]
        self.assertEqual(up.train_widget_index(node, "checkpoint_depth"), 2)
        self.assertIsNone(up.train_widget_index(node, "missing"))


if __name__ == "__main__":
    unittest.main()
