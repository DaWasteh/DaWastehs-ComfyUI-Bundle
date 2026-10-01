#!/usr/bin/env python3
"""v1.3.1: Qwen Image Edit 2511 · 8 camera angles with one shared model chain.

The workflow came from the official "multiple angles" template: the subgraph "Qwen-Image 2511: Batch Angle Generation"
holds eight copies of "Image Edit (Qwen-Image 2511 with LoRA)", and every copy loaded its own diffusion model
(``qwen_image_edit_2511_bf16``, 41 GB), text encoder, VAE and both LoRAs. On a 47 GB machine the RAM-pressure cache
dropped the first model while it was still loaded, the second angle loaded another copy, and the system commit reached
173 GiB after two of eight angles (gallery run 2026-09-30).

The chain UNETLoader -> Select Model Device -> multiple-angles LoRA -> ModelSamplingAuraFlow -> CFGNorm
(-> Lightning LoRA when ``value`` is on) and the text encoder and VAE loaders with their device selectors now exist
once, in the outer subgraph, and feed MODEL / CLIP / VAE inputs of the eight angle subgraphs. Every angle samples with
the same model object: one load for all eight images. Prompts, steps, CFG, sizes and the Lightning switch are
unchanged. The outer input ``lora_name_1_1`` (a second copy of the angles LoRA) is gone; the device selectors read
``daw_model_device`` / ``daw_clip_device`` / ``daw_vae_device`` of the outer subgraph like before in every copy.

The workflow is addressed by its v1.3.0 name ``Image Editing/Multi-Character-Angles-One-Click.json``.
"""
from __future__ import annotations

import copy
import re
import uuid

OUTER_NAME = "Qwen-Image 2511: Batch Angle Generation"
INNER_NAME = "Image Edit (Qwen-Image 2511 with LoRA)"
MOVED_TYPES = ("UNETLoader", "SelectModelDevice", "LoraLoaderModelOnly", "ModelSamplingAuraFlow", "CFGNorm",
               "CLIPLoader", "SelectCLIPDevice", "VAELoader", "SelectVAEDevice")
REMOVED_INNER_INPUTS = ("unet_name", "clip_name", "vae_name", "lora_name", "lora_name_1",
                        "daw_model_device", "daw_clip_device", "daw_vae_device")
DEVICE_INPUTS = ("daw_model_device", "daw_clip_device", "daw_vae_device")
NAMESPACE = uuid.UUID("5b0b1c0e-6d3a-4f39-9d0e-7a1b2c3d4e5f")
NOTE_PROPERTY = "dawasteh_note_for"
HF = "https://huggingface.co/"
USER_NOTE_TITLE = "For Local User"
USER_NOTE = (  # the template's note listed the 2509 files; the workflow loads 2511
    "## Modelle (Qwen Image Edit 2511)\n\n"
    "**diffusion_models** (Ordner `Qwen`, eine der beiden Dateien im Feld `unet_name` wählen)\n\n"
    f"- [qwen_image_edit_2511_bf16.safetensors]({HF}Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/"
    "diffusion_models/qwen_image_edit_2511_bf16.safetensors) – 41 GB, Standard\n"
    f"- [qwen_image_edit_2511_int8_convrot.safetensors]({HF}Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/"
    "split_files/diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors) – 20,5 GB, halber Speicher\n\n"
    "**loras** (Ordner `Qwen`)\n\n"
    f"- [qwen-image-edit-2511-multiple-angles-lora.safetensors]({HF}fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA/"
    "resolve/main/qwen-image-edit-2511-multiple-angles-lora.safetensors)\n"
    f"- [Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors]({HF}lightx2v/Qwen-Image-Edit-2511-Lightning/"
    "resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors)\n\n"
    "**text_encoders** (Ordner `Qwen`)\n\n"
    f"- [qwen_2.5_vl_7b_fp8_scaled.safetensors]({HF}Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/"
    "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors)\n\n"
    "**vae** (Ordner `Qwen`)\n\n"
    f"- [qwen_image_vae.safetensors]({HF}Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/"
    "qwen_image_vae.safetensors)\n\n"
    "## Aufbau seit v1.3.1\n\n"
    "Modell, Text-Encoder, VAE und beide LoRAs werden **einmal** geladen (im Subgraph „Qwen-Image 2511: Batch Angle "
    "Generation“) und von allen acht Winkeln geteilt. In der offiziellen Vorlage lud jeder Winkel eine eigene Kopie; "
    "mit dem bf16-Modell stieg der System-Commit so schon nach zwei Winkeln auf 173 GB. `value` schaltet die "
    "Lightning-LoRA (4 Schritte) ein oder aus.\n\n"
    "Vorlage: [ComfyUI workflow templates](https://github.com/Comfy-Org/workflow_templates)"
)


def _uuid(*parts) -> str:
    return str(uuid.uuid5(NAMESPACE, "/".join(str(p) for p in parts)))


def _links(graph: dict) -> dict:
    return {link["id"]: link for link in graph.get("links", [])}


def _notes(graph: dict) -> dict:
    return {(n.get("properties") or {}).get(NOTE_PROPERTY): n for n in graph.get("nodes", [])
            if (n.get("properties") or {}).get("dawasteh_generated_note")}


class Ids:
    """Global node / link counters (the frontend shares them between the root graph and all subgraphs)."""

    def __init__(self, wf: dict):
        graphs = [wf, *wf["definitions"]["subgraphs"]]
        self.node = max(max((n["id"] for g in graphs for n in g["nodes"] if isinstance(n["id"], int)), default=0),
                        int(wf.get("last_node_id", 0)))
        link_ids = [l[0] for l in wf.get("links", [])] + [l["id"] for g in graphs[1:] for l in g.get("links", [])]
        self.link = max(max(link_ids, default=0), int(wf.get("last_link_id", 0)))

    def next_node(self) -> int:
        self.node += 1
        return self.node

    def next_link(self) -> int:
        self.link += 1
        return self.link


def _remove_link(graph: dict, link_id: int) -> None:
    link = _links(graph).get(link_id)
    if link is None:
        return
    graph["links"] = [l for l in graph["links"] if l["id"] != link_id]
    nodes = {n["id"]: n for n in graph["nodes"]}
    origin, target = nodes.get(link["origin_id"]), nodes.get(link["target_id"])
    if origin is not None:
        out = origin["outputs"][link["origin_slot"]]
        out["links"] = [l for l in (out.get("links") or []) if l != link_id] or None
    if target is not None:
        for item in target.get("inputs", []):
            if item.get("link") == link_id:
                item["link"] = None
    for item in graph.get("inputs", []):
        if link_id in item.get("linkIds", []):
            item["linkIds"] = [l for l in item["linkIds"] if l != link_id]


def _add_link(graph: dict, ids: Ids, origin_id: int, origin_slot: int, target_id: int, target_slot: int,
              link_type: str) -> int:
    link_id = ids.next_link()
    graph["links"].append({"id": link_id, "origin_id": origin_id, "origin_slot": origin_slot, "target_id": target_id,
                           "target_slot": target_slot, "type": link_type})
    nodes = {n["id"]: n for n in graph["nodes"]}
    if origin_id == -10:
        graph["inputs"][origin_slot].setdefault("linkIds", []).append(link_id)
    else:
        out = nodes[origin_id]["outputs"][origin_slot]
        out["links"] = [*(out.get("links") or []), link_id]
    nodes[target_id]["inputs"][target_slot]["link"] = link_id
    return link_id


def _renumber_input_slots(graph: dict) -> None:
    """Links from the subgraph input node use the position in ``inputs`` as origin_slot."""
    slot_of = {lid: index for index, item in enumerate(graph["inputs"]) for lid in item.get("linkIds", [])}
    for link in graph["links"]:
        if link["origin_id"] == -10 and link["id"] in slot_of:
            link["origin_slot"] = slot_of[link["id"]]


def refresh_note(note: dict, node: dict, graph: dict, new_id: int | None = None) -> None:
    """Rewrite the node id and the link lines of a generated note after rewiring."""
    text = note["widgets_values"][0]
    if new_id is not None:
        old = (note.get("properties") or {}).get(NOTE_PROPERTY)
        text = re.sub(rf"· Node {old}\b", f"· Node {new_id}", text)
        note["title"] = re.sub(rf"· Node {old}\b", f"· Node {new_id}", note.get("title") or "")
        note["properties"][NOTE_PROPERTY] = new_id
    inputs = {i["name"]: i for i in node.get("inputs", [])}
    outputs = {o["name"]: o for o in node.get("outputs", [])}
    section, lines = None, []
    for line in text.split("\n"):
        if line.startswith("**Eingänge**"):
            section = "in"
        elif line.startswith("**Ausgänge**"):
            section = "out"
        elif line.startswith("**"):
            section = None
        m = re.match(r"^- `([^`]+)` \(([^,]+), (Link \d+|nicht verbunden|\d+ Verbindung\(en\))\)(.*)$", line)
        if m and section == "in" and m.group(1) in inputs:
            link = inputs[m.group(1)].get("link")
            line = f"- `{m.group(1)}` ({m.group(2)}, {f'Link {link}' if link is not None else 'nicht verbunden'}){m.group(4)}"
        elif m and section == "out" and m.group(1) in outputs:
            count = len(outputs[m.group(1)].get("links") or [])
            line = f"- `{m.group(1)}` ({m.group(2)}, {f'{count} Verbindung(en)' if count else 'nicht verbunden'}){m.group(4)}"
        if section == "in" and m and m.group(1) not in inputs:
            continue  # input removed from the node
        lines.append(line)
    note["widgets_values"] = ["\n".join(lines)]


def _model_switch(graph: dict) -> dict:
    nodes = {n["id"]: n for n in graph["nodes"]}
    links = _links(graph)
    sampler = next(n for n in graph["nodes"] if n["type"] == "KSampler")
    model_in = next(i for i in sampler["inputs"] if i["name"] == "model")
    return nodes[links[model_in["link"]]["origin_id"]]


def _moved_nodes(graph: dict) -> list[dict]:
    switch = _model_switch(graph)
    return [n for n in graph["nodes"] if n["type"] in MOVED_TYPES] + [switch]


def strip_angle(inner: dict, ids: Ids) -> dict:
    """Remove the model chain from one angle subgraph; returns the new MODEL / CLIP / VAE input targets."""
    moved = {n["id"] for n in _moved_nodes(inner)}
    links = _links(inner)
    targets: dict[str, list[tuple[int, int]]] = {"MODEL": [], "CLIP": [], "VAE": []}
    for link in list(links.values()):
        if link["origin_id"] in moved and link["target_id"] not in moved and link["type"] in targets:
            targets[link["type"]].append((link["target_id"], link["target_slot"]))
    for link in list(links.values()):
        if link["origin_id"] in moved or link["target_id"] in moved:
            _remove_link(inner, link["id"])
    notes = _notes(inner)
    inner["nodes"] = [n for n in inner["nodes"] if n["id"] not in moved and
                      (n.get("properties") or {}).get(NOTE_PROPERTY) not in moved]
    inner["inputs"] = [i for i in inner["inputs"] if i["name"] not in REMOVED_INNER_INPUTS]
    for name, kind in (("model", "MODEL"), ("clip", "CLIP"), ("vae", "VAE")):
        inner["inputs"].append({"id": _uuid(inner["id"], name), "name": name, "type": kind, "linkIds": [],
                                "pos": [-80.0, 120.0 + 20.0 * len(inner["inputs"])]})
        slot = len(inner["inputs"]) - 1
        for target_id, target_slot in targets[kind]:
            _add_link(inner, ids, -10, slot, target_id, target_slot, kind)
    _renumber_input_slots(inner)
    nodes = {n["id"]: n for n in inner["nodes"]}
    for target, note in notes.items():
        if target in nodes:
            refresh_note(note, nodes[target], inner)
    inner["extra"]["dawasteh_workflow_refinement"]["generated_notes"] = len(_notes(inner))
    return targets


def restructure(wf: dict) -> list:
    subgraphs = (wf.get("definitions") or {}).get("subgraphs") or []
    outer = next((g for g in subgraphs if g.get("name") == OUTER_NAME), None)
    if outer is None or any(i["name"] == "model" for g in subgraphs if g.get("name") == INNER_NAME for i in g["inputs"]):
        return []  # not the v1.3.0 structure (or already restructured)
    inners = {g["id"]: g for g in subgraphs if g.get("name") == INNER_NAME}
    instances = [n for n in outer["nodes"] if n["type"] in inners]
    if len(instances) != 8:
        return []
    ids = Ids(wf)
    template = inners[instances[0]["type"]]
    template_nodes = {n["id"]: n for n in template["nodes"]}
    template_links = _links(template)
    template_notes = _notes(template)
    moved_template = _moved_nodes(template)
    boolean = next(n for n in template["nodes"] if n["type"] == "PrimitiveBoolean")
    template_input_names = [i["name"] for i in template["inputs"]]  # before stripping: origin_slot -> name

    # 1) the eight angle subgraphs lose their loaders
    for inner in inners.values():
        strip_angle(inner, ids)

    # 2) the outer subgraph drops the per-angle loader inputs and gains the shared chain
    outer_links = _links(outer)
    for inst in instances:
        for item in list(inst["inputs"]):
            if item["name"] in REMOVED_INNER_INPUTS:
                if item.get("link") is not None:
                    _remove_link(outer, item["link"])
                inst["inputs"].remove(item)
        widget_names = [i["name"] for i in inst["inputs"] if i.get("widget")]
        inst["widgets_values"] = inst["widgets_values"][:len(widget_names)]
    for item in list(outer["inputs"]):
        if item["name"] == "lora_name_1_1":
            for lid in list(item.get("linkIds", [])):
                _remove_link(outer, lid)
            outer["inputs"].remove(item)
    for name in DEVICE_INPUTS:
        outer["inputs"].append({"id": _uuid(outer["id"], name), "name": name, "type": "COMBO", "linkIds": [],
                                "pos": [-80.0, 120.0 + 20.0 * len(outer["inputs"])]})
    _renumber_input_slots(outer)

    new_id: dict[int, int] = {}
    for node in [*moved_template, boolean]:
        clone = {k: (v if not isinstance(v, (dict, list)) else copy.deepcopy(v)) for k, v in node.items()}
        clone["id"] = new_id[node["id"]] = ids.next_node()
        for item in clone.get("inputs", []):
            item["link"] = None
        for out in clone.get("outputs", []):
            out["links"] = None
        outer["nodes"].append(clone)
    # internal links of the chain, as in the template
    for link in template_links.values():
        if link["origin_id"] in new_id and link["target_id"] in new_id:
            _add_link(outer, ids, new_id[link["origin_id"]], link["origin_slot"], new_id[link["target_id"]],
                      link["target_slot"], link["type"])
    # outer subgraph inputs -> chain (the template read them from its own subgraph inputs)
    outer_slot = {i["name"]: index for index, i in enumerate(outer["inputs"])}
    for link in template_links.values():
        if link["origin_id"] == -10 and link["target_id"] in new_id:
            name = template_input_names[link["origin_slot"]]
            if name in outer_slot:
                _add_link(outer, ids, -10, outer_slot[name], new_id[link["target_id"]], link["target_slot"],
                          link["type"])
    # chain -> the eight angles
    switch = new_id[moved_template[-1]["id"]]  # _moved_nodes() lists the model switch last
    selector = {n["type"]: new_id[n["id"]] for n in moved_template if n["type"].startswith("Select")}
    sources = {"model": (switch, 0, "MODEL"), "clip": (selector["SelectCLIPDevice"], 0, "CLIP"),
               "vae": (selector["SelectVAEDevice"], 0, "VAE")}
    for inst in instances:
        for name, (origin, slot, kind) in sources.items():
            inst["inputs"].append({"name": name, "type": kind, "link": None})
            _add_link(outer, ids, origin, slot, inst["id"], len(inst["inputs"]) - 1, kind)
    # notes: move the template's notes of the chain, refresh the instance notes
    outer_nodes = {n["id"]: n for n in outer["nodes"]}
    for old, new in new_id.items():
        note = copy.deepcopy(template_notes[old])
        note["id"] = ids.next_node()
        refresh_note(note, outer_nodes[new], outer, new_id=new)
        outer["nodes"].append(note)
    for target, note in _notes(outer).items():
        if target in outer_nodes:
            refresh_note(note, outer_nodes[target], outer)
    outer["extra"]["dawasteh_workflow_refinement"]["generated_notes"] = len(_notes(outer))

    # 3) root: the outer instance loses lora_name_1_1
    root_instance = next(n for n in wf["nodes"] if n["type"] == outer["id"])
    for item in list(root_instance["inputs"]):
        if item["name"] == "lora_name_1_1":
            if item.get("link") is not None:
                raise ValueError("lora_name_1_1 is connected on the root instance")
            # promoted widgets = every input except the image, in input order
            widget_index = [i["name"] for i in root_instance["inputs"] if i["type"] != "IMAGE"].index("lora_name_1_1")
            root_instance["inputs"].remove(item)
            del root_instance["widgets_values"][widget_index]
    user_note = next((n for n in wf["nodes"] if n.get("title") == USER_NOTE_TITLE and n["type"] == "MarkdownNote"), None)
    if user_note is not None:
        user_note["widgets_values"] = [USER_NOTE]
    root_note = _notes(wf).get(root_instance["id"])
    if root_note is not None:
        refresh_note(root_note, root_instance, wf)

    # 4) counters and markers
    for graph in [*subgraphs]:
        graph["last_node_id"] = ids.node
        graph.setdefault("state", {}).update({"lastNodeId": ids.node, "lastLinkId": ids.link})
    wf["last_node_id"], wf["last_link_id"] = ids.node, ids.link
    gpu = (wf.get("extra") or {}).get("dawasteh_dual_gpu")
    if isinstance(gpu, dict):
        gpu["selector_count"] = 3
        gpu["v131_shared_chain"] = "one model / text encoder / VAE chain for all eight angles"
    return [root_instance["id"], outer["id"]]
