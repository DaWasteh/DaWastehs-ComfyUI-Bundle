"""v1.3.1 workflow names: the rename map (tools/workflow_renames_v131.json) as lookups in both directions.

Keys are paths relative to ``workflows/``. Historical release tools, git refs up to v1.3.0 and the evidence reports
of older releases use the old names; the files carry the new ones."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENAME_FILE = ROOT / "tools" / "workflow_renames_v131.json"


@lru_cache(maxsize=1)
def renames() -> dict[str, str]:
    """v1.3.0 path -> v1.3.1 path."""
    return dict(json.loads(RENAME_FILE.read_text(encoding="utf-8"))["renames"])


@lru_cache(maxsize=1)
def previous_names() -> dict[str, str]:
    """v1.3.1 path -> v1.3.0 path."""
    return {new: old for old, new in renames().items()}


def old_key(key: str) -> str:
    return previous_names().get(key, key)


def new_key(key: str) -> str:
    return renames().get(key, key)


def original_name(key: str) -> str:
    """The name a workflow's identity is derived from: its v1.3.0 path, for old and new keys alike.

    The builders, generators and migrations derive ``workflow["id"]`` (uuid5 of the path), the subgraph ids of the
    central GPU control, ``extra.dawasteh_dual_gpu.source`` and ``.family`` from the workflow's path. v1.3.1 renamed
    the files but keeps that identity, so saved copies, the updater and the release evidence still recognize them:
    every such derivation goes through this function. Path-keyed tables (profiles, targets, manifests) use the new
    names and are looked up with the key itself."""
    return old_key(key)


def old_path(path: str) -> str:
    """A repository path ``workflows/<key>`` under its v1.3.0 name, for git refs up to v1.3.0; other paths unchanged."""
    prefix = "workflows/"
    return prefix + old_key(path[len(prefix):]) if path.startswith(prefix) else path


def current_path(key: str) -> Path:
    """The file for a workflow addressed by its v1.3.0 or v1.3.1 name."""
    return ROOT / "workflows" / new_key(key)
