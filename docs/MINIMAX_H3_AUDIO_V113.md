# MiniMax H3 · Audiountersuchung v1.1.3

Untersuchung vom 6. September 2026 zur Beobachtung: „Der offizielle Template-Workflow erzeugt guten
Ton, unsere REF- und FL-Workflows erzeugen blechernen, artefaktbehafteten Ton; die Stimme klingt
robotisch." Diese Seite hält fest, was **belegt**, was **gemessen** und was **offen** ist.

> **Hörabnahme durchgeführt (Nutzer, 2026-09-06):** „Fix ist definitiv besser, aber immer noch
> eine roboterhafte Stimme im Vergleich zum offiziellen Workflow." Der Fix ist damit als
> Verbesserung bestätigt, das Problem aber **nicht gelöst**. Die Weiterarbeit läuft unter v1.1.4.
>
> Ich selbst habe keinen Hörtest durchgeführt; alle Messwerte unten stammen aus dem tatsächlichen
> Code, den eingebetteten Ausführungsgraphen und objektiven Signalmessungen.

## 1. Vergleichsbasis: die Graphen stammen aus den Dateien selbst

ComfyUI legt den vollständigen ausgeführten Graphen als `prompt`-Metadatum in die MP4. Damit war
die damalige Konfiguration exakt rekonstruierbar — es musste nichts geraten werden.

Extraktion (reproduzierbar):

```
ffmpeg -i <datei>.mp4 -f ffmetadata -      # Schluessel "prompt" = ausgefuehrter API-Graph
```

Vier Läufe aus `L:\ComfyUI\ComfyUI\output\video`:

| Datei | UNET | Turbo-LoRA | Steps | Sampler/Scheduler | SigmaShift | Spectrum | MultiGPU |
|---|---|---|---|---|---|---|---|
| `MiniMax_H3_00003_` (Nutzer: **guter Ton**) | fl2va | **aus** | 20 | res_multistep / simple | keiner (→ 3.0) | nein | nein |
| `MiniMax_H3_00002_` | fl2va | **an** | 8 | res_multistep / simple | keiner (→ 3.0) | nein | nein |
| `..._FL2VA_First_Last_Frame_00001_` (**beanstandet**) | fl2va | an | 8 | **euler / beta** | **12 / 4.0** | **ja** | gpu:0/1/1 |
| `..._Ref2VA_MAXIMUM_All_References_00001_` (**beanstandet**) | ref2va | an | 8 | **euler / beta** | **12 / 4.0** | **ja** | gpu:0/1/1 |

## 2. Der entscheidende Zufallsfund: ein bereits vorhandenes kontrolliertes Paar

`MiniMax_H3_00002_` und `00003_` sind **bis auf einen einzigen `PrimitiveBoolean` identisch**:
gleicher Seed `757358688076805`, byteidentischer Prompt (5 180 Zeichen), gleiche Dauer (13,0 s),
gleiche Modelle und VAEs, gleicher Sampler, kein Spectrum, kein SigmaShift, keine MultiGPU-Knoten.
Der Schalter steuert genau zwei Dinge: Turbo-LoRA ein/aus und Schrittzahl 20 ↔ 8.

Damit ließ sich der am häufigsten geäußerte Verdacht sauber prüfen.

### Messverfahren

Reiner Bandvergleich ist unbrauchbar, sobald sich der Inhalt unterscheidet. Verwendet wird deshalb
der **HF-Abstand**: Rauschboden 4–8 kHz relativ zum Tiefton (< 1 kHz) **derselben** leisen Frames
(leisestes Energieviertel, 2048-Punkt-Hann, Leistungsdichte). Das ist pegelnormiert und damit
robust gegen Lautheits- und Inhaltsunterschiede innerhalb derselben Inhaltsart.

| Lauf | HF-Abstand |
|---|---|
| `00003_` — 20 Schritte, kein Turbo (Nutzer: guter Ton) | **−29,1 dB** |
| `00002_` — 8 Schritte, Turbo-LoRA | **−28,5 dB** |

**Ergebnis: 0,6 dB Unterschied.** Turbo-LoRA und die reduzierte Schrittzahl sind damit als Ursache
des Problems **ausgeschlossen**. Beide bleiben in v1.1.3 unverändert.

Die verbreitete Annahme, die `fl2v`-LoRA sei „nur Video" und lasse deshalb den Audiozweig
unterentrauscht, wurde ebenfalls geprüft und **widerlegt**: Die LoRA patcht 208 Module des
**gemeinsamen** Audio+Video-Trunks (50 DiT-Blöcke × {`attn.qkv_proj`, `attn.out_proj`, `mlp.fc1`,
`mlp.fc2`} plus 2 Token-Refiner-Blöcke).

## 3. Was tatsächlich von der Hersteller-Referenz abweicht

Drei Einstellungen unterscheiden unsere Workflows von der offiziellen Vorlage und von **beiden**
gut klingenden Läufen. Alle drei stammen aus **einem** eigenen Werkzeug,
`tools/integrate_h3_turbo_lora.py`, das sie beim Turbo-Einbau gemeinsam gesetzt hat — die alten
Knotentitel im Code („video 12 / audio **3**", „SAMPLER — **res_multistep**") belegen den
Ursprungszustand.

### 3a · `MiniMaxH3SigmaShift.shift_audio` 4.0 statt 3.0

3.0 ist der Default an drei unabhängigen Stellen des Kerncodes:

- `comfy_extras/nodes_minimax_h3.py:384` — Knoten-Default
- `comfy/supported_models.py:966-969` — `sampling_settings = {"shift": 12.0, "audio_shift": 3.0}`
- `comfy/ldm/minimax/model.py:479` — DiT-Konstruktor

Der Wert ist **nicht** kosmetisch. Video und Audio liegen als ein gepackter Tensor auf **einer**
Sigma-Achse; der Audiostrom wird über `audio_scale = shift_video / shift_audio` darauf
reparametrisiert (`comfy/model_sampling.py:343-347`, `comfy/model_base.py:2149-2165`,
`comfy/ldm/minimax/model.py:36-39`). `shift_audio` bestimmt damit die **gesamte Rauschbahn des
Audiostroms** und den adaLN-Zeitschritt jedes Audio-Tokens in allen 50 Blöcken. 4.0 statt 3.0
ergibt eine andere, in sich konsistente Diskretisierung derselben ODE — also eine **andere
Stimmcharakteristik**, nicht bloß mehr Rauschen. Das deckt sich mit der Beobachtung „robotisch,
falsch" besser als jede reine Rauschmessung.

### 3b · `euler` / `beta` statt `res_multistep` / `simple`

Die offizielle ComfyUI-H3-Vorlage
(`comfyui_workflow_templates/templates/video_minimax_h3_i2v.json`) und beide guten Läufe verwenden
`res_multistep` + `simple`. Geprüft und bestätigt: Beide Sampler machen **gleich viele**
Modellauswertungen; `res_multistep` ist ein Verfahren zweiter Ordnung, `euler` eines erster
Ordnung. Bei 8 Schritten ist das ein realer Genauigkeitsunterschied ohne Mehrkosten.

### 3c · Spectrum war standardmäßig aktiv

Geprüft und bestätigt:

- `SpectrumApplyMiniMaxH3` prognostiziert den **gepackten Video+Audio**-Zustand, nicht nur
  Videomerkmale. Auf einer Prognosestufe entsteht die Audio-Geschwindigkeit **ohne**
  Transformer-Auswertung.
- `audio_blend_weight = 0.0` hält Audio **nicht** exakt. Die Null bedeutet „null spektraler
  Anteil"; die Audiozeilen werden weiterhin ersetzt, dann per zweipunkt-linearer Interpolation.

Upstream (v0.2.24) warnt zudem ausdrücklich vor Wenig-Schritt-Beschleunigungs-LoRAs. Spectrum
bleibt im Graphen, ist aber ab v1.1.3 **auf Bypass** — Beschleunigung wird zum bewussten Opt-in.

## 4. Reproduktion und Wirksamkeitsmessung

Auf einer **isolierten** Bench-Instanz (Port 8190, eigene Ausgabe-/Temp-Verzeichnisse, Produktion
unberührt) wurde der beanstandete Ref2VA-Lauf mit dem exakt rekonstruierten Graphen wiederholt:

| Lauf | HF-Abstand | Rauschanteil > 4 kHz (leise Frames) |
|---|---|---|
| Original `..._Ref2VA_MAXIMUM_...00001_` | +0,7 dB | 30,9 % |
| Reproduktion `ref_exact` (gleicher Graph, gleiche Eingaben) | −0,3 dB | 28,7 % |

**Der Defekt ist deterministisch reproduzierbar.**

Anschließend derselbe Graph mit allen drei zurückgenommenen Einstellungen:

| Lauf | HF-Abstand | Rauschanteil > 4 kHz |
|---|---|---|
| `ref_exact` (Fehlerzustand) | −0,3 dB | 28,7 % |
| `ref_vendor` (3a + 3b + 3c zurückgenommen) | **−2,7 dB** | 22,6 % |

**Verbesserung: 2,4 dB** im kontrollierten Paar (gleiche Eingaben, gleicher Seed).

> **Später relativiert (Abschnitt 8c):** Der HF-Abstand streut allein durch den Seed um ±7 dB.
> Diese 2,4 dB liegen damit innerhalb der Streuung und sind **kein belastbarer Effektnachweis**.
> Der Fix ist durch die Hörabnahme bestätigt, nicht durch diese Zahl.

### Wichtige Einschränkung dieser Zahl

Der Ref2VA-Lauf verwendet ein **Musikstück** als Referenzaudio (`TaylorSwift_Ref_Audio.mp3`) und
erzeugt entsprechend musikähnliches Audio. Die guten Referenzläufe erzeugen **Sprache**. Ein
Rauschboden-Vergleich zwischen Musik und Sprache ist **nicht gültig** — Musik hat in „leisen"
Frames systembedingt viel mehr Breitbandenergie. Belastbar ist ausschließlich der Vergleich
`ref_exact` ↔ `ref_vendor` (2,4 dB), nicht der Abstand zu den Sprachläufen.

Der FL2VA-Fall — der Ihrer Beschreibung der **Stimme** entspricht und denselben Prompt wie die
offizielle Referenz verwendet — konnte nicht mehr gemessen werden: Der Host (48 GB RAM) geriet mit
dem 26-GB-Textencoder neben laufender Nutzerarbeit an das Commit-Limit, die Testinstanz wurde zum
Schutz des Systems beendet.

## 5. Was v1.1.3 ändert

`tools/upgrade_v113.py` nimmt in **6 Workflows** (5 Spectrum-Graphen + Music-Video-Director)
genau die drei Abweichungen zurück:

| | vorher | nachher |
|---|---|---|
| `shift_audio` | 4.0 | **3.0** (Hersteller-Default) |
| Sampler | `euler` | **`res_multistep`** |
| Scheduler | `beta` | **`simple`** |
| Spectrum | aktiv | **Bypass** (Geschwindigkeitsmodus, Opt-in) |
| Turbo-LoRA | aktiv | unverändert aktiv |
| Schrittzahl | 8 | unverändert 8 |

Damit entspricht die Standardkonfiguration exakt der von `MiniMax_H3_00002_` — also dem Lauf, der
mit −28,5 dB so gut misst wie die 20-Schritt-Referenz.

`tools/integrate_h3_turbo_lora.py` wurde mitgeändert, damit ein erneuter Turbo-Einbau die
Abweichungen nicht wieder einspielt; Alttexte in den Hinweisknoten werden mitgeheilt.

### Beschleunigung zurückholen

Spectrum-Knoten im Workflow markieren und Bypass aufheben (Strg+B). Für den vollen alten
Geschwindigkeitsmodus zusätzlich `KSamplerSelect` auf `euler` und `BasicScheduler` auf `beta`
stellen. Der zuverlässige Standardpfad hat Vorrang, die Beschleunigung ist dokumentiert optional.

## 6. Offene Punkte

1. **Hörabnahme erfolgt, Restproblem bestätigt.** Der Fix ist hörbar besser, die Stimme klingt
   aber weiterhin roboterhaft gegenüber der offiziellen Referenz. Weiterarbeit: v1.1.4.
   Der wichtigste noch ungeprüfte Verdacht ist die **8-Schritt-Turbo-Destillation**: Der
   kontrollierte Vergleich `00002_`/`00003_` zeigt einen identischen *Rauschboden* (0,6 dB), sagt
   aber nichts über *Klangfarbe und Prosodie* — genau die Größen, die „roboterhaft" beschreibt.
   `MiniMax_H3_00002_` (Turbo an, 8 Schritte) wurde vom Nutzer nie bewertet.
2. **FL2VA-Fall ungemessen.** Der Stimm-Fall ist der eigentlich relevante und wurde nicht mehr
   verifiziert (Host-Speicher). Vorbereitet und lauffähig: `P0_fl_exact` / `P4_fl_vendor`.
3. **Dominante Ursache des Ref2VA-Rauschbodens unbekannt.** Die drei zurückgenommenen
   Einstellungen erklären 2,4 dB. Nicht isoliert geprüft sind: das Referenzaudio als Conditioning
   (ein Musikstück als Stimmreferenz), das `ref2va`-Modell selbst und die Geräteaufteilung.
4. **Zweiter Seed nicht gefahren.** Die Bestätigung mit einem weiteren Seed steht aus.
5. **Geräteaufteilung:** Bei CLIP auf `gpu:1` lädt der 26-GB-Textencoder auf der 16-GB-Karte nur
   teilweise (gemessen: 10 374 MB geladen, 15 508 MB ausgelagert). Das ist ein
   Performance-Befund, kein belegter Audio-Befund.

## 8. Nacharbeit v1.1.4 (2026-09-06, nach der Hörabnahme)

Die Hörabnahme ergab: hörbar besser, Stimme aber weiterhin roboterhaft. Vier Nachmessungen auf der
isolierten Bench-Instanz — und eine wichtige Korrektur an der Methodik.

### 8a · Turbo-LoRA endgültig entlastet

Der Nutzer hat `MiniMax_H3_00002_` (Turbo, 8 Schritte) gegen `00003_` (kein Turbo, 20 Schritte)
gehört: **beide klingen gut.** Damit ist die Turbo-Destillation auch perzeptiv ausgeschlossen,
obwohl ihr HNR um 1,2 dB niedriger liegt. Ein Turbo-Qualitätsschalter wurde deshalb **nicht**
gebaut — er hätte ein Problem gelöst, das nicht existiert.

### 8b · Geräteaufteilung erzeugt bitidentisches Audio

Kontrollierter Dreiervergleich, identische Eingaben und Seed, 8 s:

| Variante | Audio |
|---|---|
| `M0` offizielle Konfiguration (kein MultiGPU, kein SigmaShift) | Referenz |
| `M1` = M0 + `DaWMultiGPUDeviceControl` (gpu:0/1/1) | **bitidentisch zu M0** |
| `M2` = M1 + `MiniMaxH3SigmaShift(12.0, 3.0)` | **bitidentisch zu M0** |

Geprüft per SHA-256 über die dekodierten PCM-Daten. Die Geräteaufteilung und der SigmaShift-Knoten
mit Hersteller-Werten sind für das Audio **exakte No-ops**.

**Damit ist der Audiopfad unserer Workflows nach v1.1.3 byte-für-byte der offizielle Pfad.** Ein
Pipeline-Defekt existiert an dieser Stelle nicht mehr.

### 8c · Methodische Korrektur: der HF-Abstand ist seed-abhängig

Test des Seitenverhältnisses (Hochformat 480×864 gegen Querformat 864×480, sonst alles gleich),
zwei unabhängige Seeds:

| | Seed A | Seed B |
|---|---|---|
| Hochformat | −26,5 dB | −19,8 dB |
| Querformat | −19,2 dB | −26,5 dB |

Vollständige Umkehr. Der HF-Abstand streut allein durch den Seed um **±7 dB**.

Daraus folgen zwei Dinge:

1. Das Seitenverhältnis ist **nicht** die Ursache.
2. **Die in Abschnitt 4 berichtete Verbesserung von 2,4 dB liegt innerhalb dieser Streuung** und ist
   damit *kein* belastbarer Effektnachweis. Der v1.1.3-Fix bleibt trotzdem richtig — er ist durch
   die Hörabnahme des Nutzers bestätigt und durch die Rücknahme dokumentierter Abweichungen von der
   Hersteller-Referenz begründet, nicht durch diese Zahl.

Einzelmessungen von Rauschkennzahlen über verschiedene Denoising-Trajektorien sind für diese Frage
untauglich. Belastbar sind nur bitidentische Vergleiche (8b) oder Hörabnahmen.

### 8d · Was als Ursache übrig bleibt

Der beanstandete Vergleich ist in vier Punkten unkontrolliert: **anderer Seed**
(271828182845904 gegen 757358688076805), **anderes Referenzbild**, **andere Dauer** (11 s gegen
13 s) und **anderes Seitenverhältnis**. Nur der Prompt ist byteidentisch.

Ungeprüft ist bisher die **Bild-Vorverarbeitung**: Der offizielle Graph reicht `LoadImage` direkt an
`MiniMaxH3ImageToVideo`, unser FL2VA-Workflow schiebt `PixaromaLongestSide` → `PixaromaSwitchWH` →
`PixaromaResizeCrop` dazwischen. H3 ist bild-konditioniert; ein anderer Bildausschnitt ändert die
Konditionierung und damit die erzeugte Stimme. Das ist der nächste konkrete Testpunkt.

### Nächster Test

Unseren **echten** FL2VA-Workflow gegen den offiziellen Graphen laufen lassen, mit identischem
Bild, Seed, Dauer und Zielauflösung. Ist das Ergebnis bitidentisch, liegt kein Workflow-Defekt mehr
vor und die Unterschiede stammen ausschliesslich aus den Eingaben. Weicht es ab, ist die
Vorverarbeitungskette die Ursache.

## 7. Nicht gemacht

Kein Equalizer, kein Denoiser, keine Lautstärkekorrektur, keine Promptänderung. Der Eingriff
besteht ausschließlich darin, dokumentierte Abweichungen von der Hersteller-Referenz
zurückzunehmen.
