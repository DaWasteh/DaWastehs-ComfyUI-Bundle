"""German titles and summaries: music generation, voice design and vocal separation."""
from __future__ import annotations

from workflow_meta import m

M = "Music Generation/"
LORA_NOTE = ("Die lokal installierten ACE-Step-LoRAs bilden reale Sängerinnen nach; damit werden hier keine Beispiele "
             "erzeugt.")
YUE2_NOTE = ("YuE2 steht unter CC-BY-NC-4.0 und ist im Bundle ausdrücklich für private Projekte gedacht – deshalb keine "
             "Audiobeispiele im öffentlichen Repo.")
m(M + "ACE-Step1_5_Turbo_4B-Music-Generation.json", "ACE-Step 1.5 Turbo (BF16) · Stil-Tags + Songtext → Song",
  "Der schnelle ACE-Step: 8 Schritte für einen kompletten Song mit Gesang; Sprache, Tonart und Tempo einstellbar.",
  ["Tags", "Songtext"], ["Song"])
m(M + "ACE-Step1_5_XL-LoRA-Music-Generation.json", "ACE-Step 1.5 XL SFT (BF16) + LoRA · Song mit Stimmen-LoRA",
  "Wie ACE-Step XL SFT, dazu eine Stimmen- oder Stil-LoRA (eigene LoRAs aus dem Voice-LoRA-Training).",
  ["Tags", "Songtext"], ["Song"], note=LORA_NOTE)
m(M + "ACE-Step1_5_XL_SFT-Music-Generation.json", "ACE-Step 1.5 XL SFT (BF16) · Stil-Tags + Songtext → Song",
  "Die große SFT-Version mit APG-Stabilisierung: 75 Schritte, CFG 4, detailreicher Gesang.", ["Tags", "Songtext"],
  ["Song"])
m(M + "ACE-Step1_5_XL_SFT_APG-Reference-Audio-Music-Generation.json", "ACE-Step 1.5 XL SFT (BF16) · Klangreferenz + Songtext → Song",
  "Eine 30-s-Referenz gibt Klangfarbe und Produktion vor, Tags und Songtext den neuen Song.",
  ["Audio", "Tags", "Songtext"], ["Song"])
for _llm, _name in [("Gemma4_e4B", "Gemma 4 e4B"), ("Qwen3_5_4B", "Qwen3.5 4B")]:
    m(M + f"ACE-Step1_5_XL_SFT_{_llm}-AutoSongwriter-Genre-Selector.json",
      f"ACE-Step 1.5 XL SFT + {_name} · Idee → Songtext → Song",
      f"{_name} schreibt aus einer Song-Idee den Songtext und die ACE-Beschreibung, das Genre-Preset setzt Tempo und "
      "Tonart.", ["Text"], ["Songtext", "Song"])
m(M + "ACE-Step1_5_XL_SFT_INT8_ConvRot-Music-Generation.json", "ACE-Step 1.5 XL SFT (INT8) · Stil-Tags + Songtext → Song",
  "INT8-Variante des XL-SFT-Modells – im Quant-Vergleich neben BF16.", ["Tags", "Songtext"], ["Song"])
for _llm, _name in [("Gemma4_e4B", "Gemma 4 e4B"), ("Qwen3_5_4B", "Qwen3.5 4B")]:
    m(M + f"HeartMuLa_HappyNewYear_3B_{_llm}-Idea-to-Lyrics-to-Music.json",
      f"HeartMuLa 3B + {_name} · Idee → Songtext → Song",
      f"{_name} schreibt den Songtext (auch auf Deutsch), HeartMuLa 3B singt ihn mit HeartCodec.", ["Text", "Tags"],
      ["Songtext", "Song"])
m(M + "HeartMuLa_HappyNewYear_3B_R9700-Music-Generation.json", "HeartMuLa 3B · Tags + Songtext → Song",
  "HeartMuLa (Happy-New-Year-Checkpoint) mit eigenem Songtext.", ["Tags", "Songtext"], ["Song"])
m(M + "MiniMax_Music3_FP32-BF16-Text-to-Music.json", "MiniMax Music 3 (FP32) · Beschreibung + Songtext → Song",
  "Lokales MiniMax Music 3 mit strukturierter Beschreibung (Genre, Tempo, Tonart, Stimmung) und Songtext.",
  ["Text", "Songtext"], ["Song"])
m(M + "StableAudio3_Medium-Audio-Generation.json", "Stable Audio 3 Medium (FP32) · Text → Musik/Geräusch",
  "Musik, Instrumente, Soundeffekte oder One-Shots; Qwen3.5 2B formuliert die Beschreibung vorher aus.", ["Text"],
  ["Audio"])
m(M + "StableAudio3_Medium_INT8_ConvRot-Audio-Generation.json", "Stable Audio 3 Medium (INT8) · Text → Musik/Geräusch",
  "INT8-Variante – im Quant-Vergleich neben FP32.", ["Text"], ["Audio"])
m(M + "StableAudio3_Medium_Gemma4-Image-to-Music.json", "Stable Audio 3 + Gemma 4 · Bild → Musik",
  "Gemma 4 sieht das Bild und schreibt einen Musik-Prompt, Stable Audio 3 komponiert den passenden Soundtrack.",
  ["Bild"], ["Prompt", "Audio"])
m(M + "StableAudio3_Medium_Gemma4-Text-to-Music.json", "Stable Audio 3 + Gemma 4 · Idee → Musik",
  "Gemma 4 erweitert die Idee zum Musik-Prompt (Pause zum Prüfen), Stable Audio 3 erzeugt die Musik.", ["Text"],
  ["Prompt", "Audio"])
m(M + "StableAudio3_Medium_Gemma4-Text-to-Sound.json", "Stable Audio 3 + Gemma 4 · Idee → Geräusch",
  "Wie Idee → Musik, abgestimmt auf Geräusche und Atmosphären.", ["Text"], ["Prompt", "Audio"])
m(M + "YuE2_3B_BF16-PRIVATE-LoRA-Music-Generation.json", "YuE2 3B (BF16) + Stil-LoRA · Song (privat)",
  "YuE2 mit eigener Stil-LoRA (aus dem YuE2-LoRA-Training).", ["Tags", "Songtext"], ["Song"], note=YUE2_NOTE)
m(M + "YuE2_3B_INT8-PRIVATE-ABC-to-Music.json", "YuE2 3B (INT8) · ABC-Noten + Songtext → Song (privat)",
  "Eigene Partitur in ABC-Notation plus Songtext.", ["ABC", "Songtext"], ["Song"], note=YUE2_NOTE)
m(M + "YuE2_3B_INT8-PRIVATE-Audio-Cover.json", "YuE2 3B (INT8) · Song + Songtext → Cover (privat)",
  "Neue Version eines eigenen Songs mit anderem Text.", ["Song", "Songtext"], ["Song"], note=YUE2_NOTE)
m(M + "YuE2_3B_INT8-PRIVATE-Text-to-Music.json", "YuE2 3B (INT8) · Stil + Songtext → Song (privat)",
  "YuE2 plant zuerst ABC-Noten und singt dann den Songtext.", ["Tags", "Songtext"], ["Song"], note=YUE2_NOTE)
m(M + "YuE_7B-FP16_R9700-Music-Generation.json", "YuE 7B (FP16) · Genre-Tags + Songtext → Song",
  "YuE (Stage A 7B + Stage B 1B) singt Songtexte abschnittsweise; langsam, aber sehr musikalisch.", ["Tags", "Songtext"],
  ["Song"])
m(M + "YuE_7B-FP16_R9700-Reference-Voice-ICL-Music-Generation.json", "YuE 7B ICL (FP16) · Referenzgesang + Songtext → Song",
  "In-Context-Learning: ein ca. 30 s langer Referenzgesang gibt Stimme und Stil vor.", ["Audio", "Songtext"], ["Song"])
m(M + "YuE_7B-INT8_R9700-Music-Generation.json", "YuE 7B (INT8) · Genre-Tags + Songtext → Song",
  "INT8-Variante von YuE (bitsandbytes) für Karten mit wenig VRAM.", ["Tags", "Songtext"], ["Song"],
  note="Gekürztes Beispiel (ein Abschnitt, 15 s): Auf dem Referenzrechner (Windows, ROCm) rechnet bitsandbytes-INT8 sehr "
       "langsam – 36 Minuten für 15 Sekunden; Stufe 2 eines 60-Sekunden-Songs war nach zwei Stunden nicht fertig. Die "
       "FP16-Variante braucht auf der R9700 für 60 Sekunden rund 25 Minuten.")
m("Vocal Separation/Local_Vocal_Remover_MelBandRoFormer.json", "MelBand-RoFormer (FP16) · Song → Gesang + Instrumental",
  "Trennt Gesang und Begleitung eines Songs in zwei Spuren.", ["Song"], ["Audio"])

D = "Voice Design/"
m(D + "MOSS-TTS_Local_v1.5-Audio+Transcript-to-Speech-Continuation.json", "MOSS-TTS v1.5 (BF16) · Aufnahme + Transkript → Fortsetzung",
  "Setzt eine Sprachaufnahme nahtlos mit neuem Text in derselben Stimme fort.", ["Audio", "Text"], ["Sprache"])
m(D + "MOSS-TTS_Local_v1.5-Text+Voice-Reference-to-Speech.json", "MOSS-TTS v1.5 (BF16) · Text + Stimmprobe → Sprache",
  "Klont eine Stimme aus einer kurzen Aufnahme und spricht neuen Text (48 kHz Stereo).", ["Text", "Audio"], ["Sprache"])
m(D + "Qwen3-TTS_LoRA-Low-Latency-Live-Voice.json", "Qwen3-TTS 0.6B + Voice-LoRA · Text → eigene Stimme (live)",
  "Schnelle Sprachausgabe mit einer selbst trainierten Stimmen-LoRA, etwa für den Live-Avatar.", ["Text"], ["Sprache"],
  note="Kein Beispiel: nutzt eine private, selbst trainierte Stimme (siehe LoRA-Training).")
m(D + "QwenTTS_CustomVoice-Text-to-Voice.json", "Qwen3-TTS 1.7B CustomVoice (BF16) · Text → Sprache mit fertiger Stimme",
  "Neun eingebaute Stimmen (z. B. Vivian, Ryan), zehn Sprachen, optional mit Sprechanweisung.", ["Text"], ["Sprache"])
m(D + "QwenTTS_VoiceClone-Load-Saved-Voice.json", "Qwen3-TTS 1.7B Base (BF16) · gespeicherte Stimme → Sprache",
  "Eine vorher gespeicherte, geklonte Stimme laden und neuen Text sprechen.", ["Stimme", "Text"], ["Sprache"])
m(D + "QwenTTS_VoiceClone-Multi-Voice-Dialogue.json", "Qwen3-TTS 1.7B Base (BF16) · Dialog mit gespeicherten Stimmen",
  "Ein Skript mit Rollen (man: …, woman: …) wird mit zwei gespeicherten Stimmen gesprochen.", ["Stimme", "Text"],
  ["Sprache"])
m(D + "QwenTTS_VoiceClone-Save-Voice.json", "Qwen3-TTS 1.7B Base (BF16) · Stimme klonen und speichern",
  "Aufnahme (10–20 s) + exaktes Transkript: Stimme klonen, als Datei speichern und gleich einen Satz sprechen.",
  ["Audio", "Text"], ["Stimme", "Sprache"])
m(D + "QwenTTS_VoiceClone-Voice-Generation.json", "Qwen3-TTS 1.7B Base (BF16) · Stimmprobe + Text → Sprache",
  "Direktes Klonen ohne Speichern: Aufnahme, Transkript und neuer Text.", ["Audio", "Text"], ["Sprache"])
m(D + "QwenTTS_VoiceDesign-Dialogue.json", "Qwen3-TTS 1.7B VoiceDesign (BF16) · zwei beschriebene Stimmen → Dialog",
  "Zwei Stimmen per Beschreibung entwerfen und ein Dialog-Skript sprechen lassen.", ["Text"], ["Sprache"])
m(D + "QwenTTS_VoiceDesign-Save-Voice.json", "Qwen3-TTS 1.7B VoiceDesign (BF16) · Stimme entwerfen und speichern",
  "Stimme per Beschreibung (Alter, Klang, Tempo, Akzent) entwerfen und für spätere Workflows speichern.", ["Text"],
  ["Stimme", "Sprache"])
m(D + "QwenTTS_VoiceDesign-Voice-Generation.json", "Qwen3-TTS 1.7B VoiceDesign (BF16) · Stimmbeschreibung + Text → Sprache",
  "Eine neue Stimme nur aus einer Beschreibung erzeugen – ohne Aufnahme.", ["Text"], ["Sprache"])
m(D + "RVC_DirectML-Live-Microphone-Voice-Swap.json", "RVC (DirectML) · Mikrofon → andere Stimme (live)",
  "Startet und prüft den DirectML-RVC-Stimmwandler für Live-Mikrofon und OBS.", ["Mikrofon"], ["Sprache"],
  note="Kein Beispiel: Echtzeit-Workflow (Mikrofon-Eingang), der einen externen Dienst startet.")
