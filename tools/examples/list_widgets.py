"""Load workflows into the frontend (no queueing) and list the widgets of chosen nodes as the frontend sees them.

  L:/ComfyUI/tmp/minimax-test-venv/Scripts/python.exe tools/examples/list_widgets.py "<rel.json>" [...] [--all]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_driver import ComfyDriver, load_workflow  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

JS = r"""
const all = arguments[0];
const { app } = window.comfyAPI.app;
const out = [];
for (const n of app.graph._nodes) {
  const isSub = !!n.subgraph;
  if (!all && !isSub) continue;
  if (['MarkdownNote', 'Note', 'PixaromaNote', 'PixaromaLabel'].includes(n.type)) continue;
  out.push({id: n.id, type: isSub ? 'SUBGRAPH ' + (n.subgraph.name || '') : n.type, title: n.title,
            widgets: (n.widgets || []).map(w => [w.name, typeof w.value === 'string' ? w.value.slice(0, 60) : w.value])});
}
return out;
"""


def main() -> None:
    args = []
    for a in sys.argv[1:]:
        if a.startswith("@"):
            args += [line.strip() for line in Path(a[1:]).read_text(encoding="utf-8").splitlines() if line.strip()]
        elif not a.startswith("--"):
            args.append(a)
    d = ComfyDriver()
    try:
        d.open()
        for rel in args:
            d.load(load_workflow(ROOT / "workflows" / rel))
            print("##", rel)
            for n in d.driver.execute_script(JS, "--all" in sys.argv):
                print(f"  {n['id']} {n['type']} '{n['title']}'")
                for w in n["widgets"]:
                    print("      ", json.dumps(w, ensure_ascii=False)[:140])
    finally:
        d.close()


if __name__ == "__main__":
    main()
