from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.integrate_duration_seconds import (
    DURATION_KEY,
    DURATION_VERSION,
    DYNAMIC_SOURCE_FPS_PATHS,
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
        # v1.1.3: Ref2VA-Dublette konsolidiert (54 -> 53)
        self.assertEqual(checked, 53)
        self.assertEqual(modes, {
            # v1.1.3: Ref2VA-Dublette konsolidiert (32 -> 31)
            "native-seconds": 31,
            "explicit-seconds-to-model-valid-frames": 12,
            "explicit-seconds-dynamic-source-fps": 1,
            "source-media-duration": 9,
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

    def test_wan_animate_uses_seconds_source_fps_and_4n_plus_1_frames(self):
        self.assertEqual(DYNAMIC_SOURCE_FPS_PATHS, {
            "Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json"
        })
        key = next(iter(DYNAMIC_SOURCE_FPS_PATHS))
        workflow = json.loads((WORKFLOWS / key).read_text(encoding="utf-8"))
        marker = workflow["extra"][DURATION_KEY]
        self.assertEqual(marker["mode"], "explicit-seconds-dynamic-source-fps")
        nodes = {node.get("id"): node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        seconds = next(node for node in nodes.values() if node.get("title") == "OUTPUT DURATION · SECONDS")
        math_node = next(node for node in nodes.values() if node.get("title") == "SECONDS + SOURCE FPS → WAN 4n+1 FRAMES")
        self.assertEqual(seconds["widgets_values"], [3.0])
        self.assertEqual(
            math_node["widgets_values"][0],
            "max(5, round((a * b - 1) / 4) * 4 + 1)",
        )
        self.assertEqual(links[868][1:5], [seconds["id"], 0, math_node["id"], 0])
        self.assertEqual(links[869][1:5], [288, 2, math_node["id"], 1])
        self.assertEqual(links[870][1:5], [math_node["id"], 1, 261, 24])
        target = nodes[261]
        self.assertEqual(target["inputs"][24]["name"], "length")
        self.assertEqual(target["inputs"][24]["link"], 870)
        self.assertTrue(target["widgets_values"][7], "context windows must be enabled for longer durations")
        self.assertEqual(nodes[477]["mode"], 4, "manual second segment must stay bypassed")
        self.assertEqual(nodes[189]["type"], "DaWAdaptiveLoadImage")
        self.assertEqual(nodes[240]["type"], "DaWAdaptiveLoadVideo")
        for link_id, expected in {
            864: [189, 2, 261, 14],
            865: [189, 3, 261, 15],
            866: [189, 2, 477, 14],
            867: [189, 3, 477, 15],
        }.items():
            self.assertEqual(links[link_id][1:5], expected)
        note_text = {
            node.get("properties", {}).get("dawasteh_note_for"): node["widgets_values"][0]
            for node in workflow["nodes"]
            if node.get("properties", {}).get("dawasteh_generated_note")
        }
        self.assertIn("Adaptive Load Image", note_text[189])
        self.assertIn("`length` (INT, Link 870)", note_text[261])
        self.assertIn("`fps` (FLOAT, 2 Verbindung(en))", note_text[288])

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
