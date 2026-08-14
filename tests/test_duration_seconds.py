from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.integrate_duration_seconds import (
    DURATION_KEY,
    DURATION_VERSION,
    GENERATION_FOLDERS,
    SOURCE_DURATION_PATHS,
    SPECS,
    integrate_duration_seconds,
    model_frame_count,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"


class DurationSecondsTests(unittest.TestCase):
    def test_every_music_and_video_generation_workflow_has_a_seconds_contract(self):
        modes: dict[str, int] = {}
        checked = 0
        for path in sorted(WORKFLOWS.rglob("*.json")):
            if path.parent.name not in GENERATION_FOLDERS:
                continue
            checked += 1
            workflow = json.loads(path.read_text(encoding="utf-8"))
            marker = workflow.get("extra", {}).get(DURATION_KEY, {})
            self.assertEqual(marker.get("version"), DURATION_VERSION, path.name)
            self.assertEqual(marker.get("unit"), "seconds", path.name)
            modes[marker["mode"]] = modes.get(marker["mode"], 0) + 1
        self.assertEqual(checked, 54)
        self.assertEqual(modes, {
            "native-seconds": 32,
            "explicit-seconds-to-model-valid-frames": 12,
            "source-media-duration": 10,
        })

    def test_explicit_controls_drive_every_manifested_frame_input(self):
        for key, spec in SPECS.items():
            workflow = json.loads((WORKFLOWS / key).read_text(encoding="utf-8"))
            nodes = {node.get("id"): node for node in workflow["nodes"]}
            links = {link[0]: link for link in workflow["links"]}
            seconds = next(node for node in nodes.values() if node.get("properties", {}).get("dawasteh_duration_control") and node.get("type") == "PrimitiveFloat")
            math_node = next(node for node in nodes.values() if node.get("properties", {}).get("dawasteh_duration_control") and node.get("type") == "ComfyMathExpression")
            self.assertEqual(seconds["widgets_values"], [spec.default_seconds], key)
            expression = math_node["widgets_values"][0]
            self.assertIn(f"a * {spec.fps:g}", expression, key)
            self.assertIn(f"/ {spec.alignment}", expression, key)
            seconds_link = links[math_node["inputs"][0]["link"]]
            self.assertEqual(seconds_link[1:5], [seconds["id"], 0, math_node["id"], 0], key)
            for node_id, input_name in spec.targets:
                target = nodes[node_id]
                target_slot = next(index for index, item in enumerate(target["inputs"]) if item["name"] == input_name)
                link = links[target["inputs"][target_slot]["link"]]
                self.assertEqual(link[1:5], [math_node["id"], 1, node_id, target_slot], key)
                self.assertEqual(link[5], "INT", key)
            sink_fps = set()
            for node in workflow["nodes"]:
                if node.get("type") not in {"CreateVideo", "VHS_VideoCombine"}:
                    continue
                values = node.get("widgets_values")
                value = values.get("frame_rate") if isinstance(values, dict) else values[0] if isinstance(values, list) and values else None
                if isinstance(value, (int, float)):
                    sink_fps.add(float(value))
            self.assertIn(spec.fps, sink_fps, key)

    def test_frame_formulas_obey_minimum_alignment_and_duration_error_bound(self):
        for key, spec in SPECS.items():
            for seconds in (0.0, 0.5, spec.default_seconds, spec.default_seconds + 0.37):
                frames = model_frame_count(seconds, spec)
                self.assertGreaterEqual(frames, spec.minimum, key)
                self.assertEqual((frames - 1) % spec.alignment, 0, key)
                if frames > spec.minimum:
                    represented = (frames - 1) / spec.fps
                    self.assertLessEqual(abs(represented - seconds), spec.alignment / (2 * spec.fps) + 1e-9, key)

    def test_source_driven_workflows_are_documented_without_fake_frame_controls(self):
        for key in SOURCE_DURATION_PATHS:
            workflow = json.loads((WORKFLOWS / key).read_text(encoding="utf-8"))
            marker = workflow["extra"][DURATION_KEY]
            self.assertEqual(marker["mode"], "source-media-duration", key)
            self.assertFalse(any(
                node.get("properties", {}).get("dawasteh_duration_control")
                for node in workflow["nodes"]
            ), key)

    def test_duration_integration_is_idempotent(self):
        for path in sorted(WORKFLOWS.rglob("*.json")):
            key = path.relative_to(WORKFLOWS).as_posix()
            if path.parent.name not in GENERATION_FOLDERS:
                continue
            workflow = json.loads(path.read_text(encoding="utf-8"))
            migrated, changed = integrate_duration_seconds(workflow, key)
            self.assertFalse(changed, key)
            self.assertEqual(migrated, workflow, key)


if __name__ == "__main__":
    unittest.main()
