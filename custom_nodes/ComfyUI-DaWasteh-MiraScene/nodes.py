"""v1.2.9 Mira-Scene nodes: single image -> editable 3D scene (VAST-AI-Research Mira-Scene, ported to ComfyUI).

Stages as in Mira's infer_scripts, with ComfyUI's native models where Mira uses external projects:
segmentation = native SAM3 (text prompts) + DaWMiraMasks, depth = native MoGe-2, CCM = Mira-CCM (this pack, Mira's
pinned code), meshes = native TRELLIS.2 with Mira's voxel structure, scene = DaWMiraAssembleScene (Mira's transform
solver, floor fit and support placement). Mira's Gemini object redraw and the API environment map are left out.
"""
from __future__ import annotations

import io
import json
import logging
import math
import os
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

import comfy.model_management
import comfy.utils
import folder_paths
from comfy_api.latest import ComfyExtension, Types, io as cio

from . import mira_runtime
from .helpers import (MIRA_SIZE, PALETTE, YUP_TO_CANONICAL, camera_points_from_moge, ccm_preview, clean_masks,
                      compose_scene_glb, floor_extent, floor_mesh, floor_texture, fov_x_from_intrinsics, mask_preview,
                      object_cutout, restore_ccm, square_crop_box, support_graph, trellis_structure, upright_flags,
                      voxel_mesh)

TAG = mira_runtime.TAG
CATEGORY = "DaWasteh/mira scene"
MiraModel = cio.Custom("MIRA_CCM_MODEL")
MiraCCM = cio.Custom("MIRA_CCM")
MoGeGeometry = cio.Custom("MOGE_GEOMETRY")
IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
_PIPELINES: dict[tuple[str, str], object] = {}


def _np(image: torch.Tensor) -> np.ndarray:
    return image.detach().float().cpu().numpy()


def _tensor(array: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(np.ascontiguousarray(array, dtype=np.float32))


def _pipeline_dirs() -> list[str]:
    found = []
    for base in folder_paths.get_folder_paths("diffusers"):
        if not os.path.isdir(base):
            continue
        for current, _, files in os.walk(base):
            if "model_index.json" in files:
                try:
                    index = json.loads(Path(current, "model_index.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if index.get("_class_name") == "CCMVoxelPipeline":
                    found.append(os.path.relpath(current, base))
    return sorted(found) or ["Mira-Scene" + os.sep + "pipeline"]


def _pipeline_path(name: str) -> str:
    for base in folder_paths.get_folder_paths("diffusers"):
        path = os.path.join(base, name)
        if os.path.isfile(os.path.join(path, "model_index.json")):
            return path
    raise FileNotFoundError(f"Mira-CCM pipeline '{name}' not found in models/diffusers (expected model_index.json there)")


class DaWMiraPrepareImage(cio.ComfyNode):
    @classmethod
    def define_schema(cls):
        return cio.Schema(
            node_id="DaWMiraPrepareImage",
            display_name="DaW Mira Prepare Image",
            category=CATEGORY,
            description="Mira works on the centre square of the photo at 518 px (like Mira's prepare_case). 'scene' goes "
                        "to SAM3, MoGe and the CCM stage; 'hires' is the same square at up to max_hires px for sharper "
                        "TRELLIS.2 object crops.",
            inputs=[
                cio.Image.Input("image"),
                cio.Int.Input("max_hires", default=2048, min=518, max=4096, step=2, advanced=True),
            ],
            outputs=[cio.Image.Output("scene"), cio.Image.Output("hires")],
        )

    @classmethod
    def execute(cls, image, max_hires) -> cio.NodeOutput:
        frame = (np.clip(_np(image[:1, ..., :3])[0], 0, 1) * 255).round().astype(np.uint8)
        left, top, side = square_crop_box(frame.shape[1], frame.shape[0])
        square = Image.fromarray(frame[top:top + side, left:left + side])
        scene = square.resize((MIRA_SIZE, MIRA_SIZE), Image.Resampling.LANCZOS)
        hires = square if side <= max_hires else square.resize((max_hires, max_hires), Image.Resampling.LANCZOS)
        to = lambda im: _tensor(np.asarray(im, dtype=np.float32)[None] / 255.0)  # noqa: E731
        return cio.NodeOutput(to(scene), to(hires))


class DaWMiraMasks(cio.ComfyNode):
    @classmethod
    def define_schema(cls):
        return cio.Schema(
            node_id="DaWMiraMasks",
            display_name="DaW Mira Clean Masks",
            category=CATEGORY,
            description="Turns SAM3 detections into Mira's disjoint instance masks: duplicates (IoU > 0.7) removed, "
                        "overlaps given to the smaller object, tiny masks dropped, at most max_objects. The floor keeps "
                        "only pixels no object claims. Stops with a clear message when no object is left.",
            inputs=[
                cio.Image.Input("scene"),
                cio.Mask.Input("masks", tooltip="SAM3 Detect with individual_masks on (one mask per object)."),
                cio.Float.Input("min_area", default=0.002, min=0.0, max=0.5, step=0.001,
                                tooltip="Smallest object as share of the image (0.002 = 0.2 %)."),
                cio.Int.Input("max_objects", default=12, min=1, max=32),
                cio.Mask.Input("floor", optional=True, tooltip="SAM3 'floor' mask; used for gravity and the floor plane."),
            ],
            outputs=[cio.Mask.Output("masks"), cio.Mask.Output("floor"), cio.Int.Output("count"), cio.Image.Output("preview")],
        )

    @classmethod
    def execute(cls, scene, masks, min_area, max_objects, floor=None) -> cio.NodeOutput:
        size = scene.shape[1:3]
        def fit(m):
            m = m.float()
            if m.ndim == 2:
                m = m[None]
            if tuple(m.shape[-2:]) != tuple(size):
                m = F.interpolate(m[:, None], size=tuple(size), mode="nearest")[:, 0]
            return m.cpu().numpy()
        kept, floor_mask, info = clean_masks(fit(masks), None if floor is None else fit(floor), min_area, max_objects)
        logging.info("%s masks: %s", TAG, ", ".join(f"{i['index']}:{i['status']}" for i in info))
        if kept.shape[0] == 0:
            raise ValueError("Keine Objekte gefunden: SAM3 hat nichts erkannt oder alles war zu klein. Objektliste "
                             "anpassen (englisch, kommagetrennt, z. B. 'chair, table, lamp') oder threshold senken. / "
                             "No objects left after cleaning.")
        floor_out = floor_mask if floor_mask is not None else np.zeros(tuple(size), dtype=bool)
        preview = mask_preview(_np(scene[0]), kept, floor_mask)
        return cio.NodeOutput(_tensor(kept.astype(np.float32)), _tensor(floor_out[None].astype(np.float32)),
                              int(kept.shape[0]), _tensor(preview[None]))


class DaWMiraLoadCCM(cio.ComfyNode):
    @classmethod
    def define_schema(cls):
        return cio.Schema(
            node_id="DaWMiraLoadCCM",
            display_name="DaW Mira Load CCM Model",
            category=CATEGORY,
            description="Mira-Scene's CCM pipeline (DINOv2 image encoder, dual-stream CCM/voxel DiT, sparse-structure "
                        "VAE) from models/diffusers. Code: pinned Mira-Scene checkout (see the pack README).",
            inputs=[
                cio.Combo.Input("pipeline", options=_pipeline_dirs()),
                cio.Combo.Input("dtype", options=["bf16", "fp32"], default="bf16", tooltip="Mira runs bf16."),
            ],
            outputs=[MiraModel.Output("mira_model")],
        )

    @classmethod
    def execute(cls, pipeline, dtype) -> cio.NodeOutput:
        path = _pipeline_path(pipeline)
        mira_runtime.modules()          # fail early with the checkout hint
        return cio.NodeOutput({"path": path, "dtype": dtype})


def _load_pipeline(handle: dict):
    key = (handle["path"], handle["dtype"])
    if key not in _PIPELINES:
        _PIPELINES.clear()
        cls = mira_runtime.modules()["CCMVoxelPipeline"]
        dtype = torch.bfloat16 if handle["dtype"] == "bf16" else torch.float32
        pipe = cls.from_pretrained(handle["path"], torch_dtype=dtype, safety_checker=None, requires_safety_checker=False)
        pipe.set_progress_bar_config(disable=True)
        _PIPELINES[key] = pipe
    return _PIPELINES[key]


class DaWMiraCCM(cio.ComfyNode):
    @classmethod
    def define_schema(cls):
        return cio.Schema(
            node_id="DaWMiraCCM",
            display_name="DaW Mira Predict CCM + Voxels",
            category=CATEGORY,
            description="Mira-Scene's CCM stage for every object at once: pixel-aligned canonical coordinate maps "
                        "(where each pixel sits on its object) and the object's 64^3 occupancy. Outputs the voxel "
                        "structure for TRELLIS.2 (32^3, like Mira's trellis2 backend), 1024 px object crops for the "
                        "TRELLIS.2 conditioning and a preview (canonical x/y/z as colour).",
            inputs=[
                MiraModel.Input("mira_model"),
                cio.Image.Input("scene", tooltip="518x518 scene from DaW Mira Prepare Image."),
                cio.Mask.Input("masks", tooltip="Clean instance masks from DaW Mira Clean Masks."),
                cio.Image.Input("hires", tooltip="High-resolution square from DaW Mira Prepare Image (object crops)."),
                cio.Int.Input("seed", default=42, min=0, max=2**31 - 1, control_after_generate=True),
                cio.Int.Input("steps", default=30, min=4, max=100),
                cio.Float.Input("guidance", default=3.0, min=1.0, max=10.0, step=0.1),
            ],
            outputs=[MiraCCM.Output("mira_ccm"), cio.Voxel.Output("voxel"), cio.Image.Output("objects"),
                     cio.Image.Output("preview"), cio.Int.Output("count")],
        )

    @classmethod
    def execute(cls, mira_model, scene, masks, hires, seed, steps, guidance) -> cio.NodeOutput:
        mods = mira_runtime.modules()
        crop_around_mask = mods["crop_around_mask"]
        image = scene[:1, ..., :3].float().cpu()
        if tuple(image.shape[1:3]) != (MIRA_SIZE, MIRA_SIZE):
            raise ValueError(f"scene must be {MIRA_SIZE}x{MIRA_SIZE} (DaW Mira Prepare Image), got {tuple(image.shape[1:3])}")
        mask = masks.float().cpu()
        if mask.ndim == 2:
            mask = mask[None]
        count = mask.shape[0]
        # prepare_inference_input of Mira's DataProcessor (518 px scene: its resize + centre crop are the identity)
        image_t = image[0].permute(2, 0, 1)[None].expand(count, -1, -1, -1).clone()
        mask_t = (mask > 0.5).float()[:, None]
        part = image_t * mask_t
        crops, crop_masks, params = [], [], []
        for i in range(count):
            rgb_c, mask_c, param = crop_around_mask(part[i], mask_t[i], box_size_factor=1.2, target_h=MIRA_SIZE, target_w=MIRA_SIZE)
            crops.append(rgb_c)
            crop_masks.append(mask_c)
            params.append(param)
        crops = torch.stack(crops)
        crop_masks = torch.stack(crop_masks)
        image_norm = (image_t - IMAGENET_MEAN) / IMAGENET_STD
        crop_norm = (crops - IMAGENET_MEAN) / IMAGENET_STD
        mask_3 = mask_t.expand(-1, 3, -1, -1)
        crop_mask_3 = crop_masks.expand(-1, 3, -1, -1)

        pipe = _load_pipeline(mira_model)
        device = comfy.model_management.get_torch_device()
        dtype = torch.bfloat16 if mira_model["dtype"] == "bf16" else torch.float32
        comfy.model_management.free_memory(8 * 1024 ** 3, device)
        pbar = comfy.utils.ProgressBar(steps)

        def on_step(_pipe, index, _t, kwargs):
            comfy.model_management.throw_exception_if_processing_interrupted()
            pbar.update_absolute(index + 1)
            return {}

        try:
            pipe.to(device)
            layout_res = pipe.transformer.config.latent_config["layout"]["pos_embedder"]["resolution"]
            to_dev = lambda t: t.to(device=device, dtype=dtype)  # noqa: E731
            layout_mask = F.interpolate(crop_masks.float(), size=(layout_res, layout_res), mode="nearest")
            layout_image = F.interpolate(crop_norm.float(), size=(layout_res, layout_res), mode="bilinear", align_corners=False)
            generator = torch.Generator(device=device).manual_seed(int(seed))
            with torch.inference_mode():
                output = pipe(
                    image=to_dev(image_norm), mask=to_dev(mask_3), image_cropped=to_dev(crop_norm),
                    mask_cropped=to_dev(crop_mask_3), num_inference_steps=int(steps), resolution=64,
                    guidance_scale=float(guidance), keep_layout_condition_in_uncond=True,
                    layout_mask_for_concat=to_dev(layout_mask), layout_image_for_conv=to_dev(layout_image),
                    use_cropped_condition=True, layout_pred_mode="velocity", layout_t_eps=1e-5, generator=generator,
                    callback_on_step_end=on_step, callback_on_step_end_tensor_inputs=[])
            ccm_pred = output.latent_voxel_cam_pts.float().cpu()
            coords = [c.cpu().numpy().astype(np.int64) for c in output.coords]
            pcds = [np.asarray(p, dtype=np.float32) for p in output.pcds]
        finally:
            pipe.to("cpu")
            comfy.model_management.soft_empty_cache()

        # 2_inference_CCM.py: mask in cropped space, upsample to the scene size, clamp, mask, restore onto the canvas
        h, w = ccm_pred.shape[-2:]
        ccm_pred = ccm_pred * (F.interpolate(crop_masks.float(), size=(h, w), mode="nearest") > 0.5).float()
        up = F.interpolate(ccm_pred, size=(MIRA_SIZE, MIRA_SIZE), mode="bilinear", align_corners=False).clamp(-0.5, 0.5)
        up = up * (F.interpolate(crop_masks.float(), size=(MIRA_SIZE, MIRA_SIZE), mode="nearest") > 0.5).float()
        restored = torch.stack([restore_ccm(up[i], params[i], MIRA_SIZE) for i in range(count)]).numpy()

        structure = trellis_structure(coords)
        hires_np = np.clip(_np(hires[0, ..., :3]), 0, 1)
        objects = np.stack([object_cutout(hires_np, mask[i].numpy()) for i in range(count)])
        preview = ccm_preview(image[0].numpy(), restored)
        voxels = [int(len(c)) for c in coords]
        logging.info("%s CCM for %d objects, voxels per object: %s", TAG, count, voxels)
        data = {"scene": image[0].numpy(), "masks": mask.numpy() > 0.5, "ccm": restored, "voxel_coords": coords,
                "pcds": pcds, "seed": int(seed), "steps": int(steps), "guidance": float(guidance),
                "commit": mods.get("commit")}
        return cio.NodeOutput(data, Types.VOXEL(_tensor(structure)), _tensor(objects), _tensor(preview[None]), int(count))


class DaWMiraTrellisObjects(cio.ComfyNode):
    """TRELLIS.2 for every object, one after the other, through ComfyUI's own Trellis2 and mesh nodes.

    A batched Trellis2 sampler pads every object to the largest one's token count: a living room with a 3 m sofa and
    nine small objects took 92 s per 1024 step instead of 16 s for five furniture pieces. Here each object gets its own
    pass with exactly the calls (and settings) of the bundle's TRELLIS2 PBR workflow.
    """

    @classmethod
    def define_schema(cls):
        return cio.Schema(
            node_id="DaWMiraTrellisObjects",
            display_name="DaW Mira TRELLIS.2 Objects",
            category=CATEGORY,
            description="Runs the native TRELLIS.2 chain per object on Mira's voxel structure (instead of TRELLIS's own "
                        "first stage): shape at 512, optional 1024 cascade, texture, then remesh, decimate, UV unwrap and "
                        "PBR bake with the core mesh nodes. Output: one textured mesh per object, in mask order.",
            inputs=[
                cio.Model.Input("shape_model", tooltip="TRELLIS.2 with CFGOverride + RescaleCFG (shape stages)."),
                cio.Model.Input("texture_model", tooltip="TRELLIS.2 without patches (texture stage, CFG 1)."),
                cio.ClipVision.Input("clip_vision", tooltip="DINOv3 ViT-L."),
                cio.Vae.Input("shape_vae"),
                cio.Vae.Input("texture_vae"),
                cio.Voxel.Input("voxel", tooltip="From DaW Mira Predict CCM + Voxels."),
                cio.Image.Input("objects", tooltip="Object crops from DaW Mira Predict CCM + Voxels."),
                cio.Combo.Input("detail", options=["1024", "512"], default="1024",
                                tooltip="1024 = Mira's cascade (512 then 1024); 512 = faster, coarser."),
                cio.Int.Input("seed", default=42, min=0, max=2**31 - 1, control_after_generate=True),
                cio.Int.Input("shape_steps", default=20, min=1, max=100, advanced=True),
                cio.Int.Input("detail_steps", default=12, min=1, max=100, advanced=True),
                cio.Int.Input("texture_steps", default=12, min=1, max=100, advanced=True),
                cio.Float.Input("cfg", default=7.5, min=1.0, max=20.0, step=0.1, advanced=True),
                cio.Int.Input("remesh_resolution", default=384, min=128, max=1024, step=32,
                              tooltip="Remesh grid (UDF); 256 ~ 100k faces, 512 ~ 1M."),
                cio.Int.Input("max_faces", default=60000, min=2000, max=2000000, step=1000),
                cio.Int.Input("texture_size", default=1024, min=256, max=4096, step=256),
            ],
            outputs=[cio.Mesh.Output("meshes")],
        )

    @classmethod
    def execute(cls, shape_model, texture_model, clip_vision, shape_vae, texture_vae, voxel, objects, detail, seed,
                shape_steps, detail_steps, texture_steps, cfg, remesh_resolution, max_faces, texture_size) -> cio.NodeOutput:
        import nodes as core
        from comfy_extras import nodes_mesh_postprocess as mesh_nodes
        from comfy_extras import nodes_trellis2 as trellis
        from comfy_extras.nodes_save_3d import get_mesh_batch_item, pack_variable_mesh_batch

        def run(node, *args):
            # V3 nodes read cls.hidden (unique_id for progress text); only the executor's class clone carries it.
            return node.PREPARE_CLASS_CLONE(None).execute(*args).args

        grid = voxel.data
        count = int(grid.shape[0])
        if int(objects.shape[0]) != count:
            raise ValueError(f"{int(objects.shape[0])} object images for {count} voxel structures")
        pbar = comfy.utils.ProgressBar(count)
        parts = {k: [] for k in ("vertices", "faces", "uvs", "normals", "texture", "metallic_roughness")}
        for i in range(count):
            comfy.model_management.throw_exception_if_processing_interrupted()
            positive, negative = run(trellis.Trellis2Conditioning, clip_vision, objects[i:i + 1])
            positive, negative, latent = run(trellis.Trellis2ShapeStage, positive, negative, Types.VOXEL(grid[i:i + 1]))
            latent = core.common_ksampler(shape_model, seed, shape_steps, cfg, "euler", "normal", positive, negative, latent)[0]
            if detail == "1024":
                positive, negative, upsampled = run(trellis.Trellis2UpsampleStage, positive, negative, latent, shape_vae, 1024)
                latent = core.common_ksampler(shape_model, seed, detail_steps, cfg, "euler", "simple", positive, negative, upsampled)[0]
            raw_mesh, subdivides = run(trellis.VaeDecodeShapeTrellis, latent, shape_vae)
            t_pos, t_neg, t_latent = run(trellis.Trellis2TextureStage, positive, negative, latent)
            t_latent = core.common_ksampler(texture_model, seed + 1, texture_steps, 1.0, "euler", "normal", t_pos, t_neg, t_latent)[0]
            colours = run(trellis.VaeDecodeTextureTrellis, t_latent, texture_vae, subdivides)[0]
            sign_mode = {"sign_mode": "udf", "qef": False, "drop_inverted_components": False, "drop_enclosed_components": False}
            mesh = run(mesh_nodes.RemeshMesh, raw_mesh, remesh_resolution, sign_mode, 1.0, 0.0, False, 2, 0.002, 20000000)[0]
            mesh = run(mesh_nodes.DecimateMesh, mesh, max_faces, {"placement_mode": "midpoint"})[0]
            mesh = run(mesh_nodes.MeshSmoothNormals, mesh, 45.0)[0]
            mesh = run(mesh_nodes.UnwrapMesh, mesh, "pec", texture_size, 4, 0.0002)[0]
            base, metallic, roughness = run(mesh_nodes.BakeTextureFromVoxel, mesh, colours, texture_size, raw_mesh)
            mesh = run(mesh_nodes.ApplyTextureToMesh, mesh, base, metallic, roughness)[0]
            mesh = run(mesh_nodes.MeshSmoothNormals, mesh, 45.0)[0]
            vertices, faces, _, uvs, normals = get_mesh_batch_item(mesh, 0)
            parts["vertices"].append(vertices.cpu())
            parts["faces"].append(faces.cpu())
            parts["uvs"].append(uvs.cpu())
            parts["normals"].append(normals.cpu() if normals is not None else None)
            parts["texture"].append(mesh.texture[0:1].cpu())
            parts["metallic_roughness"].append(mesh.metallic_roughness[0:1].cpu() if mesh.metallic_roughness is not None else None)
            logging.info("%s TRELLIS.2 object %d/%d: %d faces", TAG, i + 1, count, int(faces.shape[0]))
            pbar.update(1)
        normals = parts["normals"] if all(n is not None for n in parts["normals"]) else None
        roughness_maps = parts["metallic_roughness"]
        packed = pack_variable_mesh_batch(
            parts["vertices"], parts["faces"], uvs=parts["uvs"], texture=torch.cat(parts["texture"]), normals=normals,
            metallic_roughness=torch.cat(roughness_maps) if all(m is not None for m in roughness_maps) else None)
        return cio.NodeOutput(packed)


class DaWMiraAssembleScene(cio.ComfyNode):
    @classmethod
    def define_schema(cls):
        return cio.Schema(
            node_id="DaWMiraAssembleScene",
            display_name="DaW Mira Assemble Scene",
            category=CATEGORY,
            description="Places every object in 3D like Mira's construct_scene: similarity transform from the object's "
                        "canonical coordinates to the MoGe camera points (RANSAC), the floor plane from the floor mask "
                        "sets gravity, upright objects get the hard gravity constraint, objects are set onto the floor or "
                        "onto the object below them. Without meshes it shows Mira's voxel shapes (fast layout check). "
                        "Output: one GLB in the floor frame (Y up, floor at 0) with a textured floor and the photo camera.",
            inputs=[
                MiraCCM.Input("mira_ccm"),
                MoGeGeometry.Input("moge_geometry", tooltip="MoGe Inference on the 518 px scene."),
                cio.Combo.Input("upright", options=["auto", "all", "none"], default="auto",
                                tooltip="auto: objects standing within 30 degrees of vertical are snapped upright."),
                cio.Boolean.Input("snap_to_support", default=True, tooltip="Set objects onto the floor / the object below."),
                cio.Boolean.Input("add_floor", default=True),
                cio.Int.Input("seed", default=42, min=0, max=2**31 - 1, control_after_generate=True, advanced=True),
                cio.Mask.Input("floor", optional=True, tooltip="Floor mask from DaW Mira Clean Masks."),
                cio.Mesh.Input("meshes", optional=True, tooltip="TRELLIS.2 meshes, one per object in mask order."),
            ],
            outputs=[cio.File3DGLB.Output(display_name="model_3d"), cio.String.Output("report")],
        )

    @classmethod
    def execute(cls, mira_ccm, moge_geometry, upright, snap_to_support, add_floor, seed, floor=None, meshes=None) -> cio.NodeOutput:
        # ComfyUI runs nodes in inference mode; Mira's gravity fit optimises yaw with Adam, so its tensors must be
        # ordinary (autograd-capable) tensors created outside inference mode.
        with torch.inference_mode(False), torch.enable_grad():
            return cls._assemble(mira_ccm, moge_geometry, upright, snap_to_support, add_floor, seed, floor, meshes)

    @classmethod
    def _assemble(cls, mira_ccm, moge_geometry, upright, snap_to_support, add_floor, seed, floor, meshes) -> cio.NodeOutput:
        import trimesh
        mods = mira_runtime.modules()
        solve, placement, floor_mod = mods["solve"], mods["placement"], mods["floor"]
        np.random.seed(int(seed))
        torch.manual_seed(int(seed))
        ccm = torch.from_numpy(np.asarray(mira_ccm["ccm"], dtype=np.float32))
        count = ccm.shape[0]
        size = ccm.shape[-1]
        points = moge_geometry["points"][0].float().cpu().clone()
        geo_mask = moge_geometry.get("mask")
        geo_depth = moge_geometry.get("depth")
        if tuple(points.shape[:2]) != (size, size):
            logging.warning("%s MoGe geometry is %s, resampling to %d px (connect the 518 px scene to MoGe)", TAG,
                            tuple(points.shape[:2]), size)
            points = F.interpolate(points.permute(2, 0, 1)[None], size=(size, size), mode="nearest")[0].permute(1, 2, 0)
            geo_mask = None if geo_mask is None else F.interpolate(geo_mask[:1, None].float(), size=(size, size), mode="nearest")[:, 0] > 0.5
            geo_depth = None
        camera_np, valid_np = camera_points_from_moge(points.numpy(), None if geo_mask is None else geo_mask[0].cpu().numpy(),
                                                      None if geo_depth is None else geo_depth[0].float().cpu().numpy())
        fov_x = fov_x_from_intrinsics(moge_geometry["intrinsics"][0].cpu().numpy(), size) if "intrinsics" in moge_geometry else math.radians(60)
        cam = torch.from_numpy(camera_np)[None].expand(count, -1, -1, -1)
        valid = torch.from_numpy(valid_np)[None].expand(count, -1, -1)
        masks = (ccm.abs().sum(dim=1, keepdim=True) > 1e-6).float()
        initial = solve.solve_similarity_transforms(ccm, cam, valid, masks)
        to_matrix = lambda t: np.asarray(t["transform_matrix"].detach().cpu().numpy() if torch.is_tensor(t["transform_matrix"]) else t["transform_matrix"], dtype=np.float64)  # noqa: E731
        initial_camera = [to_matrix(t) for t in initial]

        report = {"objects": count, "fov_x_deg": round(math.degrees(fov_x), 2), "mira_commit": mira_ccm.get("commit")}
        floor_np = None if floor is None else (floor[0].float().cpu().numpy() > 0.5)
        plane = None
        if floor_np is not None and floor_np.shape != (size, size):
            floor_np = np.asarray(Image.fromarray(floor_np.astype(np.uint8) * 255).resize((size, size), Image.Resampling.NEAREST)) > 127
        if floor_np is not None:
            candidates = floor_np & valid_np
            floor_points = camera_np[candidates].astype(np.float64)
            if len(floor_points) >= 500:
                plane = floor_mod.fit_floor_plane(floor_points, threshold=0.03, iterations=1000, min_inliers=500,
                                                  seed=int(seed), ransac_max_points=50000)
            report["floor_pixels"] = int(candidates.sum())
        if plane is not None:
            camera_to_floor = floor_mod.make_floor_transform(plane)
            report["floor"] = {"inliers": plane["num_inliers"], "median_residual_m": round(plane["median_residual"], 4),
                               "normal_camera": [round(float(x), 4) for x in plane["normal"]]}
            inliers = np.zeros((size, size), dtype=bool)
            rows, cols = np.nonzero(floor_np & valid_np)
            inliers[rows[plane["inlier_mask"]], cols[plane["inlier_mask"]]] = True
        else:
            # No usable floor: camera +Y is up, the floor sits under the lowest object point.
            lowest = min((float(np.percentile(camera_np[(masks[i, 0].numpy() > 0) & valid_np][:, 1], 2))
                          for i in range(count) if ((masks[i, 0].numpy() > 0) & valid_np).any()), default=0.0)
            camera_to_floor = np.eye(4)
            camera_to_floor[1, 3] = -lowest
            inliers = None
            report["floor"] = "no floor mask / fit failed: camera up axis, floor under the lowest object"

        flags, tilts = upright_flags(initial_camera, camera_to_floor, upright)
        gravity = solve.solve_similarity_transforms_gravity(ccm, cam, valid, masks, camera_to_floor, flags,
                                                            initial_transforms=initial)
        gravity_floor = [to_matrix(t) for t in gravity]

        items, hulls = [], []
        if meshes is not None:
            from comfy_extras.nodes_save_3d import get_mesh_batch_item, mesh_item_to_glb_bytes
            if int(meshes.vertices.shape[0]) != count:
                raise ValueError(f"{int(meshes.vertices.shape[0])} meshes for {count} objects (same order as the masks)")
            for i in range(count):
                vertices = get_mesh_batch_item(meshes, i)[0].float().cpu().numpy()
                canonical = vertices @ YUP_TO_CANONICAL[:3, :3].T
                hulls.append(trimesh.Trimesh(canonical, process=False).convex_hull)
                glb = mesh_item_to_glb_bytes(meshes, i)
                items.append(trimesh.load(io.BytesIO(glb), file_type="glb", force="scene"))
        else:
            for i in range(count):
                mesh = voxel_mesh(mira_ccm["voxel_coords"][i], PALETTE[i % len(PALETTE)])
                if mesh is None:
                    mesh = trimesh.creation.box((0.05, 0.05, 0.05))
                items.append(mesh)
                hulls.append(mesh.convex_hull)
        hull_vertices = [np.asarray(h.vertices) for h in hulls]

        graph = support_graph(hull_vertices, gravity_floor) if snap_to_support else {"nodes": [], "edges": []}
        final_floor, decisions, collisions = placement.create_placement_backend("geometry").optimize(
            hulls, gravity_floor, graph, 0.9)

        objects = []
        for i in range(count):
            transform = final_floor[i] @ (YUP_TO_CANONICAL if meshes is not None else np.eye(4))
            objects.append((f"object_{i:03d}", items[i], transform))
        floor_geometry = None
        placed = [h @ final_floor[i][:3, :3].T + final_floor[i][:3, 3] for i, h in enumerate(hull_vertices)]
        if add_floor:
            center, side = floor_extent(placed)
            texture = floor_texture(mira_ccm["scene"], inliers if inliers is not None else np.zeros((size, size), bool))
            floor_geometry = floor_mesh(center, side, texture, repeat=side)
            report["floor_side_m"] = round(side, 3)
        glb = compose_scene_glb(objects, floor_geometry, camera=(camera_to_floor, fov_x, 1.0))

        by_child = {d["child"]: d for d in decisions}
        report["placement"] = []
        for i in range(count):
            scale = float(np.linalg.norm(final_floor[i][:3, 0]))
            low, high = placed[i].min(axis=0), placed[i].max(axis=0)
            decision = by_child.get(f"object_{i:03d}")
            report["placement"].append({
                "object": i, "upright": flags[i], "tilt_deg": round(tilts[i], 1), "scale_m": round(scale, 3),
                "size_m": [round(float(x), 3) for x in (high - low)], "bottom_y_m": round(float(low[1]), 3),
                "support": None if decision is None else f"{decision.get('parent')} ({decision.get('status')}, {decision.get('reason')})",
            })
        report["aabb_overlaps"] = len(collisions.get("pairs", []))
        report["camera_to_floor"] = np.round(camera_to_floor, 5).tolist()
        text = json.dumps(report, indent=1, ensure_ascii=False)
        logging.info("%s scene: %d objects, %d support moves, %d overlaps", TAG, count,
                     sum(1 for d in decisions if d.get("status") == "applied"), report["aabb_overlaps"])
        return cio.NodeOutput(Types.File3D(io.BytesIO(glb), file_format="glb"), text)


class MiraSceneExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[cio.ComfyNode]]:
        return [DaWMiraPrepareImage, DaWMiraMasks, DaWMiraLoadCCM, DaWMiraCCM, DaWMiraTrellisObjects, DaWMiraAssembleScene]


async def comfy_entrypoint() -> MiraSceneExtension:
    return MiraSceneExtension()
