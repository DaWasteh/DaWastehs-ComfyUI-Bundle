from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

import numpy as np

HAS_CV2 = importlib.util.find_spec("cv2") is not None
ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-LiveAvatar" / "face_swap.py"
spec = importlib.util.spec_from_file_location("live_avatar_face_swap", MODULE_PATH)
face_swap = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = face_swap
spec.loader.exec_module(face_swap)


def five_points(center=(320.0, 240.0), scale=100.0):
    template = face_swap.WARP_TEMPLATES["arcface_128"]
    return (template - template.mean(axis=0)) * scale + np.array(center, dtype=np.float32)


@unittest.skipUnless(HAS_CV2, "OpenCV is only installed in the ComfyUI venv")
class GeometryTests(unittest.TestCase):
    def test_affine_alignment_and_paste_back_roundtrip(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :, 1] = 90
        crop, matrix = face_swap.warp_face(frame, five_points(), "arcface_128", 128)
        self.assertEqual(crop.shape, (128, 128, 3))
        self.assertEqual(matrix.shape, (2, 3))
        red = np.zeros_like(crop)
        red[:, :, 2] = 255
        mask = face_swap.create_box_mask(128, 0.0)
        pasted = face_swap.paste_back(frame, red, mask, matrix)
        self.assertEqual(pasted.shape, frame.shape)
        self.assertGreater(int(pasted[240, 320, 2]), 200)
        self.assertEqual(int(pasted[10, 10, 2]), 0)
        self.assertEqual(int(pasted[10, 10, 1]), 90)

    def test_box_mask_is_soft_and_bounded(self):
        mask = face_swap.create_box_mask(256, 0.3, (0, 0, 0, 0))
        self.assertEqual(mask.shape, (256, 256))
        self.assertAlmostEqual(float(mask[128, 128]), 1.0, places=4)
        self.assertLess(float(mask[0, 128]), 0.1)
        self.assertTrue(0.0 <= mask.min() <= mask.max() <= 1.0)

    def test_invalid_landmarks_are_rejected(self):
        with self.assertRaises(ValueError):
            face_swap.estimate_affine(np.zeros((4, 2), dtype=np.float32), "arcface_128", 128)


class OnnxReaderTests(unittest.TestCase):
    def test_reads_named_initializer_from_minimal_protobuf(self):
        import struct
        import tempfile

        def varint(value):
            out = bytearray()
            while True:
                byte = value & 0x7F
                value >>= 7
                if value:
                    out.append(byte | 0x80)
                else:
                    out.append(byte)
                    return bytes(out)

        def field(number, payload):
            return varint((number << 3) | 2) + varint(len(payload)) + payload

        values = np.arange(6, dtype=np.float32).reshape(2, 3)
        tensor = varint((1 << 3) | 0) + varint(2) + varint((1 << 3) | 0) + varint(3)
        tensor += varint((2 << 3) | 0) + varint(1) + field(8, b"emap") + field(9, values.tobytes())
        other = varint((2 << 3) | 0) + varint(1) + field(8, b"other") + field(9, struct.pack("<f", 1.0)) + varint((1 << 3) | 0) + varint(1)
        graph = field(5, other) + field(1, b"node-bytes") + field(5, tensor)
        model = varint((1 << 3) | 0) + varint(9) + field(7, graph)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mini.onnx"
            path.write_bytes(model)
            read = face_swap.read_onnx_initializer(path, "emap")
            self.assertTrue(np.array_equal(read, values))
            with self.assertRaises(RuntimeError):
                face_swap.read_onnx_initializer(path, "missing")


class NormalisationTests(unittest.TestCase):
    def test_inswapper_and_hyperswap_normalisation_roundtrip(self):
        crop = np.random.default_rng(1).integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
        for name in ("inswapper_128", "hyperswap_1a_256"):
            spec_ = face_swap.SWAPPERS[name]
            prepared = face_swap.prepare_swapper_input(crop, spec_)
            self.assertEqual(prepared.shape, (1, 3, 32, 32))
            self.assertEqual(prepared.dtype, np.float32)
            restored = face_swap.normalize_swapper_output(prepared[0], spec_)
            self.assertTrue(np.array_equal(restored, crop), name)

    def test_enhancer_normalisation_roundtrip(self):
        crop = np.random.default_rng(2).integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
        restored = face_swap.normalize_enhancer_output(face_swap.prepare_enhancer_input(crop)[0])
        self.assertTrue(np.array_equal(restored, crop))

    def test_source_embedding_uses_emap_only_for_inswapper(self):
        embedding = np.arange(512, dtype=np.float32) + 1.0
        emap = np.eye(512, dtype=np.float32) * 2.0
        inswapper = face_swap.source_embedding_for(face_swap.SWAPPERS["inswapper_128"], embedding, emap)
        hyperswap = face_swap.source_embedding_for(face_swap.SWAPPERS["hyperswap_1a_256"], embedding, None)
        self.assertEqual(inswapper.shape, (1, 512))
        self.assertAlmostEqual(float(np.linalg.norm(hyperswap)), 1.0, places=5)
        self.assertAlmostEqual(float(np.linalg.norm(inswapper)), 2.0, places=4)
        with self.assertRaises(ValueError):
            face_swap.source_embedding_for(face_swap.SWAPPERS["inswapper_128"], embedding, None)
        with self.assertRaises(ValueError):
            face_swap.source_embedding_for(face_swap.SWAPPERS["hyperswap_1a_256"], np.zeros(512), None)

    def test_identity_blend_and_average(self):
        source = np.ones((1, 4), dtype=np.float32)
        target = np.array([1, 0, 0, 0], dtype=np.float32)
        self.assertTrue(np.array_equal(face_swap.blend_identity(source, target, 1.0), source))
        blended = face_swap.blend_identity(source, target, 0.5)
        self.assertAlmostEqual(float(blended[0, 0]), 1.0)
        self.assertAlmostEqual(float(blended[0, 1]), 0.5)
        self.assertTrue(np.array_equal(face_swap.average_embedding([np.zeros(3), np.ones(3) * 2]), np.ones(3)))
        with self.assertRaises(ValueError):
            face_swap.average_embedding([])


class DetectorMathTests(unittest.TestCase):
    def test_distance_decoding_and_nms(self):
        points = np.array([[10.0, 10.0], [50.0, 50.0]], dtype=np.float32)
        boxes = face_swap.distance2bbox(points, np.array([[1, 2, 3, 4], [5, 5, 5, 5]], dtype=np.float32))
        self.assertTrue(np.array_equal(boxes, np.array([[9, 8, 13, 14], [45, 45, 55, 55]], dtype=np.float32)))
        kps = face_swap.distance2kps(points[:1], np.arange(10, dtype=np.float32)[None])
        self.assertEqual(kps.shape, (1, 10))
        self.assertEqual(kps[0, 0], 10.0)
        self.assertEqual(kps[0, 1], 11.0)
        dets = np.array([[0, 0, 10, 10, 0.9], [1, 1, 11, 11, 0.8], [50, 50, 60, 60, 0.7]], dtype=np.float32)
        self.assertEqual(face_swap.nms(dets, 0.4), [0, 2])

    @unittest.skipUnless(HAS_CV2, "OpenCV is only installed in the ComfyUI venv")
    def test_scrfd_decodes_a_synthetic_response(self):
        det_size = 32
        strides = [8, 16, 32]

        class Session:
            def get_inputs(self):
                return [types.SimpleNamespace(name="input.1", shape=[1, 3, "?", "?"])]

            def get_outputs(self):
                return [types.SimpleNamespace(name=f"o{i}") for i in range(9)]

            def run(self, names, feeds):
                outs = []
                for stride in strides:
                    n = (det_size // stride) ** 2 * 2
                    scores = np.zeros((n, 1), dtype=np.float32)
                    scores[0] = 0.9 if stride == 8 else 0.0
                    outs.append(scores)
                for stride in strides:
                    n = (det_size // stride) ** 2 * 2
                    outs.append(np.ones((n, 4), dtype=np.float32))
                for stride in strides:
                    n = (det_size // stride) ** 2 * 2
                    outs.append(np.zeros((n, 10), dtype=np.float32))
                return outs

        detector = face_swap.ScrfdDetector(Session(), det_size, 0.5)
        boxes, kpss = detector.detect(np.zeros((64, 64, 3), dtype=np.uint8))
        self.assertEqual(boxes.shape, (1, 5))
        self.assertEqual(kpss.shape, (1, 5, 2))
        self.assertTrue(np.allclose(boxes[0, :4], [-16, -16, 16, 16]))
        self.assertAlmostEqual(float(boxes[0, 4]), 0.9, places=5)


class TrackingTests(unittest.TestCase):
    def test_largest_face_prefers_tracked_neighbour(self):
        boxes = np.array([[0, 0, 100, 100, 0.9], [300, 300, 340, 340, 0.9]], dtype=np.float32)
        kpss = np.zeros((2, 5, 2), dtype=np.float32)
        self.assertEqual(face_swap.largest_face(boxes, kpss, None), 0)
        self.assertEqual(face_swap.largest_face(boxes, kpss, np.array([320.0, 320.0])), 1)
        self.assertIsNone(face_swap.largest_face(np.zeros((0, 5)), None, None))

    def test_landmark_smoothing_resets_on_large_jumps(self):
        previous = five_points((100.0, 100.0))
        near = five_points((104.0, 100.0))
        smoothed = face_swap.smooth_landmarks(previous, near, 0.5)
        self.assertTrue(np.allclose(smoothed, (previous + near) / 2))
        far = five_points((400.0, 100.0))
        self.assertTrue(np.array_equal(face_swap.smooth_landmarks(previous, far, 0.5), far))
        self.assertTrue(np.array_equal(face_swap.smooth_landmarks(None, near, 0.5), near))


class FakeSession:
    def __init__(self, input_names, output_shape_from_target=True, mode="echo"):
        self._inputs = [types.SimpleNamespace(name=name) for name in input_names]
        self._outputs = [types.SimpleNamespace(name="output")]
        self.calls = 0
        self.mode = mode
        self.threads: set[str] = set()

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def run(self, _outputs, feeds):
        import threading

        self.calls += 1
        self.threads.add(threading.current_thread().name)
        image = [value for key, value in feeds.items() if key in ("target", "input")][0]
        if self.mode == "parser":  # NCHW -> 19 class logits, everything "skin" except the top rows (hair)
            size = image.shape[2]
            logits = np.zeros((1, 19, size, size), dtype=np.float32)
            logits[0, 1] = 1.0
            logits[0, 17, : size // 4] = 2.0
            return [logits]
        if self.mode == "occluder":  # NHWC -> face everywhere except the left quarter (a "hand")
            size = image.shape[1]
            mask = np.ones((1, size, size, 1), dtype=np.float32)
            mask[:, :, : size // 4] = 0.0
            return [mask]
        if self.mode == "matting":  # person = right half
            size = image.shape[2]
            alpha = np.zeros((1, 1, size, size), dtype=np.float32)
            alpha[:, :, :, size // 2 :] = 1.0
            return [alpha]
        return [np.clip(image, -1, 1)]


@unittest.skipUnless(HAS_CV2, "OpenCV is only installed in the ComfyUI venv")
class MaskHelperTests(unittest.TestCase):
    def test_scaled_template_widens_the_crop_without_moving_its_centre(self):
        base = face_swap.WARP_TEMPLATES["arcface_128"]
        wide = face_swap.scaled_template("arcface_128", 0.8)
        self.assertTrue(np.allclose(wide.mean(axis=0), base.mean(axis=0)))
        self.assertLess(float(np.linalg.norm(wide[1] - wide[0])), float(np.linalg.norm(base[1] - base[0])))
        self.assertTrue(np.array_equal(face_swap.scaled_template("arcface_128", 1.0), base))

    def test_region_and_beard_masks_from_a_class_map(self):
        size = 64
        classes = np.full((size, size), 1, dtype=np.int16)  # skin
        classes[:8] = 17  # hair on top
        classes[40:44, 28:36] = 11  # mouth interior
        template = face_swap.scaled_template("arcface_128", 1.0) * size
        region = face_swap.region_mask_from_classes(classes, face_swap.DEFAULT_REGIONS, size)
        self.assertEqual(region.shape, (size, size))
        self.assertLess(float(region[2, 32]), 0.5)
        self.assertGreater(float(region[32, 32]), 0.9)
        without_mouth = face_swap.region_mask_from_classes(classes, tuple(r for r in face_swap.DEFAULT_REGIONS if r != "mouth"), size)
        self.assertLess(float(without_mouth[42, 32]), float(region[42, 32]))
        beard = face_swap.beard_mask_from_classes(classes, template, size, None, 1.0)
        self.assertEqual(beard.shape, (size, size))
        self.assertEqual(float(beard[10, 32]), 0.0)  # forehead is never beard
        self.assertEqual(float(beard[60, 32]), 1.0)  # chin zone is
        self.assertEqual(float(beard[42, 32]), 0.0)  # mouth interior is kept
        self.assertFalse(face_swap.beard_mask_from_classes(classes, template, size, None, 0.0).any())
        chin_only = face_swap.beard_mask_from_classes(classes, template, size, None, 0.6)
        self.assertLessEqual(float(chin_only.sum()), float(beard.sum()))

    def test_shave_and_colour_match_keep_shape_and_change_only_the_zone(self):
        rng = np.random.default_rng(3)
        crop = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
        zone = np.zeros((64, 64), dtype=np.float32)
        zone[48:, 16:48] = 1.0
        shaved = face_swap.shave_crop(crop, zone, "skin", np.array([120.0, 140.0, 180.0], dtype=np.float32))
        self.assertEqual(shaved.shape, crop.shape)
        self.assertTrue(np.array_equal(shaved[:32], crop[:32]))
        self.assertGreater(float(np.abs(shaved[56, 32].astype(int) - crop[56, 32].astype(int)).sum()), 0.0)
        self.assertIs(face_swap.shave_crop(crop, np.zeros((64, 64), dtype=np.float32), "skin"), crop)
        reference = np.full((64, 64, 3), 200, dtype=np.uint8)
        matched = face_swap.match_color(crop, reference, np.ones((64, 64), dtype=np.float32), 1.0)
        self.assertGreater(float(matched.mean()), float(crop.mean()))
        self.assertIs(face_swap.match_color(crop, reference, np.ones((64, 64), dtype=np.float32), 0.0), crop)

    def test_occlusion_extension_and_background_composite(self):
        size = 64
        occlusion = np.zeros((size, size), dtype=np.float32)
        occlusion[:40] = 1.0  # face oval ends at row 40
        zone = np.zeros((size, size), dtype=np.float32)
        zone[36:56] = 1.0  # beard zone below the chin
        grown = face_swap.extend_occlusion_downward(occlusion, zone, size)
        self.assertEqual(float(grown[44, 32]), 1.0)
        self.assertEqual(float(grown[62, 32]), 0.0)
        frame = np.full((8, 8, 3), 200, dtype=np.uint8)
        background = np.zeros((8, 8, 3), dtype=np.uint8)
        alpha = np.zeros((8, 8), dtype=np.float32)
        alpha[:, 4:] = 1.0
        mixed = face_swap.composite_background(frame, alpha, background)
        self.assertEqual(int(mixed[0, 0, 0]), 0)
        self.assertEqual(int(mixed[0, 7, 0]), 200)
        self.assertEqual(face_swap._resize_background(None, frame, "green").tolist()[0][0], [0, 255, 0])
        with self.assertRaises(RuntimeError):
            face_swap._resize_background(None, frame, "image")

    def test_v110_identity_boost_temporal_blend_lookahead_and_dfm_helpers(self):
        source = np.ones((1, 4), dtype=np.float32)
        live = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        boosted = face_swap.boost_identity(source, live, 1.0)
        self.assertAlmostEqual(float(boosted[0, 0]), 1.0, places=5)
        self.assertAlmostEqual(float(boosted[0, 1]), 1.35, places=5)
        self.assertIs(face_swap.boost_identity(source, live, 0.0), source)
        previous = np.zeros((4, 4, 3), dtype=np.uint8)
        current = np.full((4, 4, 3), 200, dtype=np.uint8)
        self.assertEqual(int(face_swap.temporal_blend(previous, current, 0.5)[0, 0, 0]), 100)
        self.assertIs(face_swap.temporal_blend(None, current, 0.5), current)
        buffer = face_swap.LookaheadBuffer(2)
        base = five_points()
        self.assertIsNone(buffer.push("a", 1, base))
        self.assertIsNone(buffer.push("b", 2, base + 1.0))
        captured, frame, landmarks = buffer.push("c", 3, base + 2.0)
        self.assertEqual((captured, frame), ("a", 1))
        self.assertTrue(np.allclose(landmarks, base + 1.0))
        jump = buffer.push("d", 4, base + 500.0)  # frame b with a far-away future frame: ignored
        self.assertEqual(jump[0], "b")
        self.assertTrue(np.allclose(jump[2], base + 1.5))
        passthrough = face_swap.LookaheadBuffer(0).push("x", 9, None)
        self.assertEqual(passthrough, ("x", 9, None))
        crop = np.full((16, 16, 3), 120, dtype=np.uint8)
        blob = face_swap.prepare_dfm_input(crop)
        self.assertEqual(blob.shape, (1, 16, 16, 3))
        inner = np.pad(np.ones((8, 8), dtype=np.float32), 4)
        mask = face_swap.dfm_mask(inner.reshape(16, 16, 1), inner.reshape(1, 16, 16), 16)
        self.assertEqual(mask.shape, (16, 16))
        self.assertLess(float(mask[0, 0]), float(mask[8, 8]))
        classes = np.full((32, 32), 1, dtype=np.int16)
        classes[20:24] = 12  # upper lip
        classes[24:28] = 11  # mouth interior
        band = face_swap.moustache_band(classes)
        self.assertEqual(float(band[21, 5]), 1.0)
        self.assertEqual(float(band[25, 5]), 0.0)
        zone = np.zeros((16, 16), dtype=np.float32)
        zone[8:] = 1.0
        fixed = face_swap.fix_zone_color(np.full((16, 16, 3), 60, dtype=np.uint8), np.full((16, 16, 3), 160, dtype=np.uint8), zone, 1.0)
        self.assertGreater(int(fixed[12, 8, 0]), 60)
        self.assertEqual(face_swap.resolve_swapper("dfm/anything").kind, "dfm")
        self.assertEqual(face_swap.dfm_spec("dfm/anything").file_name, "anything.dfm")
        inputs = face_swap.DaWastehLiveFaceSwap.INPUT_TYPES()["required"]
        self.assertEqual(inputs["lookahead_frames"][1]["default"], 2)
        self.assertEqual(inputs["identity_strength"][1]["default"], 0.85)
        self.assertEqual(inputs["glasses"][0], face_swap.GLASSES_MODES)

    def test_parser_and_matting_preprocessing(self):
        crop = np.full((32, 32, 3), 128, dtype=np.uint8)
        blob = face_swap.prepare_parser_input(crop, 64)
        self.assertEqual(blob.shape, (1, 3, 64, 64))
        self.assertAlmostEqual(float(blob[0, 0, 0, 0]), (128 / 255 - 0.485) / 0.229, places=4)
        matte = face_swap.prepare_matting_input(crop, 16)
        self.assertEqual(matte.shape, (1, 3, 16, 16))
        self.assertAlmostEqual(float(matte[0, 1, 0, 0]), (128 - 127.5) / 127.5, places=4)
        occ = face_swap.prepare_occluder_input(crop, 16)
        self.assertEqual(occ.shape, (1, 16, 16, 3))


class FakeDetector:
    def __init__(self, boxes, kpss):
        self.boxes = boxes
        self.kpss = kpss

    def detect(self, _frame, max_num=0, metric="default"):
        return self.boxes, self.kpss


class FakeEmbedder:
    def __init__(self, embedding):
        self.embedding = embedding
        self.calls = 0

    def embed(self, _frame, _landmarks):
        self.calls += 1
        return self.embedding


class EngineTests(unittest.TestCase):
    def _root(self, tmp: Path, with_enhancer=True):
        (tmp / "insightface" / "models" / "buffalo_l").mkdir(parents=True)
        for name in face_swap.DETECTOR_FILES:
            (tmp / "insightface" / "models" / "buffalo_l" / name).write_bytes(b"x")
        (tmp / "insightface" / "hyperswap_1a_256.onnx").write_bytes(b"x")
        (tmp / "facerestore_models").mkdir()
        if with_enhancer:
            (tmp / "facerestore_models" / "gpen_bfr_256.onnx").write_bytes(b"x")
        return tmp

    def _engine(self, root, boxes, kpss, enhancer="gpen_bfr_256", **extra):
        detector = FakeDetector(boxes, kpss)
        embedder = FakeEmbedder(np.linspace(0.1, 1.0, 512, dtype=np.float32))
        sessions = {}

        def factory(path):
            names = ("target", "source") if "hyperswap" in path.name else ("input",)
            mode = "parser" if "bisenet" in path.name else "occluder" if "xseg" in path.name else "matting" if "modnet" in path.name else "echo"
            sessions[path.name] = FakeSession(names, mode=mode)
            return sessions[path.name]

        engine = face_swap.FaceSwapEngine(
            root, "hyperswap_1a_256", enhancer, 1, 320,
            session_factory=factory, detector_factory=lambda: detector, embedder_factory=lambda: embedder, **extra,
        )
        return engine, sessions

    def _root_with_masks(self, tmp: Path):
        root = self._root(tmp)
        (root / "face_parsing").mkdir()
        (root / "face_parsing" / "xseg_3.onnx").write_bytes(b"x")
        (root / "face_parsing" / "bisenet_resnet_34.onnx").write_bytes(b"x")
        (root / "background_removal").mkdir()
        (root / "background_removal" / "modnet.onnx").write_bytes(b"x")
        return root

    @unittest.skipUnless(HAS_CV2, "OpenCV is only installed in the ComfyUI venv")
    def test_v100_pipeline_runs_masks_on_the_worker_and_keeps_the_alpha(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._root_with_masks(Path(tmp))
            self.assertEqual(face_swap.available_mask_models(face_swap.OCCLUDERS, face_swap.MASK_SUBDIR, root), ["xseg_3"])
            self.assertEqual(face_swap.available_mask_models(face_swap.MATTERS, face_swap.MATTING_SUBDIR, root), ["modnet"])
            frame = np.full((480, 640, 3), 90, dtype=np.uint8)
            boxes = np.array([[270, 190, 370, 290, 0.95]], dtype=np.float32)
            engine, sessions = self._engine(root, boxes, five_points()[None], occluder="xseg_3", parser="bisenet_resnet_34", matter="modnet", mask_device_id=0)
            identity = face_swap.FaceIdentity(np.ones((1, 512), dtype=np.float32) / np.sqrt(512), 1, "abc")
            regions = face_swap._regions_for(True)
            timing = face_swap.SwapTimings()
            out = engine.swap_frame(frame, identity, crop_scale=0.8, color_match=0.5, regions=regions, shave="skin", matte=True, timings=timing)
            out2 = engine.swap_frame(frame, identity, crop_scale=0.8, color_match=0.5, regions=regions, shave="skin", matte=True, timings=timing)
            self.assertEqual(out.shape, frame.shape)
            self.assertEqual(out2.shape, frame.shape)
            self.assertTrue(timing.face_found)
            self.assertEqual(sessions["bisenet_resnet_34.onnx"].calls, 2)
            self.assertEqual(sessions["xseg_3.onnx"].calls, 2)
            self.assertEqual(sessions["modnet.onnx"].calls, 2)
            self.assertIsNotNone(engine.last_alpha)
            self.assertEqual(engine.last_alpha.shape, frame.shape[:2])
            self.assertTrue(engine.parallel_masks)
            self.assertTrue(any(name.startswith("DaWastehFaceSwapMasks") for name in sessions["bisenet_resnet_34.onnx"].threads))
            self.assertEqual(sessions["xseg_3.onnx"].threads, {"MainThread"})
            self.assertIsNotNone(engine._previous_branch.beard)
            # without a face the matte is still produced (person may be turned away)
            engine_none, _ = self._engine(root, np.zeros((0, 5), dtype=np.float32), None, occluder="xseg_3", parser="bisenet_resnet_34", matter="modnet", mask_device_id=0)
            self.assertIs(engine_none.swap_frame(frame, identity, matte=True), frame)
            self.assertIsNotNone(engine_none.last_alpha)
            # same adapter for masks and swapper -> no worker thread (DirectML is not thread-safe per adapter)
            engine_same, _ = self._engine(root, boxes, five_points()[None], occluder="xseg_3", parser="bisenet_resnet_34", mask_device_id=1)
            engine_same.load()
            self.assertFalse(engine_same.parallel_masks)
            self.assertIsNone(engine_same._pool)
            engine_same.swap_frame(frame, identity, regions=regions, shave="skin")

    def test_discovery_reports_installed_models_only(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(Path(tmp))
            self.assertEqual(face_swap.available_swappers(root), ["hyperswap_1a_256"])
            self.assertEqual(face_swap.available_enhancers(root), ["gpen_bfr_256"])
            self.assertTrue(face_swap.detector_ready(root))

    @unittest.skipUnless(HAS_CV2, "OpenCV is only installed in the ComfyUI venv")
    def test_swap_frame_passthrough_without_face_and_swaps_with_face(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(Path(tmp))
            frame = np.full((480, 640, 3), 40, dtype=np.uint8)
            engine, sessions = self._engine(root, np.zeros((0, 5), dtype=np.float32), None)
            identity = face_swap.FaceIdentity(np.ones((1, 512), dtype=np.float32) / np.sqrt(512), 1, "abc")
            timing = face_swap.SwapTimings()
            out = engine.swap_frame(frame, identity, timings=timing)
            self.assertIs(out, frame)
            self.assertFalse(timing.face_found)
            self.assertEqual(sessions["hyperswap_1a_256.onnx"].calls, 0)

            boxes = np.array([[270, 190, 370, 290, 0.95]], dtype=np.float32)
            kpss = five_points()[None]
            engine2, sessions2 = self._engine(root, boxes, kpss)
            timing2 = face_swap.SwapTimings()
            out2 = engine2.swap_frame(frame, identity, timings=timing2, enhancer_blend=0.5)
            self.assertTrue(timing2.face_found)
            self.assertEqual(out2.shape, frame.shape)
            self.assertEqual(sessions2["hyperswap_1a_256.onnx"].calls, 1)
            self.assertEqual(sessions2["gpen_bfr_256.onnx"].calls, 1)
            self.assertGreater(timing2.swap_ms, 0.0)
            # identity extraction averages faces and normalises hyperswap embeddings
            ident = engine2.identity_from_images([frame, frame])
            self.assertEqual(ident.source_count, 2)
            self.assertAlmostEqual(float(np.linalg.norm(ident.embedding)), 1.0, places=5)

    def test_missing_models_fail_closed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = face_swap.FaceSwapEngine(root, "inswapper_128", None, 0, 320, session_factory=lambda p: None, detector_factory=lambda: None, embedder_factory=lambda: None)
            with self.assertRaises(RuntimeError):
                engine.load()

    def test_node_registration_and_tensor_helpers(self):
        self.assertEqual(
            set(face_swap.NODE_CLASS_MAPPINGS),
            {
                "DaWastehFaceSwapModelLoader", "DaWastehFaceSwapIdentity", "DaWastehFaceSwapIdentityFromFolder",
                "DaWastehWebcamSnapshot", "DaWastehFaceSwapImage", "DaWastehLiveFaceSwap",
            },
        )
        self.assertEqual(set(face_swap.NODE_DISPLAY_NAME_MAPPINGS), set(face_swap.NODE_CLASS_MAPPINGS))
        live_inputs = face_swap.DaWastehLiveFaceSwap.INPUT_TYPES()["required"]
        self.assertEqual(live_inputs["cam_index"][1]["default"], 2)
        self.assertEqual(live_inputs["capture_backend"][1]["default"], "DirectShow")
        self.assertEqual(live_inputs["crop_scale"][1]["default"], 0.8)
        self.assertEqual(live_inputs["shave"][1]["default"], "skin")
        self.assertTrue(live_inputs["keep_mouth"][1]["default"])
        self.assertEqual(live_inputs["background_mode"][0], face_swap.BACKGROUND_MODES)
        self.assertIn("background", face_swap.DaWastehLiveFaceSwap.INPUT_TYPES()["optional"])
        self.assertTrue(face_swap.DaWastehLiveFaceSwap.OUTPUT_NODE)
        from unittest import mock

        with mock.patch.object(face_swap, "models_root", return_value=Path("does-not-exist")):
            loader_inputs = face_swap.DaWastehFaceSwapModelLoader.INPUT_TYPES()["required"]
        self.assertEqual(loader_inputs["mask_device_id"][1]["default"], 0)
        self.assertEqual(loader_inputs["swapper"][1]["default"], "hyperswap_1c_256")  # falls back to the full list when nothing is installed
        self.assertEqual(loader_inputs["occluder"][0][0], "none")
        # the webcam snapshot caches until a widget such as ``retake`` changes
        first = face_swap.DaWastehWebcamSnapshot.IS_CHANGED(cam_index=2, retake=0)
        self.assertEqual(first, face_swap.DaWastehWebcamSnapshot.IS_CHANGED(retake=0, cam_index=2))
        self.assertNotEqual(first, face_swap.DaWastehWebcamSnapshot.IS_CHANGED(cam_index=2, retake=1))
        self.assertEqual(face_swap._regions_for(True), tuple(r for r in face_swap.DEFAULT_REGIONS if r != "mouth"))
        self.assertEqual(face_swap._regions_for(False), face_swap.DEFAULT_REGIONS)
        rgba = face_swap.bgr_to_rgba(np.zeros((4, 4, 3), dtype=np.uint8))
        self.assertEqual(rgba.shape, (4, 4, 4))
        self.assertEqual(int(rgba[0, 0, 3]), 255)
        frames = face_swap.image_tensor_to_bgr_list(np.ones((2, 4, 4, 3), dtype=np.float32) * 0.5)
        self.assertEqual(len(frames), 2)
        self.assertEqual(int(frames[0][0, 0, 0]), 127)


if __name__ == "__main__":
    unittest.main()
