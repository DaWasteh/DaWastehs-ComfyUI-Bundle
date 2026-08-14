from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control"
SPEC = importlib.util.spec_from_file_location("daw_adaptive_profiles", PACK / "adaptive_profiles.py")
profiles = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = profiles
SPEC.loader.exec_module(profiles)


class AdaptiveMediaProfileTests(unittest.TestCase):
    def test_native_wan_resolution_tracks_orientation_without_crop(self):
        landscape = profiles.target_dimensions(
            1920, 1080, "Wan 2.x / Animate 2 (480p)", "Model native (100%)"
        )
        portrait = profiles.target_dimensions(
            1080, 1920, "Wan 2.x / Animate 2 (480p)", "Model native (100%)"
        )
        self.assertEqual(landscape, (832, 464))
        self.assertEqual(portrait, (464, 832))
        self.assertAlmostEqual(landscape[0] / landscape[1], 16 / 9, delta=0.05)

    def test_square_input_uses_pixel_budget_and_model_alignment(self):
        width, height = profiles.target_dimensions(
            1000, 1000, "Wan 2.x / Animate 2 (480p)", "Model native (100%)"
        )
        self.assertEqual((width, height), (624, 624))
        self.assertEqual(width % 16, 0)
        self.assertEqual(height % 16, 0)

    def test_draft_preserves_aspect_and_only_reduces_resolution(self):
        native = profiles.target_dimensions(
            1920, 1080, "Wan 2.x / Animate 2 (480p)", "Model native (100%)"
        )
        draft = profiles.target_dimensions(
            1920, 1080, "Wan 2.x / Animate 2 (480p)", "Draft (50%)"
        )
        self.assertEqual(draft, (416, 240))
        self.assertLess(draft[0] * draft[1], native[0] * native[1])
        self.assertAlmostEqual(draft[0] / draft[1], 16 / 9, delta=0.05)

    def test_extreme_aspect_ratio_fails_instead_of_cropping_or_distorting(self):
        with self.assertRaisesRegex(ValueError, "cannot be represented"):
            profiles.target_dimensions(
                10000, 100, profiles.FALLBACK_PROFILE, "Model native (100%)"
            )

    def test_auto_resolution_uses_detection_or_documented_fallback(self):
        self.assertEqual(
            profiles.resolve_profile(profiles.AUTO_PROFILE, "LTX Video (768x512)"),
            ("LTX Video (768x512)", True),
        )
        self.assertEqual(
            profiles.resolve_profile(profiles.AUTO_PROFILE, "Not detected"),
            (profiles.FALLBACK_PROFILE, False),
        )
        self.assertEqual(
            profiles.resolve_profile("SD 1.5 (512)", "Wan 2.x / Animate 2 (480p)"),
            ("SD 1.5 (512)", False),
        )

    def test_pack_sources_parse_and_frontend_covers_both_nodes(self):
        for path in (PACK / "__init__.py", PACK / "nodes.py", PACK / "adaptive_nodes.py", PACK / "adaptive_profiles.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        frontend = (PACK / "web" / "adaptive_media.js").read_text(encoding="utf-8")
        self.assertIn('"DaWAdaptiveLoadImage"', frontend)
        self.assertIn('"DaWAdaptiveLoadVideo"', frontend)
        self.assertIn("onConnectionsChange", frontend)
        self.assertIn("graphToPrompt", frontend)
        self.assertIn("incomingSources", frontend)
        self.assertIn("adjacentNodes", frontend)
        self.assertIn("Ambiguous (select manually)", frontend)
        self.assertIn("crop=disabled", (PACK / "adaptive_nodes.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
