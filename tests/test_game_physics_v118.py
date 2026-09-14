"""Pure CPU regression coverage for conservative collision geometry."""

import importlib.util
from pathlib import Path
import unittest
import numpy as np
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "game_physics_geometry",
    ROOT / "custom_nodes/ComfyUI-DaWasteh-GamePhysics/geometry.py",
)
geo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geo)


class CollisionTests(unittest.TestCase):
    def setUp(self):
        self.box = np.array(
            [[x, y, z] for x in (-1, 1) for y in (-2, 2) for z in (-3, 3)], dtype=float
        )

    def test_hull_is_closed_outward_and_contains_source(self):
        vertices, faces, report = geo.collision_proxy(self.box, margin=0.01)
        self.assertEqual(report["actual_mode"], "convex_hull")
        self.assertTrue(report["contains_source"])
        hull = ConvexHull(vertices)
        self.assertLessEqual(
            np.max(self.box @ hull.equations[:, :3].T + hull.equations[:, 3]), 0
        )
        normals = np.cross(
            vertices[faces[:, 1]] - vertices[faces[:, 0]],
            vertices[faces[:, 2]] - vertices[faces[:, 0]],
        )
        self.assertTrue(
            np.all(
                np.sum(normals * (vertices[faces].mean(1) - vertices.mean(0)), axis=1)
                > 0
            )
        )
        edges = {}
        for a, b, c in faces:
            for edge in ((a, b), (b, c), (c, a)):
                key = tuple(sorted(edge))
                edges[key] = edges.get(key, 0) + 1
        self.assertEqual(set(edges.values()), {2})

    def test_complex_hull_falls_back_without_shrinking(self):
        rng = np.random.default_rng(118)
        points = rng.normal(size=(512, 3))
        points /= np.linalg.norm(points, axis=1)[:, None]
        vertices, faces, report = geo.collision_proxy(points, max_vertices=8)
        self.assertEqual(report["actual_mode"], "box")
        self.assertIsNotNone(report["fallback_reason"])
        self.assertEqual(len(vertices), 8)
        self.assertEqual(len(faces), 12)
        self.assertTrue(np.all(points.min(0) >= vertices.min(0)))
        self.assertTrue(np.all(points.max(0) <= vertices.max(0)))

    def test_box_preserves_translation_and_units(self):
        p, _, _ = geo.collision_proxy(self.box * 5 + 17, "box", margin=0)
        np.testing.assert_allclose(p.min(0), (self.box * 5 + 17).min(0))
        np.testing.assert_allclose(p.max(0), (self.box * 5 + 17).max(0))

    def test_bad_inputs_fail_closed(self):
        for points in (
            self.box * np.nan,
            np.zeros((8, 3)),
            self.box[:3],
            np.ones((8, 2)),
        ):
            with self.assertRaises(ValueError):
                geo.collision_proxy(points)
        for kwargs in (
            {"margin": -1},
            {"margin": float("nan")},
            {"mode": "decompose"},
            {"max_vertices": 4},
        ):
            with self.assertRaises(ValueError):
                geo.collision_proxy(self.box, **kwargs)

    def test_real_godot_body_scene(self):
        text = geo.godot_scene(self.box, "RigidBody3D", 2.5)
        for token in (
            "ConvexPolygonShape3D",
            "CollisionShape3D",
            "RigidBody3D",
            "mass = 2.5",
            "PackedVector3Array",
        ):
            self.assertIn(token, text)
        self.assertNotIn("mass =", geo.godot_scene(self.box))
        with self.assertRaises(ValueError):
            geo.godot_scene(self.box, "invalid")
        with self.assertRaises(ValueError):
            geo.godot_scene(self.box, mass=0)


if __name__ == "__main__":
    unittest.main()
