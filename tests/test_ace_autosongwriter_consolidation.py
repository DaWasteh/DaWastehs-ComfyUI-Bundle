from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.consolidate_ace_autosongwriters_v093 import (
    CUSTOM_NODE_TYPE,
    MIGRATION_KEY,
    PROFILE_LABELS,
    SOURCE_WORKFLOWS,
    TARGET_WORKFLOWS,
    consolidate_workflow,
    migrate_collection,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
NODE_DIR = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-AutoSongwriter"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profiles_module():
    path = NODE_DIR / "profiles.py"
    spec = importlib.util.spec_from_file_location("dawasteh_autosongwriter_profiles", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AutoSongwriterConsolidationTests(unittest.TestCase):
    def test_fourteen_sources_are_replaced_by_exactly_two_targets(self):
        self.assertEqual(len(SOURCE_WORKFLOWS), 14)
        self.assertEqual(len(TARGET_WORKFLOWS), 2)
        for key in SOURCE_WORKFLOWS:
            self.assertFalse((WORKFLOWS / Path(key)).exists(), key)

        expected = {target.path for target in TARGET_WORKFLOWS}
        actual = {
            path.relative_to(WORKFLOWS).as_posix()
            for path in (WORKFLOWS / "Music Generation").glob(
                "ACE-Step1_5_XL_SFT_*AutoSongwriter*.json"
            )
        }
        self.assertEqual(actual, expected)

    def test_both_targets_link_direction_bpm_and_key_from_one_selector(self):
        for target in TARGET_WORKFLOWS:
            with self.subTest(workflow=target.path):
                workflow = load(WORKFLOWS / Path(target.path))
                by_id = {node["id"]: node for node in workflow["nodes"]}
                selector = by_id[138]
                encoder = by_id[94]
                links = {link[0]: link for link in workflow["links"]}

                self.assertEqual(selector["type"], CUSTOM_NODE_TYPE)
                self.assertEqual(selector["widgets_values"], [PROFILE_LABELS[0], "", 120, "C major", "en"])
                self.assertEqual([output["name"] for output in selector["outputs"]], [
                    "music_direction", "bpm", "keyscale", "language", "filename_prefix",
                ])
                for input_name, output_slot, link_type in (
                    ("bpm", 1, "INT"),
                    ("keyscale", 2, "COMBO"),
                    ("language", 3, "COMBO"),
                ):
                    encoder_input = next(item for item in encoder["inputs"] if item["name"] == input_name)
                    link = links[encoder_input["link"]]
                    self.assertEqual(link[1:6], [138, output_slot, 94, encoder["inputs"].index(encoder_input), link_type])

                direction_link = links[selector["outputs"][0]["links"][0]]
                self.assertEqual(direction_link[1:5], [138, 0, 140, 1])
                filename_link = links[selector["outputs"][4]["links"][0]]
                save_audio = by_id[107]
                filename_slot = next(
                    index for index, item in enumerate(save_audio["inputs"])
                    if item["name"] == "filename_prefix"
                )
                self.assertEqual(filename_link[1:6], [138, 4, 107, filename_slot, "STRING"])
                self.assertEqual(workflow["extra"][MIGRATION_KEY]["source_workflows"], 7)
                self.assertTrue(workflow["extra"][MIGRATION_KEY]["custom_profile"])
                self.assertEqual(sum(node["type"] == "PixaromaRunTimer" for node in workflow["nodes"]), 1)
                self.assertEqual(sum(node["type"] == "DaWMultiGPUDeviceControl" for node in workflow["nodes"]), 1)

    def test_selector_has_six_curated_profiles_and_custom_mode(self):
        profiles = load_profiles_module()
        self.assertEqual(tuple(PROFILE_LABELS), profiles.PROFILE_OPTIONS)
        self.assertEqual(len(profiles.PROFILES), 6)
        self.assertEqual(len(profiles.PROFILE_OPTIONS), 7)

        expected = {
            "POP": (120, "C major"),
            "GLOW": (96, "G major"),
            "DRIVE": (108, "A minor"),
            "CLUB": (126, "F# minor"),
            "NIGHT": (84, "E minor"),
            "RUSH": (138, "D major"),
        }
        for profile in profiles.PROFILES:
            with self.subTest(profile=profile.code):
                prompt, bpm, keyscale, language, filename_prefix = profiles.resolve_profile(profile.label)
                self.assertEqual((bpm, keyscale), expected[profile.code])
                self.assertEqual(language, "en")
                self.assertEqual(filename_prefix, f"audio/ACE_Album/{profile.code}_Track")
                self.assertIn(f"PROFILE: {profile.code}", prompt)
                self.assertIn(profile.direction, prompt)

        prompt, bpm, keyscale, language, filename_prefix = profiles.resolve_profile(
            profiles.CUSTOM_PROFILE,
            "Progressive bluegrass with modular synth bass",
            111,
            "Bb minor",
            "de",
        )
        self.assertEqual((bpm, keyscale, language), (111, "Bb minor", "de"))
        self.assertEqual(filename_prefix, "audio/ACE_Album/CUSTOM_Track")
        self.assertIn("PROFILE: CUSTOM", prompt)
        self.assertIn("Progressive bluegrass", prompt)
        self.assertIn("111 BPM, Bb minor, 4/4", prompt)
        self.assertIn("LYRICS LANGUAGE: de", prompt)

    def test_custom_node_uses_current_comfy_extension_api(self):
        source = (NODE_DIR / "nodes.py").read_text(encoding="utf-8")
        self.assertIn('node_id="DaWAutoSongwriterGenreSelector"', source)
        self.assertIn('io.Combo.Input("profile"', source)
        self.assertIn('io.String.Input(\n                    "custom_genre_or_direction"', source)
        self.assertIn('io.Int.Output("bpm")', source)
        self.assertIn('io.Combo.Output("keyscale")', source)
        self.assertIn('io.Combo.Output("language")', source)
        self.assertIn('io.String.Output("filename_prefix")', source)
        self.assertNotIn("torch", source.lower())

    def test_checked_in_targets_rebuild_from_v092_sources(self):
        for target in TARGET_WORKFLOWS:
            with self.subTest(workflow=target.path):
                raw = subprocess.check_output(
                    ["git", "show", f"v0.9.2:workflows/{target.source}"],
                    text=True,
                    encoding="utf-8",
                )
                expected = consolidate_workflow(json.loads(raw), target)
                self.assertEqual(expected, load(WORKFLOWS / Path(target.path)))

    def test_checked_in_targets_are_migration_idempotent_and_integrity_guarded(self):
        for target in TARGET_WORKFLOWS:
            path = WORKFLOWS / Path(target.path)
            workflow = load(path)
            self.assertEqual(consolidate_workflow(workflow, target), workflow, target.path)
            corrupted = copy.deepcopy(workflow)
            corrupted["nodes"][0]["title"] = "corrupted after migration"
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                consolidate_workflow(corrupted, target)
        self.assertEqual(migrate_collection(WORKFLOWS, check=True), (2, 0, 0))


if __name__ == "__main__":
    unittest.main()
