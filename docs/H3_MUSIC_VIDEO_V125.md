# Song → Musikvideo · v1.2.5: jede Szene prüfen, Prompt Writer mit Qwen3.8 27B, 1664×928 als Standard

v1.2.5 bringt drei Änderungen im Workflow
`workflows/Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json`: den neuen Prüf-Node **MV 5b**
nach jeder Szene, **MV 2 · Prompt Writer** mit Qwen3.8 27B und die Standardauflösung 1664×928. Planung, Encoder,
Extend und Speicherverhalten bleiben wie in [`H3_MUSIC_VIDEO_V122.md`](H3_MUSIC_VIDEO_V122.md) und
[`H3_MUSIC_VIDEO_V124.md`](H3_MUSIC_VIDEO_V124.md) beschrieben.

## Jede Szene prüfen: MV 5b

Bis v1.2.4 hielt der Workflow nur einmal an, nach Szene 1, und zeigte dort ein Standbild (Pixaroma Pause Image).
Danach lief die Schleife bis zum Ende durch. Eine misslungene Szene sah man erst im fertigen Film. Weil jede Szene
auf den letzten Frames der vorigen aufbaut, hätte man ab dieser Stelle alles neu rendern müssen.

Jetzt steht hinter jedem **MV 5 · Szene speichern** der Node **MV 5b · Szene prüfen** (`DaWMV2ReviewScene`), einmal
für Szene 1 und einmal im Loop. Nach jeder neu gerenderten Szene hält der Lauf an. Der Node spielt die Szene als
Video **mit Originalton** ab (Lippensync prüfbar), unten rechts erscheint ein Hinweis mit **Anzeigen**, der die
Ansicht auf den Node setzt.

| Knopf | Wirkung |
|---|---|
| **✓ Weiter** | Szene übernehmen, die nächste wird per Extend gerendert |
| **↻ Neu rendern** | dieselbe Szene noch einmal mit neuem Seed, im selben Lauf. Die Schleife zählt erst nach *Weiter* weiter |
| Reiter **Take 1 / Take 2 …** | frühere Versuche derselben Szene abspielen; **Take N nehmen + weiter** übernimmt einen früheren Take |
| **⏩ Rest ohne Prüfung** | Szene übernehmen, alle weiteren Szenen dieses Laufs ohne Halt (z. B. über Nacht) |
| Schalter `review` am Node | `durchrendern`: von Anfang an ohne Halt (entspricht *Pass* am alten Gate) |

**Wie Neu rendern funktioniert.** MV 5b verschiebt die Dateien des gezeigten Takes nach `takes/` im Projektordner,
gibt der Szene einen neuen Seed und hängt per ComfyUI-Graph-Expansion eine Kopie seiner eigenen Kette in den
laufenden Prompt: MV 4 → Rauschen → Guider → Sampler → MV 5 → MV 5b. Modell, VAEs, Sampler-Einstellungen und
Loop-Index werden geteilt, nicht neu geladen. Das funktioniert für Szene 1 und innerhalb jeder Loop-Runde. Take 0
behält den Seed aus dem Planer, deshalb setzen bestehende Projekte ihre Szenen unverändert fort. Spätere Takes
bekommen einen Seed weit weg von allen anderen Szenen (`mv2.take_seed`). Ein neuer Take einer Szene macht, wie bisher
jede Änderung, alle *folgenden* Szenen ungültig. Im normalen Ablauf existieren die zu diesem Zeitpunkt noch nicht.

**Fortsetzen und Abbrechen.** Der Stand steht in `plan.json`: Take, Seed, `review` (`pending`/`approved`) und die
archivierten Takes. **Abbrechen** in der Queue beendet das Warten sofort. Ein neuer Run überspringt fertige Szenen
wie bisher. Freigegebene Szenen laufen ohne Halt durch, eine Szene, die beim Abbruch noch wartete, erscheint sofort
wieder zur Prüfung, ohne neu gerendert zu werden. Szenen aus Projekten vor v1.2.5 gelten als freigegeben. Lädt man
die Seite neu, während eine Szene wartet, holt sich das Widget die offene Prüfung vom Server.

**Unterschied zum Pixaroma-Gate.** Das Gate beendete den Prompt und startete ihn für *Continue* neu. MV 5b hält den
laufenden Prompt an, FastH3 bleibt geladen. Die Queue zeigt den Lauf während des Wartens als aktiv, andere Workflows
warten so lange, und der Run-Timer zählt die Wartezeit mit.

**Ohne Browser** (API-Läufe): Das Log nennt die Prüf-ID. `GET /dawasteh/mv2/review` liefert die offene Prüfung,
`POST /dawasteh/mv2/review` mit `{"id": "…", "action": "continue" | "redo" | "continue_all", "take": 0}` entscheidet
(`take` optional, 0-basiert). Für reine API-Läufe `review` auf `durchrendern` stellen.

**Grenzen.** Neu rendern ändert den Seed, nicht den Prompt; dafür müsste der 26-GB-Textencoder neben FastH3 geladen
werden. Nachträglich lässt sich nur die Szene neu machen, die gerade wartet, weil alle späteren auf ihr aufbauen.

**Live geprüft** (R9700, 1664×928, echtes Frontend in headless Edge, Entscheidungen per Klick auf die Knöpfe und
Reiter im Widget; Nachweis [`h3-music-video-v125-review-validation.json`](../performance/rdna4/h3-music-video-v125-review-validation.json)):
19,2-s-Songausschnitt, 3 Szenen.

| Schritt | Ergebnis |
|---|---|
| Szene 1 → Neu rendern, dann Reiter *Take 1* → übernehmen | Take 1 zurück in `scenes/`, Take 2 in `takes/`, Szene 2 setzt auf Take 1 auf |
| Szene 2 → Abbrechen in der Queue, neu starten | Szene 2 erscheint nach 3,6 s wieder zur Prüfung, ohne Sampling und ohne FastH3 zu laden |
| Szene 2 → zweimal Neu rendern in der Schleife | Take 2 und Take 3 im selben Lauf, Take 1 und 2 archiviert |
| Szene 2, Take 3 → Rest ohne Prüfung | Szene 3 läuft ohne Halt durch, danach der Film |
| Film | 461/461 Frames, alle 801 MP3-Pakete bitidentisch, jede Szene bildgenau der gewählte Take, Nähte 0,93/1,03 |
| Zeit bis zur nächsten Prüfung nach *Neu rendern* | 10 min (175 H3-Frames), 15 min (209 H3-Frames) |

Der Test fand einen Fehler, der vor dem Release behoben wurde: In der ersten Loop-Runde hängt Loop Start am
Prüf-Node von Szene 1, und die erste Version klonte beim Neu rendern deshalb Szene 1s Kette mit (dort übersprungen,
aber unnötig). MV 5b klont jetzt nur die Kette ab dem nächstgelegenen MV 4.

## Was sich ändert

| Änderung | Warum |
|---|---|
| `llm = auto`: MV 2 schreibt mit dem GGUF-Modell aus dem Startprofil (Qwen3.8 27B über `llama-server`), ohne Eintrag wie bisher mit Qwen3.5 4B | 4B wiederholte Handlungen, verlor Orte und Kleidungsstufen (Messung unten) |
| Der Server läuft nur, solange Prompts fehlen, auf **gpu:1** (RX 9070 XT) und wird danach beendet | Das Rendern auf gpu:0 bekommt VRAM und RAM vollständig zurück; mit fertigen Prompts startet er gar nicht |
| Vor dem Start entlädt MV 2 ComfyUI-Modelle, die ein anderer Workflow auf der Server-GPU liegen ließ | sonst teilen sich zwei Prozesse 16 GB |
| Zeilen der Videoidee wie `Chorus - …`, `Verse 2: …`, `Intro and Verse 1: …` gehen gezielt an die Szenen dieses Abschnitts | Das Modell soll Ort, Kleidung und Handlung des eigenen Abschnitts übernehmen, nicht die des nächsten |
| B-Roll-Schnitte bleiben am Ort des eigenen Abschnitts | Bisher schnitten Shots ohne Gesang reihum zu Orten anderer Abschnitte. Weil jede Szene am letzten Ort der vorigen beginnt, blieben danach ganze Refrains dort hängen (Intro-Test: Szenen 7–13 im Thronsaal aus Verse 3, mit 4B und 27B) |
| Unlesbare Szenenantwort → zweiter Versuch mit anderem Seed | Bei 4 % Wahrscheinlichkeit zieht der Sampler `SH` statt des Tokens `SHOT`; danach beendet das Modell die Antwort (reproduziert mit und ohne MTP) |
| `PROMPT_VERSION` 11 | Die Szenen-Anfrage ist neu. Vorhandene Projekte schreiben ihre Prompts einmal neu; mit `auto` + GGUF gilt das ohnehin, weil der Modellname im Schlüssel steht |

## Standardauflösung 1664×928

Der Workflow startet jetzt mit **1664×928** (Pixaroma-Sizes, Planer-Default). Bei 1344×768 und darunter zeigten die
Testvideos erste Artefakte an Gesicht und Lippen; 1920×1088 kostet fast die doppelte Zeit. Renderzeit auf der R9700
(Median pro Szene, Szenen im Mittel 7,3 s lang):

| Auflösung | pro Szene | 90-s-Song (13 Szenen) |
|---|---|---|
| 1344×768 | 7,8 min | ≈ 1,7 h |
| **1664×928** | **15,6 min** | **≈ 3,4 h** |
| 1920×1088 | ≈ 28 min | ≈ 6 h |

1664×928 liegt mit ~94 000 Tokens pro Extend-Szene über der 65 536-Token-Grenze; dort greifen die
Speichermaßnahmen aus v1.2.4 (Aktivierungsreserve, MLP-Blöcke), gemessen ohne OOM. Die Auflösung steckt im
Projekt-Fingerprint: Ein Wechsel legt ein neues Projekt an, statt Szenen einer anderen Auflösung fortzusetzen.

Qwen3.5-Projekte behalten ihren Cache-Schlüssel, solange das Modell gleich bleibt. Das Feld `prompt_llm` im
`plan.json` hält fest, welches Modell die Prompts geschrieben hat.

## Einrichtung

`tools/start-MultiGPU.ps1` (bzw. die installierte Kopie `L:\ComfyUI\start-MultiGPU.ps1`):

```powershell
$PromptLlmGguf = Join-Path $ComfyPath "models\LLM\Qwen3.8\Qwen3.8-27B-IQ4_XS-3.84bpw.gguf"
$LlamaServerExe = "L:\LAB\ai-local\b11160_hip_llama.cpp\build\bin\llama-server.exe"
$LlamaHipDevice = "1"              # physischer HIP-Index: 1 = RX 9070 XT
```

Modell und Vision-Projektor liegen in `ComfyUI/models/LLM/Qwen3.8/`:
`Qwen3.8-27B-IQ4_XS-3.84bpw.gguf` (13,1 GB) und `mmproj-Qwen3.8-27B-IQ4_XS-3.84bpw-bf16.gguf` (0,9 GB).
Das Profil setzt `DAWASTEH_PROMPT_LLM_GGUF`, `DAWASTEH_LLAMA_SERVER` und `DAWASTEH_LLAMA_HIP_DEVICE` nur, wenn beide
Dateien existieren; sonst bleibt MV 2 bei Qwen3.5 4B. Der Vision-Projektor (`mmproj-…gguf`) wird im Modellordner
gesucht, bevorzugt mit demselben Quant-Tag und derselben Modellgröße. HIP- und Vulkan-Builds von llama.cpp
funktionieren beide.

Weitere Schalter (Umgebungsvariablen): `DAWASTEH_LLAMA_CTX` (Standard 8192), `DAWASTEH_LLAMA_MMPROJ_GPU=1`
(Projektor auf der GPU, braucht 0,9 GiB mehr VRAM).

Server-Parameter: `-ngl 999 -c 8192 -fa on -np 1 --reasoning off --no-mmproj-offload --spec-type draft-mtp`.
Als Draft dient der **eingebaute MTP-Kopf** des Modells, kein separates Draft-Modell (DFlash2 bleibt aus). Scheitert der
Start mit MTP, versucht MV 2 es ohne spekulatives Decoding. Scheitert auch das, schreibt MV 2 mit Qwen3.5 4B weiter
und meldet das im Log. Unter Windows hängt der Server an einem Job-Objekt: Stürzt ComfyUI ab, beendet Windows auch den
Server, damit keine 12 GiB VRAM verwaist belegt bleiben.

## Speicher auf der RX 9070 XT

Der Desktop läuft auf derselben Karte; Windows gibt dem Serverprozess daneben rund 12,5 GiB dediziert. HIP meldet
unter Windows fremden Verbrauch nicht; `--fit` greift außerdem nicht, wenn `-ngl`/`-c` gesetzt sind. Gemessen über die
Windows-GPU-Zähler (dedizierter und geteilter Speicher des Serverprozesses), mit MTP, zuerst Ridge 3,7 bpw:

| Konfiguration | VRAM | geteilt (Host) | Text | Charakterblatt |
|---|---|---|---|---|
| 16k Kontext, Projektor auf GPU, ubatch 512 | 12,82 GiB | **2,31 GiB** | 40,9 tok/s | 6,3 s |
| 8k, Projektor auf GPU, ubatch 256 | 13,14 GiB | 1,27 GiB | 41,3 tok/s | 6,2 s |
| **8k, Projektor auf CPU, ubatch 512 (Standard)** | **12,47 GiB** | **0,34 GiB** | **40,5 tok/s** | 12,7 s |
| 8k, Projektor auf CPU, ubatch 256 | 12,34 GiB | 0,31 GiB | 40,0 tok/s | 13,7 s |
| **IQ4_XS 3,84 bpw, 8k, Projektor auf CPU, ubatch 512 (Standard)** | **12,68 GiB** | **0,92 GiB** | **27,1 tok/s** | 14,6 s |
| IQ4_XS, 8k, ubatch 128 | 12,48 GiB | 0,88 GiB | 29,3 tok/s | 15,4 s |
| IQ4_XS, 6k, ubatch 256 | 12,54 GiB | 0,89 GiB | 29,2 tok/s | 15,7 s |

Geteilter Speicher über ~0,3 GiB heißt: Teile des Modells liegen im Host-RAM. Unter Windows/ROCm gibt es dabei kein
OOM (siehe VRAM-Guard, v1.1.2). Bei IQ4_XS sind es ~0,55 GiB. Kleinerer Kontext oder ubatch ändert daran nichts, das
Modell ist schlicht 0,45 GiB größer als Ridge. Das kostet rund 30 % Tempo, sonst nichts. MV 2 prüft den Wert nach dem
Start und warnt ab 1,5 GiB. Die längste MV-2-Anfrage (Produktionsbibel mit Lyrics eines 5-Minuten-Songs) passt in
8k Kontext.

## Welches Quant

Perplexity auf wikitext-2 (`llama-perplexity`, 20 Blöcke à 2048 Tokens, alle auf demselben Text, gpu:1):

| Datei | Größe | Perplexity | Tempo auf der 9070 XT |
|---|---|---|---|
| `Qwen3.8-27B-Ridge-3.7bpw.gguf` | 12,6 GB | 6,593 ± 0,111 | 40 tok/s |
| **`Qwen3.8-27B-IQ4_XS-3.84bpw.gguf`** | **13,1 GB** | **6,208 ± 0,106** | **28 tok/s** |
| `Qwen3.8-27B-UD-Q4_K_XL.gguf` | 17,6 GB | 5,997 ± 0,101 | passt nicht (46 von 65 Schichten auf der GPU: ~10 tok/s) |

Ridge ist bei fast gleicher Größe deutlich verlustreicher (+6 % gegenüber IQ4_XS). Bei den Aufgabenmetriken unten
erreichen Ridge und IQ4_XS beide die Bestwerte; die Perplexity gibt den Ausschlag, das Tempo spielt neben dem Rendern
keine Rolle (Outro 103 statt 85 s, Intro 281 statt 196 s). UD-Q4_K_XL wäre auf der R9700 möglich
(`$LlamaHipDevice = "0"`), dort teilt es sich aber die Karte mit ComfyUI und anderen llama-Servern. Deshalb ist es
kein Standard.

## Qualität: 27B gegen 4B

Gleiche Pläne, Ideen, Charakterblätter und Seeds wie in den Vergleichsläufen vom 25.09.2026. Auswertung per Skript:
Ortstreue (Stichwörter des Abschnitts in den Shot-Handlungen), wiederholte Shots (Ähnlichkeit > 0,75 zu einem
früheren Shot), Kleidungskonflikte (Outro: Kleidung, die zur Stufe des Abschnitts nicht passt).

| Lauf | Ortstreue | wiederholte Shots | Kleidungskonflikte | Dauer MV 2 |
|---|---|---|---|---|
| Outro-Villa, Qwen3.5 4B | 0,85 | 6 / 18 | Szenen 7, 12 | – |
| **Outro-Villa, Qwen3.8 27B** | **1,00** | **0 / 18** | **keine** | 85 s |
| Intro Idee 2, Qwen3.5 4B, bester von 4 Seeds | 0,78 | 22 / 56 | – | – |
| Outro-Villa, Qwen3.8 27B IQ4_XS | 1,00 | 0 / 18 | keine | 103 s |
| Intro Idee 2, Qwen3.8 27B, B-Roll noch wie v1.2.4 | 0,88 | 0 / 56 | – | 196 s (41 Szenen, 3 Blätter) |
| **Intro Idee 2, Qwen3.8 27B, v1.2.5** | **1,00** | **0 / 56** | – | 196 s |
| Intro Idee 2, Qwen3.8 27B IQ4_XS, v1.2.5 | 1,00 | 0 / 56 | – | 281 s |

Die fett markierten 27B-Zeilen stammen von Ridge (gleiche Seeds).

4B schrieb im Outro für vier Szenen wortgleich dieselbe Handlung und ließ die Bomberjacke bis Verse 2 an. 27B
führt die Kleidungssteigerung Abschnitt für Abschnitt aus und hält die nächtliche Villa, die Lichtführung und die
Blickrichtung über die Szenen hinweg durch. Explizite oder minderjährig codierte Begriffe kamen in keinem Lauf vor.
Die Intro-Fehltreffer mit der alten B-Roll-Ortswahl (Szenen 3, 7, 11–13: Refrain im Thronsaal aus Verse 3) sind
mit v1.2.5 verschwunden. Der 4B-Lauf hatte an denselben Stellen dieselbe Drift.
