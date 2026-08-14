from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-H3-MusicVideo" / "core.py"
HAVE_COMFY_RUNTIME = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("av") is not None


class H3WorkflowSerializationTests(unittest.TestCase):
    def test_director_seed_control_does_not_shift_following_widgets(self):
        workflow_path = (
            ROOT
            / "workflows"
            / "Reference to Video"
            / "MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json"
        )
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        director = next(node for node in workflow["nodes"] if node["type"] == "DaWH3MusicVideoDirectorDualGPU")
        values = director["widgets_values"]
        input_names = [entry["name"] for entry in director["inputs"]]
        self.assertEqual(
            input_names[-5:],
            ["reference_strategy", "force_reference_as_first_frame", "model_device", "clip_device", "vae_device"],
        )
        self.assertEqual(values[12], 8)
        self.assertEqual(values[13], 314159265358979)
        self.assertEqual(values[14], "fixed")
        self.assertEqual(values[15], "fixed")
        self.assertIs(values[16], True)
        self.assertEqual(values[17:21], [14.0, 18.0, "medium", "mkv"])
        self.assertEqual(values[31:35], [12.0, 4.0, "euler", "beta"])
        self.assertEqual(values[-5:-3], ["identity lock (recommended)", True])
        self.assertEqual(values[-3:], ["gpu:0", "gpu:1", "gpu:1"])


@unittest.skipUnless(HAVE_COMFY_RUNTIME, "requires the ComfyUI runtime's torch and PyAV")
class H3MusicVideoCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("h3_music_video_core_test", CORE_PATH)
        assert spec and spec.loader
        cls.core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.core)

    def run_ffmpeg(self, *args: str) -> None:
        subprocess.run(
            [self.core.find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
            check=True,
        )

    def make_video(self, path: Path, frames: int) -> None:
        import av
        import numpy as np
        with av.open(str(path), "w") as container:
            stream = container.add_stream("mpeg4", rate=24)
            stream.width = stream.height = 16
            stream.pix_fmt = "yuv420p"
            for _ in range(frames):
                frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    def test_frame_grid_boundaries(self):
        self.assertEqual(self.core.align_h3_frames(0), 5)
        self.assertEqual(self.core.align_h3_frames(5), 5)
        self.assertEqual(self.core.align_h3_frames(6), 22)
        self.assertEqual(self.core.align_h3_frames(22), 22)
        self.assertEqual(self.core.align_h3_frames(3592), 3592)
        with self.assertRaises(ValueError):
            self.core.align_h3_frames(3593)

    def test_pyav_counts_decoded_frames_without_ffprobe(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "frames.mp4"
            self.make_video(video, 7)
            with mock.patch.object(self.core, "find_ffprobe", side_effect=AssertionError("ffprobe must not run")):
                self.assertEqual(self.core.count_video_frames("definitely-not-ffmpeg", str(video)), 7)

    def test_no_video_stream_reports_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "audio.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(b"\\0\\0" * 800)
            with self.assertRaisesRegex(ValueError, "No video stream"):
                self.core.count_video_frames("definitely-not-ffmpeg", str(audio))

    def test_pyav_decode_error_falls_back_to_ffprobe(self):
        invalid_data = self.core.av.error.InvalidDataError(1094995529, "invalid data")
        probe_result = subprocess.CompletedProcess(
            ["ffprobe"],
            0,
            stdout=b'{"streams":[{"nb_read_frames":"7"}]}',
            stderr=b"",
        )
        with (
            mock.patch.object(self.core.av, "open", side_effect=invalid_data),
            mock.patch.object(self.core, "find_ffprobe", return_value="ffprobe") as find_probe,
            mock.patch.object(self.core, "run_command", return_value=probe_result),
        ):
            self.assertEqual(self.core.count_video_frames("ffmpeg", "broken.mp4"), 7)
        find_probe.assert_called_once_with("ffmpeg")

    def test_identity_lock_uses_only_original_reference_after_first_scene(self):
        settings = {
            "text_encoder": "text.safetensors", "video_vae": "video.safetensors",
            "audio_vae": "audio.safetensors", "diffusion_model": "model.safetensors",
            "shift_video": 12.0, "shift_audio": 3.0, "width": 480, "height": 864,
            "ref_image_size": "match", "sampler_name": "res_multistep", "scheduler": "beta",
            "steps": 20, "spectrum_enabled": False, "continuity": True,
            "reference_strategy": self.core.IDENTITY_LOCK,
        }
        manifest = {
            "settings": settings,
            "reference_image_path": "reference.png",
            "segments": [
                {"h3_frames": 22, "target_frames": 20, "prompt": "first", "seed": 1, "continuity_path": "first-last.png"},
                {"h3_frames": 22, "target_frames": 20, "prompt": "second", "seed": 1, "continuity_path": "second-last.png"},
            ],
        }
        prompt = self.core.build_segment_api_prompt("manifest.json", 1, manifest)
        self.assertIn("2", prompt)
        self.assertNotIn("3", prompt)
        reference_inputs = [name for name in prompt["17"]["inputs"] if name.startswith("ref_images.")]
        self.assertEqual(reference_inputs, ["ref_images.ref_image_0"])

    def test_dual_gpu_child_prompt_routes_model_clip_and_vaes(self):
        settings = {
            "text_encoder": "text.safetensors", "video_vae": "video.safetensors",
            "audio_vae": "audio.safetensors", "diffusion_model": "model.safetensors",
            "shift_video": 12.0, "shift_audio": 3.0, "width": 480, "height": 864,
            "ref_image_size": "match", "sampler_name": "res_multistep", "scheduler": "beta",
            "steps": 20, "spectrum_enabled": False, "continuity": False,
            "reference_strategy": self.core.IDENTITY_LOCK, "dual_gpu": True,
            "model_device": "gpu:1", "clip_device": "gpu:0", "vae_device": "cpu",
        }
        manifest = {
            "settings": settings,
            "reference_image_path": None,
            "segments": [
                {"h3_frames": 22, "target_frames": 20, "prompt": "first", "seed": 1, "continuity_path": "first-last.png"},
            ],
        }
        prompt = self.core.build_segment_api_prompt("manifest.json", 0, manifest)
        self.assertEqual(prompt["30"], {"class_type": "SelectCLIPDevice", "inputs": {"clip": ["10", 0], "device": "gpu:0"}})
        self.assertEqual(prompt["31"]["inputs"]["device"], "cpu")
        self.assertEqual(prompt["32"]["inputs"]["device"], "cpu")
        self.assertEqual(prompt["33"], {"class_type": "SelectModelDevice", "inputs": {"model": ["13", 0], "device": "gpu:1"}})
        self.assertEqual(prompt["29"]["class_type"], "LoraLoaderModelOnly")
        self.assertEqual(prompt["29"]["inputs"], {
            "model": ["33", 0],
            "lora_name": self.core.DEFAULT_H3_TURBO_LORA,
            "strength_model": 1.0,
        })
        self.assertEqual(prompt["14"]["inputs"]["model"], ["29", 0])
        self.assertEqual(prompt["17"]["inputs"]["clip"], ["30", 0])
        self.assertEqual(prompt["17"]["inputs"]["vae"], ["31", 0])
        self.assertEqual(prompt["17"]["inputs"]["audio_vae"], ["32", 0])
        self.assertEqual(prompt["22"]["inputs"]["vae"], ["31", 0])

    def test_encoder_forces_canonical_reference_as_first_frame(self):
        import av
        import numpy as np
        from PIL import Image
        import torch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.png"
            video = root / "scene.mp4"
            pixels = np.zeros((32, 16, 3), dtype=np.uint8)
            pixels[:, :8] = (240, 30, 30)
            pixels[:, 8:] = (20, 220, 70)
            Image.fromarray(pixels, mode="RGB").save(reference)
            images = torch.zeros((8, 32, 32, 3), dtype=torch.float32)
            self.core.encode_images_to_h264(
                self.core.find_ffmpeg(), images, 8, str(video), crf=0, preset="fast",
                first_frame_path=str(reference),
            )
            expected = self.core.canonical_reference_frame(str(reference), 32, 32).astype(np.int16)
            with av.open(str(video)) as container:
                decoded = next(container.decode(video=0)).to_ndarray(format="rgb24").astype(np.int16)
            self.assertLess(float(np.mean(np.abs(decoded - expected))), 5.0)

    def test_identity_lock_prompt_is_explicit_and_stable(self):
        segments = [
            {"index": 0, "energy": 0.8, "role": "opening", "text_excerpt": "hello"},
            {"index": 1, "energy": 0.8, "role": "chorus", "text_excerpt": "again"},
        ]
        prompts = self.core.build_deterministic_prompts(
            segments, "One singer on one stage", has_base_reference=True, continuity=True,
            reference_strategy=self.core.IDENTITY_LOCK,
        )
        self.assertTrue(all("immutable cast" in prompt for prompt in prompts))
        self.assertTrue(all("exactly two arms and two hands" in prompt for prompt in prompts))
        self.assertTrue(all("<Picture 2>" not in prompt for prompt in prompts))
        self.assertTrue(all(self.core.LIGHTING[0] in prompt for prompt in prompts))

    def test_final_mux_preserves_every_original_audio_packet(self):
        import av
        import hashlib

        def audio_packet_digest(path: Path) -> tuple[str, int]:
            digest = hashlib.sha256()
            count = 0
            with av.open(str(path)) as container:
                for packet in container.demux(container.streams.audio[0]):
                    payload = bytes(packet)
                    if payload:
                        digest.update(payload)
                        count += 1
            return digest.hexdigest(), count

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            segment = project / "segment.mp4"
            source_audio = project / "song.mp3"
            output = project / "final.mkv"
            self.make_video(segment, 48)
            self.run_ffmpeg(
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "libmp3lame", "-b:a", "192k", str(source_audio),
            )
            manifest = {
                "project_dir": str(project),
                "source_audio_copy": str(source_audio),
                "final_output_path": str(output),
                "settings": {"video_preset": "medium", "final_crf": 18},
                "segments": [{"video_path": str(segment), "target_frames": 48}],
            }
            manifest_path = project / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            original_run_command = self.core.run_command
            commands = []

            def record(command, **kwargs):
                commands.append(command)
                return original_run_command(command, **kwargs)

            with mock.patch.object(self.core, "run_command", side_effect=record):
                self.assertEqual(
                    self.core.concat_and_mux_project(self.core.find_ffmpeg(), str(manifest_path)),
                    str(output),
                )
            joined = project / "joined_video.mkv"
            silent = project / "joined_video_silent.mp4"
            final_command = next(command for command in commands if str(joined.with_name("joined_video.tmp.mkv")) in command)
            self.assertNotIn("-shortest", final_command)
            self.assertIn("-c:a", final_command)
            self.assertEqual(final_command[final_command.index("-c:a") + 1], "copy")
            self.assertTrue(joined.is_file())
            self.assertTrue(silent.is_file())
            self.assertEqual(joined.read_bytes(), output.read_bytes())
            self.assertEqual(self.core.count_video_frames(self.core.find_ffmpeg(), str(output)), 48)
            with av.open(str(output)) as container:
                self.assertIn(container.streams.audio[0].codec_context.name, {"mp3", "mp3float"})
                self.assertLessEqual(float(container.duration / av.time_base), 2.1)
            with av.open(str(silent)) as container:
                self.assertFalse(container.streams.audio)
            self.assertEqual(audio_packet_digest(source_audio), audio_packet_digest(joined))
            self.assertEqual(audio_packet_digest(source_audio), audio_packet_digest(output))
            updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["silent_concat_path"], str(silent))
            self.assertEqual(updated["joined_deliverable_path"], str(joined))


if __name__ == "__main__":
    unittest.main()
