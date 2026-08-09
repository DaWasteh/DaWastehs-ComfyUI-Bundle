import importlib.util
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-LiveAvatar" / "nodes.py"
spec = importlib.util.spec_from_file_location("live_avatar_nodes", MODULE_PATH)
nodes = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = nodes
spec.loader.exec_module(nodes)


class LatestSlotTests(unittest.TestCase):
    def test_overwrite_returns_only_latest_frame(self):
        slot = nodes.LatestFrameSlot()
        slot.publish("old")
        slot.publish("latest")
        self.assertEqual(slot.get_after(0, 0.01), ("latest", 2))
        self.assertEqual(slot.latest(), ("latest", 2))

    def test_close_unblocks_waiter(self):
        slot = nodes.LatestFrameSlot()
        result = []
        thread = threading.Thread(target=lambda: result.append(slot.get_after(0, 1)))
        thread.start()
        time.sleep(0.01)
        slot.close()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [None])


class MetricsSafetyTests(unittest.TestCase):
    def test_metrics_are_resettable_and_confined_to_log_root(self):
        environment = __import__("os").environ
        old_root = environment.get("DAWASTEH_LIVE_AVATAR_LOG_ROOT")
        try:
            with tempfile.TemporaryDirectory() as directory:
                environment["DAWASTEH_LIVE_AVATAR_LOG_ROOT"] = directory
                metrics = nodes.LiveAvatarMetrics()
                metrics.produced(now=1.0)
                metrics.reset(now=2.0)
                metrics.produced(now=3.0)
                metrics.publish_json("safe/metrics.json")
                self.assertTrue((Path(directory) / "safe" / "metrics.json").is_file())
                self.assertEqual(metrics.snapshot(now=4.0)["ai_frames"], 1)
                with self.assertRaises(ValueError):
                    metrics.publish_json(Path(directory).parent / "outside.json")
        finally:
            if old_root is None:
                environment.pop("DAWASTEH_LIVE_AVATAR_LOG_ROOT", None)
            else:
                environment["DAWASTEH_LIVE_AVATAR_LOG_ROOT"] = old_root


class ImageUtilityTests(unittest.TestCase):
    def test_centered_square_roi_and_offsets_are_clamped(self):
        frame = np.arange(4 * 8 * 3, dtype=np.uint8).reshape(4, 8, 3)
        centered = nodes.square_roi(frame)
        self.assertTrue(np.array_equal(centered, frame[:, 2:6, :]))
        self.assertTrue(np.array_equal(nodes.square_roi(frame, 100, -100), frame[:, 4:8, :]))

    def test_invalid_roi_and_alpha_semantics(self):
        with self.assertRaises(ValueError):
            nodes.square_roi(np.zeros((3, 3), dtype=np.uint8))
        rgb = np.zeros((2, 2, 3), dtype=np.float32)
        mask = np.array([[0.0, 1.0], [0.25, 0.75]], dtype=np.float32)
        self.assertTrue(np.array_equal(nodes.rgba_from_rgb_and_mask(rgb, mask)[..., 3], 1 - mask))
        with self.assertRaises(ValueError):
            nodes.rgba_from_rgb_and_mask(rgb, np.zeros((1, 1)))

    @unittest.skipUnless(importlib.util.find_spec("torch"), "torch is only present in the ComfyUI environment")
    def test_production_composite_uses_bchw_and_appends_alpha_channel(self):
        import torch

        face_mask = torch.full((1, 3, 2, 2), 0.25)
        warped = torch.ones((1, 3, 2, 2))
        static = torch.full((1, 3, 2, 2), 0.5)
        alpha = torch.full((1, 1, 2, 2), 0.75)
        rgba = nodes.composite_rgba_bchw(face_mask, warped, static, alpha)
        self.assertEqual(tuple(rgba.shape), (1, 4, 2, 2))
        self.assertTrue(torch.allclose(rgba[:, :3], torch.full((1, 3, 2, 2), 0.75)))
        self.assertTrue(torch.allclose(rgba[:, 3:], alpha))
        with self.assertRaises(ValueError):
            nodes.composite_rgba_bchw(face_mask.permute(0, 2, 3, 1), warped, static, alpha)

    @unittest.skipUnless(importlib.util.find_spec("torch"), "torch is only present in the ComfyUI environment")
    def test_persistent_spout_converts_rgb_to_latest_rgba(self):
        import torch

        frames = []
        sink = types.SimpleNamespace(
            metrics=None,
            metrics_path="",
            lock=threading.Lock(),
            publish=lambda frame: frames.append(frame.copy()),
        )
        original = nodes._persistent_spout
        nodes._persistent_spout = lambda name, fps: sink
        try:
            result = nodes.DaWastehPersistentSpout().publish(
                torch.tensor([[[[1.0, 0.5, 0.0], [0.0, 0.0, 1.0]]]]),
                "PersistentTest",
                30,
            )
        finally:
            nodes._persistent_spout = original
        self.assertEqual(result, ())
        self.assertEqual(frames[0].shape, (1, 2, 4))
        self.assertTrue(np.array_equal(frames[0][0, 0], [255, 128, 0, 255]))
        self.assertTrue(np.array_equal(frames[0][0, 1], [0, 0, 255, 255]))

    @unittest.skipUnless(importlib.util.find_spec("torch"), "torch is only present in the ComfyUI environment")
    def test_persistent_spout_preserves_rgba_and_counts_unique_production(self):
        import torch

        frames = []
        metric_calls = []
        metrics = types.SimpleNamespace(
            produced=lambda **kwargs: metric_calls.append(kwargs),
            reset=lambda **kwargs: metric_calls.append({"reset": kwargs}),
            publish_json=lambda path: metric_calls.append({"path": path}),
        )
        sink = types.SimpleNamespace(
            metrics=metrics,
            metrics_path="",
            lock=threading.Lock(),
            publish=lambda frame: frames.append(frame.copy()),
        )
        original = nodes._persistent_spout
        nodes._persistent_spout = lambda name, fps: sink
        try:
            nodes.DaWastehPersistentSpout().publish(
                torch.tensor([[[[1.0, 0.5, 0.0, 0.25]]]]),
                "PersistentMetrics",
                30,
                "metrics.json",
            )
        finally:
            nodes._persistent_spout = original
        self.assertTrue(np.array_equal(frames[0][0, 0], [255, 128, 0, 64]))
        self.assertIn("now", metric_calls[0]["reset"])
        self.assertIn("now", metric_calls[1])
        self.assertEqual(metric_calls[2], {"path": "metrics.json"})

    @unittest.skipUnless(importlib.util.find_spec("torch"), "torch is only present in the ComfyUI environment")
    def test_optional_metrics_failure_does_not_break_spout_publication(self):
        import torch

        frames = []
        produced = []
        metrics = types.SimpleNamespace(
            produced=lambda **kwargs: produced.append(kwargs),
            reset=lambda **kwargs: None,
            publish_json=lambda _path: (_ for _ in ()).throw(OSError("read-only log root")),
        )
        sink = types.SimpleNamespace(
            metrics=metrics,
            metrics_path="",
            lock=threading.Lock(),
            publish=lambda frame: frames.append(frame.copy()),
        )
        original = nodes._persistent_spout
        nodes._persistent_spout = lambda name, fps: sink
        try:
            result = nodes.DaWastehPersistentSpout().publish(
                torch.tensor([[[[0.1, 0.2, 0.3, 1.0]]]]),
                "PersistentMetricsFailure",
                30,
                "safe/metrics.json",
            )
        finally:
            nodes._persistent_spout = original
        self.assertEqual(result, ())
        self.assertEqual(len(frames), 1)
        self.assertEqual(len(produced), 1)


class DependencyTests(unittest.TestCase):
    def test_loaded_liveportrait_module_is_reused(self):
        name = "test_loaded_liveportrait_nodes"
        fake = types.ModuleType(name)
        fake.__file__ = str(Path("X:/custom_nodes/ComfyUI-LivePortraitKJ/nodes.py"))
        fake._transform_img_kornia = object()
        sys.modules[name] = fake
        try:
            self.assertIs(nodes._loaded_liveportrait_nodes(), fake)
        finally:
            sys.modules.pop(name, None)

    @unittest.skipUnless(shutil.which("git"), "git is required for patch applicability test")
    def test_kjnodes_patch_applies_to_expected_source(self):
        patch = ROOT / "tools" / "patches" / "ComfyUI-KJNodes-WebcamCaptureCV2-Windows-Backend.patch"
        fixture = ROOT / "tests" / "fixtures" / "kjnodes_webcam_capture_cv2_original.py"
        source = "\n" * 806 + fixture.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "nodes" / "image_nodes.py"
            target.parent.mkdir(parents=True)
            target.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [shutil.which("git"), "apply", str(patch)],
                cwd=temp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            patched = target.read_text(encoding="utf-8")
            self.assertIn('"backend": (["auto", "DirectShow", "Media Foundation"]', patched)
            self.assertIn("cv2.CAP_DSHOW", patched)
            self.assertIn("self._release_capture()", patched)
            self.assertIn("cv2.resize(frame, (width, height)", patched)


class CachedOpenPoseTests(unittest.TestCase):
    def test_openpose_weights_are_loaded_only_once_per_node_instance(self):
        calls = {"load": 0, "to": 0}

        class FakeDetector:
            @classmethod
            def from_pretrained(cls):
                calls["load"] += 1
                return cls()

            def to(self, device):
                calls["to"] += 1
                self.device = device
                return self

        comfy_package = types.ModuleType("comfy")
        comfy_package.__path__ = []
        model_management = types.ModuleType("comfy.model_management")
        model_management.get_torch_device = lambda: "cuda:0"
        custom_package = types.ModuleType("custom_controlnet_aux")
        custom_package.__path__ = []
        openpose_module = types.ModuleType("custom_controlnet_aux.open_pose")
        openpose_module.OpenposeDetector = FakeDetector
        replacements = {
            "comfy": comfy_package,
            "comfy.model_management": model_management,
            "custom_controlnet_aux": custom_package,
            "custom_controlnet_aux.open_pose": openpose_module,
        }
        previous = {name: sys.modules.get(name) for name in replacements}
        sys.modules.update(replacements)
        try:
            node = nodes.DaWastehCachedOpenPose()
            first = node._get_model()
            second = node._get_model()
        finally:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        self.assertIs(first, second)
        self.assertEqual(calls, {"load": 1, "to": 1})


    @unittest.skipUnless(importlib.util.find_spec("torch"), "torch is only present in the ComfyUI environment")
    def test_diagnostic_openpose_json_is_opt_in_and_compact(self):
        import torch

        fake_utils = types.ModuleType("comfy.utils")
        fake_utils.ProgressBar = lambda total: types.SimpleNamespace(update=lambda amount: None)
        fake_comfy = types.ModuleType("comfy")
        fake_comfy.__path__ = []
        fake_comfy.utils = fake_utils
        previous_comfy = sys.modules.get("comfy")
        previous_utils = sys.modules.get("comfy.utils")
        sys.modules["comfy"] = fake_comfy
        sys.modules["comfy.utils"] = fake_utils
        node = nodes.DaWastehCachedOpenPose()
        pose_image = np.zeros((2, 2, 3), dtype=np.uint8)
        node._get_model = lambda: lambda *args, **kwargs: (pose_image, {"people": [1]})
        try:
            disabled = node.estimate_pose(torch.zeros((1, 2, 2, 3)), diagnostic_json="disable")
            enabled = node.estimate_pose(torch.zeros((1, 2, 2, 3)), diagnostic_json="enable")
        finally:
            if previous_comfy is None:
                sys.modules.pop("comfy", None)
            else:
                sys.modules["comfy"] = previous_comfy
            if previous_utils is None:
                sys.modules.pop("comfy.utils", None)
            else:
                sys.modules["comfy.utils"] = previous_utils
        self.assertNotIn("ui", disabled)
        payload = enabled["ui"]["openpose_json"][0]
        self.assertNotIn("\n", payload)
        self.assertEqual(payload, '[{"people":[1]}]')


class LifecycleTests(unittest.TestCase):
    def tearDown(self):
        nodes._PERSISTENT_SPOUTS.clear()

    def test_failed_persistent_worker_is_recreated_before_publish(self):
        created = []
        class FakeWorker:
            def __init__(self, slot, name, fps, metrics=None): self.slot, self.delay, self.live, self.metrics = slot, 1 / fps, False, metrics; created.append(self)
            def start(self): self.live = True
            def healthy(self): return self.live
            def stop(self): self.live = False; self.slot.close(); return True
        original = nodes.SpoutWorker
        nodes.SpoutWorker = FakeWorker
        try:
            first = nodes._persistent_spout("recover", 30)
            first.fail(RuntimeError("injected"))
            second = nodes._persistent_spout("recover", 30)
            self.assertIsNot(first, second)
            self.assertEqual(len(created), 2)
            self.assertTrue(created[-1].healthy())
        finally:
            nodes.SpoutWorker = original

    def test_hung_persistent_worker_blocks_overlapping_replacement(self):
        slot = nodes.LatestFrameSlot()
        class HungWorker:
            delay = 1 / 30
            def healthy(self): return True
            def stop(self): return False
        worker = HungWorker()
        nodes._PERSISTENT_SPOUTS["hung"] = (slot, worker)
        with self.assertRaisesRegex(RuntimeError, "refusing an overlapping replacement"):
            nodes._persistent_spout("hung", 60)
        self.assertIs(nodes._PERSISTENT_SPOUTS["hung"][1], worker)

    def test_workers_can_stop_before_start(self):
        capture = nodes.CaptureWorker(nodes.LatestFrameSlot(), 1, 256, 256, True, 0, 0, False)
        spout = nodes.SpoutWorker(nodes.LatestFrameSlot(), "test", 30)
        self.assertTrue(capture.stop(0.01))
        self.assertTrue(spout.stop(0.01))

    def test_capture_worker_releases_camera(self):
        released = []

        class FakeCap:
            def isOpened(self):
                return True

            def set(self, *args):
                return True

            def read(self):
                return False, None

            def release(self):
                released.append(True)

        fake_cv2 = types.SimpleNamespace(
            VideoCapture=lambda index: FakeCap(),
            CAP_PROP_FRAME_WIDTH=1,
            CAP_PROP_FRAME_HEIGHT=2,
            CAP_PROP_BUFFERSIZE=3,
            CAP_PROP_READ_TIMEOUT_MSEC=4,
            INTER_AREA=5,
            flip=lambda image, axis: image,
            resize=lambda image, size, interpolation: image,
        )
        old = sys.modules.get("cv2")
        sys.modules["cv2"] = fake_cv2
        try:
            worker = nodes.CaptureWorker(nodes.LatestFrameSlot(), 1, 256, 256, True, 0, 0, False)
            worker.start()
            worker.thread.join(1)
            self.assertTrue(released)
            with self.assertRaises(RuntimeError):
                worker.slot.get_after(0, 0.01)
            self.assertTrue(worker.stop(0.01))
        finally:
            if old is None:
                sys.modules.pop("cv2", None)
            else:
                sys.modules["cv2"] = old

    def test_spout_worker_releases_sender_and_paces_repeated_frames(self):
        released = []
        send_times = []

        class FakeSender:
            def setSenderName(self, name):
                pass

            def sendImage(self, *args):
                send_times.append(time.monotonic())

            def setFrameSync(self, name):
                pass

            def releaseSender(self):
                released.append(True)

        old_platform = sys.platform
        old_spout = sys.modules.get("SpoutGL")
        old_opengl = sys.modules.get("OpenGL")
        sys.platform = "win32"
        sys.modules["SpoutGL"] = types.SimpleNamespace(SpoutSender=FakeSender)
        sys.modules["OpenGL"] = types.SimpleNamespace(GL=types.SimpleNamespace(GL_RGBA=1))
        try:
            slot = nodes.LatestFrameSlot()
            slot.metrics_path = "safe/metrics.json"
            slot.publish(np.zeros((2, 2, 4), dtype=np.uint8))
            metrics = types.SimpleNamespace(
                presented=lambda *args: None,
                publish_json=lambda _path: (_ for _ in ()).throw(OSError("read-only log root")),
            )
            worker = nodes.SpoutWorker(slot, "test", 20, metrics)
            worker.start()
            time.sleep(0.13)
            self.assertTrue(worker.healthy())
            self.assertTrue(worker.stop())
            self.assertTrue(released)
            self.assertGreaterEqual(len(send_times), 2)
            self.assertLessEqual(len(send_times), 4)
            if len(send_times) > 1:
                self.assertGreaterEqual(min(b - a for a, b in zip(send_times, send_times[1:])), 0.035)
        finally:
            sys.platform = old_platform
            if old_spout is None:
                sys.modules.pop("SpoutGL", None)
            else:
                sys.modules["SpoutGL"] = old_spout
            if old_opengl is None:
                sys.modules.pop("OpenGL", None)
            else:
                sys.modules["OpenGL"] = old_opengl

    def test_config_restoration_removes_temporary_attributes(self):
        cfg = types.SimpleNamespace(flag_stitching=False, flag_lip_zero=False)
        saved = dict(vars(cfg))
        cfg.flag_stitching = True
        cfg.extra = 1
        nodes.DaWastehContinuousLiveAvatar._restore_cfg(cfg, saved)
        self.assertFalse(cfg.flag_stitching)
        self.assertFalse(cfg.flag_lip_zero)
        self.assertFalse(hasattr(cfg, "extra"))

    @unittest.skipUnless(importlib.util.find_spec("torch"), "torch is only present in the ComfyUI environment")
    def test_partial_start_failure_stops_both_workers_and_restores_cfg(self):
        import torch

        events = []

        class FakeCapture:
            def __init__(self, *args):
                pass

            def start(self):
                events.append("capture-start")

            def stop(self):
                events.append("capture-stop")
                return True

        class FakeSpout:
            def __init__(self, *args):
                pass

            def start(self):
                events.append("spout-start")
                raise RuntimeError("spout start failed")

            def stop(self):
                events.append("spout-stop")
                return True

        cfg = types.SimpleNamespace(
            flag_stitching=False,
            flag_lip_zero=False,
            lip_zero_threshold=0.02,
            flag_eye_retargeting=True,
            eyes_retargeting_multiplier=2.0,
            flag_lip_retargeting=True,
            lip_retargeting_multiplier=2.0,
            flag_use_half_precision=False,
        )
        pipeline = types.SimpleNamespace(live_portrait_wrapper=types.SimpleNamespace(cfg=cfg))
        crop_info = {"crop_info_list": [{"M_c2o": np.eye(3, dtype=np.float32)}]}
        fake_kj = types.SimpleNamespace(
            script_directory=".",
            _transform_img_kornia=lambda image, matrix, size, device: image.permute(0, 3, 1, 2),
        )
        fake_cv2 = types.SimpleNamespace(
            IMREAD_COLOR=1,
            imread=lambda path, mode: np.ones((2, 2, 3), dtype=np.uint8) * 255,
        )
        fake_mm = types.ModuleType("comfy.model_management")
        fake_mm.get_torch_device = lambda: torch.device("cpu")
        fake_mm.throw_exception_if_processing_interrupted = lambda: None
        fake_comfy = types.ModuleType("comfy")
        fake_comfy.__path__ = []
        fake_comfy.model_management = fake_mm

        originals = {
            "capture": nodes.CaptureWorker,
            "spout": nodes.SpoutWorker,
            "loader": nodes._loaded_liveportrait_nodes,
            "platform": sys.platform,
            "cv2": sys.modules.get("cv2"),
            "comfy": sys.modules.get("comfy"),
            "mm": sys.modules.get("comfy.model_management"),
        }
        nodes.CaptureWorker = FakeCapture
        nodes.SpoutWorker = FakeSpout
        nodes._loaded_liveportrait_nodes = lambda: fake_kj
        sys.platform = "win32"
        sys.modules["cv2"] = fake_cv2
        sys.modules["comfy"] = fake_comfy
        sys.modules["comfy.model_management"] = fake_mm
        try:
            with self.assertRaisesRegex(RuntimeError, "spout start failed"):
                nodes.DaWastehContinuousLiveAvatar().run(
                    pipeline,
                    crop_info,
                    torch.zeros((1, 2, 2, 3)),
                    torch.zeros((1, 2, 2)),
                    "test",
                    30,
                    1,
                    960,
                    540,
                    True,
                    0,
                    0,
                    True,
                    0.75,
                    True,
                    False,
                    0.03,
                    1,
                )
            self.assertEqual(events, ["capture-start", "spout-start", "capture-stop", "spout-stop"])
            self.assertFalse(cfg.flag_stitching)
            self.assertTrue(cfg.flag_eye_retargeting)
            self.assertEqual(cfg.eyes_retargeting_multiplier, 2.0)
        finally:
            nodes.CaptureWorker = originals["capture"]
            nodes.SpoutWorker = originals["spout"]
            nodes._loaded_liveportrait_nodes = originals["loader"]
            sys.platform = originals["platform"]
            for key, value in (("cv2", originals["cv2"]), ("comfy", originals["comfy"]), ("comfy.model_management", originals["mm"])):
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value

    def test_inference_loop_has_no_per_frame_cache_flush(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        loop = source[source.index("while max_frames") : source.index("finally:", source.index("while max_frames"))]
        self.assertNotIn("soft_empty_cache", loop)
        self.assertNotIn("gc.collect", loop)


if __name__ == "__main__":
    unittest.main()
