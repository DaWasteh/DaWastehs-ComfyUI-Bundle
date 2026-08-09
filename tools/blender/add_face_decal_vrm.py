"""Add a source-faithful animated facial decal to a rigged VRM0 avatar."""
import bpy
import json
import sys
from pathlib import Path

args = sys.argv[sys.argv.index("--") + 1 :]
if len(args) != 5:
    raise SystemExit("expected: input_blend face_rgba output_blend output_vrm report")
input_blend, face_path, output_blend, output_vrm, report_path = map(Path, args)
bpy.ops.wm.open_mainfile(filepath=str(input_blend))
arm = next(obj for obj in bpy.data.objects if obj.type == "ARMATURE")
head_bone = next((bone.name for bone in arm.data.bones if bone.name.endswith(":Head")), None)
if head_bone is None:
    raise RuntimeError("humanoid Head bone is missing")

columns, rows = 13, 15
vertices = []
uvs = []
for row in range(rows):
    v = row / (rows - 1)
    z = 1.205 + 0.29 * v
    for column in range(columns):
        u = column / (columns - 1)
        nx = u * 2.0 - 1.0
        x = nx * 0.145
        # Head-bone skin export mirrors this local axis. The round-tripped VRM
        # therefore places the authored -Y shell just in front of the +Y face.
        y = -0.164 + 0.022 * nx * nx
        vertices.append((x, y, z))
        uvs.append((u, v))
faces = []
for row in range(rows - 1):
    for column in range(columns - 1):
        a = row * columns + column
        faces.append((a, a + 1, a + 1 + columns, a + columns))
mesh = bpy.data.meshes.new("Img00031FaceDecalMesh")
mesh.from_pydata(vertices, [], faces)
mesh.update()
decal = bpy.data.objects.new("Img00031FaceDecal", mesh)
bpy.context.collection.objects.link(decal)
uv_layer = mesh.uv_layers.new(name="Img00031FaceDecalUV")
for polygon in mesh.polygons:
    for loop_index in polygon.loop_indices:
        uv_layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]

image = bpy.data.images.load(str(face_path), check_existing=False)
image.pack()
material = bpy.data.materials.new("Img00031FaceDecalPBR")
material.use_nodes = True
material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
if hasattr(material, "surface_render_method"):
    material.surface_render_method = "DITHERED"
elif hasattr(material, "blend_method"):
    material.blend_method = "BLEND"
nodes = material.node_tree.nodes
links = material.node_tree.links
for node in list(nodes):
    nodes.remove(node)
output = nodes.new("ShaderNodeOutputMaterial")
bsdf = nodes.new("ShaderNodeBsdfPrincipled")
texture = nodes.new("ShaderNodeTexImage")
texture.image = image
texture.interpolation = "Linear"
uv_map = nodes.new("ShaderNodeUVMap")
uv_map.uv_map = uv_layer.name
bsdf.inputs["Metallic"].default_value = 0.0
bsdf.inputs["Roughness"].default_value = 0.65
bsdf.inputs["Emission Strength"].default_value = 0.22
links.new(uv_map.outputs["UV"], texture.inputs["Vector"])
links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
links.new(texture.outputs["Color"], bsdf.inputs["Emission Color"])
links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
mesh.materials.append(material)

head_group = decal.vertex_groups.new(name=head_bone)
head_group.add(range(len(mesh.vertices)), 1.0, "REPLACE")
modifier = decal.modifiers.new("HumanoidHeadArmature", "ARMATURE")
modifier.object = arm
decal.parent = arm

basis = decal.shape_key_add(name="Basis")
changed = {}

def add_key(name, transform):
    key = decal.shape_key_add(name=name)
    count = 0
    for index, point in enumerate(key.data):
        u, v = uvs[index]
        if transform(point.co, u, v):
            count += 1
    changed[name] = count


def blink(side):
    def transform(coordinate, u, v):
        on_side = side == 0 or (side > 0 and u >= 0.5) or (side < 0 and u <= 0.5)
        if on_side and 0.55 < v < 0.70 and abs(u - 0.5) < 0.43:
            eye_z = 1.205 + 0.29 * 0.625
            coordinate.z = eye_z + (coordinate.z - eye_z) * 0.22
            return True
        return False
    return transform


def mouth(kind):
    def transform(coordinate, u, v):
        if 0.18 < v < 0.42 and abs(u - 0.5) < 0.31:
            strength = max(0.0, 1.0 - abs(u - 0.5) / 0.31)
            if kind == "A":
                coordinate.z -= 0.020 * strength * max(0.0, 0.36 - v) / 0.18
            elif kind == "O":
                coordinate.x *= 0.90
                coordinate.z -= 0.010 * strength
            elif kind == "I":
                coordinate.x *= 1.06
            elif kind == "U":
                coordinate.x *= 0.94
                coordinate.z -= 0.006 * strength
            elif kind == "E":
                coordinate.x *= 1.04
                coordinate.z -= 0.005 * strength
            return True
        return False
    return transform

add_key("Blink", blink(0))
add_key("Blink_L", blink(1))
add_key("Blink_R", blink(-1))
for name in ("A", "I", "U", "E", "O"):
    add_key(name, mouth(name))

extension = arm.data.vrm_addon_extension
if extension.spec_version != "0.0":
    raise RuntimeError(f"expected VRM0, got {extension.spec_version}")
groups = {group.name: group for group in extension.vrm0.blend_shape_master.blend_shape_groups}
for name in changed:
    group = groups.get(name)
    if group is None:
        group = extension.vrm0.blend_shape_master.blend_shape_groups.add()
        group.name = name
        group.preset_name = name.lower() if name in {"A", "I", "U", "E", "O"} else (
            "blink_l" if name == "Blink_L" else "blink_r" if name == "Blink_R" else "blink"
        )
    bind = group.binds.add()
    bind.mesh.mesh_object_name = decal.name
    bind.index = name
    bind.weight = 1.0

extension.vrm0.meta.title = "Local high-realism avatar with source-faithful face detail"
bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
bpy.ops.export_scene.vrm(filepath=str(output_vrm), armature_object_name=arm.name)
report_path.write_text(
    json.dumps(
        {
            "decal": decal.name,
            "head_bone": head_bone,
            "vertices": len(mesh.vertices),
            "faces": len(mesh.polygons),
            "shape_keys": changed,
            "face_texture": str(face_path),
            "output_vrm": str(output_vrm),
        },
        indent=2,
    ),
    encoding="utf-8",
)
