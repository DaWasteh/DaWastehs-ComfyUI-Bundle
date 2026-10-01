"""Print a compact view of a UI workflow: nodes (without notes) with mode, title, widget values and their links.

  python tools/examples/graph_dump.py "workflows/Image Editing/FLUX2_Klein_4B-One-Image-Edit.json"
"""
from __future__ import annotations

import json
import sys

SKIP = {"MarkdownNote", "Note", "PixaromaNote", "PixaromaLabel", "PixaromaRunTimer", "VRAM_Debug"}


def dump(nodes, links, indent=""):
    by_id = {n["id"]: n for n in nodes}
    link_map = {}
    for link in links:
        if isinstance(link, dict):
            lid, src, sslot, dst, dslot = link["id"], link["origin_id"], link["origin_slot"], link["target_id"], link["target_slot"]
        else:
            lid, src, sslot, dst, dslot = link[:5]
        link_map[lid] = (src, sslot, dst, dslot)
    for n in nodes:
        if n["type"] in SKIP:
            continue
        mode = {0: "", 2: " MUTED", 4: " BYPASS"}.get(n.get("mode", 0), "")
        wv = n.get("widgets_values")
        wv_s = json.dumps(wv, ensure_ascii=False)
        if len(wv_s) > 160:
            wv_s = wv_s[:160] + "…"
        ins = []
        for i in n.get("inputs") or []:
            if i.get("link") is not None and i["link"] in link_map:
                src = link_map[i["link"]][0]
                ins.append(f"{i['name']}<-{src}:{by_id.get(src, {}).get('type', '?')}")
        props = n.get("properties") or {}
        extra = ""
        if "promptState" in props:
            extra = " prompt=" + json.dumps(props["promptState"].get("text", "")[:100], ensure_ascii=False)
        print(f"{indent}{n['id']} {n['type']}{mode} '{n.get('title') or ''}' {wv_s}{extra}")
        if ins:
            print(f"{indent}    in: {', '.join(ins)}")


def main():
    wf = json.load(open(sys.argv[1], encoding="utf-8"))
    dump(wf.get("nodes", []), wf.get("links", []))
    for sg in (wf.get("definitions") or {}).get("subgraphs") or []:
        print(f"== subgraph {sg.get('name')} ({sg.get('id')})")
        dump(sg.get("nodes", []), sg.get("links", []), "   ")


if __name__ == "__main__":
    main()
