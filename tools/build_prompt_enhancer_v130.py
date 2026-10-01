#!/usr/bin/env python3
"""Rebuild the v1.3.0 image prompt enhancer workflow (flat RODENT graph); no runtime/model writes.

Draft -> finished image prompt with the local Qwen3.8 27B GGUF (llama.cpp on the RX 9070 XT, the model the MV 2
music-video prompt writer and the Ming Image writers use). One node does the work (DaWImagePromptEnhancer, pack
ComfyUI-DaWasteh-PromptEnhancer); the workflow adds the draft input, an optional image and the two text views.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

try:
    from tools.build_workflows_v118 import Graph
    from tools import migrate_workflows_v092 as migration
    from tools.generate_dual_gpu_workflows import install_run_timer
    from tools.refine_workflows import refine_workflow
    from tools.rodent_layout import apply_rodent_layout
    from tools.workflow_names_v131 import original_name
except ModuleNotFoundError:
    from build_workflows_v118 import Graph
    import migrate_workflows_v092 as migration
    from generate_dual_gpu_workflows import install_run_timer
    from refine_workflows import refine_workflow
    from rodent_layout import apply_rodent_layout
    from workflow_names_v131 import original_name

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools/workflow_templates/v130"
MARKER = "dawasteh_prompt_enhancer_v130"
RELEASE = "v1.3.0"
PATH = "Prompt Enhancer/LLM_Qwen3_8_27B_IQ4_XS-Draft-to-Image-Prompt.json"
# Defaults the tests pin (docs/PROMPT_ENHANCER_V130.md): running text, medium length, English, a fresh seed per queue.
SETTINGS = {
    "target": "Fließtext (Z-Image, FLUX, Qwen Image, Krea)",
    "detail": "mittel",
    "language": "English",
    "enhance": True,
    "seed": 0,
    "seed_control": "randomize",
    "temperature": 0.7,
    "max_tokens": 1024,
}
DRAFT = "Ein alter Leuchtturm bei Sturm, Möwen, dramatisches Licht"
IMAGE = "example.png"


def build(schemas: dict) -> dict:
    g = Graph(schemas)
    draft = g.prompt("1 · ENTWURF · grob, Deutsch oder Englisch (Texte im Bild in \"Anführungszeichen\")", DRAFT)
    load = g.add("PixaromaLoadImage", "2 · BILD (optional · Strg+M zum Aktivieren) · Referenz oder zu bearbeitendes Bild", image=IMAGE)
    load["mode"] = 2  # muted: an optional image must not block prompt validation; the enhancer input is optional
    load["properties"]["loadImagePixState"] = json.dumps({"version": 1, "mode": "off", "snap": 0})
    load["size"] = [480, 620]
    writer = g.add("DaWImagePromptEnhancer", "PROMPT-ENHANCER · Qwen3.8 27B · Inference über llama.cpp auf der RX 9070 XT · Ziel, Länge, Sprache",
                   draft="", target=SETTINGS["target"], detail=SETTINGS["detail"], language=SETTINGS["language"],
                   enhance=SETTINGS["enhance"], seed=SETTINGS["seed"], temperature=SETTINGS["temperature"],
                   max_tokens=SETTINGS["max_tokens"], notes="")
    # the seed widget is followed by its control_after_generate value; the builder default is "fixed"
    seed_control = writer["widgets_values"].index(SETTINGS["seed"]) + 1
    writer["widgets_values"][seed_control] = SETTINGS["seed_control"]
    writer["size"] = [520, 720]
    g.connect(draft, 0, writer, "draft")
    g.connect(load, 0, writer, "image")
    result = g.add("PixaromaShowText", "3 · FERTIGER PROMPT · kopieren oder per Verbindung weiterreichen")
    result["size"] = [520, 520]
    g.connect(writer, 0, result, "source")
    info = g.add("PixaromaShowText", "INFO · Modell, Ziel, Länge, Dauer (oder warum der Entwurf unverändert blieb)")
    info["size"] = [520, 200]
    g.connect(writer, 1, info, "source")
    g.note(f"START HIER · Bild-Prompt-Enhancer · Qwen3.8 27B · {RELEASE}", START_NOTE)
    g.note("TECHNIK · Modell, Startprofil, Speicher, Grenzen", TECH_NOTE)
    return finish(g)


def finish(g: Graph) -> dict:
    install_run_timer(g.w)
    g.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v130:" + original_name(PATH)))
    g.w["revision"] = 0
    g.w["extra"][MARKER] = {
        "version": 1,
        "kind": "image_prompt_enhancer",
        "source_manifest": "tools/workflow_templates/v130/node-schemas.json",
        "validation_report": "performance/rdna4/prompt-enhancer-v130-validation.json",
    }
    refine_workflow(g.w, g.schemas)
    before = copy.deepcopy(migration.OBJECT_INFO)
    try:
        migration.OBJECT_INFO.update(g.schemas)
        result = migration.migrate_workflow(g.w, PATH)
    finally:
        migration.OBJECT_INFO.clear()
        migration.OBJECT_INFO.update(before)
    for node in result["nodes"]:
        if node["type"] == "MarkdownNote":
            text = node.get("widgets_values", [""])[0]
            lines = sum(max(1, (len(line) + 79) // 80) for line in text.splitlines())
            node["size"] = [680, max(620, 160 + lines * 22)]
    apply_rodent_layout(result, PATH)
    return result


START_NOTE = """# Bild-Prompt-Enhancer · Entwurf → fertiger Prompt · Qwen3.8 27B

Aus ein paar Wörtern wird der ausformulierte Prompt für ein Bildmodell. Geschrieben vom **Qwen3.8 27B**, demselben Modell
wie beim Musikvideo-Prompt-Writer (MV 2), lokal über llama.cpp auf der RX 9070 XT.

1. **ENTWURF** (Knoten 1): grob beschreiben, Deutsch oder Englisch. Texte, die im Bild stehen sollen, in „Anführungszeichen“.
2. **Ziel** am Enhancer wählen, für welches Modell der Prompt ist:
   - **Fließtext**: Z-Image, FLUX, Qwen Image, Krea (ein Absatz, Motiv → Umgebung → Licht → Kamera → Stil)
   - **Text im Bild**: Poster, Logo, Schild (exakte Texte in Anführungszeichen, Position und Schriftbild)
   - **Tags**: SDXL, Pony, Illustrious (kleingeschriebene englische Tags, `1girl`, `1boy` …)
   - **Bearbeiten**: Anweisung für Edit-Modelle (was ändert sich, was bleibt); dafür **BILD** aktivieren
3. **Länge** (kurz / mittel / ausführlich) und **Sprache** (English ist für die meisten Bildmodelle am besten; Tags immer
   Englisch). **notes** nimmt eigene Zusatzregeln („immer 35-mm-Film-Look“, „keine Personen“).
4. **Queue**. Der fertige Prompt steht unter **FERTIGER PROMPT**; **INFO** zeigt Modell, Länge und Dauer.

**BILD (optional)**: Knoten 2 mit **Strg+M** aktivieren und ein Bild wählen. Das Modell sieht es: als Referenz für das,
was der Entwurf erwähnt („dieselbe Szene im Winter“), beim Ziel **Bearbeiten** als das zu bearbeitende Bild.
**Seed** steht auf *randomize*: jeder Lauf ist eine neue Variante; für dieselbe Antwort auf *fixed* stellen.
**enhance aus** reicht den Entwurf unverändert durch (das Modell wird dann nicht gestartet).
Den fertigen Prompt in einen Bild-Workflow zu übernehmen geht per Kopieren oder mit einer Verbindung vom Enhancer-Ausgang
`prompt` zum Prompt-Eingang des Bildmodells.
"""

TECH_NOTE = """# Technik

**Modell:** das Qwen3.8-27B-GGUF aus dem Startprofil (`start-MultiGPU.ps1`: `$PromptLlmGguf`, `$LlamaServerExe`, HIP-Gerät 1 =
RX 9070 XT), Standard `Qwen3.8-27B-IQ4_XS-3.84bpw.gguf` in `ComfyUI/models/LLM/Qwen3.8/`. Der Enhancer startet den
llama-server nur für die Dauer des Schreibens (Start ca. 15–30 s, danach Sekunden je Prompt) und beendet ihn danach:
VRAM und RAM sind wieder frei. Fehlen GGUF oder llama-server im Startprofil, bricht der Knoten mit einer Meldung ab, die
sagt, was fehlt.

**Antworten prüfen:** Leere, mitten im Satz abgebrochene, für die gewählte Länge zu kurze Antworten und Ablehnungen des
Modells werden einmal mit Seed + 1000 wiederholt. Danach geht der **Entwurf unverändert** weiter, und INFO nennt den Grund.

**Speicher und Dauer:** Der Server belegt ca. 11,5–12,7 GiB VRAM der RX 9070 XT und 1–3 GiB im Host-RAM (der Desktop läuft
auf derselben Karte); der Rechner-Commit steigt dabei um ca. 18 GiB. Ein Lauf dauert 20–35 s, davon ca. 16 s Serverstart.
Andere GPU-lastige Programme auf dieser Karte vorher schließen.

Bedienung, Beispiele und Messwerte: `docs/PROMPT_ENHANCER_V130.md`.
"""


def build_all() -> dict[str, dict]:
    schemas = json.loads((SOURCES / "node-schemas.json").read_text(encoding="utf-8"))
    return {PATH: build(schemas)}


def main() -> None:
    for path, workflow in build_all().items():
        target = ROOT / "workflows" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
