"""v1.3.0 DaWasteh Prompt Enhancer pack: prompt assembly, answer cleaning/checks and the retry logic (pure helpers, no ComfyUI import)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-PromptEnhancer"
BACKEND_PATH = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo" / "llm_backend.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


h = _load("pe_helpers_v130_test", PACK / "helpers.py")

LONG = ("A weathered lighthouse stands on a black rock while a storm breaks over the sea, waves exploding into white spray at its "
        "base and gulls tumbling in the wind. Low, heavy clouds part for one shaft of cold light that hits the tower's chipped white "
        "and red paint. Shot from a low angle with a 35 mm lens, the horizon tilted slightly, in a moody cinematic photograph "
        "with desaturated blues and a warm glow from the lantern room.")
TAGS = ("masterpiece, best quality, highly detailed, 1girl, solo, silver hair, long hair, school uniform, pleated skirt, "
        "cherry blossoms, petals, spring, outdoors, park, soft sunlight, depth of field, from side, anime style")

# stands in for llama-server.exe like in test_h3_music_video_v125: `python -m fake_llama_server <llama-server args>`
FAKE_SERVER = textwrap.dedent('''
    import json, os, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1])
    record = os.environ["FAKE_RECORD"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, payload):
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send({"status": "ok"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with open(record, "a", encoding="utf-8") as f:
                f.write(json.dumps(body) + "\\n")
            answers = json.loads(os.environ["FAKE_ANSWERS"])
            count = sum(1 for _ in open(record, encoding="utf-8"))
            self._send({"choices": [{"message": {"content": answers[min(count, len(answers)) - 1]}}]})

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
''')


class SystemPromptTests(unittest.TestCase):
    def test_every_combination_has_rules_target_length_and_language(self):
        for target in h.TARGETS:
            for detail in h.DETAILS:
                for language in h.LANGUAGES:
                    text = h.system_prompt(target, detail, language)
                    self.assertIn(h.COMMON_RULES, text)
                    self.assertIn(h.TARGET_RULES[target], text)
                    self.assertIn(f"Length: {h.LENGTH_RULES[target][detail]}. Stay inside that range.", text)
                    self.assertTrue(text.startswith("You are the prompt writer"))

    def test_language_rule_follows_the_choice_and_tags_stay_english(self):
        self.assertIn("in English", h.system_prompt(h.TARGET_NATURAL, "mittel", "English"))
        self.assertIn("in German", h.system_prompt(h.TARGET_NATURAL, "mittel", "Deutsch"))
        self.assertIn("language of the draft", h.system_prompt(h.TARGET_TEXT, "mittel", "wie der Entwurf"))
        for language in h.LANGUAGES:
            tags = h.system_prompt(h.TARGET_TAGS, "mittel", language)
            self.assertIn(h.TAGS_LANGUAGE, tags)
            self.assertNotIn("Write the prompt in", tags)

    def test_unknown_options_are_rejected(self):
        for args in (("x", "mittel", "English"), (h.TARGET_NATURAL, "x", "English"), (h.TARGET_NATURAL, "mittel", "x")):
            with self.assertRaises(ValueError):
                h.system_prompt(*args)

    def test_the_writer_is_not_told_to_override_its_own_refusals(self):
        # refusals are handled by the fallback (the draft goes on unchanged), never by an instruction to ignore them
        for text in (h.COMMON_RULES, *h.TARGET_RULES.values()):
            self.assertNotRegex(text.lower(), r"never refuse|do not refuse|ignore (any|all|your) (rules|guidelines)")

    def test_exclusions_are_described_not_named(self):
        # "no people" came back as "entirely empty of people" (v1.3.0 run); naming it invites the image model to draw it
        for target in (h.TARGET_NATURAL, h.TARGET_TEXT):
            self.assertIn("do not name it", h.TARGET_RULES[target])
        self.assertIn("a deserted street", h.TARGET_RULES[h.TARGET_NATURAL])
        # Danbooru has a real "no humans" tag, so the tag target keeps its own rule (no negatives) without this one
        self.assertNotIn("do not name it", h.TARGET_RULES[h.TARGET_TAGS])

    def test_min_sizes_cover_every_level_and_grow_with_the_detail(self):
        for target in h.TARGETS:
            sizes = [h.MIN_SIZE[target][d] for d in h.DETAILS]
            self.assertEqual(sizes, sorted(sizes))
            self.assertEqual(set(h.MIN_SIZE[target]), set(h.DETAILS))
            self.assertEqual(set(h.LENGTH_RULES[target]), set(h.DETAILS))


class UserMessageTests(unittest.TestCase):
    def test_draft_is_required(self):
        for empty in ("", "   \n", None):
            with self.assertRaises(ValueError):
                h.user_message(empty)

    def test_notes_and_image_hints(self):
        plain = h.user_message("  a fox  ")
        self.assertEqual(plain, "Draft:\na fox\n\nWrite the finished prompt now.")
        with_notes = h.user_message("a fox", notes="35 mm film look")
        self.assertIn("Additional notes from the user (follow them):\n35 mm film look", with_notes)
        reference = h.user_message("the same fox in winter", has_image=True)
        self.assertIn("reference image is attached", reference)
        edit = h.user_message("make the sweater red", has_image=True, target=h.TARGET_EDIT)
        self.assertIn("input image of the edit is attached", edit)
        self.assertNotIn("reference image", edit)
        self.assertTrue(edit.endswith("Write the finished prompt now."))


class CleanAnswerTests(unittest.TestCase):
    def test_strips_labels_fences_thinking_and_wrapping_quotes(self):
        self.assertEqual(h.clean_answer("Prompt: A red fox."), "A red fox.")
        self.assertEqual(h.clean_answer("**Final prompt:** A red fox."), "A red fox.")
        self.assertEqual(h.clean_answer("Here is the prompt:\n\nA red fox in snow."), "A red fox in snow.")
        self.assertEqual(h.clean_answer("```\nA red fox.\n```"), "A red fox.")
        self.assertEqual(h.clean_answer("<think>hmm</think>\nA red fox."), "A red fox.")
        self.assertEqual(h.clean_answer('"A red fox in snow."'), "A red fox in snow.")
        self.assertEqual(h.clean_answer("“A red fox in snow.”"), "A red fox in snow.")

    def test_keeps_quotes_inside_and_texts_meant_for_the_image(self):
        text = 'A sign reads "OPEN" in red neon above a door that says "PUSH".'
        self.assertEqual(h.clean_answer(text), text)
        wrapped_with_inner = '"A sign reads "OPEN" in neon."'
        self.assertEqual(h.clean_answer(wrapped_with_inner), wrapped_with_inner)   # ambiguous: left alone

    def test_one_paragraph_without_bullets_or_emphasis(self):
        answer = "A fox sits in the snow.\n\nIts fur is **bright red**.\n- warm light\n- soft shadows"
        self.assertEqual(h.clean_answer(answer), "A fox sits in the snow. Its fur is bright red. warm light soft shadows")
        self.assertEqual(h.clean_answer(""), "")
        self.assertEqual(h.clean_answer(None), "")

    def test_tags_are_normalised_and_deduplicated(self):
        answer = "Tags: masterpiece, best quality, 1girl,\nsolo, Solo, silver hair.; cherry blossoms."
        self.assertEqual(h.clean_answer(answer, h.TARGET_TAGS), "masterpiece, best quality, 1girl, solo, silver hair, cherry blossoms")


class UsableTests(unittest.TestCase):
    def test_complete_answers_pass(self):
        self.assertTrue(h.usable(LONG, h.TARGET_NATURAL, "mittel"))
        self.assertTrue(h.usable(TAGS, h.TARGET_TAGS, "mittel"))
        self.assertTrue(h.usable("Change the sweater to red wool. Keep the face and background exactly as they are.", h.TARGET_EDIT, "mittel"))

    def test_short_cut_off_and_refused_answers_fail(self):
        self.assertFalse(h.usable("", h.TARGET_NATURAL, "kurz"))
        self.assertFalse(h.usable("A fox.", h.TARGET_NATURAL, "mittel"))                               # the early "SH" stop
        self.assertFalse(h.usable(LONG[:-40], h.TARGET_NATURAL, "mittel"))                            # cut in mid-sentence
        self.assertFalse(h.usable("I'm sorry, but I can't help with that request. " * 5, h.TARGET_NATURAL, "kurz"))
        self.assertFalse(h.usable("I cannot write this prompt.", h.TARGET_EDIT, "kurz"))
        self.assertFalse(h.usable("masterpiece, 1girl", h.TARGET_TAGS, "mittel"))

    def test_the_bar_rises_with_the_detail(self):
        self.assertTrue(h.usable(LONG, h.TARGET_NATURAL, "kurz"))
        self.assertFalse(h.usable(LONG, h.TARGET_NATURAL, "ausführlich"))   # 76 words < 90

    def test_ends_with_a_quote_or_bracket_count_as_finished(self):
        text = ("A flat vector poster on a dark blue night sky with a saxophonist in silhouette, a warm gold glow behind him and a "
                "row of small stars above, the big title across the top in tall gold letters reading \"BLUE NOTE NIGHTS\"")
        self.assertGreaterEqual(len(text.split()), h.MIN_SIZE[h.TARGET_TEXT]["kurz"])
        self.assertTrue(h.usable(text, h.TARGET_TEXT, "kurz"))
        self.assertFalse(h.usable(text[:-1], h.TARGET_TEXT, "kurz"))   # quote missing: cut off inside the lettering


class RetryTests(unittest.TestCase):
    def test_retry_with_seed_plus_1000(self):
        seeds = []

        def generate(seed):
            seeds.append(seed)
            return "A fox." if seed == 7 else LONG

        answer, rejected = h.first_usable(generate, h.TARGET_NATURAL, "mittel", 7)
        self.assertEqual((answer, rejected, seeds), (LONG, ["A fox."], [7, 1007]))

    def test_no_second_call_when_the_first_answer_is_fine_and_none_when_both_fail(self):
        seeds = []
        answer, rejected = h.first_usable(lambda s: seeds.append(s) or LONG, h.TARGET_NATURAL, "mittel", 3)
        self.assertEqual((answer, rejected, seeds), (LONG, [], [3]))
        answer, rejected = h.first_usable(lambda s: "no", h.TARGET_NATURAL, "mittel", 0)
        self.assertEqual((answer, rejected), (None, ["no", "no"]))


class EnhanceTests(unittest.TestCase):
    def run_enhance(self, answers, enhance=True, target=h.TARGET_NATURAL, detail="mittel", **kw):
        calls = []

        def generate(system, user, seed):
            calls.append((system, user, seed))
            return answers[min(len(calls), len(answers)) - 1]

        result = h.enhance_prompt("  ein Fuchs im Schnee  ", target, detail, "English", kw.pop("notes", ""), enhance, kw.pop("seed", 5),
                                  generate, **kw)
        return result, calls

    def test_enhanced_prompt_and_what_the_model_receives(self):
        (prompt, source, rejected), calls = self.run_enhance([LONG], notes="warm colours")
        self.assertEqual((prompt, source, rejected), (LONG, "llm", []))
        system, user, seed = calls[0]
        self.assertEqual(system, h.system_prompt(h.TARGET_NATURAL, "mittel", "English"))
        self.assertIn("Draft:\nein Fuchs im Schnee", user)
        self.assertIn("warm colours", user)
        self.assertEqual(seed, 5)

    def test_enhancer_off_never_calls_the_model(self):
        (prompt, source, _), calls = self.run_enhance([LONG], enhance=False)
        self.assertEqual((prompt, source, calls), ("ein Fuchs im Schnee", "draft", []))

    def test_unusable_answers_leave_the_draft_unchanged(self):
        (prompt, source, rejected), calls = self.run_enhance(["I'm sorry, but I can't do that."])
        self.assertEqual((prompt, source, len(rejected), len(calls)), ("ein Fuchs im Schnee", "draft: answer unusable", 2, 2))
        (prompt, source, _), calls = self.run_enhance(["A fox.", LONG])
        self.assertEqual((prompt, source, [c[2] for c in calls]), (LONG, "llm", [5, 1005]))

    def test_empty_draft_and_bad_options_raise_even_with_the_enhancer_off(self):
        with self.assertRaises(ValueError):
            h.enhance_prompt("  ", h.TARGET_NATURAL, "mittel", "English", "", False, 0, lambda *a: "")
        with self.assertRaises(ValueError):
            h.enhance_prompt("fox", "x", "mittel", "English", "", False, 0, lambda *a: "")

    def test_info_line(self):
        model = "Qwen3.8-27B-IQ4_XS-3.84bpw.gguf"
        self.assertEqual(h.info_line(model, h.TARGET_NATURAL, "mittel", "llm", LONG, 31.4),
                         f"{model} · Fließtext · mittel · {len(LONG.split())} Wörter · 31 s")
        self.assertIn("Tags", h.info_line(model, h.TARGET_TAGS, "kurz", "llm", TAGS, 5))
        self.assertIn("ACHTUNG", h.info_line("Qwen3.5-4B.gguf", h.TARGET_NATURAL, "mittel", "llm", LONG, 5))
        self.assertIn("Enhancer aus", h.info_line("-", h.TARGET_NATURAL, "mittel", "draft", "x", 0))
        self.assertIn("keine brauchbare Antwort", h.info_line(model, h.TARGET_NATURAL, "mittel", "draft: answer unusable", "x", 9))
        for name in ("Qwen3.8-27B-IQ4_XS-3.84bpw.gguf", "Qwen3.8_27B-Ridge-3.7bpw.gguf", "qwen3.8-27b-ud-q4_k_xl.gguf"):
            self.assertTrue(h.looks_like_qwen38_27b(name), name)
        for name in ("Qwen3.5-4B.gguf", "Qwen3.8-Flash-Next-UD-Q2_K_XL.gguf", "", "gemma-4-e4b.gguf"):
            self.assertFalse(h.looks_like_qwen38_27b(name), name)


class RealBackendTests(unittest.TestCase):
    """The helpers against llm_backend.LlamaServer with a fake llama-server: request shape, image, retry, stop."""

    def setUp(self):
        self.backend = _load("pe_backend_v130_test", BACKEND_PATH)
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        (folder / "fake_llama_server.py").write_text(FAKE_SERVER, encoding="utf-8")
        self.record = folder / "record.jsonl"
        self.answers = [LONG]
        self.env = mock.patch.dict(os.environ, {
            self.backend.ENV_SERVER: sys.executable, "FAKE_RECORD": str(self.record),
            "PYTHONPATH": str(folder) + os.pathsep + os.environ.get("PYTHONPATH", "")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def bodies(self):
        return [json.loads(line) for line in self.record.read_text(encoding="utf-8").splitlines()]

    def run_enhance(self, answers, **kw):
        os.environ["FAKE_ANSWERS"] = json.dumps(answers)
        with self.backend.LlamaServer("fake_llama_server", log_dir=self.tmp.name) as server:
            process = server.process
            result = h.enhance_prompt(
                kw.pop("draft", "ein Fuchs im Schnee"), kw.pop("target", h.TARGET_NATURAL), "mittel", "English", "", True, 3,
                lambda system, user, seed: server.generate(user, image=kw.get("image"), max_length=1024, temperature=0.7, seed=seed,
                                                           system_prompt=system), has_image=kw.get("image") is not None)
        self.assertIsNotNone(process.poll())   # the server stopped with the context
        return result

    def test_system_and_user_message_reach_the_server_and_the_answer_is_used(self):
        prompt, source, _ = self.run_enhance([f"Prompt: {LONG}"])
        self.assertEqual((prompt, source), (LONG, "llm"))
        (body,) = self.bodies()
        self.assertEqual(body["messages"][0], {"role": "system", "content": h.system_prompt(h.TARGET_NATURAL, "mittel", "English")})
        self.assertIn("Draft:\nein Fuchs im Schnee", body["messages"][1]["content"])
        self.assertEqual((body["seed"], body["max_tokens"]), (3, 1024))
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})

    def test_a_cut_short_answer_is_retried_with_another_seed_on_the_same_server(self):
        prompt, source, rejected = self.run_enhance(["A fox", LONG])
        self.assertEqual((prompt, source, rejected), (LONG, "llm", ["A fox"]))
        self.assertEqual([b["seed"] for b in self.bodies()], [3, 1003])

    def test_image_goes_to_the_model_as_a_jpeg_data_url(self):
        try:
            import torch
        except ImportError:
            self.skipTest("torch is needed for the image encoding of llm_backend")
        self.run_enhance([LONG], image=torch.rand(1, 32, 24, 3))
        content = self.bodies()[0]["messages"][1]["content"]
        self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertIn("reference image is attached", content[1]["text"])


class PackFilesTests(unittest.TestCase):
    def test_node_uses_the_helpers_and_the_h3_backend(self):
        source = (PACK / "nodes.py").read_text(encoding="utf-8")
        for needle in ('node_id="DaWImagePromptEnhancer"', "helpers.TARGETS", "helpers.DETAILS", "helpers.LANGUAGES",
                       "ComfyUI-DaWasteh-H3-MusicVideo", "llm_backend.py", "backend.LlamaServer(gguf).start()",
                       "session[\"server\"].stop()", "control_after_generate=True"):
            self.assertIn(needle, source)
        self.assertIn("comfy_entrypoint", (PACK / "__init__.py").read_text(encoding="utf-8"))
        self.assertTrue((PACK / "README.md").is_file())
        self.assertTrue(BACKEND_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
