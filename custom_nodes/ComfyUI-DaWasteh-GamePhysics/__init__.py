"""Conservative CPU collision export for generated ComfyUI game meshes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import torch
import folder_paths
from comfy_api.latest import ComfyExtension, io, Types
from .geometry import collision_proxy, godot_scene


class DaWCollisionProxy(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWCollisionProxy", display_name="DaW Game Collision Proxy (CPU)",
            category="DaWasteh/3d/physics", is_output_node=True,
            description="Build a conservative convex collider and export a real Godot 4 physics scene. One solid hull fills doorways and other concavities; not suitable for walkable buildings or articulated characters. Input units/axes are preserved. CPU only.",
            inputs=[io.Mesh.Input("mesh"), io.Combo.Input("mode", options=["convex_hull", "box"]),
                    io.Int.Input("max_vertices", default=128, min=8, max=4096),
                    io.Float.Input("margin", default=0.002, min=0, max=1, step=0.001),
                    io.Combo.Input("body_type", options=["StaticBody3D", "RigidBody3D"]),
                    io.Float.Input("mass", default=1.0, min=0.001, max=100000),
                    io.String.Input("filename_prefix", default="GameDev/Collision/asset")],
            outputs=[io.Mesh.Output(display_name="collision_mesh"), io.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, mesh, mode, max_vertices, margin, body_type, mass, filename_prefix):
        if mesh.vertices.shape[0] != 1:
            raise ValueError("Collision export accepts exactly one mesh")
        vertices = mesh.vertices[0]
        if mesh.vertex_counts is not None:
            vertices = vertices[:int(mesh.vertex_counts[0])]
        if len(vertices) > 200_000:
            raise ValueError("Feed the simplified game mesh, not the dense neural reference (>200k vertices)")
        p, faces, report = collision_proxy(vertices.detach().cpu().numpy(), mode, max_vertices, margin)
        text = godot_scene(p, body_type, mass)
        output = Path(folder_paths.get_output_directory()).resolve()
        # Reject absolute/escaping prefixes before Comfy's path helper is called.
        rel = Path(filename_prefix)
        if rel.is_absolute() or ':' in filename_prefix or '..' in rel.parts:
            raise ValueError("filename_prefix must stay inside ComfyUI/output")
        directory, filename, _, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, str(output))
        directory = Path(directory).resolve()
        if not directory.is_relative_to(output):
            raise ValueError("Output directory escapes ComfyUI/output")
        directory.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix=filename + "_", suffix=".tscn", dir=directory)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        report.update({"godot_scene": Path(path).relative_to(output).as_posix(), "body_type": body_type,
                       "mass_kg": mass if body_type == "RigidBody3D" else None,
                       "axes_units": "Input coordinates preserved; align with the exported visual mesh and set scale before production."})
        report_text = json.dumps(report, ensure_ascii=False, indent=2)
        Path(path).with_suffix('.json').write_text(report_text + '\n', encoding='utf-8')
        collider = Types.MESH(vertices=torch.from_numpy(p)[None], faces=torch.from_numpy(faces)[None])
        return io.NodeOutput(collider, report_text)


class GamePhysicsExtension(ComfyExtension):
    async def get_node_list(self):
        return [DaWCollisionProxy]


async def comfy_entrypoint():
    return GamePhysicsExtension()
