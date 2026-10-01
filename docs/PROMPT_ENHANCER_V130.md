# Bild-Prompt-Enhancer · Entwurf → fertiger Prompt mit Qwen3.8 27B · v1.3.0

Neuer Workflow `Prompt Enhancer/LLM_Qwen3_8_27B_IQ4_XS-Draft-to-Image-Prompt`: aus einem groben Entwurf (ein paar Wörter,
Deutsch oder Englisch) wird der ausformulierte Prompt für ein Bildmodell. Geschrieben wird er vom **Qwen3.8 27B**, dem
Modell, das auch der Musikvideo-Prompt-Writer (MV 2) und die Ming-Image-Writer benutzen: dasselbe GGUF, derselbe
`llama-server`, dieselbe Grafikkarte (RX 9070 XT), aus demselben Startprofil.

Die vorhandenen Enhancer im Ordner (Gemma 4 e4B, Qwen3.5 4B, `LLM_Gemma4_E4B_FP8-Idea-to-Prompt`) laufen im ComfyUI-Prozess mit
kleinen Modellen und bleiben unverändert. Der neue Workflow ist die große, sorgfältigere Variante; sein Preis ist der
Serverstart (siehe Dauer).

## Bedienung

1. **ENTWURF** (Knoten 1): grob beschreiben. Texte, die im Bild stehen sollen, in „Anführungszeichen“.
2. Am Knoten **PROMPT-ENHANCER** das **Ziel** wählen, **Länge** und **Sprache** einstellen.
3. **Queue**. Der Prompt erscheint unter **FERTIGER PROMPT** (zum Kopieren), **INFO** nennt Modell, Länge und Dauer.

| Einstellung | Werte | Wirkung |
|---|---|---|
| `target` | Fließtext · Text im Bild · Tags · Bearbeiten | für welche Modellfamilie der Prompt ist (siehe unten) |
| `detail` | kurz · mittel · ausführlich | Fließtext ca. 55 / 115 / 220 Wörter, Text im Bild 80 / 140 / 240, Tags 15–25 / 25–40 / 40–60, Bearbeiten 1–2 / 2–3 / bis zu 5 Sätze |
| `language` | English · Deutsch · wie der Entwurf | Sprache des fertigen Prompts; English passt zu den meisten Bildmodellen, Tags sind immer Englisch, Texte in Anführungszeichen werden nie übersetzt |
| `enhance` | an / aus | aus = Entwurf unverändert, das GGUF wird nicht gestartet |
| `seed` | Zahl (Standard *randomize*) | anderer Seed = andere Variante desselben Entwurfs |
| `temperature`, `max_tokens` | 0,7 / 1024 | erweitert: niedriger = näher am Entwurf |
| `notes` | Text (optional) | eigene Zusatzregeln, z. B. „immer 35-mm-Film-Look“, „keine Personen im Bild“ |
| BILD (Knoten 2, stummgeschaltet) | Strg+M aktiviert | das Modell sieht das Bild (siehe unten) |

## Die vier Ziele

| Ziel | Für | Format des Prompts |
|---|---|---|
| **Fließtext** (Standard) | Z-Image, FLUX, Qwen Image, Krea | ein Absatz aus ganzen Sätzen: Motiv mit Haltung und Ausdruck → Kleidung und Details → Umgebung → Licht und Farbe → Bildausschnitt, Kamera, Objektiv → Stil und Stimmung. Ohne Stilangabe im Entwurf wird eine realistische Fotografie beschrieben, sonst der genannte Stil mit seinem Vokabular. Keine Verneinungen, keine Qualitätsfloskeln („masterpiece“, „8k“). |
| **Text im Bild** | Poster, Logo, Schild, Cover, Sticker (Qwen Image, Ideogram) | ein Absatz: was das Stück ist und wie es aufgebaut ist → Hintergrund und Farben → jeder Text in Lesereihenfolge mit **wörtlichem Inhalt in Anführungszeichen**, Position und Schriftbild → Grafiken → Material oder Darstellung. Erfindet keine zusätzlichen Texte. |
| **Tags** | SDXL, Pony, Illustrious | kleingeschriebene englische Tags in einer Zeile: Qualitäts-Tags → Motiv und Anzahl (`1girl`, `1boy`, `solo`) → Aussehen, Kleidung, Pose → Ort → Licht → Kamera → Stil. Keine Sätze, keine Gewichte, keine doppelten Tags. |
| **Bearbeiten** | Edit-Modelle (Qwen Image Edit, FLUX Klein Edit, Ming Edit) | imperative Sätze: was sich ändert (das Element so benannt, wie es im Bild aussieht), wie das Neue aussieht, dann was unverändert bleibt. Bei Textänderungen alter und neuer Text in Anführungszeichen. |

## Optionales Bild

Knoten 2 (**BILD**) ist stummgeschaltet, damit der Workflow ohne Bild gültig ist (ein aktiver Loader mit fehlender Datei
würde die Prompt-Validierung blockieren). **Strg+M** aktiviert ihn. Das Modell sieht das Bild über den Vision-Projektor
des GGUF (`mmproj-…gguf` im Modellordner, auf der CPU):

- bei **Bearbeiten** als das zu bearbeitende Bild: die Anweisung benennt die Elemente so, wie sie im Bild aussehen, und
  die „bleibt unverändert“-Klausel nennt nur Teile, die wirklich im Bild sind;
- bei den anderen Zielen als Referenz für das, was der Entwurf erwähnt („dieselbe Szene im Winter“, „die Figur als
  Plüschtier“).

Ohne Bild und mit Ziel **Bearbeiten** entsteht die Anweisung nur aus dem Entwurf und schließt mit „Keep everything else
exactly as it is.“; das Log warnt einmal.

## Was der Knoten tut

`DaWImagePromptEnhancer` (Paket `ComfyUI-DaWasteh-PromptEnhancer`, im Updater) setzt einen Systemprompt aus vier Teilen
zusammen: gemeinsame Regeln (nur den Prompt ausgeben, alles aus dem Entwurf behalten, Lücken konkret füllen, nichts
Neues als Hauptmotiv, keine Marken oder realen Personen, keine Kommentare), Regeln des Ziels, Längenvorgabe, Sprachregel.
Der Entwurf, die `notes` und ein Hinweis auf das Bild gehen als Nutzernachricht mit. Dann:

1. `llm_backend.LlamaServer` des Pakets ComfyUI-DaWasteh-H3-MusicVideo startet `llama-server` mit dem GGUF aus dem
   Startprofil (`-ngl 999 -c 8192 -fa on`, Vision-Projektor auf der CPU, eingebauter MTP-Kopf als Draft).
2. Die Antwort wird bereinigt: Beschriftungen („Prompt:“, „Here is the prompt:“), Codeblöcke, umschließende
   Anführungszeichen, Markdown-Hervorhebungen, Aufzählungszeichen und Zeilenumbrüche fallen weg; Tags werden normalisiert
   und dedupliziert. Anführungszeichen **im** Text (Schriftzüge) bleiben.
3. Die Antwort muss brauchbar sein: nicht leer, keine Ablehnung des Modells („I can't …“), für die gewählte Länge nicht
   zu kurz und (außer bei Tags) nicht mitten im Satz abgebrochen. Sonst gibt es **einen zweiten Versuch mit Seed + 1000**
   auf demselben Server. Grund: Der Sampler zieht gelegentlich ein falsches erstes Token, und das Modell beendet die
   Antwort dann sofort (bei MV 2 gemessen, v1.2.5).
4. Auch der zweite Versuch unbrauchbar: Der **Entwurf geht unverändert weiter**, `INFO` sagt das, die verworfenen
   Antworten stehen im ComfyUI-Log. Nie eine halbe Antwort.
5. Der Server wird beendet, VRAM und RAM sind wieder frei. Fehlen das GGUF oder `llama-server` im Startprofil, bricht der
   Knoten mit einer Meldung ab, die sagt, was fehlt; mit `enhance` aus läuft er ohne beides.

Das System schreibt dem Modell **keine** Anweisung vor, Ablehnungen zu übergehen: Lehnt es ab, gilt das als unbrauchbar und
der Entwurf geht weiter.

## Einrichtung

Nichts Neues, wenn der Musikvideo-Prompt-Writer schon läuft. `tools/start-MultiGPU.ps1` setzt
`DAWASTEH_PROMPT_LLM_GGUF`, `DAWASTEH_LLAMA_SERVER` und `DAWASTEH_LLAMA_HIP_DEVICE`, sobald
`ComfyUI/models/LLM/Qwen3.8/Qwen3.8-27B-IQ4_XS-3.84bpw.gguf` und ein `llama-server.exe` (Standard: neuester
`b<Build>_hip_llama.cpp` unter `L:\LAB\ai-local`) existieren; Einzelheiten, Quant-Vergleich und Speicherverhalten in
[H3_MUSIC_VIDEO_V125.md](H3_MUSIC_VIDEO_V125.md). Das Startbanner heißt jetzt „LLM: MV 2 / Ming / image prompt enhancer“.

## Messwerte und Nachweis

Alle Läufe über das echte Frontend (headless Edge, `app.graphToPrompt` via `performance/rdna4/bench/ui_to_api.py`, Frontend 1.53.6)
auf einem frischen Testserver (Port 8192, MultiGPU-Profil mit VRAM-Guard) und mit demselben Startprofil wie im Alltag:
Qwen3.8-27B-IQ4_XS auf der RX 9070 XT, llama.cpp b11249 (HIP). Einzelwerte in
[`performance/rdna4/prompt-enhancer-v130-validation.json`](../performance/rdna4/prompt-enhancer-v130-validation.json),
gesichert durch `tests/test_prompt_enhancer_workflow_v130.py` (Bericht passt zur ausgelieferten Datei, jeder Fall
lief durch) und `tests/test_prompt_enhancer_nodes_v130.py`. GGUF und Projektor per SHA-256 im Bericht.

| Fall | Zeit | Ergebnis |
|---|---:|---|
| **Standard**: deutscher Entwurf „Ein alter Leuchtturm bei Sturm, Möwen, dramatisches Licht“ → Fließtext, mittel, English | 30,5 s | 136 Wörter, ein Absatz |
| anderer Seed (7) | 36,3 s | andere Fassung (153 Wörter) |
| Text im Bild: Jazzfestival-Poster mit zwei Schriftzügen | 24,1 s | beide Texte **wörtlich in Anführungszeichen** (auch „14. August · Stadtpark · Eintritt frei“) |
| Tags, ausführlich: Ritter im brennenden Dorf | 19,6 s | 42 Tags, `1boy`, kleingeschrieben, ohne Sätze |
| Ausgabe Deutsch, kurz | 30,2 s | deutscher Text (89 Wörter, deutsche Sätze laufen länger als die Vorgabe) |
| `notes`: „no people in the picture, warm colours, 35 mm film look“ | 27,1 s | Marktstraße ohne Menschen, 35-mm-Look, ohne das Wort „people“ |
| `enhance` aus | 0,0 s | Entwurf unverändert, der llama-server wird nicht gestartet |
| abgeschnittene Antwort (`max_tokens = 128`) | 33,2 s | beide Versuche mitten im Satz beendet → Entwurf unverändert, INFO nennt den Grund |
| Bearbeiten mit Bild (Strg+M, `angry_broccoli.png`), kurz | 19,8 s | „Place a tall black felt top hat … on the broccoli figure’s stem … Keep the face, pose …“ |
| Fließtext mit Bild als Referenz („die Figur als Plüschtier in einem Kinderzimmer“) | 24,2 s | beschreibt die Brokkoli-Figur mit dem wütenden Gesicht aus dem Bild |
| ohne GGUF/llama-server im Startprofil (zweiter Testserver) | 1,5 s | Fehler „Qwen3.8 27B ist nicht eingerichtet: … DAWASTEH_PROMPT_LLM_GGUF … start-MultiGPU.bat“ |
| ohne GGUF, `enhance` aus | 0,3 s | läuft, Entwurf unverändert |

**Dauer:** 20–36 s pro Lauf, davon ca. 16 s Serverstart; das Schreiben selbst dauert danach je nach Länge 4–20 s. Der Server
wird für jeden Lauf neu gestartet, weil er danach VRAM und RAM wieder freigibt (wie bei MV 2 und Ming). Läuft der Workflow
mehrfach mit demselben Seed und Entwurf, liefert ComfyUI das gespeicherte Ergebnis sofort; *randomize* (Standard) schreibt
bei jedem Queue neu.

**Speicher (Windows-GPU-Zähler des llama-servers, alle Läufe mit Modell):** 11,4–12,7 GiB dediziertes VRAM der RX 9070 XT
plus 0,9–2,6 GiB geteilter (Host-)Speicher, weil der Desktop auf derselben Karte läuft; ab 1,5 GiB warnt das Log. Der
Commit des Rechners stieg von ca. 43–45 GiB im Leerlauf auf höchstens 61,6 von 99,4 GiB, freier RAM mindestens 9,5 GiB.
Ohne Modell (Enhancer aus, ohne GGUF) bleibt alles beim Leerlaufwert.

## Grenzen

- Der Schreiber **füllt Lücken absichtlich**: „Sturm, dramatisches Licht“ wird zu Blitzen, schäumender Brandung, Möwen und einer festen Farbpalette im Detail. Was
  nicht abweichen darf, gehört in den Entwurf oder in `notes`.
- **Längenvorgaben sind Richtwerte.** Fließtext liegt oft an der oberen Grenze oder knapp darüber, deutsche Ausgabe länger
  als die Wortzahl vermuten lässt. Das Modell schreibt in **English** deutlich sauberer; deutsche Sätze haben gelegentlich
  Grammatikfehler.
- **Ausschlüsse** („keine Personen“, „ohne Text“) werden meist positiv umschrieben („leere Straße“), weil ein genanntes
  Wort ein Bildmodell erst recht malen lässt; das Modell hält sich nicht immer daran (in einem Vorversuch stand bei
  „Visitenkarte, kein Logo“ trotzdem „without any logos“). Für harte Ausschlüsse den Negativ-Prompt des Bildmodells nutzen.
- **Tags** enthalten die üblichen Qualitäts-Tags („masterpiece, best quality“) und gelegentlich „8k“ oder „realistic“;
  für Anime-Checkpoints (Danbooru-Vokabular) am besten, für andere SDXL-Modelle ein Ausgangspunkt.
- **Bearbeiten**: Die Anweisung ist nur so gut wie das, was das Modell im Bild erkennt; ob das Edit-Modell sie umsetzt,
  prüft der Enhancer nicht.
- Kein Dauerserver: jeder Lauf startet das GGUF (ca. 16 s). Für Serien vieler Prompts ist das langsamer als ein
  ComfyUI-internes 4B-Modell (`LLM_Gemma4_E4B_FP8-Idea-to-Prompt`), dafür ist es das größere Modell.
- Braucht die RX 9070 XT weitgehend frei; bei zu wenig VRAM lagert Windows in den Host-RAM aus und das Schreiben wird
  langsam (Warnung im Log).
