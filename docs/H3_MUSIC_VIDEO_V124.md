# Song → Musikvideo · v1.2.4: Realismus-LoRA und 1920×1088 ohne OOM

v1.2.4 erweitert `workflows/Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json` um einen
eigenen Modell-Loader **MV 0** mit optionaler Realismus-LoRA und behebt den Speicherfehler, der bei 1920×1088 in
der Extend-Schleife auftrat. Bedienung und Pipeline sind unverändert, siehe [`H3_MUSIC_VIDEO_V122.md`](H3_MUSIC_VIDEO_V122.md).

## Warum 1920×1088 bei Szene 1 lief und im Extend-Loop „OOM“ meldete

Gemessen auf der R9700 mit dem normalen Startprofil (reserve-vram 4, VRAM-Guard 3 GiB), Szene 2 des Outro-Songs:
209 H3-Frames bei 1920×1088 = **127 541 Tokens**.

1. **Die Extend-Szenen sind länger als Szene 1.** Szene 1 hat keine Übergangs-Frames (175 H3-Frames), jede weitere
   Szene trägt die 22 eingefrorenen Frames der Vorgängerszene zusätzlich (209–243 H3-Frames). Die Aktivierungen
   sind damit etwa 20–40 % größer.
2. **Jede VRAM-Allokation zählt auf diesem Treiber gegen das Windows-Commit-Limit** (RAM + Auslagerungsdatei, hier
   103,6 GB). Beim Laden stiegen VRAM-Belegung und System-Commit im Verhältnis 1 : 1 (+12,3 GB VRAM ≙ +12,9 GB Commit).
3. **ComfyUI bildet die 22-GB-FastH3-Datei als Copy-on-Write ab.** Windows verbucht dafür sofort die ganze Datei als
   Commit (gemessen **+20,65 GiB**, obwohl noch nichts gelesen war).
4. Zusammen erreichte der erste Block der Extend-Szene **100,4 von 103,6 GB Commit**. Danach schlägt `hipMalloc`
   fehl, und PyTorch meldet „out of memory“, obwohl die Karte rechnerisch noch Platz hätte.
5. Nach Behebung von Punkt 3 lief Schritt 1 durch, Schritt 2 scheiterte an **Fragmentierung**:
   `Tried to allocate 5.11 GiB … 6.79 GiB reserved but unallocated`. Die 5,11 GiB sind die fusionierte
   QKV-Projektion (127 541 × 21 504 × 2 Byte), die in keinem der zerstückelten freien Blöcke Platz fand.

Weitere Randbedingung: ComfyUI hält auf AMD immer mindestens 40 % des freien VRAMs für Gewichte fest
(`MIN_WEIGHT_MEMORY_RATIO = 0.4`, auf NVIDIA 0), hier 12,5 GB. Der Spitzenwert pro Block liegt in der
VSA-Attention (+10,7 GiB über den Gewichten); das MLP läge ungeteilt noch darüber (~+12 GiB).

## Was v1.2.4 ändert

| Maßnahme | Wirkung (gemessen) |
|---|---|
| **MV 0** bildet FastH3 **schreibgeschützt** ab (`mmap` read-only) statt Copy-on-Write | +0,04 statt +20,65 GiB Commit; Prozess-Private-Bytes 12,8 statt 38 GB; Commit-Reserve im Sampling ~25 statt 0,9 GB |
| Cache vor jedem Schritt leeren, Aktivierungsreserve prüfen (Tokens × 112 kB × 1,2), bei Bedarf Gewichte auslagern | jeder Schritt startet mit frischem Speicherlayout; Schritt 2+ ohne Fragmentierungs-OOM |
| MLP in Token-Blöcken (32 768), adaLN-Modulation als Segmente statt Per-Token-Kopie | MLP-Spitze unter der Attention; Modulation **bitidentisch** (Test) |
| `render_key` enthält Modell, LoRA, Stärke und Triggerwort | Wechsel der LoRA rendert neu statt alte Szenen zu übernehmen |

Alles davon greift erst oberhalb von **65 536 Tokens**. 864×480 (29k Tokens) und die 1344×768-Szenen bis 209 Frames
(64k) laufen exakt den v1.2.2-Rechenweg. Die Anpassungen hängen nur am Modell aus MV 0, andere Workflows sind nicht betroffen.

Nicht geändert wurde ComfyUI selbst. Wer den Guard abschaltet oder die Auslagerungsdatei verkleinert, verschiebt die
Grenzen.

**Verworfen:** `max_split_size_mb:512` verhindert die Fragmentierung ebenfalls, machte einen VSA-Schritt aber 1,8×
langsamer (215,9 statt 122,7 s bei 127 541 Tokens), weil übergroße Blöcke bei jeder Nutzung neu per `hipMalloc`
angelegt werden. Zum Experimentieren bleibt es per `DAWASTEH_H3_ALLOC_CONF=max_split_size_mb:512` zuschaltbar.
`expandable_segments` hängt unter ROCm/Windows beim ersten Allokieren.

MV 2 und MV 3 laden Qwen3.5 und den H3-Textencoder ebenfalls schreibgeschützt. Im Abnahmelauf hatte der
Copy-on-Write-Textencoder den Commit allein in MV 3 auf 97,5 von 103,6 GB gebracht, unabhängig von der Auflösung.

## Realismus-LoRA

MV 0 lädt standardmäßig **fal/MiniMax-H3-Realism-People-LoRA** (`h3-realism-people-t2v-i2v-r2v.safetensors`,
Rank 32, nur Attention, SHA-256-gepinnt in `tools/workflow_templates/v122/models.json`) und setzt das Triggerwort
`r34l1sm` vor jeden Szenen-Prompt (in MV 3). `lora_name = none` schaltet sie ab.

### Vergleich (gleicher Seed, gleiche Szene)

Szene 1 des Outro-Songs, 1344×768, 175 H3-Frames, Seed 20260923, FastH3 8 Schritte; Referenz ist der bereits
vorhandene Lauf ohne LoRA. Jede Variante mit ihrem eigenen Triggerwort in MV 3. Rechenzeit je Variante 350–370 s.

| Variante | Gesicht (Originalauflösung) | Bildwirkung | Urteil |
|---|---|---|---|
| ohne LoRA | glatt, glänzend, „Beauty-Filter“ | kräftige Neonfarben, ignoriert „desaturated“ im Prompt | Referenz |
| **fal Realism People 0,8** (`r34l1sm`) | **natürlichste Haut, klare Augen, kein Plastik-Look** | filmisch, entsättigt, Doku-Kamera; folgt „desaturated neon“ | **Standard** |
| fal Realism People 1,0 | ähnlich, etwas grauer und überschärft | noch stärker entsättigt | möglich, aber 0,8 reicht |
| Natural Face & Speech v2 0,7 (vpakarinen, Apache-2.0) | gut, ausdrucksstark, Haut etwas glatter | behält die Farben der Referenz; deutlichste Mundformen beim Singen | **Alternative**, wenn Farben wichtiger sind als Hautrealismus |
| Facial Realism CloseUp 0,8 (prithiv, `Facial Realism`) | verwischt, leicht deformiert | Halbtotale statt Nahaufnahme | nicht empfohlen |

Recherchiert, aber nicht geladen: „MiniMax H3 Cinematic“ (TuTu, Civitai 2937713) ist laut Autor für pruned-Modelle
gebaut, der Download verlangt aber einen Civitai-Login. Eine LoRA speziell für FastH3 (8 Schritte) gibt es derzeit
nicht; alle getesteten wurden auf dem Basis-H3 trainiert. Nutzerberichte zur fal-LoRA nennen Glitches auf
pruned-INT8-Modellen bei hoher Stärke und Probleme mit Multi-Shot-Prompts – bei 0,8 traten in den Tests keine auf.

Die beiden zusätzlich geladenen Dateien liegen in `models/loras/MiniMax H3/` und sind in MV 0 auswählbar:
`natural_face_speech_h3_lora_v2_500.safetensors` (SHA-256 `40b1af61…`) und
`minimax-h3-facial-realism-closeup-cp2000.safetensors` (`df2e588d…`, kann gelöscht werden). ComfyUI lädt alle drei
ohne Konvertierung (für H3 gibt es eine eigene Schlüsselzuordnung ohne `diffusion_model.`-Präfix).

## Abnahmelauf

[`h3-music-video-v124-validation.json`](../performance/rdna4/h3-music-video-v124-validation.json), gesichert durch
`tests/test_h3_music_video_v124.py`. Ausgelieferter Workflow mit den Eingaben des Outro-Songs (90 s, Lyrics,
Videoidee, ein Charaktersheet), **1920×1088**, fal-LoRA 0,8 mit `r34l1sm`; serialisiert über das echte Frontend
(`app.graphToPrompt`) und Pixaromas `prune.mjs` (Pause, dann Continue). Die finale Workflow-Datei erzeugt denselben
API-Vertrag wie der getestete Graph (`89f57848…`).

| Messung | Ergebnis |
|---|---|
| Szenen | 13, 5,25–8,5 s, 175 / 209 / 243 H3-Frames (107k / 128k / 148k Tokens) |
| Versuch 1 | Szenen 1–6 fertig, dann OOM in Schritt 2 von Szene 7 (243 Frames): die erste Reserve-Kalibrierung ließ nur 0,8 GiB Luft. Korrigiert auf die gemessenen Blockspitzen (112 kB/Token × 1,2) |
| Versuch 2 (Resume) | Szenen 1–6 übersprungen, 7–13 ohne OOM; bei 243 Frames lagerte MV 0 je Szene ~2,9 GiB Gewichte aus |
| Rechenzeit | 5,8 h für den 90-s-Song inklusive des abgebrochenen Versuchs; Szenen 13–36 min |
| Schritt (8 je Szene) | dicht (Schritte 1–2): 170–180 s bei 175, 265–370 s bei 209, 310–535 s bei 243 Frames; VSA: 65–240 s |
| Speicher | Commit-Reserve in der Render-Schleife ≥ 21 GiB (vorher < 1 GiB); VRAM-Spitze 28,0 von 28,7 GiB (Guard) |
| Fertiger Film | 2160/2160 Frames (90,00 s), 1920×1088, MP4 |
| Originalton | 3751/3751 MP3-Pakete **bitidentisch** |
| Nähte | Median 1,005, Maximum 1,16 (v1.2.2: 1,74) |
| Lyrics-Abdeckung | 87 % (Whisper small) |

**Knappe Reserve kostet auch Zeit:** Mit der ersten Kalibrierung brauchte Schritt 1 von Szene 7 565 s (11,2 s pro
Block), mit der korrigierten 393 s (7,8 s pro Block). Am Guard-Limit muss der Allocator ständig freigeben und neu
anfordern.

Sichtprüfung: Die Szenen folgen der Idee (Straße, Haus, Raum, Dach, Skyline, zerstörte Stadt, Serverracks, Dachluke).
Die Gesichter wirken mit der LoRA fotorealistisch, Outfit und Haare bleiben durchgehend gleich. Zwischen weit
entfernten Szenen driftet das Gesicht etwas (Identität nur per Text), und Schrift auf Jacken und Schildern bleibt
unleserlich.

### Schreibgeschützte Loader: bitgleich zum Core

- **Textencoder:** MV 3 hat die 13 Prompts des Abnahmelaufs in einem frischen Prozess schreibgeschützt neu encodiert:
  13/13 Conditionings bitgleich zum Copy-on-Write-Lauf. Dafür muss der Loader die Schlüssel wie safetensors
  **sortieren**. In Header-Reihenfolge waren die Gewichte identisch, die Ausgaben wichen aber um 4·10⁻⁶ ab, weil ein
  anderes VRAM-Layout andere GEMM-Kernel auswählt.
- **FastH3 unterhalb der Schwelle:** Szene 1 des 1344×768-Outro-Laufs (63,8k Tokens) über `UNETLoader` und über MV 0
  (schreibgeschützt, ohne LoRA) im selben Server: Übergangs-Latents bitgleich (Differenz 0,0). Ein Rendering aus einer
  früheren Serversitzung wich von beiden gleich stark ab – Umgebung, nicht Loader.
- **Commit beim Textencoder:** Private Bytes 29,6 → 2,9 GB, Commit-Spitze 77,1 → 54,4 GB.
- Der Abnahmelauf lief noch vor dem Sortieren (identische Gewichte, nur Rundungsunterschiede über die Kernelwahl).
