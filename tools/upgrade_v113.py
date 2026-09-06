#!/usr/bin/env python3
"""v1.1.3 deterministic workflow migration (MiniMax-H3-Audiofix).

Applies, idempotently, on top of the v1.1.2 collection:

  A1  MiniMax-H3-Audiopfad (6 Workflows, ``H3_AUDIO_PATH``): die drei Abweichungen von der
      Hersteller-Referenz werden zurueckgenommen. Belegt aus den in den Ausgabedateien
      eingebetteten Graphen (``prompt``-Metadatum in den MP4s) und einem kontrollierten
      Paar, das der Nutzer selbst erzeugt hatte:

        MiniMax_H3_00003_.mp4  (Nutzer: guter Ton)  seed 757358688076805, 20 Schritte, kein Turbo
        MiniMax_H3_00002_.mp4                       seed 757358688076805,  8 Schritte, Turbo-LoRA

      Beide Graphen sind ansonsten byteidentisch (gleicher Prompt, gleiche Dauer, gleiche
      Modelle/VAEs, ``res_multistep`` + ``simple``, kein ``MiniMaxH3SigmaShift``, kein Spectrum,
      keine MultiGPU-Knoten); der einzige Unterschied ist ein ``PrimitiveBoolean``.

      Gemessener HF-Rauschabstand (Rauschboden 4-8 kHz relativ zum Tiefton derselben leisen
      Frames, leisestes Energieviertel, 2048-Punkt-Hann; pegelnormiert und damit robust gegen
      Inhaltsunterschiede):

        00003_ (20 Schritte, kein Turbo)                    -29.1 dB
        00002_ ( 8 Schritte, Turbo-LoRA)                    -28.5 dB
        FL2VA-Workflow (ausgeliefert)                       -18.0 dB
        Ref2VA-Workflow (ausgeliefert)                       +0.7 dB

      Turbo-LoRA und 8 Schritte sind damit als Ursache ausgeschlossen (0.6 dB Unterschied);
      sie bleiben unveraendert. Zurueckgenommen werden ausschliesslich die drei Einstellungen,
      in denen unsere Workflows von der Hersteller-Referenz abweichen:

        A1a ``MiniMaxH3SigmaShift.shift_audio`` 4.0 -> 3.0.
            3.0 ist der Default des Kernknotens (``comfy_extras/nodes_minimax_h3.py``:384),
            der Modellkonfiguration (``comfy/supported_models.py``:966-969 ``audio_shift: 3.0``)
            und des DiT-Konstruktors (``comfy/ldm/minimax/model.py``:479). Der Wert bestimmt
            ueber ``audio_scale = shift_video / shift_audio`` die gesamte Rauschbahn des
            Audiostroms (``comfy/model_sampling.py``:343-347, ``comfy/model_base.py``:2149-2165).
            Beide gut klingenden Laeufe verwenden 3.0, beide beanstandeten 4.0.

        A1b ``KSamplerSelect`` ``euler`` -> ``res_multistep`` und ``BasicScheduler`` ``beta`` ->
            ``simple``. Das ist die Kombination der offiziellen ComfyUI-H3-Vorlage und beider
            guten Laeufe. Gleiche Anzahl Modellauswertungen, aber Verfahren zweiter statt
            erster Ordnung (adversarial geprueft und bestaetigt).

        A1c ``SpectrumApplyMiniMaxH3`` wird auf Bypass (mode 4) gesetzt. Spectrum prognostiziert
            den gepackten Video+Audio-Zustand, nicht nur Videomerkmale; auf einer Prognosestufe
            entsteht die Audio-Geschwindigkeit ohne Transformer-Auswertung. ``audio_blend_weight
            = 0.0`` haelt Audio NICHT exakt - die Audiozeilen werden weiterhin ersetzt, dann per
            zweipunkt-linearer Interpolation (beides adversarial geprueft und bestaetigt).
            Der Knoten bleibt im Graphen und ist ein dokumentierter Geschwindigkeitsmodus:
            Bypass aufheben stellt die Beschleunigung wieder her.

      Nicht geaendert: Turbo-LoRA, Schrittzahl, Modelle, Aufloesung, Geraetezuweisung.

Every migrated file carries ``extra[MARKER_KEY] = {"version": MARKER_VERSION}`` so that
``tools/validate_workflows.py --against-head`` can rebuild it from the previous release
(v1.1.2 form -> v1.1.3 form).

  python tools/upgrade_v113.py --check     # verify workflows/ == apply(HEAD files)
  python tools/upgrade_v113.py --apply     # rewrite workflows/ in place
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / "workflows"
MARKER_KEY = "dawasteh_rdna4_v113"
MARKER_VERSION = 1

# Die sechs H3-Workflows mit Spectrum-Beschleunigung und gemeinsamem Audiopfad.
# ``..._Ref2VA_All_Reference_Inputs.json`` fehlt hier bewusst: die Datei wird in derselben
# Version durch ``tools/consolidate_workflows_v113.py`` als Dublette entfernt (Alt -> Neu:
# ``..._Ref2VA_MAXIMUM_All_Reference_Inputs.json``).
H3_AUDIO_PATH = {
    "Reference to Video/MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json",
    "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json",
    "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_Picture_and_Video_to_Video_LOCAL.json",
    "Reference to Video/MiniMax_H3_Spectrum_RefImage_Audio_to_Video_OriginalAudio_AutoLength.json",
    "Reference to Video/MiniMax_H3_Spectrum_RefImage_RefVideo_to_Video_Audio_AutoLength.json",
}

# Der Music-Video-Director traegt dieselben drei Abweichungen in seinen eigenen Widgets
# (Index 31/32 = shift_video/shift_audio, 33/34 = sampler/scheduler), gesetzt von
# tools/integrate_h3_turbo_lora.py:200-201.
DIRECTOR_WORKFLOW = "Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json"
DIRECTOR_SHIFT_AUDIO_INDEX = 32
DIRECTOR_SAMPLER_INDEX = 33
DIRECTOR_SCHEDULER_INDEX = 34

SHIFT_AUDIO_VENDOR = 3.0        # comfy_extras/nodes_minimax_h3.py:384 (Knoten-Default)
SAMPLER_VENDOR = "res_multistep"
SCHEDULER_VENDOR = "simple"
MODE_BYPASS = 4                 # ComfyUI: 0 = aktiv, 2 = mute, 4 = bypass


def set_sigma_shift_audio(wf: dict, value: float = SHIFT_AUDIO_VENDOR) -> bool:
    """``MiniMaxH3SigmaShift`` widget 1 (shift_audio) auf den Hersteller-Default."""
    changed = False
    for node in wf.get("nodes", []):
        if node.get("type") != "MiniMaxH3SigmaShift":
            continue
        wv = node.get("widgets_values")
        if not isinstance(wv, list) or len(wv) < 2:
            continue
        if wv[1] != value:
            wv[1] = value
            changed = True
    return changed


def set_sampler_scheduler(wf: dict) -> bool:
    """``KSamplerSelect`` -> res_multistep, ``BasicScheduler`` -> simple (Schrittzahl bleibt)."""
    changed = False
    for node in wf.get("nodes", []):
        wv = node.get("widgets_values")
        if not isinstance(wv, list) or not wv:
            continue
        if node.get("type") == "KSamplerSelect":
            if wv[0] != SAMPLER_VENDOR:
                wv[0] = SAMPLER_VENDOR
                changed = True
        elif node.get("type") == "BasicScheduler":
            if wv[0] != SCHEDULER_VENDOR:
                wv[0] = SCHEDULER_VENDOR
                changed = True
    return changed


def bypass_spectrum(wf: dict) -> bool:
    """``SpectrumApplyMiniMaxH3`` auf Bypass; der Knoten bleibt als Geschwindigkeitsmodus erhalten."""
    changed = False
    for node in wf.get("nodes", []):
        if node.get("type") != "SpectrumApplyMiniMaxH3":
            continue
        if node.get("mode", 0) != MODE_BYPASS:
            node["mode"] = MODE_BYPASS
            changed = True
    return changed


def set_director_sampling(wf: dict) -> bool:
    """Dieselben drei Werte in den Widgets des Music-Video-Directors."""
    changed = False
    for node in wf.get("nodes", []):
        if not str(node.get("type", "")).startswith("DaWH3MusicVideoDirector"):
            continue
        wv = node.get("widgets_values")
        if not isinstance(wv, list) or len(wv) <= DIRECTOR_SCHEDULER_INDEX:
            continue
        for idx, value in ((DIRECTOR_SHIFT_AUDIO_INDEX, SHIFT_AUDIO_VENDOR),
                           (DIRECTOR_SAMPLER_INDEX, SAMPLER_VENDOR),
                           (DIRECTOR_SCHEDULER_INDEX, SCHEDULER_VENDOR)):
            if wv[idx] != value:
                wv[idx] = value
                changed = True
    return changed


def apply(wf: dict, rel: str) -> dict:
    """Return the v1.1.3 form of *wf* (already-migrated input is returned unchanged)."""
    wf = copy.deepcopy(wf)
    rel = rel.replace("\\", "/")
    if rel not in H3_AUDIO_PATH and rel != DIRECTOR_WORKFLOW:
        return wf
    # Werte, Titel und die generierten Hinweistexte stammen aus einer Quelle:
    # tools/integrate_h3_turbo_lora.py schreibt seit v1.1.3 die Hersteller-Werte und ist
    # idempotent. So koennen Widget und Beschriftung nicht auseinanderlaufen.
    try:
        from tools.integrate_h3_turbo_lora import integrate_director, integrate_visible
    except ModuleNotFoundError:  # direct execution from tools/
        from integrate_h3_turbo_lora import integrate_director, integrate_visible
    if rel == DIRECTOR_WORKFLOW:
        integrate_director(wf)
    else:
        integrate_visible(wf, rel)
        bypass_spectrum(wf)
    wf.setdefault("extra", {})[MARKER_KEY] = {"version": MARKER_VERSION}
    # keep the RODENT layout marker consistent with the changed widgets (same rule as upgrade_v112)
    try:
        from tools.rodent_layout import RODENT_KEY, _topology_hash
    except ModuleNotFoundError:  # direct execution from tools/
        from rodent_layout import RODENT_KEY, _topology_hash
    marker = wf.get("extra", {}).get(RODENT_KEY)
    if marker and marker.get("topology_sha256") != _topology_hash(wf):
        marker["topology_sha256"] = _topology_hash(wf)
    return wf


def targets() -> set[str]:
    return set(H3_AUDIO_PATH) | {DIRECTOR_WORKFLOW}


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
