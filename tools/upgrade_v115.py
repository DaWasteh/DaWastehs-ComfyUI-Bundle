#!/usr/bin/env python3
"""v1.1.5 deterministic workflow migration (optionale Zweige, Sekundenvorschau).

Applies, idempotently, on top of the v1.1.4 collection:

  B1  Optionale Referenzzweige abschaltbar und ausgeliefert lauffaehig
      (``OPTIONAL_BRANCH_WORKFLOWS``, Auftrag §6).

      Gemessen 2026-09-06 gegen die Prompt-Validierung von ComfyUI 0.34.0:

        A  verbundener Loader mit fehlender Datei  -> HTTP 400,
           "Custom validation failed for node | image - Invalid image file"
        B  Loader stummgeschaltet (nicht im Prompt) -> HTTP 200
        C  Loader im Prompt, aber unverbunden       -> HTTP 200

      Die drei H3-Referenzworkflows liefern zusammen 15 Loader aus, die auf
      dokumentierte Platzhalter (``REFERENCE_*``) zeigen -- Dateien, die es auf keiner
      Installation gibt. Alle waren aktiv und verbunden, also Fall A: **die Workflows
      scheiterten ausgeliefert an der Validierung, bevor ueberhaupt etwas gerechnet wurde.**

      Diese Loader und die Knoten, die ausschliesslich sie weiterverarbeiten, werden auf
      ``mode = 2`` (Mute) gesetzt. Mute ist hier korrekt und Bypass waere falsch:

        Mute   Der Knoten faellt aus dem Prompt. Ein optionaler Eingang bleibt dann
               schlicht unbelegt -- genau das beabsichtigte Verhalten.
        Bypass Der Knoten wird durchgereicht. Ein Loader hat keinen passenden Eingang
               zum Durchreichen, das Ergebnis waere ein toter Link.

      Vor dem Stummschalten prueft ``_branch_is_optional`` fuer jeden Zweig, dass
      **jede** Verbindung, die ihn verlaesst, in einem als optional deklarierten Eingang
      (litegraph ``shape == 7``) endet. Trifft das nicht zu, wird der Zweig nicht
      angefasst und die Migration meldet das.

      Zusaetzlich traegt jeder Knoten des Zweigs eine Beschriftung, sodass der Schalter
      im Canvas sichtbar ist: Knoten markieren, Strg+M. Eigene Gruppen sind dafuer nicht
      moeglich -- das RODENT-Layout erzeugt die Gruppen deterministisch (feste Stage-Titel,
      eine Gruppe je Knoten, ueberlappungsfrei).

  B2  Sekundenvorschau (Auftrag §5).

      Der Sekundenvertrag existiert seit v0.9.4 fuer alle 53 Generierungs-Workflows und
      seine Rasterwerte wurden fuer v1.1.5 gegen die Node-Schemata verifiziert
      (``EmptyLTXVLatentVideo`` step 8, ``Wan22FunControlToVideo`` /
      ``Kandinsky5ImageToVideo`` / ``Wan22ImageToVideoLatent`` / ``WanImageToVideo`` /
      ``WanSCAILToVideo`` step 4). Was fehlte, war die vom Auftrag geforderte Angabe
      "gewuenschte Dauer, berechnete Frames und tatsaechlich resultierende Dauer".

      Der Marker ``extra[DURATION_KEY]`` traegt jetzt eine ``preview``-Tabelle mit
      Stuetzstellen -- Minimum, Standardwert und ein nicht ganzzahliger Wert -- jeweils
      mit gewuenschter Dauer, daraus berechneter Frame-Anzahl und der Dauer, die dabei
      tatsaechlich herauskommt. Die Werte stammen aus ``model_frame_count`` und damit
      aus derselben Formel, die auch im Graphen steht.

  python tools/upgrade_v115.py --check     # verify workflows/ == apply(HEAD files)
  python tools/upgrade_v115.py --apply     # rewrite workflows/ in place
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / "workflows"
MARKER_KEY = "dawasteh_rdna4_v115"
MARKER_VERSION = 1

MODE_ACTIVE = 0
MODE_MUTE = 2

# Mit der Sammlung ausgelieferte Platzhalternamen. Bewusst eng gefasst: Nutzer-Medien
# (eigene Bilder, eigene Tonspuren) heissen anders und werden nie angefasst.
PLACEHOLDER_RE = re.compile(r"^REFERENCE_", re.IGNORECASE)
MEDIA_RE = re.compile(r"\.(png|jpg|jpeg|webp|bmp|mp4|mov|mkv|webm|wav|mp3|flac|ogg|m4a)$", re.IGNORECASE)
LOADER_TYPES = {"LoadImage", "LoadAudio", "LoadVideo", "LoadImageMask", "VHS_LoadVideo"}

OPTIONAL_BRANCH_WORKFLOWS = {
    "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json",
    "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_Picture_and_Video_to_Video_LOCAL.json",
    "Reference to Video/MiniMax_H3_Spectrum_RefImage_RefVideo_to_Video_Audio_AutoLength.json",
}

BRANCH_GROUP_PREFIX = "OPTIONAL · "   # Praefix der Knotentitel abgeschalteter Zweige
OPTIONAL_SHAPE = 7          # litegraph: optionaler Eingang


def _filename(node: dict) -> str | None:
    wv = node.get("widgets_values")
    values = wv if isinstance(wv, list) else list(wv.values()) if isinstance(wv, dict) else []
    for v in values:
        if isinstance(v, str) and MEDIA_RE.search(v):
            return v
    return None


def placeholder_loaders(wf: dict) -> list[dict]:
    out = []
    for node in wf.get("nodes", []):
        if node.get("type") not in LOADER_TYPES:
            continue
        fn = _filename(node)
        if fn and PLACEHOLDER_RE.match(fn):
            out.append(node)
    return out


def _consumers(wf: dict) -> dict[int, list[tuple[int, int]]]:
    """node id -> [(consumer id, consumer input slot)] ueber die links-Liste."""
    out: dict[int, list[tuple[int, int]]] = {}
    for link in wf.get("links", []):
        if not isinstance(link, list) or len(link) < 5:
            continue
        _lid, src, _sslot, dst, dslot = link[0], link[1], link[2], link[3], link[4]
        out.setdefault(int(src), []).append((int(dst), int(dslot)))
    return out


def _producers(wf: dict) -> dict[int, set[int]]:
    """node id -> {ids der Knoten, die Eingaenge liefern}."""
    out: dict[int, set[int]] = {}
    for link in wf.get("links", []):
        if not isinstance(link, list) or len(link) < 5:
            continue
        out.setdefault(int(link[3]), set()).add(int(link[1]))
    return out


def branch_nodes(wf: dict, seeds: list[dict]) -> set[int]:
    """Zweig = Platzhalter-Loader plus alle Knoten, die *ausschliesslich* von ihnen leben."""
    nodes = {int(n["id"]): n for n in wf.get("nodes", [])}
    consumers, producers = _consumers(wf), _producers(wf)
    branch = {int(n["id"]) for n in seeds}
    changed = True
    while changed:
        changed = False
        for nid, node in nodes.items():
            if nid in branch or node.get("type") in LOADER_TYPES:
                continue
            src = producers.get(nid)
            # nur Knoten mit Eingaengen, die vollstaendig aus dem Zweig gespeist werden
            if src and src <= branch and consumers.get(nid):
                branch.add(nid)
                changed = True
    return branch


def _branch_is_optional(wf: dict, branch: set[int]) -> tuple[bool, list[str]]:
    """Jede Verbindung, die den Zweig verlaesst, muss in einem optionalen Eingang enden."""
    nodes = {int(n["id"]): n for n in wf.get("nodes", [])}
    problems: list[str] = []
    for link in wf.get("links", []):
        if not isinstance(link, list) or len(link) < 5:
            continue
        src, dst, dslot = int(link[1]), int(link[3]), int(link[4])
        if src not in branch or dst in branch:
            continue
        target = nodes.get(dst)
        inputs = (target or {}).get("inputs") or []
        if dslot >= len(inputs) or inputs[dslot].get("shape") != OPTIONAL_SHAPE:
            name = inputs[dslot].get("name") if dslot < len(inputs) else f"slot {dslot}"
            problems.append(f"{src} -> {dst}.{name} ist kein optionaler Eingang")
    return (not problems), problems


def _branch_label(wf: dict, branch: set[int]) -> str:
    types = [n.get("type") for n in wf.get("nodes", []) if int(n["id"]) in branch]
    if any(t == "LoadVideo" or t == "VHS_LoadVideo" for t in types):
        return "Referenzvideos"
    if any(t == "LoadAudio" for t in types):
        return "Referenzaudio"
    return "Referenzbilder"


def apply_optional_branches(wf: dict) -> dict:
    seeds = placeholder_loaders(wf)
    if not seeds:
        return wf
    # je Loader ein eigener Zweig, damit sie einzeln schaltbar bleiben
    branches: list[set[int]] = []
    required: list[str] = []
    for seed in seeds:
        b = branch_nodes(wf, [seed])
        ok, problems = _branch_is_optional(wf, b)
        if ok:
            branches.append(b)
        else:
            required.extend(problems)
    if not branches:
        # Der Platzhalter speist Pflichteingaenge -- Stummschalten waere ein Graphbruch.
        # Solche Workflows brauchen die Datei wirklich; das wird dokumentiert statt geaendert.
        wf.setdefault("extra", {})["dawasteh_optional_branches"] = {
            "version": 1,
            "mechanism": "none",
            "reason": "Der Platzhalter-Loader speist Pflichteingaenge; es gibt keinen gueltigen "
                      "Ersatzpfad. Die Datei muss bereitgestellt oder im Loader ausgewaehlt werden.",
            "required_links": sorted(required),
        }
        return wf
    muted = set().union(*branches)
    for node in wf.get("nodes", []):
        if int(node["id"]) in muted and node.get("mode", MODE_ACTIVE) != MODE_MUTE:
            node["mode"] = MODE_MUTE

    # Beschriftung statt eigener Gruppen: Das RODENT-Layout erzeugt die Gruppen
    # deterministisch (ein Knoten je Gruppe, ueberlappungsfrei, feste Stage-Titel).
    # Knotentitel sind im Canvas genauso sichtbar und kollidieren nicht damit.
    by_label: dict[str, set[int]] = {}
    for b in branches:
        by_label.setdefault(_branch_label(wf, b), set()).update(b)
    nodes = {int(n["id"]): n for n in wf.get("nodes", [])}
    for label, ids in by_label.items():
        for nid in sorted(ids):
            node = nodes[nid]
            base = str(node.get("title") or node.get("type"))
            if not base.startswith(BRANCH_GROUP_PREFIX):
                node["title"] = f"{BRANCH_GROUP_PREFIX}{label} · AUS · Strg+M schaltet ein · {base}"

    wf.setdefault("extra", {})["dawasteh_optional_branches"] = {
        "version": 1,
        "mechanism": "mute",
        "reason": "Mute entfernt den Knoten aus dem Prompt; ein optionaler Eingang bleibt unbelegt. "
                  "Bypass waere falsch, weil ein Loader keinen Eingang zum Durchreichen hat.",
        "switch": "Knoten des Zweigs markieren und Strg+M druecken.",
        "muted_nodes": sorted(muted),
        "branches": {label: sorted(ids) for label, ids in sorted(by_label.items())},
    }
    return wf


def duration_preview(spec, model_frame_count) -> list[dict]:
    """Stuetzstellen: Minimum, Standard und ein nicht ganzzahliger Wert."""
    minimum_seconds = (spec.minimum - 1) / spec.fps
    points = [minimum_seconds, spec.default_seconds, round(spec.default_seconds + 0.37, 2)]
    out = []
    for seconds in points:
        frames = model_frame_count(seconds, spec)
        out.append({
            "requested_seconds": round(float(seconds), 3),
            "frames": int(frames),
            "actual_seconds": round((frames - 1) / spec.fps, 3),
        })
    return out


def apply_duration_preview(wf: dict, rel: str) -> dict:
    try:
        from tools.integrate_duration_seconds import DURATION_KEY, SPECS, model_frame_count
    except ModuleNotFoundError:  # direct execution from tools/
        from integrate_duration_seconds import DURATION_KEY, SPECS, model_frame_count
    spec = SPECS.get(rel)
    if spec is None:
        return wf
    marker = wf.get("extra", {}).get(DURATION_KEY)
    if not isinstance(marker, dict):
        return wf
    marker["minimum_frames"] = spec.minimum
    marker["preview"] = duration_preview(spec, model_frame_count)
    marker["rounding"] = (
        "Nicht darstellbare Dauern rasten auf das naechstgelegene gueltige Raster ein; "
        "die tatsaechliche Dauer steht in preview.actual_seconds."
    )
    return wf


def apply(wf: dict, rel: str) -> dict:
    """Return the v1.1.5 form of *wf* (already-migrated input is returned unchanged)."""
    wf = copy.deepcopy(wf)
    rel = rel.replace("\\", "/")
    if rel not in targets():
        return wf
    if rel in OPTIONAL_BRANCH_WORKFLOWS:
        apply_optional_branches(wf)
    apply_duration_preview(wf, rel)
    wf.setdefault("extra", {})[MARKER_KEY] = {"version": MARKER_VERSION}
    try:
        from tools.rodent_layout import RODENT_KEY, _topology_hash
    except ModuleNotFoundError:  # direct execution from tools/
        from rodent_layout import RODENT_KEY, _topology_hash
    marker = wf.get("extra", {}).get(RODENT_KEY)
    if marker and marker.get("topology_sha256") != _topology_hash(wf):
        marker["topology_sha256"] = _topology_hash(wf)
    return wf


def targets() -> set[str]:
    try:
        from tools.integrate_duration_seconds import SPECS
    except ModuleNotFoundError:  # direct execution from tools/
        from integrate_duration_seconds import SPECS
    return set(OPTIONAL_BRANCH_WORKFLOWS) | set(SPECS)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    diffs = 0
    for rel in sorted(targets()):
        p = WORKFLOWS / rel
        wf = json.loads(p.read_text(encoding="utf-8"))
        new = apply(wf, rel)
        if new != wf:
            diffs += 1
            if a.apply:
                p.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"rewrote {rel}")
            else:
                print(f"differs {rel}")
    print(f"{'applied' if a.apply else 'check'}: {diffs} file(s) {'rewritten' if a.apply else 'differ'}")
    return 0 if a.apply or diffs == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
