"""v1.2.2 FastH3 music video: planning invariants, prompt format and the rebuilt UI graph."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MV2_PATH = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo" / "mv2.py"
spec = importlib.util.spec_from_file_location("dawasteh_mv2_test", MV2_PATH)
assert spec is not None and spec.loader is not None
mv2 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mv2  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(mv2)

LYRICS = """[Verse 1]
Walking down an empty road tonight
Counting every silent passing light
[Chorus]
Hold the signal, keep it bright
Carry every secret into light
[Guitar Solo]
[Outro]
See you on the other side"""


def click_track(seconds: float, bpm: float = 120.0, sr: int = 12000) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    audio = 0.05 * np.sin(2 * np.pi * 220 * t)
    beat = 60.0 / bpm
    for k in range(int(seconds / beat)):
        start = int(k * beat * sr)
        audio[start:start + 240] += np.hanning(240) * (0.9 if k % 4 == 0 else 0.5)
    # louder second half, so energy/novelty vary
    audio[len(audio) // 2:] *= 1.8
    return audio.astype(np.float32)


def plan(seconds: float, lyrics: str = LYRICS, split=None):
    features = mv2.audio_features(click_track(seconds), 12000)
    sections, lines, _ = mv2.parse_lyrics(lyrics)
    if lines:
        mv2.distribute_lines_evenly(lines, 1.0, seconds - 1.0)
    sections = mv2.resolve_sections(sections, lines, seconds)
    return mv2.build_scenes(seconds, features, sections, lines, split or mv2.SplitSettings()), lines, sections


class LyricsTests(unittest.TestCase):
    def test_sections_and_instrumental_headers(self):
        sections, lines, timed = mv2.parse_lyrics(LYRICS)
        self.assertFalse(timed)
        self.assertEqual([s.name for s in sections], ["Verse 1", "Chorus", "Guitar Solo", "Outro"])
        self.assertEqual([s.kind for s in sections], ["sung", "sung", "instrumental", "sung"])
        self.assertEqual(len(lines), 5)

    def test_lrc_timestamps(self):
        _, lines, timed = mv2.parse_lyrics("[00:01.50] Hello world\n[00:04.25] Second line")
        self.assertTrue(timed)
        self.assertEqual([l.start for l in lines], [1.5, 4.25])

    def test_alignment_maps_misheard_words_and_orders_lines(self):
        _, lines, _ = mv2.parse_lyrics(LYRICS)
        words = []
        cursor = 2.0
        for line in lines:
            for token in line.text.replace("secret", "secrets").split():
                words.append({"word": token, "start": cursor, "end": cursor + 0.3})
                cursor += 0.35
            cursor += 1.0
        coverage = mv2.align_lines_to_words(lines, words, 60.0)
        self.assertGreater(coverage, 0.9)
        self.assertAlmostEqual(lines[0].start, 2.0)
        starts = [l.start for l in lines]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(l.source == "asr" for l in lines))

    def test_unaligned_lines_are_interpolated(self):
        _, lines, _ = mv2.parse_lyrics(LYRICS)
        coverage = mv2.align_lines_to_words(lines, [{"word": "zzz", "start": 1.0, "end": 1.2}], 30.0)
        self.assertEqual(coverage, 0.0)
        self.assertTrue(all(l.start is not None and l.end > l.start for l in lines))


class PlanTests(unittest.TestCase):
    def test_any_length_exact_frame_accounting(self):
        for seconds in (3.0, 30.0, 90.0, 600.0):
            with self.subTest(seconds=seconds):
                scenes, _, _ = plan(seconds)
                total = math.ceil(seconds * 24 - 1e-9)
                self.assertEqual(scenes[0]["start_frame"], 0)
                self.assertEqual(scenes[-1]["end_frame"], total)
                self.assertEqual(sum(s["frames"] for s in scenes), total)
                for a, b in zip(scenes, scenes[1:]):
                    self.assertEqual(a["end_frame"], b["start_frame"])
                for s in scenes:
                    self.assertEqual(s["gen_frames"] % 17, 5)
                    self.assertEqual(mv2.latent_frames(s["gen_frames"]) % 2, 0, "odd VSA latent lengths are slower")
                    self.assertGreaterEqual(s["gen_frames"], s["prefix_frames"] + s["frames"])
                    self.assertLessEqual(s["gen_frames"], 362)
                    self.assertEqual(s["audio_start_frame"], s["start_frame"] - s["prefix_frames"])
                    self.assertEqual(s["prefix_frames"], 0 if s["index"] == 0 else 22)
                if total > 9 * 24:
                    self.assertTrue(all(4 * 24 <= s["frames"] <= 9 * 24 for s in scenes))
                    # at 864x480 every clip fits FastH3 completely in VRAM (measured limit 243 H3 frames).
                    self.assertTrue(all(s["gen_frames"] <= 243 for s in scenes))

    def test_scene_count_scales_and_lengths_vary(self):
        counts = {s: len(plan(s)[0]) for s in (30.0, 90.0, 600.0)}
        self.assertLess(counts[30.0], counts[90.0])
        self.assertLess(counts[90.0], counts[600.0])
        self.assertGreater(counts[600.0], 40)
        lengths = {s["frames"] for s in plan(600.0)[0]}
        self.assertGreater(len(lengths), 3)

    def test_section_boundaries_are_preferred_cuts(self):
        scenes, _, sections = plan(90.0)
        cut_times = [s["start"] for s in scenes[1:]]
        for previous, section in zip(sections, sections[1:]):
            if section.kind != "sung":
                continue
            # A cut at this boundary, or at the start of an instrumental break directly before it.
            window_start = previous.start if previous.kind == "instrumental" else section.start
            self.assertTrue(any(window_start - 0.6 <= t <= section.start + 0.6 for t in cut_times), section.name)

    def test_invalid_split_settings(self):
        with self.assertRaises(ValueError):
            mv2.SplitSettings(target=3.0, minimum=5.0, maximum=8.0).validate()
        with self.assertRaises(ValueError):
            mv2.SplitSettings(target=8.0, minimum=4.0, maximum=16.0).validate()
        self.assertEqual((mv2.SplitSettings().target, mv2.SplitSettings().maximum), (7.0, 9.0))

    def test_fast_gen_frames_prefers_even_latents(self):
        self.assertEqual(mv2.fast_gen_frames(192), 209)   # t 57 -> 62
        self.assertEqual(mv2.fast_gen_frames(210), 226 + 17)  # 226 (t 67) -> 243 (t 72)
        self.assertEqual(mv2.fast_gen_frames(243), 243)
        self.assertEqual(mv2.fast_gen_frames(330), 345)   # t 102 already even
        self.assertEqual(mv2.fast_gen_frames(362), 362)   # t 107 odd, but +17 would leave the trained range

    def test_seeds_differ_per_scene(self):
        self.assertEqual(len({mv2.scene_seed(7, i) for i in range(100)}), 100)


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.scenes, self.lines, _ = plan(90.0)
        parts = mv2.story_parts(self.scenes)
        self.bible = mv2.default_bible("A walk through a ruined city.", ["This character is a young woman with pink hair."], parts, "Pop.")
        previous = (None, None, None)
        for scene in self.scenes:
            scene["shots"] = mv2.build_scene_shots(scene, self.lines, self.bible, index=scene["index"], previous_camera=previous[0],
                                                   previous_location=previous[1], previous_part=previous[2])
            previous = (scene["shots"][-1]["camera"], scene["shots"][-1]["location"], scene["part"])

    def test_minimax_base_format_and_lyrics(self):
        prompt = mv2.assemble_prompt(self.scenes[1], self.bible, index=1, total=len(self.scenes), language="English")
        self.assertTrue(prompt.startswith("integrated_multimodal_description: [Shot 1] "))
        self.assertIn("\n\noverall_soundscape: ", prompt)
        self.assertIn("\n\nnon_diegetic_music: ", prompt)
        self.assertIn("The singer is a young woman with pink hair.", prompt)
        self.assertIn("The running shot continues without any cut in", prompt)
        self.assertNotIn("logo", prompt.lower())
        sung = [l for shot in self.scenes[1]["shots"] for l in shot["lyrics"]]
        if sung:
            self.assertIn("(S1)", prompt)
            self.assertIn("<d>[English] ", prompt)
        for number, shot in enumerate(self.scenes[1]["shots"][1:], start=2):
            # clip time = scene time + the frozen continuity frames at the start of an extended clip
            clip_time = shot['start'] + self.scenes[1]['prefix_frames'] / 24
            self.assertIn(f"[Shot {number}] At {mv2.fmt_ts(clip_time)}, the camera cuts to", prompt)

    def test_first_scene_has_no_continuity_clause(self):
        prompt = mv2.assemble_prompt(self.scenes[0], self.bible, index=0, total=len(self.scenes), language="English")
        self.assertNotIn("without any cut", prompt)

    def test_every_lyric_line_is_sung_exactly_once(self):
        sung = [l for scene in self.scenes for shot in scene["shots"] for l in shot["lyrics"]]
        self.assertEqual(sorted(sung), sorted(l.text for l in self.lines))

    def test_extended_scene_starts_in_previous_location(self):
        for a, b in zip(self.scenes, self.scenes[1:]):
            self.assertEqual(b["shots"][0]["location"], a["shots"][-1]["location"])

    def test_bible_parser_is_chronological(self):
        parts = mv2.story_parts(self.scenes)
        text = "STYLE: Gritty live-action look.\n" + "\n".join(f"LOCATION {k + 1}: Place number {k + 1} with light" for k in range(len(parts)))
        bible = mv2.parse_bible_text(text, self.bible, parts)
        self.assertEqual(bible["style"], "Gritty live-action look.")
        self.assertEqual([bible["locations"][p["key"]] for p in parts], [f"Place number {k + 1} with light" for k in range(len(parts))])

    def test_shot_parser(self):
        self.assertEqual(mv2.parse_shot_text("SHOT 1: She walks down the street slowly.\nSHOT 2: She opens a door.", 2),
                         ["She walks down the street slowly.", "She opens a door."])
        self.assertEqual(mv2.parse_shot_text("garbage", 2), [None, None])


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.build_h3_music_video_v122 import build_all, PATH
        cls.path = PATH
        cls.workflow = build_all()[PATH]

    def node(self, kind):
        return [n for n in self.workflow["nodes"] if n["type"] == kind]

    def source(self, target, name):
        slot = next(i for i, s in enumerate(target["inputs"]) if s["name"] == name)
        link = next(l for l in self.workflow["links"] if l[3:5] == [target["id"], slot])
        return next(n for n in self.workflow["nodes"] if n["id"] == link[1]), link[2]

    def test_shipped_file_is_the_deterministic_build(self):
        from tools.build_h3_music_video_v122 import build_all
        self.assertEqual(build_all()[self.path], self.workflow)
        shipped = json.loads((ROOT / "workflows" / self.path).read_text(encoding="utf-8"))
        self.assertEqual(shipped, self.workflow)
        self.assertNotIn(b"\r\n", (ROOT / "workflows" / self.path).read_bytes())

    def test_flat_valid_rodent_timer_gpu_control(self):
        from tools.rodent_layout import _topology_hash
        from tools.validate_workflows import validate_graph
        errors = []
        validate_graph(Path(self.path), "root", self.workflow, errors)
        self.assertEqual(errors, [])
        self.assertFalse(self.workflow.get("definitions", {}).get("subgraphs"))
        self.assertEqual(self.workflow["extra"]["dawasteh_rodent_layout"]["topology_sha256"], _topology_hash(self.workflow))
        self.assertEqual(len(self.node("PixaromaRunTimer")), 1)
        self.assertEqual(len(self.node("DaWMultiGPUDeviceControl")), 1)
        self.assertFalse(self.node("DaWH3MusicVideoDirectorDualGPU"))

    def test_fasth3_profile_matches_local_test(self):
        unet = self.node("DaWMV2LoadModel")[0]  # v1.2.4: read-only FastH3 loader with optional LoRA (MV 0)
        self.assertIn("fastvideo_fasth3_8step_v2_pruned_int8_convrot", unet["widgets_values"][0])
        self.assertEqual(self.node("MiniMaxH3SigmaShift")[0]["widgets_values"], [10.0, 3.0])
        self.assertEqual(self.node("ModelAttentionBackend")[0]["widgets_values"], ["comfy kitchen attention"])
        self.assertEqual(self.node("BlockSparseAttention")[0]["widgets_values"][:2], ["vsa", 10.0])
        self.assertEqual(self.node("KSamplerSelect")[0]["widgets_values"], ["res_multistep"])
        self.assertEqual(self.node("BasicScheduler")[0]["widgets_values"], ["simple", 8, 1.0])
        self.assertEqual(len(self.node("SamplerCustomAdvanced")), 2)
        self.assertFalse(self.node("CLIPLoader"))

    def test_review_then_loop_then_final(self):
        # v1.2.5: MV 5b (video review after every scene) replaced the Pixaroma image gate after scene 1
        self.assertFalse(self.node("PixaromaPauseImage"))
        start = self.node("PixaromaLoopStart")[0]
        # v1.2.7: MV 5c (upscale of the accepted take) sits between the review and the loop
        first_upscale = self.source(start, "value1")[0]
        self.assertEqual(first_upscale["type"], "DaWMV2UpscaleScene")
        first_review = self.source(first_upscale, "scene")[0]
        self.assertEqual(first_review["type"], "DaWMV2ReviewScene")
        first_save, slot = self.source(first_review, "scene")
        self.assertEqual((first_save["type"], slot), ("DaWMV2SaveScene", 0))
        self.assertEqual(first_save["widgets_values"][:2], [0, 0])
        planner, slot = self.source(start, "total")
        self.assertEqual((planner["type"], slot), ("DaWMV2Planner", 2))
        saves = self.node("DaWMV2SaveScene")
        loop_save = next(s for s in saves if s["id"] != first_save["id"])
        self.assertEqual(self.source(loop_save, "scene_index"), (start, 6))
        self.assertEqual(loop_save["widgets_values"][1], 1)
        self.assertEqual(self.source(loop_save, "after"), (start, 0))
        end = self.node("PixaromaLoopEnd")[0]
        loop_upscale = self.source(end, "value1")[0]
        self.assertEqual(loop_upscale["type"], "DaWMV2UpscaleScene")
        loop_review = self.source(loop_upscale, "scene")[0]
        self.assertEqual(loop_review["type"], "DaWMV2ReviewScene")
        self.assertEqual(self.source(loop_review, "scene"), (loop_save, 0))
        self.assertEqual(self.source(end, "loop"), (start, 5))
        final = self.node("DaWMV2Finalize")[0]
        self.assertEqual(self.source(final, "after")[0]["id"], end["id"])

    def test_inputs_are_pixaroma_and_optional_sheets_are_muted(self):
        planner = self.node("DaWMV2Planner")[0]
        self.assertEqual(self.source(planner, "lyrics")[0]["type"], "PixaromaPrompt")
        self.assertEqual(self.source(planner, "video_idea")[0]["type"], "PixaromaPrompt")
        self.assertEqual(self.source(planner, "width"), (self.node("PixaromaSizes")[0], 0))
        self.assertEqual(self.source(planner, "height"), (self.node("PixaromaSizes")[0], 1))
        writer = self.node("DaWMV2PromptWriter")[0]
        for k in (1, 2, 3):
            load, _ = self.source(writer, f"character_{k}")
            self.assertEqual((load["type"], load["mode"]), ("PixaromaLoadImage", 2))
            self.assertEqual(json.loads(load["properties"]["loadImagePixState"])["mode"], "off")
            shape = next(s for s in writer["inputs"] if s["name"] == f"character_{k}").get("shape")
            self.assertEqual(shape, 7)


class LiveEvidenceTests(unittest.TestCase):
    """The committed end-to-end evidence must describe exactly the shipped files."""

    @classmethod
    def setUpClass(cls):
        import hashlib
        cls.sha = staticmethod(lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest())
        cls.report = json.loads((ROOT / "performance/rdna4/h3-music-video-v122-validation.json").read_text(encoding="utf-8"))

    def test_report_pins_shipped_workflow_and_sources(self):
        import hashlib
        import subprocess
        # v1.2.4 rebuilt the workflow around MV 0; this evidence describes the v1.2.2 file (see the v1.2.4 report).
        shipped = subprocess.check_output(["git", "show", "v1.2.2:" + self.report["workflow"]["path"]], cwd=ROOT)
        self.assertEqual(self.report["workflow"]["sha256"], hashlib.sha256(shipped).hexdigest())
        for entry in self.report["sources"]:
            # v1.2.3 fixed the shot-cut timestamps in mv2.py; the evidence describes the v1.2.2 run.
            data = subprocess.check_output(["git", "show", "v1.2.2:" + entry["path"]], cwd=ROOT)
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"], entry["path"])

    def test_pause_then_continue_produced_the_full_film(self):
        runs = self.report["runs"]
        self.assertEqual((runs["pause"]["status"], runs["continue"]["status"]), ("success", "success"))
        self.assertNotIn("PixaromaLoopStart", self.report["workflow"]["pause_node_classes"])
        self.assertNotIn("DaWMV2Finalize", self.report["workflow"]["pause_node_classes"])
        self.assertIn("DaWMV2Finalize", self.report["workflow"]["continue_node_classes"])
        self.assertEqual(len(runs["scenes"]), self.report["plan"]["scenes"])
        film = self.report["final_film"]
        self.assertEqual(film["frames"], film["expected_frames"])
        self.assertTrue(film["audio_packets_identical"])
        self.assertLess(film["seam_ratio_median"], 1.2)
        self.assertLess(film["seam_ratio_max"], 2.0)  # singing close-ups move fast; frozen frames pass one VAE round trip
        for scene in runs["scenes"]:
            self.assertLessEqual(scene["h3_frames"], 243)
            self.assertEqual(scene["latent_t"] % 2, 0)


if __name__ == "__main__":
    unittest.main()
