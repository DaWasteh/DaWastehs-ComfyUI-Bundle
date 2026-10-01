"""v1.3.1: every workflow change of the release as a pure function of the v1.3.0 graphs.

Used by ``tools/validate_workflows.py --against-head`` to rebuild each changed workflow from the baseline and by the
tests. The individual repair scripts stay the tools that write the files:

* tools/build_finetune_fixes_v131.py      – the two "SDXL" finetunes rebuilt on their real architecture
* tools/fix_subgraph_device_values_v131.py – device strings removed from proxy-promoted subgraph instances
* tools/repair_widget_values_v131.py       – shifted Qwen3-TTS values, Director replay save
* tools/migrate_ltx_director_v131.py       – LTX Director nodes moved to the WhatDreamsCost 2.x schema
* tools/fix_gallery_findings_v131.py     – bugs found by the example runs (WAN 5B decode, Z-Image encoder, Kontext negative)
* tools/workflow_renames_v131.json         – new file names; ids and provenance keep the v1.3.0 names
                                             (tools/workflow_names_v131.original_name), only the two Mira-Scene
                                             notes that name each other change (their builder's output)

Every repair re-pins the RODENT topology hash of the graphs it changes (rodent_layout.refresh_topology_hashes), so the
repaired files stay idempotent under the v0.9.2 migration.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable

try:
    from tools import build_finetune_fixes_v131 as finetune
    from tools import fix_subgraph_device_values_v131 as subgraph_devices
    from tools import fix_gallery_findings_v131 as gallery_findings
    from tools import migrate_ltx_director_v131 as director
    from tools import repair_widget_values_v131 as widget_values
    from tools.workflow_names_v131 import new_key, old_key, previous_names, renames  # noqa: F401
except ModuleNotFoundError:  # run from inside tools/
    import build_finetune_fixes_v131 as finetune
    import fix_subgraph_device_values_v131 as subgraph_devices
    import fix_gallery_findings_v131 as gallery_findings
    import migrate_ltx_director_v131 as director
    import repair_widget_values_v131 as widget_values
    from workflow_names_v131 import new_key, old_key, previous_names, renames  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def expected(key: str, baseline: dict, ref_json: Callable[[str], dict]) -> dict | None:
    """The v1.3.1 form of workflow ``key`` (v1.3.0 path) built from its v1.3.0 graph ``baseline``.

    ``ref_json(key)`` loads another v1.3.0 workflow (the finetunes are rebuilt from their base graphs).
    Returns None when v1.3.1 leaves the graph unchanged."""
    fix = next((f for f in finetune.FIXES if f["target"] == key), None)
    if fix is not None:
        return finetune.build(fix, base=ref_json(fix["base"]), old=baseline)
    wf = copy.deepcopy(baseline)
    changed = bool(subgraph_devices.repair(wf))
    changed |= bool(widget_values.apply(key, wf))
    changed |= bool(gallery_findings.apply(key, wf))
    if key in director.WORKFLOWS:
        changed |= bool(director.migrate(wf))
    return wf if changed else None
