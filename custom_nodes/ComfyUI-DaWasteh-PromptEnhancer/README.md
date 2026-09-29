# DaWasteh PromptEnhancer

ComfyUI-Node (`comfy_api.latest`) für den v1.3.0-Workflow `Prompt Enhancer/LLM_Qwen3_8_27B-Image-Prompt-Enhancer`:
aus einem groben Entwurf wird der fertig ausformulierte Prompt für ein Bildmodell.

- **DaWImagePromptEnhancer** (`DaW Image Prompt Enhancer (Qwen3.8 27B GGUF)`):
  - `draft`: der Entwurf, Deutsch oder Englisch, ein paar Wörter bis ein Absatz. Texte, die im Bild stehen sollen, in
    „Anführungszeichen“.
  - `target`: für welche Modellfamilie der Prompt ist. **Fließtext** (Z-Image, FLUX, Qwen Image, Krea), **Text im Bild**
    (Poster, Logo, Schild: exakte Texte in Anführungszeichen, Position und Schriftbild), **Tags** (SDXL, Pony,
    Illustrious) und **Bearbeiten** (Anweisung für Edit-Modelle: was ändert sich, was bleibt).
  - `detail`: kurz / mittel / ausführlich (Fließtext ca. 55 / 115 / 220 Wörter, Tags 15–25 / 25–40 / 40–60, Bearbeiten 1 /
    2–3 / bis zu 5 Sätze). `language`: English (Standard), Deutsch oder wie der Entwurf; Tags sind immer Englisch.
  - `enhance`: aus = Entwurf unverändert, das GGUF wird nicht gestartet. `seed`: anderer Seed = andere Variante.
    `temperature`, `max_tokens`: erweitert.
  - `notes` (optional): eigene Zusatzregeln für den Schreiber („immer 35-mm-Film-Look“, „keine Personen“).
  - `image` (optional): das Modell sieht das Bild, als Referenz für das, was der Entwurf erwähnt, beim Ziel **Bearbeiten**
    als das zu bearbeitende Bild.
  - Ausgänge: `prompt` und `info` (Modell, Ziel, Länge, Dauer).

Das Modell ist das **Qwen3.8-27B-GGUF aus dem Startprofil** (`start-MultiGPU.ps1`: `DAWASTEH_PROMPT_LLM_GGUF`,
`DAWASTEH_LLAMA_SERVER`, `DAWASTEH_LLAMA_HIP_DEVICE`), dasselbe wie beim Musikvideo-Prompt-Writer (MV 2) und bei Ming
Image. Es läuft über `llm_backend.py` des Pakets ComfyUI-DaWasteh-H3-MusicVideo (llama.cpp auf der RX 9070 XT) und wird nur
für die Dauer des Schreibens gestartet; danach sind VRAM und RAM wieder frei. Fehlt das GGUF oder der llama-server im
Startprofil, bricht der Knoten mit einer Meldung ab, die sagt, was fehlt (mit `enhance` aus läuft er ohne).

Unbrauchbare Antworten (leer, mitten im Satz abgebrochen, zu kurz für die gewählte Länge, Ablehnung des Modells) werden
einmal mit Seed + 1000 wiederholt; danach geht der Entwurf unverändert weiter und `info` sagt das. Die Antwort wird von
Beschriftungen („Prompt:“), Codeblöcken, umschließenden Anführungszeichen und Zeilenumbrüchen befreit.

Abhängigkeiten: nur ComfyUI und das H3-MusicVideo-Paket des Bundles; der Bundle-Updater installiert beides.
Workflow und Messwerte: [docs/PROMPT_ENHANCER_V130.md](../../docs/PROMPT_ENHANCER_V130.md).
