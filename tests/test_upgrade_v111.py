"""v1.1.1 RDNA4 performance migration: idempotence, markers and the measured widget changes."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import upgrade_v111 as up

WORKFLOWS = Path("workflows")


def load(rel: str) -> dict:
    return json.loads((WORKFLOWS / rel).read_text(encoding="utf-8"))


class UpgradeV111Tests(unittest.TestCase):
    def test_checked_in_collection_is_in_v111_form_and_idempotent(self):
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            wf = load(rel)
            self.assertEqual(up.apply(wf, rel), wf, rel)
            self.assertEqual(up.apply(up.apply(wf, rel), rel), wf, rel)

    def test_targets_carry_marker_and_others_do_not(self):
        targets = up.targets()
        self.assertGreaterEqual(len(targets), 70)
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            marker = load(rel).get("extra", {}).get(up.MARKER_KEY, {}).get("version")
            self.assertEqual(marker == up.MARKER_VERSION, rel in targets, rel)

    def test_wan_i2v_graphs_use_16_channel_latent_path(self):
        for rel in up.WAN_I2V:
            wf = load(rel)
            types = [n["type"] for n in wf["nodes"]]
            self.assertIn("WanImageToVideo", types, rel)
            self.assertNotIn("Wan22ImageToVideoLatent", types, rel)
            vaes = [n["widgets_values"][0] for n in wf["nodes"] if n["type"] == "VAELoader"]
            self.assertTrue(all("wan_2.1_vae" in v for v in vaes), (rel, vaes))
            node = next(n for n in wf["nodes"] if n["type"] == "WanImageToVideo")
            self.assertEqual([o["name"] for o in node["outputs"]], ["positive", "negative", "latent"])
            links = {l[0]: l for l in wf["links"]}
            for sampler in (n for n in wf["nodes"] if n["type"] in ("KSampler", "KSamplerAdvanced")):
                for inp in sampler["inputs"]:
                    if inp["name"] in ("positive", "negative"):
                        self.assertEqual(links[inp["link"]][1], node["id"], (rel, sampler["id"], inp["name"]))

    def test_train_lora_widgets_include_control_after_generate(self):
        for rel in up.TRAIN:
            wf = load(rel)
            node = next(n for n in wf["nodes"] if n["type"] == "TrainLoraNode")
            names = [i["name"] for i in node["inputs"] if i.get("widget")]
            self.assertEqual(len(node["widgets_values"]), len(names) + 1, rel)
            self.assertEqual(node["widgets_values"][names.index("seed") + 1], "fixed", rel)

    def test_cleanup_barriers_keep_unload_only_outside_image_audio_categories(self):
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            category = rel.split("/")[0]
            wf = load(rel)
            for g in up._graphs(wf):
                for n in g.get("nodes", []):
                    if n.get("type") != "VRAM_Debug":
                        continue
                    unload = n["widgets_values"][2]
                    if category in up.E1_CATEGORIES and rel not in up.E1_EXCLUDE:
                        self.assertIs(unload, False, rel)
                    else:
                        self.assertIs(unload, True, rel)

    def test_device_placement(self):
        for rel in up.E2_IMAGE:
            ctl = next(n for n in load(rel)["nodes"] if n["type"] == "DaWMultiGPUDeviceControl")
            self.assertEqual(ctl["widgets_values"], ["gpu:0", "gpu:0", "gpu:0"], rel)
        for rel in up.E2B_LTX:
            ctl = next(n for n in load(rel)["nodes"] if n["type"] == "DaWMultiGPUDeviceControl")
            self.assertEqual(ctl["widgets_values"], ["gpu:0", "gpu:0", "gpu:1"], rel)


if __name__ == "__main__":
    unittest.main()
