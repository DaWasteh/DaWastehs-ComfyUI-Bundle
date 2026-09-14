import importlib.util
from pathlib import Path
from collections.abc import Mapping
from types import SimpleNamespace
import unittest

PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_nodes/ComfyUI-DaWasteh-GamePhysics/video_frames.py"
)
spec = importlib.util.spec_from_file_location("v118_video_frames", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ExplodingAudio(Mapping):
    def __getitem__(self, key):
        raise AssertionError("Silent-video audio must never be materialized")

    def __iter__(self):
        raise AssertionError("Silent-video audio must never be iterated")

    def __len__(self):
        raise AssertionError("Silent-video audio must never be measured")


class VideoFramesTests(unittest.TestCase):
    def test_only_image_is_returned_and_audio_stays_lazy(self):
        image = SimpleNamespace(shape=(5, 480, 848, 3))
        calls = []

        def load_video(**kwargs):
            calls.append(kwargs)
            return image, 5, ExplodingAudio(), {}

        loader = SimpleNamespace(load_video=load_video)
        self.assertIs(mod.load_frames(loader, "silent.mp4", 16, 848, 480, 5), image)
        self.assertEqual(calls[0]["frame_load_cap"], 5)
        self.assertEqual(calls[0]["force_rate"], 16)
        self.assertEqual(calls[0]["format"], "Wan")

    def test_invalid_bounds_and_paths_fail_before_decoding(self):
        for kwargs in (
            {"fps": float("nan")},
            {"frame_limit": 0},
            {"frame_limit": 94},
            {"width": 8192},
            {"height": 479},
            {"video": "../escape.mp4"},
            {"video": "C:/escape.mp4"},
            {"video": "..\\escape.mp4"},
        ):
            args = dict(
                video="silent.mp4", fps=16, width=848, height=480, frame_limit=5
            )
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                mod.load_frames(None, **args)


if __name__ == "__main__":
    unittest.main()
