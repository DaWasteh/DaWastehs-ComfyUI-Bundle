"""CPU-only, conservative single-convex collision proxies (no neural physics)."""

from __future__ import annotations

import itertools
import numpy as np
from scipy.spatial import ConvexHull, QhullError


def collision_proxy(vertices, mode="convex_hull", max_vertices=128, margin=0.002):
    """Enclose all source vertices; never decimate a hull inward.

    Excessively complex hulls fall back to a bounding box, explicitly reported.
    Coordinates/margin use the input mesh's units; no implicit metre conversion.
    """
    points = np.asarray(vertices, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 4:
        raise ValueError("Expected at least four 3D vertices")
    if not np.isfinite(points).all():
        raise ValueError("Non-finite mesh coordinates")
    if mode not in {"convex_hull", "box"}:
        raise ValueError("Unsupported collision mode")
    if not 8 <= max_vertices <= 4096 or not np.isfinite(margin) or margin < 0:
        raise ValueError("Invalid vertex budget or margin")
    lo, hi = points.min(0), points.max(0)
    span = hi - lo
    if np.any(span <= 1e-9):
        raise ValueError("Flat/degenerate mesh cannot form a 3D collider")
    reason = None
    if mode == "convex_hull":
        try:
            hull = ConvexHull(points)
            proxy = points[hull.vertices]
            if len(proxy) > max_vertices:
                reason = f"Hull has {len(proxy)} vertices; conservative box fallback for budget {max_vertices}"
            else:
                # Uniform expansion about an interior point by inradius. Every
                # supporting plane moves outward by at least margin.
                center = proxy.mean(0)
                radius = -(hull.equations[:, :3] @ center + hull.equations[:, 3]).max()
                if radius <= 1e-12:
                    raise ValueError("Degenerate hull")
                proxy = center + (proxy - center) * (1 + margin / radius)
        except QhullError as exc:
            raise ValueError("Mesh cannot form a full-dimensional convex hull") from exc
    if mode == "box" or reason:
        proxy = np.array(list(itertools.product(*zip(lo - margin, hi + margin))))
    hull = ConvexHull(proxy)
    faces = hull.simplices.copy()
    normal = np.cross(
        proxy[faces[:, 1]] - proxy[faces[:, 0]], proxy[faces[:, 2]] - proxy[faces[:, 0]]
    )
    flip = (normal * hull.equations[:, :3]).sum(1) < 0
    faces[flip] = faces[flip][:, [0, 2, 1]]
    # Chunked containment check: bounded RAM even for dense input meshes.
    tolerance = max(1e-7, float(span.max()) * 1e-6)
    for start in range(0, len(points), 4096):
        if (
            np.max(
                points[start : start + 4096] @ hull.equations[:, :3].T
                + hull.equations[:, 3]
            )
            > tolerance
        ):
            raise ValueError("Collision proxy failed source-containment check")
    return (
        proxy.astype(np.float32),
        faces.astype(np.int64),
        {
            "requested_mode": mode,
            "actual_mode": "box" if mode == "box" or reason else "convex_hull",
            "fallback_reason": reason,
            "source_vertices": len(points),
            "vertices": len(proxy),
            "triangles": len(faces),
            "volume": float(hull.volume),
            "margin_mesh_units": margin,
            "contains_source": True,
            "limitation": "One solid convex collider; fills holes, doors and concavities. No rig, joints or decomposition.",
        },
    )


def godot_scene(points, body_type="StaticBody3D", mass=1.0):
    if body_type not in {"StaticBody3D", "RigidBody3D"}:
        raise ValueError("Unsupported Godot body type")
    if not np.isfinite(mass) or mass <= 0:
        raise ValueError("Mass must be positive and finite")
    values = ", ".join(format(float(x), ".9g") for x in np.asarray(points).reshape(-1))
    mass_line = f"mass = {mass:.9g}\n" if body_type == "RigidBody3D" else ""
    return (
        "[gd_scene load_steps=2 format=3]\n\n"
        '[sub_resource type="ConvexPolygonShape3D" id="Shape_collision"]\n'
        f"points = PackedVector3Array({values})\n\n"
        f'[node name="DaWastehCollision" type="{body_type}"]\n{mass_line}\n'
        '[node name="CollisionShape3D" type="CollisionShape3D" parent="."]\n'
        'shape = SubResource("Shape_collision")\n'
    )
