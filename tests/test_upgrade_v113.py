"""v1.1.3 MiniMax-H3-Audiofix: Hersteller-Defaults im Audiopfad, Idempotenz und Marker."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import upgrade_v113 as up

WORKFLOWS = Path("workflows")


def load(rel: str) -> dict:
    return json.loads((WORKFLOWS / rel).read_text(encoding="utf-8"))


class UpgradeV113Tests(unittest.TestCase):
    def test_checked_in_collection_is_in_v113_form_and_idempotent(self):
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            wf = load(rel)
            self.assertEqual(up.apply(wf, rel), wf, rel)
            self.assertEqual(up.apply(up.apply(wf, rel), rel), wf, rel)

    def test_targets_are_the_five_spectrum_workflows_plus_the_director(self):
        self.assertEqual(up.targets(), up.H3_AUDIO_PATH | {up.DIRECTOR_WORKFLOW})
        self.assertEqual(len(up.H3_AUDIO_PATH), 5)
        self.assertNotIn(up.DIRECTOR_WORKFLOW, up.H3_AUDIO_PATH)
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            marker = load(rel).get("extra", {}).get(up.MARKER_KEY, {}).get("version")
            self.assertEqual(marker == up.MARKER_VERSION, rel in up.targets(), rel)

    def test_audio_sigma_shift_is_the_vendor_default(self):
        """shift_audio 3.0 = Default von MiniMaxH3SigmaShift, der Modellkonfiguration und des DiT.

        Beide gut klingenden Referenzlaeufe (MiniMax_H3_00002_/00003_) liefen ohne den Knoten,
        also auf 3.0; beide beanstandeten Laeufe auf 4.0.
        """
        self.assertEqual(up.SHIFT_AUDIO_VENDOR, 3.0)
        for rel in up.H3_AUDIO_PATH:
            wf = load(rel)
            shifts = [n["widgets_values"] for n in wf["nodes"] if n["type"] == "MiniMaxH3SigmaShift"]
            self.assertTrue(shifts, rel)
            for wv in shifts:
                self.assertEqual(wv[1], up.SHIFT_AUDIO_VENDOR, rel)
                self.assertEqual(wv[0], 12.0, f"{rel}: shift_video bleibt unveraendert")

    def test_sampler_and_scheduler_match_the_official_template(self):
        for rel in up.H3_AUDIO_PATH:
            wf = load(rel)
            for node in wf["nodes"]:
                if node["type"] == "KSamplerSelect":
                    self.assertEqual(node["widgets_values"][0], up.SAMPLER_VENDOR, rel)
                elif node["type"] == "BasicScheduler":
                    self.assertEqual(node["widgets_values"][0], up.SCHEDULER_VENDOR, rel)
                    # Schrittzahl bleibt unangetastet (Turbo-LoRA ist als Ursache ausgeschlossen)
                    self.assertEqual(node["widgets_values"][1], 8, rel)

    def test_spectrum_is_bypassed_but_still_present_as_a_speed_mode(self):
        for rel in up.H3_AUDIO_PATH:
            wf = load(rel)
            nodes = [n for n in wf["nodes"] if n["type"] == "SpectrumApplyMiniMaxH3"]
            self.assertTrue(nodes, f"{rel}: Spectrum-Knoten muss erhalten bleiben")
            for n in nodes:
                self.assertEqual(n["mode"], up.MODE_BYPASS, rel)

    def test_turbo_lora_and_device_placement_are_untouched(self):
        """Die LoRA ist durch das kontrollierte Paar 00002_/00003_ als Ursache ausgeschlossen."""
        for rel in up.H3_AUDIO_PATH:
            wf = load(rel)
            loras = [n for n in wf["nodes"] if n["type"] == "LoraLoaderModelOnly"]
            self.assertTrue(loras, rel)
            for n in loras:
                self.assertEqual(n.get("mode", 0), 0, f"{rel}: Turbo-LoRA bleibt aktiv")

    def test_apply_rebuilds_v113_from_the_v112_form(self):
        """Der v1.1.2-Zustand wird vollstaendig nachgebildet: Widgets, Titel und Hinweistexte."""
        revert = {
            "MiniMax H3 Sigma Shift — video 12 / audio 3": "MiniMax H3 Sigma Shift — video 12 / audio 4",
            "SAMPLER — res_multistep": "SAMPLER — euler",
            "SCHEDULER — simple / 8 steps": "SCHEDULER — beta / 8 steps",
            "`shift_audio` = `3.0`": "`shift_audio` = `4.0`",
            "`sampler_name` = `res_multistep`": "`sampler_name` = `euler`",
            "`scheduler` = `simple`": "`scheduler` = `beta`",
        }
        for rel in up.H3_AUDIO_PATH:
            wf = load(rel)
            raw = json.dumps(wf, ensure_ascii=False)
            for new_text, old_text in revert.items():
                raw = raw.replace(new_text, old_text)
            older = json.loads(raw)
            for n in older["nodes"]:
                if n["type"] == "MiniMaxH3SigmaShift":
                    n["widgets_values"][1] = 4.0
                elif n["type"] == "KSamplerSelect":
                    n["widgets_values"][0] = "euler"
                elif n["type"] == "BasicScheduler":
                    n["widgets_values"][0] = "beta"
                elif n["type"] == "SpectrumApplyMiniMaxH3":
                    n["mode"] = 0
            older["extra"].pop(up.MARKER_KEY, None)
            older["extra"].get("dawasteh_h3_turbo_lora", {}).pop("sampling", None)
            self.assertNotEqual(older, wf, rel)
            self.assertEqual(up.apply(older, rel), wf, rel)

    def test_director_carries_the_vendor_sampling_values(self):
        """Der Music-Video-Director traegt dieselben drei Abweichungen in eigenen Widgets."""
        wf = load(up.DIRECTOR_WORKFLOW)
        director = next(n for n in wf["nodes"] if str(n["type"]).startswith("DaWH3MusicVideoDirector"))
        wv = director["widgets_values"]
        self.assertEqual(wv[up.DIRECTOR_SHIFT_AUDIO_INDEX], up.SHIFT_AUDIO_VENDOR)
        self.assertEqual(wv[up.DIRECTOR_SAMPLER_INDEX], up.SAMPLER_VENDOR)
        self.assertEqual(wv[up.DIRECTOR_SCHEDULER_INDEX], up.SCHEDULER_VENDOR)
        self.assertEqual(wv[31], 12.0, "shift_video bleibt unveraendert")
        self.assertEqual(wv[12], 8, "Schrittzahl bleibt unveraendert")
        older = json.loads(json.dumps(wf))
        ow = next(n for n in older["nodes"] if str(n["type"]).startswith("DaWH3MusicVideoDirector"))["widgets_values"]
        ow[up.DIRECTOR_SHIFT_AUDIO_INDEX] = 4.0
        ow[up.DIRECTOR_SAMPLER_INDEX] = "euler"
        ow[up.DIRECTOR_SCHEDULER_INDEX] = "beta"
        older["extra"].pop(up.MARKER_KEY, None)
        self.assertEqual(up.apply(older, up.DIRECTOR_WORKFLOW), wf)

    def test_non_target_workflows_are_returned_unchanged(self):
        rel = "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_Picture_and_Video_to_Video_LOCAL.json"
        self.assertIn(rel, up.targets())
        rel = "Prompt Enhancer/LLM_General-Prompt-Enhancer.json"
        self.assertNotIn(rel, up.targets())
        wf = load(rel)
        self.assertEqual(up.apply(wf, rel), wf)
        self.assertNotIn(up.MARKER_KEY, wf.get("extra", {}))


if __name__ == "__main__":
    unittest.main()
