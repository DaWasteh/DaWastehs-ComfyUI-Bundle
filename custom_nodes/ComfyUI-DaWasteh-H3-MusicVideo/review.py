"""v1.2.5 scene review for the FastH3 music video (MV 5b).

After MV 5 has saved a scene, MV 5b shows it with the original song audio in the node and waits for
the user's decision:

- continue:     accept the shown take (the current one or an earlier one) and render the next scene
- redo:         move the current take to takes/, give the scene a new seed and render it again in the
                same run (node expansion: MV 5b clones its own scene chain Setup -> sampler -> MV 5 -> MV 5b)
- continue_all: accept and stop asking for the rest of this run

The decision travels from the browser through POST /dawasteh/mv2/review; the node polls for it and
honours ComfyUI's Cancel button. Everything that must survive a restart (take, seed, review state,
archived takes) lives in plan.json, so a resumed run shows a scene that was left unreviewed again
and passes accepted scenes straight through.

No ComfyUI import at module level: the tests load this file on its own.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

EVENT = "dawasteh-mv2-review"
EVENT_DONE = "dawasteh-mv2-review-done"
ROUTE = "/dawasteh/mv2/review"
ACTIONS = ("continue", "redo", "continue_all")
SETUP_CLASS = "DaWMV2SceneSetup"
PENDING, APPROVED = "pending", "approved"
FILE_SUFFIXES = {"video": ".mp4", "tail": "_tail_latent.pt", "sheet": "_sheet.png", "preview": "_with_audio.mp4"}
# per-take bookkeeping that moves between the scene and its archive entry
TAKE_FIELDS = ("seed", "render_key", "verified_frames", "completed_at")


# ---------------------------------------------------------------------------
# Tokens and review state
# ---------------------------------------------------------------------------

def parse_token(token: str) -> tuple[str, int | None]:
    """MV 5 token 'plan|index|render_key' (or 'plan|end' past the last scene) -> (plan, index or None)."""
    parts = str(token).rsplit("|", 2)
    if len(parts) == 3 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return str(token).rsplit("|", 1)[0], None


def needs_review(scene: dict[str, Any]) -> bool:
    """Only scenes that MV 5 rendered since v1.2.5 and nobody accepted yet. Scenes of older projects
    (no review field) were accepted under the old single approval gate and pass through."""
    return scene.get("review") == PENDING


def take_of(scene: dict[str, Any]) -> int:
    return int(scene.get("take", 0))


def take_files(project: Path, index: int, take: int) -> dict[str, Path]:
    root = Path(project) / "takes"
    return {key: root / f"scene_{index:04d}_take{take:02d}{suffix}" for key, suffix in FILE_SUFFIXES.items()}


def _move_files(source: dict[str, Path], target: dict[str, Path]) -> None:
    for key, path in source.items():
        if path.is_file():
            target[key].parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target[key])


def archive_current_take(scene: dict[str, Any], index: int, current: dict[str, Path], project: Path) -> int:
    """Move the scene's rendered files to takes/ and remember the take's seed and keys there."""
    take = take_of(scene)
    _move_files(current, take_files(project, index, take))
    entry = {"take": take, **{k: scene[k] for k in TAKE_FIELDS if k in scene}}
    scene.setdefault("takes", {})[str(take)] = entry
    for key in (*TAKE_FIELDS, "review"):
        if key != "seed":
            scene.pop(key, None)
    return take


def start_new_take(scene: dict[str, Any], index: int, current: dict[str, Path], project: Path,
                   seed_for_take: Callable[[int], int]) -> int:
    """Redo: archive the current take and give the scene the seed of a fresh take number."""
    archive_current_take(scene, index, current, project)
    used = [take_of(scene)] + [int(t) for t in scene.get("takes", {})]
    new_take = max(used) + 1
    scene["take"] = new_take
    scene["seed"] = int(seed_for_take(new_take))
    return new_take


def restore_take(scene: dict[str, Any], index: int, take: int, current: dict[str, Path], project: Path) -> None:
    """Make an earlier take the scene's current one again; the take shown so far moves to takes/."""
    if take == take_of(scene):
        return
    entry = scene.get("takes", {}).get(str(take))
    if entry is None:
        raise KeyError(f"Scene {index + 1} has no take {take + 1}")
    source = take_files(project, index, take)
    if not source["video"].is_file() or not source["tail"].is_file():
        raise FileNotFoundError(f"Take {take + 1} of scene {index + 1} is missing its files in {source['video'].parent}")
    archive_current_take(scene, index, current, project)
    _move_files(source, current)
    del scene["takes"][str(take)]
    scene["take"] = take
    scene.update({k: entry[k] for k in TAKE_FIELDS if k in entry})


def review_takes(scene: dict[str, Any], index: int, current: dict[str, Path], project: Path) -> list[dict[str, Any]]:
    """All takes of a scene that can still be shown, oldest first; 'path' is the preview with audio."""
    rows = [{"take": take_of(scene), "seed": scene.get("seed"), "current": True, "path": current["preview"]}]
    for key, entry in scene.get("takes", {}).items():
        preview = take_files(project, index, int(key))["preview"]
        if preview.is_file():
            rows.append({"take": int(key), "seed": entry.get("seed"), "current": False, "path": preview})
    return sorted(rows, key=lambda row: row["take"])


# ---------------------------------------------------------------------------
# Redo inside the running prompt: clone the scene chain of this review node
# ---------------------------------------------------------------------------

def _parents(dynprompt, node_id: str) -> list[str]:
    from comfy_execution.graph_utils import is_link

    return [v[0] for v in dynprompt.get_node(node_id)["inputs"].values() if is_link(v)]


def scene_chain(dynprompt, review_id: str) -> list[str]:
    """Ids of this review node and every node on a path from this scene's Setup node to it (Setup, noise, guider,
    sampler, MV 5). Model, VAEs, sampler settings, plan and loop index are shared, not cloned.

    This scene's Setup is the nearest one upstream. Earlier scenes have Setup nodes upstream too: in the first loop
    round Loop Start carries scene 1's review token, and through it scene 1's whole chain is an ancestor."""
    setup, seen, frontier = None, {review_id}, [review_id]
    while frontier and setup is None:   # breadth first: the nearest Setup wins
        next_frontier = []
        for node_id in frontier:
            for parent in _parents(dynprompt, node_id):
                if parent not in seen:
                    seen.add(parent)
                    next_frontier.append(parent)
                    if setup is None and dynprompt.get_node(parent)["class_type"] == SETUP_CLASS:
                        setup = parent
        frontier = next_frontier
    if setup is None:
        raise RuntimeError("MV 5b · Szene prüfen: no 'MV 4 · Szene vorbereiten' upstream; wire MV 5 (token) into this node")

    memo: dict[str, bool] = {}

    def from_setup(node_id: str) -> bool:
        if node_id not in memo:
            memo[node_id] = False
            memo[node_id] = node_id == setup or any(from_setup(p) for p in _parents(dynprompt, node_id))
        return memo[node_id]

    chain, stack = [review_id], [review_id]
    while stack:
        for parent in _parents(dynprompt, stack.pop()):
            if parent not in chain and from_setup(parent):
                chain.append(parent)
                stack.append(parent)
    return chain


def clone_scene_chain(dynprompt, review_id: str, take: int):
    """GraphBuilder with a copy of the scene chain. The cloned Setup gets an extra 'take' input: it is not
    part of the node's schema (ignored on execution) but part of its cache signature, so the sampler chain
    runs again instead of returning the cached result of the rejected take."""
    from comfy_execution.graph_utils import GraphBuilder, is_link

    chain = scene_chain(dynprompt, review_id)
    graph = GraphBuilder()
    for node_id in chain:
        clone = graph.node(dynprompt.get_node(node_id)["class_type"], node_id)
        clone.set_override_display_id(dynprompt.get_display_node_id(node_id))
    for node_id in chain:
        node = dynprompt.get_node(node_id)
        clone = graph.lookup_node(node_id)
        for key, value in node["inputs"].items():
            if is_link(value) and value[0] in chain:
                clone.set_input(key, graph.lookup_node(value[0]).out(value[1]))
            else:
                clone.set_input(key, value)
        if node["class_type"] == SETUP_CLASS:
            clone.set_input("take", int(take))
    return graph, graph.lookup_node(review_id)


# ---------------------------------------------------------------------------
# Waiting for the browser
# ---------------------------------------------------------------------------

class ReviewGate:
    """One review can be open at a time (ComfyUI executes one prompt at a time)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: dict[str, Any] | None = None
        self._decisions: dict[str, dict[str, Any]] = {}
        self._auto: dict[str, str] = {}

    def pending(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._pending) if self._pending else {}

    def decide(self, body: dict[str, Any]) -> tuple[bool, str]:
        action = body.get("action")
        if action not in ACTIONS:
            return False, f"unknown action {action!r}"
        with self._lock:
            pending = self._pending
            if not pending or body.get("id") != pending["id"]:
                return False, "no open review with this id"
            take = body.get("take")
            if take is not None:
                try:
                    take = int(take)
                except (TypeError, ValueError):
                    return False, f"invalid take {take!r}"
                if take not in {row["take"] for row in pending.get("takes", [])}:
                    return False, f"scene has no take {take + 1}"
            self._decisions[pending["id"]] = {"action": action, "take": take}
        return True, "ok"

    def auto_active(self, plan: str, prompt_id: str) -> bool:
        with self._lock:
            return bool(prompt_id) and self._auto.get(plan) == prompt_id

    def set_auto(self, plan: str, prompt_id: str) -> None:
        with self._lock:
            self._auto[plan] = prompt_id

    def wait(self, payload: dict[str, Any], send: Callable[[str, dict], None], check_interrupt: Callable[[], None],
             poll: float = 0.25) -> dict[str, Any]:
        review_id = uuid.uuid4().hex
        payload = {**payload, "id": review_id}
        with self._lock:
            self._pending = payload
            self._decisions.clear()
        send(EVENT, payload)
        try:
            while True:
                check_interrupt()
                with self._lock:
                    decision = self._decisions.pop(review_id, None)
                if decision is not None:
                    return decision
                time.sleep(poll)
        finally:
            with self._lock:
                if self._pending and self._pending["id"] == review_id:
                    self._pending = None
            send(EVENT_DONE, {"id": review_id})


GATE = ReviewGate()


def register_routes(gate: ReviewGate = GATE) -> bool:
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception:
        return False
    routes = PromptServer.instance.routes

    @routes.get(ROUTE)
    async def _pending(request):
        pending = gate.pending()
        return web.json_response({k: v for k, v in pending.items() if k != "plan"} if pending else {})

    @routes.post(ROUTE)
    async def _decide(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON body expected"}, status=400)
        ok, message = gate.decide(body if isinstance(body, dict) else {})
        return web.json_response({"ok": ok, "error": None if ok else message}, status=200 if ok else 409)

    return True
