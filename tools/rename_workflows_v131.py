#!/usr/bin/env python3
"""v1.3.1: rename workflows to the scheme <Model>[_<Variant>]_<Quant>[+<Helper>]-<Input>-to-<Output>[-<Purpose>].

The map lives in tools/workflow_renames_v131.json. The script
  1. keeps the git attributes (eol) each file had under its old name,
  2. moves the files with ``git mv`` (content and SHA-256 stay the same),
  3. rewrites references in tracked text files (tools, tests, docs, README, evidence reports, node packs),
  4. adds every rename to the updater's $WorkflowMigrationMap, so a locally changed old file is kept and the log names
     its replacement.

The provenance field ``extra.dawasteh_dual_gpu.source`` inside the workflows keeps the historical path on purpose.

  python tools/rename_workflows_v131.py [--dry-run]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
SKIP_PREFIXES = ("workflows/", "tools/workflow_templates/", "tools/patches/", "performance/rdna4/raw/",
                 "performance/rdna4/baseline_state/", "performance/rdna4/workflows/", "performance/rdna4/logs/",
                 "examples/", ".git", "tools/examples/")
# the v1.3.1 repair tools describe the step v1.3.0 -> v1.3.1 and address the workflows by their v1.3.0 names; the
# example tools (catalog, run folders) do the same and map through the rename file
SKIP_FILES = {"tools/workflow_renames_v131.json", "tools/rename_workflows_v131.py", "tools/workflow_fixes_v131.py",
              "tools/build_finetune_fixes_v131.py", "tools/repair_widget_values_v131.py",
              "tools/migrate_ltx_director_v131.py", "tools/fix_subgraph_device_values_v131.py",
              "tools/fix_gallery_findings_v131.py"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".ps1", ".bat", ".txt", ".yml", ".yaml", ".js", ".mjs", ".html", ".css",
                 ".gitattributes", ".cfg", ".ini", ".toml", ".csv"}
BOUNDARY = r"(?<![A-Za-z0-9_+.\-]){}(?![A-Za-z0-9_+\-])"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def eol_attrs(paths: list[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not paths:
        return out
    text = subprocess.run(["git", "check-attr", "text", "eol", "--stdin"], cwd=ROOT, check=True, capture_output=True,
                          text=True, input="\n".join(paths) + "\n").stdout
    for line in text.splitlines():
        path, attr, value = line.rsplit(": ", 2)
        out.setdefault(path, {})[attr] = value
    return out


def gitattributes_pattern(path: str) -> str:
    return path.replace(" ", "?")


def replace_references(dry: bool) -> list[str]:
    pairs = []
    for old, new in MAP.items():
        pairs.append((old, new))                                   # "Category/Name.json"
        pairs.append((Path(old).name, Path(new).name))             # "Name.json"
        pairs.append((Path(old).stem, Path(new).stem))             # "Name"
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    lookup = dict(pairs)
    combined = re.compile(r"(?<![A-Za-z0-9_+.\-])(" + "|".join(re.escape(o) for o, _ in pairs) + r")(?![A-Za-z0-9_+\-])")
    changed = []
    for rel in git("ls-files").splitlines():
        if rel.startswith(SKIP_PREFIXES) or rel in SKIP_FILES:
            continue
        path = ROOT / rel
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitattributes":
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        new_text = combined.sub(lambda m: lookup[m.group(1)], text)
        # JSON evidence stores Windows paths with escaped backslashes; the forward-slash forms above cover the rest.
        if new_text != text:
            changed.append(rel)
            if not dry:
                path.write_bytes(new_text.encode("utf-8"))
    return changed


def update_migration_map(dry: bool) -> None:
    ps1 = ROOT / "tools" / "update-comfyui-rdna4.ps1"
    text = ps1.read_text(encoding="utf-8")
    start = text.index("$WorkflowMigrationMap = [ordered]@{")
    end = text.index("}", start)
    body = text[start:end]
    lines = []
    for old, new in MAP.items():
        entry = f'    "{old}" = "{new}"'
        if f'"{old}"' not in body:
            lines.append(entry)
    if not lines:
        return
    width = max(len(f'    "{o}"') for o in MAP) + 1
    formatted = [f'{l.split(" = ")[0].ljust(width)}= {l.split(" = ")[1]}' for l in lines]
    comment = "    # v1.3.1: einheitliches Namensschema (Modell_Quant-Eingabe-to-Ausgabe), tools/workflow_renames_v131.json\n"
    new_body = body.rstrip() + "\n" + comment + "\n".join(formatted) + "\n"
    if not dry:
        ps1.write_text(text[:start] + new_body + text[end:], encoding="utf-8", newline="\n")


def main() -> int:
    dry = "--dry-run" in sys.argv
    olds = [f"workflows/{o}" for o in MAP]
    missing = [o for o in olds if not (ROOT / o).exists()]
    if missing:
        print("already renamed or missing:", len(missing))
        olds = [o for o in olds if o not in missing]
    before = eol_attrs(olds)
    for old in olds:
        new = "workflows/" + MAP[old.removeprefix("workflows/")]
        print(f"git mv {old} -> {new}")
        if not dry:
            git("mv", old, new)
    news = ["workflows/" + MAP[o.removeprefix("workflows/")] for o in olds]
    after = eol_attrs(news) if not dry else {}
    extra = []
    for old, new in zip(olds, news):
        b, a = before.get(old, {}), after.get(new, {})
        if b.get("eol") == "lf" and a.get("eol") != "lf":
            extra.append(f"{gitattributes_pattern(new)} text eol=lf")
    changed = replace_references(dry)
    print(f"{len(changed)} files with updated references")
    for rel in changed:
        print("  ", rel)
    if extra and not dry:
        ga = ROOT / ".gitattributes"
        ga.write_text(ga.read_text(encoding="utf-8").rstrip("\n") +
                      "\n# v1.3.1: renamed workflows keep the line endings of their old names.\n" +
                      "\n".join(extra) + "\n", encoding="utf-8", newline="\n")
        print(f".gitattributes: {len(extra)} explicit eol entries")
    update_migration_map(dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
