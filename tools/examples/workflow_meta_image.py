"""German titles and summaries: image editing, inpainting, outpainting, fusion, upscaling, utilities, character, batch."""
from __future__ import annotations

from workflow_meta import m

E = "Image Editing/"
m(E + "Bernini_R-Image-Edit.json", "Bernini-R · Bild bearbeiten",
  "Bernini-R (WAN-2.2-Basis, 14B, FP8) bearbeitet ein einzelnes Bild per Anweisung – eigentlich ein Video-Editor, hier "
  "mit einem Frame. Turbo-LoRA, 6 Schritte.", ["Bild", "Text"], ["Bild"])
m(E + "FLUX2_Klein_4B-One-Image-Edit.json", "FLUX.2 Klein 4B · Bild bearbeiten",
  "Ein Bild plus Anweisung (Hintergrund tauschen, Stil ändern, Objekt umfärben). 4 Schritte, das Ausgabeformat folgt dem "
  "Eingabebild.", ["Bild", "Text"], ["Bild"])
m(E + "FLUX2_Klein_4B-Two-Image-Edit.json", "FLUX.2 Klein 4B · zwei Bilder kombinieren",
  "Zwei Referenzbilder und eine Anweisung, z. B. Kleidung aus Bild 2 auf die Person in Bild 1.", ["Bild", "Text"],
  ["Bild"])
m(E + "FLUX2_Klein_9B-Multi-Step-Edit.json", "FLUX.2 Klein 9B · mehrstufige Bearbeitung",
  "Objekt freistellen (RMBG), auf einen Hintergrund setzen und in zwei Klein-9B-Durchgängen nacheinander bearbeiten; "
  "optional ein Film-Filter. Die Stufen werden per Fast Groups Muter ein- und ausgeschaltet.", ["Bild", "Text"],
  ["Bild"])
m(E + "FLUX2_Klein_9B-Pixaroma-3D-Builder-Edit.json", "FLUX.2 Klein 9B · 3D-Szene → Bild",
  "Mit dem Pixaroma-3D-Builder grob eine Szene aus Grundkörpern bauen, Klein 9B macht daraus ein fertiges Bild.",
  ["3D-Szene", "Text"], ["Bild"])
m(E + "FLUX2_Klein_9B-Pixaroma-Composer-Edit.json", "FLUX.2 Klein 9B · Collage → Bild",
  "Bilder im Pixaroma-Composer zusammenschieben, Klein 9B verschmilzt die Collage zu einem stimmigen Bild.",
  ["Collage", "Text"], ["Bild"])
m(E + "FLUX2_Klein_9B-Pixaroma-Paint-Edit.json", "FLUX.2 Klein 9B · Skizze → Bild",
  "Im Pixaroma-Paint-Knoten zeichnen, Klein 9B setzt die Skizze in ein Foto oder Gemälde um.", ["Skizze", "Text"],
  ["Bild"])
m(E + "FLUX2_Klein_9B_KV-Four-Image-Edit.json", "FLUX.2 Klein 9B · vier Bilder zu einer Szene",
  "Bis zu vier Referenzen (Personen, Tier, Ort) werden zu einem neuen Bild zusammengesetzt; Größe über den "
  "Resolution-Selector.", ["Bild", "Text"], ["Bild"])
m(E + "FLUX2_Klein_9B_KV-Image-Blend.json", "FLUX.2 Klein 9B · Objekt in Hintergrund einfügen",
  "Vordergrund automatisch freistellen, auf den Hintergrund setzen und von Klein 9B an Licht, Perspektive und Schatten "
  "anpassen lassen.", ["Bild", "Text"], ["Bild"])
m(E + "FLUX2_Klein_9B_KV-One-Image-Edit-Custom-Ratio.json", "FLUX.2 Klein 9B DARE (BF16) · Bild bearbeiten, freies Format",
  "Bearbeitung mit dem DARE-Merge und abliterated Text-Encoder; das Ausgabeformat wählst du frei im Resolution-Selector.",
  ["Bild", "Text"], ["Bild"])
m(E + "FLUX2_Klein_9B_KV-One-Image-Edit-Same-Ratio.json", "FLUX.2 Klein 9B · Bild bearbeiten",
  "Ein Bild plus Anweisung, Format wie das Eingabebild. Schnell (4 Schritte) und sehr treu bei Details.", ["Bild", "Text"],
  ["Bild"])
m(E + "FLUX2_Klein_9B_KV-Three-Image-Edit.json", "FLUX.2 Klein 9B · drei Bilder kombinieren",
  "Person, Kleidungsstück und Ort aus drei Bildern in einem neuen Bild.", ["Bild", "Text"], ["Bild"])
m(E + "FLUX2_Klein_9B_KV-Two-Image-Edit.json", "FLUX.2 Klein 9B · zwei Bilder kombinieren",
  "Motiv aus Bild 1, Element aus Bild 2 – etwa ein Kleidungsstück, ein Muster oder ein Gegenstand.", ["Bild", "Text"],
  ["Bild"])
m(E + "FLUX2_Klein_9B_Qwen3_5-Image-to-Prompt-to-Image.json", "FLUX.2 Klein 9B + Qwen3.5 · Bild → Prompt → neues Bild",
  "Qwen3.5 4B beschreibt das Eingabebild ausführlich, du prüfst den Text am Pause-Knoten, dann malt Klein 9B daraus ein "
  "neues Bild.", ["Bild"], ["Prompt", "Bild"])
m(E + "Ming_Image_0_1_Design_INT8-Image-Edit.json", "Ming Image 0.1 Design · Design bearbeiten",
  "Texte, Farben oder Motive in einem fertigen Design (Karte, Poster, Folie) ändern, Layout und Schrift bleiben.",
  ["Bild", "Text"], ["Bild"])
m(E + "Multi-Character-Angles-One-Click.json", "Qwen Image Edit 2511 · acht Kamerawinkel",
  "Aus einem Bild einer Figur entstehen acht Ansichten (nah, 45°/90° links/rechts, Vogel-/Froschperspektive, Weitwinkel) "
  "mit der Multiple-Angles-LoRA.", ["Bild"], ["Bilder"])
m(E + "Qwen_Image_2_1_BF16+AnyAngle_LoRA+TripoSplat-Image-to-4-Camera-Angles.json",
  "Qwen Image 2.1 + AnyAngle · vier Kamerawinkel aus einem Bild",
  "TripoSplat baut aus dem freigestellten Motiv ein 3D-Splat, ComfyUI rendert es grob aus vier neuen Kameras, und Qwen "
  "Image 2.1 mit der AnyAngle-LoRA überträgt Stil und Details des Originals auf jede Ansicht. Ohne Editor, ein Klick; "
  "als Vorbereitung für Video-Workflows, die mehrere Ansichten derselben Figur brauchen.", ["Bild"], ["Bilder"])
m(E + "Qwen_Image_2_1_BF16+AnyAngle_LoRA-Image+Guide-to-Camera-Angle.json",
  "Qwen Image 2.1 + AnyAngle · eigenes Render → neue Kameraansicht",
  "Original plus ein grobes Render der Zielansicht (Splat, Blender, 3D-Szene): die AnyAngle-LoRA bringt das Original in "
  "genau diesen Kamerawinkel.", ["Bild", "Render"], ["Bild"])
m(E + "Qwen_Image_2_1_BF16+AnyAngle_Studio_T8-Image-to-Camera-Angle.json",
  "Qwen Image 2.1 + AnyAngle Studio T8 · interaktive 3D-Kamera",
  "3D-Werkbank im Browser: Motiv per TripoSplat rekonstruieren, Kamera frei drehen, Render mit einem Klick übergeben; "
  "auch GLB-Modelle, Posen-Figur und Batch-Winkel.", ["Bild"], ["Bild"],
  note="Der Workflow startet erst, wenn im Studio eine Kamera gesetzt und mit „Apply to node“ übergeben wurde. Für das "
       "Beispiel wurde der Editor im Browser bedient (rekonstruieren, 45° / 10°, anwenden).")
m(E + "Qwen_Image_2_1_BF16-Background-Remover.json", "Qwen Image 2.1 · Hintergrund entfernen",
  "Offizieller Freistell-Prompt von Qwen Image 2.1: Ergebnis als PNG mit Alphakanal plus separate Maske.", ["Bild"],
  ["Bild (RGBA)"])
m(E + "Qwen_Image_2_1_BF16-Multi-Image-Edit.json", "Qwen Image 2.1 · mehrere Bilder bearbeiten",
  "Bild 1 ist die Basis, Bild 2 liefert z. B. Kleidung oder ein Objekt; Referenzen im Prompt als <image1>/<image2>.",
  ["Bild", "Text"], ["Bild"])
m(E + "Qwen_Image_Edit_2509-Image-Edit.json", "Qwen Image Edit 2509 (FP8) · Bild bearbeiten",
  "Qwen Image Edit 2509 mit Lightning-LoRA; stark bei Stilwechseln, z. B. Anime → Foto.", ["Bild", "Text"], ["Bild"])
m(E + "Qwen_Image_Edit_2511_Action-LoRA-Image-Edit.json", "Qwen Image Edit 2511 + Action-LoRA · Pose ändern",
  "Qwen Image Edit 2511 (BF16) mit Lightning- und Action-LoRA: Posen und Handlungen einer Person gezielt ändern.",
  ["Bild", "Text"], ["Bild"])
m(E + "SDXL_Illustrious-Face-and-Hand-Detailer.json", "SDXL Illustrious · Text → Bild mit Gesichts-/Hand-Detailer",
  "Anime-Bild aus Tags, danach bessern zwei FaceDetailer-Durchgänge Gesicht und Hände automatisch nach. (Der alte Name "
  "klang nach Bildbearbeitung; der Workflow startet aus Text.)", ["Text"], ["Bild"])
m(E + "SDXL_Illustrious-Simple-Image-to-Image.json", "SDXL Illustrious · Bild → Bild",
  "Klassisches Img2Img mit Illustrious (Denoise 0,88) plus Gesichts-Detailer – Stil oder Details eines Bildes ändern.",
  ["Bild", "Text"], ["Bild"])
m(E + "SDXL_Illustrious-Super-Composite.json", "SDXL Illustrious · Bild → großes Komposit",
  "Mehrstufige Illustrious-Kette mit Hochskalierung auf bis zu 16 MP.", ["Bild", "Text"], ["Bild"])
m(E + "SDXL_Illustrious-to-RealVis-Detailer-Chain.json", "SDXL Illustrious → RealVisXL · Anime → realistisch",
  "Illustrious-Durchgang und danach RealVisXL mit Gesichts-Detailer: aus einer Anime-Figur wird ein realistisches Foto.",
  ["Bild", "Text"], ["Bild"])

m("Image Inpainting/FLUX2_Klein_4B-Inpaint.json", "FLUX.2 Klein 4B · Inpainting mit Maske",
  "Maskierten Bereich neu malen (Maske im Masken-Editor oder als Alphakanal); Pixaroma schneidet den Bereich aus und "
  "setzt ihn nahtlos zurück.", ["Bild", "Maske", "Text"], ["Bild"])
m("Image Inpainting/FLUX2_Klein_9B-Pixaroma-Inpaint.json", "FLUX.2 Klein 9B · Pixaroma-Inpainting",
  "Wie das 4B-Inpainting, mit Klein 9B und Kontrollvorschau des Ausschnitts.", ["Bild", "Maske", "Text"], ["Bild"])
m("Image Inpainting/FLUX2_Klein_9B_KV-Inpaint.json", "FLUX.2 Klein 9B · Inpainting mit Maske",
  "Klein 9B KV (FP8) malt den maskierten Bereich neu, der Rest bleibt pixelgenau.", ["Bild", "Maske", "Text"], ["Bild"])
m("Image Inpainting/Qwen_Image_2_1_BF16-Mask-Inpaint.json", "Qwen Image 2.1 · Inpainting mit Maske",
  "Qwen Image 2.1 bearbeitet nur den maskierten 1024-px-Ausschnitt (plus 64 px Umgebung) und setzt ihn wieder ein.",
  ["Bild", "Maske", "Text"], ["Bild"])
m("Image Inpainting/Qwen_Image_2_1_BF16+LanPaint-Image+Mask-Inpaint.json", "Qwen Image 2.1 + LanPaint · Inpainting mit Maske",
  "Wie das Qwen-2.1-Masken-Inpainting, aber mit dem LanPaint-Sampler (2.2): trainingsfreies Inpainting, das je Schritt "
  "mehrfach „nachdenkt“, damit der neue Inhalt nahtlos zur Umgebung passt. Zum direkten Vergleich dieselben Masken.",
  ["Bild", "Maske", "Text"], ["Bild"])
m("Image Outpainting/FLUX2_Klein_9B_KV-Outpaint-Custom-Ratio.json", "FLUX.2 Klein 9B · Bild erweitern (Outpainting)",
  "Das Bild wird auf ein neues Seitenverhältnis (z. B. 16:9) gepolstert und Klein 9B füllt die Ränder passend auf.",
  ["Bild"], ["Bild"])
m("Image Fusion/Krea2_INT8_3-Reference_Fusion.json", "Krea 2 Turbo · drei Referenzen verschmelzen",
  "Drei Bilder (zwei Identitäten + ein Kompositionsanker) werden mit Krea 2 Turbo (FP8) und Style-Reference-LoRA zu einem "
  "neuen Foto. Der alte Name sagte INT8, das Modell ist FP8.", ["Bild", "Text"], ["Bild"])
m("Image Upscaling/Image-4x_NMKD_Siax-Model-Upscale.json", "NMKD Siax 4× · Bild hochskalieren",
  "Klassischer ESRGAN-Upscaler (4×) ohne Diffusion – schnell, bleibt nah am Original.", ["Bild"], ["Bild"])
m("Image Upscaling/Image-Simple-Bicubic-Upscale.json", "Bikubisch · Bild hochskalieren",
  "Reine Interpolation (4×) als Vergleichsbasis – keine neuen Details.", ["Bild"], ["Bild"])
m("Image Upscaling/ZImage_Turbo-Tiled-Upscale.json", "Z-Image Turbo · Kachel-Upscale",
  "NMKD 4× vergrößert, danach verfeinert Z-Image Turbo in Kacheln (Mixture of Diffusers, Denoise 0,2) und ergänzt Details.",
  ["Bild"], ["Bild"])

U = "Image Utilities/"
m(U + "Image-Blend.json", "Bilder überblenden", "Vordergrund freistellen und auf einen Hintergrund setzen (ohne "
  "KI-Bearbeitung).", ["Bild"], ["Bild"])
m(U + "Image-Combiner-Transparent-Items.json", "Freigestelltes Objekt einsetzen",
  "Objekt mit RMBG freistellen und in ein anderes Bild einsetzen.", ["Bild"], ["Bild"])
m(U + "Image-Combiner.json", "Bilder kombinieren", "Zwei Bilder übereinanderlegen und zusammenführen.", ["Bild"], ["Bild"])
m(U + "Image-Compare.json", "Bilder vergleichen", "Zwei Bilder mit Schieberegler vergleichen (rgthree Image Comparer).",
  ["Bild"], ["Vergleich"])
m(U + "Image-Filters-Catalog.json", "Filter-Katalog", "Viele Bildfilter zum Durchprobieren; einzelne Gruppen per Strg+M "
  "einschalten.", ["Bild"], ["Bild"])
m(U + "Image-Filters-Example.json", "Filter + Overlay", "Filterkette mit Überlagerungs-Textur.", ["Bild"], ["Bild"])
m(U + "Image-Scale.json", "Bild skalieren", "Vier Arten zu skalieren (feste Größe, Faktor, Megapixel, KJ-Resize) im "
  "Vergleich.", ["Bild"], ["Bilder"])
m(U + "Image-Stitch.json", "Bilder aneinanderfügen", "Zwei Bilder neben- oder untereinander setzen.", ["Bild"], ["Bild"])
m(U + "Image-Transformation.json", "Bild transformieren", "Drehen, spiegeln, zuschneiden.", ["Bild"], ["Bild"])
m(U + "Lama-Object-Remover.json", "LaMa · Objekt entfernen", "Maskiertes Objekt mit LaMa entfernen und den Hintergrund "
  "ergänzen (ohne Diffusion, sehr schnell).", ["Bild", "Maske"], ["Bild"])
m(U + "Ming_Image_0_1_Design_Layer_INT8-Layer-Decompose.json", "Ming Image 0.1 Design-Layer · Design → Ebenen",
  "Ein fertiges Design wird in RGBA-Ebenen zerlegt (Text, Illustrationen, Hintergrund); der Qwen3.8-Writer erstellt den "
  "Ebenenplan.", ["Bild"], ["Ebenen (RGBA)"])
m(U + "Remove-Background-RMBG.json", "RMBG-2.0 · Hintergrund entfernen", "Schnelles Freistellen mit RMBG-2.0 als PNG mit "
  "Alphakanal.", ["Bild"], ["Bild (RGBA)"])
m(U + "Remove-Background-Transparent-Items.json", "Freisteller für Objekte", "Freistellen für Produkte und Objekte "
  "(transparente PNGs).", ["Bild"], ["Bild (RGBA)"])

m("Character & Consistency/FLUX1_Kontext-Character-Keep.json", "FLUX.1 Kontext · Person beibehalten, neue Szene",
  "Kontext dev (FP8) setzt dieselbe Person in eine neue Umgebung, Gesicht und Kleidung bleiben erhalten.", ["Bild", "Text"],
  ["Bild"])
m("Character & Consistency/SDXL_IPAdapter-Character-Keep.json", "SDXL RealVisXL + IP-Adapter · Referenzgesicht",
  "Ein Referenzbild steuert über IP-Adapter das Aussehen, der Prompt die neue Szene; danach Gesichts-Detailer.",
  ["Bild", "Text"], ["Bild"])
m("Character & Consistency/SDXL_IPAdapter_FaceID-Character-Keep.json", "SDXL + IP-Adapter FaceID · Referenzgesicht",
  "FaceID-Variante mit Illustrious- und RealVisXL-Durchgang und Gesichts-Detailer.", ["Bild", "Text"], ["Bild"],
  note="Braucht das Python-Paket insightface (ab v1.3.1 setzt der Updater insightface 1.0.1 mit protobuf 5.29.6).")
m("Batch Processing/FLUX2_Klein_9B-Batch-Image-Edit.json", "FLUX.2 Klein 9B · Ordner stapelweise bearbeiten",
  "Alle Bilder eines Ordners nacheinander mit derselben Anweisung bearbeiten (Pixaroma Load Images Folder).",
  ["Ordner", "Text"], ["Bilder"])
m("Batch Processing/Load-Images-From-Folder-and-Crop.json", "Ordner laden und zuschneiden",
  "Alle Bilder eines Ordners laden und einheitlich zuschneiden oder skalieren – ohne KI.", ["Ordner"], ["Bilder"])
