"""Pure helpers for the v1.2.9 Mira-Scene nodes (NumPy / trimesh / PIL only, no ComfyUI or Mira import).

Conventions follow the Mira-Scene inference scripts: the scene image is the centre square of the photo at 518 px,
canonical object space is Z-up in [-0.5, 0.5]^3, camera space is OpenGL (+X right, +Y up, -Z forward) and the floor frame
is +Y up with the floor at y = 0.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

MIRA_SIZE = 518
TRELLIS_IMAGE = 1024
PALETTE = np.array([
    [230, 74, 25], [0, 114, 178], [0, 158, 115], [204, 121, 167], [240, 228, 66], [86, 180, 233],
    [213, 94, 0], [0, 90, 50], [150, 90, 200], [120, 120, 120], [255, 160, 0], [60, 60, 200],
    [180, 30, 90], [30, 160, 160], [140, 100, 40], [90, 200, 90],
], dtype=np.uint8)

# ComfyUI's Trellis2 decoder turns Z-up vertices into glTF Y-up with (x, y, z) -> (x, z, -y); Mira loads its TRELLIS
# GLBs with a +90 degree rotation about X to get back to canonical Z-up. Same matrix here: (x, y, z) -> (x, -z, y).
YUP_TO_CANONICAL = np.array([[1.0, 0.0, 0.0, 0.0],
                             [0.0, 0.0, -1.0, 0.0],
                             [0.0, 1.0, 0.0, 0.0],
                             [0.0, 0.0, 0.0, 1.0]])


def square_crop_box(width: int, height: int) -> tuple[int, int, int]:
    """(left, top, side) of the centred square, like Mira's prepare_case."""
    side = min(int(width), int(height))
    return (int(width) - side) // 2, (int(height) - side) // 2, side


def clean_masks(masks: np.ndarray, floor: np.ndarray | None = None, min_area: float = 0.002, max_objects: int = 16,
                duplicate_iou: float = 0.7) -> tuple[np.ndarray, np.ndarray | None, list[dict]]:
    """Disjoint instance masks for the CCM stage.

    - binarise at 0.5, drop duplicates (IoU above duplicate_iou with an earlier mask, e.g. "sofa" and "couch"),
    - a pixel claimed by several masks goes to the smallest one (usually the object in front),
    - drop masks below min_area of the image, keep at most max_objects (largest first, original order kept),
    - the floor keeps only pixels no object claims.
    Returns (masks [K,H,W] bool, floor [H,W] bool or None, info per input mask).
    """
    masks = np.asarray(masks, dtype=np.float32)
    if masks.ndim == 2:
        masks = masks[None]
    binary = masks > 0.5
    count, height, width = binary.shape
    info = [{"index": i, "area": float(binary[i].mean()), "status": "kept"} for i in range(count)]
    keep: list[int] = []
    for i in range(count):
        if not binary[i].any():
            info[i]["status"] = "empty"
            continue
        duplicate = None
        for j in keep:
            union = np.logical_or(binary[i], binary[j]).sum()
            if union and np.logical_and(binary[i], binary[j]).sum() / union > duplicate_iou:
                duplicate = j
                break
        if duplicate is not None:
            info[i]["status"] = f"duplicate_of_{duplicate}"
            continue
        keep.append(i)
    areas = np.array([binary[i].sum() for i in keep], dtype=np.int64)
    owner = np.full((height, width), -1, dtype=np.int64)
    for rank in np.argsort(-areas, kind="stable"):          # large first, small ones overwrite = smallest wins
        owner[binary[keep[rank]]] = keep[rank]
    result = []
    for i in keep:
        resolved = owner == i
        if resolved.mean() < min_area:
            info[i]["status"] = "too_small"
            continue
        result.append((i, resolved))
    if len(result) > max_objects:
        largest = sorted(result, key=lambda item: -item[1].sum())[:max_objects]
        chosen = {i for i, _ in largest}
        for i, _ in result:
            if i not in chosen:
                info[i]["status"] = "over_limit"
        result = [item for item in result if item[0] in chosen]
    kept = np.stack([m for _, m in result]) if result else np.zeros((0, height, width), dtype=bool)
    for new_index, (i, m) in enumerate(result):
        info[i].update(status="kept", object=new_index, area=float(m.mean()))
    floor_out = None
    if floor is not None:
        floor_out = np.asarray(floor, dtype=np.float32)
        floor_out = (floor_out.max(axis=0) if floor_out.ndim == 3 else floor_out) > 0.5
        if kept.shape[0]:
            floor_out &= ~kept.any(axis=0)
    return kept, floor_out, info


def camera_points_from_moge(points: np.ndarray, mask: np.ndarray | None, depth: np.ndarray | None = None
                            ) -> tuple[np.ndarray, np.ndarray]:
    """MoGe points (OpenCV: +Y down, +Z forward) -> Mira camera points (OpenGL) and the validity mask."""
    points = np.asarray(points, dtype=np.float32)
    valid = np.isfinite(points).all(axis=-1)
    if mask is not None:
        valid &= np.asarray(mask, dtype=bool)
    if depth is not None:
        depth = np.asarray(depth, dtype=np.float32)
        valid &= np.isfinite(depth) & (depth > 0)
    else:
        valid &= points[..., 2] > 0
    camera = points.copy()
    camera[..., 1] *= -1.0
    camera[..., 2] *= -1.0
    camera[~valid] = np.inf
    return camera, valid


def fov_x_from_intrinsics(intrinsics: np.ndarray, width: int) -> float:
    """Horizontal field of view (radians) from normalised (fx ~ 1) or pixel intrinsics."""
    fx = float(np.asarray(intrinsics)[0, 0])
    if fx < 10.0:          # MoGe returns normalised intrinsics
        fx *= width
    return float(2.0 * math.atan(width / 2.0 / max(fx, 1e-6)))


def trellis_structure(voxel_coords: list, voxel_res: int = 64, structure_res: int = 32) -> np.ndarray:
    """Mira's 64^3 occupancy -> TRELLIS.2's 32^3 sparse structure (np.unique(coords // 2)), as dense [N,R,R,R]."""
    ratio = voxel_res // structure_res
    grid = np.zeros((len(voxel_coords), structure_res, structure_res, structure_res), dtype=np.float32)
    for index, coords in enumerate(voxel_coords):
        coords = np.asarray(coords, dtype=np.int64).reshape(-1, 3)
        if coords.size == 0:
            continue
        if coords.max() >= voxel_res or coords.min() < 0:
            raise ValueError(f"voxel index outside 0..{voxel_res - 1}")
        small = np.unique(coords // ratio, axis=0)
        grid[index, small[:, 0], small[:, 1], small[:, 2]] = 1.0
    return grid


def object_cutout(image: np.ndarray, mask: np.ndarray, size: int = TRELLIS_IMAGE) -> np.ndarray:
    """TRELLIS.2 conditioning image like Mira's preprocess: square around the alpha > 0.8 box, premultiplied on black.

    image: [S,S,3] float in [0,1] (the high-resolution centre square); mask: [h,w] (any size, e.g. 518).
    """
    image = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
    height, width = image.shape[:2]
    alpha = Image.fromarray((np.clip(np.asarray(mask, dtype=np.float32), 0, 1) * 255).astype(np.uint8))
    alpha = np.asarray(alpha.resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
    alpha = (alpha > 0.5).astype(np.float32)
    rows, cols = np.nonzero(alpha > 0.8)
    if rows.size == 0:
        return np.zeros((size, size, 3), dtype=np.float32)
    x0, x1, y0, y1 = cols.min(), cols.max(), rows.min(), rows.max()
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    side = max(1, int(max(x1 - x0, y1 - y0)))
    left, top = int(cx - side / 2), int(cy - side / 2)
    premultiplied = Image.fromarray((image * alpha[..., None] * 255).round().astype(np.uint8))
    crop = premultiplied.crop((left, top, left + side, top + side))   # outside the image = black
    crop = crop.resize((size, size), Image.Resampling.LANCZOS)
    return np.asarray(crop, dtype=np.float32) / 255.0


def restore_ccm(ccm, params: dict, size: int):
    """Cropped-space CCM (torch [3,S,S], already at the scene size) back onto the scene canvas, zeros outside the crop
    box: resize to the padded square, strip the pad-to-square padding, paste at the crop box (Mira's
    restore_canonical_coord_map, nearest interpolation)."""
    import torch.nn.functional as F
    top, left, bottom, right = params["top"], params["left"], params["bottom"], params["right"]
    ph, pw = params.get("pad_h", 0), params.get("pad_w", 0)
    ph_e, pw_e = params.get("pad_h_extra", 0), params.get("pad_w_extra", 0)
    crop_h, crop_w = max(bottom - top, 1), max(right - left, 1)
    square = crop_h + ph + ph_e
    if square != crop_w + pw + pw_e:
        raise ValueError("inconsistent pad-to-square crop parameters")
    out = ccm.new_zeros((ccm.shape[0], size, size))
    resized = F.interpolate(ccm[None], size=(square, square), mode="nearest")[0]
    out[:, top:bottom, left:right] = resized[:, ph:square - ph_e, pw:square - pw_e]
    return out


def mask_preview(image: np.ndarray, masks: np.ndarray, floor: np.ndarray | None = None, opacity: float = 0.55) -> np.ndarray:
    """Scene image with every instance in its palette colour (floor hatched grey)."""
    out = np.clip(np.asarray(image, dtype=np.float32)[..., :3], 0, 1).copy()
    if floor is not None and floor.any():
        stripes = ((np.add.outer(np.arange(out.shape[0]), np.arange(out.shape[1])) // 6) % 2 == 0) & floor
        out[stripes] = out[stripes] * 0.5 + 0.25
    for index, m in enumerate(np.asarray(masks, dtype=bool)):
        colour = PALETTE[index % len(PALETTE)] / 255.0
        out[m] = out[m] * (1 - opacity) + colour * opacity
    return out


def ccm_preview(image: np.ndarray, ccm: np.ndarray) -> np.ndarray:
    """Canonical coordinates as RGB ((x,y,z)+0.5) over a darkened scene; ccm: [N,3,H,W] with zeros outside objects."""
    base = np.clip(np.asarray(image, dtype=np.float32)[..., :3], 0, 1) * 0.35
    for item in np.asarray(ccm, dtype=np.float32):
        inside = np.abs(item).sum(axis=0) > 1e-6
        rgb = np.clip(np.moveaxis(item, 0, -1) + 0.5, 0, 1)
        base[inside] = rgb[inside]
    return base


def upright_flags(initial_camera: list[np.ndarray], camera_to_floor: np.ndarray, mode: str, max_tilt_deg: float = 30.0
                  ) -> tuple[list[bool], list[float]]:
    """Which objects get Mira's hard gravity constraint (canonical +Z = floor +Y).

    Mira decides from a VLM scene graph (objects resting on something are upright). Without it: 'auto' snaps an
    object upright when its independent CCM/depth fit already stands within max_tilt_deg of vertical; 'all' / 'none'.
    Returns the flags and each object's measured tilt in degrees.
    """
    tilts = []
    for matrix in initial_camera:
        floor_matrix = np.asarray(camera_to_floor) @ np.asarray(matrix)
        scale = np.linalg.norm(floor_matrix[:3, 0])
        up = floor_matrix[:3, 2] / max(scale, 1e-12)
        tilts.append(float(np.degrees(np.arccos(np.clip(up[1], -1.0, 1.0)))))
    if mode == "all":
        return [True] * len(tilts), tilts
    if mode == "none":
        return [False] * len(tilts), tilts
    return [tilt <= max_tilt_deg for tilt in tilts], tilts


def transformed_bounds(vertices: np.ndarray, transform: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    placed = np.asarray(vertices, dtype=np.float64) @ transform[:3, :3].T + transform[:3, 3]
    return placed.min(axis=0), placed.max(axis=0)


def support_graph(hull_vertices: list[np.ndarray], transforms: list[np.ndarray], floor_ratio: float = 0.15,
                  floor_min: float = 0.10, stack_ratio: float = 0.25, stack_min: float = 0.10) -> dict:
    """Mira-style scene graph with 'rests_on' edges derived from geometry (instead of Mira's VLM).

    An object whose bottom lies within max(floor_min, floor_ratio * height) of the floor rests on the floor; otherwise
    on the object below whose footprint overlaps its own and whose top is within max(stack_min, stack_ratio * height)
    of its bottom. Objects matching neither (hanging, floating) keep their pose. Both minimum tolerances are 10 cm:
    MoGe's depth error at 2-3 m left a pot 9.5 cm above the cabinet it stands on (office test scene).
    """
    count = len(hull_vertices)
    bounds = [transformed_bounds(v, t) for v, t in zip(hull_vertices, transforms)]
    edges = []
    for child in range(count):
        low, high = bounds[child]
        height = max(high[1] - low[1], 1e-6)
        bottom = low[1]
        if abs(bottom) <= max(floor_min, floor_ratio * height):
            edges.append({"child": f"object_{child:03d}", "parent": "floor", "relation": "rests_on",
                          "confidence": 1.0, "operational": True})
            continue
        best = None
        for parent in range(count):
            if parent == child:
                continue
            p_low, p_high = bounds[parent]
            overlap_x = min(high[0], p_high[0]) - max(low[0], p_low[0])
            overlap_z = min(high[2], p_high[2]) - max(low[2], p_low[2])
            if overlap_x <= 0 or overlap_z <= 0:
                continue
            footprint = max((high[0] - low[0]) * (high[2] - low[2]), 1e-9)
            if overlap_x * overlap_z / footprint < 0.3:
                continue
            gap = bottom - p_high[1]
            if abs(gap) > max(stack_min, stack_ratio * height) or p_low[1] > bottom:
                continue
            if best is None or abs(gap) < best[0]:
                best = (abs(gap), parent)
        if best is not None:
            edges.append({"child": f"object_{child:03d}", "parent": f"object_{best[1]:03d}", "relation": "rests_on",
                          "confidence": 1.0, "operational": True})
    return {"schema": "mira_scene_graph_v1", "nodes": [{"id": f"object_{i:03d}", "kind": "object", "mask_index": i}
                                                        for i in range(count)], "edges": edges}


def floor_extent(placed_vertices: list[np.ndarray], margin_ratio: float = 0.10, min_margin: float = 0.25
                 ) -> tuple[np.ndarray, float]:
    """Centre (x, z) and side of a square floor under all objects (Mira's floor_from_final_meshes rule)."""
    projected = np.concatenate([np.asarray(v)[:, [0, 2]] for v in placed_vertices], axis=0)
    minimum, maximum = projected.min(axis=0), projected.max(axis=0)
    base = float(max(maximum - minimum))
    margin = float(max(min_margin, margin_ratio * base))
    return (minimum + maximum) / 2.0, max(base + 2 * margin, 2 * min_margin)


def floor_texture(image: np.ndarray, floor: np.ndarray, size: int = 1024) -> Image.Image:
    """Observed floor pixels, the rest filled with their median colour (Mira's source floor texture)."""
    rgb = (np.clip(np.asarray(image, dtype=np.float32)[..., :3], 0, 1) * 255).astype(np.uint8)
    rows, cols = np.nonzero(floor)
    if rows.size == 0:
        return Image.new("RGB", (size, size), (128, 128, 128))
    top, bottom, left, right = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    crop, crop_mask = rgb[top:bottom, left:right], floor[top:bottom, left:right]
    texture = np.broadcast_to(np.median(crop[crop_mask], axis=0).astype(np.uint8), crop.shape).copy()
    texture[crop_mask] = crop[crop_mask]
    return Image.fromarray(texture, "RGB").resize((size, size), Image.Resampling.LANCZOS)


def floor_mesh(center_xz: np.ndarray, side: float, texture: Image.Image, repeat: float):
    import trimesh
    half, (x, z) = side / 2.0, center_xz
    vertices = np.array([[x - half, 0, z - half], [x + half, 0, z - half], [x + half, 0, z + half], [x - half, 0, z + half]])
    uv = np.array([[0, 0], [repeat, 0], [repeat, repeat], [0, repeat]], dtype=np.float64)
    material = trimesh.visual.material.PBRMaterial(name="floor", baseColorTexture=texture, baseColorFactor=[255, 255, 255, 255],
                                                   metallicFactor=0.0, roughnessFactor=1.0, doubleSided=True)
    return trimesh.Trimesh(vertices=vertices, faces=np.array([[0, 2, 1], [0, 3, 2]]),
                           visual=trimesh.visual.texture.TextureVisuals(uv=uv, material=material), process=False)


def voxel_mesh(coords: np.ndarray, colour: np.ndarray, voxel_res: int = 64):
    """Canonical (Z-up, [-0.5, 0.5]^3) surface of a voxel occupancy via marching cubes, one flat colour."""
    import trimesh
    from skimage import measure
    grid = np.zeros((voxel_res + 2,) * 3, dtype=np.float32)
    coords = np.asarray(coords, dtype=np.int64).reshape(-1, 3)
    if coords.size == 0:
        return None
    grid[coords[:, 0] + 1, coords[:, 1] + 1, coords[:, 2] + 1] = 1.0
    vertices, faces, _, _ = measure.marching_cubes(grid, level=0.5)
    vertices = (vertices - 1.0 + 0.5) / voxel_res - 0.5
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces[:, ::-1], process=False)
    mesh.visual.vertex_colors = np.tile(np.append(colour, 255).astype(np.uint8), (len(vertices), 1))
    return mesh


def compose_scene_glb(objects: list[tuple[str, object, np.ndarray]], floor=None, camera: tuple[np.ndarray, float, float] | None = None
                      ) -> bytes:
    """One GLB: every (name, trimesh.Scene or Trimesh, 4x4 transform) as its own node; optional floor and camera.

    camera = (camera_to_world 4x4, horizontal fov in radians, width / height).
    """
    import trimesh
    scene = trimesh.Scene()
    for name, item, transform in objects:
        if isinstance(item, trimesh.Scene):
            for node_name in item.graph.nodes_geometry:
                node_transform, geometry_name = item.graph[node_name]
                scene.add_geometry(item.geometry[geometry_name].copy(), node_name=f"{name}_{node_name}",
                                   geom_name=f"{name}_{geometry_name}", transform=np.asarray(transform) @ node_transform)
        else:
            scene.add_geometry(item, node_name=name, geom_name=f"{name}_geometry", transform=np.asarray(transform))
    if floor is not None:
        scene.add_geometry(floor, node_name="floor", geom_name="floor_geometry")
    if camera is not None:
        pose, fov_x, aspect = camera
        fov_y = 2.0 * math.atan(math.tan(fov_x / 2.0) / max(aspect, 1e-6))
        scene.camera = trimesh.scene.Camera(name="photo_camera", fov=(math.degrees(fov_x), math.degrees(fov_y)))
        scene.camera_transform = np.asarray(pose)
    buffer = io.BytesIO()
    scene.export(buffer, file_type="glb")
    return buffer.getvalue()
