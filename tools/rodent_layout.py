#!/usr/bin/env python3
"""Apply a compact, deterministic RODENT Method layout to ComfyUI workflows.

RODENT follows the visual organization popularized by Nerdy Rodent: functional
modules, stable stage colors, clear labels, and a readable left-to-right flow.
The pass changes presentation only; node IDs, widgets, links, modes, and graph
interfaces remain intact.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict, deque
from typing import Any, Iterable

RODENT_KEY = "dawasteh_rodent_layout"
RODENT_VERSION = 1
GRID = 20.0
NODE_GAP_X = 80.0
NODE_GAP_Y = 40.0
STAGE_GAP = 120.0
GROUP_PAD_X = 40.0
GROUP_PAD_TOP = 80.0
GROUP_PAD_BOTTOM = 40.0
MAX_ROWS = 8
REFERENCE_COLUMNS = 4

STAGE_ORDER = ("R", "O", "D", "E", "N", "T")
STAGE_LABELS = {
    "R": "README & RUNTIME",
    "O": "ORIGIN INPUTS",
    "D": "DEPENDENCIES",
    "E": "ENCODE & CONDITION",
    "N": "NEURAL EXECUTION",
    "T": "TRANSFORM & TERMINAL",
}
STAGE_COLORS = {
    "R": "#5B6472",
    "O": "#7C5CC4",
    "D": "#3F789E",
    "E": "#C68B31",
    "N": "#B85C5C",
    "T": "#3F9E6D",
}
DOC_TYPES = {"Note", "MarkdownNote", "PixaromaNote"}
SELECTOR_TYPES = {"SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"}
RUNTIME_TOKENS = (
    "timer", "multigpudevicecontrol", "groupsmuter", "groupmuter", "queue", "runtime",
    "purge", "cleanup", "unload", "releasevram", "persistent", "spout",
)
INPUT_TOKENS = (
    "loadimage", "loadaudio", "loadvideo", "webcam", "primitive", "prompt", "seed",
    "emptylatent", "emptyimage", "dimension", "width", "height", "duration", "string",
    "textinput", "folder", "directory", "maskeditor",
)
DEPENDENCY_TOKENS = (
    "checkpointloader", "unetloader", "modelloader", "cliploader", "vaeloader", "loraloader",
    "controlnetloader", "ipadaptermodelloader", "clipvisionloader", "downloadandload", "gguf",
    "selectmodeldevice", "selectclipdevice", "selectvaedevice", "modelpatch", "modelsampling",
)
ENCODE_TOKENS = (
    "encode", "conditioning", "condition", "controlnetapply", "ipadapter", "preprocessor",
    "cropper", "segment", "detector", "pose", "guide", "reference", "latentprepare",
)
NEURAL_TOKENS = (
    "ksampler", "sampler", "scheduler", "guider", "noise", "denoise", "train", "generator",
    "diffusion", "director", "spectrum", "sigmashift", "sampling", "inference", "process",
)
TERMINAL_TOKENS = (
    "decode", "save", "preview", "combine", "composite", "upscale", "resize", "scale",
    "stitch", "blend", "compare", "export", "write", "output", "rmbg", "background",
    "filter", "transform", "mux", "audioseparation", "play", "showtext",
)


def _number(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _node_size(node: dict[str, Any]) -> tuple[float, float]:
    size = node.get("size")
    if not isinstance(size, list):
        return 280.0, 140.0
    return max(80.0, _number(size[0] if size else None, 280.0)), max(
        40.0, _number(size[1] if len(size) > 1 else None, 140.0)
    )


def _node_pos(node: dict[str, Any]) -> tuple[float, float]:
    pos = node.get("pos")
    if not isinstance(pos, list):
        return 0.0, 0.0
    return _number(pos[0] if pos else None, 0.0), _number(pos[1] if len(pos) > 1 else None, 0.0)


def _snap(value: float) -> float:
    return round(value / GRID) * GRID


def _stable_id(value: Any) -> tuple[int, str]:
    if isinstance(value, int):
        return 0, f"{value:020d}"
    return 1, str(value)


def _link_parts(link: Any) -> tuple[Any, Any] | None:
    if isinstance(link, list) and len(link) >= 4:
        return link[1], link[3]
    if isinstance(link, dict):
        origin = link.get("origin_id", link.get("originId", link.get("source")))
        target = link.get("target_id", link.get("targetId", link.get("target")))
        if isinstance(origin, dict):
            origin = origin.get("id", origin.get("node_id", origin.get("nodeId")))
        if isinstance(target, dict):
            target = target.get("id", target.get("node_id", target.get("nodeId")))
        return origin, target
    return None


def _topology_depths(graph: dict[str, Any]) -> dict[Any, int]:
    ids = {node.get("id") for node in graph.get("nodes", [])}
    incoming: dict[Any, set[Any]] = {node_id: set() for node_id in ids}
    outgoing: dict[Any, set[Any]] = {node_id: set() for node_id in ids}
    for link in (graph.get("links", []) or []):
        parts = _link_parts(link)
        if not parts:
            continue
        source, target = parts
        if source in ids and target in ids and source != target:
            incoming[target].add(source)
            outgoing[source].add(target)
    indegree = {node_id: len(values) for node_id, values in incoming.items()}
    queue = deque(sorted((node_id for node_id, degree in indegree.items() if degree == 0), key=_stable_id))
    depths = {node_id: 0 for node_id in ids}
    visited: set[Any] = set()
    while queue:
        source = queue.popleft()
        visited.add(source)
        for target in sorted(outgoing[source], key=_stable_id):
            depths[target] = max(depths[target], depths[source] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    # Cycles retain a deterministic depth derived from their non-cyclic inputs.
    for node_id in sorted(ids - visited, key=_stable_id):
        external = [depths[source] + 1 for source in incoming[node_id] if source in visited]
        depths[node_id] = max(external, default=0)
    return depths


def _compact_type(node: dict[str, Any]) -> str:
    return re.sub(r"[^a-z0-9]", "", f"{node.get('type', '')} {node.get('title', '')}".lower())


def classify_stage(node: dict[str, Any]) -> str:
    """Classify one execution node into a stable RODENT stage."""
    node_type = str(node.get("type", ""))
    compact = _compact_type(node)
    if node_type in DOC_TYPES or any(token in compact for token in RUNTIME_TOKENS):
        return "R"
    if node_type in SELECTOR_TYPES or any(token in compact for token in DEPENDENCY_TOKENS):
        return "D"
    if any(token in compact for token in TERMINAL_TOKENS):
        return "T"
    if any(token in compact for token in NEURAL_TOKENS):
        return "N"
    if any(token in compact for token in ENCODE_TOKENS):
        return "E"
    if any(token in compact for token in INPUT_TOKENS):
        return "O"
    output_types = {str(item.get("type", "")) for item in node.get("outputs", [])}
    input_types = {str(item.get("type", "")) for item in node.get("inputs", [])}
    if output_types & {"MODEL", "CLIP", "VAE", "CONTROL_NET", "CLIP_VISION"}:
        return "D"
    if output_types & {"CONDITIONING", "GUIDER", "SIGMAS", "NOISE"}:
        return "E"
    if input_types & {"MODEL", "GUIDER", "SIGMAS", "NOISE"}:
        return "N"
    if not any(item.get("link") is not None for item in node.get("inputs", [])):
        return "O"
    return "T"


def _generated_reference(node: dict[str, Any]) -> bool:
    return bool(node.get("properties", {}).get("dawasteh_generated_note"))


def _pack_nodes(
    nodes: list[dict[str, Any]], start_x: float, start_y: float, *, columns: int | None = None,
    depths: dict[Any, int] | None = None,
) -> tuple[float, float, float, float]:
    """Pack nodes into deterministic compact columns and return their bounds."""
    if not nodes:
        return start_x, start_y, start_x, start_y
    depth_map = depths or {}
    ordered = sorted(
        nodes,
        key=lambda node: (
            depth_map.get(node.get("id"), 0),
            _stable_id(node.get("id")),
            str(node.get("type", "")),
        ),
    )
    requested_columns = columns or max(1, math.ceil(len(ordered) / MAX_ROWS))
    row_count = max(1, math.ceil(len(ordered) / requested_columns))
    buckets = [ordered[index * row_count:(index + 1) * row_count] for index in range(requested_columns)]
    buckets = [bucket for bucket in buckets if bucket]
    x = _snap(start_x)
    right = x
    bottom = _snap(start_y)
    for bucket in buckets:
        width = max(_node_size(node)[0] for node in bucket)
        y = _snap(start_y)
        for node in bucket:
            node["pos"] = [_snap(x), _snap(y)]
            _, height = _node_size(node)
            y = _snap(y + height + NODE_GAP_Y)
            bottom = max(bottom, y - NODE_GAP_Y)
        right = max(right, x + width)
        x = _snap(x + width + NODE_GAP_X)
    return _snap(start_x), _snap(start_y), _snap(right), _snap(bottom)


def _group(group_id: int, title: str, color: str, bounds: tuple[float, float, float, float]) -> dict[str, Any]:
    left, top, right, bottom = bounds
    return {
        "id": group_id,
        "title": title,
        "bounding": [
            _snap(left - GROUP_PAD_X),
            _snap(top - GROUP_PAD_TOP),
            _snap((right - left) + GROUP_PAD_X * 2),
            _snap((bottom - top) + GROUP_PAD_TOP + GROUP_PAD_BOTTOM),
        ],
        "color": color,
        "font_size": 24,
        "flags": {},
    }


def _layout_standard(graph: dict[str, Any]) -> list[str]:
    nodes = graph.get("nodes", [])
    depths = _topology_depths(graph)
    generated = [node for node in nodes if _generated_reference(node)]
    manual_runtime = [
        node for node in nodes
        if not _generated_reference(node) and classify_stage(node) == "R"
    ]
    stage_nodes = {
        stage: [
            node for node in nodes
            if not _generated_reference(node) and node not in manual_runtime and classify_stage(node) == stage
        ]
        for stage in STAGE_ORDER[1:]
    }

    groups: list[dict[str, Any]] = []
    x = GROUP_PAD_X
    group_id = 1
    if manual_runtime:
        bounds = _pack_nodes(manual_runtime, x, GROUP_PAD_TOP, depths=depths)
        groups.append(_group(group_id, "R1 · README & RUNTIME", STAGE_COLORS["R"], bounds))
        x = groups[-1]["bounding"][0] + groups[-1]["bounding"][2] + STAGE_GAP
        group_id += 1

    for stage in STAGE_ORDER[1:]:
        members = stage_nodes[stage]
        if not members:
            continue
        bounds = _pack_nodes(members, x, GROUP_PAD_TOP, depths=depths)
        groups.append(_group(group_id, f"{stage}1 · {STAGE_LABELS[stage]}", STAGE_COLORS[stage], bounds))
        x = groups[-1]["bounding"][0] + groups[-1]["bounding"][2] + STAGE_GAP
        group_id += 1

    if generated:
        bounds = _pack_nodes(generated, x, GROUP_PAD_TOP, columns=min(REFERENCE_COLUMNS, len(generated)))
        groups.append(_group(group_id, "R9 · PARAMETER REFERENCE", STAGE_COLORS["R"], bounds))

    graph["groups"] = groups
    return []


def _membership(groups: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> dict[Any, list[dict[str, Any]]]:
    result: dict[Any, list[dict[str, Any]]] = {group.get("id"): [] for group in groups}
    for node in nodes:
        if _generated_reference(node):
            continue
        x, y = _node_pos(node)
        width, height = _node_size(node)
        center_x, center_y = x + width / 2, y + height / 2
        for group in groups:
            gx, gy, gw, gh = group.get("bounding", [0, 0, 0, 0])
            if _number(gx, 0) <= center_x <= _number(gx, 0) + _number(gw, 0) and _number(gy, 0) <= center_y <= _number(gy, 0) + _number(gh, 0):
                result[group.get("id")].append(node)
                break
    return result


def _layout_rgthree_groups(graph: dict[str, Any]) -> list[str]:
    """Compact authored groups without changing IDs/titles used by rgthree."""
    groups = graph.get("groups", []) or []
    nodes = graph.get("nodes", [])
    memberships = _membership(groups, nodes)
    assigned = {id(node) for values in memberships.values() for node in values}
    generated = [node for node in nodes if _generated_reference(node)]
    ungrouped = [node for node in nodes if id(node) not in assigned and not _generated_reference(node)]
    depths = _topology_depths(graph)

    x = GROUP_PAD_X
    if ungrouped:
        bounds = _pack_nodes(ungrouped, x, GROUP_PAD_TOP, depths=depths)
        x = bounds[2] + STAGE_GAP + GROUP_PAD_X
    ordered_groups = sorted(groups, key=lambda group: (_number(group.get("bounding", [0])[0], 0), _stable_id(group.get("id"))))
    for group in ordered_groups:
        members = memberships.get(group.get("id"), [])
        if not members:
            continue
        bounds = _pack_nodes(members, x, GROUP_PAD_TOP, depths=depths)
        stage_counts = Counter(classify_stage(node) for node in members)
        dominant = min(stage_counts, key=lambda stage: (-stage_counts[stage], STAGE_ORDER.index(stage)))
        compact = _group(int(group.get("id", 0)), str(group.get("title", "Functional module")), STAGE_COLORS[dominant], bounds)
        group.update(compact)
        x = group["bounding"][0] + group["bounding"][2] + STAGE_GAP
    if generated:
        _pack_nodes(generated, x, GROUP_PAD_TOP, columns=min(REFERENCE_COLUMNS, len(generated)))
    graph["groups"] = ordered_groups
    return ["rgthree-authored-group-ids-and-titles-preserved"]


def _layout_pixaroma_group_demo(graph: dict[str, Any]) -> list[str]:
    """Keep demo group geometry synchronized while placing migration controls safely."""
    controls = {
        node.get("id") for node in graph.get("nodes", [])
        if node.get("type") == "DaWMultiGPUDeviceControl"
    }
    movable = [
        node for node in graph.get("nodes", [])
        if node.get("id") in controls
        or node.get("properties", {}).get("dawasteh_note_for") in controls
    ]
    fixed = [node for node in graph.get("nodes", []) if node not in movable]
    if movable:
        right = max((_node_pos(node)[0] + _node_size(node)[0] for node in fixed), default=0.0)
        top = min((_node_pos(node)[1] for node in fixed), default=0.0)
        _pack_nodes(movable, right + STAGE_GAP, top)
    return ["pixaroma-group-demo-authored-geometry-preserved"]


def _topology_hash(graph: dict[str, Any]) -> str:
    payload = {
        "nodes": [
            {
                "id": node.get("id"),
                "type": node.get("type"),
                "mode": node.get("mode"),
                "inputs": node.get("inputs"),
                "outputs": node.get("outputs"),
                "widgets_values": node.get("widgets_values"),
            }
            for node in graph.get("nodes", [])
        ],
        "links": graph.get("links", []),
        "inputs": graph.get("inputs", []),
        "outputs": graph.get("outputs", []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _update_interfaces(graph: dict[str, Any]) -> None:
    if not graph.get("nodes"):
        return
    left = min(_node_pos(node)[0] for node in graph["nodes"])
    right = max(_node_pos(node)[0] + _node_size(node)[0] for node in graph["nodes"])
    top = min(_node_pos(node)[1] for node in graph["nodes"])
    for key, x in (("inputNode", left - 240.0), ("outputNode", right + 80.0)):
        interface = graph.get(key)
        if not isinstance(interface, dict):
            continue
        bounding = interface.get("bounding")
        if not isinstance(bounding, list) or len(bounding) < 4:
            continue
        bounding[0] = _snap(x)
        bounding[1] = _snap(top)
        for index, item in enumerate(graph.get("inputs" if key == "inputNode" else "outputs", []) or []):
            if isinstance(item.get("pos"), list):
                item["pos"] = [_snap(x + 120.0), _snap(top + 40.0 + index * GRID)]


def graph_children(workflow: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield workflow
    for child in workflow.get("definitions", {}).get("subgraphs", []) or []:
        yield from graph_children(child)


def apply_rodent_layout(workflow: dict[str, Any], workflow_key: str = "") -> int:
    """Apply RODENT layout recursively and return the number of laid-out graphs."""
    count = 0
    pixaroma_group_demo = "pixaroma-group-compare" in workflow_key.lower()
    for graph in graph_children(workflow):
        extra = graph.setdefault("extra", {})
        exceptions: list[str]
        if pixaroma_group_demo and graph is workflow and extra.get("pixaromaGroups"):
            exceptions = _layout_pixaroma_group_demo(graph)
        elif any("Groups Muter" in str(node.get("type", "")) for node in graph.get("nodes", [])):
            exceptions = _layout_rgthree_groups(graph)
            _update_interfaces(graph)
        else:
            exceptions = _layout_standard(graph)
            _update_interfaces(graph)
        marker = {
            "version": RODENT_VERSION,
            "method": "RODENT Method",
            "credit": "Nerdy Rodent",
            "algorithm": "rodent-v1",
            "grid": int(GRID),
            "node_gap": [int(NODE_GAP_X), int(NODE_GAP_Y)],
            "stage_gap": int(STAGE_GAP),
            "topology_sha256": _topology_hash(graph),
            "exceptions": exceptions,
        }
        extra[RODENT_KEY] = marker
        refinement = extra.get("dawasteh_workflow_refinement")
        if isinstance(refinement, dict):
            refinement.update({"layout": "rodent-v1", "x_scale": 1.0, "y_scale": 1.0, "gap": NODE_GAP_Y})
        count += 1
    return count
