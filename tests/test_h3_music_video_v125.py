"""v1.2.5 music-video prompt writer: GGUF models through llama.cpp (llm_backend.py), section directions, start profile."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import torch

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mv2 = _load("dawasteh_mv2_v125_test", PACK / "mv2.py")
backend = _load("dawasteh_llm_backend_v125_test", PACK / "llm_backend.py")

OUTRO_IDEA = """Adults-only art-house video. She is alone at night in her villa:
Verse 1 - her streaming room: RGB gaming PC, the stream has just ended; full outfit.
Chorus - she wanders barefoot through the dark villa, phone in hand; her jacket slides off.
Bridge - the villa lounge at midnight: calls from her management, black lace lingerie.
Guitar solo - she dances alone on the moonlit marble floor.
Verse 2 - in front of a gold-framed mirror she writes his name with red lipstick.
Outro - her bedroom: candlelight, silk sheets."""

# stands in for llama-server.exe: `python -m <module> <llama-server args>`; LlamaServer passes the model path right
# after the executable as "-m <model>", so a module name as "model" turns the call into a normal python -m run
FAKE_SERVER = textwrap.dedent('''
    import json, os, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer
    args = sys.argv[1:]
    if os.environ.get("FAKE_NO_MTP") == "1" and "--spec-type" in args:
        sys.exit(3)   # a build without MTP support refuses the flag
    port = int(args[args.index("--port") + 1])
    record = os.environ["FAKE_RECORD"]
    with open(record, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": args}) + "\\n")

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
                f.write(json.dumps({"body": body}) + "\\n")
            self._send({"choices": [{"message": {"content": "<think>x</think>SHOT 1: The singer turns to the window."}}]})

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
''')


class ResolveTests(unittest.TestCase):
    def test_auto_uses_the_start_profile_gguf_or_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "Qwen3.8-27B-Ridge-3.7bpw.gguf"
            model.write_bytes(b"GGUF")
            with mock.patch.dict(os.environ, {backend.ENV_MODEL: ""}):
                self.assertEqual(backend.resolve(backend.AUTO, "Qwen\\qwen3.5_4b_bf16.safetensors"),
                                 ("comfy", "Qwen\\qwen3.5_4b_bf16.safetensors"))
                self.assertIsNone(backend.gguf_option())
            with mock.patch.dict(os.environ, {backend.ENV_MODEL: f'"{model}"'}):
                self.assertEqual(backend.resolve(backend.AUTO, "fallback"), ("gguf", str(model)))
                self.assertEqual(backend.gguf_option(), "gguf: Qwen3.8-27B-Ridge-3.7bpw.gguf")
                self.assertEqual(backend.resolve("gguf: Qwen3.8-27B-Ridge-3.7bpw.gguf", "fallback"), ("gguf", str(model)))
                with self.assertRaises(FileNotFoundError):
                    backend.resolve("gguf: other.gguf", "fallback")
                # a saved workflow that names a text encoder keeps using it
                self.assertEqual(backend.resolve("Qwen\\qwen3.5_9b.safetensors", "fallback"), ("comfy", "Qwen\\qwen3.5_9b.safetensors"))

    def test_mmproj_follows_quant_tag_and_model_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in ("mmproj-Qwen3.8-27B-BF16.gguf", "mmproj-Qwen3.8-27B-IQ4_XS-3.84bpw-bf16.gguf",
                         "mmproj-Qwen3.8-27B-Ridge-BF16.gguf", "mmproj-Qwen3.8-Flash-Next-BF16.gguf"):
                (folder / name).write_bytes(b"GGUF")
            pick = lambda model: Path(backend.find_mmproj(str(folder / model))).name
            self.assertEqual(pick("Qwen3.8-27B-Ridge-3.7bpw.gguf"), "mmproj-Qwen3.8-27B-Ridge-BF16.gguf")
            self.assertEqual(pick("Qwen3.8-27B-IQ4_XS-3.84bpw.gguf"), "mmproj-Qwen3.8-27B-IQ4_XS-3.84bpw-bf16.gguf")
            self.assertEqual(pick("Qwen3.8-27B-UD-Q4_K_XL.gguf"), "mmproj-Qwen3.8-27B-BF16.gguf")
            self.assertEqual(pick("Qwen3.8-Flash-Next-UD-Q2_K_XL-00001-of-00003.gguf"), "mmproj-Qwen3.8-Flash-Next-BF16.gguf")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(backend.find_mmproj(str(Path(tmp) / "model.gguf")))

    def test_device_index_follows_the_visible_hip_list(self):
        with mock.patch.dict(os.environ, {"HIP_VISIBLE_DEVICES": "0,1"}):
            self.assertEqual(backend.comfy_device_index("1"), 1)
        with mock.patch.dict(os.environ, {"HIP_VISIBLE_DEVICES": "1"}):
            self.assertEqual(backend.comfy_device_index("1"), 0)
            self.assertIsNone(backend.comfy_device_index("0"))   # not visible to ComfyUI: nothing to unload
        with mock.patch.dict(os.environ, {"HIP_VISIBLE_DEVICES": ""}):
            self.assertEqual(backend.comfy_device_index("1"), 1)

    def test_server_arguments_use_the_built_in_mtp_head_and_fit_the_9070xt(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "Qwen3.8-27B-Ridge-3.7bpw.gguf"
            (Path(tmp) / "mmproj-Qwen3.8-27B-Ridge-BF16.gguf").write_bytes(b"GGUF")
            with mock.patch.dict(os.environ, {backend.ENV_CTX: "", backend.ENV_MMPROJ_GPU: ""}):
                server = backend.LlamaServer(str(model))
            server.port = 1234
            args = server._args(mtp=True)
            self.assertEqual(args[args.index("--spec-type") + 1], "draft-mtp")
            for draft_model_flag in ("-md", "--model-draft", "--spec-draft-model"):
                self.assertNotIn(draft_model_flag, args)   # no DFlash drafter, only the model's own head
            self.assertEqual(args[args.index("-c") + 1], "8192")
            self.assertIn("--no-mmproj-offload", args)     # measured: 16k + projector on the GPU spilled 2.3 GiB
            self.assertEqual(args[args.index("--reasoning") + 1], "off")
            self.assertEqual(server.device, "1")
            self.assertNotIn("--spec-type", server._args(mtp=False))
            with mock.patch.dict(os.environ, {backend.ENV_MMPROJ_GPU: "1"}):
                gpu = backend.LlamaServer(str(model))
            gpu.port = 1234
            self.assertNotIn("--no-mmproj-offload", gpu._args(mtp=True))


class FakeServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        (folder / "fake_llama_server.py").write_text(FAKE_SERVER, encoding="utf-8")
        self.record = folder / "record.jsonl"
        self.env = mock.patch.dict(os.environ, {
            backend.ENV_SERVER: sys.executable, "FAKE_RECORD": str(self.record),
            "PYTHONPATH": str(folder) + os.pathsep + os.environ.get("PYTHONPATH", "")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def entries(self, key):
        return [json.loads(line)[key] for line in self.record.read_text(encoding="utf-8").splitlines() if key in json.loads(line)]

    def test_chat_request_image_and_stop(self):
        server = backend.LlamaServer("fake_llama_server", log_dir=self.tmp.name)
        with server:
            process = server.process
            image = torch.rand(1, 64, 48, 4)
            text = server.generate("Describe", image=image, max_length=50, temperature=0.3, seed=11, system_prompt="SYS")
            self.assertEqual(text, "SHOT 1: The singer turns to the window.")   # thinking block stripped
        self.assertIsNotNone(process.poll())                                     # server stopped on exit
        body = self.entries("body")[0]
        self.assertEqual(body["messages"][0], {"role": "system", "content": "SYS"})
        content = body["messages"][1]["content"]
        self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(content[1], {"type": "text", "text": "Describe"})
        self.assertEqual((body["max_tokens"], body["seed"], body["temperature"]), (50, 11, 0.3))
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertIn("--spec-type", self.entries("argv")[0])

    def test_start_retries_without_mtp(self):
        with mock.patch.dict(os.environ, {"FAKE_NO_MTP": "1"}):
            with backend.LlamaServer("fake_llama_server", log_dir=self.tmp.name) as server:
                self.assertEqual(server.generate("x", max_length=10), "SHOT 1: The singer turns to the window.")
        self.assertNotIn("--spec-type", self.entries("argv")[0])

    @unittest.skipUnless(os.name == "nt", "job objects are Windows-only")
    def test_server_dies_with_a_crashed_comfyui(self):
        import subprocess
        import psutil
        crash = textwrap.dedent(f'''
            import importlib.util, os, sys
            spec = importlib.util.spec_from_file_location("llm_backend", {str(PACK / "llm_backend.py")!r})
            backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
            server = backend.LlamaServer("fake_llama_server", log_dir={self.tmp.name!r}).start()
            print(server.process.pid, flush=True)
            os._exit(1)   # no stop(), no __exit__: like a killed ComfyUI
        ''')
        out = subprocess.run([sys.executable, "-c", crash], capture_output=True, text=True, timeout=120)
        pid = int(out.stdout.split()[0])
        try:
            psutil.Process(pid).wait(timeout=20)
        except psutil.NoSuchProcess:
            pass
        self.assertFalse(psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE)

    def test_missing_binary_raises_a_clear_error(self):
        with mock.patch.dict(os.environ, {backend.ENV_SERVER: str(Path(self.tmp.name) / "missing.exe")}):
            with self.assertRaisesRegex(FileNotFoundError, backend.ENV_SERVER):
                backend.LlamaServer("fake_llama_server").start()


class WriterTests(unittest.TestCase):
    def test_llm_dispatch_sends_llama_server_calls_to_generate(self):
        source = (PACK / "nodes_v2.py").read_text(encoding="utf-8")
        keep = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_llm"]
        namespace: dict = {}
        exec(compile(ast.Module(body=keep, type_ignores=[]), "nodes_v2.py", "exec"), namespace)
        calls = []

        class Server:
            is_llama_server = True

            def generate(self, prompt, **kw):
                calls.append((prompt, kw))
                return "ok"

        self.assertEqual(namespace["_llm"](Server(), "p", max_length=9, seed=3, system_prompt="s"), "ok")
        self.assertEqual(calls, [("p", {"image": None, "max_length": 9, "temperature": 0.7, "seed": 3, "system_prompt": "s"})])

    def test_writer_keys_fallback_retry_and_cleanup(self):
        source = (PACK / "nodes_v2.py").read_text(encoding="utf-8")
        self.assertIn("from . import llm_backend, mv2", source)
        self.assertIn('io.Combo.Input("llm", options=_llm_options(), default=llm_backend.AUTO', source)
        # the key names the model that writes; Qwen3.5 keys keep their v1.2.4 form
        self.assertIn("llm_backend.GGUF_PREFIX + Path(name).name if kind == \"gguf\" else name", source)
        self.assertIn("_free_comfy_models_on(server.device)", source)
        self.assertIn("except (OSError, RuntimeError) as exc:", source)
        self.assertIn("server.stop()", source)
        self.assertIn("1000 * attempt", source)
        self.assertIn('manifest["prompt_llm"] = llm_name if use_llm else "template"', source)
        self.assertEqual(mv2.PROMPT_VERSION, 11)


class SectionDirectionTests(unittest.TestCase):
    def test_each_section_gets_its_own_direction(self):
        directions = mv2.section_directions(OUTRO_IDEA)
        self.assertEqual(len(directions), 6)
        get = lambda section: mv2.directions_for(section, directions) or ""
        self.assertIn("streaming room", get("Verse 1"))
        self.assertIn("mirror", get("Verse 2"))
        self.assertIn("barefoot", get("Chorus"))
        self.assertIn("dances", get("Guitar Solo / Melodic Outro Breakdown"))
        self.assertIn("bedroom", get("Outro"))
        self.assertIsNone(mv2.directions_for("Intro", directions))

    def test_generic_and_instrumental_directions(self):
        directions = mv2.section_directions("Intro and Verse 1: hotel room at night.\nVerse - on stage.\n"
                                            "Instrumental break - drone flight over the city.\nSome other line: not a section.")
        self.assertEqual(mv2.directions_for("Verse 1", directions), "hotel room at night.")   # exact beats generic
        self.assertEqual(mv2.directions_for("Verse 3", directions), "on stage.")
        self.assertEqual(mv2.directions_for("Guitar Solo", directions), "drone flight over the city.")
        self.assertEqual(mv2.directions_for("Intro", directions), "hotel room at night.")

    def test_scene_request_carries_only_the_matching_direction(self):
        scene = {"section": "Verse 2", "energy": 0.5, "shots": [
            {"start": 0.0, "end": 4.0, "size": "close-up", "location": "gold mirror", "lyrics": ["line"]}]}
        bible = {"style": "film", "characters": ["an adult woman"]}
        request = mv2.scene_llm_request(scene, bible, index=10, total=13, idea=OUTRO_IDEA, previous_summary="")
        self.assertIn("DIRECTIONS FOR THIS SECTION (Verse 2)", request)
        self.assertIn("red lipstick", request.split("DIRECTIONS FOR THIS SECTION")[1].splitlines()[0])
        plain = mv2.scene_llm_request(scene, bible, index=10, total=13, idea="A calm song about the sea.", previous_summary="")
        self.assertNotIn("DIRECTIONS FOR THIS SECTION", plain)


class ShotLocationTests(unittest.TestCase):
    def test_shots_never_leave_for_another_sections_place(self):
        """Only shot 1 of a new section may still show the previous section's place; B-roll stays at home.
        v1.2.4 cut B-roll to other sections' places and the next scenes stayed there (intro chorus -> throne)."""
        lyrics = ("[Verse 1]\nWalking down an empty road tonight\nCounting every silent passing light\n[Chorus]\n"
                  "Hold the signal, keep it bright\n[Guitar Solo]\n[Bridge]\nOne more call I never take\n[Outro]\nSee you")
        seconds = 120.0
        sections, lines, _ = mv2.parse_lyrics(lyrics)
        mv2.distribute_lines_evenly(lines, 1.0, seconds - 1.0)
        sections = mv2.resolve_sections(sections, lines, seconds)
        t = torch.arange(int(seconds * 12000)) / 12000
        audio = (0.05 * torch.sin(2 * torch.pi * 220 * t)).numpy()
        scenes = mv2.build_scenes(seconds, mv2.audio_features(audio, 12000), sections, lines, mv2.SplitSettings())
        parts = mv2.story_parts(scenes)
        bible = mv2.default_bible("idea", [], parts, "Pop.")
        bible["locations"] = {p["key"]: f"place of {p['key']}" for p in parts}
        previous = (None, None, None)
        broll = 0
        for scene in scenes:
            scene["shots"] = mv2.build_scene_shots(scene, lines, bible, index=scene["index"], previous_camera=previous[0],
                                                   previous_location=previous[1], previous_part=previous[2])
            own = f"place of {scene['part']}"
            for k, shot in enumerate(scene["shots"]):
                allowed = {own, previous[1]} if k == 0 and previous[1] else {own}
                self.assertIn(shot["location"], allowed, (scene["index"], k))
                broll += k > 0 and not shot["lyrics"]
            if previous[2] == scene["part"]:
                self.assertEqual(scene["shots"][0]["location"], own)   # inside a section: never elsewhere
            previous = (scene["shots"][-1]["camera"], scene["shots"][-1]["location"], scene["part"])
        self.assertGreater(broll, 0)   # the fixture really contains B-roll cuts


class WorkflowV125Tests(unittest.TestCase):
    def test_shipped_workflow_writes_prompts_with_auto(self):
        sys.path.insert(0, str(ROOT))
        from tools.build_h3_music_video_v122 import PATH, LLM, RELEASE, build_all
        self.assertEqual(LLM, backend.AUTO)
        built = build_all()[PATH]
        shipped = json.loads((ROOT / "workflows" / PATH).read_text(encoding="utf-8"))
        self.assertEqual(shipped, built)
        writer = next(n for n in shipped["nodes"] if n["type"] == "DaWMV2PromptWriter")
        self.assertEqual(writer["widgets_values"][1], backend.AUTO)
        marker = shipped["extra"]["dawasteh_h3_music_video_v122"]
        self.assertEqual((marker["version"], marker["release"], RELEASE), (1, "v1.2.5", "v1.2.5"))
        schema = json.loads((ROOT / "tools/workflow_templates/v122/node-schemas.json").read_text(encoding="utf-8"))
        llm = schema["DaWMV2PromptWriter"]["input"]["required"]["llm"][1]
        self.assertEqual((llm["default"], llm["options"][0]), (backend.AUTO, backend.AUTO))
        self.assertIn("Qwen\\qwen3.5_4b_bf16.safetensors", llm["options"])   # the fallback stays selectable

    def test_default_resolution_is_1664x928(self):
        """1344x768 and below showed lip/face artifacts; 1920x1088 takes ~1.8x longer than 1664x928."""
        sys.path.insert(0, str(ROOT))
        from tools.build_h3_music_video_v122 import PATH
        shipped = json.loads((ROOT / "workflows" / PATH).read_text(encoding="utf-8"))
        sizes = next(n for n in shipped["nodes"] if n["type"] == "PixaromaSizes")
        for state in (sizes["widgets_values"][0], json.loads(sizes["properties"]["sizesState"])):
            self.assertEqual(state["sizes"][state["selected"]], [1664, 928])
            self.assertEqual((state["w"], state["h"]), (1664, 928))
        planner = next(n for n in shipped["nodes"] if n["type"] == "DaWMV2Planner")
        self.assertEqual(planner["widgets_values"][3:5], [1664, 928])
        source = (PACK / "nodes_v2.py").read_text(encoding="utf-8")
        self.assertIn('io.Int.Input("width", default=1664', source)
        self.assertIn('io.Int.Input("height", default=928', source)


class EvidenceV125Tests(unittest.TestCase):
    def test_report_backs_the_chosen_quant(self):
        report = json.loads((ROOT / "performance/rdna4/h3-music-video-v125-prompt-writer.json").read_text(encoding="utf-8"))
        script = (ROOT / "tools" / "start-MultiGPU.ps1").read_text(encoding="utf-8-sig")
        chosen = Path(report["chosen"]["model"]).name
        self.assertIn(chosen, script)
        ppl = {row["file"]: row["ppl"] for row in report["perplexity_wikitext2"]["rows"]}
        fits = [row for row in report["vram_fit_rx9070xt"]["rows"] if row["model"] in chosen and row["ctx"] == 8192
                and row["mmproj"] == "cpu" and row["ubatch"] == 512]
        self.assertLess(ppl[chosen], ppl["Qwen3.8-27B-Ridge-3.7bpw.gguf"])
        self.assertLess(fits[0]["shared_gib"], backend.SPILL_WARN_GIB)   # no spill warning with the shipped setup
        for flag in ("--spec-type draft-mtp", "--no-mmproj-offload", "-c 8192"):
            self.assertIn(flag, report["chosen"]["server_args"])
        best = [r for r in report["prompt_quality"]["rows"] if "IQ4_XS" in r["writer"]]
        self.assertTrue(all(r["place"] == 1.0 and r["repeated"].startswith("0/") for r in best))


class LauncherTests(unittest.TestCase):
    def test_start_profile_sets_the_prompt_model_only_when_both_files_exist(self):
        script = (ROOT / "tools" / "start-MultiGPU.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('$PromptLlmGguf = Join-Path $ComfyPath "models\\LLM\\Qwen3.8\\Qwen3.8-27B-IQ4_XS-3.84bpw.gguf"', script)
        self.assertLess(script.index("$ComfyPath = "), script.index("$PromptLlmGguf = "))
        self.assertIn("(Test-Path -LiteralPath $PromptLlmGguf) -and (Test-Path -LiteralPath $LlamaServerExe)", script)
        for env in ("DAWASTEH_PROMPT_LLM_GGUF", "DAWASTEH_LLAMA_SERVER", "DAWASTEH_LLAMA_HIP_DEVICE"):
            self.assertIn(f"$env:{env} = ", script)
        self.assertIn("Remove-Item Env:DAWASTEH_PROMPT_LLM_GGUF", script)
        self.assertIn('$LlamaHipDevice = "1"', script)
        self.assertIn(backend.ENV_MODEL, script)


if __name__ == "__main__":
    unittest.main()
