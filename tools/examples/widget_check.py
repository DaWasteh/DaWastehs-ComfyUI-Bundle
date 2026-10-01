"""Check every widget of every workflow as the frontend loads it against the node definitions (/object_info).

Finds values that ended up in the wrong widget after a node gained or lost an input (a string in a number field,
top_p = 20, a sampler name in a strength field ...), combo values that are not offered (missing model file or renamed
option) and numbers outside the allowed range. Needs a running ComfyUI (default: the example test server).

  L:/ComfyUI/tmp/minimax-test-venv/Scripts/python.exe tools/examples/widget_check.py [--only substring] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_driver import ComfyDriver, load_workflow  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SKIP_TYPES = {"MarkdownNote", "Note", "PixaromaNote", "PixaromaLabel", "PrimitiveNode", "Reroute"}
SKIP_WIDGETS = {"control_after_generate", "control_before_generate", "upload", "audioUI", "videoUI", "run_timer_ui",
                "image_upload", "preview", "control_filter_list"}

JS = r"""
const { app } = window.comfyAPI.app;
const out = [];
const safe = v => {
  if (v === null || v === undefined || ['string', 'number', 'boolean'].includes(typeof v)) return v === undefined ? null : v;
  try { return '§obj:' + JSON.stringify(v).slice(0, 200); } catch (e) { return '§obj'; }
};
const visit = (graph, path) => {
  for (const n of graph._nodes || graph.nodes || []) {
    if (n.subgraph) { visit(n.subgraph, path.concat([String(n.id)])); continue; }
    const linked = new Set((n.inputs || []).filter(i => i.link != null && i.widget).map(i => i.widget.name || i.name));
    out.push({id: n.id, path: path.join('/'), type: n.type, title: n.title || '', mode: n.mode || 0,
              widgets: (n.widgets || []).filter(w => w.name && !linked.has(w.name)).map(w => [w.name, safe(w.value)])});
  }
};
visit(app.graph, []);
return out;
"""


def check_value(spec, value):
    """Return a problem string or None."""
    kind = spec[0]
    opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if isinstance(kind, list):
        if value not in kind and kind:
            return f"not an option: {value!r}"
        return None
    if kind == "COMBO":
        options = opts.get("options") or []
        if options and value not in options:
            return f"not an option: {value!r}"
        return None
    if kind == "INT" or kind == "FLOAT":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{kind} expected, got {value!r}"
        lo, hi = opts.get("min"), opts.get("max")
        if lo is not None and value < lo - 1e-9:
            return f"{value} < min {lo}"
        if hi is not None and value > hi + 1e-9:
            return f"{value} > max {hi}"
        return None
    if kind == "BOOLEAN":
        if not isinstance(value, bool):
            return f"BOOLEAN expected, got {value!r}"
        return None
    if kind == "STRING":
        if not isinstance(value, str):
            return f"STRING expected, got {value!r}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--url", default="http://127.0.0.1:8192")
    args = ap.parse_args()
    d = ComfyDriver(args.url)
    report = {}
    try:
        d.open()
        info = d.get_json("/object_info", timeout=120)
        for path in sorted((ROOT / "workflows").rglob("*.json")):
            rel = path.relative_to(ROOT / "workflows").as_posix()
            if args.only and args.only not in rel:
                continue
            try:
                d.load(load_workflow(path))
            except Exception as exc:
                report[rel] = [f"LOAD FAILED: {exc}"[:300]]
                print(rel, "LOAD FAILED")
                continue
            problems = []
            try:
                nodes = d.driver.execute_script(JS)
            except Exception as exc:
                report[rel] = [f"READ FAILED: {type(exc).__name__}"]
                print(rel, "READ FAILED", flush=True)
                continue
            for n in nodes:
                if n["type"] in SKIP_TYPES:
                    continue
                spec_all = info.get(n["type"])
                if not spec_all:
                    problems.append(f"{n['path'] + '/' if n['path'] else ''}{n['id']} {n['type']}: unknown node type")
                    continue
                inputs = {**(spec_all["input"].get("required") or {}), **(spec_all["input"].get("optional") or {})}
                for name, value in n["widgets"]:
                    if name in SKIP_WIDGETS or name not in inputs or (isinstance(value, str) and value.startswith("§obj")):
                        continue
                    problem = check_value(inputs[name], value)
                    if problem:
                        muted = " (muted/bypassed)" if n["mode"] in (2, 4) else ""
                        where = f"{n['path'] + '/' if n['path'] else ''}{n['id']}"
                        problems.append(f"{where} {n['type']} '{n['title']}'.{name}: {problem}{muted}"[:400])
            report[rel] = problems
            print(rel, len(problems), "problem(s)", flush=True)
            for p in problems:
                print("   ", p, flush=True)
    finally:
        d.close()
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
