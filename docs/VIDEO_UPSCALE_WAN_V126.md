# Video-Upscaling mit WAN 2.2 (WAN 2.1 kompatibel) · v1.2.6

Neuer Workflow in `workflows/Video Upscaling/`: **`WAN22_14B_LowNoise-Video-Upscale.json`**. Er vergrößert fertige
Videos beliebiger Länge mit Lanczos auf die Zielgröße und lässt dann den **Low-Noise-Experten von WAN 2.2 A14B**
(Text-to-Video, fp8) mit der lightx2v-LoRA kurz nachrechnen. Der Low-Noise-Experte ist genau für die letzte, feine
Phase einer Generierung trainiert: Er ergänzt Haut-, Haar-, Stoff- und Fassadendetails, Komposition, Personen und
Bewegung bleiben stehen. Derselbe Graph läuft mit **WAN 2.1 T2V 14B** (gleiche Architektur, gleiches VAE); nur Modell
und LoRA werden getauscht. Rahmen, Bedienung und Ton-Behandlung sind dieselben wie bei den drei Upscale-Workflows aus
v1.2.3 (RODENT-Layout, Blöcke an Schnitten, Freigabe nach Block 1, Pixaroma-Loop, Originalton `-c:a copy`).

## Bedienung

1. **VU 1 · Planer**: Video wählen oder hochladen. Ein fertiges Video aus `output/` ohne Kopieren: vollständigen Pfad
   in `video_path_override`.
2. `scale` (Standard ×1,5) bestimmt die Zielgröße, gerundet auf 32 px (1344×768 → 2016×1152).
3. **PROMPT** beschreibt, was im Video zu sehen ist, und die gewünschte Bildqualität (Englisch). Der Standardtext
   funktioniert für jedes Video.
4. **Run**: Block 1 wird hochskaliert und mit Originalton gezeigt, das Gate *FREIGABE* hält an.
5. **Continue** skaliert alle weiteren Blöcke und schreibt
   `output/video/DaWasteh_VideoUpscale/<Projekt>_wan22_<B>x<H>_<Zeit>.mp4`.

Fertige Blöcke werden bei einem erneuten Lauf übersprungen. Nach Änderungen an Denoise/Schritten
`resume_existing_blocks` ausschalten oder `method_tag` ändern.

## Die Kette

| Stufe | Node | Einstellung |
|---|---|---|
| Block laden | `VU 2 · Block laden` | WAN-Raster `4k+1`, **5 Frames Vorlauf** (neu, siehe unten) |
| Vergrößern | `ResizeImageMaskNode` | Lanczos auf die Zielgröße des Planers |
| Encode | `VAEEncodeTiled` | WAN-2.1-VAE, Kachel 512, **zeitlich ungeteilt** (4096) |
| Modell | `VU · Diffusion-Modell laden (RAM-schonend)` (**neu**) → `LoraLoaderModelOnly` → `ModelSamplingSD3` | WAN 2.2 T2V A14B Low-Noise fp8, lightx2v 4-Step v1.1 (low noise) Stärke 1, Shift 5 |
| Text | `VU · Textencoder laden (RAM-schonend)` (**neu**) → `CLIPTextEncode` | UMT5-XXL fp8, Typ `wan` |
| Kacheln | `VU · Räumliche Kacheln` (**neu**, `DaWVUSpatialTiles`) | 832×480, Überlappung ≥ 128 px, bei jedem Schritt überblendet |
| Zeitfenster | `WanContextWindowsManual` (Core) | 33 Frames, 8 überlappend, `standard_static`, `pyramid` |
| Sampling | `KSampler` | euler, simple, **2 Schritte, Denoise 0,15**, CFG 1 |
| Decode | `VAEDecodeTiled` | Kachel 512, zeitlich ungeteilt |
| Speichern | `VU 3 · Block speichern` | Vorlauf und Auffüllung wieder abschneiden, H.264 CRF 14 |

Das WAN-VAE ist kausal: Eine zeitliche Kachel startet es mitten im Block neu, was als Sprung alle paar Frames sichtbar
würde. Deshalb kacheln Encode und Decode nur räumlich; ein Test sichert `temporal_size` ≥ längster Block + Vorlauf.

## Einstellungen und warum (gemessen)

Messungen auf der R9700 an Ausschnitten der Testszene (1344×768 → 2016×1152; PSNR nach Herunterskalieren auf die
Quelle, Schärfe = Laplace-Varianz, Lanczos-Vergrößerung der Quelle = 38).

| Variante | s pro Schritt¹ | PSNR | Schärfe | Befund |
|---|---|---|---|---|
| ganzes Bild, Denoise 0,30, 4 Schritte | 281² | 16,4 dB | 66 | zeichnet Gesicht, Schildtexte und Leuchtreklame neu (Start-σ 0,69) |
| ganzes Bild, Denoise 0,15, 4 Schritte | 95 | 20,3 dB | 58 | inhaltstreu, Details wie vergrößertes 720p |
| Kacheln 1280×720, Denoise 0,20, 4 Schritte | 73 | 19,8 dB | 63 | |
| Kacheln 832×480, Denoise 0,20, 4 Schritte | **43** | 19,9 dB | 66 | feinere Fassaden, keine sichtbaren Nähte |
| Kacheln 832×480, Denoise 0,15, 4 Schritte | 43 | 21,4 dB | 61 | |
| **Kacheln 832×480, Denoise 0,15, 2 Schritte** | 43 | **21,5 dB** | **63** | **Standard**: wie 4 Schritte, halbe Zeit |
| Kacheln 832×480, Denoise 0,10, 2 Schritte | 43 | 23,9 dB | 55 | am treuesten, weniger neue Details |
| wie Standard, WAN 2.1 T2V 14B | 51 | 27,4 dB | 49 | läuft im selben Graphen; ändert deutlich weniger |

¹ je 33-Frame-Fenster (9 Latent-Frames). ² 2 Fenster im `standard_uniform`-Schema.

**Räumliche Kacheln.** WAN 14B ist auf 480p und 720p trainiert. Im ganzen 2016×1152-Bild (82 000 Tokens pro Fenster)
zeichnet es Details im eigenen Maßstab – das Ergebnis wirkt wie ein vergrößertes 720p-Bild – und die Attention
dominiert die Rechenzeit. `DaWVUSpatialTiles` rechnet stattdessen überlappende Kacheln in nativer Größe und mittelt
deren Vorhersagen bei **jedem** Schritt mit linearen Rampen (MultiDiffusion); so überlebt keine Naht den nächsten
Schritt. Jede Kachel bekommt eigene Positionen (RoPE ab 0), als würde WAN ein Video in Kachelgröße rendern. 832×480
war feiner und 2,2× schneller als das ganze Bild, 1280×720 lag dazwischen. Der Patch sitzt an `apply_model` und
arbeitet deshalb mit den zeitlichen Context-Windows des Cores zusammen; VRAM wird nur für eine Kachel eingeplant, das
Modell lädt vollständig (im ganzen Bild wurde es teilweise ausgelagert).

**Denoise 0,15, 2 Schritte.** Mit Shift 5 startet Denoise 0,30 bei σ 0,69: Gesichter und Schildtexte werden neu
erfunden (wie die 0,45 aus v1.2.3). 0,15 (σ 0,48) hält Komposition, Schilder und Figuren. 2 Schritte (σ 0,48 → 0,29 →
0) lagen in Abweichung und Schärfe gleichauf mit 4 Schritten. Auch bei 0,15 verändert der Low-Noise-Experte kleine,
unnatürliche Details der Quelle: Die leuchtend blauen Iris der Testszene wurden dunkel, Schriftzüge in unscharfen
Leuchtreklamen änderten Buchstaben. Ein beschreibender Prompt (Augenfarbe, Make-up) änderte daran nichts; Denoise
0,10 hält mehr, bringt aber weniger Detail.

**5 Frames Vorlauf (neu in `VU 2`).** WAN zeichnet den Anfang jedes Clips stärker neu: Das erste Latent steht für einen
einzelnen Frame. Gemessen fiel die Abweichung zur Quelle von 24,9 (Frame 0) auf ~17 (Frame 8); ein reiner
VAE-Rundlauf ist flach (3,4) – es ist der Sampler, nicht das VAE. Mit 5 Vorlauf-Frames, die mitgerechnet und von
`VU 3` verworfen werden, sank Frame 0 auf 15,4, der Sprung zu Frame 1 von +3,8 auf +1,0 und der Median über den Clip
von 17,0 auf 14,4. Innerhalb einer Einstellung sind es die echten vorherigen Frames (Bewegungskontext an der
Blockgrenze), an einem harten Schnitt oder am Videoanfang wird der erste Frame wiederholt; der Vorlauf greift nie über
einen Schnitt. H3 und SeedVR2 laufen unverändert ohne Vorlauf (`lead_frames` 0, alte Workflows bleiben gültig).

**Blöcke 7 s (2–10 s), wie SeedVR2/Ultimate in v1.2.3.** Jeder Block wird unabhängig gerechnet. Im Test mit zwei
Blöcken innerhalb einer Einstellung blieb das Gesicht über die Grenze konsistent, aber unscharfe Leuchtschriften im
Hintergrund bekamen in Block 2 andere Buchstaben („INAAG“ → „IHAAS“; Nahtwert +0,57, innerhalb eines Blocks ≈ 0). Die
Szenen der vorhandenen Musikvideos sind im Mittel 7,0 s lang, 70 von 126 länger als 7 s, keine länger als 10 s. Mit
höchstens 10 s bleibt jede solche Szene ein Block, die Grenzen liegen an ihren Schnitten.

## WAN 2.1 und 2.2

| Modell | Diffusion-Modell | LoRA | VAE |
|---|---|---|---|
| **WAN 2.2 A14B (Standard)** | `wan2.2_t2v_low_noise_14B_fp8_scaled` | `wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise` | `wan_2.1_vae` |
| WAN 2.1 T2V 14B | `wan2.1_t2v_14B_fp8_scaled` | `lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16` | `wan_2.1_vae` |

Beide live getestet (gleicher 33-Frame-Ausschnitt, gleiche Kette; WAN 2.1 per direktem API-Lauf). WAN 2.1 blieb viel
näher an der Quelle (PSNR 27,4 statt 21,5 dB, blaue Augen und Schildtexte erhalten), fügte aber weniger Detail hinzu
(Schärfe 49 statt 63). Wer maximale Treue will, nimmt 2.1; wer mehr neue Details will, 2.2. Der High-Noise-Experte von
2.2 wird nicht gebraucht: Er formt die grobe Szene, die beim Upscaling schon feststeht. WAN 2.2 TI2V 5B passt nicht
(anderes VAE, 48 Kanäle).

## Live-Test

Alle Läufe mit der ausgelieferten Datei über das echte Frontend (headless Edge, `app.graphToPrompt`) und Pixaromas
eigenes Submit-Pruning: **Run** (Planung + Block 1, Pause) und **Continue** (Loop + Finale), jeweils nach einem
Neustart von ComfyUI (kalt), R9700 mit VRAM-Guard. Geändert wurden nur `video_path_override`, der Projektname und im
Zwei-Block-Lauf die Blocklängen.

| | Hauptlauf | Zwei Blöcke in einer Einstellung | Speicherlauf |
|---|---|---|---|
| Video | Outro `scene_0000`, 1344×768, 6,33 s | wie Hauptlauf, Blöcke 3/2/4 s | Intro `scene_0004`, 1664×928, 8,5 s |
| Ziel | 2016×1152 | 2016×1152 | 2496×1408 |
| Blöcke | 1 (152 + 5 Vorlauf) | 2 (72 + 80, je 5 Vorlauf aus derselben Einstellung) | 1 (204 + 5 Vorlauf; ein Schnitt bei Frame 73 liegt im Block) |
| Run / Continue | 890 s / 1,8 s | 453 s / 447 s | 1983 s / 3,3 s |
| Sampling | 2 × 296 s (6 Fenster × 9 Kacheln) | 2 × 144 s je Block | 2 × 704 s (8 Fenster × 16 Kacheln) |
| Frames | 152 / 152 | 152 / 152 | 204 / 204 |
| Ton | 298 AAC-Pakete bitidentisch | bitidentisch | 400 AAC-Pakete bitidentisch |
| Commit-Spitze (Limit 105,4 GB) | 77,5 GB | 80,9 GB | 97,2 GB |

Der Hauptlauf war bitidentisch mit einem früheren Lauf derselben Einstellungen mit den Core-Loadern. Rechenzeit bei
2016×1152: rund 2,4 min pro Sekunde Video (ein 90-s-Musikvideo ≈ 3,5 h).

**Sichtprüfung** (1:1-Ausschnitte, Frames 38/76/114): deutlich mehr Detail als Lanczos – Balkongitter, Fensterrahmen,
Efeu, Ziegel, Hautstruktur und einzelne Haarsträhnen; das in der Quelle bewegungsunscharfe Gesicht (Frame 76) wird
klar. Schildtexte bleiben erhalten („INAAG“), Lippen und Iris werden etwas satter bzw. dunkler. Im Zwei-Block-Lauf
bleibt das Gesicht über die Blockgrenze konsistent, unscharfe Leuchtschriften wechseln die Buchstaben (Nahtwert +0,57,
innerhalb eines Blocks ≈ 0; zum Vergleich v1.2.3 Latent 3D bis +1,36). Die Laplace-Varianz taugt hier nicht als
Schärfemaß: Sie zählt bei der Lanczos-Vergrößerung die Blockartefakte der Quelle mit.

Nachweis mit Workflow-, Quell- und Modell-Hashes: `performance/rdna4/video-upscale-wan-v126-validation.json`,
gesichert durch `tests/test_video_upscale_wan_v126.py`.

## Speicher

Auf diesem System rechnet Windows jede VRAM-Allocation und die copy-on-write-Abbildung der safetensors-Dateien auf das
Commit-Limit an (siehe v1.2.4). Mit den Core-Loadern (`UNETLoader`, `CLIPLoader`) stieg der Commit beim Hauptlauf von
39,9 auf 90,7 GB (Limit 105,4 GB): UMT5 +12 GB, Laden des Modells +25 GB (Dateiabbildung + Bildtensoren), Modell auf
die GPU +10 GB, Decode +5 GB. Bei 1664×928 × 1,5 = 2496×1408 stand er schon vor dem Decode bei 93,5 GB; mit dem
Decode wären es ~109 GB gewesen – über dem Limit.

Die beiden neuen Loader `VU · Diffusion-Modell laden (RAM-schonend)` und `VU · Textencoder laden (RAM-schonend)`
bilden die Dateien schreibgeschützt ab (Funktionen aus v1.2.4, `h3_highres.py`) und nehmen dieselben Dateien wie die
Core-Loader. Gemessen: bitidentisches Ergebnis; Commit-Spitze im Hauptlauf 77,5 statt 90,7 GB, im Speicherlauf
(2496×1408, 209 Frames) 97,2 GB bei 34,9 GB Grundlast. Das ist der schwerste gemessene Fall: Wer nebenher ein großes
Programm (z. B. ein lokales LLM) laufen lässt, nimmt bei 1664×928-Quellen `scale` 1,25 oder kürzere Blöcke.

Zwischen WAN-Modellfamilien (2.1 ↔ 2.2) ComfyUI neu starten oder *Unload Models* nutzen: Während der Tests lag einmal
ein zweites 14B-Modell im RAM, der Commit erreichte 101 GB.

## Modelle

| Datei | Quelle | Zielordner |
|---|---|---|
| `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors` (14,3 GB) | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged) | `models/diffusion_models/WAN/` |
| `wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors` (1,2 GB) | ebenda | `models/loras/WAN/` |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (6,7 GB) | ebenda | `models/text_encoders/UMT5/` |
| `wan_2.1_vae.safetensors` (254 MB) | ebenda | `models/vae/WAN/` |

Revision und SHA-256 stehen in `tools/workflow_templates/v126/models.json`. Für WAN 2.1:
`wan2.1_t2v_14B_fp8_scaled.safetensors` aus
[Comfy-Org/Wan_2.1_ComfyUI_repackaged](https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged) und die lightx2v-T2V-LoRA
aus [Kijai/WanVideo_comfy](https://huggingface.co/Kijai/WanVideo_comfy) (`Lightx2v/`). Alle Nodes sind im ComfyUI-Core
bzw. im DaWasteh-Bundle enthalten.

## Grenzen

- WAN 14B ist bei 2K teuer: rund 2,4 min pro Sekunde Video bei 2016×1152 (ein 90-s-Musikvideo ≈ 3,5 h), rund 3,9 min
  pro Sekunde bei 2496×1408. Für lange Videos über Nacht rechnen oder `scale` senken.
- Einstellungen über 10 s werden geteilt. Der Vorlauf gibt Bewegungskontext, trotzdem können neu gezeichnete Details
  an der Blockgrenze wechseln – am deutlichsten unscharfe Schrift (siehe oben). Wer das vermeiden will, nimmt Denoise
  0,10 oder SeedVR2.
- WAN „korrigiert“ unnatürliche Details der Quelle (leuchtende Iris, verschwommene Schrift). Wer das nicht will, nimmt
  Denoise 0,10, WAN 2.1 oder SeedVR2 aus v1.2.3.
- Mundformen werden geglättet: Im Speicherlauf blieb Öffnen und Schließen synchron zur Quelle, ein schiefer Sprechmund
  wurde aber zu einem symmetrischen Lächeln. Für lippensync-kritische Nahaufnahmen Denoise 0,10 oder WAN 2.1.
