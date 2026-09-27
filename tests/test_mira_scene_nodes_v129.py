"""v1.2.9 DaWasteh Mira-Scene pack: pure helpers (masks, camera points, voxels, crops, placement, GLB); no ComfyUI import."""
from __future__ import annotations

import importlib.util
import io
import math
import os
import sys
import unittest
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MiraScene"
CHECKOUT = Path(os.environ.get("DAWASTEH_MIRA_SCENE_ROOT", r"L:\ComfyUI\third_party\Mira-Scene"))


def helpers():
    spec = importlib.util.spec_from_file_location("mira_helpers_under_test", PACK / "helpers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MaskTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_duplicates_overlaps_small_and_floor(self):
        masks = np.zeros((4, 100, 100), np.float32)
        masks[0, 10:60, 10:60] = 1          # table
        masks[1, 12:60, 10:60] = 1          # same table again (IoU 0.96) -> duplicate
        masks[2, 20:30, 20:30] = 1          # vase on the table -> overlap goes to the smaller mask
        masks[3, 0:2, 0:2] = 1              # 4 px -> too small
        floor = np.zeros((100, 100), np.float32)
        floor[50:, :] = 1
        kept, floor_out, info = self.h.clean_masks(masks, floor, min_area=0.002, max_objects=16)
        self.assertEqual([i["status"] for i in info], ["kept", "duplicate_of_0", "kept", "too_small"])
        self.assertEqual(kept.shape, (2, 100, 100))
        self.assertFalse(np.logical_and(kept[0], kept[1]).any())       # disjoint
        self.assertTrue(kept[1][20:30, 20:30].all())                     # vase keeps its pixels
        self.assertFalse(kept[0][20:30, 20:30].any())
        self.assertFalse((floor_out & kept.any(axis=0)).any())           # objects win over the floor
        self.assertTrue(floor_out[70:, :].all())

    def test_max_objects_keeps_the_largest_in_original_order(self):
        masks = np.zeros((3, 50, 50), np.float32)
        masks[0, :5, :5] = 1
        masks[1, 10:40, 10:40] = 1
        masks[2, 45:50, 0:20] = 1
        kept, _, info = self.h.clean_masks(masks, None, min_area=0.0, max_objects=2)
        self.assertEqual([i["status"] for i in info], ["over_limit", "kept", "kept"])
        self.assertEqual([i.get("object") for i in info], [None, 0, 1])
        self.assertEqual(kept.shape[0], 2)
        empty, _, _ = self.h.clean_masks(np.zeros((1, 8, 8), np.float32))
        self.assertEqual(empty.shape, (0, 8, 8))


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_moge_opencv_to_mira_opengl(self):
        points = np.array([[[0.5, 0.25, 2.0], [np.nan, 0, 1]], [[0, 0, -1.0], [1, 1, 3]]], np.float32)
        mask = np.array([[True, True], [True, False]])
        camera, valid = self.h.camera_points_from_moge(points, mask)
        self.assertEqual(valid.tolist(), [[True, False], [False, False]])     # NaN, behind the camera, masked
        self.assertEqual(camera[0, 0].tolist(), [0.5, -0.25, -2.0])
        self.assertTrue(np.isinf(camera[1, 1]).all())
        self.assertAlmostEqual(math.degrees(self.h.fov_x_from_intrinsics(np.diag([1.0, 1.0, 1.0]), 518)), 53.13, places=2)
        self.assertAlmostEqual(math.degrees(self.h.fov_x_from_intrinsics(np.diag([259.0, 259.0, 1.0]), 518)), 90.0, places=4)

    def test_trellis_structure_is_mira_coords_halved(self):
        coords = [np.array([[0, 0, 0], [1, 1, 1], [63, 62, 10]]), np.zeros((0, 3), np.int64)]
        grid = self.h.trellis_structure(coords)
        self.assertEqual(grid.shape, (2, 32, 32, 32))
        self.assertEqual(sorted(map(tuple, np.argwhere(grid[0] > 0).tolist())), [(0, 0, 0), (31, 31, 5)])
        self.assertEqual(grid[1].sum(), 0)
        with self.assertRaises(ValueError):
            self.h.trellis_structure([np.array([[64, 0, 0]])])

    def test_yup_matrix_undoes_the_trellis_decoder_rotation(self):
        canonical = np.array([[0.1, 0.2, 0.3]])
        comfy_yup = np.stack([canonical[:, 0], canonical[:, 2], -canonical[:, 1]], axis=-1)   # VaeDecodeShapeTrellis
        back = comfy_yup @ self.h.YUP_TO_CANONICAL[:3, :3].T
        self.assertTrue(np.allclose(back, canonical))

    def test_object_cutout_square_premultiplied(self):
        image = np.ones((200, 200, 3), np.float32) * 0.5
        mask = np.zeros((100, 100), np.float32)
        mask[10:30, 40:80] = 1                       # 40 wide, 20 high at half resolution
        cut = self.h.object_cutout(image, mask, size=64)
        self.assertEqual(cut.shape, (64, 64, 3))
        self.assertAlmostEqual(float(cut[32, 32, 0]), 0.5, places=1)   # object in the middle
        self.assertEqual(float(cut[2, 32].max()), 0.0)                  # square box, black above/below the object
        self.assertEqual(self.h.object_cutout(image, np.zeros((10, 10))).max(), 0.0)

    def test_square_crop(self):
        self.assertEqual(self.h.square_crop_box(1920, 1080), (420, 0, 1080))
        self.assertEqual(self.h.square_crop_box(1000, 1500), (0, 250, 1000))


@unittest.skipUnless((CHECKOUT / "UniDataset" / "src").is_dir(), "Mira-Scene checkout not installed")
class RestoreRoundTripTests(unittest.TestCase):
    def test_crop_then_restore_returns_the_map_inside_the_box(self):
        sys.path.insert(0, str(CHECKOUT / "UniDataset" / "src"))
        try:
            from UniDataset.utils.img_and_mask_transforms import crop_around_mask
        finally:
            sys.path.remove(str(CHECKOUT / "UniDataset" / "src"))
        h = helpers()
        size = 518
        yy, xx = torch.meshgrid(torch.linspace(-0.5, 0.5, size), torch.linspace(-0.5, 0.5, size), indexing="ij")
        ccm = torch.stack([xx, yy, xx * yy])
        mask = torch.zeros(1, size, size)
        mask[0, 100:180, 300:460] = 1                  # wide object -> pad-to-square vertically
        cropped, _, params = crop_around_mask(ccm * mask, mask, box_size_factor=1.2, target_h=size, target_w=size)
        restored = h.restore_ccm(cropped, params, size)
        inside = torch.zeros(size, size, dtype=torch.bool)
        inside[103:177, 303:457] = True               # 3 px from the mask edge (bilinear resize blends with zeros there)
        error = (restored[:, inside] - ccm[:, inside]).abs()
        self.assertLess(float(error.max()), 0.01)     # an off-by-one-pixel paste would already show ~0.002 per pixel
        self.assertLess(float(error.mean()), 0.002)
        box = torch.zeros(size, size, dtype=torch.bool)
        box[params["top"]:params["bottom"], params["left"]:params["right"]] = True
        self.assertEqual(float(restored[:, ~box].abs().max()), 0.0)


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.h = helpers()

    def test_upright_modes(self):
        tilted = np.eye(4)
        angle = math.radians(20)
        tilted[:3, :3] = np.array([[1, 0, 0], [0, math.cos(angle), -math.sin(angle)], [0, math.sin(angle), math.cos(angle)]])
        to_y_up = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1.0]])   # canonical +Z -> floor +Y
        flipped = np.eye(4)
        flipped[:3, :3] = np.diag([1.0, -1.0, -1.0])                                       # 180 degrees about X
        mats = [to_y_up, to_y_up @ tilted, to_y_up @ flipped]
        flags, tilts = self.h.upright_flags(mats, np.eye(4), "auto")
        self.assertEqual(flags, [True, True, False])
        self.assertAlmostEqual(tilts[1], 20.0, places=3)
        self.assertEqual(self.h.upright_flags(mats, np.eye(4), "none")[0], [False] * 3)
        self.assertEqual(self.h.upright_flags(mats, np.eye(4), "all")[0], [True] * 3)

    def test_support_graph_floor_stack_and_floating(self):
        box = np.array([[x, y, z] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)])
        def place(scale, x, y, z):
            m = np.eye(4) * scale
            m[3, 3] = 1
            m[:3, 3] = (x, y, z)
            return m
        transforms = [place(1.0, 0, 0.52, 0),        # table, bottom 0.02 -> floor
                      place(0.2, 0.1, 1.15, 0),      # vase, bottom 1.05, table top 1.02 -> on the table
                      place(0.3, 3, 1.6, 0)]         # picture on a wall -> nothing
        graph = self.h.support_graph([box] * 3, transforms)
        edges = {e["child"]: e["parent"] for e in graph["edges"]}
        self.assertEqual(edges, {"object_000": "floor", "object_001": "object_000"})
        self.assertTrue(all(e["relation"] == "rests_on" and e["operational"] for e in graph["edges"]))
        # depth error: a pot 9.5 cm above the cabinet top still rests on it, 15 cm above does not
        near = self.h.support_graph([box] * 2, [place(1.0, 0, 0.52, 0), place(0.2, 0, 1.215, 0)])
        far = self.h.support_graph([box] * 2, [place(1.0, 0, 0.52, 0), place(0.2, 0, 1.27, 0)])
        self.assertEqual([e["parent"] for e in near["edges"]], ["floor", "object_000"])
        self.assertEqual([e["parent"] for e in far["edges"]], ["floor"])

    def test_floor_extent_and_scene_glb(self):
        import trimesh
        center, side = self.h.floor_extent([np.array([[0, 0, 0], [2, 1, 1]])])
        self.assertTrue(np.allclose(center, [1.0, 0.5]))
        self.assertAlmostEqual(side, 2.5)
        voxel = self.h.voxel_mesh(np.array([[30, 30, 30], [31, 30, 30]]), self.h.PALETTE[1])
        self.assertTrue(voxel.is_watertight)
        self.assertLessEqual(float(np.abs(voxel.vertices).max()), 0.5)
        floor = self.h.floor_mesh(center, side, self.h.floor_texture(np.ones((8, 8, 3)) * 0.5, np.ones((8, 8), bool)), repeat=side)
        pose = np.eye(4)
        pose[:3, 3] = (0, 1.2, 2.5)
        glb = self.h.compose_scene_glb([("object_000", voxel, np.eye(4)), ("object_001", voxel.copy(), pose)], floor,
                                       camera=(pose, math.radians(50), 1.0))
        scene = trimesh.load(io.BytesIO(glb), file_type="glb", force="scene")
        self.assertEqual(sorted(scene.graph.nodes_geometry), ["floor", "object_000", "object_001"])
        self.assertTrue(np.allclose(scene.graph["object_001"][0], pose))
        self.assertIn(b"photo_camera", glb)


if __name__ == "__main__":
    unittest.main()
