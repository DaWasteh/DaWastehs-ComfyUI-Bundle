# Song → Musikvideo · v1.2.7: Upscale nach jeder Freigabe (MV 5c), Favoriten 960×544 und 1280×704

v1.2.7 erweitert den Workflow
`workflows/Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json` um einen optionalen Upscale.
Er sitzt direkt hinter der Szenen-Prüfung (MV 5b) und skaliert jede **freigegebene** Szene hoch, bevor die nächste
gerendert und zur Prüfung vorgelegt wird. Wählbar sind die vier Methoden aus `workflows/Video Upscaling/`.
Am Ende legt MV 6 den Originalfilm, den hochskalierten Film und ein Vergleichsvideo ab. Planung, Prompts, Extend und
Prüfung bleiben wie in [`H3_MUSIC_VIDEO_V125.md`](H3_MUSIC_VIDEO_V125.md) beschrieben.

## Bedienung

| Node | Was man einstellt |
|---|---|
| **MV 5c · UPSCALE AN/AUS + METHODE** (`DaWMV2UpscaleSettings`, bei den Eingaben) | `upscale`: hochskalieren / aus · `method`: eine der vier Methoden · `target_long_side`: lange Seite des Upscales (Standard 1920) |
| **SZENE 1 · HOCHSKALIEREN** und **LOOP · HOCHSKALIEREN** (`DaWMV2UpscaleScene`) | nichts – beide holen sich die Einstellung von der Schalter-Node, zeigen Fortschritt und das hochskalierte Ergebnis mit Originalton |
| **MV 6 · FERTIGES MUSIKVIDEO** | `comparison`: `nebeneinander` (Standard) oder `aus` |

Ablauf pro Szene: rendern → **MV 5b** zeigt sie → **Weiter** → **MV 5c** skaliert genau diesen Take hoch → nächste
Szene. **Neu rendern** hängt nur die Kette bis MV 5b neu ein; ein verworfener Take erreicht MV 5c nie. Wählt man einen
früheren Take (Reiter + *Take N nehmen + weiter*), wird dieser hochskaliert. Auch **Rest ohne Prüfung** und
`review = durchrendern` skalieren jede Szene, denn sie gelten als freigegeben.

MV 6 schreibt nach `output/video/DaWasteh_MusicVideo/`:

| Datei | Inhalt |
|---|---|
| `<Projekt>_<Zeit>.mp4` | Original in Renderauflösung, Originalton per `-c:a copy` |
| `<Projekt>_<Zeit>_upscale_<Methode>_<B>x<H>.mp4` | dieselben Szenen hochskaliert, gleiche Tonspur |
| `<Projekt>_<Zeit>_vergleich_original_vs_<Methode>.mp4` | links das Original (Lanczos auf Zielgröße), rechts der Upscale, gleiche Tonspur |

Die hochskalierten Szenen liegen im Projektordner unter `upscaled/<Methode>_<B>x<H>/`. **Methode oder Zielgröße
wechseln** geht jederzeit: Ein neuer Run rendert keine Szene neu, er skaliert nur die fertigen Szenen mit der neuen
Einstellung (eigener Ordner, frühere Upscales bleiben erhalten). Mit `upscale = aus` laufen die Szenen durch, und MV 6
schreibt nur das Original.

## Auflösung: Favoriten 960×544 und 1280×704

Die Größenliste übernimmt deine Liste aus dem Workflow: **1280×704** kam dazu, **960×544** und **1280×704** tragen
den Stern, **960×544** ist ausgewählt. Beide landen mit der Standard-Langseite 1920 bei Full-HD-Breite:
960×544 → **1920×1088** (×2), 1280×704 → **1920×1056** (×1,5). Ohne Upscale bleibt **1664×928** die Empfehlung
(Planer-Standard unverändert). Rendern pro 7-s-Szene auf der R9700: 960×544 ≈ 2 min, 1280×704 ≈ 4–5 min,
1664×928 ≈ 8–15 min.

## Die vier Methoden im Vergleich

Gemessen auf der R9700 an Szene 3 des 19,2-s-Testausschnitts (130 Frames = 5,4 s, 960×544 → 1920×1088), jeweils mit
kaltem Modell. PSNR gegen das Lanczos-hochskalierte Original (Treue), Laplace-Varianz als Maß für feine Details
(Lanczos: 10,3):

| Methode | Zeit | ≈ 90-s-Song | PSNR | Detail | Eindruck |
|---|---|---|---|---|---|
| **WAN 2.2 Low-Noise** (Standard) | 12,9 min | 3,6 h | 26,2 dB | 15,8 | bleibt am Original: Gesicht, Mundform, Pose; saubere Haut-, Haar- und Stoffdetails |
| **SeedVR2 3B** | 8,2 min | 2,3 h | 28,5 dB | 124 | scharfe Kanten, wirkt bei ×2 gemalt: stachelige Haarspitzen, fleckige Haut |
| **H3 Latent Upscaler 3D** | 4,9 min | 1,4 h | 23,9 dB | 29,0 | am schnellsten, sehr scharf, zeichnet aber Mimik und Pose neu (im Testframe Mund geschlossen statt offen) |
| **H3 Ultimate Upscale** | 7,6 min | 2,1 h | 22,9 dB | 27,7 | zweiter FastH3-Durchgang in Kacheln, zeichnet am freiesten neu |

Die hohe Laplace-Varianz von SeedVR2 kommt von den Mal-Artefakten, nicht von echtem Detail. Keine Methode hat einen
Zeitversatz: Jede Ausgabe passt bei Verschiebung 0 am besten zum Original.

**Warum WAN der Standard ist.** Im Musikvideo zählt der Lippensync. Die beiden H3-Methoden rechnen bei Denoise 0,25
(Start-σ ≈ 0,7 bei Shift 10) so viel neu, dass sich Mundformen ändern. SeedVR2 bleibt zwar in der Struktur treu, sieht
bei ×2 aus 960×544 aber gemalt aus (bei ×1,5 aus 864×480 schrieb v1.2.3 noch „leicht gemalte Haut“). WAN hält
Gesicht und Mund und ergänzt trotzdem Details. Es ist am langsamsten; wer Zeit sparen will, nimmt Latent 3D und prüft
den Lippensync im Vergleichsvideo.

**SeedVR2 geprüft.** MV 5c erzeugt mit SeedVR2 **bitgleich** dasselbe wie der unveränderte v1.2.3-Graph (Core-
`UNETLoader`, gleiche Szene, ×2): Das Aussehen liegt an SeedVR2 3B bei ×2, nicht am Einbau. Eine Abweichung ist Absicht:
MV 5c nutzt die Farbkorrektur **`lab`** statt `none` wie v1.2.3. Gemessen bei ×2: Farbfehler 3,0 → 1,96,
PSNR 26,3 → 28,9 dB; mit `none` blieben magenta/rote Schlieren. Die gemalte Struktur bleibt auch mit `lab`.

## Wie MV 5c arbeitet

MV 5c ist eine Graph-Expansion wie *Neu rendern* in MV 5b. Für jede freigegebene Szene hängt es die Kette der
gewählten Methode in den laufenden Prompt, mit denselben Nodes und Einstellungen wie im Workflow unter
`Video Upscaling/`. Anfang und Ende sind interne Nodes:

1. **Upscale Source** (`DaWMV2UpscaleSource`) liest den freigegebenen Take aus `scenes/scene_NNNN.mp4`. WAN bekommt
   5 Frames Vorlauf, das sind die letzten Frames der vorigen Szene: Die Szenen setzen einander per Extend fort, also
   sind das die echten Vorgänger (bei Szene 1 wird der erste Frame wiederholt). Aufgefüllt wird auf das Raster der
   Methode (WAN/SeedVR2 `4k+1`, H3 `17k+5`). Dazu kommen der Songausschnitt und das **H3-Conditioning der Szene
   selbst** aus `conditioning/`.
2. **Methode:** SeedVR2 Lanczos → Preprocess → VAE-Encode 1024 → 1 Schritt → Decode 512 → Post (lab).
   WAN Lanczos → WAN-VAE → Low-Noise-Experte + lightx2v, 2 Schritte bei Denoise 0,15, Kacheln 832×480, Fenster 33.
   Latent 3D: H3-AV-Latent → gelerntes 3D-Upscale → 2 FastH3-Schritte (beta, 0,25). Ultimate: MMH3 Ultimate Upscale
   mit gelerntem Upscale, Zeitfenstern 136/17 und Token-Budget 70 000 (linear_quadratic, 4 Schritte, 0,25).
3. **Upscale Save** (`DaWMV2UpscaleSave`) schneidet Vorlauf und Auffüllung ab, speichert unter
   `upscaled/<Methode>_<B>x<H>/`, prüft die Frame-Zahl und legt eine Vorschau mit Originalton an.

- Die **H3-Methoden** rechnen mit der laufenden FastH3-Kette aus MV 0 (inklusive LoRA und Speicherverwaltung für
  hohe Auflösungen) und dem eigenen Szenen-Prompt. Es lädt kein zweites großes Modell.
- **SeedVR2** und **WAN** laden ihre Modelle schreibgeschützt (v1.2.4-Abbildung) über den internen Node
  `DaWMV2UpscaleModels`. Er hält sie nur **schwach** fest: Alle Szenen eines Laufs teilen eine Kopie, solange ComfyUIs
  eigener Cache sie hält. Nach dem Lauf oder mit *Free model and node cache* sind sie weg. Der WAN-Prompt wird einmal
  encodiert, UMT5 danach sofort freigegeben.
- Nach SeedVR2/WAN verlassen deren Modelle den VRAM, damit FastH3 für die nächste Szene wieder vollständig lädt.
- Resume-Schlüssel je Szene: Render-Schlüssel des Takes + Methode + Größe + Einstellungsversion (`plan.json`,
  Feld `upscaled`). Ein neuer Take oder eine andere Methode skaliert neu, alles andere wird übersprungen.
- Der Extend baut immer auf dem **Original** auf, nie auf dem Upscale.
- Fehlt ein Node-Pack oder ein Modell, bricht MV 5c mit einer Liste ab, was fehlt, bevor gerechnet wird.

## Live-Test

R9700, 960×544, Upscale WAN 2.2 → 1920×1088, echtes Frontend in headless Edge, Entscheidungen per Klick auf die Knöpfe
und Reiter im MV-5b-Widget; 19,2-s-Songausschnitt, 3 Szenen, gleiche Prompts und Seeds wie der v1.2.5-Test.
Nachweis: [`h3-music-video-v127-upscale-validation.json`](../performance/rdna4/h3-music-video-v127-upscale-validation.json).

| Schritt | Ergebnis |
|---|---|
| Szene 1 → Neu rendern, neuen Take übernehmen | MV 5c skaliert Take 2 hoch; der verworfene Take 1 liegt in `takes/` und wird nicht hochskaliert |
| Szene 2 → Weiter | erscheint erst zur Prüfung, nachdem der Upscale von Szene 1 fertig ist (14,7 min WAN) |
| Szene 3 → Neu rendern, dann Reiter *Take 1* → übernehmen | MV 5c skaliert den zurückgeholten Take 1 hoch, nicht Take 2 |
| Zuordnung | jeder Upscale weicht vom angenommenen Take um 6,7–8,8 ab (Grauwert-MAE), vom verworfenen um 56–59 |
| Upscale-Zeiten (WAN) | 14,7 / 17,1 / 12,5 min für 152 / 179 / 130 Frames |
| Filme | Original 960×544, Upscale 1920×1088, Vergleich 3840×1088: je 461/461 Frames, alle 801 MP3-Pakete bitidentisch |
| Nähte an den Szenengrenzen | Original 1,08 / 1,06, Upscale 1,20 / 1,27 (Sprung im Verhältnis zur Bewegung davor und danach) |
| Gesamtlauf | ≈ 61 min Rechenzeit für 19 s Song (5 Renderdurchgänge inkl. zwei *Neu rendern*, 3 Upscales, Finale) |

Der Upscale-Film bekommt an den Szenengrenzen etwas mehr Sprung als das Original, bleibt aber deutlich unter dem
Faktor 2, ab dem ein Sprung ins Auge fällt.

## Speicher

Während eines WAN-Upscales liegt FastH3 (22 GB) im RAM und WAN (13,6 GB) im VRAM; auf diesem Windows/ROCm-Treiber zählt
auch der VRAM voll auf das Commit-Limit (v1.2.4). Gemessen im Live-Test: Spitze **95,6 von 97,4 GB Commit** beim
WAN-Decode der 7,5-s-Szene (ComfyUI selbst 42 GB privat), ohne Fehler. Das ist knapp: Für Szenen bis 9 s mit WAN
empfiehlt sich eine größere Auslagerungsdatei (höheres Commit-Limit), oder man wählt H3 Latent 3D bzw. SeedVR2,
die kein zweites großes Modell brauchen. Ein Abbruch verliert nichts: Ein neuer Run überspringt fertige Szenen und
Upscales.

## Grenzen

- Jede Szene wird für sich hochskaliert. Szenengrenzen liegen mitten in einer Einstellung (Extend), dort springen
  feine Details etwas mehr als im Original (Naht 1,20–1,27 statt 1,06–1,08).
- Die H3-Methoden zeichnen Mimik neu; den Lippensync im Vergleichsvideo prüfen.
- Der Upscale läuft im selben Prompt: Die nächste Szene erscheint erst zur Prüfung, wenn der Upscale der vorigen
  fertig ist (bei WAN ≈ 13 min pro 5-s-Szene).
