#!/usr/bin/env python3
"""Static validation for the curated ComfyUI workflow collection."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from tools.refine_workflows import DOC_TYPES, NOTE_PROPERTY, REFINEMENT_KEY, graph_children, is_target
    from tools.integrate_pixaroma_prompts import pause_node as expected_pause_node, prompt as expected_prompt_node
    from tools.integrate_h3_turbo_lora import DIRECTOR_WORKFLOW, VISIBLE_WORKFLOWS, integrate_director, integrate_visible
    from tools.migrate_workflows_v092 import (
        ADDITIONS,
        DELETED_PATHS,
        MIGRATION_KEY,
        MIGRATION_VERSION,
        build_addition,
        migrate_workflow,
    )
    from tools.consolidate_ace_autosongwriters_v093 import (
        SOURCE_WORKFLOWS as V093_SOURCE_WORKFLOWS,
        TARGET_WORKFLOWS as V093_TARGET_WORKFLOWS,
        consolidate_workflow as consolidate_v093_autosongwriter,
    )
    from tools.upgrade_v095 import addition_sources as v095_addition_sources
except ModuleNotFoundError:  # Direct execution: python tools/validate_workflows.py
    from refine_workflows import DOC_TYPES, NOTE_PROPERTY, REFINEMENT_KEY, graph_children, is_target
    from integrate_pixaroma_prompts import pause_node as expected_pause_node, prompt as expected_prompt_node
    from integrate_h3_turbo_lora import DIRECTOR_WORKFLOW, VISIBLE_WORKFLOWS, integrate_director, integrate_visible
    from migrate_workflows_v092 import (
        ADDITIONS,
        DELETED_PATHS,
        MIGRATION_KEY,
        MIGRATION_VERSION,
        build_addition,
        migrate_workflow,
    )
    from consolidate_ace_autosongwriters_v093 import (
        SOURCE_WORKFLOWS as V093_SOURCE_WORKFLOWS,
        TARGET_WORKFLOWS as V093_TARGET_WORKFLOWS,
        consolidate_workflow as consolidate_v093_autosongwriter,
    )
    from upgrade_v095 import addition_sources as v095_addition_sources

BLACKLIST = ("cudaexecutionprovider", "nunchaku", "svdq", "nvfp4", "tensorrt", "xformers", "flash_attn")
BASELINE_REF = "HEAD"
INTEGRATION_MARKER = "dawasteh_pixaroma_prompt_integration"
MANIFEST_PATH = Path(__file__).with_name("pixaroma_prompt_manifest.json")
AUTHORIZED_WIDGET_DELTAS: dict[str, dict[int, set[int]]] = {
    "workflows/LoRA Generation/Qwen3-TTS_0.6B-Voice-LoRA-Training.json": {
        1: {0},  # document the supported <audio-stem>_Text.txt transcript alias
        2: {9},  # serialize numeric-looking COMBO choices as strings for ComfyUI validation
    },
    "workflows/Music Generation/YuE_7B-FP16_R9700-Reference-Voice-ICL-Music-Generation.json": {
        2: {1, 4},  # restore the 20-section/600-second-safe lyrics capacity
    },
    "workflows/Music Generation/YuE_7B-FP16_R9700-Music-Generation.json": {
        2: {1, 4, 5},  # restore 20 sections and the documented 540-second target
        8: {0},  # keep the generated parameter note synchronized with those values
    },
    "workflows/Music Generation/HeartMuLa_HappyNewYear_3B_R9700-Music-Generation.json": {
        3: {2},  # restore the documented 300-second default upper bound
        10: {0},  # keep the generated parameter note synchronized with that value
    },
}
AUTHORIZED_NODE_REPLACEMENTS: dict[str, dict[int, str]] = {
    # Pin the v0.8.4 Identity-Lock Director serialization, user-facing guide,
    # and schema-generated parameter note. This includes ComfyUI's control-after-
    # generate widget immediately after the integer seed.
    "workflows/Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json": {
        1: "31109d644802d5d7fea67f890802fec3bf3b5e6c5dda3d6979e7e09a91b85cbb",
        2: "692d4b2a3dba7827b661f8560e0723f57a5a3e01e95a910d7ee4accd2741a042",
        4: "8d1d238d1f26397d0458d6db5f9278878e67b3674b0a3eb3ecbb67e259813aaa",
    },
    # Persistent latest-frame Spout replaces the transient Jovi writer; hashes
    # pin both the runtime node and its synchronized generated documentation.
    "workflows/Live Avatar/LiveAvatar-03-LivePortrait-Webcam-Spout-OBS.json": {
        10: "d4bb2789e112b14be5bf66383540c5052a1faa5deccb03fe2782316ae7fbfe88",
        12: "9a7babbb37f4d9dc927d74b1e09c6877a35a0e4db591ed2eaddcc35a55bdeac9",
        22: "faa3cd6ecddd426a253d7980a54f10f1b196f83521e4436b8b3cecffaad6299a",
    },
    "workflows/Live Avatar/LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA.json": {
        10: "d4bb2789e112b14be5bf66383540c5052a1faa5deccb03fe2782316ae7fbfe88",
        12: "06da5ed6eb7dbfe3ed1b8ea1d01d0c85c51d8487c0dc4c78f64106019d29c5cf",
        22: "faa3cd6ecddd426a253d7980a54f10f1b196f83521e4436b8b3cecffaad6299a",
    },
    # v0.8.5 LiveAvatar replacements are limited to runtime configuration and
    # their synchronized user-facing notes. Every link and unrelated node must
    # remain byte/semantic-equivalent to the v0.8.4 historical baseline.
    "workflows/Live Avatar/LiveAvatar-06-VRM-Full-Body-Hand-Face+Live-Mic.json": {
        1: "4cc78378109966b9de2d770f658126cd89c15937937bf225c108c9e40ca2e707",
        2: "7dd4252891ebb25f0ce14354628a95b2323c822390ff9958ccf8efc0da8c3f2c",
    },
    "workflows/Live Avatar/LiveAvatar-07-AI-Webcam-Character-Swap-Experimental.json": {
        1: "2361a22fd22235cc672625fc5b0845be047c7ac3c52db19e665c88bafc522f90",
        17: "152f37b21391c7712e3b079dc7776948bc1318224e4cf1eb8a61c6f1b29875eb",
    },
    "workflows/Live Avatar/LiveAvatar-11-AI-Webcam-Character-Swap-Cached-OpenPose.json": {
        1: "d86ee2a8c23c8ac6b52a07ec45960072e611cf22199dedb7e0454daff27249c7",
        3: "971e99f2ff08df81b087faed16bb9a488b93e5d8fcd86f07000074e7ce597172",
        17: "95cd470aea323cc09e0235a006bb1b19bf5b88c2880355975a60322984814fca",
        20: "da7c2069cc9422c6e417490ee00329566226f22d71cc57a0dfe8e55b4087a782",
    },
    "workflows/Live Avatar/LiveAvatar-12-III-Reliable-VRM-Mode.json": {
        1: "1fafcb08a29d256031edfd5599bf1f94f03ad225853ad9c2ade2a8986739c9a8",
        2: "8ed5786ad1e52558c93c1bfe6c40d23eb8a38021cf6607394c915ff0f7e40c29",
    },
}
AUTHORIZED_WIDGET_VALUE_HASHES: dict[str, dict[int, dict[int, str]]] = {
    "workflows/LoRA Generation/Qwen3-TTS_0.6B-Voice-LoRA-Training.json": {
        1: {0: "2709348679a192c731239fc1f71f73a1d1deb3369d821717d6279b5d9d1ba08f"},
        2: {9: "17eed2c0e7c9788d0b46fafdf328b3e955aa0a22132c16cde72aa4f32dcd5282"},
    },
}


def _widget_value_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def graph_locator(workflow: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    yield "root", workflow
    def descend(graph: dict[str, Any], prefix: str):
        for sg in graph.get("definitions", {}).get("subgraphs", []):
            loc = f"{prefix}/subgraph:{sg.get('id')}"
            yield loc, sg
            yield from descend(sg, loc)
    yield from descend(workflow, "root")


def link_id(entry: Any) -> Any:
    if isinstance(entry, list) and entry:
        return entry[0]
    if isinstance(entry, dict):
        return entry.get("id")
    return None


def endpoints(entry: Any) -> tuple[Any, Any]:
    origin, _, target, _, _ = connection(entry)
    return origin, target


def connection(entry: Any) -> tuple[Any, Any, Any, Any, Any]:
    if isinstance(entry, list) and len(entry) >= 5:
        return entry[1], entry[2], entry[3], entry[4], entry[5] if len(entry) > 5 else None
    if isinstance(entry, dict):
        origin = entry.get("origin_id", entry.get("originId", entry.get("from", entry.get("source"))))
        target = entry.get("target_id", entry.get("targetId", entry.get("to", entry.get("target"))))
        if isinstance(origin, dict): origin = origin.get("node_id", origin.get("nodeId", origin.get("id")))
        if isinstance(target, dict): target = target.get("node_id", target.get("nodeId", target.get("id")))
        origin_slot = entry.get("origin_slot", entry.get("originSlot", entry.get("source_slot", entry.get("sourceSlot"))))
        target_slot = entry.get("target_slot", entry.get("targetSlot"))
        return origin, origin_slot, target, target_slot, entry.get("type")
    return None, None, None, None, None


def _compatible_link_type(slot_type: Any, link_type: Any) -> bool:
    if slot_type in (None, "*") or link_type in (None, "*"):
        return True
    slot_types = {value.strip() for value in str(slot_type).split(",")}
    link_types = {value.strip() for value in str(link_type).split(",")}
    return bool(slot_types.intersection(link_types))


def rect(node: dict[str, Any]) -> tuple[float, float, float, float]:
    x, y = (list(node.get("pos", [0, 0])) + [0, 0])[:2]
    w, h = (list(node.get("size", [260, 120])) + [260, 120])[:2]
    return float(x), float(y), float(x)+float(w), float(y)+float(h)


def overlaps(a, b) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def git_ref_json(path_key: str) -> dict[str, Any]:
    raw = subprocess.check_output(
        ["git", "show", f"{BASELINE_REF}:{path_key}"], text=True, encoding="utf-8",
        stderr=subprocess.DEVNULL,
    )
    return json.loads(raw)


def git_head_json(path: Path) -> dict[str, Any]:
    return git_ref_json(_path_key(path))


def git_baseline_workflow_paths() -> set[str]:
    raw = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", BASELINE_REF, "workflows"],
        text=True,
        encoding="utf-8",
        stderr=subprocess.DEVNULL,
    )
    return {line.strip().replace("\\", "/") for line in raw.splitlines() if line.strip().endswith(".json")}


def validate_graph(path: Path, locator: str, graph: dict[str, Any], errors: list[str]) -> tuple[int, int, int]:
    nodes = graph.get("nodes", [])
    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        errors.append(f"{path}:{locator}: duplicate node IDs")
    numeric = [i for i in ids if isinstance(i, int)]
    is_subgraph = locator != "root"
    if "last_node_id" not in graph:
        errors.append(f"{path}:{locator}: last_node_id missing")
    elif numeric and int(graph.get("last_node_id", -1)) < max(numeric):
        errors.append(f"{path}:{locator}: last_node_id below maximum")
    if is_subgraph and not isinstance(graph.get("state"), dict):
        errors.append(f"{path}:{locator}: subgraph state missing")

    targets = [n for n in nodes if is_target(n) and not n.get("properties", {}).get("dawasteh_generated_note")]
    notes = [n for n in nodes if n.get("properties", {}).get("dawasteh_generated_note")]
    by_target: dict[Any, list[dict[str, Any]]] = {}
    for note in notes:
        if note.get("type") != "MarkdownNote":
            errors.append(f"{path}:{locator}: generated note {note.get('id')} is not MarkdownNote")
        by_target.setdefault(note.get("properties", {}).get(NOTE_PROPERTY), []).append(note)
    target_ids = {n.get("id") for n in targets}
    if set(by_target) != target_ids:
        errors.append(f"{path}:{locator}: note target set differs (missing={target_ids-set(by_target)}, extra={set(by_target)-target_ids})")
    for target, matches in by_target.items():
        if len(matches) != 1:
            errors.append(f"{path}:{locator}: target {target} has {len(matches)} notes")
    marker = graph.get("extra", {}).get(REFINEMENT_KEY, {})
    if marker.get("generated_notes") != len(notes):
        errors.append(f"{path}:{locator}: refinement marker note count mismatch")

    link_entries = graph.get("links", []) or []
    if isinstance(link_entries, dict):
        entries = list(link_entries.values())
    else:
        entries = list(link_entries)
    link_ids = [link_id(e) for e in entries]
    if len(link_ids) != len(set(link_ids)):
        errors.append(f"{path}:{locator}: duplicate link IDs")
    known_links = set(link_ids)
    numeric_links = [value for value in link_ids if isinstance(value, int)]
    if not is_subgraph and "last_link_id" not in graph:
        errors.append(f"{path}:{locator}: last_link_id missing")
    elif "last_link_id" in graph and numeric_links and int(graph.get("last_link_id", -1)) < max(numeric_links):
        errors.append(f"{path}:{locator}: last_link_id below maximum")
    state = graph.get("state")
    if isinstance(state, dict):
        if "lastNodeId" not in state:
            errors.append(f"{path}:{locator}: state.lastNodeId missing")
        elif numeric and int(state.get("lastNodeId", -1)) < max(numeric):
            errors.append(f"{path}:{locator}: state.lastNodeId below maximum")
        if "lastLinkId" not in state:
            errors.append(f"{path}:{locator}: state.lastLinkId missing")
        elif numeric_links and int(state.get("lastLinkId", -1)) < max(numeric_links):
            errors.append(f"{path}:{locator}: state.lastLinkId below maximum")
    node_ids = set(ids)
    nodes_by_id = {node.get("id"): node for node in nodes}
    input_interface = graph.get("inputNode") if isinstance(graph.get("inputNode"), dict) else None
    output_interface = graph.get("outputNode") if isinstance(graph.get("outputNode"), dict) else None
    input_interface_id = input_interface.get("id") if input_interface else None
    output_interface_id = output_interface.get("id") if output_interface else None
    interface_ids = {value for value in (input_interface_id, output_interface_id) if value is not None}
    allowed_nodes = node_ids | interface_ids
    entries_by_id = {link_id(entry): entry for entry in entries}
    for entry in entries:
        lid = link_id(entry)
        origin, origin_slot, target, target_slot, linked_type = connection(entry)
        if linked_type in (None, ""):
            errors.append(f"{path}:{locator}: link {lid} type missing")
        if origin not in allowed_nodes or target not in allowed_nodes:
            errors.append(f"{path}:{locator}: link {lid} endpoint missing ({origin}->{target})")
            continue
        if origin == output_interface_id:
            errors.append(f"{path}:{locator}: link {lid} cannot originate at outputNode")
        elif origin == input_interface_id:
            graph_inputs = graph.get("inputs", []) or []
            if not isinstance(origin_slot, int) or not 0 <= origin_slot < len(graph_inputs):
                errors.append(f"{path}:{locator}: link {lid} inputNode source slot missing ({origin_slot})")
            elif not _compatible_link_type(graph_inputs[origin_slot].get("type"), linked_type):
                errors.append(f"{path}:{locator}: link {lid} inputNode type mismatch")
        if target == input_interface_id:
            errors.append(f"{path}:{locator}: link {lid} cannot target inputNode")
        elif target == output_interface_id:
            graph_outputs = graph.get("outputs", []) or []
            if not isinstance(target_slot, int) or not 0 <= target_slot < len(graph_outputs):
                errors.append(f"{path}:{locator}: link {lid} outputNode target slot missing ({target_slot})")
            elif not _compatible_link_type(graph_outputs[target_slot].get("type"), linked_type):
                errors.append(f"{path}:{locator}: link {lid} outputNode type mismatch")
        if origin in nodes_by_id:
            outputs = nodes_by_id[origin].get("outputs", []) or []
            if not isinstance(origin_slot, int) or not 0 <= origin_slot < len(outputs):
                errors.append(f"{path}:{locator}: link {lid} source slot missing ({origin}:{origin_slot})")
            else:
                output = outputs[origin_slot]
                if lid not in (output.get("links") or []):
                    errors.append(f"{path}:{locator}: link {lid} absent from source output ({origin}:{origin_slot})")
                if not _compatible_link_type(output.get("type"), linked_type):
                    errors.append(f"{path}:{locator}: link {lid} source type mismatch ({output.get('type')} != {linked_type})")
        if target in nodes_by_id:
            inputs = nodes_by_id[target].get("inputs", []) or []
            if not isinstance(target_slot, int) or not 0 <= target_slot < len(inputs):
                errors.append(f"{path}:{locator}: link {lid} target slot missing ({target}:{target_slot})")
            else:
                input_slot = inputs[target_slot]
                if input_slot.get("link") != lid:
                    errors.append(f"{path}:{locator}: link {lid} absent from target input ({target}:{target_slot})")
                if not _compatible_link_type(input_slot.get("type"), linked_type):
                    errors.append(f"{path}:{locator}: link {lid} target type mismatch ({input_slot.get('type')} != {linked_type})")
    for node in nodes:
        for slot, inp in enumerate(node.get("inputs", []) or []):
            lid = inp.get("link")
            if lid is not None and lid not in known_links:
                errors.append(f"{path}:{locator}: node {node.get('id')} input link {lid} missing")
            elif lid is not None:
                _, _, target, target_slot, _ = connection(entries_by_id[lid])
                if (target, target_slot) != (node.get("id"), slot):
                    errors.append(f"{path}:{locator}: node {node.get('id')} input {slot} is not reciprocal with link {lid}")
        for slot, out in enumerate(node.get("outputs", []) or []):
            for lid in out.get("links") or []:
                if lid not in known_links:
                    errors.append(f"{path}:{locator}: node {node.get('id')} output link {lid} missing")
                else:
                    origin, origin_slot, _, _, _ = connection(entries_by_id[lid])
                    if (origin, origin_slot) != (node.get("id"), slot):
                        errors.append(f"{path}:{locator}: node {node.get('id')} output {slot} is not reciprocal with link {lid}")

    # Every node rectangle must be collision-free. Touching edges is allowed.
    rects = [(n.get("id"), rect(n)) for n in nodes]
    for i, (aid, ar) in enumerate(rects):
        for bid, br in rects[i+1:]:
            if overlaps(ar, br):
                errors.append(f"{path}:{locator}: overlapping nodes {aid} and {bid}")
                if sum("overlapping nodes" in e for e in errors) > 30:
                    break
        if sum("overlapping nodes" in e for e in errors) > 30:
            break
    return len(nodes), len(notes), len(entries)


def _manifest_entries() -> dict[str, dict[str, Any]]:
    data = load(MANIFEST_PATH)
    return {entry["path"]: entry for entry in data.get("entries", [])}


def _path_key(path: Path) -> str:
    root = Path(__file__).resolve().parents[1]
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _input_index(node: dict[str, Any], name: str) -> int | None:
    return next((index for index, item in enumerate(node.get("inputs", []) or []) if item.get("name") == name), None)


def validate_integration_delta(
    path: Path,
    before: dict[str, Any],
    after: dict[str, Any],
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    """Normalize only manifest-authorized Pixaroma deltas, then demand HEAD equality."""
    prefix = f"{path}:root"
    before_nodes = {node.get("id"): node for node in before.get("nodes", [])}
    after_nodes = {node.get("id"): node for node in after.get("nodes", [])}

    # Newer release baselines already contain the authorized integration. In
    # that case validate the committed marked graph directly rather than trying
    # to replay the historical one-shot migration against itself.
    committed_marks = {
        node_id: node.get("properties", {}).get(INTEGRATION_MARKER)
        for node_id, node in before_nodes.items()
        if node.get("properties", {}).get(INTEGRATION_MARKER)
    }
    if committed_marks:
        if before == after:
            return
        for node_id, marker in committed_marks.items():
            original = before_nodes[node_id]
            current = after_nodes.get(node_id)
            if current is None:
                errors.append(f"{prefix}: committed integration node {node_id} missing")
                continue
            if marker.get("kind") == "pause":
                old_link = (original.get("inputs") or [{}])[0].get("link")
                new_link = (current.get("inputs") or [{}])[0].get("link")
                if new_link != old_link:
                    errors.append(f"{prefix}: Pause {node_id} upstream link changed from committed baseline")
            if current != original:
                label = "Prompt" if marker.get("kind") == "prompt" else "Pause"
                errors.append(f"{prefix}: {label} {node_id} schema/state differs from committed baseline")
        if set(after_nodes) != set(before_nodes):
            errors.append(f"{prefix}: committed node ID set changed")
        if after.get("links", []) != before.get("links", []):
            errors.append(f"{prefix}: committed link set changed")
        if after != before:
            errors.append(f"{prefix}: graph differs from committed HEAD baseline")
        return
    before_links = {entry[0]: entry for entry in before.get("links", []) if isinstance(entry, list)}
    after_links = {entry[0]: entry for entry in after.get("links", []) if isinstance(entry, list)}
    before_ids = set(before_nodes)
    after_ids = set(after_nodes)
    marked = {
        node_id: node for node_id, node in after_nodes.items()
        if node.get("properties", {}).get(INTEGRATION_MARKER)
    }

    if not before_ids <= after_ids:
        errors.append(f"{prefix}: original node IDs removed ({before_ids-after_ids})")
    unexpected_new = (after_ids - before_ids) - set(marked)
    if unexpected_new:
        errors.append(f"{prefix}: unmarked new node IDs {unexpected_new}")

    normalized = copy.deepcopy(after)
    norm_nodes = {node.get("id"): node for node in normalized.get("nodes", [])}
    norm_links = {entry[0]: entry for entry in normalized.get("links", []) if isinstance(entry, list)}
    consumed_nodes: set[Any] = set()
    consumed_links: set[Any] = set()

    for target in manifest.get("targets", []):
        target_id = target["node_id"]
        input_name = target["input"]
        widget_index = target["widget_index"]
        original = before_nodes.get(target_id)
        current = after_nodes.get(target_id)
        if original is None or current is None:
            errors.append(f"{prefix}: prompt target node {target_id} missing")
            continue
        prompts = [
            node for node in marked.values()
            if node.get("properties", {}).get(INTEGRATION_MARKER, {}).get("kind") == "prompt"
            and node.get("properties", {}).get(INTEGRATION_MARKER, {}).get("target") == [target_id, input_name]
        ]
        if len(prompts) != 1:
            errors.append(f"{prefix}: target {target_id}:{input_name} has {len(prompts)} marked Prompt nodes")
            continue
        prompt = prompts[0]
        consumed_nodes.add(prompt.get("id"))
        if prompt.get("type") != "PixaromaPrompt":
            errors.append(f"{prefix}: integration node {prompt.get('id')} is not PixaromaPrompt")
        state = prompt.get("properties", {}).get("promptState", {})
        if state.get("text") != target.get("source_text"):
            errors.append(f"{prefix}: Prompt {prompt.get('id')} did not preserve source text")
        if widget_index >= len(current.get("widgets_values", [])) or current["widgets_values"][widget_index] != "":
            errors.append(f"{prefix}: target {target_id} source widget was not cleared")
            continue
        expected_widgets = copy.deepcopy(original.get("widgets_values", []))
        expected_widgets[widget_index] = ""
        if current.get("widgets_values", []) != expected_widgets:
            errors.append(f"{prefix}: target {target_id} widgets changed beyond source clearing")
        slot = _input_index(current, input_name)
        if slot is None:
            errors.append(f"{prefix}: target {target_id} lacks input {input_name}")
            continue
        link_id_value = current["inputs"][slot].get("link")
        link = after_links.get(link_id_value)
        expected_link = [link_id_value, prompt.get("id"), 0, target_id, slot, "STRING"]
        if link != expected_link:
            errors.append(f"{prefix}: Prompt {prompt.get('id')} link is not reciprocal/exact")
        expected_prompt = expected_prompt_node(
            prompt.get("id"), target.get("source_text"), prompt.get("pos"), [target_id, input_name]
        )
        expected_prompt["outputs"][0]["links"] = [link_id_value]
        if prompt != expected_prompt:
            errors.append(f"{prefix}: Prompt {prompt.get('id')} schema/state differs from the authorized node")
        consumed_links.add(link_id_value)

        original_inputs = copy.deepcopy(original.get("inputs", []) or [])
        original_slot = _input_index(original, input_name)
        expected_inputs = copy.deepcopy(original_inputs)
        if original_slot is None:
            expected_inputs.append({
                "name": input_name,
                "type": "STRING",
                "widget": {"name": input_name},
                "link": link_id_value,
            })
        else:
            expected_inputs[original_slot]["link"] = link_id_value
        if current.get("inputs", []) != expected_inputs:
            errors.append(f"{prefix}: target {target_id} inputs changed beyond authorized Prompt wiring")

        norm_target = norm_nodes[target_id]
        norm_target["inputs"] = original_inputs
        norm_target["widgets_values"] = copy.deepcopy(original.get("widgets_values", []))
        norm_links.pop(link_id_value, None)

    for gate_spec in manifest.get("pauses", []):
        old_link_id = gate_spec["target_link"]
        original_link = before_links.get(old_link_id)
        gates = [
            node for node in marked.values()
            if node.get("properties", {}).get(INTEGRATION_MARKER, {}).get("kind") == "pause"
            and node.get("properties", {}).get(INTEGRATION_MARKER, {}).get("pause_target") == old_link_id
        ]
        if len(gates) != 1:
            errors.append(f"{prefix}: link {old_link_id} has {len(gates)} marked Pause nodes")
            continue
        gate = gates[0]
        consumed_nodes.add(gate.get("id"))
        if gate.get("type") != "PixaromaPauseText":
            errors.append(f"{prefix}: integration node {gate.get('id')} is not PixaromaPauseText")
        fresh_id = gate.get("inputs", [{}])[0].get("link")
        fresh_link = after_links.get(fresh_id)
        expected_fresh = [
            fresh_id,
            gate_spec["source_node"],
            gate_spec.get("source_slot", 0),
            gate.get("id"),
            0,
            "STRING",
        ]
        if fresh_link != expected_fresh:
            errors.append(f"{prefix}: Pause {gate.get('id')} upstream link is missing or incorrect")
        consumed_links.add(fresh_id)
        current_old = after_links.get(old_link_id)
        expected_old = copy.deepcopy(original_link)
        if expected_old is not None:
            expected_old[1] = gate.get("id")
            expected_old[2] = 0
        if current_old != expected_old:
            errors.append(f"{prefix}: Pause {gate.get('id')} downstream link changed unexpectedly")
        expected_gate = expected_pause_node(gate.get("id"), gate.get("pos"), fresh_id, old_link_id)
        if gate != expected_gate:
            errors.append(f"{prefix}: Pause {gate.get('id')} schema/state differs from the authorized node")

        source_id = gate_spec["source_node"]
        source_slot = gate_spec.get("source_slot", 0)
        original_source = before_nodes.get(source_id)
        current_source = after_nodes.get(source_id)
        if original_source is None or current_source is None:
            errors.append(f"{prefix}: Pause source {source_id} missing")
        else:
            expected_outputs = copy.deepcopy(original_source.get("outputs", []))
            source_links = expected_outputs[source_slot].get("links") or []
            if old_link_id not in source_links:
                errors.append(f"{prefix}: HEAD source {source_id}:{source_slot} lacks link {old_link_id}")
            else:
                source_links.remove(old_link_id)
                source_links.append(fresh_id)
            if current_source.get("outputs", []) != expected_outputs:
                errors.append(f"{prefix}: Pause source {source_id} outputs changed beyond gate split")
            norm_nodes[source_id]["outputs"] = copy.deepcopy(original_source.get("outputs", []))
        if original_link is not None:
            norm_links[old_link_id] = copy.deepcopy(original_link)
        norm_links.pop(fresh_id, None)

    if set(marked) != consumed_nodes:
        errors.append(f"{prefix}: unexpected or missing marked integration nodes ({set(marked)^consumed_nodes})")
    new_link_ids = set(after_links) - set(before_links)
    if new_link_ids != consumed_links:
        errors.append(f"{prefix}: unexpected or missing integration links ({new_link_ids^consumed_links})")

    normalized["nodes"] = [node for node in normalized.get("nodes", []) if node.get("id") not in consumed_nodes]
    normalized["links"] = [norm_links[entry[0]] for entry in normalized.get("links", []) if entry[0] in norm_links]
    normalized["last_node_id"] = before.get("last_node_id")
    normalized["last_link_id"] = before.get("last_link_id")
    if normalized != before:
        errors.append(f"{prefix}: graph differs from HEAD beyond manifest-authorized integration")

    numeric_nodes = [node_id for node_id in after_ids if isinstance(node_id, int)]
    numeric_links = [link_id_value for link_id_value in after_links if isinstance(link_id_value, int)]
    if consumed_nodes and numeric_nodes and after.get("last_node_id") != max(numeric_nodes):
        errors.append(f"{prefix}: last_node_id is not the exact maximum")
    if consumed_nodes and numeric_links and after.get("last_link_id") != max(numeric_links):
        errors.append(f"{prefix}: last_link_id is not the exact maximum")


def compare_head(path: Path, current: dict[str, Any], errors: list[str]) -> tuple[int, int]:
    head = git_head_json(path)
    if "Live Avatar" in path.parts:
        # The user explicitly requires all Live Avatar roots to be timer-free.
        # Normalize only the standalone timer out of the historical baseline;
        # every other node, link and widget still receives the normal HEAD check.
        head = copy.deepcopy(head)
        removed = {node.get("id") for node in head.get("nodes", []) if node.get("type") == "PixaromaRunTimer"}
        head["nodes"] = [node for node in head.get("nodes", []) if node.get("id") not in removed]
        head["links"] = [link for link in head.get("links", []) if link[1] not in removed and link[3] not in removed]
    # Once an authorized Pixaroma integration has been committed, HEAD already
    # contains its marked nodes and links. Treat byte/semantic-equivalent graphs
    # as the baseline instead of trying to apply the integration delta again.
    if current == head:
        return (
            sum(len(graph.get("nodes", [])) for _, graph in graph_locator(head)),
            sum(len(graph.get("links", {}) or []) for _, graph in graph_locator(head)),
        )
    if current.get("extra", {}).get(MIGRATION_KEY, {}).get("version") == MIGRATION_VERSION:
        expected = migrate_workflow(head, _path_key(path).removeprefix("workflows/"))
        if expected != current:
            errors.append(f"{path}: differs from deterministic v0.9.2 collection migration")
        return (
            sum(len(graph.get("nodes", [])) for _, graph in graph_locator(head)),
            sum(len(graph.get("links", {}) or []) for _, graph in graph_locator(head)),
        )
    if current.get("extra", {}).get("dawasteh_h3_turbo_lora", {}).get("version") == 1:
        expected = copy.deepcopy(head)
        if path.name == DIRECTOR_WORKFLOW:
            integrate_director(expected)
        elif path.name in VISIBLE_WORKFLOWS:
            integrate_visible(expected, path.name)
        else:
            errors.append(f"{path}: unexpected H3 Turbo migration target")
        if expected != current:
            errors.append(f"{path}: differs from the deterministic H3 Turbo migration")
        return (
            sum(len(graph.get("nodes", [])) for _, graph in graph_locator(head)),
            sum(len(graph.get("links", {}) or []) for _, graph in graph_locator(head)),
        )
    head_graphs = dict(graph_locator(head))
    current_graphs = dict(graph_locator(current))
    if set(head_graphs) != set(current_graphs):
        errors.append(f"{path}: graph locator set changed")
        return 0, 0
    manifest = _manifest_entries().get(_path_key(path), {"targets": [], "pauses": []})
    if not manifest.get("targets") and not manifest.get("pauses"):
        key = _path_key(path)
        replacements = AUTHORIZED_NODE_REPLACEMENTS.get(key)
        if replacements:
            normalized = copy.deepcopy(current)
            normalized_nodes = {node.get("id"): node for node in normalized.get("nodes", [])}
            head_nodes = {node.get("id"): node for node in head.get("nodes", [])}
            for node_id, expected_hash in replacements.items():
                current_node = normalized_nodes.get(node_id)
                head_node = head_nodes.get(node_id)
                if current_node is None or head_node is None:
                    errors.append(f"{path}: authorized replacement node {node_id} missing")
                    continue
                if _widget_value_hash(current_node) != expected_hash:
                    errors.append(f"{path}: authorized replacement node {node_id} has unexpected content")
                index = normalized["nodes"].index(current_node)
                normalized["nodes"][index] = copy.deepcopy(head_node)
            if normalized != head:
                errors.append(f"{path}: graph differs from HEAD beyond authorized node replacements")
        else:
            allowed = AUTHORIZED_WIDGET_DELTAS.get(key)
            if allowed:
                normalized = copy.deepcopy(current)
                normalized_nodes = {node.get("id"): node for node in normalized.get("nodes", [])}
                head_nodes = {node.get("id"): node for node in head.get("nodes", [])}
                expected_hashes = AUTHORIZED_WIDGET_VALUE_HASHES.get(key, {})
                for node_id, widget_indices in allowed.items():
                    current_node = normalized_nodes.get(node_id)
                    head_node = head_nodes.get(node_id)
                    if current_node is None or head_node is None:
                        errors.append(f"{path}: authorized widget target node {node_id} missing")
                        continue
                    for index in widget_indices:
                        current_values = current_node.get("widgets_values", [])
                        head_values = head_node.get("widgets_values", [])
                        if index >= len(current_values) or index >= len(head_values):
                            errors.append(f"{path}: authorized widget index {node_id}:{index} missing")
                            continue
                        expected_hash = expected_hashes.get(node_id, {}).get(index)
                        if expected_hash is not None and _widget_value_hash(current_values[index]) != expected_hash:
                            errors.append(f"{path}: authorized widget value {node_id}:{index} is not the expected delta")
                        current_values[index] = copy.deepcopy(head_values[index])
                if normalized != head:
                    errors.append(f"{path}: graph differs from HEAD beyond authorized widget changes")
            elif current != head:
                errors.append(f"{path}: historical skip workflow changed without an authorized delta")
        return (
            sum(len(graph.get("nodes", [])) for graph in head_graphs.values()),
            sum(len(graph.get("links", {}) or []) for graph in head_graphs.values()),
        )
    old_nodes = old_links = 0
    for locator, before in head_graphs.items():
        after = current_graphs[locator]
        old_nodes += len(before.get("nodes", []))
        old_links += len(before.get("links", {}) or [])
        if locator == "root":
            validate_integration_delta(path, before, after, manifest, errors)
        elif before != after:
            errors.append(f"{path}:{locator}: subgraph changed")
    return old_nodes, old_links


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflows", type=Path, default=Path("workflows"))
    parser.add_argument("--against-head", action="store_true")
    parser.add_argument("--baseline-ref", default="HEAD", help="Git ref used by --against-head (for example v0.9.2 after committing v0.9.3)")
    parser.add_argument("--skip-collection-totals", action="store_true", help="Validate a focused subset without repository-wide count invariants")
    args = parser.parse_args()
    global BASELINE_REF
    BASELINE_REF = args.baseline_ref
    paths = sorted(args.workflows.rglob("*.json"))
    errors: list[str] = []
    if args.against_head and not args.skip_collection_totals:
        baseline_paths = git_baseline_workflow_paths()
        expected_paths = {
            path for path in baseline_paths
            if not path.startswith("workflows/Dual GPU - R9700 + RX 9070 XT/")
            and path not in {f"workflows/{key}" for key in DELETED_PATHS}
            and path not in {f"workflows/{key}" for key in V093_SOURCE_WORKFLOWS}
        }
        expected_paths.update(f"workflows/{addition.path}" for addition in ADDITIONS)
        expected_paths.update(f"workflows/{target.path}" for target in V093_TARGET_WORKFLOWS)
        expected_paths.update(f"workflows/{target}" for target in v095_addition_sources())
        current_paths = {_path_key(path) for path in paths}
        if current_paths != expected_paths:
            errors.append(
                "collection membership differs from deterministic release migration "
                f"(missing={sorted(expected_paths-current_paths)}, extra={sorted(current_paths-expected_paths)})"
            )
    totals = {"graphs": 0, "nodes": 0, "notes": 0, "links": 0, "timers": 0, "old_nodes": 0, "old_links": 0}
    for path in paths:
        try:
            workflow = load(path)
        except Exception as exc:
            errors.append(f"{path}: JSON error: {exc}")
            continue

        path_errors: list[str] = []
        if workflow.get("version") != 0.4:
            path_errors.append(f"{path}: root version is not 0.4")
        timers = sum(1 for n in workflow.get("nodes", []) if n.get("type") == "PixaromaRunTimer")
        totals["timers"] += timers
        expected_timers = 0 if "Live Avatar" in path.parts or path.name.startswith("LiveAvatar-") else 1
        if timers != expected_timers:
            path_errors.append(f"{path}: root timer count={timers}, expected={expected_timers}")
        raw_lower = path.read_text(encoding="utf-8").lower()
        for token in BLACKLIST:
            if token in raw_lower:
                path_errors.append(f"{path}: RDNA4 blacklist token {token}")
        for locator, graph in graph_locator(workflow):
            totals["graphs"] += 1
            n, notes, links = validate_graph(path, locator, graph, path_errors)
            totals["nodes"] += n; totals["notes"] += notes; totals["links"] += links

        if args.against_head:
            try:
                head_workflow = git_head_json(path)
                baseline_errors: list[str] = []
                if head_workflow.get("version") != 0.4:
                    baseline_errors.append(f"{path}: root version is not 0.4")
                head_timers = sum(1 for n in head_workflow.get("nodes", []) if n.get("type") == "PixaromaRunTimer")
                if head_timers != 1:
                    baseline_errors.append(f"{path}: root timer count={head_timers}")
                head_raw_lower = json.dumps(head_workflow, ensure_ascii=False).lower()
                for token in BLACKLIST:
                    if token in head_raw_lower:
                        baseline_errors.append(f"{path}: RDNA4 blacklist token {token}")
                for locator, graph in graph_locator(head_workflow):
                    validate_graph(path, locator, graph, baseline_errors)
                baseline_set = set(baseline_errors)
                errors.extend(error for error in path_errors if error not in baseline_set)

                old_nodes, old_links = compare_head(path, workflow, errors)
                totals["old_nodes"] += old_nodes; totals["old_links"] += old_links
            except subprocess.CalledProcessError:
                key = _path_key(path).removeprefix("workflows/")
                addition = next((item for item in ADDITIONS if item.path == key), None)
                autosongwriter = next((item for item in V093_TARGET_WORKFLOWS if item.path == key), None)
                if addition is not None:
                    expected = migrate_workflow(build_addition(addition), key)
                    if expected != workflow:
                        errors.append(f"{path}: differs from deterministic pinned-template addition")
                elif autosongwriter is not None:
                    source = git_ref_json(f"workflows/{autosongwriter.source}")
                    expected = consolidate_v093_autosongwriter(source, autosongwriter)
                    if expected != workflow:
                        errors.append(f"{path}: differs from deterministic v0.9.3 AutoSongwriter consolidation")
                    totals["old_nodes"] += sum(
                        len(graph.get("nodes", [])) for _, graph in graph_locator(source)
                    )
                    totals["old_links"] += sum(
                        len(graph.get("links", []) or []) for _, graph in graph_locator(source)
                    )
                else:
                    v095_source = v095_addition_sources().get(key)
                    if v095_source is not None:
                        source = git_ref_json(f"workflows/{v095_source}")
                        expected = migrate_workflow(source, key)
                        if expected != workflow:
                            errors.append(f"{path}: differs from deterministic canonical-source/release migration")
                        totals["old_nodes"] += sum(
                            len(graph.get("nodes", [])) for _, graph in graph_locator(source)
                        )
                        totals["old_links"] += sum(
                            len(graph.get("links", []) or []) for _, graph in graph_locator(source)
                        )
                    else:
                        errors.append(f"{path}: unexpected workflow absent from {BASELINE_REF}")
                errors.extend(path_errors)
        else:
            errors.extend(path_errors)
    expected = {"files": 233, "graphs": 286, "nodes": 10420, "notes": 4743, "links": 7189, "timers": 215}
    actual = {"files": len(paths), **{k: totals[k] for k in ("graphs", "nodes", "notes", "links", "timers")}}
    if not args.skip_collection_totals:
        for key, value in expected.items():
            if actual[key] != value:
                errors.append(f"collection total {key}={actual[key]}, expected {value}")
    if args.against_head and (totals["old_nodes"] == 0 or totals["old_links"] == 0):
        errors.append("HEAD comparison produced no baseline nodes or links")
    print(json.dumps({"actual": actual, "head": {"nodes": totals["old_nodes"], "links": totals["old_links"]}, "errors": len(errors)}, indent=2))
    if errors:
        print("\n".join(errors[:100]), file=sys.stderr)
        if len(errors) > 100: print(f"... {len(errors)-100} more errors", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
