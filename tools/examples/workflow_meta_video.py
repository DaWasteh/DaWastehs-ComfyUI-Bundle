"""German titles and summaries: all video categories."""
from __future__ import annotations

from workflow_meta import m

T = "Text to Video/"
for _f, _v, _q, _s in [("LTX23_dev_Q8_GGUF", "dev", "GGUF Q8_0", "28 Schritte, CFG 3"),
                       ("LTX23_dev_mxfp8", "dev", "MXFP8", "28 Schritte, CFG 3"),
                       ("LTX23_distilled_fp8", "distilled", "FP8", "8 Schritte, CFG 1"),
                       ("LTX23_distilled_mxfp8", "distilled", "MXFP8", "8 Schritte, CFG 1")]:
    m(T + f"{_f}-Text-to-Video.json", f"LTX-2.3 22B {_v} ({_q}) · Text → Video mit Ton",
      f"LTX-2.3 erzeugt Bild und Ton gemeinsam (Gemma-3-12B-Text-Encoder). {_s}, 1280×704, Länge über „Output "
      "Duration“.", ["Text"], ["Video", "Audio"])
m(T + "LTX25_INT8_ConvRot-Text-to-Video.json", "LTX-2.5 22B (INT8) · Text → Video mit Ton",
  "LTX-2.5 destilliert in INT8 mit optionalem Gemma-Prompt-Enhancer und latentem 2×-Upscaler; 1280×720, 24 fps.",
  ["Text"], ["Video", "Audio"])
m(T + "WAN22_14B_fp8_lightx2v-Text-to-Video.json", "WAN 2.2 14B (FP8) · Text → Video",
  "WAN 2.2 mit High- und Low-Noise-Modell; mit Lightning-LoRA 4 Schritte, ohne 20 Schritte und CFG 3,5. Kein Ton.",
  ["Text"], ["Video"])

I = "Text+Image to Video/"
m(I + "Kandinsky5_Lite-Text+Image-to-Video.json", "Kandinsky 5 Lite · Bild + Text → Video",
  "Kandinsky 5 Lite (I2V, 5 s) animiert ein Startbild nach Prompt; 50 Schritte, 768×512.", ["Bild", "Text"], ["Video"])
m(I + "LTX23-Image-to-Video.json", "LTX-2.3 22B (FP8) · Bild + Text → Video mit Ton",
  "Startbild plus Prompt, LTX-2.3 dev mit destillierter LoRA und 2×-Latent-Upscaler; Ton entsteht mit.",
  ["Bild", "Text"], ["Video", "Audio"])
m(I + "LTX23_Director-Prompt-Replay.json", "LTX-2.3 Director · Zeitleisten-Prompt erneut abspielen",
  "Spielt eine gespeicherte Director-Zeitleiste (Szenen-Prompts mit Zeitpunkten) erneut ab.", ["Text"], ["Video", "Audio"])
m(I + "LTX23_Director_Q8_GGUF-Tiled-Video-Generation.json", "LTX-2.3 Director (GGUF Q8_0) · Zeitleiste → Video, gekachelt",
  "Mehrere Szenen-Prompts auf einer Zeitleiste; zweistufig mit gekacheltem Dekodieren für lange Clips.", ["Text", "Bild"],
  ["Video", "Audio"])
m(I + "LTX23_Director_fp8-2-Stage.json", "LTX-2.3 Director (FP8) · Zeitleiste → Video, zweistufig",
  "Zeitleiste mit Szenen-Prompts, erster Durchgang in halber Größe, zweiter im 2×-Upscaler.", ["Text", "Bild"],
  ["Video", "Audio"])
m(I + "LTX23_First+Last-Frame-Custom-Audio.json", "LTX-2.3 22B (FP8) · erstes + letztes Bild → Video",
  "Start- und Endbild vorgeben, LTX-2.3 füllt die Bewegung dazwischen; optional mit eigener Tonspur.", ["Bild", "Text"],
  ["Video", "Audio"])
m(I + "LTX25_INT8_ConvRot-First+Last-Frame-to-Video.json", "LTX-2.5 22B (INT8) · erstes + letztes Bild → Video",
  "Start- und Endbild plus Prompt; LTX-2.5 erzeugt Übergang und Ton.", ["Bild", "Text"], ["Video", "Audio"])
m(I + "LTX25_INT8_ConvRot-Image-to-Video.json", "LTX-2.5 22B (INT8) · Bild + Text → Video mit Ton",
  "Startbild plus Prompt; LTX-2.5 kann Figuren auch sprechen lassen (Sätze in Anführungszeichen im Prompt).",
  ["Bild", "Text"], ["Video", "Audio"])
m(I + "WAN22_5B-Text+Image-to-Video.json", "WAN 2.2 TI2V 5B (FP16) · Bild + Text → Video",
  "Das kleine WAN 2.2 (5B) mit eigenem VAE; 1280×704, 24 fps, 20 Schritte.", ["Bild", "Text"], ["Video"])
m(I + "WAN22_bernini_i2v-Text+Image-to-Video.json", "Bernini-R 14B (FP8) · Bild + Text → Video",
  "Bernini-R als klassisches Image-to-Video (High/Low-Noise, 20 Schritte, CFG 4).", ["Bild", "Text"], ["Video"])
m(I + "WAN22_i2v_14B_Q8_GGUF_lightx2v-Text+Image-to-Video.json", "WAN 2.2 I2V 14B (GGUF Q8_0) · Bild + Text → Video",
  "WAN 2.2 I2V mit eingebackener LightX2V-Destillation als GGUF Q8_0; 4 Schritte, 1280×720.", ["Bild", "Text"],
  ["Video"])
m(I + "WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json", "WAN 2.2 I2V 14B (FP8) + LightX2V · Bild + Text → Video",
  "WAN 2.2 I2V in FP8 mit LightX2V-LoRAs; 4 Schritte, 1280×720, 16 fps.", ["Bild", "Text"], ["Video"])

R = "Reference to Video/"
m(R + "MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json", "MiniMax FastH3 · Song → Musikvideo (One-Click)",
  "Song + Songtext + Videoidee: Szenenplan, Prompts (Qwen3.8), FastH3-Szenen mit Lippensync, Prüfung jeder Szene "
  "(Weiter/Neu rendern), optionales Upscale und fertiges Video mit Originalton.", ["Song", "Songtext", "Text"], ["Video"],
  note="Gekürztes Beispiel: 8-Sekunden-Songausschnitt, zwei Szenen in 960×544, Prüf-Stationen auf „durchrendern“, "
       "ohne Upscale. Ein komplettes Musikvideo dauert Stunden und hält standardmäßig nach jeder Szene zur Freigabe an.")
m(R + "MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json", "MiniMax H3 FL2VA (INT8) · erstes + letztes Bild → Video mit Ton",
  "H3 mit Turbo-LoRA (8 Schritte) füllt den Weg zwischen zwei Bildern und erzeugt passenden Ton.", ["Bild", "Text"],
  ["Video", "Audio"])
m(R + "MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json", "MiniMax H3 Ref2VA (INT8) · alle Referenzen → Video",
  "Bis zu 9 Bilder, 3 Videos und 3 Audios als Referenzen (<Picture n>, <Video n>, <Audio n> im Prompt); unbenutzte "
  "Eingänge bleiben stumm.", ["Bild", "Video", "Audio", "Text"], ["Video", "Audio"])
m(R + "MiniMax_H3_Spectrum_Ref2VA_Picture_and_Video_to_Video_LOCAL.json", "MiniMax H3 Ref2VA (INT8) · Bild + Video → Video",
  "Bild liefert Identität und Aussehen, Video die Bewegung und Kamera.", ["Bild", "Video", "Text"], ["Video", "Audio"])
m(R + "MiniMax_H3_Spectrum_RefImage_Audio_to_Video_OriginalAudio_AutoLength.json", "MiniMax H3 Ref2VA (INT8) · Bild + Audio → sprechendes Video",
  "Die Person aus dem Bild spricht oder singt die Tonspur; Länge automatisch aus dem Audio, Originalton bleibt erhalten.",
  ["Bild", "Audio", "Text"], ["Video"])
m(R + "MiniMax_H3_Spectrum_RefImage_RefVideo_to_Video_Audio_AutoLength.json", "MiniMax H3 Ref2VA (INT8) · Bild + Video mit Ton → neue Person",
  "Performance, Kamera und Ton eines Videos auf die Person aus dem Bild übertragen; Länge wie das Referenzvideo.",
  ["Bild", "Video", "Text"], ["Video", "Audio"])

A = "Audio to Video/"
m(A + "FLUX2_Klein_4B_Gemma4-Audio-Context-to-AudioReact-Video.json", "FLUX.2 Klein 4B + Gemma 4 · Audio → Audio-React-Video",
  "Gemma 4 hört das Audio und beschreibt eine passende Szene, Klein 4B malt sie, Pixaroma animiert das Bild im Takt "
  "(MP4 mit Originalton).", ["Audio"], ["Prompt", "Video"])
m(A + "LTX23-Image+Audio-to-Generative-Matching-Length-Video.json", "LTX-2.3 22B (FP8) · Bild + Audio → Video in Audiolänge",
  "LTX-2.3 generiert ein echtes Video zum Startbild, synchron zur eingelesenen Tonspur (Sprache oder Musik).",
  ["Bild", "Audio", "Text"], ["Video"])
m(A + "Pixaroma-Image+Audio-to-AudioReact-Video.json", "Pixaroma · Bild + Audio → Audio-React-Video",
  "Ohne KI-Modell: das Bild pulsiert, zoomt und leuchtet im Takt der Musik.", ["Bild", "Audio"], ["Video"])
m("Audio to Image/FLUX2_Klein_4B_Gemma4-Audio-Context-to-Image.json", "FLUX.2 Klein 4B + Gemma 4 · Audio → Bild",
  "Gemma 4 hört Musik, Sprache oder Geräusche und schreibt einen Bildprompt (Pause zum Prüfen), Klein 4B malt das Bild.",
  ["Audio"], ["Prompt", "Bild"])

C = "Controlled Video/"
m(C + "Cosmos_Predict2_2B-Image-to-Video.json", "Cosmos Predict2 2B · Bild → Physik-Video",
  "NVIDIAs Weltmodell setzt eine Szene physikalisch plausibel fort (rollen, fallen, prallen); 848×480, 16 fps.",
  ["Bild", "Text"], ["Video"])
m(C + "Cosmos_Predict2_2B-First-Last-Frame.json", "Cosmos Predict2 2B · Start- + Endbild → Video",
  "Anfang und Ende vorgeben, Cosmos erzeugt die Bewegung dazwischen.", ["Bild", "Text"], ["Video"])
m(C + "Cosmos_Predict2_2B-Text-to-Video.json", "Cosmos Predict2 2B · Text → Video",
  "Erst ein Startbild mit Cosmos-T2I, dann das Video daraus – alles aus einem Prompt.", ["Text"], ["Video"])
m(C + "Cosmos_Predict2_2B-Video-Continuation.json", "Cosmos Predict2 2B · Video fortsetzen",
  "Die letzten Frames eines Videos (max. 5 Referenzframes) werden physikalisch weitergeführt.", ["Video", "Text"],
  ["Video"])
m(C + "WAN22_5B_Fun-Control-to-Video.json", "WAN 2.2 Fun Control 5B (BF16) · Referenzbild + Steuervideo → Video",
  "Ein Pose-, Tiefen- oder Kanten-Video steuert die Bewegung, das Referenzbild das Aussehen.", ["Bild", "Video", "Text"],
  ["Video"])

H = "Character Animation/"
m(H + "SCAIL2-Character-Animation.json", "WAN 2.1 SCAIL-2 14B (FP8) · Figur tanzt wie im Video",
  "Die Figur aus dem Bild übernimmt die Bewegung aus einem Tanz- oder Bewegungsvideo (SAM 3.1 findet die Person).",
  ["Bild", "Video", "Text"], ["Video"])
m(H + "SCAIL2-Character-Replacement.json", "WAN 2.1 SCAIL-2 14B (FP8) · Person im Video ersetzen",
  "Die Person im Video wird durch die Figur aus dem Bild ersetzt, Hintergrund und Bewegung bleiben.",
  ["Bild", "Video", "Text"], ["Video"])
m(H + "WAN21_SCAIL2-Character-Replacement.json", "WAN 2.1 SCAIL-2 14B (FP8) + DPO · Person ersetzen, lange Videos",
  "Segmentweise Ersetzung für längere Videos (Basis + Verlängerung) mit DPO-LoRA.", ["Bild", "Video", "Text"],
  ["Video"])
m(H + "WanAnimate2_INT8_ConvRot-Motion-Transfer.json", "Wan Animate 2 14B (INT8) · Bewegung auf Figur übertragen",
  "Bewegung und Mimik aus einem Video steuern die Figur aus dem Bild; Ergebnis neben dem Original.",
  ["Bild", "Video", "Text"], ["Video"])
m("Talking Video/WAN21_InfiniteTalk-Multi-Speaker.json", "WAN 2.1 InfiniteTalk 14B (FP8) · Bild + zwei Stimmen → Gespräch",
  "Zwei Personen in einem Bild, je eine Maske und eine Stimme: beide sprechen nacheinander lippensynchron.",
  ["Bild", "Maske", "Audio"], ["Video"])
m("Video Editing/Bernini_R-Video-Editing.json", "Bernini-R 14B (FP8) · Video per Text bearbeiten",
  "Hintergrund, Kleidung oder Stil in einem Video per Anweisung ändern, Bewegung bleibt.", ["Video", "Text"], ["Video"])
m("Video to Audio/MMAudio_Video-to-Audio.json", "MMAudio Large (FP32) · Video → passender Ton",
  "Erzeugt Geräusche passend zum Bild (Schritte, Tiere, Wasser …) und legt sie unter das Video.", ["Video", "Text"],
  ["Audio", "Video"])

V = "Video Upscaling/"
m(V + "MiniMax_H3-Latent-Upscaler-3D-FastH3.json", "MiniMax FastH3 (INT8) · Video-Latent-Upscale",
  "Beliebig lange Videos in Blöcken an Schnitten: gelernter 3D-Latent-Upscaler plus kurzer FastH3-Durchgang (Denoise "
  "0,25), Block 1 wird vorab geprüft.", ["Video"], ["Video"])
m(V + "MiniMax_H3-Ultimate-Upscale-FastH3.json", "MiniMax FastH3 (INT8) · Video Ultimate Upscale",
  "Wie der Latent-Upscaler, mit zweitem FastH3-Durchgang in voller Zielgröße (4 Schritte).", ["Video"], ["Video"])
m(V + "SeedVR2_3B_INT8-Video-Upscale.json", "SeedVR2 3B (INT8) · Video-Upscale",
  "Ein-Schritt-Restaurierung und Vergrößerung mit SeedVR2, blockweise mit Originalton.", ["Video"], ["Video"])
m(V + "WAN22_14B_LowNoise-Video-Upscale.json", "WAN 2.2 T2V 14B Low-Noise (FP8) · Video-Upscale",
  "Kacheln in WAN-Nativgröße, 2 Schritte mit Denoise 0,15 – behält Mundformen und Details, auch für WAN-2.1-Videos.",
  ["Video"], ["Video"])
