"""Gallery examples: text/image/reference/audio to video, controlled video, character animation, talking video,
video editing, video upscaling and video to audio. Every clip is at most 5 seconds long."""
from __future__ import annotations

from catalog import Example, add, p_seed
from catalog_image import (DOG, FB, FOX, LAKE, PM, PW, ROOM, ANIME, ex, media, node, prompt, widget)


def top(node_id: int) -> dict:
    return {"id": node_id, "path": ""}


def w(node_id: int, name: str, value) -> list:
    return [{"select": top(node_id), "widget": name, "value": value}]


def duration(node_id: int, seconds: float = 5.0) -> list:
    return w(node_id, "value", seconds)


DANCE = "dance_woman.mp4"          # WAN 2.2 I2V example below (asset)
DOGVID = "dog_bark.mp4"            # WAN 2.2 I2V example below (asset)
ROOMVID = "living_room_dolly.mp4"  # WAN 2.2 5B example below (asset)
MANVID = "man_talking.mp4"         # LTX-2.5 I2V example below (asset, with sound)
SPEECH_DE = "speech_de_woman.mp3"  # Qwen3-TTS VoiceDesign example (asset)
SPEECH_EN = "speech_en_man.mp3"    # Qwen3-TTS VoiceDesign example (asset)
SONG = "song_pop_excerpt.mp3"      # ACE-Step example, first 8 s (asset)
POSEVID = "pose_dance.mp4"         # SDPose from video example (asset)
BALL = "physics_ball_start.png"
BALL_END = "physics_ball_end.png"
V = 5.0

# ------------------------------------------------------------------------------------------------ Text to Video
FOX_T2V = ("A red fox trots through fresh snow in a quiet pine forest at sunrise, its breath visible in the cold air, soft "
           "golden light between the trees, the camera tracks alongside at ground level, gentle crunching of snow and "
           "distant birdsong")
BARISTA_T2V = ("Close-up of a barista pouring steamed milk into a cappuccino and forming a heart-shaped latte art, soft "
               "morning light, shallow depth of field, quiet café ambience with clinking cups")
for _rel, _p, _d, _keys in [
    ("Text to Video/LTX23_dev_Q8_GGUF-Text-to-Video.json", 44, 51, ("fox",)),
    ("Text to Video/LTX23_dev_mxfp8-Text-to-Video.json", 44, 51, ("fox",)),
    ("Text to Video/LTX23_distilled_fp8-Text-to-Video.json", 46, 53, ("fox", "barista")),
    ("Text to Video/LTX23_distilled_mxfp8-Text-to-Video.json", 46, 53, ("fox", "barista")),
]:
    for _k in _keys:
        ex(_rel, _k, "Fuchs im Schnee" if _k == "fox" else "Barista · Latte Art", shot=_k == "fox", seed=42,
           prompts={_p: FOX_T2V if _k == "fox" else BARISTA_T2V}, extra=duration(_d, 4.0), params={"duration": "4 s"})

R = "Text to Video/LTX25_INT8_ConvRot-Text-to-Video.json"
ex(R, "fox", "Fuchs im Schnee (mit Prompt-Enhancer)", shot=True, seed=None,
   extra=w(405, "text", FOX_T2V) + w(405, "value_1", 5) + w(405, "noise_seed", 42),
   params={"prompt": FOX_T2V, "duration": "5 s", "seed": 42},
   changes="Gemma verbessert den Prompt vor dem Rendern (Standard im Workflow, „Enable Prompt Enhance“).")

R = "Text to Video/WAN22_14B_fp8_lightx2v-Text-to-Video.json"
ex(R, "balloon", "Heißluftballon", shot=True, seed=42, prompts={224: (
    "A colorful hot air balloon rises slowly over a green valley with a winding river at sunrise, gentle camera pan, "
    "soft morning mist over the fields")}, extra=w(189, "value", V) + w(190, "value", True),
   params={"duration": "5 s"}, changes="Lightning-LoRA eingeschaltet (4 Schritte, CFG 1) – im Workflow standardmäßig aus.")

# ------------------------------------------------------------------------------------------------ Text+Image to Video
R = "Text+Image to Video/WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json"
LAKE_I2V = ("Gentle ripples spread across the calm alpine lake, light morning mist drifts slowly over the water, a bird "
            "flies past the mountains, slow push-in camera move")
ex(R, "lake", "Bergsee wird lebendig", inputs={10: LAKE}, shot=True, seed=42, prompts={38: LAKE_I2V},
   extra=duration(45), params={"duration": "5 s"})
ex(R, "dance", "Tanz (Hochformat)", inputs={10: FB}, seed=43, asset=DANCE, prompts={38: (
    "The woman dances casually in place, swaying her hips and moving her arms to the rhythm, friendly smile, static "
    "camera, plain grey studio background")}, extra=duration(45) + w(12, "width", 480) + w(12, "height", 832),
   params={"duration": "5 s", "width": 480, "height": 832})
ex(R, "dog", "Hund bellt", inputs={10: DOG}, seed=44, asset=DOGVID, prompts={38: (
    "The golden retriever barks twice towards the camera and wags its tail, grass moves slightly in the wind, static "
    "camera")}, extra=duration(45) + w(12, "width", 832) + w(12, "height", 832),
   params={"duration": "5 s", "width": 832, "height": 832})
R = "Text+Image to Video/WAN22_i2v_14B_Q8_GGUF_lightx2v-Text+Image-to-Video.json"
ex(R, "lake", "Bergsee wird lebendig", inputs={8: LAKE}, shot=True, seed=42, prompts={34: LAKE_I2V},
   extra=duration(41), params={"duration": "5 s"})
R = "Text+Image to Video/WAN22_bernini_i2v-Text+Image-to-Video.json"
ex(R, "window", "Blick zum Fenster", inputs={8: PW}, shot=True, seed=42, prompts={34: (
    "The woman slowly turns her head towards a window on the left and smiles softly, her hair moves slightly, warm "
    "light, static camera")}, extra=duration(41), params={"duration": "5 s"})
R = "Text+Image to Video/WAN22_5B-Text+Image-to-Video.json"
ex(R, "dolly", "Kamerafahrt durchs Wohnzimmer", inputs={56: ROOM}, shot=True, seed=42, asset=ROOMVID, prompts={74: (
    "Slow cinematic camera dolly forward into the bright living room, soft daylight, the plant leaves move slightly, "
    "steady smooth motion")}, extra=duration(81), params={"duration": "5 s"})
R = "Text+Image to Video/Kandinsky5_Lite-Text+Image-to-Video.json"
ex(R, "smile", "Porträt wird lebendig", inputs={11: PW}, shot=True, seed=42, prompts={106: (
    "The woman smiles, blinks and turns her head slightly to the side, her hair moves gently, soft studio light, "
    "static camera")}, extra=duration(112), params={"duration": "5 s"})
R = "Text+Image to Video/LTX23-Image-to-Video.json"
ex(R, "lake", "Bergsee mit Ton", inputs={269: LAKE}, shot=True, seed=None, extra=w(320, "value", LAKE_I2V + (
    ", soft ambient nature sounds with water and wind")) + w(320, "value_4", 5) + w(320, "noise_seed", 42),
   params={"prompt": LAKE_I2V + ", soft ambient nature sounds with water and wind", "duration": "5 s", "seed": 42})
R = "Text+Image to Video/LTX25_INT8_ConvRot-Image-to-Video.json"
MAN_TALK = ("Use the provided start image as the first frame. The man looks into the camera and says calmly in English: "
            "\"Welcome to the examples of this ComfyUI bundle.\" He smiles slightly at the end. Static camera, quiet room.")
ex(R, "talk", "Porträt spricht (Ton aus dem Modell)", inputs={395: PM}, shot=True, seed=None, asset=MANVID,
   extra=w(398, "value", MAN_TALK) + w(398, "value_1", False) + w(398, "value_2", 5) + w(398, "noise_seed", 42),
   params={"prompt": MAN_TALK, "duration": "5 s", "seed": 42},
   changes="Prompt-Enhancer aus, damit der gesprochene Satz genau so übernommen wird.")
R = "Text+Image to Video/LTX25_INT8_ConvRot-First+Last-Frame-to-Video.json"
FLF = ("Time-lapse over the alpine lake: the sun sets, the sky turns deep blue, stars appear and a warm light switches on "
       "in the boathouse window, calm water, static camera")
ex(R, "day-night", "Tag → Nacht (erstes + letztes Bild)", inputs={31: LAKE, 39: "landscape_lake_night.png"}, shot=True,
   seed=None, extra=w(251, "value", FLF) + w(251, "value_2", 5) + w(251, "noise_seed", 42),
   params={"prompt": FLF, "duration": "5 s", "seed": 42},
   input_captions={"ex_" + LAKE: "Erstes Bild", "ex_landscape_lake_night.png": "Letztes Bild"})

# ------------------------------------------------------------------------------------------------ Video Editing
R = "Video Editing/Bernini_R-Video-Editing.json"
ex(R, "beach", "Hintergrund im Video tauschen", inputs={47: DANCE}, shot=True, seed=None,
   extra=w(76, "text", "Replace the plain grey studio backdrop with a sunny beach with palm trees and turquoise sea, keep "
                       "the woman, her clothes and her dance movements unchanged") + w(76, "noise_seed", 42),
   params={"prompt": "Replace the plain grey studio backdrop with a sunny beach with palm trees and turquoise sea, keep "
                     "the woman, her clothes and her dance movements unchanged", "seed": 42})
R = "Image Editing/Bernini_R-Image-Edit.json"
ex(R, "night", "Tag → Nacht", inputs={114: LAKE}, shot=True, seed=None,
   extra=w(76, "text", "make it a clear starry night with moonlight on the water") + w(76, "noise_seed", 42),
   params={"prompt": "make it a clear starry night with moonlight on the water", "seed": 42})

# ------------------------------------------------------------------------------------------------ Video to Audio
R = "Video to Audio/MMAudio_Video-to-Audio.json"
ex(R, "dog", "Hundegebell zum stummen Video", inputs={3: DOGVID}, shot=True, seed=None,
   prompts={16: "a golden retriever barking in a park, grass rustling, birds in the background"},
   extra=w(4, "seed", 42), params={"duration": "Länge des Videos (5 s)", "seed": 42})

# ------------------------------------------------------------------------------------------------ Controlled Video (Cosmos + WAN Fun Control)
BALL_PROMPT = ("The red rubber ball starts rolling down the wooden ramp, accelerates, leaves the ramp and bounces twice "
               "across the grey concrete floor before rolling out of frame, locked-off camera")
R = "Controlled Video/Cosmos_Predict2_2B-Image-to-Video.json"
ex(R, "ball", "Ball rollt die Rampe hinunter", inputs={29: BALL}, shot=True, seed=118, prompts={32: BALL_PROMPT},
   extra=duration(35), params={"duration": "5 s"}, asset="cosmos_ball.webm")
R = "Controlled Video/Cosmos_Predict2_2B-First-Last-Frame.json"
ex(R, "ball", "Start- und Endbild vorgeben", inputs={29: BALL, 34: BALL_END}, shot=True, seed=118,
   prompts={32: BALL_PROMPT}, extra=duration(36), params={"duration": "5 s"})
R = "Controlled Video/Cosmos_Predict2_2B-Text-to-Video.json"
ex(R, "ball", "Nur Text", shot=True, seed=118, prompts={32: (
    "A locked-off camera observes a red rubber ball rolling down a wooden ramp onto a grey concrete floor and bouncing "
    "twice, plain white wall, soft daylight")}, extra=duration(39), params={"duration": "5 s"})
R = "Controlled Video/Cosmos_Predict2_2B-Video-Continuation.json"
ex(R, "ball", "Video fortsetzen", inputs={34: "cosmos_ball.webm"}, shot=True, seed=119, prompts={32: (
    "The red ball keeps bouncing across the concrete floor, loses energy and comes to rest near the white wall")},
   extra=duration(36), params={"duration": "5 s"})
R = "Controlled Video/WAN22_5B_Fun-Control-to-Video.json"
ex(R, "fox-dance", "Pose-Video steuert die Figur", inputs={70: FOX, 66: POSEVID}, shot=True, seed=42, prompts={92: (
    "A cute cartoon fox adventurer with an orange coat, green scarf and brown boots dances happily, 3D animation, plain "
    "light background")}, extra=duration(99), params={"duration": "5 s"},
   input_captions={"ex_" + FOX: "Referenzbild", "ex_" + POSEVID: "Steuervideo (Pose aus dem SDPose-Beispiel)"})

# ------------------------------------------------------------------------------------------------ Character Animation
R = "Character Animation/SCAIL2-Character-Animation.json"
ex(R, "anime-dance", "Figur tanzt wie im Video", inputs={58: ANIME, 113: DANCE}, shot=True, seed=123,
   prompts={155: ("A girl with short silver hair, green eyes, a red hoodie, black shorts and sneakers dances casually in "
                  "front of a plain white wall")}, extra=duration(163), params={"duration": "5 s"})
R = "Character Animation/SCAIL2-Character-Replacement.json"
ex(R, "anime-replace", "Person im Video ersetzen", inputs={58: ANIME, 113: DANCE}, shot=True, seed=1234,
   prompts={162: ("A girl with short silver hair, green eyes, a red hoodie, black shorts and sneakers dances casually in "
                  "a grey studio")}, extra=duration(170), params={"duration": "5 s"})
R = "Character Animation/WAN21_SCAIL2-Character-Replacement.json"
_scail = ("An adult woman with silver hair and green eyes, wearing a red hoodie, blue jeans and white sneakers, dances "
          "casually in a plain grey studio. She has a normal-sized head and a slim face.")
# the dance clip is portrait (480x832); the workflow renders 896x512 landscape by default and cut the clip down to the
# hips. Width/height are promoted on both segment instances (base 213, extend 262) as value_3 / value_4.
_portrait = [p for node_id in (213, 262) for p in w(node_id, "value_3", 512) + w(node_id, "value_4", 896)]
ex(R, "anime-replace", "Person ersetzen (lange Videos, segmentweise)", inputs={30: ANIME, 155: DANCE}, shot=True,
   seed=None, extra=w(213, "text", _scail) + w(262, "text", _scail) + _portrait,
   params={"prompt": _scail, "size": "512 × 896 (hochkant wie das Tanzvideo)"},
   changes="Breite/Höhe in beiden Segmenten auf 512×896 gestellt: das Tanzvideo ist hochkant, der Workflow rendert "
           "standardmäßig quer (896×512) und schneidet ein Hochkant-Video sonst auf die Bildmitte zu.")
R = "Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json"
ex(R, "fox-dance", "Bewegung auf Figur übertragen", inputs={189: FOX, 240: DANCE}, shot=True, seed=None,
   extra=w(261, "text", "Character appearance description: a cute cartoon fox adventurer with orange fur, a green scarf "
                        "and brown leather boots. Background description: plain light grey studio.")
   + w(261, "text_4", "A fox character dancing casually with swaying hips and moving arms") + duration(592),
   params={"prompt": "a cute cartoon fox adventurer with orange fur, a green scarf and brown leather boots",
           "duration": "5 s"})

# ------------------------------------------------------------------------------------------------ Video Upscaling (block review gate)
for _rel, _key in [("Video Upscaling/SeedVR2_3B_INT8-Video-Upscale.json", "dance"),
                   ("Video Upscaling/WAN22_14B_LowNoise-Video-Upscale.json", "dance"),
                   ("Video Upscaling/MiniMax_H3-Ultimate-Upscale-FastH3.json", "dance"),
                   ("Video Upscaling/MiniMax_H3-Latent-Upscaler-3D-FastH3.json", "dance")]:
    e = ex(_rel, _key, "480×832 → ×1,5", shot=True, seed=None, use_defaults=False,
           extra=w(1, "video", "ex_" + DANCE) + w(1, "project_name", "gallery_" + _rel.split("/")[1].split("-")[0]),
           gates=1, changes="Block 1 wird am Pause-Knoten geprüft, dann „Continue“ für den Rest (wie im Workflow vorgesehen).")
    e.uploads[DANCE] = "ex_" + DANCE

# ------------------------------------------------------------------------------------------------ Reference to Video (MiniMax H3, INT8)
R = "Reference to Video/MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json"
ex(R, "day-night", "Erstes + letztes Bild → Video mit Ton", inputs={2: LAKE, 3: "landscape_lake_night.png"}, shot=True,
   seed=None, extra=w(4, "value", FLF + ", quiet evening ambience with crickets") + duration(6) + w(15, "noise_seed", 42),
   params={"prompt": FLF + ", quiet evening ambience with crickets", "duration": "5 s", "seed": 42})
R = "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json"
_park = ("Use <Picture 1> as the identity and face reference and <Picture 2> for the full outfit. The woman walks towards "
         "the camera along a sunny park path, smiles and waves, trees and warm afternoon light, birdsong and distant "
         "children playing.")
ex(R, "park", "Zwei Referenzbilder → Video mit Ton", inputs={2: PW, 25: FB}, shot=True, seed=None,
   extra=w(5, "value", _park) + duration(7) + w(16, "noise_seed", 42),
   params={"prompt": _park, "duration": "5 s", "seed": 42})
R = "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_Picture_and_Video_to_Video_LOCAL.json"
_pv = ("Use <Picture 1> as the identity and appearance reference for the main character and follow the body motion and "
       "camera of <Video 1>: the man dances casually in a plain grey studio.")
ex(R, "man-dance", "Bild (Identität) + Video (Bewegung)", inputs={2: PM, 3: DANCE}, shot=True, seed=None,
   extra=w(5, "value", _pv) + duration(7) + w(16, "noise_seed", 42),
   params={"prompt": _pv, "duration": "5 s", "seed": 42})
R = "Reference to Video/MiniMax_H3_Spectrum_RefImage_Audio_to_Video_OriginalAudio_AutoLength.json"
_ia = ("Use <Picture 1> as the persistent identity, face, hair and clothing. The woman speaks the words of <Audio 1> "
       "directly into the camera with natural lip movement and small head nods, plain grey studio, static camera.")
ex(R, "speech", "Bild + Sprachaufnahme → sprechendes Video", inputs={2: PW, 3: SPEECH_DE}, shot=True, seed=None,
   extra=w(4, "value", _ia) + w(3, "max_seconds", 5.0) + w(12, "noise_seed", 42),
   params={"prompt": _ia, "duration": "Länge der Aufnahme (max. 5 s)", "seed": 42})
R = "Reference to Video/MiniMax_H3_Spectrum_RefImage_RefVideo_to_Video_Audio_AutoLength.json"
_iv = ("Use <Picture 1> as the identity, face, body, clothing and visual-style reference. Recreate the performance, "
       "camera and sound of <Video 1> and <Audio 1> with this woman: she looks into the camera and says the same sentence.")
ex(R, "speech-swap", "Bild + Video mit Ton → neue Person, gleicher Satz", inputs={2: PW, 3: MANVID}, shot=True,
   seed=None, extra=w(5, "value", _iv) + w(13, "noise_seed", 42),
   params={"prompt": _iv, "duration": "Länge des Referenzvideos (5 s)", "seed": 42})

# ------------------------------------------------------------------------------------------------ Audio to Video / Audio to Image
R = "Audio to Video/Pixaroma-Image+Audio-to-AudioReact-Video.json"
ex(R, "lake-song", "Bild pulsiert zur Musik", inputs={1: LAKE, 3: SONG}, shot=True, seed=None, use_defaults=False)
R = "Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json"
_mv_idea = ("A woman with shoulder-length auburn hair in a dark green sweater dances happily on a sunny rooftop above a "
            "city, warm late-afternoon light, colorful, cinematic")
# lyrics, video idea and format come from their own input nodes (PixaromaPrompt 1 and 2, PixaromaSizes 3, all linked
# into the planner), so the planner's own widgets are overridden; the format stays at the workflow favourite 960x544
ex(R, "short", "8-s-Song → Musikvideo (2 Szenen, 960×544)", inputs={7: SONG}, shot=True, seed=None, timeout=3600,
   extra=[{"select": top(1), "prompt": ""}, {"select": top(2), "prompt": _mv_idea}]
   + w(7, "project_name", "Gallery_MV")
   + w(7, "target_scene_seconds", 4.0) + w(7, "min_scene_seconds", 3.0) + w(7, "max_scene_seconds", 5.0)
   + w(7, "resume_existing_scenes", False) + w(26, "review", False) + w(34, "review", False) + w(20, "upscale", False),
   params={"video_idea": _mv_idea, "song": "8-s-Ausschnitt (instrumental, Lyrics leer)", "size": "960 × 544",
           "scenes": "Ziel 4 s (min 3, max 5)", "review": "durchrendern", "upscale": "aus"},
   changes="Kurzes Galerie-Beispiel: 8-Sekunden-Songausschnitt in 960×544 mit zwei Szenen, Prüf-Stationen auf "
           "„durchrendern“ und ohne Upscale. Für echte Musikvideos: Prüfung jeder Szene (Standard) und Upscale.",
   show=["37", "25", "33"], captions={"37": "Fertiges Musikvideo (Originalton)", "25": "Szene 1", "33": "Szene 2"})
R = "Audio to Video/LTX23-Image+Audio-to-Generative-Matching-Length-Video.json"
# LTX-2 talks when the prompt quotes the spoken words (LTX-2 prompting guide); without them the face stayed almost still
_la = ("A real cinematic close-up video. The woman looks into the camera and talks. She says in German: \"Hallo und "
       "willkommen! Diese Stimme wurde komplett lokal auf meinem Rechner erzeugt.\" Her lips move clearly with every "
       "word, natural facial expressions, small head movements, she blinks. Soft studio light, the camera does not move. "
       "Smooth, plain light-grey background.")
ex(R, "speech", "Bild + Sprache → Video in Audiolänge", inputs={381: PW, 499: SPEECH_DE}, shot=True, seed=None,
   extra=w(504, "value", _la) + w(499, "start_time", 0) + w(499, "end_time", 5) + w(499, "duration", 5),
   params={"prompt": _la, "duration": "Länge der Aufnahme (5 s)"})
R = "Audio to Video/FLUX2_Klein_4B_Gemma4-Audio-Context-to-AudioReact-Video.json"
ex(R, "song", "Musik → passendes Bild → Audio-React-Video", inputs={13: SONG}, shot=True, seed=42, gates=1,
   changes="Der von Gemma geschriebene Bildprompt wird am Pause-Knoten unverändert übernommen („Continue“).")
R = "Audio to Image/FLUX2_Klein_4B_Gemma4-Audio-Context-to-Image.json"
ex(R, "song", "Musik → passendes Bild", inputs={1: SONG}, shot=True, seed=42, gates=1,
   changes="Der von Gemma geschriebene Bildprompt wird am Pause-Knoten unverändert übernommen („Continue“).")

R = "Text+Image to Video/LTX23_First+Last-Frame-Custom-Audio.json"
_e = ex(R, "day-night", "Erstes + letztes Bild → Video", seed=None, shot=True,
        extra=w(381, "image_paths", "\n".join(["ex_" + LAKE, "ex_landscape_lake_night.png"]))
        + w(499, "audio", "ex_" + SONG)
        + w(10, "value", FLF) + w(10, "value_2", 5) + w(10, "noise_seed", 42),
        params={"prompt": FLF, "duration": "5 s", "seed": 42},
        changes="Eigene Tonspur aus (Standard); die Bilder kommen über den Multi-Image-Loader (Pfade im Eingabeordner).")
_e.uploads.update({LAKE: "ex_" + LAKE, "landscape_lake_night.png": "ex_landscape_lake_night.png", SONG: "ex_" + SONG})


# ------------------------------------------------------------------------------------------------ LTX Director
def director(global_prompt: str, segments: list, *, width: int = 0, height: int = 0, fps: int = 24):
    """prepare() hook: write a fresh WhatDreamsCost 2.x timeline into the LTX Director node (id 46) before loading.

    segments: (frames, prompt, image or None). The editor restores its widgets from node.properties, so the values go
    into both widgets_values (23-slot 2.x order) and properties."""
    import json
    import time as _t

    def hook(wf: dict) -> dict:
        start, segs = 0, []
        for k, (frames, text, image) in enumerate(segments):
            seg = {"id": f"{int(_t.time() * 1000)}ex{k}", "start": start, "length": frames, "prompt": text,
                   "type": "image" if image else "text"}
            if image:
                seg.update(imageFile="ex_" + image, guideStrength=1,
                           imageB64=f"/api/view?filename=ex_{image}&type=input&subfolder=")
            segs.append(seg)
            start += frames
        total = start
        timeline = {"mainTrackEnabled": True, "audioTrackEnabled": True, "motionTrackEnabled": True, "propHeight": 90,
                    "globalPropHeight": 60, "showFilenames": True, "overrideAudio": False, "inpaint_audio": True,
                    "global_prompt": global_prompt, "retake_global_prompt": "", "retakeMode": False,
                    "retakeStart": 24, "retakeLength": 48, "retakePrompt": "", "retakeStrength": 1,
                    "retakeVideo": None, "normalStartFrame": 0, "normalDurationFrames": total, "segments": segs,
                    "motionSegments": [], "audioSegments": []}
        values = {"start_second": 0.0, "end_second": total / fps, "duration_seconds": total / fps, "start_frame": 0,
                  "end_frame": total, "duration_frames": total,
                  "timeline_data": json.dumps(timeline, ensure_ascii=False, separators=(",", ":")),
                  "local_prompts": " | ".join(s[1] for s in segments),
                  "segment_lengths": ",".join(str(s[0]) for s in segments),
                  "guide_strength": ",".join("1.00" for s in segments if s[2])}
        node = next(n for n in wf["nodes"] if n["type"] == "LTXDirector")
        names = ["start_second", "end_second", "duration_seconds", "start_frame", "end_frame", "duration_frames",
                 "timeline_data", "local_prompts", "segment_lengths", "epsilon", "guide_strength", "use_custom_audio",
                 "use_custom_motion", "inpaint_audio", "frame_rate", "display_mode", "custom_width", "custom_height",
                 "resize_method", "divisible_by", "img_compression", "override_audio", "timeline_ui"]
        wv = dict(zip(names, node["widgets_values"]))
        wv.update(values, custom_width=width, custom_height=height)
        node["widgets_values"] = [wv[n] for n in names]
        node["properties"].update({n: wv[n] for n in names}, global_prompt=global_prompt)
        return wf
    return hook


FOX_DIR = ("Cinematic nature short film. A red fox in a snowy pine forest at golden hour, photorealistic, soft "
           "volumetric light, fine snow in the air.")
FOX_SEGS = [(40, "Wide aerial shot slowly descending toward the fox walking through deep snow between the pines.", None),
            (40, "Close-up of the fox's face as it stops and sniffs the air, its breath visible in the cold.", None),
            (40, "The fox leaps high and dives head-first into the snow to catch a mouse, snow sprays around it.", None)]
for R in ("Text+Image to Video/LTX23_Director_fp8-2-Stage.json",
          "Text+Image to Video/LTX23_Director_Q8_GGUF-Tiled-Video-Generation.json"):
    _e = ex(R, "fox-timeline", "Timeline · drei Textsegmente", seed=42, shot=True,
            params={"global prompt": FOX_DIR, "segmente": " | ".join(f"{s[0]} Frames: {s[1]}" for s in FOX_SEGS),
                    "duration": "5 s (120 Frames)"},
            changes="Timeline auf 5 s gekürzt (3 × 40 Frames) und mit eigenem Inhalt statt der Beispiel-Timeline gefüllt.")
    _e.prepare = director(FOX_DIR, FOX_SEGS)

MAN_DIR = ("A friendly man in his thirties in a softly lit room, natural window light, photorealistic, 35 mm film look, "
           "calm and warm mood.")
MAN_SEGS = [(8, "He looks into the camera and smiles.", PM),
            (56, "He raises his hand and waves at the camera, smiling warmly.", None),
            (56, "He laughs softly, nods and gives a thumbs up.", None)]
_e = ex("Text+Image to Video/LTX23_Director_Q8_GGUF-Tiled-Video-Generation.json", "man-keyframe",
        "Timeline · Startbild + zwei Textsegmente", seed=42,
        params={"global prompt": MAN_DIR, "segmente": " | ".join(f"{s[0]} Frames: {s[1]}" for s in MAN_SEGS),
                "duration": "5 s (120 Frames)"},
        changes="Erstes Segment ist ein Bildsegment (Keyframe) mit dem Porträt, danach zwei reine Textsegmente.")
_e.prepare = director(MAN_DIR, MAN_SEGS, width=768, height=768)  # 1024 x 1024 pushed the box past 160 GiB commit
_e.uploads[PM] = "ex_" + PM

WOMAN_DIR = ("A cheerful young woman with long brown hair and a knitted sweater in a bright studio, photorealistic, "
             "soft light.")
WOMAN_SEGS = [(40, "She smiles, tilts her head slightly and winks playfully at the camera.", PW),
              (40, "She brings both hands to her cheeks and laughs.", None),
              (40, "She blows a kiss to the camera and waves goodbye.", None)]
_e = ex("Text+Image to Video/LTX23_Director-Prompt-Replay.json", "woman-replay", "Replay · Porträt + zwei Textsegmente",
        seed=42, shot=True,
        params={"global prompt": WOMAN_DIR, "segmente": " | ".join(f"{s[0]} Frames: {s[1]}" for s in WOMAN_SEGS),
                "duration": "5 s (120 Frames)", "size": "720 × 1280"},
        changes="Eigenes Porträt statt des Beispielbilds; Timeline auf 5 s (3 × 40 Frames).")
_e.prepare = director(WOMAN_DIR, WOMAN_SEGS, width=720, height=1280)
_e.uploads[PW] = "ex_" + PW
