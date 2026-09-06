#!/usr/bin/env python3
"""v1.1.3 Workflow-Konsolidierung: echte Doppelungen zusammenfuehren, Betriebsarten erhalten.

Zwei Cluster, beide durch kanonischen Graphvergleich (Typ + Widgets + Links, ohne Knoten-IDs
und Positionen) als funktional identisch belegt:

  C1  General Prompt Enhancer 3 -> 1.
      ``LLM_Gemma3_12B_``, ``LLM_Gemma4_e4b_`` und ``LLM_Gemma4_e4b_abliterated_``
      ``General-Prompt-Enhancer.json`` haben identische Knoten-IDs, identische ``links`` und einen
      byteidentischen ``TextGenerate``-Systemprompt. Sie unterscheiden sich ausschliesslich im
      ``CLIPLoader``-Widget sowie in Notiztexten und Layout-Markern. Ergebnis ist ein Workflow
      ``LLM_General-Prompt-Enhancer.json``, in dem das Modell ueber den ``CLIPLoader`` gewaehlt
      wird; die dokumentierte Preset-Tabelle nennt zu jedem Modell den noetigen ``type``, weil
      dieser modellspezifisch ist (Gemma 3 12B: ``ltxv``, Gemma 4 e4b: ``stable_diffusion``).

  C2  MiniMax H3 Ref2VA 2 -> 1.
      ``MiniMax_H3_Spectrum_Ref2VA_All_Reference_Inputs.json`` und
      ``..._Ref2VA_MAXIMUM_All_Reference_Inputs.json`` haben beide 92 Knoten, dieselben
      9 Bild-, 3 Video- und 3 Audioeingaenge und schreiben sogar denselben ``SaveVideo``-Praefix
      ``video/MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_References``. Einziger funktionaler
      Unterschied ist die Geraetezuweisung (``gpu:0/gpu:1/gpu:1`` gegenueber ``gpu:0/gpu:0/gpu:0``).
      Behalten wird die MAXIMUM-Datei (all-gpu:0): Bei CLIP auf ``gpu:1`` laedt der 26-GB-Textencoder
      auf der 16-GB-Karte nur teilweise (gemessen 2026-09-06: 10 374 MB geladen, 15 508 MB
      ausgelagert), was denselben gpu:1-Engpass ausloest, der in v1.1.2 bereits fuer ACE-Step und
      WAN 2.2 auf all-gpu:0 zurueckgenommen wurde.

NICHT zusammengefuehrt (bewusste Entscheidung, dokumentiert):
  Die beiden ``*-Official-Guide-Prompt-Enhancer`` sind zwar strukturgleich, tragen aber
  unterschiedliche Ausgabevertraege im ``StringConcatenate``-Systemprompt (Base/FL2VA:
  Dreifeldformat, 17 574 Zeichen; Ref2VA: Sechs-Sektionen-Format, 41 643 Zeichen). Das ist eine
  echte Betriebsartentrennung, kein blosser Modellwechsel.

Alt -> Neu:
  Prompt Enhancer/LLM_Gemma3_12B_General-Prompt-Enhancer.json             -> LLM_General-Prompt-Enhancer.json (CLIPLoader: Gemma 3 12B / type ltxv)
  Prompt Enhancer/LLM_Gemma4_e4b_General-Prompt-Enhancer.json             -> LLM_General-Prompt-Enhancer.json (CLIPLoader: Gemma 4 e4b / type stable_diffusion)
  Prompt Enhancer/LLM_Gemma4_e4b_abliterated_General-Prompt-Enhancer.json -> LLM_General-Prompt-Enhancer.json (CLIPLoader: Gemma 4 e4b abliterated / type stable_diffusion)
  Reference to Video/MiniMax_H3_Spectrum_Ref2VA_All_Reference_Inputs.json -> MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json (Geraete all-gpu:0)

  python tools/consolidate_workflows_v113.py --check
  python tools/consolidate_workflows_v113.py --apply
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / "workflows"

TARGET_PATH = "Prompt Enhancer/LLM_General-Prompt-Enhancer.json"
TARGET_SOURCE = "Prompt Enhancer/LLM_Gemma4_e4b_General-Prompt-Enhancer.json"


@dataclass(frozen=True)
class ModelPreset:
    label: str
    clip_name: str
    clip_type: str
    note: str


# Reihenfolge = Reihenfolge in der Preset-Tabelle des Workflows.
MODEL_PRESETS = (
    ModelPreset(
        "Gemma 4 e4B FP8 (Standard)",
        "Gemma\\gemma4_e4b_it_fp8_scaled.safetensors",
        "stable_diffusion",
        "Klein und schnell; Standard fuer zuegige Prompt-Iteration auf wenig VRAM.",
    ),
    ModelPreset(
        "Gemma 3 12B FP8 (hoechste Qualitaet)",
        "Gemma\\gemma_3_12B_it_fp8_e4m3fn.safetensors",
        "ltxv",
        "Groesstes Modell, beste Prompt-Qualitaet, mehr VRAM. Zugleich der LTX-2.3-Textencoder.",
    ),
    ModelPreset(
        "Gemma 4 e4B abliterated BF16 (ungefiltert)",
        "Gemma\\gemma4-e4b-it-abliterated_bf16.safetensors",
        "stable_diffusion",
        "Wie der Standard, ohne Inhaltsfilter des Basismodells.",
    ),
)

# Quellen, die in TARGET_PATH aufgehen und danach entfallen.
C1_SOURCES = {
    "Prompt Enhancer/LLM_Gemma3_12B_General-Prompt-Enhancer.json",
    "Prompt Enhancer/LLM_Gemma4_e4b_General-Prompt-Enhancer.json",
    "Prompt Enhancer/LLM_Gemma4_e4b_abliterated_General-Prompt-Enhancer.json",
}

# Dublette, die zugunsten der MAXIMUM-Datei entfaellt.
C2_REMOVED = "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_All_Reference_Inputs.json"
C2_KEPT = "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json"

REMOVED_PATHS = set(C1_SOURCES) | {C2_REMOVED}
ADDED_PATHS = {TARGET_PATH}

# Alt -> Neu fuer Migration und Dokumentation.
MIGRATION_MAP = {
    **{src: TARGET_PATH for src in sorted(C1_SOURCES)},
    C2_REMOVED: C2_KEPT,
}

PRESET_TABLE_TITLE = "MODELLAUSWAHL — General Prompt Enhancer"


def _preset_markdown() -> str:
    lines = [
        f"# {PRESET_TABLE_TITLE}",
        "",
        "Ein Workflow fuer alle drei LLMs. Das Modell wird im **CLIPLoader (Node 1)** gewaehlt.",
        "",
        "> **Wichtig:** `type` gehoert zum Modell und muss mitgesetzt werden.",
        "",
        "| Modell | `clip_name` | `type` |",
        "|---|---|---|",
    ]
    for p in MODEL_PRESETS:
        lines.append(f"| {p.label} | `{p.clip_name.replace(chr(92), '/')}` | `{p.clip_type}` |")
    lines += ["", "**Hinweise**", ""]
    for p in MODEL_PRESETS:
        lines.append(f"- *{p.label}* — {p.note}")
    lines += [
        "",
        "Systemprompt, Sampling-Einstellungen und Ein-/Ausgabeformat sind fuer alle drei Modelle",
        "identisch; ersetzt die frueheren Einzelworkflows "
        "`LLM_Gemma3_12B_`, `LLM_Gemma4_e4b_` und `LLM_Gemma4_e4b_abliterated_General-Prompt-Enhancer`.",
    ]
    return "\n".join(lines)


def build_target(source: dict) -> dict:
    """Erzeugt den zusammengefuehrten Enhancer aus einer der drei Quellen."""
    wf = copy.deepcopy(source)
    default = MODEL_PRESETS[0]
    for node in wf.get("nodes", []):
        if node.get("type") == "CLIPLoader":
            wv = node.get("widgets_values")
            if isinstance(wv, list) and len(wv) >= 2:
                wv[0] = default.clip_name
                wv[1] = default.clip_type
            node["title"] = "LLM-Auswahl — siehe Preset-Tabelle"
        elif node.get("type") == "Note":
            node["widgets_values"] = [
                "=== General Prompt Enhancer ===\n\n"
                "Ein Workflow, drei LLM-Presets. Modell im CLIPLoader (Node 1)\n"
                "waehlen; passenden `type` aus der Preset-Tabelle uebernehmen.\n\n"
                "Wandelt eine kurze Idee in einen ausgearbeiteten Bild-/Video-Prompt."
            ]
    # Preset-Tabelle in die erste MarkdownNote; Layout/Groesse bleiben erhalten.
    for node in wf.get("nodes", []):
        if node.get("type") == "MarkdownNote":
            node["widgets_values"] = [_preset_markdown()]
            node["title"] = PRESET_TABLE_TITLE
            break
    # Layout-Marker an die geaenderten Widgets/Notizen anpassen (gleiche Regel wie upgrade_v112).
    try:
        from tools.rodent_layout import RODENT_KEY, _topology_hash
    except ModuleNotFoundError:  # direct execution from tools/
        from rodent_layout import RODENT_KEY, _topology_hash
    marker = wf.get("extra", {}).get(RODENT_KEY)
    if marker:
        marker["topology_sha256"] = _topology_hash(wf)
    extra = wf.setdefault("extra", {})
    extra["dawasteh_v113_consolidation"] = {
        "version": 1,
        "target": TARGET_PATH,
        "sources": sorted(C1_SOURCES),
        "presets": [
            {"label": p.label, "clip_name": p.clip_name, "clip_type": p.clip_type}
            for p in MODEL_PRESETS
        ],
    }
    return wf


def desired_target(root: Path = WORKFLOWS) -> dict:
    src = root / Path(TARGET_SOURCE)
    tgt = root / Path(TARGET_PATH)
    if src.is_file():
        base = json.loads(src.read_text(encoding="utf-8-sig"))
    elif tgt.is_file():
        base = json.loads(tgt.read_text(encoding="utf-8-sig"))
    else:
        raise FileNotFoundError(f"weder Quelle {TARGET_SOURCE} noch Ziel {TARGET_PATH} vorhanden")
    return build_target(base)


def consolidate(root: Path = WORKFLOWS, *, check: bool = False) -> tuple[int, int]:
    """Schreibt das Ziel und entfernt die abgeloesten Dateien. Gibt (geaendert, entfernt) zurueck."""
    changed = 0
    target = root / Path(TARGET_PATH)
    rendered = json.dumps(desired_target(root), ensure_ascii=False, indent=2) + "\n"
    current = target.read_text(encoding="utf-8-sig") if target.is_file() else None
    if current != rendered:
        changed = 1
        if not check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
    removed = 0
    for rel in sorted(REMOVED_PATHS):
        p = root / Path(rel)
        if p.exists():
            removed += 1
            if not check:
                p.unlink()
    return changed, removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workflows", type=Path, default=WORKFLOWS)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    changed, removed = consolidate(a.workflows, check=a.check)
    print(f"target_changed={changed} removed={removed} check={a.check}")
    if a.check:
        print("Alt -> Neu:")
        for old, new in sorted(MIGRATION_MAP.items()):
            print(f"  {old}\n    -> {new}")
    return 1 if a.check and (changed or removed) else 0


if __name__ == "__main__":
    sys.exit(main())
