# DaWasteh GamePhysics

ComfyUI `comfy_api.latest` nodes for the v1.1.8 model workflows.

- **DaWCollisionProxy**: CPU convex hull or conservative box from a simplified MESH. Exports collision MESH, JSON report and a real Godot 4 `ConvexPolygonShape3D` scene (StaticBody3D/RigidBody3D). Input coordinates are preserved. Complex hulls fall back to a box when the vertex budget is exceeded. No compound colliders, rigs or walkable concave interiors.
- **DaWVideoFrames**: bounded VideoHelperSuite decoding with an IMAGE-only return. Default: first five frames at 16fps, 848×480. Requires `VHS_LoadVideo`. Never caches VHS's lazy AUDIO map, avoiding the observed ComfyUI 0.35 RAM-cache crash when a reference has no audio. This does not patch unrelated VHS graphs or the ComfyUI cache globally.

Dependencies: ComfyUI/PyTorch, NumPy, SciPy; VideoHelperSuite for video loading. Copy the complete directory into `ComfyUI/custom_nodes` and restart. The bundle updater includes this pack.

[Model workflows, installation, licensing and acceptance limits](../../docs/MODEL_WORKFLOWS_V118.md).
