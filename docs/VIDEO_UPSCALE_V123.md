# Video-Upscaling · drei Methoden aus Nerdy Rodents Video · v1.2.3

Neue Kategorie `workflows/Video Upscaling/` mit den drei Upscale-Methoden aus Nerdy Rodents Video
[„MiniMax H3 Ultimate Upscaling“](https://www.youtube.com/watch?v=fjWeg8so8y0), jeweils als eigener flacher
RODENT-Workflow für **fertige Videos beliebiger Länge**:

| Workflow | Methode | Charakter (Rodent + eigene Messung) |
|---|---|---|
| `MiniMax_H3-Ultimate-Upscale-FastH3.json` | PlagueKind **MMH3 Ultimate Upscale**: zweiter FastH3-Durchgang in Zielgröße, zeitliche Chunks mit Anker, bei Bedarf räumliche Kacheln | die meisten neuen Details, verändert das Bild am stärksten |
| `MiniMax_H3-Latent-Upscaler-3D-FastH3.json` | LBH-123-AI **Latent Upscaler 3D** (gelerntes Modell) + 2 FastH3-Schritte, Original-Audio-Latent | nah am Original, am schnellsten |
| `SeedVR2_3B_INT8-Video-Upscale.json` | **SeedVR2 3B INT8** (ComfyUI-Core), ein Schritt | schärfer, praktisch keine neuen Details; gut als letzter Durchgang |

## Bedienung (alle drei gleich)

1. **VU 1 · Planer**: Video wählen oder hochladen (Unterordner in `input/` erscheinen). Ein fertiges Video aus
   `output/` ohne Kopieren: vollständigen Pfad in `video_path_override`.
2. `scale` (Standard ×1,5) bestimmt die Zielgröße, gerundet auf 32 px (864×480 → 1280×704).
3. Nur H3-Methoden: **PROMPT** beschreibt, was im Video zu sehen ist (Englisch, MiniMax-Format). Der Qwen3-VL-Encoder
   läuft einmal, das Ergebnis wird unter `output/DaWasteh_VideoUpscale/_conditioning/` zwischengespeichert.
4. **Run**: Block 1 wird hochskaliert und mit Originalton gezeigt, das Gate *FREIGABE* hält an.
5. **Continue** skaliert alle weiteren Blöcke (Pixaroma-Loop) und schreibt
   `output/video/DaWasteh_VideoUpscale/<Projekt>_<Methode>_<B>x<H>_<Zeit>.mp4`. Die Tonspur der Quelle wird
   unverändert übernommen (`-c:a copy`, MKV bei Codecs, die MP4 nicht trägt).

Fertige Blöcke werden bei einem erneuten Lauf übersprungen (auch nach Absturz oder Abbruch). Nach Änderungen an
Denoise/Schritten `resume_existing_blocks` ausschalten oder `method_tag` ändern.

## Der gemeinsame Rahmen

| Node | Aufgabe |
|---|---|
| `VU 1 · Planer` | 24-fps-Arbeitskopie falls nötig, Schnitterkennung, Blockplan, Zielgröße |
| `VU 2 · Block laden` | Frames des Blocks, aufgefüllt auf das Raster der Methode (H3 `17k+5`, SeedVR2 `4k+1`) mit dem letzten Frame, dazu der passende Tonausschnitt (48 kHz) |
| `Video + Originalton → H3-AV-Latent` | nur H3: Video-VAE und Audio-VAE, Audio-Latent aus dem echten Ton |
| Methode | siehe oben |
| `VU 3 · Block speichern` | Auffüllung wieder abschneiden, H.264 CRF 14, Vorschau mit Originalton |
| `VU 4 · Hochskaliertes Video` | Blöcke ohne Neukodierung verbinden, Original-Tonspur darunter |

**Warum Blöcke:** Ein 90-s-Video bei 1280×704 wäre als ein IMAGE-Tensor ~22 GB groß, und H3 kann nur ~15 s am Stück.
Blöcke machen jede Länge möglich und halten den Speicher konstant.

**Blockgrenzen an harten Schnitten:** Jeder Block wird unabhängig neu berechnet. Mitten in einer Einstellung kann das
als kleiner Sprung sichtbar werden, an einem Schnitt nicht. Der Planer misst die Grauwert-Änderung zwischen
aufeinanderfolgenden Frames (Vorschau 128×72 px). Ein Schnitt ist eine Änderung über `cut_threshold` (18) **und** über
dem 2,5-Fachen des Medians der ±12 Nachbarn – eine feste Schwelle allein hält schnelle Bewegung für Schnitte. Eine
dynamische Programmierung wählt die Grenzen: Schnitte stark bevorzugt, sonst ruhige Frames, Blocklängen zwischen
Minimum und Maximum, nahe am Ziel.

## Einstellungen und warum

**Gelerntes Upscale-Modell auch in Ultimate.** Rodent vergrößert im Ultimate-Workflow das Latent bicubisch
(`MMH3 Latent Upscale Params`). Auf dem fertigen Testvideo blieb dieses Latent bei Denoise 0,25 blockig; FastH3 machte
aus den Blöcken erfundene Objekte: eine Brille und Leuchtlinien im Gesicht, eine Kappe, ein Logo-Schild statt des
Monds, Glitch-Linien über einem Close-up, pixelige Wolken. Derselbe Block mit `MMH3 Latent Upscale with Model Params`
(gleiches Pack, lädt das LBH-Modell) war sauber und behielt die neuen Details. Das Modell muss dafür **direkt** in
`models/latent_upscale_models/` liegen: PlagueKinds Node sucht nicht in Unterordnern.

**Denoise 0,25 statt Rodents 0,45 / 0,4.** FastH3 läuft mit Sigma-Shift 10. Damit beginnt
`linear_quadratic`, 4 Schritte, Denoise 0,45 bei Sigma **0,975** – praktisch reines Rauschen. Rodent wendet es auf
Latents an, die er gerade mit demselben Prompt erzeugt hat; bei einem fertigen, fremden Video erfand es im Test eine
völlig andere Szene. Denoise 0,25 startet bei 0,725 (Ultimate) bzw. 0,683 (beta, 2 Schritte, Latent 3D) und behält
Komposition, Person und Bewegung.

| Methode | Blöcke (Ziel / max) | Sampling | Sonstiges |
|---|---|---|---|
| Ultimate | 7 s / 10 s | euler, linear_quadratic, 4 Schritte, Denoise 0,25, CFG 1 | Latent-Upscale mit dem gelernten 3D-Modell (`MMH3 Latent Upscale with Model Params`); zeitliche Chunks 136 / Überlappung 17 / Anker 1,0; räumlich auto (Kachel 864×480, Überlappung 128, Fade 32, Token-Budget 70000) wie im Video |
| Latent 3D | 4 s / **4,45 s** | euler, beta, 2 Schritte, Denoise 0,25, CFG 1 | Zielmaße aus dem Planer, align 32, zeitliches Chunking, force_unload, `rocm`, bf16 |
| SeedVR2 | 7 s / 10 s | 1 Schritt, euler, simple, Denoise 1 | Lanczos auf Zielmaß; VAE-Encode Kachel 1024, Decode Kachel **512**; Chunk-Überlappung 2, auto |

- **Latent 3D höchstens 4,45 s (107 Frames = 17·6+5):** 108 Frames werden auf 124 aufgefüllt, FastH3 lädt bei
  1280×704 dann nur teilweise (gemessen 27 statt 12 s/Schritt), und 124 Frames ergeben eine ungerade Latent-Länge.
- **SeedVR2-Kacheln:** Encode 1024 statt 512: 94 statt 152 s pro Block. Beim Decode sind 512 und 640 gleich schnell
  (Block 3, 167 Frames: 226 bzw. 224 s gesamt); 768 ist etwas schneller, fordert aber 8,65 GiB am Stück an und lief im
  ersten Komplettlauf nach zwei Blöcken in den VRAM-Guard (10 GiB reserviert, aber fragmentiert). Zeitlich 32 statt
  64 Frames war deutlich langsamer (309 s).
- **Alles auf `gpu:0`:** MODEL, CLIP und VAE stehen in der zentralen GPU-Steuerung auf der R9700
  (siehe v1.2.2: das H3-Video-VAE-Encoding passt neben den Modellen nicht auf die RX 9070 XT).

## Live-Test

Alle drei ausgelieferten Workflows liefen über das echte Frontend (headless Edge, `app.graphToPrompt`) und
Pixaromas eigenes Submit-Pruning: **Run** (Planung + Block 1, Pause) und **Continue** (Loop + Finale). Testvideo war
das 90-s-Musikvideo aus dem v1.2.2-Test (864×480, 24 fps, MP3), Ziel 1280×704, R9700 mit VRAM-Guard.

| | Latent 3D | Ultimate | SeedVR2 |
|---|---|---|---|
| Blöcke (davon an Schnitt) | 22 (7) | 13 (7) | 13 (7) |
| Block 1 inkl. Planung (Run) | 95 s | 259 s | 237 s |
| Loop-Block (Median) | 129 s (~4,4 s Video) | 222 s (~7 s) | 223 s (~7 s) |
| Gesamt für 90 s | **45 min** | ≈ 46 min¹ | 49 min |
| Frames | 2160 / 2160 | 2160 / 2160 | 2160 / 2160 |
| Audio (3751 MP3-Pakete) | bitidentisch | bitidentisch | bitidentisch |
| PSNR zur Quelle (Median, nach Runterskalieren) | 20,1 dB | 19,8 dB | 25,5 dB |
| Schärfe (Laplace-Varianz, Lanczos = 73) | 178 | 167 | 344 |
| Nahtwert innerhalb einer Einstellung (Median / Max)² | +0,26 / +1,36 | +0,37 / +0,80 | −0,09 / −0,05 |

¹ Windows Update startete den PC während Continue nach 9 von 13 Blöcken neu. Nach dem Neustart: Run (Block 1 in
0,2 s übersprungen) und Continue rechneten die Blöcke 10–13 und das Finale; die fertigen Blöcke wurden
wiederverwendet. Die Gesamtzeit ist aus den Blockzeiten hochgerechnet.
² Bildsprung an der Blockgrenze relativ zur Bewegung davor/danach, minus derselbe Wert im Original. 0 = unsichtbar.

**Sichtprüfung** (1:1-Ausschnitte, Frames 60/700/1500/2050): Latent 3D ist originalgetreu und sichtbar schärfer
(Haut, Zähne, Haare), nichts erfunden. SeedVR2 ist am originalgetreuesten mit den schärfsten Kanten, Haut wirkt leicht
gemalt, neue Details gibt es kaum. Ultimate liefert die meisten neuen Details (Wolken, Wimpern, Fassaden), interpretiert
aber frei: Schildtexte ändern sich, der Mond sitzt plötzlich auf einem Turm, der Bildausschnitt verschiebt sich leicht.

**Im ersten Komplettlauf gefunden und behoben:**

- *Finalize* meldete „Blocks not rendered yet“, obwohl alle Blöcke gespeichert waren: Der Render-Schlüssel hashte
  den ganzen Block-Eintrag, den *Block speichern* danach erweitert. Jetzt zählen nur die geplanten Felder
  (Regressionstest). Resume ist seitdem zweimal live bestätigt, darunter nach dem Update-Neustart.
- SeedVR2 lief mit Decode-Kachel 768 im dritten Block in den VRAM-Guard, siehe oben.
- Ultimate mit bicubischem Latent-Upscale lieferte erfundene Objekte, siehe oben.

Nachweis mit Workflow-, Quell- und Modell-Hashes: `performance/rdna4/video-upscale-v123-validation.json`, gesichert
durch `tests/test_video_upscale_v123.py`.

## Modelle und Node-Packs

| Datei | Quelle | Zielordner |
|---|---|---|
| `minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors` (690,6 MB) | [LBH-123-AI/Minimax_h3_latent_Upscaler](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler) | `models/latent_upscale_models/` (direkt, ohne Unterordner) |
| `seedvr2_3b_int8_convrot.safetensors` (3,46 GB) | [Comfy-Org/SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2) | `models/diffusion_models/SeedVR2/` |
| `seedvr2_ema_vae_fp16.safetensors` (501 MB) | [Comfy-Org/SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2) | `models/vae/SeedVR2/` |
| FastH3, Qwen3-VL-Encoder, H3-Video-/Audio-VAE | wie v1.2.2 | `models/.../MiniMax H3/` |

Revisionen und SHA-256 stehen in `tools/workflow_templates/v123/models.json`. Die Node-Packs
[Comfyui-PlagueKind-Nodes](https://github.com/PlagueKind/Comfyui-PlagueKind-Nodes) und
[Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) pflegt der
Bundle-Updater jetzt wie Pixaroma per Git mit; keines bringt zusätzliche Python-Abhängigkeiten mit.

## Grenzen

- Blöcke innerhalb einer Einstellung (ohne Schnitt) werden unabhängig neu berechnet. Bei den H3-Methoden können dort
  kleine Details wechseln; am deutlichsten im Test bei Latent 3D in einer Totalen (Strümpfe/Tattoos und Haarsträhnen
  der Sängerin springen). SeedVR2 zeigt keine solchen Sprünge. Längere Blöcke helfen nur bis zur VRAM-Grenze. Wer
  keine Sprünge möchte, nimmt SeedVR2.
- Die H3-Methoden sind auf 24 fps ausgelegt; andere Bildraten werden in eine 24-fps-Arbeitskopie umgerechnet.
- Rodent kombiniert gern Ultimate oder Latent 3D mit einem SeedVR2-Durchgang danach. Das geht, indem man das fertige
  Video über `video_path_override` in den SeedVR2-Workflow gibt (`scale` z. B. 1,25).
