"""Blender script: four calibrated views (front, left, back, right) of a procedural object for the Pixal3D MultiView example.

The MultiView workflow needs rig renders, not invented views: 90 degrees apart, same scale, black background, horizontal
FOV 20 degrees. The camera rig is copied from ComfyUI's Pixal3DMultiViewConditioning (comfy_extras/nodes_trellis2.py):
Z up, the object normalised to the unit cube, front camera at -Y, left at +X, back at +Y, right at -X, distance
1.1 * 0.5 / tan(fov / 2). The object is a mailbox on a post: door in front, flag on its right, house number on its left,
so every view shows something the others do not.

    blender -b --factory-startup -P tools/examples/blender_multiview_views.py -- <out_dir> [prefix]
"""
import math
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[0] if args else "."
PREFIX = args[1] if len(args) > 1 else "mv_mailbox"
FOV, PAD, SIZE = 20.0, 1.1, 1024
VIEWS = {"front": 0.0, "left": 90.0, "back": 180.0, "right": 270.0}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True  # deprecated no-op from Blender 5.0, needed before
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def add(obj, mat):
    obj.data.materials.append(mat)
    if obj.type == "MESH" and len(obj.data.polygons) > 12:
        bpy.ops.object.shade_smooth_by_angle()  # round sides smooth, flat caps stay sharp
    return obj


def box(loc, dims, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.object
    obj.scale = dims
    return add(obj, mat)


def cylinder(loc, radius, depth, rotation, mat, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    return add(bpy.context.object, mat)


RED = material("mailbox red", (0.62, 0.04, 0.03), metallic=0.3, roughness=0.35)
DOOR = material("door red", (0.45, 0.03, 0.02), metallic=0.3, roughness=0.4)
STEEL = material("steel", (0.8, 0.8, 0.82), metallic=1.0, roughness=0.25)
WOOD = material("wood", (0.33, 0.19, 0.08), roughness=0.8)
STONE = material("stone", (0.42, 0.42, 0.4), roughness=0.9)
FLAG = material("flag yellow", (0.95, 0.68, 0.03), roughness=0.45)
WHITE = material("white", (0.92, 0.92, 0.9), roughness=0.5)

# base slab and a short post, so the mailbox itself fills most of the frame
P = 0.06 + 0.55  # top of the post
box((0, 0, 0.03), (0.5, 0.5, 0.06), STONE)
box((0, 0, 0.06 + 0.275), (0.1, 0.1, 0.55), WOOD)
# body: box bottom plus half cylinder top along Y (the lower half of the cylinder sits inside the box). The box is a
# little shorter than the cylinder and the door box a little thinner than the door disc: coplanar faces render black.
box((0, 0, P + 0.07), (0.28, 0.596, 0.14), RED)
cylinder((0, 0, P + 0.14), 0.14, 0.6, (math.radians(90), 0, 0), RED)
# front door (-Y) with a handle
cylinder((0, -0.305, P + 0.14), 0.143, 0.02, (math.radians(90), 0, 0), DOOR)
box((0, -0.305, P + 0.07), (0.286, 0.016, 0.14), DOOR)
box((0, -0.325, P + 0.24), (0.08, 0.025, 0.025), STEEL)
# flag on the mailbox's right side: it faces -Y, so its right is -X
box((-0.152, 0.12, P + 0.16), (0.012, 0.02, 0.3), STEEL)
box((-0.155, 0.19, P + 0.28), (0.008, 0.14, 0.08), FLAG)
# house number on its left side (+X)
bpy.ops.object.text_add(location=(0.141, 0.0, P + 0.07), rotation=(math.radians(90), 0, math.radians(90)))
number = bpy.context.object
number.data.body = "42"
number.data.align_x, number.data.align_y = "CENTER", "CENTER"
number.data.size, number.data.extrude = 0.11, 0.004
add(number, WHITE)

# normalise into the unit cube around the origin, like the rig expects (matrix_world is stale until the update)
bpy.context.view_layer.update()
objs = [o for o in scene.objects]
lo = Vector((min((o.matrix_world @ Vector(c))[i] for o in objs for c in o.bound_box) for i in range(3)))
hi = Vector((max((o.matrix_world @ Vector(c))[i] for o in objs for c in o.bound_box) for i in range(3)))
bpy.ops.object.empty_add(location=(lo + hi) / 2)
root = bpy.context.object
bpy.context.view_layer.update()
for o in objs:
    o.parent = root
    o.matrix_parent_inverse = root.matrix_world.inverted()
root.location = (0, 0, 0)
root.scale = [1.0 / max(hi - lo)] * 3
bpy.context.view_layer.update()
DISTANCE = PAD * 0.5 / math.tan(math.radians(FOV) / 2.0)


def widest(scale):
    """Largest half-extent of the object in any view, in frame halves (perspective: near parts look bigger)."""
    corners = [(o.matrix_world @ Vector(c)) * scale for o in objs for c in o.bound_box]
    t = math.tan(math.radians(FOV) / 2.0)
    worst = 0.0
    for az in VIEWS.values():
        a = math.radians(az)
        right, back = Vector((math.cos(a), math.sin(a), 0)), Vector((math.sin(a), -math.cos(a), 0))
        for p in corners:
            depth = DISTANCE - p.dot(back)
            worst = max(worst, abs(p.dot(right)) / (depth * t), abs(p.z) / (depth * t))
    return worst


# the unit cube alone overshoots the frame through perspective; shrink until the widest view spans 1/PAD of it
lo_s, hi_s = 0.3, 1.0
for _ in range(30):
    mid = (lo_s + hi_s) / 2
    lo_s, hi_s = (mid, hi_s) if widest(mid) < 1.0 / PAD else (lo_s, mid)
root.scale = [root.scale[0] * lo_s] * 3
bpy.context.view_layer.update()
print(f"fit scale {lo_s:.3f}")

# world: grey for lighting, black where the camera looks straight at it (the rig wants a black background)
world = bpy.data.worlds.new("rig")
world.use_nodes = True
scene.world = world
nodes, links = world.node_tree.nodes, world.node_tree.links
nodes.clear()
lit = nodes.new("ShaderNodeBackground")
lit.inputs["Color"].default_value = (0.55, 0.55, 0.55, 1.0)
black = nodes.new("ShaderNodeBackground")
black.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
path = nodes.new("ShaderNodeLightPath")
mix = nodes.new("ShaderNodeMixShader")
out = nodes.new("ShaderNodeOutputWorld")
links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
links.new(lit.outputs["Background"], mix.inputs[1])
links.new(black.outputs["Background"], mix.inputs[2])
links.new(mix.outputs["Shader"], out.inputs["Surface"])
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(40), math.radians(15), math.radians(-30)))
bpy.context.object.data.energy = 3.0

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 96
scene.cycles.use_denoising = True
scene.render.threads_mode, scene.render.threads = "FIXED", 12
scene.render.resolution_x = scene.render.resolution_y = SIZE
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"

bpy.ops.object.camera_add()
cam = bpy.context.object
scene.camera = cam
cam.data.sensor_fit = "HORIZONTAL"
cam.data.angle = math.radians(FOV)
for name, az in VIEWS.items():
    a = math.radians(az)
    cam.location = (DISTANCE * math.sin(a), -DISTANCE * math.cos(a), 0.0)
    cam.rotation_euler = (math.radians(90), 0.0, a)
    scene.render.filepath = f"{OUT}/{PREFIX}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("wrote", scene.render.filepath)
