# Dauer in Sekunden und optionale Zweige · v1.1.5

Setzt §5 und §6 des Auftrags `COMFYUI_v1.1.3_Arbeitsauftrag.md` um.

## 1 · Optionale Zweige (§6)

### Der belegte Fehler

Gemessen am 6. September 2026 gegen die Prompt-Validierung von ComfyUI 0.34.0:

| Fall | Ergebnis |
|---|---|
| **A** Loader verbunden, Datei fehlt | **HTTP 400** — `Custom validation failed for node \| image - Invalid image file` |
| **B** Loader stummgeschaltet (nicht im Prompt) | HTTP 200 |
| **C** Loader im Prompt, aber unverbunden | HTTP 200 — unverbundene Knoten werden nicht geprüft |

Der Workflow `MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs` lieferte **13 aktive
Loader** aus, die auf Platzhalter (`REFERENCE_PICTURE_03.png` …) zeigen — Dateien, die es auf
keiner Installation gibt. Das ist Fall A: **der Workflow scheiterte ausgeliefert an der
Validierung, bevor überhaupt etwas gerechnet wurde.**

### Die Lösung: Mute, nicht Bypass

Die Platzhalter-Loader und die Knoten, die ausschließlich sie weiterverarbeiten, stehen jetzt auf
**Mute** (`mode = 2`).

| | Wirkung | Für optionale Eingänge |
|---|---|---|
| **Mute** | Knoten fällt aus dem Prompt | **richtig** — der optionale Eingang bleibt unbelegt |
| **Bypass** | Knoten wird durchgereicht | falsch — ein Loader hat keinen Eingang zum Durchreichen, es entsteht ein toter Link |

Vor jedem Stummschalten prüft die Migration, dass **jede** Verbindung, die den Zweig verlässt, in
einem als optional deklarierten Eingang endet (litegraph `shape == 7`). Ist das nicht so, wird der
Zweig **nicht** angefasst.

Genau das trat bei zwei Workflows ein: In `..._Picture_and_Video_to_Video_LOCAL` und
`..._RefImage_RefVideo_to_Video_Audio_AutoLength` speist das Referenzvideo Pflichteingänge
(`PixaromaSwitch.input_1` bzw. `length` und `duration`). Dort gibt es keinen gültigen Ersatzpfad —
diese Workflows brauchen die Datei wirklich. Das steht im Marker
(`extra.dawasteh_optional_branches.mechanism = "none"` mit den betroffenen Verbindungen), statt den
Graphen zu brechen.

### Bedienung

Abgeschaltete Zweige tragen die Beschriftung `OPTIONAL · <Zweig> · AUS · Strg+M schaltet ein · …`.

1. Knoten des Zweigs markieren (oder alle mit derselben Beschriftung)
2. **Strg+M** — der Zweig ist aktiv
3. Datei im Loader auswählen

Ausschalten geht genauso. Der Marker `extra.dawasteh_optional_branches.branches` listet zu jedem
Zweig die zugehörigen Knoten-IDs.

Eigene Gruppen als Schalter sind nicht möglich: Das RODENT-Layout erzeugt die Gruppen
deterministisch (feste Stage-Titel `R1`/`O1`/`D1`/`E1`/`N1`/`T1`, eine Gruppe je Knoten,
überlappungsfrei). Knotentitel sind im Canvas genauso sichtbar und kollidieren nicht damit.

## 2 · Dauer in Sekunden (§5)

### Verifizierte Modellgrenzen

Die Rasterwerte des Sekundenvertrags wurden gegen die Node-Schemata der installierten
ComfyUI-Version geprüft — keine universelle Rundungsformel, sondern je Modell die dort deklarierte
Schrittweite:

| Node | `step` | Raster | fps im Workflow |
|---|---|---|---|
| `EmptyLTXVLatentVideo` | 8 | 8n+1 | 25 |
| `Wan22FunControlToVideo` | 4 | 4n+1 | 24 |
| `Kandinsky5ImageToVideo` | 4 | 4n+1 | 24 |
| `Wan22ImageToVideoLatent` | 4 | 4n+1 | 24 |
| `WanImageToVideo` | 4 | 4n+1 | 16 |
| `WanSCAILToVideo` | 4 | 4n+1 | 16 |
| `MiniMaxH3ImageToVideo` | 17 | 17k+5 | 24 |

Die Formel im Graphen lautet `max(<min>, round((a * <fps> - 1) / <raster>) * <raster> + 1)` und
trifft damit exakt das jeweilige Gitter. Für MiniMax H3 gilt die abweichende Form
`max(5, round(a*24)) + (5 - (max(5, round(a*24)) % 17)) % 17`, identisch zu `align_frame_count`
in `comfy_extras/nodes_minimax_h3.py`.

### Gewünscht → berechnet → tatsächlich

Der Marker `extra.dawasteh_duration_seconds` trägt jetzt `minimum_frames`, eine Rundungsregel und
eine `preview`-Tabelle mit drei Stützstellen: Minimum, Standardwert und ein nicht ganzzahliger
Wert. Beispiele:

| Workflow | gewünscht | Frames | tatsächlich |
|---|---|---|---|
| LTX 2.3 (25 fps, 8n+1) | 4,0 s | 97 | **3,84 s** |
| LTX 2.3 | 4,37 s | 113 | 4,48 s |
| WAN 2.2 5B (24 fps, 4n+1) | 10,0 s | 241 | 10,0 s |
| WAN 2.2 14B (16 fps, 4n+1) | 5,37 s | 85 | 5,25 s |
| SCAIL2 (16 fps, 4n+1) | 0,25 s | 5 | 0,25 s |

Nicht darstellbare Dauern rasten auf das nächstgelegene gültige Gitter ein — sie werden nicht
stillschweigend falsch, sondern stehen mit dem tatsächlichen Wert im Marker.

### Betriebsarten

| Modus | Anzahl | Bedeutung |
|---|---|---|
| `native-seconds` | 31 | Das Modell nimmt Sekunden direkt entgegen |
| `explicit-seconds-to-model-valid-frames` | 12 | Sekunden → gültige Frame-Anzahl über die geprüfte Formel |
| `source-media-duration` | 9 | Länge stammt aus Referenz-Audio/-Video; kein Sekundenfeld, damit keine Scheinkontrolle entsteht |
| `explicit-seconds-dynamic-source-fps` | 1 | Sekunden mit der FPS des Quellvideos (Wan Animate 2) |

Bei `source-media-duration` hat die Quelldatei Vorrang; ein zusätzliches Sekundenfeld wäre
irreführend und wurde bewusst nicht eingebaut.
