from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from tools.migrate_workflows_v092 import migrate_workflow
from tools.upgrade_v095 import (
    UPGRADE_VERSION,
    VOICE_PATH,
    VOICE_SOURCE,
    VOICE_UPGRADE_KEY,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / Path(VOICE_PATH)


def load() -> dict:
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


class V095LiveVoiceWorkflowTests(unittest.TestCase):
    def test_v094_launcher_source_reconstructs_workflow_exactly(self):
        previous = json.loads(
            subprocess.check_output(
                ["git", "show", f"v0.9.4:workflows/{VOICE_SOURCE}"],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
            )
        )
        self.assertEqual(migrate_workflow(previous, VOICE_PATH), load())

    def test_workflow_is_idempotent_and_has_one_control_and_timer(self):
        workflow = load()
        self.assertEqual(migrate_workflow(workflow, VOICE_PATH), workflow)
        self.assertEqual(sum(node["type"] == "DaWMultiGPUDeviceControl" for node in workflow["nodes"]), 1)
        self.assertEqual(sum(node["type"] == "PixaromaRunTimer" for node in workflow["nodes"]), 1)
        self.assertEqual(sum(node["type"] == "DaWastehLiveVoiceSwapLauncher" for node in workflow["nodes"]), 1)

    def test_launcher_defaults_to_verified_local_start_and_no_bundled_voice(self):
        workflow = load()
        launcher = next(node for node in workflow["nodes"] if node["type"] == "DaWastehLiveVoiceSwapLauncher")
        self.assertEqual(
            launcher["widgets_values"],
            ["start / open UI", "L:/ComfyUI/voice-changer-dml-b2332", True],
        )
        self.assertEqual([output["type"] for output in launcher["outputs"]], ["STRING", "STRING", "INT"])
        marker = workflow["extra"][VOICE_UPGRADE_KEY]
        self.assertEqual(marker["version"], UPGRADE_VERSION)
        self.assertEqual(marker["release"], "v0.9.5")
        self.assertEqual(marker["runtime_downloads"], 0)
        self.assertFalse(marker["voice_model_bundled"])
        self.assertTrue(marker["live_audio_outside_comfy_queue"])
        self.assertEqual(marker["fixed_loopback_url"], "http://127.0.0.1:18888/")

    def test_note_is_explicit_about_omnivoice_consent_credit_and_routing(self):
        workflow = load()
        note = next(node for node in workflow["nodes"] if node["type"] == "PixaromaNote")
        payload = json.loads(note["widgets_values"][0])
        content = payload["content"]
        self.assertIn("OmniVoice wurde bewusst nicht verwendet", content)
        self.assertIn("kein echtes inkrementelles Speech-to-Speech-Streaming", content)
        self.assertIn("Amitaro's Voice Material Studio", content)
        self.assertIn("Keine Täuschung", content)
        self.assertIn("virtuelles Audiokabel", content)
        self.assertIn("stop verified service", content)

    def test_node_is_registered_in_bundled_pack(self):
        init_text = (ROOT / "custom_nodes/ComfyUI-DaWasteh-LiveAvatar/__init__.py").read_text(encoding="utf-8")
        self.assertIn('"DaWastehLiveVoiceSwapLauncher": DaWastehLiveVoiceSwapLauncher', init_text)
        self.assertTrue((ROOT / "docs/OMNIVOICE_LIVE_SWAP_EVALUATION.md").is_file())


if __name__ == "__main__":
    unittest.main()
