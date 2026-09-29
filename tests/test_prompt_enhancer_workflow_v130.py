"""v1.3.0 workflow: image prompt enhancer (draft -> finished prompt with Qwen3.8 27B through llama.cpp)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_prompt_enhancer_v130 import DRAFT, MARKER, PATH, ROOT, SETTINGS, SOURCES, build_all
from tools.rodent_layout import _topology_hash
from tools.validate_workflows import validate_graph

REPORT = ROOT / "performance/rdna4/prompt-enhancer-v130-validation.json"
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-PromptEnhancer"


def helpers():
    spec = importlib.util.spec_from_file_location("pe_helpers_workflow_test", PACK / "helpers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nodes(workflow, kind):
    return [n for n in workflow["nodes"] if n["type"] == kind]


def one(workflow, kind):
    found = nodes(workflow, kind)
    assert len(found) == 1, (kind, len(found))
    return found[0]


def source(workflow, target, name):
    slot = next(i for i, s in enumerate(target["inputs"]) if s["name"] == name)
    link = next(item for item in workflow["links"] if item[3:5] == [target["id"], slot])
    return next(n for n in workflow["nodes"] if n["id"] == link[1]), link[2]


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = build_all()
        cls.w = cls.built[PATH]

    def test_rebuild_is_exact_and_lf_only(self):
        self.assertEqual(set(self.built), {PATH})
        self.assertEqual(build_all(), self.built)
        from tools import build_prompt_enhancer_v130 as builder
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "ROOT", Path(directory)):
            builder.main()
            data = (Path(directory) / "workflows" / PATH).read_bytes()
        self.assertNotIn(b"\r\n", data)
        self.assertEqual(data, (ROOT / "workflows" / PATH).read_bytes())

    def test_flat_valid_rodent_timer_and_one_gpu_control(self):
        errors = []
        validate_graph(Path(PATH), "root", self.w, errors)
        self.assertEqual(errors, [])
        self.assertFalse(self.w.get("definitions", {}).get("subgraphs"))
        self.assertEqual(self.w["extra"]["dawasteh_rodent_layout"]["topology_sha256"], _topology_hash(self.w))
        self.assertEqual(len(nodes(self.w, "PixaromaRunTimer")), 1)
        self.assertEqual(one(self.w, "DaWMultiGPUDeviceControl")["widgets_values"], ["gpu:0"] * 3)
        self.assertEqual(self.w["extra"][MARKER]["kind"], "image_prompt_enhancer")
        titles = [n["title"] for n in self.w["nodes"] if n["type"] == "MarkdownNote"]
        self.assertTrue(any(t.startswith("START HIER") for t in titles))

    def test_no_comfyui_model_is_loaded_the_writer_runs_in_llama_cpp(self):
        # the whole workflow is one LLM call: nothing may load a diffusion model or text encoder into ComfyUI's VRAM
        for kind in ("UNETLoader", "CLIPLoader", "VAELoader", "CheckpointLoaderSimple", "TextGenerate", "DaWVUReadOnlyCLIPLoader"):
            self.assertEqual(nodes(self.w, kind), [], kind)
        writer = one(self.w, "DaWImagePromptEnhancer")
        self.assertIn("Qwen3.8 27B", writer["title"])

    def test_wiring_and_defaults(self):
        writer = one(self.w, "DaWImagePromptEnhancer")
        # draft, target, detail, language, enhance, seed (+ control), temperature, max_tokens, notes
        self.assertEqual(writer["widgets_values"], [
            "", SETTINGS["target"], SETTINGS["detail"], SETTINGS["language"], SETTINGS["enhance"], SETTINGS["seed"],
            SETTINGS["seed_control"], SETTINGS["temperature"], SETTINGS["max_tokens"], ""])
        draft, slot = source(self.w, writer, "draft")
        self.assertEqual((draft["type"], slot), ("PixaromaPrompt", 0))
        self.assertEqual(draft["properties"]["promptState"]["text"], DRAFT)
        shown = {source(self.w, n, "source")[1]: n for n in nodes(self.w, "PixaromaShowText")}
        self.assertEqual(set(shown), {0, 1})   # prompt and info
        for n in shown.values():
            self.assertEqual(source(self.w, n, "source")[0], writer)
        self.assertTrue(shown[0]["title"].startswith("3 · FERTIGER PROMPT"))

    def test_optional_image_is_muted_and_only_feeds_an_optional_input(self):
        writer = one(self.w, "DaWImagePromptEnhancer")
        load = one(self.w, "PixaromaLoadImage")
        self.assertEqual(load["mode"], 2)   # muted: an optional image must not block prompt validation
        self.assertIn("optional", load["title"])
        self.assertEqual(source(self.w, writer, "image"), (load, 0))
        slot = next(s for s in writer["inputs"] if s["name"] == "image")
        self.assertEqual(slot["shape"], 7)   # litegraph optional input
        outgoing = [link for link in self.w["links"] if link[1] == load["id"]]
        self.assertEqual(len(outgoing), 1)

    def test_defaults_are_options_of_the_node_and_match_the_helpers(self):
        h = helpers()
        schema = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))["DaWImagePromptEnhancer"]["input"]
        for name, options in (("target", h.TARGETS), ("detail", h.DETAILS), ("language", h.LANGUAGES)):
            self.assertEqual(schema["required"][name][1]["options"], options, name)
            self.assertIn(SETTINGS[name], options)
        self.assertEqual((h.DEFAULT_TARGET, h.DEFAULT_DETAIL, h.DEFAULT_LANGUAGE),
                         (SETTINGS["target"], SETTINGS["detail"], SETTINGS["language"]))
        self.assertEqual(schema["required"]["seed"][1]["control_after_generate"], True)
        self.assertEqual([spec[1].get("default") for name, spec in schema["required"].items()
                          if name in ("temperature", "max_tokens", "enhance")], [True, 0.7, 1024])
        self.assertEqual(list(schema["optional"]), ["notes", "image"])

    def test_notes_name_the_model_targets_and_fallback(self):
        text = " ".join(n["widgets_values"][0] for n in nodes(self.w, "MarkdownNote"))
        for needle in ("Qwen3.8 27B", "Fließtext", "Text im Bild", "Tags", "Bearbeiten", "Strg+M", "start-MultiGPU.ps1",
                       "randomize", "Seed + 1000", "docs/PROMPT_ENHANCER_V130.md"):
            self.assertIn(needle, text)


class PackAndLauncherTests(unittest.TestCase):
    def test_pack_is_installed_by_the_updater_and_the_launcher_names_the_enhancer(self):
        updater = (ROOT / "tools" / "update-comfyui-rdna4.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('"ComfyUI-DaWasteh-PromptEnhancer"', updater)
        script = (ROOT / "tools" / "start-MultiGPU.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("image prompt enhancer", script)
        self.assertIn("Launcher v1.3.0", script)
        self.assertIn('$PromptLlmGguf = Join-Path $ComfyPath "models\\LLM\\Qwen3.8\\Qwen3.8-27B-IQ4_XS-3.84bpw.gguf"', script)

    def test_the_h3_backend_the_node_loads_exists_and_is_installed_too(self):
        self.assertTrue((ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo" / "llm_backend.py").is_file())
        updater = (ROOT / "tools" / "update-comfyui-rdna4.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('"ComfyUI-DaWasteh-H3-MusicVideo"', updater)


@unittest.skipUnless(REPORT.is_file(), "live evidence is written by the v1.3.0 GPU run")
class LiveEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.runs = {run["case"]: run for run in cls.report["runs"]}

    def test_report_matches_the_shipped_file_and_every_run_succeeded(self):
        self.assertEqual(self.report["workflows"][PATH]["sha256"], hashlib.sha256((ROOT / "workflows" / PATH).read_bytes()).hexdigest())
        self.assertTrue(any(run.get("final") for run in self.report["runs"]))
        for run in self.report["runs"]:
            self.assertEqual(run["status"], run.get("expected_status", "success"), run["case"])
            self.assertEqual(run.get("node_errors"), {}, run["case"])

    def test_the_shipped_default_writes_an_english_paragraph_from_the_german_draft(self):
        run = self.runs["default_german_draft_natural"]
        self.assertIn("Qwen3.8-27B", run["info"])
        self.assertNotIn("ACHTUNG", run["info"])
        self.assertGreaterEqual(run["check"]["words"], 90)
        self.assertNotIn("\n", run["prompt"])
        self.assertIn("lighthouse", run["prompt"].lower())
        self.assertTrue(run["memory"]["llama_server_seen"])

    def test_targets_follow_their_format(self):
        poster = self.runs["text_in_image_poster"]["prompt"]
        for text in ('"BLUE NOTE NIGHTS"', '"14. August · Stadtpark · Eintritt frei"'):
            self.assertIn(text, poster)   # texts for the image are copied exactly
        tags = self.runs["tags_long"]
        self.assertGreaterEqual(tags["check"]["tags"], 24)
        self.assertEqual(tags["prompt"], tags["prompt"].lower().replace("  ", " "))
        self.assertNotIn(". ", tags["prompt"])
        edit = self.runs["edit_with_image"]["prompt"]
        self.assertIn("hat", edit.lower())
        self.assertIn("Keep", edit)

    def test_enhancer_off_and_unusable_answers_hand_the_draft_on_unchanged(self):
        off = self.runs["enhance_off_passthrough"]
        self.assertEqual(off["prompt"], off["draft"])
        self.assertFalse(off["memory"]["llama_server_seen"])   # the GGUF is not started at all
        self.assertIn("Enhancer aus", off["info"])
        cut = self.runs["truncated_answer_falls_back"]
        self.assertEqual(cut["prompt"], cut["draft"])
        self.assertIn("keine brauchbare Antwort", cut["info"])

    def test_the_writer_saw_the_reference_image_and_the_seed_changes_the_text(self):
        self.assertIn("broccoli", self.runs["reference_image_natural"]["prompt"].lower())
        self.assertNotEqual(self.runs["seed_variation"]["prompt"], self.runs["default_german_draft_natural"]["prompt"])

    def test_language_and_notes(self):
        self.assertNotRegex(self.runs["german_output_short"]["prompt"], r"\b(the|with|and)\b")
        market = self.runs["notes_no_people"]["prompt"].lower()
        self.assertNotRegex(market, r"\b(people|person|man|woman|crowd|vendor|shopper|tourist)s?\b")

    def test_without_a_gguf_the_error_says_what_is_missing_and_enhance_off_still_works(self):
        error = self.runs["no_gguf_in_start_profile_clear_error"]
        self.assertEqual(error["status"], "error")
        for needle in ("Qwen3.8 27B ist nicht eingerichtet", "DAWASTEH_PROMPT_LLM_GGUF", "DAWASTEH_LLAMA_SERVER", "start-MultiGPU.bat"):
            self.assertIn(needle, error["error"])
        self.assertFalse(error["memory"]["llama_server_seen"])
        off = self.runs["enhance_off_without_gguf"]
        self.assertEqual((off["status"], off["prompt"]), ("success", off["draft"]))

    def test_llama_server_memory_fits_the_rx_9070_xt(self):
        for run in self.report["runs"]:
            memory = run["memory"]
            if memory["llama_server_seen"]:
                self.assertLess(memory["peak_llama_dedicated_gib"], 15.5, run["case"])
            self.assertLess(memory["peak_commit_gib"], memory["peak_commit_limit_gib"] - 5, run["case"])


if __name__ == "__main__":
    unittest.main()
