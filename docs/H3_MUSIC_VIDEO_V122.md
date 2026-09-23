# Song → Musikvideo mit MiniMax FastH3 · v1.2.2

`workflows/Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json` wurde von Grund auf neu gebaut.
Der bisherige Ein-Node-Director (bis v1.2.1) lief immer gleich ab: pro Szene dasselbe Referenzbild, fester Seed, ein
kleines Kamera-Vokabular und keine Verbindung zwischen den Szenen. Das Ergebnis war ein Vor-und-zurück der Kamera
ohne Handlung. Der neue Graph arbeitet in sichtbaren Schritten mit **FastH3**, echtem **Extend** zwischen den Szenen,
Story-Planung durch ein lokales LLM und dem **Originalsong als festem Audio-Strom** (lippensynchron).

## Bedienung

1. **MV 1 · Planer**: Song wählen oder hochladen (MP3/WAV/FLAC/M4A/OGG, beliebige Länge).
2. **LYRICS** einfügen, am besten mit `[Verse 1]`, `[Chorus]`, `[Bridge]`, `[Guitar Solo]` … Zeilen mit
   `[mm:ss.xx]`-Zeitstempel (LRC) werden direkt übernommen.
3. **VIDEOIDEE** in eigenen Worten, Deutsch oder Englisch: Story, Orte, Look, Stimmung.
4. Optional **bis zu drei Charaktersheets**: Loader mit **Strg+M** aktivieren und ein Bild wählen (Unterordner wie
   `input/Sheets/` werden angezeigt). Charakter 1 ist die Sängerin bzw. der Sänger.
5. **VIDEOFORMAT** im Pixaroma-Sizes-Node wählen. Getestet ist 864×480; Hochformat per Klick.
6. **Run**: Planung, Prompts, einmaliges Encodieren, dann Szene 1. Der Node *MV 5* zeigt Szene 1 als Video
   **mit Originalton**, das Gate *FREIGABE* hält an.
7. **Continue** am Gate: Alle weiteren Szenen werden per Extend gerendert, danach entsteht der fertige Film unter
   `output/video/DaWasteh_MusicVideo/<Projekt>_<Zeit>.mp4` (MP3/AAC) bzw. `.mkv` (WAV, FLAC, Opus …).
   - Anfang gefällt nicht: im Planer den **seed** ändern und erneut **Run**.
   - Ohne Zwischenstopp: Gate auf **Pass** stellen.

## Was im Graph passiert

| Schritt | Node | Inhalt |
|---|---|---|
| Planung | `MV 1 · Song + Lyrics Planner` | Dauer, Tempo und Energie; Lyrics-Timing per lokalem **Whisper small** (Wort-Zeitstempel, Fuzzy-Abgleich gegen den eingegebenen Text); Szenen mit variabler Länge |
| Prompts | `MV 2 · MiniMax Prompt Writer` | **Qwen3.5 4B**: Charaktersheets → Textbeschreibung, Produktionsbibel (Stil, eine Location je Songabschnitt in Story-Reihenfolge), Handlung je Shot |
| Encodieren | `MV 3 · H3-Textencoder` | Qwen3-VL-32B encodiert **alle** Szenen einmal und wird danach vollständig freigegeben |
| Szene 1 | `MV 4` → Sampler → `MV 5` | Songausschnitt fest im Audio-Strom, FastH3 8 Schritte, Vorschau mit Originalton |
| Freigabe | Pixaroma **Pause Image** | Pause / Continue / Pass |
| Rest | Pixaroma **Loop** (`Szenen − 1` Runden) | jede Runde: `MV 4` (Extend) → Sampler → `MV 5` |
| Film | `MV 6 · Fertiges Musikvideo` | Szenen ohne Neukodierung verbunden, Originaldatei per `-c:a copy` darunter |

### Szenenplan: jede Länge, variable Szenen

Kandidaten für Schnitte sind Abschnittsgrenzen (stark bevorzugt), Lücken zwischen Lyrics-Zeilen, Beats und ein
0,5-s-Raster (Schnitte mitten in einer gesungenen Zeile werden bestraft). Eine dynamische Programmierung wählt die
Schnitte so, dass jede Szene zwischen `min_scene_seconds` (4 s) und `max_scene_seconds` (9 s) liegt und möglichst
nahe am Ziel (7 s) ist. Beispiele: 30 s ≈ 5 Szenen, 90 s ≈ 12, 180 s ≈ 24, 600 s ≈ 80. Szenen über 6,5 s bekommen
2 Shots mit einem Schnitt an einer Zeilengrenze.

Warum höchstens 9 s: Mit 22 Übergangs-Frames ergibt das maximal 243 H3-Frames. Bei 864×480 lädt ComfyUI FastH3
(21,1 GB) dann vollständig; bei 260 bzw. 277 Frames reserviert es mehr Aktivierungsspeicher, lädt FastH3 nur teilweise
und das Sampling wird 2–4× langsamer (gemessen 24–26 bzw. 35–60 s/Schritt statt 12–16). Außerdem wählt der Planer
nur Clip-Längen mit **gerader** Latent-Länge: Ungerade Längen liefen mit VSA langsamer als die nächstlängere gerade
(192 Frames 15,0 s/Schritt, 209 Frames 12,5 s/Schritt, 226 Frames 18,9 s/Schritt). Die zusätzlichen Frames werden
erzeugt, aber nicht gespeichert.

### Frame-Buchhaltung und Lippensync

Szene *k* deckt die Song-Frames `[start, end)` ab (24 fps). Ab Szene 2 werden zusätzlich die letzten **22 Frames**
(0,92 s) der Vorgängerszene vorangestellt. Die Gesamtlänge wird auf das H3-Raster `17k+5` aufgerundet. Das Audio des
ganzen Clips ist der Originalsong ab `start − 22 Frames`.

In jedem Sampling-Schritt ersetzt ComfyUIs `noise_mask`-Mechanik

- den **Audio-Strom** vollständig durch das korrekt verrauschte Original: Das Modell erzeugt nur das Bild, und das Bild
  folgt dem echten Gesang;
- die **ersten Video-Latents** ab Szene 2 durch die eingefrorenen Übergangs-Frames: Die Szene setzt die vorherige
  nahtlos fort.

Gespeichert werden nur die neuen Frames. Der Film hat damit exakt `ceil(Dauer × 24)` Frames, und die unveränderte
Originaldatei passt ohne Resampling darunter.

Warum nicht `MiniMaxH3AddGuide`? Guides hängen Bild und Audio als zusätzliche Bedingungs-Tokens an (FL2VA-Mechanik).
Laut Modellkarte ist FastH3 **nur für Text-to-Video+Audio destilliert** („FL2VA and Ref2VA were not distilled“). Die
Maskenmethode funktioniert modellunabhängig.

### Charaktere

Weil Ref2VA nicht destilliert ist, gibt der Workflow die Sheets nicht als Referenzbilder an FastH3, sondern lässt sie
von Qwen3.5 (Vision) in eine genaue Textbeschreibung übersetzen: Kleidungsstück für Kleidungsstück mit Farben;
Logos und Maskottchen nur als kleine Aufdrucke. Die Beschreibung steht in jedem Szenen-Prompt. Die Identität über die
Szenen hinweg trägt zusätzlich der Extend.

### Speicher

Qwen3.5 4B und der 26-GB-H3-Textencoder werden **innerhalb** von MV 2/MV 3 geladen und danach freigegeben. Als
gecachte `CLIPLoader`-Ausgaben würden sie während der ganzen Render-Schleife Host-RAM belegen oder beim Entladen in den
Host-RAM verschoben werden (gemessen: Encodieren dauerte so 13 min statt ~1 min). In der Schleife bleibt nur FastH3
(21,1 GB) auf der R9700.

Der Übergangs-Encode (22 Frames bei 864×480) belegt am Stück **7,2 GiB**, ComfyUI schätzt für den H3-Video-VAE aber
nur ~1,2 GB. MV 5 gibt deshalb vorher gezielt 14 GiB VRAM frei (FastH3 wird teilweise ausgelagert und vor der nächsten
Szene automatisch zurückgeladen). Bei einem OOM räumt MV 5 alle Modelle aus dem VRAM und versucht es einmal erneut.

GPU-Platzierung: MODEL, CLIP und VAE alle auf **gpu:0** (R9700). Gemessen: Mit dem VAE auf der RX 9070 XT (gpu:1)
scheitert der Übergangs-Encode an der VRAM-Guard-Grenze der 16-GB-Karte (5 GiB VAE + 7,2 GiB Encode > 12,8 GiB).

### Fortsetzen

Alles liegt unter `output/DaWasteh_H3_MusicVideo_v2/<Projekt>_<Hash>/`: `plan.json`, `conditioning/`, `scenes/`
(Szenen-MP4, Übergangs-Latent, Kontaktbogen) und `preview/` (Szenen mit Originalton). Ein erneuter Lauf mit denselben
Eingaben überspringt fertige Szenen, ohne FastH3 zu starten (Lazy-Input). Das gilt auch nach einem Absturz oder
Neustart. Szenen hängen voneinander ab: Wird Szene *k* neu gerendert, werden alle folgenden ebenfalls neu gerendert.
`resume_existing_scenes = aus` rendert bewusst alles neu.

## FastH3-Profil

Übernommen aus dem lokal vom Nutzer getesteten Pixaroma-FastH3-Workflow (rekonstruiert aus den MP4-Metadaten):

| Parameter | Wert |
|---|---|
| Modell | `MiniMax H3/fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors` |
| Sigma-Shift | Video 10 / Audio 3 |
| Attention | `ModelAttentionBackend` = comfy kitchen attention, `BlockSparseAttention` = VSA 10 % |
| Sampler | `res_multistep`, `simple`, 8 Schritte, CFG 1 (`BasicGuider`) |

## Messwerte (R9700, 864×480, VRAM-Guard, v1.2.2-Validierung)

Finaler Lauf des ausgelieferten Workflows über das echte Frontend (headless Edge) und Pixaromas eigenes
Pause/Continue-Pruning; Details in `performance/rdna4/h3-music-video-v122-validation.json`. Eingaben: 90-s-MP3 mit
Lyrics, Videoidee und ein Charaktersheet (privat, nicht im Repository).

| Messung | Ergebnis |
|---|---|
| Pause (kalt: Whisper, Qwen3.5, H3-Encoder für 13 Szenen, Szene 1) | 325 s |
| Continue (12 Szenen per Extend + Finale) | 2503 s (41:43) |
| Gesamt für 90 s Song | 47 min ≈ 31 s Rechenzeit pro Songsekunde |
| Szenen | 13, Längen 5,25–8,5 s, 175–243 H3-Frames, alle mit gerader Latent-Länge |
| Sampling pro Schritt | 9,3–27,4 s, Median 12,6 s (8 Schritte) |
| FastH3 vollständig im VRAM | 12 von 13 Szenen (1× 189 MB ausgelagert) |
| Lyrics-Abdeckung (Whisper small) | 87 % der Wörter |
| Fertiger Film | 2160/2160 Frames (90,00 s), MP4 |
| Originalton | 3751/3751 MP3-Pakete **bitidentisch** (SHA-256 gleich) |
| Nähte (Bildänderung über der Naht ÷ Bewegung daneben) | Median 1,05, Maximum 1,74 (visuell geprüft: gleiche Einstellung) |

Die Sampling-Zeit schwankte bei gleicher Länge und vollständig geladenem Modell um den Faktor 2, obwohl kein anderer
Prozess die GPU nutzte. Die Ursache (Takt, Allocator) ist nicht geklärt; Zeiten sind deshalb als Spanne angegeben.
Hochgerechnet braucht ein 600-s-Song mit ~80 Szenen etwa 5 Stunden.

## Grenzen

- FastH3 ist ein 8-Schritt-Destillat: schwierige Bewegungen und feine Details liegen laut Modellkarte unter dem
  Basis-H3. Hände und Schrift auf Schildern können fehlerhaft sein.
- Qwen3.5 4B plant die Story gut, wiederholt aber gelegentlich Handlungen benachbarter Szenen. Alle Prompts stehen im
  Node *PROMPTS* und in `plan.json`.
- Whisper erkennt gesungenen Text nicht perfekt. Der Fuzzy-Abgleich gegen die eingegebenen Lyrics fängt Hörfehler ab,
  aber stark verfremdete Vocals können Zeilen verschieben. LRC-Zeitstempel sind dann die exakte Alternative.
- Charaktertreue ist textbasiert und daher nicht pixelgenau.
- Rechenzeit wächst linear mit der Songlänge (siehe Messwerte).
