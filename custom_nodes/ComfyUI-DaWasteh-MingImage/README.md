# DaWasteh MingImage

ComfyUI-Nodes (`comfy_api.latest`) für die v1.2.9-Workflows mit **Ming Image 0.1 Design** und **Design-Layer**
(inclusionAI, MIT). Das Sampling läuft über ComfyUIs native Ming-Unterstützung; das Paket ergänzt nur, was die
offizielle Pipeline zusätzlich tut.

- **DaWMingPromptWriter** (`DaW Ming Prompt Writer (Qwen3.8 GGUF)`): die beiden offiziellen Prompt-Rewriter von
  inclusionAI. `design`/`transparent`: kurze Beschreibung → Figma-artiges JSON (Ebenen, Koordinaten, Farben, exakte
  Texte), das echte Leinwandformat wird mitgegeben; `transparent` setzt den offiziellen RGBA-Präfix davor.
  `layers`: grober Ebenenplan + Bild → genaue Ebenen-Spezifikation; Ausgang `layers` = Ebenenzahl für das Latent.
  Läuft mit dem Qwen3.8-27B-GGUF aus dem Startprofil über `llm_backend.py` des Pakets ComfyUI-DaWasteh-H3-MusicVideo
  (llama.cpp auf der RX 9070 XT, nur während des Schreibens). Ohne GGUF oder mit `enhance` aus wird der Text direkt
  verwendet. Unbrauchbare Antworten (kein gültiges JSON, unvollständige Ebenenliste) werden einmal mit Seed + 1000
  wiederholt, danach gilt der Originaltext.
- **DaWMingReferenceSize** (`DaW Ming Reference Size`): offizielle Arbeitsgröße eines Referenzbilds: Eintrag der
  1024er- (oder 512er-) Bucket-Tabelle mit dem nächstliegenden Seitenverhältnis, bilinear, ohne Beschnitt. Breite/Höhe
  gehen ins leere Latent.
- **DaWMingLayerSplit** (`DaW Ming Layer Split`): dekodierte Layer-Frames (Komposit + N Ebenen, je Frame ein Bild via
  `LatentCutToBatch t/1`) → RGBA-Ebenen (1 = vorne), Komposit des Modells, Ebenen wieder übereinander gelegt (zum
  Vergleich mit dem Original) und ein Vorschaublatt auf Schachbrett.
- **DaWMingAlphaFallback** (`DaW Ming Alpha Fallback`): behält Mings eigenen Alpha-Kanal, wenn mindestens `min_share`
  des Bildes transparent ist; sonst wird die angeschlossene Vordergrundmaske (BiRefNet) zum Alpha. Der Masken-Eingang
  ist lazy: das Freistellmodell lädt nur, wenn es gebraucht wird.
- **DaWMingCheckerboard** (`DaW Ming Alpha Checkerboard`): RGBA auf Schachbrett für Vorschauen.

`prompts/` enthält die unveränderten Rewriter-Texte aus <https://github.com/inclusionAI/Ming-Image> (Commit f39a706,
Zeilenenden LF) mit deren MIT-Lizenz (`prompts/LICENSE-Ming-Image.txt`); die Bucket-Tabellen in `helpers.py` stammen aus
demselben Repository. Abhängigkeiten: nur ComfyUI (PyTorch, NumPy, Pillow) und für den Writer das H3-MusicVideo-Paket
des Bundles. Der Bundle-Updater installiert beides.
Workflows und Messwerte: [docs/MING_IMAGE_V129.md](../../docs/MING_IMAGE_V129.md).
