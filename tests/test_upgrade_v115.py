"""v1.1.5: optionale Zweige zentral abschaltbar (§6), Sekundenvorschau (§5)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import upgrade_v115 as up
from tools.integrate_duration_seconds import DURATION_KEY, SPECS, model_frame_count

WORKFLOWS = Path("workflows")


def load(rel: str) -> dict:
    return json.loads((WORKFLOWS / rel).read_text(encoding="utf-8"))


class UpgradeV115Tests(unittest.TestCase):
    def test_checked_in_collection_is_in_v115_form_and_idempotent(self):
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            wf = load(rel)
            self.assertEqual(up.apply(wf, rel), wf, rel)
            self.assertEqual(up.apply(up.apply(wf, rel), rel), wf, rel)

    def test_marker_is_present_exactly_on_the_targets(self):
        for path in sorted(WORKFLOWS.glob("*/*.json")):
            rel = path.relative_to(WORKFLOWS).as_posix()
            marker = load(rel).get("extra", {}).get(up.MARKER_KEY, {}).get("version")
            self.assertEqual(marker == up.MARKER_VERSION, rel in up.targets(), rel)

    # ---- §6: optionale Zweige -------------------------------------------------

    def test_no_shipped_placeholder_loader_is_active_and_connected(self):
        """Ein verbundener Loader mit fehlender Datei blockiert die Prompt-Validierung.

        Gemessen gegen ComfyUI 0.34.0: HTTP 400 "Invalid image file". Platzhalterdateien
        gibt es auf keiner Installation, also duerfen solche Loader nicht aktiv sein.
        """
        for rel in sorted(up.OPTIONAL_BRANCH_WORKFLOWS):
            wf = load(rel)
            branch_info = wf["extra"]["dawasteh_optional_branches"]
            if branch_info["mechanism"] == "none":
                # Zweig speist Pflichteingaenge; dokumentiert statt stummgeschaltet.
                self.assertTrue(branch_info["required_links"], rel)
                continue
            for node in up.placeholder_loaders(wf):
                self.assertEqual(node.get("mode"), up.MODE_MUTE,
                                 f"{rel}: Loader {node['id']} zeigt auf einen Platzhalter und ist aktiv")

    def test_muting_uses_mute_not_bypass(self):
        """Bypass reicht einen Knoten durch; ein Loader hat dafuer keinen Eingang."""
        for rel in sorted(up.OPTIONAL_BRANCH_WORKFLOWS):
            wf = load(rel)
            if wf["extra"]["dawasteh_optional_branches"]["mechanism"] != "mute":
                continue
            for node in wf["nodes"]:
                if node.get("mode") == 4 and node.get("type") in up.LOADER_TYPES:
                    self.fail(f"{rel}: Loader {node['id']} ist auf Bypass statt Mute")

    def test_every_muted_branch_only_feeds_optional_inputs(self):
        """Nachgeschaltete Knoten muessen einen gueltigen Ersatzpfad haben."""
        for rel in sorted(up.OPTIONAL_BRANCH_WORKFLOWS):
            wf = load(rel)
            info = wf["extra"]["dawasteh_optional_branches"]
            if info["mechanism"] != "mute":
                continue
            ok, problems = up._branch_is_optional(wf, set(info["muted_nodes"]))
            self.assertTrue(ok, f"{rel}: {problems}")

    def test_muted_branch_nodes_are_labelled_in_the_canvas(self):
        """Der Schalter muss im Canvas sichtbar sein, ohne das RODENT-Layout zu verletzen.

        Eigene Gruppen sind dort nicht moeglich (feste Stage-Titel, eine Gruppe je Knoten,
        ueberlappungsfrei), deshalb traegt jeder Knoten des Zweigs die Beschriftung.
        """
        for rel in sorted(up.OPTIONAL_BRANCH_WORKFLOWS):
            wf = load(rel)
            info = wf["extra"]["dawasteh_optional_branches"]
            if info["mechanism"] != "mute":
                continue
            self.assertTrue(info["branches"], rel)
            nodes = {int(n["id"]): n for n in wf["nodes"]}
            for label, ids in info["branches"].items():
                for nid in ids:
                    title = str(nodes[nid].get("title", ""))
                    self.assertTrue(title.startswith(up.BRANCH_GROUP_PREFIX), f"{rel}: {nid} {title!r}")
                    self.assertIn(label, title, rel)
                    self.assertIn("Strg+M", title, rel)
            self.assertEqual(sorted(n for ids in info["branches"].values() for n in ids),
                             info["muted_nodes"], rel)

    def test_active_loaders_do_not_reference_placeholders(self):
        """Der ausgelieferte Zustand muss ohne Zusatzdateien validierbar sein."""
        for rel in sorted(up.OPTIONAL_BRANCH_WORKFLOWS):
            wf = load(rel)
            if wf["extra"]["dawasteh_optional_branches"]["mechanism"] != "mute":
                continue
            active = [n for n in wf["nodes"]
                      if n.get("type") in up.LOADER_TYPES and n.get("mode", 0) == up.MODE_ACTIVE]
            for node in active:
                fn = up._filename(node) or ""
                self.assertFalse(up.PLACEHOLDER_RE.match(fn),
                                 f"{rel}: aktiver Loader {node['id']} auf Platzhalter {fn}")

    # ---- §5: Sekundenvorschau -------------------------------------------------

    def test_every_explicit_seconds_workflow_documents_requested_frames_and_actual(self):
        for rel, spec in SPECS.items():
            marker = load(rel)["extra"][DURATION_KEY]
            self.assertEqual(marker["minimum_frames"], spec.minimum, rel)
            self.assertIn("rounding", marker, rel)
            preview = marker["preview"]
            self.assertGreaterEqual(len(preview), 3, rel)
            for row in preview:
                self.assertEqual(set(row), {"requested_seconds", "frames", "actual_seconds"}, rel)
                frames = model_frame_count(row["requested_seconds"], spec)
                self.assertEqual(row["frames"], frames, rel)
                self.assertEqual(row["actual_seconds"], round((frames - 1) / spec.fps, 3), rel)
                self.assertEqual((row["frames"] - 1) % spec.alignment, 0, rel)
                self.assertGreaterEqual(row["frames"], spec.minimum, rel)

    def test_preview_covers_minimum_default_and_a_non_integer_duration(self):
        for rel, spec in SPECS.items():
            preview = load(rel)["extra"][DURATION_KEY]["preview"]
            requested = [row["requested_seconds"] for row in preview]
            self.assertEqual(preview[0]["frames"], spec.minimum, f"{rel}: erste Stuetzstelle ist das Minimum")
            self.assertIn(spec.default_seconds, requested, rel)
            self.assertTrue(any(abs(v - round(v)) > 1e-9 for v in requested),
                            f"{rel}: keine nicht ganzzahlige Stuetzstelle")

    def test_non_target_workflows_are_returned_unchanged(self):
        rel = "Reference to Video/MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json"
        self.assertNotIn(rel, up.targets())
        wf = load(rel)
        self.assertEqual(up.apply(wf, rel), wf)


if __name__ == "__main__":
    unittest.main()
