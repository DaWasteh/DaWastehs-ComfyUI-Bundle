#!/usr/bin/env python3
"""Migrate the complete workflow collection to the v0.9.2 presentation model.

The migration dissolves the former Dual-GPU folder, installs one central GPU
control in every canonical workflow, keeps curated split-device defaults where
they already existed, defaults all other workflows to the R9700, and applies
the deterministic RODENT Method layout credited to Nerdy Rodent.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from tools.generate_dual_gpu_workflows import (
        DEVICE_CONTROL_TYPE,
        FAMILIES,
        SELECTOR_OBJECT_INFO,
        _graphs,
        _localize_model_paths,
        _workflow_template_path,
        insert_device_selectors,
        install_central_device_control,
        install_run_timer,
    )
    from tools.integrate_duration_seconds import integrate_duration_seconds
    from tools.refine_workflows import (
        NOTE_PROPERTY,
        REFINEMENT_KEY,
        _subgraph_schemas,
        build_note_text,
        is_target,
        refine_graph,
    )
    from tools.rodent_layout import RODENT_KEY, apply_rodent_layout
    from tools.upgrade_v094 import ADAPTIVE_OBJECT_INFO, upgrade_workflow as upgrade_v094_workflow
    from tools.upgrade_v095 import (
        V095_OBJECT_INFO,
        addition_sources as v095_addition_sources,
        upgrade_workflow as upgrade_v095_workflow,
    )
    from tools.upgrade_v096 import V096_OBJECT_INFO, upgrade_workflow as upgrade_v096_workflow
    from tools.upgrade_v098 import upgrade_workflow as upgrade_v098_workflow
    from tools.upgrade_v099 import V099_OBJECT_INFO
    from tools.upgrade_v100 import (
        FACE_SWAP_PATH as V100_FACE_SWAP_PATH,
        FACE_SWAP_TEMPLATE as V100_FACE_SWAP_TEMPLATE,
        PERSON_SWAP_PATH as V100_PERSON_SWAP_PATH,
        PERSON_SWAP_TEMPLATE as V100_PERSON_SWAP_TEMPLATE,
        V100_OBJECT_INFO,
    )
    from tools.upgrade_v097 import (
        CREATURE_PATH as V097_CREATURE_PATH,
        ENVIRONMENT_PATH as V097_ENVIRONMENT_PATH,
        SOURCE_TEMPLATE as V097_SOURCE_TEMPLATE,
        V097_OBJECT_INFO,
        specialize_game_asset_template,
    )
except ModuleNotFoundError:  # Direct execution
    from generate_dual_gpu_workflows import (
        DEVICE_CONTROL_TYPE,
        FAMILIES,
        SELECTOR_OBJECT_INFO,
        _graphs,
        _localize_model_paths,
        _workflow_template_path,
        insert_device_selectors,
        install_central_device_control,
        install_run_timer,
    )
    from integrate_duration_seconds import integrate_duration_seconds
    from refine_workflows import (
        NOTE_PROPERTY,
        REFINEMENT_KEY,
        _subgraph_schemas,
        build_note_text,
        is_target,
        refine_graph,
    )
    from rodent_layout import RODENT_KEY, apply_rodent_layout
    from upgrade_v094 import ADAPTIVE_OBJECT_INFO, upgrade_workflow as upgrade_v094_workflow
    from upgrade_v095 import (
        V095_OBJECT_INFO,
        addition_sources as v095_addition_sources,
        upgrade_workflow as upgrade_v095_workflow,
    )
    from upgrade_v096 import V096_OBJECT_INFO, upgrade_workflow as upgrade_v096_workflow
    from upgrade_v098 import upgrade_workflow as upgrade_v098_workflow
    from upgrade_v099 import V099_OBJECT_INFO
    from upgrade_v100 import (
        FACE_SWAP_PATH as V100_FACE_SWAP_PATH,
        FACE_SWAP_TEMPLATE as V100_FACE_SWAP_TEMPLATE,
        PERSON_SWAP_PATH as V100_PERSON_SWAP_PATH,
        PERSON_SWAP_TEMPLATE as V100_PERSON_SWAP_TEMPLATE,
        V100_OBJECT_INFO,
    )
    from upgrade_v097 import (
        CREATURE_PATH as V097_CREATURE_PATH,
        ENVIRONMENT_PATH as V097_ENVIRONMENT_PATH,
        SOURCE_TEMPLATE as V097_SOURCE_TEMPLATE,
        V097_OBJECT_INFO,
        specialize_game_asset_template,
    )

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
DUAL_GPU_DIRECTORY = WORKFLOWS / "Dual GPU - R9700 + RX 9070 XT"
MIGRATION_KEY = "dawasteh_v092_collection"
MIGRATION_VERSION = 1
ALL_R9700 = {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"}

DELETED_PATHS = {
    "Reference to Video/MiniMax_H3_Spectrum_FL2VA_All_Supported_Inputs.json",
    "Reference to Video/MiniMax_H3_Spectrum_FL2VA_MAXIMUM_All_Supported_Inputs.json",
}


@dataclass(frozen=True)
class Addition:
    path: str
    template: str
    family: str
    devices: dict[str, str]


ADDITIONS = (
    Addition(
        "Text to Video/LTX25_INT8_ConvRot-Text-to-Video.json",
        "video_ltx2_5_t2v.json",
        "LTX 2.5 Text to Video",
        {"MODEL": "gpu:0", "CLIP": "gpu:1", "VAE": "gpu:1"},
    ),
    Addition(
        "Text+Image to Video/LTX25_INT8_ConvRot-Image-to-Video.json",
        "video_ltx2_5_i2v.json",
        "LTX 2.5 Image to Video",
        {"MODEL": "gpu:0", "CLIP": "gpu:1", "VAE": "gpu:1"},
    ),
    Addition(
        "Text+Image to Video/LTX25_INT8_ConvRot-First+Last-Frame-to-Video.json",
        "video_ltx2_5_flf2v.json",
        "LTX 2.5 First/Last Frame to Video",
        {"MODEL": "gpu:0", "CLIP": "gpu:1", "VAE": "gpu:1"},
    ),
    Addition(
        "Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json",
        "video_wan_animate2.json",
        "Wan Animate 2 Motion Transfer",
        {"MODEL": "gpu:0", "CLIP": "gpu:1", "VAE": "gpu:1"},
    ),
    Addition(
        V097_ENVIRONMENT_PATH,
        V097_SOURCE_TEMPLATE,
        "Pixal3D INT8 Buildings and Environment PBR for Godot",
        {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"},
    ),
    Addition(
        V097_CREATURE_PATH,
        V097_SOURCE_TEMPLATE,
        "Pixal3D INT8 Humanoids and Animals PBR for Godot",
        {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"},
    ),
    Addition(
        V100_FACE_SWAP_PATH,
        V100_FACE_SWAP_TEMPLATE,
        "Live Face Swap DirectML Spout OBS",
        {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"},
    ),
    Addition(
        V100_PERSON_SWAP_PATH,
        V100_PERSON_SWAP_TEMPLATE,
        "Live Person Swap Matting Voice DirectML Spout OBS",
        {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"},
    ),
)


def _load_object_info() -> dict[str, Any]:
    path = ROOT / "assets" / "live-avatar-v072" / "object-info.json"
    info = json.loads(path.read_text(encoding="utf-8"))
    info.update(SELECTOR_OBJECT_INFO)
    info.update(ADAPTIVE_OBJECT_INFO)
    info.update(V095_OBJECT_INFO)
    info.update(V096_OBJECT_INFO)
    info.update(V097_OBJECT_INFO)
    info.update(V099_OBJECT_INFO)
    info.update(V100_OBJECT_INFO)
    return info


OBJECT_INFO = _load_object_info()


def _curated_profiles() -> dict[str, tuple[str, dict[str, str], bool]]:
    profiles: dict[str, tuple[str, dict[str, str], bool]] = {}
    for family in FAMILIES:
        if not family.source:
            continue
        path = family.source
        if path in DELETED_PATHS:
            if "FL2VA" not in family.name:
                continue
            path = "Reference to Video/MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json"
        profiles[path] = (family.name, family.devices, family.h3_director)
    profiles["Music Generation/MiniMax_Music3_FP32-BF16-Text-to-Music.json"] = (
        "MiniMax Music 3",
        {"MODEL": "gpu:1", "CLIP": "gpu:0", "VAE": "gpu:1"},
        False,
    )
    for addition in ADDITIONS:
        profiles[addition.path] = (addition.family, addition.devices, False)
    # v1.1.1 (performance/rdna4/REPORT.md): measured device placement overrides.
    try:
        from tools.upgrade_v111 import E2B_LTX as _V111_LTX, E2_IMAGE as _V111_IMAGE
    except ModuleNotFoundError:  # direct execution from tools/
        from upgrade_v111 import E2B_LTX as _V111_LTX, E2_IMAGE as _V111_IMAGE
    for path in _V111_IMAGE:
        if path in profiles:
            name, _devices, h3 = profiles[path]
            profiles[path] = (name, {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"}, h3)
    for path in _V111_LTX:
        if path in profiles:
            name, _devices, h3 = profiles[path]
            profiles[path] = (name, {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:1"}, h3)
    # v1.1.2 (performance/rdna4/REPORT.md §9.4): measured placement of the remaining split workflows.
    try:
        from tools.upgrade_v112 import E2_REMAINING as _V112_E2
    except ModuleNotFoundError:  # direct execution from tools/
        from upgrade_v112 import E2_REMAINING as _V112_E2
    for path in _V112_E2:
        if path in profiles:
            name, _devices, h3 = profiles[path]
            profiles[path] = (name, {"MODEL": "gpu:0", "CLIP": "gpu:0", "VAE": "gpu:0"}, h3)
    return profiles


CURATED_PROFILES = _curated_profiles()


def _normalize_counters(workflow: dict[str, Any]) -> None:
    for graph in _graphs(workflow):
        numeric_nodes = [node.get("id") for node in graph.get("nodes", []) if isinstance(node.get("id"), int)]
        numeric_links = []
        for link in graph.get("links", []) or []:
            link_id = link[0] if isinstance(link, list) and link else link.get("id") if isinstance(link, dict) else None
            if isinstance(link_id, int):
                numeric_links.append(link_id)
        maximum_node = max(numeric_nodes, default=0)
        maximum_link = max(numeric_links, default=0)
        graph["last_node_id"] = max(int(graph.get("last_node_id", 0)), maximum_node)
        if "last_link_id" in graph or graph is workflow:
            graph["last_link_id"] = max(int(graph.get("last_link_id", 0)), maximum_link)
        state = graph.get("state")
        if isinstance(state, dict):
            state["lastNodeId"] = max(int(state.get("lastNodeId", 0)), maximum_node)
            state["lastLinkId"] = max(int(state.get("lastLinkId", 0)), maximum_link)


def _profile(path_key: str) -> tuple[str, dict[str, str], bool, bool]:
    curated = CURATED_PROFILES.get(path_key)
    if curated:
        family, devices, h3_director = curated
        return family, dict(devices), h3_director, True
    return Path(path_key).stem, dict(ALL_R9700), False, False


def _ensure_parameter_notes(workflow: dict[str, Any]) -> None:
    """Preserve existing authored note text and document only newly added nodes."""
    schemas = _subgraph_schemas(workflow)
    for graph in _graphs(workflow):
        extra = graph.setdefault("extra", {})
        marker = extra.get(REFINEMENT_KEY)
        if not isinstance(marker, dict):
            refine_graph(graph, OBJECT_INFO, schemas)
            continue
        valid_targets = {
            node.get("id") for node in graph.get("nodes", [])
            if is_target(node) and not node.get("properties", {}).get("dawasteh_generated_note")
        }
        seen_note_targets: set[Any] = set()
        cleaned_nodes = []
        for node in graph.get("nodes", []):
            if not node.get("properties", {}).get("dawasteh_generated_note"):
                cleaned_nodes.append(node)
                continue
            target_id = node.get("properties", {}).get(NOTE_PROPERTY)
            if target_id not in valid_targets or target_id in seen_note_targets:
                continue
            seen_note_targets.add(target_id)
            cleaned_nodes.append(node)
        graph["nodes"] = cleaned_nodes
        notes = {
            node.get("properties", {}).get(NOTE_PROPERTY): node
            for node in graph.get("nodes", [])
            if node.get("properties", {}).get("dawasteh_generated_note")
        }
        for target in graph.get("nodes", []):
            properties = target.get("properties", {})
            if not properties.pop("dawasteh_refresh_generated_note", False):
                continue
            note = notes.get(target.get("id"))
            if note is None:
                continue
            node_type = str(target.get("type", ""))
            sub_name, schema = schemas.get(node_type, (None, OBJECT_INFO.get(node_type, {})))
            note["title"] = f"Erklärung · {target.get('title') or schema.get('display_name') or sub_name or node_type} · Node {target['id']}"
            note["widgets_values"] = [build_note_text(target, schema, sub_name)]
        missing = [
            node for node in graph.get("nodes", [])
            if is_target(node)
            and not node.get("properties", {}).get("dawasteh_generated_note")
            and node.get("id") not in notes
        ]
        if not missing:
            marker["generated_notes"] = len(notes)
            continue
        numeric = [node.get("id") for node in graph.get("nodes", []) if isinstance(node.get("id"), int)]
        next_id = max([int(graph.get("last_node_id", 0)), *numeric], default=0) + 1
        order = max((int(node.get("order", 0)) for node in graph.get("nodes", [])), default=0) + 1
        for target in sorted(missing, key=lambda node: (isinstance(node.get("id"), str), str(node.get("id")))):
            node_type = str(target.get("type", ""))
            sub_name, schema = schemas.get(node_type, (None, OBJECT_INFO.get(node_type, {})))
            text = build_note_text(target, schema, sub_name)
            line_count = text.count("\n") + 1
            graph.setdefault("nodes", []).append({
                "id": next_id,
                "type": "MarkdownNote",
                "pos": [0, 0],
                "size": [390, min(540, max(230, 90 + line_count * 17))],
                "flags": {},
                "order": order,
                "mode": 0,
                "inputs": [],
                "outputs": [],
                "title": f"Erklärung · {target.get('title') or schema.get('display_name') or sub_name or node_type} · Node {target['id']}",
                "properties": {
                    "Node name for S&R": "MarkdownNote",
                    "cnr_id": "comfy-core",
                    NOTE_PROPERTY: target["id"],
                    "dawasteh_generated_note": True,
                },
                "widgets_values": [text],
                "color": "#1b2638",
                "bgcolor": "#101722",
            })
            next_id += 1
            order += 1
        marker["generated_notes"] = len(notes) + len(missing)


def _rebuild_presentation(workflow: dict[str, Any], path_key: str) -> None:
    _ensure_parameter_notes(workflow)
    _normalize_counters(workflow)
    apply_rodent_layout(workflow, path_key)


def migrate_workflow(workflow: dict[str, Any], path_key: str) -> dict[str, Any]:
    """Return a deterministically migrated copy of one canonical workflow."""
    migrated = copy.deepcopy(workflow)
    marker = migrated.get("extra", {}).get(MIGRATION_KEY, {})
    if marker.get("version") == MIGRATION_VERSION:
        migrated, duration_changed = integrate_duration_seconds(migrated, path_key)
        migrated, v094_changed = upgrade_v094_workflow(migrated, path_key)
        migrated, v095_changed = upgrade_v095_workflow(migrated, path_key)
        migrated, v096_changed = upgrade_v096_workflow(migrated, path_key)
        migrated, v098_changed = upgrade_v098_workflow(migrated, path_key)
        if duration_changed or v094_changed or v095_changed or v096_changed or v098_changed:
            _rebuild_presentation(migrated, path_key)
        else:
            apply_rodent_layout(migrated, path_key)
        return migrated

    family, devices, h3_director, curated = _profile(path_key)
    existing_controls = [node for node in migrated.get("nodes", []) if node.get("type") == DEVICE_CONTROL_TYPE]
    if existing_controls:
        raise ValueError(f"{path_key}: workflow already has a central GPU control before v0.9.2 migration")

    if h3_director:
        directors = [node for node in migrated.get("nodes", []) if node.get("type") == "DaWH3MusicVideoDirector"]
        if len(directors) != 1:
            raise ValueError(f"{path_key}: expected exactly one H3 Director, found {len(directors)}")
        director = directors[0]
        director["type"] = "DaWH3MusicVideoDirectorDualGPU"
        director["title"] = "H3 Complete-Song Director · central GPU control · 8188"
        director.setdefault("properties", {})["Node name for S&R"] = "DaWH3MusicVideoDirectorDualGPU"
        director_note = next((
            node for node in migrated.get("nodes", [])
            if node.get("properties", {}).get(NOTE_PROPERTY) == director.get("id")
        ), None)
        if director_note is not None:
            director_note["title"] = f"Erklärung · {director['title']} · Node {director['id']}"
        inserted = 0
    else:
        inserted = sum(insert_device_selectors(graph, devices) for graph in _graphs(migrated))

    install_central_device_control(migrated, path_key, h3_director=h3_director, devices=devices)
    gpu = migrated.setdefault("extra", {}).setdefault("dawasteh_dual_gpu", {})
    gpu.update({
        "version": 3,
        "scope": "collection-wide optional GPU placement",
        "family": family,
        "source": f"workflows/{path_key}",
        "server": "127.0.0.1:8188",
        "backend": "ROCm/HIP",
        "selector_count": inserted,
        "curated_split_default": curated,
        "defaults": {
            "MODEL": devices["MODEL"],
            "CLIP": devices["CLIP"],
            "VAE": devices["VAE"],
        },
        "execution": "device placement only; ComfyUI graph stages remain sequential",
    })
    migrated["extra"][MIGRATION_KEY] = {
        "version": MIGRATION_VERSION,
        "release": "v0.9.2",
        "dual_gpu_folder_dissolved": True,
        "rodent_method": True,
        "rodent_credit": "Nerdy Rodent",
    }

    migrated, _ = integrate_duration_seconds(migrated, path_key)
    migrated, _ = upgrade_v094_workflow(migrated, path_key)
    migrated, _ = upgrade_v095_workflow(migrated, path_key)
    migrated, _ = upgrade_v096_workflow(migrated, path_key)
    migrated, _ = upgrade_v098_workflow(migrated, path_key)
    # Rebuild one generated parameter note per executable node, including the
    # newly inserted selectors, GPU control, and duration controls.
    _rebuild_presentation(migrated, path_key)
    return migrated


def build_addition(addition: Addition) -> dict[str, Any]:
    workflow = json.loads(_workflow_template_path(addition.template).read_text(encoding="utf-8-sig"))
    workflow = specialize_game_asset_template(workflow, addition.path)
    _localize_model_paths(workflow)
    if not addition.path.startswith("Live Avatar/"):
        # Live Avatar roots stay timer-free by explicit user decision.
        install_run_timer(workflow)
    workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dawasteh-v092:{addition.path}"))
    workflow["revision"] = 0
    workflow.setdefault("extra", {})["dawasteh_template_source"] = {
        "template": addition.template,
        "pinned_under": "tools/workflow_templates",
    }
    return workflow


def desired_workflows(source_root: Path = WORKFLOWS) -> dict[str, dict[str, Any]]:
    desired: dict[str, dict[str, Any]] = {}
    for path in sorted(source_root.rglob("*.json")):
        if DUAL_GPU_DIRECTORY.name in path.parts:
            continue
        key = path.relative_to(source_root).as_posix()
        if key in DELETED_PATHS:
            continue
        desired[key] = json.loads(path.read_text(encoding="utf-8-sig"))
    for addition in ADDITIONS:
        desired.setdefault(addition.path, build_addition(addition))
    for target, source in sorted(v095_addition_sources().items()):
        if target in desired:
            continue
        if source not in desired:
            if source_root.resolve() == WORKFLOWS.resolve():
                raise ValueError(f"v0.9.5 addition source is missing: {source}")
            continue
        desired[target] = copy.deepcopy(desired[source])
    return desired


def migrate_collection(destination: Path = WORKFLOWS, *, check: bool = False) -> tuple[int, int, int]:
    desired = desired_workflows(destination)
    changed = 0
    for key, original in sorted(desired.items()):
        migrated = migrate_workflow(original, key)
        path = destination / Path(key)
        rendered = json.dumps(migrated, ensure_ascii=False, indent=2) + "\n"
        current = path.read_text(encoding="utf-8-sig") if path.is_file() else None
        if current != rendered:
            changed += 1
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(rendered, encoding="utf-8")

    removed = 0
    legacy_dual_gpu_directory = destination / DUAL_GPU_DIRECTORY.name
    stale_paths = [destination / Path(key) for key in DELETED_PATHS]
    if legacy_dual_gpu_directory.is_dir():
        stale_paths.extend(legacy_dual_gpu_directory.glob("*.json"))
    for path in stale_paths:
        if path.exists():
            removed += 1
            if not check:
                path.unlink()
    if legacy_dual_gpu_directory.is_dir() and not check:
        shutil.rmtree(legacy_dual_gpu_directory)
    return len(desired), changed, removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows", type=Path, default=WORKFLOWS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    total, changed, removed = migrate_collection(args.workflows, check=args.check)
    print(f"workflows={total} changed={changed} removed={removed} check={args.check}")
    return 1 if args.check and (changed or removed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
