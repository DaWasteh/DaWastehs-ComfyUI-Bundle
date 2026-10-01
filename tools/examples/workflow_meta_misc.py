"""German titles and summaries: 3D, game development, pose & depth, prompt enhancers/tools, Pixaroma demos, Live Avatar,
LoRA training, NSFW and templates."""
from __future__ import annotations

from workflow_meta import m

G = "Game Development/"
m("Image to 3D-Mesh/Hunyuan3D_v2_1-Image-to-3D-Mesh.json", "Hunyuan3D 2.1 (FP16) · Bild → 3D-Mesh",
  "Ein freigestelltes Objekt oder eine Figur wird zum Mesh (GLB, untexturiert).", ["Bild"], ["3D-Modell"])
m("Image to 3D-Mesh/Mira_Scene-Image-to-3D-Scene.json", "Mira-Scene + TRELLIS.2 (INT8) · Foto → 3D-Szene",
  "SAM 3.1 findet die genannten Objekte, MoGe-2 schätzt die Tiefe, Mira platziert je Objekt ein TRELLIS.2-Mesh mit "
  "PBR-Textur – Ergebnis ist eine bearbeitbare GLB-Szene.", ["Bild", "Text"], ["3D-Szene"])
m("Image to 3D-Mesh/Mira_Scene-Layout-Preview.json", "Mira-Scene · Foto → 3D-Layout (Vorschau)",
  "Schnelle Vorschau: Miras Voxelformen statt TRELLIS-Meshes, um Objektliste und Lage zu prüfen.", ["Bild", "Text"],
  ["3D-Szene"])
m(G + "FLUX2_Klein_4B-PS1-Texture-Concept.json", "FLUX.2 Klein 4B · Text → PS1-Textur",
  "Textur-Konzept in 1024 px, dann Flächen-Verkleinerung auf 128 px und Nearest-Vorschau im Retro-Look.", ["Text"],
  ["Bild"])
m(G + "Hunyuan3D_v2_1-Low-Poly-Static-Mesh-for-Godot.json", "Hunyuan3D 2.1 (FP16) · Bild → Low-Poly-Meshes für Godot",
  "Ein Mesh in vier Detailstufen (5000 bis 600 Dreiecke) mit UV-Abwicklung, fertig für Godot.", ["Bild"], ["3D-Modell"])
m(G + "Pixal3D_INT8-Buildings-and-Environment-PBR-for-Godot.json", "Pixal3D (INT8) · Gebäude → PBR-Mesh für Godot",
  "Pixal3D mit TRELLIS.2-VAEs: Form, PBR-Texturen (Farbe, Metall, Rauheit, Normal, AO) und 12.000-Dreiecke-Budget.",
  ["Bild"], ["3D-Modell"])
m(G + "Pixal3D_INT8-Humanoids-and-Animals-PBR-for-Godot.json", "Pixal3D (INT8) · Figur/Tier → PBR-Mesh für Godot",
  "Wie die Gebäude-Variante, mit 2048-px-Texturen und 24.000 Dreiecken für Figuren.", ["Bild"], ["3D-Modell"])
m(G + "Pixal3D_INT8-MultiView-PBR-Collision.json", "Pixal3D MultiView (INT8) · vier Ansichten → PBR-Mesh + Kollision",
  "Vorne/links/hinten/rechts auf schwarzem Grund ergeben ein genaueres Mesh plus separates Kollisions-Mesh für Godot.",
  ["Bilder"], ["3D-Modell"],
  note="Die vier Eingaben sind kalibrierte Blender-Renders (Kamera-Rig des Nodes: 90° Abstand, FOV 20°, gleiche Skala). "
       "Erfundene Mehransichten aus einem Bildmodell passen nicht zu diesem Rig.")
m(G + "Pixal3D_INT8-PBR-Collision.json", "Pixal3D (INT8) · Bild → PBR-Mesh + Kollision",
  "Sichtmesh mit PBR-Textur und ein vereinfachtes Kollisions-Mesh (CPU) für Godot 4.", ["Bild"], ["3D-Modell"])
m(G + "Pixal3D_INT8-Shape-Collision.json", "Pixal3D (INT8) · Bild → Form + Kollision",
  "Nur die Form (ohne Textur) plus Kollisions-Mesh – schneller für Blockouts.", ["Bild"], ["3D-Modell"])
m(G + "TRELLIS2_INT8-PBR-Collision.json", "TRELLIS.2 (INT8) · Bild → PBR-Mesh + Kollision",
  "TRELLIS.2 mit DINOv3: Mesh mit PBR-Texturen und separatem Kollisions-Mesh.", ["Bild"], ["3D-Modell"])
m(G + "TRELLIS2_INT8-Shape-Collision.json", "TRELLIS.2 (INT8) · Bild → Form + Kollision",
  "Nur die Form plus Kollisions-Mesh.", ["Bild"], ["3D-Modell"])

m("Pose & Depth/DepthAnything3-Depth-from-Image.json", "Depth Anything 3 Large (FP32) · Bild → Tiefenkarte",
  "Tiefenkarte als 8- und 16-Bit-PNG (für ControlNet, 3D oder Displacement) plus eingefärbte Kontrolle.", ["Bild"],
  ["Tiefenkarte"])
m("Pose & Depth/DepthAnything3-Depth-from-Video.json", "Depth Anything 3 Large (FP32) · Video → Tiefenvideo",
  "Tiefe für jedes Frame, als MP4 mit Originalton und -fps.", ["Video"], ["Video"])
m("Pose & Depth/SDPose-Pose-from-Image.json", "SDPose WholeBody (FP16) · Bild → Pose",
  "Ganzkörper-Keypoints (Körper, Hände, Gesicht) als Pose-Karte und OpenPose-JSON.", ["Bild"], ["Pose"])
m("Pose & Depth/SDPose-Pose-from-Video.json", "SDPose WholeBody (FP16) · Video → Pose-Video",
  "Pose für jedes Frame – z. B. als Steuervideo für WAN Fun Control oder SCAIL.", ["Video"], ["Video"])

P = "Prompt Enhancer/"
m(P + "LLM_Qwen3_8_27B-Image-Prompt-Enhancer.json", "Qwen3.8 27B (IQ4_XS) · Entwurf → fertiger Bild-Prompt",
  "Grober Entwurf (Deutsch oder Englisch) → ausformulierter Prompt für Fließtext-, Schrift-, Tag- oder Edit-Modelle; "
  "läuft über llama.cpp auf der RX 9070 XT.", ["Text"], ["Prompt"])
m(P + "LLM_General-Prompt-Enhancer.json", "Gemma 4 e4B (FP8) · Idee → Prompt",
  "Allgemeiner Prompt-Enhancer für Bild- und Videomodelle.", ["Text"], ["Prompt"])
m(P + "LLM_Gemma4_e4b-Audio-to-Text.json", "Gemma 4 e4B (FP8) · Sprache → Text",
  "Transkribiert eine Aufnahme wortgetreu.", ["Audio"], ["Text"])
m(P + "LLM_Gemma4_e4b-Image-to-Prompt.json", "Gemma 4 e4B (FP8) · Bild → Prompt",
  "Beschreibt ein Bild als Prompt zum Nachbauen.", ["Bild"], ["Prompt"])
m(P + "LLM_Gemma4_e4b-Video-to-Description.json", "Gemma 4 e4B (FP8) · Video → Beschreibung",
  "Beschreibt, was im Video passiert.", ["Video"], ["Text"])
m(P + "LLM_Gemma4_e4b-Video-to-Prompt.json", "Gemma 4 e4B (FP8) · Video → Prompt",
  "Formuliert ein Video als Prompt für Videomodelle.", ["Video"], ["Prompt"])
m(P + "LLM_Qwen3_5_4B-Image-to-Prompt.json", "Qwen3.5 4B (BF16) · Bild → Prompt", "Sehr ausführliche Bildbeschreibung "
  "als Prompt.", ["Bild"], ["Prompt"])
m(P + "LLM_Qwen3_5_4B-Text-to-Prompt.json", "Qwen3.5 4B (BF16) · Idee → Prompt", "Kurze Idee → detaillierter Prompt.",
  ["Text"], ["Prompt"])
m(P + "MiniMax_H3_Base_FL2VA-Official-Guide-Prompt-Enhancer.json", "Qwen3.5 4B · Idee → MiniMax-H3-Prompt (FL2VA)",
  "Schreibt Prompts nach dem offiziellen H3-Guide für Base- und First/Last-Frame-Videos.", ["Text"], ["Prompt"])
m(P + "MiniMax_H3_Ref2VA-Official-Guide-Prompt-Enhancer.json", "Qwen3.5 4B · Idee → MiniMax-H3-Prompt (Ref2VA)",
  "Schreibt Ref2VA-Prompts mit <Picture n>/<Video n>/<Audio n>-Verweisen.", ["Text"], ["Prompt"])
m(P + "MiniMax_Music3-Official-Skill-Caption-Enhancer.json", "Qwen3.5 4B · Musikidee → MiniMax-Music-3-Caption",
  "Strukturierte Caption nach dem offiziellen Music-3-Skill (Genre, Tempo, Tonart, Instrumente, Stimmung).", ["Text"],
  ["Prompt"])
m(P + "Qwen3VL_8b_fp8_scaled-Krea2-Prompt-Enhancer.json", "Qwen3-VL 8B (FP8) · Idee → Krea-2-Prompt",
  "Prompt-Enhancer mit dem Text-Encoder-LLM von Krea 2.", ["Text"], ["Prompt"])
m(P + "Ideogram4_Qwen3_5-Auto-Prompt-to-Image.json", "Ideogram 4 (FP8) + Qwen3.5 4B · Idee → JSON → Bild",
  "Qwen3.5 macht aus einer deutschen Bildidee das strukturierte Ideogram-JSON, Ideogram 4 rendert das Bild.",
  ["Text"], ["Prompt", "Bild"])

PT = "Prompt Tools/"
m(PT + "Ideogram4_Qwen3_5-Field-Text-Builder.json", "Qwen3.5 4B · Idee → Ideogram-Felder",
  "Füllt die Felder des Ideogram-Prompt-Builders aus einer Idee (optional mit Skizze).", ["Text"], ["Prompt"])
m(PT + "Ideogram4_Qwen3_5-JSON-Prompt-Builder.json", "Qwen3.5 4B · Idee → Ideogram-JSON",
  "Erzeugt das komplette Ideogram-4-JSON aus einer Idee.", ["Text"], ["Prompt"])
m(PT + "LLM_Qwen3_4B-Text-Generation.json", "Qwen3 4B (BF16) · Text → Text", "Einfache Textgenerierung mit Qwen3 4B.",
  ["Text"], ["Text"])
m(PT + "LLM_Qwen3_5_4B_abliterated-Text-Generation.json", "Qwen3.5 4B abliterated (BF16) · Bild → Beschreibung",
  "Bildbeschreibung mit der abliterated Qwen3.5-Variante (der alte Name sagte Text-Generierung, es ist Bild → Text).",
  ["Bild"], ["Text"])
for _name, _title, _sum, _io in [
    ("Pixaroma-Change-Node-Color", "Pixaroma · Knotenfarben", "Zeigt alle Pixaroma-Farbvorgaben für Knoten.", ([], ["Text"])),
    ("Pixaroma-Find-and-Replace+ZImage", "Pixaroma · Suchen/Ersetzen + Z-Image", "Ein LLM schreibt einen Prompt, "
     "Suchen/Ersetzen erzeugt Varianten, Z-Image Turbo malt sie.", (["Text"], ["Bild"])),
    ("Pixaroma-Prompt-Multi-From-List", "Pixaroma · mehrere Prompts aus Liste", "Prompts aus einer Liste nacheinander "
     "ausgeben.", (["Text"], ["Text"])),
    ("Pixaroma-Prompt-Multi-Queue-Text", "Pixaroma · Prompt-Warteschlange", "Mehrere Prompts als Warteschlange.",
     (["Text"], ["Text"])),
    ("Pixaroma-Prompt-Pack-Line", "Pixaroma · Prompt-Paket (Zeile)", "Prompt-Bausteine zeilenweise zusammensetzen.",
     (["Text"], ["Text"])),
    ("Pixaroma-Prompt-Pack-Paragraph", "Pixaroma · Prompt-Paket (Absatz)", "Prompt-Bausteine absatzweise "
     "zusammensetzen.", (["Text"], ["Text"])),
    ("Pixaroma-Prompt-Stack", "Pixaroma · Prompt-Stapel", "Prompt-Teile stapeln und kombinieren.", (["Text"], ["Text"])),
    ("Pixaroma-Read-Prompt-From-Image", "Pixaroma · Prompt aus PNG lesen", "Liest Prompt und Einstellungen aus einem "
     "ComfyUI-PNG.", (["Bild"], ["Text"])),
    ("Pixaroma-Switch-Value", "Pixaroma · Wert umschalten", "Zwischen zwei Eingaben (Bild oder Text) umschalten.",
     (["Bild", "Text"], ["Bild", "Text"])),
    ("Pixaroma-Text-Overlay", "Pixaroma · Text über Bild", "Schriftzug über ein Bild legen.", (["Bild"], ["Bild"])),
    ("Pixaroma-XY-Plot+ZImage", "Pixaroma · XY-Plot + Z-Image", "Raster mit Varianten (z. B. Sampler × Schritte) zum "
     "Vergleichen.", (["Text"], ["Bild"])),
]:
    m(PT + f"{_name}.json", _title, _sum, *_io)

X = "Pixaroma Node Demos/"
for _name, _title, _sum, _io in [
    ("Pixaroma-3D-Builder", "Pixaroma · 3D-Builder", "Szene aus Grundkörpern bauen und rendern.", ([], ["Bild"])),
    ("Pixaroma-Combine-Two-Images", "Pixaroma · zwei Bilder kombinieren", "Zwei Bilder nebeneinander setzen.",
     ([], ["Bild"])),
    ("Pixaroma-Crop", "Pixaroma · Zuschneiden", "Bild interaktiv zuschneiden.", ([], ["Bild"])),
    ("Pixaroma-Group-Compare", "Pixaroma · Gruppenvergleich", "Mehrere Bilder in einem Raster vergleichen.",
     ([], ["Bild"])),
    ("Pixaroma-Image-Compare", "Pixaroma · Bildvergleich", "Zwei Bilder mit Regler vergleichen.", (["Bild"], ["Vergleich"])),
    ("Pixaroma-Image-Composer", "Pixaroma · Composer", "Bilder auf einer Leinwand anordnen.", ([], ["Bild"])),
    ("Pixaroma-Labels", "Pixaroma · Beschriftungen", "Überschriften und Labels für Workflows.", ([], [])),
    ("Pixaroma-LoadImage-Notify-Switch-Export-v3", "Pixaroma · Laden, Benachrichtigen, Umschalten, Export",
     "Pixaroma-Bildloader, FLUX.2-Klein-Edit, Benachrichtigung am Ende und Vergleich.", (["Bild"], ["Bild"])),
    ("Pixaroma-Loop-Build-Image-Batch", "Pixaroma · Schleife: Bildstapel bauen", "Pixaroma-Loop sammelt Bilder zu einem "
     "Stapel.", ([], ["Bild"])),
    ("Pixaroma-Loop-Build-List", "Pixaroma · Schleife: Liste bauen", "Pixaroma-Loop sammelt Texte zu einer Liste.",
     ([], ["Text"])),
    ("Pixaroma-Loop-Carry-Two-Values", "Pixaroma · Schleife: zwei Werte weiterreichen", "Zwei Werte über Schleifen-"
     "Durchläufe tragen.", ([], ["Bild", "Text"])),
    ("Pixaroma-Paint", "Pixaroma · Paint", "Im Knoten zeichnen und als Bild ausgeben.", ([], ["Bild"])),
]:
    m(X + f"{_name}.json", _title, _sum, *_io)

LA = "Live Avatar/"
RT = "Kein Beispiel: Echtzeit-Workflow (Webcam/Spout/OBS bzw. Mikrofon); die Ausgabe ist ein Live-Stream."
for _name, _title, _sum, _io, _note in [
    ("LiveAvatar-01-SDXL-Avatar-Generation", "Live Avatar 01 · SDXL RealVisXL · Avatar-Quellbild", "Frontal-Porträt für "
     "LivePortrait (neutraler Blick, geschlossener Mund).", (["Text"], ["Bild"]), ""),
    ("LiveAvatar-02-RMBG-Transparency", "Live Avatar 02 · RMBG · Avatar freistellen", "Transparentes PNG für die "
     "Spout/OBS-Workflows.", (["Bild"], ["Bild (RGBA)"]), ""),
    ("LiveAvatar-03-LivePortrait-Webcam-Spout-OBS", "Live Avatar 03 · LivePortrait · Webcam → Spout/OBS",
     "Der Avatar folgt der Webcam, Ausgabe per Spout an OBS.", (["Bild", "Webcam"], ["Live-Video"]), RT),
    ("LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA", "Live Avatar 04 · LivePortrait + Qwen3-TTS-LoRA",
     "Wie 03, dazu spricht der Avatar Text mit der eigenen Stimmen-LoRA.", (["Bild", "Webcam", "Text"], ["Live-Video",
                                                                                                     "Sprache"]), RT),
    ("LiveAvatar-05-LivePortrait-Continuous-Spout-OBS", "Live Avatar 05 · LivePortrait dauerhaft → Spout/OBS",
     "Durchgehender Lauf bis zum Abbrechen.", (["Bild", "Webcam"], ["Live-Video"]), RT),
    ("LiveAvatar-06-VRM-Full-Body-Hand-Face+Live-Mic", "Live Avatar 06 · VRM-Ganzkörper mit Händen, Gesicht und Mikro",
     "Startet den Browser-VRM-Avatar mit Körper-, Hand- und Gesichtstracking.", (["Webcam", "Mikrofon"],
                                                                                 ["Live-Video"]), RT),
    ("LiveAvatar-07-AI-Webcam-Character-Swap-Experimental", "Live Avatar 07 · SD1.5 LCM · Webcam → KI-Figur (experimentell)",
     "OpenPose aus der Webcam, SD 1.5 LCM zeichnet die Figur neu.", (["Webcam", "Bild"], ["Live-Video"]), RT),
    ("LiveAvatar-08-Local-VRM-Texture-Creator-Realistic+Stylized", "Live Avatar 08 · lokale VRM-Textur erstellen",
     "Referenzbilder → neue UV-Textur für ein vorhandenes VRM-Modell.", (["Bild"], ["Textur"]),
     "Kein Beispiel: braucht ein lokales VRM-Modell und seine UV-Vorlage."),
    ("LiveAvatar-09-Meshy-AutoRig-to-VRM-Candidate-Optional-Cloud", "Live Avatar 09 · Meshy Auto-Rig → VRM (Cloud)",
     "Optionaler Cloud-Weg über Meshy (kostet Credits).", (["Bild"], ["3D-Modell"]),
     "Kein Beispiel: nutzt einen kostenpflichtigen Cloud-Dienst."),
    ("LiveAvatar-10-Realistic-Adult-Character-Reference-Prompt+Image", "Live Avatar 10 · SDXL · realistische "
     "Charakter-Referenz", "Ganzkörper-Referenz (bekleidet) aus Prompt, optional mit Porträt.", (["Text"], ["Bild"]), ""),
    ("LiveAvatar-11-AI-Webcam-Character-Swap-Cached-OpenPose", "Live Avatar 11 · Webcam → KI-Figur mit OpenPose-Cache",
     "Schnellere Variante von 07.", (["Webcam", "Bild"], ["Live-Video"]), RT),
    ("LiveAvatar-12-I-DirectML-Face-Clone-Bakeoff", "Live Avatar 12-I · DirectML-Gesichtsklon-Vergleich",
     "Vorabprüfung der DirectML-Pfade.", ([], ["Text"]), RT),
    ("LiveAvatar-12-II-LivePortrait-Quality-Mode", "Live Avatar 12-II · LivePortrait-Qualitätsmodus",
     "Geglättetes Gesichtstracking für ruhigere Ausgabe.", (["Bild", "Webcam"], ["Live-Video"]), RT),
    ("LiveAvatar-12-III-Reliable-VRM-Mode", "Live Avatar 12-III · zuverlässiger VRM-Modus",
     "Lokaler Browser-VRM-Starter.", (["Webcam"], ["Live-Video"]), RT),
    ("LiveAvatar-13-Synthetic-Character-Sheet", "Live Avatar 13 · Qwen Image Edit 2511 · Charakterblatt",
     "Aus einem Ganzkörperfoto entstehen Front-, Seiten-, Rücken- und Nahansichten für die Avatar-Workflows.",
     (["Bild"], ["Bilder"]), ""),
    ("LiveAvatar-14-Local-Hunyuan3D-Multiview-Mesh-Unrigged", "Live Avatar 14 · Hunyuan3D · vier Ansichten → Mesh",
     "Nimmt die neuesten Ansichten aus Workflow 13 und baut ein Mesh (ohne Rig).", (["Bilder"], ["3D-Modell"]), ""),
    ("LiveAvatar-15-Local-High-Realism-VRM", "Live Avatar 15 · Hunyuan3D · Ganzkörperfoto → Mesh",
     "Single-View-Mesh aus einem A-Pose-Foto (ohne Rig).", (["Bild"], ["3D-Modell"]), ""),
    ("LiveAvatar-16-Live-Face-Swap-DirectML-Spout-OBS", "Live Avatar 16 · Live-Face-Swap (DirectML) → Spout/OBS",
     "Gesichtstausch in Echtzeit mit drei Zielbildern.", (["Bild", "Webcam"], ["Live-Video"]), RT),
    ("LiveAvatar-17-Live-Person-Swap-Matting-Voice-DirectML-Spout-OBS", "Live Avatar 17 · Live-Person-Swap + Stimme",
     "Gesicht, Freistellung und Stimme live tauschen.", (["Bild", "Webcam", "Mikrofon"], ["Live-Video"]), RT),
]:
    m(LA + f"{_name}.json", _title, _sum, *_io, note=_note)

L = "LoRA Generation/"
TR = ("Kein Beispiel: Training dauert Stunden und braucht einen eigenen Datensatz; das Ergebnis ist eine LoRA-Datei, "
      "die in den passenden Generierungs-Workflows geladen wird.")
for _name, _title, _io in [
    ("ACE-Step1_5_XL-Voice-LoRA-Training", "ACE-Step 1.5 XL SFT (BF16) · Songs → Stimmen-LoRA", (["Songs"], ["LoRA"])),
    ("Boogu_Image_Base-LoRA-Training", "Boogu Image Base (BF16) · Bilder → LoRA", (["Bilder"], ["LoRA"])),
    ("FLUX1_Dev-LoRA-Training", "FLUX.1 dev (FP8) · Bilder → LoRA", (["Bilder"], ["LoRA"])),
    ("FLUX2_Klein_4B_Base-LoRA-Training", "FLUX.2 Klein Base 4B (BF16) · Bilder → LoRA", (["Bilder"], ["LoRA"])),
    ("Qwen3-TTS_0.6B-Voice-LoRA-Training", "Qwen3-TTS 0.6B · Aufnahmen → Stimmen-LoRA", (["Audio"], ["LoRA"])),
    ("SDXL-LoRA-Training", "SDXL RealVisXL (FP16) · Bilder → LoRA", (["Bilder"], ["LoRA"])),
    ("YuE2_3B_BF16-PRIVATE-Style-LoRA-Training", "YuE2 3B (BF16) · Songs → Stil-LoRA (privat)", (["Songs"], ["LoRA"])),
    ("ZImage_Base-LoRA-Training", "Z-Image Base (BF16) · Bilder → LoRA", (["Bilder"], ["LoRA"])),
]:
    m(L + f"{_name}.json", _title, "Lokales LoRA-Training auf RDNA4 mit VRAM-Guard und Checkpointing; Datensatz aus dem "
      "ComfyUI-Eingabeordner.", *_io, note=TR)

N = "NSFW/"
m(N + "SDXL_AniToReal_v1-Image-to-Image.json", "SDXL One Obsession + Illus Real · Text → Anime → realistisch",
  "Erzeugt erst ein Anime-Bild und verwandelt es in einem zweiten Durchgang in eine realistische Version (der alte Name "
  "sagte Image-to-Image, der Workflow startet aus Text).", ["Text"], ["Bild"])
m(N + "SDXL_AniToReal_v2-Image-to-Image.json", "SDXL One Obsession + RealVisXL · Text → Anime → realistisch",
  "Variante mit RealVisXL im zweiten Durchgang.", ["Text"], ["Bild"])
m(N + "SDXL_Illustrious_v2-Text-to-Image.json", "SDXL Illustrious v2 · Bild + Tags → Bild",
  "Nimmt ein Eingabebild als Ausgangspunkt (Denoise 0,77) – der alte Name sagte Text-to-Image.", ["Bild", "Text"],
  ["Bild"])
m(N + "SDXL_Multi-Checkpoint_v1-Text-to-Image.json", "SDXL Illustrious + RealVisXL · Bild → drei Checkpoints",
  "Ein Eingabebild läuft nacheinander durch drei Checkpoints (je Denoise 0,7).", ["Bild", "Text"], ["Bild"])
m("Templates & Tests/FLUX1_vs_FLUX2-Model-Comparison.json", "FLUX.1 vs. FLUX.2 dev · Vergleichsvorlage",
  "Vorlage zum Vergleichen: aktiv ist der FLUX.2-dev-Zweig (FP8 mixed, optional Turbo-LoRA), die FLUX.1-Zweige sind "
  "überbrückt.", ["Text"], ["Bild"])

# Canvas demos without an output node: ComfyUI rejects them as a prompt, the gallery shows the screenshot only.
_UI = "Kein Beispiel-Lauf: Die Demo zeigt eine Canvas-Funktion ohne Ausgabe-Node, ComfyUI führt sie nicht aus."
m("Prompt Tools/Pixaroma-Change-Node-Color.json", "Pixaroma · Knotenfarben",
  "Zeigt alle Pixaroma-Farbvorgaben für Knoten.", [], [], note=_UI)
m("Pixaroma Node Demos/Pixaroma-Group-Compare.json", "Pixaroma · Gruppenvergleich",
  "Mehrere Bilder in einem Raster vergleichen.", [], ["Bild"], note=_UI)
m("Pixaroma Node Demos/Pixaroma-Labels.json", "Pixaroma · Beschriftungen", "Überschriften und Labels für Workflows.",
  [], [], note=_UI)
# Editor nodes shipped empty: a run returns a blank canvas, which says nothing about the node.
_EDITOR = ("Kein Beispiel-Lauf: Der Editor ist im Workflow leer – ohne {what} liefert der Knoten nur eine leere "
           "Fläche. Den Editor des Knotens öffnen, {how}, dann ausführen.")
for _name, _title, _sum, _what, _how in [
    ("Pixaroma-3D-Builder", "Pixaroma · 3D-Builder", "Szene aus Grundkörpern bauen und rendern.", "eigene Szene",
     "Grundkörper einfügen und anordnen"),
    ("Pixaroma-Crop", "Pixaroma · Zuschneiden", "Bild interaktiv zuschneiden.", "eigenes Bild",
     "ein Bild laden und den Ausschnitt ziehen"),
    ("Pixaroma-Image-Composer", "Pixaroma · Composer", "Bilder auf einer Leinwand anordnen.", "eigene Ebenen",
     "Bilder als Ebenen einfügen und anordnen"),
    ("Pixaroma-Paint", "Pixaroma · Paint", "Im Knoten zeichnen und als Bild ausgeben.", "eigene Zeichnung", "zeichnen"),
]:
    m(X + f"{_name}.json", _title, _sum, [], ["Bild"], note=_EDITOR.format(what=_what, how=_how))
