"""Gallery examples: music generation, voice design / TTS and vocal separation.

Only own lyrics, designed voices and generated reference audio are used. The installed ACE-Step voice LoRAs imitate
real singers, so examples bypass them; YuE2 (CC-BY-NC-4.0, private use in this bundle) gets no public audio.
"""
from __future__ import annotations

from catalog_image import LAKE, ex
from catalog_video import SONG, SPEECH_DE, SPEECH_EN, w

POP_TAGS = "upbeat modern pop, female vocals, catchy chorus, bright synths, punchy drums, summer vibe, 118 BPM"
POP_LYRICS = """[Verse]
Morning light on the window pane
City waking up again
Coffee cups and a paper plane
Flying out into the rain

[Chorus]
We are running on sunshine
Every heartbeat feels like a sign
Turn it up, we got all night
We are running on sunshine

[Verse]
Neon signs on a subway train
Every stranger knows my name
Dancing through the evening haze
We don't need to change a thing

[Chorus]
We are running on sunshine
Every heartbeat feels like a sign
Turn it up, we got all night
We are running on sunshine"""
ROCK_TAGS = "energetic German indie rock, male vocals, distorted electric guitars, driving drums, anthemic chorus, 140 BPM"
ROCK_LYRICS = """[Verse]
Wir fahren nachts durch leere Straßen
die Stadt schläft, doch wir sind wach
die Lichter ziehen an uns vorbei
wie Sterne über dem Dach

[Chorus]
Wir sind laut, wir sind hier
nichts hält uns heute auf
wir sind laut, wir sind hier
und die Nacht nimmt ihren Lauf

[Verse]
Ein altes Radio, ein kaputter Sitz
wir singen jedes Lied mit
der Morgen kommt, doch nicht so schnell
wir halten noch ein bisschen Schritt

[Chorus]
Wir sind laut, wir sind hier
nichts hält uns heute auf
wir sind laut, wir sind hier
und die Nacht nimmt ihren Lauf"""
LOFI_TAGS = "lo-fi hip hop, instrumental, mellow piano chords, vinyl crackle, soft boom bap drums, warm bass, relaxing, 80 BPM"
SECONDS = 60


def ace(rel: str, key: str, title: str, tags_node: int, tags: str, lyrics: str, lang: str, *, dur_node: int = 99,
        seed_node: int | None = 109, seed: int = 42, shot=False, asset=None, bypass_lora: int | None = None,
        extra=None, inputs=None, changes=None):
    patches = w(94, "lyrics", lyrics) + w(94, "language", lang) + w(dur_node, "value", SECONDS)
    if seed_node:
        patches += w(seed_node, "value", seed)
    if bypass_lora:
        patches += [{"select": {"id": bypass_lora, "path": ""}, "mode": 4}]
    note = changes
    if bypass_lora:
        note = ((note + " ") if note else "") + ("Die Stimmen-LoRA ist im Beispiel überbrückt: die lokal installierten "
                                                  "LoRAs bilden reale Sängerinnen nach und werden hier nicht gezeigt.")
    return ex(rel, key, title, prompts={tags_node: tags}, extra=patches + (extra or []), seed=None, shot=shot,
              asset=asset, inputs=inputs, changes=note,
              params={"prompt": tags, "lyrics": lyrics, "duration": f"{SECONDS} s", "seed": seed, "language": lang})


# ------------------------------------------------------------------------------------------------ ACE-Step 1.5
R = "Music Generation/ACE-Step1_5_Turbo_4B-Music-Generation.json"
ace(R, "pop", "Pop · englisch", 121, POP_TAGS, POP_LYRICS, "en", seed_node=102, shot=True, asset="song_pop.mp3")
ace(R, "rock", "Indie-Rock · deutsch", 121, ROCK_TAGS, ROCK_LYRICS, "de", seed_node=102)
ace(R, "lofi", "Lo-Fi · instrumental", 121, LOFI_TAGS, "[Instrumental]", "en", seed_node=102)
for _rel, _tags_node, _lora in [("Music Generation/ACE-Step1_5_XL_SFT-Music-Generation.json", 123, None),
                                ("Music Generation/ACE-Step1_5_XL_SFT_INT8_ConvRot-Music-Generation.json", 123, 124)]:
    ace(_rel, "pop", "Pop · englisch", _tags_node, POP_TAGS, POP_LYRICS, "en", shot=True, bypass_lora=_lora)
    ace(_rel, "rock", "Indie-Rock · deutsch", _tags_node, ROCK_TAGS, ROCK_LYRICS, "de", bypass_lora=_lora)
R = "Music Generation/ACE-Step1_5_XL_SFT_APG-Reference-Audio-Music-Generation.json"
ace(R, "rock-ref", "Neuer Song mit Klangreferenz", 137, ROCK_TAGS, ROCK_LYRICS, "de", shot=True,
    inputs={112: "song_pop.mp3"}, changes="Klangreferenz ist der Pop-Song aus dem ACE-Step-Turbo-Beispiel.")
IDEA = ("Working title: \"Lighthouse\". A lighthouse keeper on a lonely island writes letters to the ships that pass "
        "at night. Hopeful, warm, a little melancholic, big singalong chorus.")
for _rel in ("Music Generation/ACE-Step1_5_XL_SFT_Gemma4_e4B-AutoSongwriter-Genre-Selector.json",
             "Music Generation/ACE-Step1_5_XL_SFT_Qwen3_5_4B-AutoSongwriter-Genre-Selector.json"):
    ex(_rel, "lighthouse", "Idee → Songtext → Song", prompts={135: IDEA}, seed=None, shot=True,
       extra=w(99, "value", SECONDS) + w(109, "value", 42) + [{"select": {"id": 119, "path": ""}, "mode": 4}],
       params={"prompt": IDEA, "duration": f"{SECONDS} s", "seed": 42, "genre": "POP · 120 BPM · C major"},
       changes="Die Stimmen-LoRA ist im Beispiel überbrückt: die lokal installierten LoRAs bilden reale Sängerinnen nach.")

# ------------------------------------------------------------------------------------------------ HeartMuLa
IDEA_DE = ("Ein warmer deutscher Popsong über zwei Freunde, die nach Jahren zufällig auf einem Bahnsteig wieder "
           "aufeinandertreffen und merken, dass sich nichts verändert hat.")
for _rel in ("Music Generation/HeartMuLa_HappyNewYear_3B_Gemma4_e4B-Idea-to-Lyrics-to-Music.json",
             "Music Generation/HeartMuLa_HappyNewYear_3B_Qwen3_5_4B-Idea-to-Lyrics-to-Music.json"):
    ex(_rel, "bahnsteig", "Idee → Songtext → Song", prompts={20: IDEA_DE, 21: (
        "warm german pop, female vocal, acoustic guitar, soft piano, hopeful chorus, 100 BPM")}, seed=None, shot=True,
       extra=w(3, "duration_seconds", SECONDS) + w(3, "seed", 42),
       params={"prompt": IDEA_DE, "duration": f"{SECONDS} s", "seed": 42})
R = "Music Generation/HeartMuLa_HappyNewYear_3B_R9700-Music-Generation.json"
ex(R, "pop", "Tags + Songtext → Song", prompts={15: POP_TAGS}, seed=None, shot=True,
   extra=w(3, "lyrics", POP_LYRICS) + w(3, "duration_seconds", SECONDS) + w(3, "seed", 42),
   params={"prompt": POP_TAGS, "lyrics": POP_LYRICS, "duration": f"{SECONDS} s", "seed": 42})

# ------------------------------------------------------------------------------------------------ MiniMax Music 3
R = "Music Generation/MiniMax_Music3_FP32-BF16-Text-to-Music.json"
_cap = ("Global Metadata: Synth-pop, 1980s inspired. 112 BPM, A minor. Uplifting and nostalgic, bright analog synth "
        "leads, gated reverb drums, warm bass. Female lead vocal, clear and emotive.")
ex(R, "synthpop", "Beschreibung + Songtext → Song", seed=None, shot=True,
   extra=w(37, "caption", _cap) + w(37, "lyrics", POP_LYRICS) + w(37, "max_duration", SECONDS) + w(37, "seed", 42),
   params={"prompt": _cap, "lyrics": POP_LYRICS, "duration": f"{SECONDS} s", "seed": 42})

# ------------------------------------------------------------------------------------------------ Stable Audio 3
ORCH = "Cinematic orchestral adventure theme with soaring strings, french horns, choir and timpani, heroic and uplifting"
RAIN = "Heavy rain on a tin roof with distant rolling thunder and water dripping from a gutter"
for _rel in ("Music Generation/StableAudio3_Medium-Audio-Generation.json",
             "Music Generation/StableAudio3_Medium_INT8_ConvRot-Audio-Generation.json"):
    ex(_rel, "orchestra", "Musik · Orchester", seed=None, shot=True,
       extra=w(52, "user_input", ORCH) + w(52, "duration", 30) + w(52, "seed", 42) + w(52, "category", "Music"),
       params={"prompt": ORCH, "duration": "30 s", "seed": 42, "category": "Music"},
       changes="Qwen3.5 2B formuliert die Beschreibung vorher aus (Reprompt, Standard im Workflow).")
    ex(_rel, "rain", "Geräusch · Regen", seed=None,
       extra=w(52, "user_input", RAIN) + w(52, "duration", 15) + w(52, "seed", 42) + w(52, "category", "SFX"),
       params={"prompt": RAIN, "duration": "15 s", "seed": 42, "category": "SFX"})
R = "Music Generation/StableAudio3_Medium_Gemma4-Image-to-Music.json"
ex(R, "lake", "Bild → passende Musik", inputs={27: LAKE}, seed=42, shot=True, extra=w(13, "value", 30),
   params={"duration": "30 s"})
R = "Music Generation/StableAudio3_Medium_Gemma4-Text-to-Music.json"
ex(R, "piano", "Idee → Musik", prompts={44: "calm piano ballad for a rainy evening, gentle and hopeful"}, seed=42,
   shot=True, extra=w(13, "value", 30), gates=1, params={"duration": "30 s"},
   changes="Gemma schreibt den Musik-Prompt; er wird am Pause-Knoten unverändert übernommen („Continue“).")
R = "Music Generation/StableAudio3_Medium_Gemma4-Text-to-Sound.json"
ex(R, "rain", "Idee → Geräusch", prompts={44: "rain on a tin roof with distant thunder"}, seed=42, shot=True,
   extra=w(13, "value", 10), gates=1, params={"duration": "10 s"},
   changes="Gemma schreibt den Geräusch-Prompt; er wird am Pause-Knoten unverändert übernommen („Continue“).")
ex(R, "footsteps", "Idee → Geräusch", prompts={44: "footsteps on crunchy snow in a quiet forest"}, seed=43,
   extra=w(13, "value", 10), gates=1, params={"duration": "10 s"})

# ------------------------------------------------------------------------------------------------ YuE 7B (Apache-2.0)
# INT8 (bitsandbytes) is so slow on Windows/ROCm that stage 2 of the 60 s song did not finish within two hours:
# the INT8 example renders one short section instead.
for _rel, _segments, _seconds in (("Music Generation/YuE_7B-FP16_R9700-Music-Generation.json", 2, 60),
                                  ("Music Generation/YuE_7B-INT8_R9700-Music-Generation.json", 1, 15)):
    ex(_rel, "pop", "Genre-Tags + Songtext → Song", seed=None, shot=True, timeout=7200,
       extra=w(2, "genres_prompt", "pop, uplifting, female vocal, bright synths, punchy drums, summer")
       + w(2, "lyrics_prompt", POP_LYRICS) + w(2, "seed", 42) + w(2, "run_n_segment", _segments)
       + w(2, "target_duration_seconds", _seconds),
       params={"prompt": "pop, uplifting, female vocal, bright synths, punchy drums, summer", "lyrics": POP_LYRICS,
               "duration": f"{_segments} Abschnitt(e) (~{_seconds} s)", "seed": 42},
       changes=(f"{_segments} Liedabschnitt(e), ~{_seconds} s statt der voreingestellten 540-s-Zieldauer."
                + (" INT8 rechnet unter ROCm sehr langsam, daher nur ein kurzer Abschnitt." if _segments == 1 else "")))
R = "Music Generation/YuE_7B-FP16_R9700-Reference-Voice-ICL-Music-Generation.json"
ex(R, "icl", "Referenzgesang + Songtext → Song", inputs={13: "song_pop.mp3"}, seed=None, shot=True, timeout=7200,
   extra=w(2, "genres_prompt", "pop, uplifting, female vocal, bright synths") + w(2, "lyrics_prompt", POP_LYRICS)
   + w(2, "seed", 42) + w(2, "run_n_segment", 2) + w(2, "target_duration_seconds", 60),
   params={"prompt": "pop, uplifting, female vocal, bright synths", "lyrics": POP_LYRICS,
           "duration": "2 Abschnitte (~60 s)", "seed": 42},
   changes="Referenzgesang ist der Pop-Song aus dem ACE-Step-Turbo-Beispiel.")

# ------------------------------------------------------------------------------------------------ Vocal separation
R = "Vocal Separation/Local_Vocal_Remover_MelBandRoFormer.json"
ex(R, "pop", "Song → Gesang + Instrumental", inputs={2: "song_pop.mp3"}, seed=None, shot=True, use_defaults=False,
   show=["10", "11"], captions={"10": "Gesang", "11": "Instrumental"})

# ------------------------------------------------------------------------------------------------ Voice design / TTS
DE_TEXT = "Hallo und willkommen! Diese Stimme wurde komplett lokal auf meinem Rechner erzeugt."
EN_TEXT = "Welcome to the examples. Every sound you hear here was generated on a local computer."
DE_VOICE = ("A warm, friendly female voice in her thirties with clear German pronunciation, calm and natural pace, "
            "studio quality")
EN_VOICE = "A deep, calm male voice in his forties with a slight British accent, speaking slowly and warmly"
R = "Voice Design/QwenTTS_VoiceDesign-Voice-Generation.json"
ex(R, "de-woman", "Stimmbeschreibung + Text → Sprache (Deutsch)", prompts={10: DE_VOICE}, seed=None, shot=True,
   asset=SPEECH_DE, extra=w(2, "text", DE_TEXT) + w(2, "language", "German") + w(2, "seed", 42),
   params={"prompt": DE_VOICE, "text": DE_TEXT, "language": "German", "seed": 42})
ex(R, "en-man", "Stimmbeschreibung + Text → Sprache (Englisch)", prompts={10: EN_VOICE}, seed=None, asset=SPEECH_EN,
   extra=w(2, "text", EN_TEXT) + w(2, "language", "English") + w(2, "seed", 43),
   params={"prompt": EN_VOICE, "text": EN_TEXT, "language": "English", "seed": 43})
R = "Voice Design/QwenTTS_CustomVoice-Text-to-Voice.json"
for _spk, _lang, _txt, _shot in [("Vivian", "German", DE_TEXT, True), ("Ryan", "English", EN_TEXT, False)]:
    ex(R, _spk.lower(), f"Vorgefertigte Stimme „{_spk}“", seed=None, shot=_shot,
       extra=w(2, "text", _txt) + w(2, "speaker", _spk) + w(2, "language", _lang) + w(2, "seed", 42),
       params={"text": _txt, "speaker": _spk, "language": _lang, "seed": 42})
CLONE_TEXT = "Das ist ein neuer Satz, gesprochen mit der geklonten Stimme aus der kurzen Aufnahme."
R = "Voice Design/QwenTTS_VoiceClone-Voice-Generation.json"
ex(R, "clone-en", "Aufnahme + Transkript → neue Sätze", inputs={16: SPEECH_EN}, seed=None, shot=True,
   extra=w(17, "positive", EN_TEXT) + w(18, "positive", "This is a brand new sentence, spoken with the cloned voice "
                                                         "from the short recording.") + w(14, "seed", 42),
   params={"reference_text": EN_TEXT, "text": "This is a brand new sentence, spoken with the cloned voice from the "
                                              "short recording.", "seed": 42})
R = "Voice Design/QwenTTS_VoiceClone-Save-Voice.json"
ex(R, "save-woman", "Stimme klonen und speichern", inputs={15: SPEECH_DE}, seed=None, shot=True,
   extra=w(6, "positive", DE_TEXT) + w(5, "positive", CLONE_TEXT) + w(18, "filename", "gallery_woman")
   + w(14, "seed", 42) + w(14, "language", "German"),
   params={"reference_text": DE_TEXT, "text": CLONE_TEXT, "saved_as": "gallery_woman", "seed": 42})
R = "Voice Design/QwenTTS_VoiceDesign-Save-Voice.json"
ex(R, "save-man", "Stimme entwerfen und speichern", seed=None, shot=True,
   extra=w(6, "positive", EN_VOICE) + w(5, "positive", EN_TEXT) + w(13, "filename", "gallery_man") + w(4, "seed", 42),
   params={"prompt": EN_VOICE, "text": EN_TEXT, "saved_as": "gallery_man", "seed": 42})
R = "Voice Design/QwenTTS_VoiceClone-Load-Saved-Voice.json"
ex(R, "load-woman", "Gespeicherte Stimme verwenden", seed=None, shot=True,
   extra=w(19, "filename", "gallery_woman.wav") + w(18, "positive", "Guten Morgen! Heute sprechen wir über lokale "
                                                                     "Sprachsynthese.") + w(14, "seed", 42)
   + w(14, "language", "German"),
   params={"voice": "gallery_woman (aus „Stimme klonen und speichern“)",
           "text": "Guten Morgen! Heute sprechen wir über lokale Sprachsynthese.", "seed": 42})
DIALOGUE = ("man: Did you hear that? The whole song was made on this computer.\n"
            "woman: Really? Even the vocals?\n"
            "man: Even the vocals. And we are talking right now with generated voices, too.\n"
            "woman: That is a little spooky, but pretty cool.")
R = "Voice Design/QwenTTS_VoiceClone-Multi-Voice-Dialogue.json"
ex(R, "dialogue", "Zwei gespeicherte Stimmen → Dialog", seed=None, shot=True,
   extra=w(26, "filename", "gallery_man.wav") + w(29, "filename", "gallery_woman.wav") + w(21, "positive", DIALOGUE)
   + w(20, "seed", 42), params={"script": DIALOGUE, "seed": 42})
R = "Voice Design/QwenTTS_VoiceDesign-Dialogue.json"
ex(R, "dialogue", "Zwei Stimmbeschreibungen → Dialog", seed=None, shot=True,
   extra=w(6, "positive", EN_VOICE) + w(15, "positive", "Female voice. Warm and clear, friendly and curious, medium pace.")
   + w(5, "positive", "Did you hear that? The whole song was made on this computer.")
   + w(19, "positive", "Really? Even the vocals?") + w(21, "positive", DIALOGUE) + w(4, "seed", 42) + w(17, "seed", 43)
   + w(20, "seed", 44), params={"script": DIALOGUE, "seed": 42})
R = "Voice Design/MOSS-TTS_Local_v1.5-Text+Voice-Reference-to-Speech.json"
ex(R, "clone-de", "Aufnahme → neue Sätze", inputs={2: SPEECH_DE}, seed=None, shot=True,
   extra=w(3, "text", CLONE_TEXT) + w(3, "seed", 42), params={"text": CLONE_TEXT, "seed": 42})
R = "Voice Design/MOSS-TTS_Local_v1.5-Audio+Transcript-to-Speech-Continuation.json"
ex(R, "continue-de", "Aufnahme + Transkript → Fortsetzung", inputs={2: SPEECH_DE}, seed=None, shot=True,
   extra=w(3, "prefix_text", DE_TEXT) + w(3, "continuation_text", "Und jetzt spricht sie einfach weiter, ohne dass "
                                                                    "man den Übergang hört.") + w(3, "seed", 42),
   params={"reference_text": DE_TEXT, "text": "Und jetzt spricht sie einfach weiter, ohne dass man den Übergang hört.",
           "seed": 42})
