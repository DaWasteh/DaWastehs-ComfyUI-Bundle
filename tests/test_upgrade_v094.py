from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.migrate_workflows_v092 import migrate_workflow
from tools.upgrade_v094 import UPGRADE_KEY, UPGRADE_VERSION, WAN_PATH


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "workflows" / WAN_PATH


class UpgradeV094Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.current = json.loads(WORKFLOW.read_text(encoding="utf-8"))

    def test_v093_release_upgrades_deterministically_to_checked_workflow(self):
        previous_text = subprocess.check_output(
            ["git", "show", f"v0.9.3:workflows/{WAN_PATH}"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        previous = json.loads(previous_text)
        self.assertEqual(migrate_workflow(previous, WAN_PATH), self.current)

    def test_previous_upgrade_marker_refreshes_stale_generated_notes_in_place(self):
        prior = copy.deepcopy(self.current)
        prior["extra"][UPGRADE_KEY]["version"] = UPGRADE_VERSION - 1
        note = next(
            node for node in prior["nodes"]
            if node.get("properties", {}).get("dawasteh_note_for") == 189
        )
        note_id = note["id"]
        note["title"] = "stale"
        note["widgets_values"] = ["stale"]
        upgraded = migrate_workflow(prior, WAN_PATH)
        self.assertEqual(upgraded, self.current)
        refreshed = next(node for node in upgraded["nodes"] if node.get("id") == note_id)
        self.assertIn("Adaptive Load Image", refreshed["title"])
        self.assertIn("without cropping", refreshed["widgets_values"][0])
        extension_note = next(node for node in upgraded["nodes"] if node.get("id") == 539)
        self.assertIn("OUTPUT DURATION · SECONDS", extension_note["widgets_values"][0])
        self.assertIn("optional expert tools", extension_note["widgets_values"][0])

    def test_current_upgrade_is_idempotent(self):
        self.assertEqual(migrate_workflow(self.current, WAN_PATH), self.current)


if __name__ == "__main__":
    unittest.main()
