"""Gallery examples: 3D / game assets, pose & depth, prompt enhancers and tools, Pixaroma demos, Live Avatar
(non-realtime parts), NSFW category (safe prompts only), templates and the text-to-image workflows with an LLM step."""
from __future__ import annotations

from catalog import wf_json
from catalog_image import (ANIME, CARD, DOG, FB, FOX, LAKE, PM, PW, ROOM, TEAPOT, ex, widget)
from catalog_video import DANCE, ROOMVID, SPEECH_EN, w

CHEST, HOUSE = "asset_chest.png", "asset_house.png"

# ------------------------------------------------------------------------------------------------ Image to 3D-Mesh
R = "Image to 3D-Mesh/Hunyuan3D_v2_1-Image-to-3D-Mesh.json"
ex(R, "fox", "Figur → 3D-Mesh", inputs={2: FOX}, shot=True, seed=42)
R = "Image to 3D-Mesh/Mira_Scene-Layout-Preview.json"
OBJ = "sofa, coffee table, television, potted plant, floor lamp, sideboard"
ex(R, "room", "Foto → Layout-Vorschau (Voxel)", inputs={1: ROOM}, shot=True, seed=None, prompts={4: OBJ},
   params={"objects": OBJ})
R = "Image to 3D-Mesh/Mira_Scene-Image-to-3D-Scene.json"
ex(R, "room", "Foto → 3D-Szene (ein Mesh je Objekt)", inputs={1: ROOM}, shot=True, seed=None, prompts={4: OBJ},
   params={"objects": OBJ}, timeout=7200, show=["25", "27"],
   captions={"25": "Gesamtszene (alle Objekte, Y oben)",
             "27": ["Objekt 1", "Objekt 2", "Objekt 3", "Objekt 4", "Objekt 5", "Objekt 6", "Objekt 7", "Objekt 8"]})

# ------------------------------------------------------------------------------------------------ Game Development
R = "Game Development/FLUX2_Klein_4B-PS1-Texture-Concept.json"
ex(R, "bricks", "Textur · Mauerwerk", shot=True, seed=42, prompts={22: (
    "Seamless tileable texture of mossy medieval stone bricks, flat front view, even diffuse lighting, no shadows")})
ex(R, "metal", "Textur · Sci-Fi-Metall", seed=43, prompts={22: (
    "Seamless tileable texture of a rusty sci-fi metal panel with rivets and warning stripes, flat front view, even "
    "diffuse lighting")})
R = "Game Development/Hunyuan3D_v2_1-Low-Poly-Static-Mesh-for-Godot.json"
ex(R, "chest", "Bild → vier LOD-Stufen für Godot", inputs={2: CHEST}, shot=True, seed=42)
for _rel, _key, _title, _img in [
    ("Game Development/Pixal3D_INT8-Buildings-and-Environment-PBR-for-Godot.json", "house", "Gebäude → PBR-Mesh", HOUSE),
    ("Game Development/Pixal3D_INT8-Humanoids-and-Animals-PBR-for-Godot.json", "fox", "Figur → PBR-Mesh", FOX),
    ("Game Development/Pixal3D_INT8-PBR-Collision.json", "teapot", "Objekt → PBR-Mesh + Kollision", TEAPOT),
    ("Game Development/Pixal3D_INT8-Shape-Collision.json", "teapot", "Objekt → Form + Kollision", TEAPOT),
    ("Game Development/TRELLIS2_INT8-PBR-Collision.json", "chest", "Objekt → PBR-Mesh + Kollision", CHEST),
    ("Game Development/TRELLIS2_INT8-Shape-Collision.json", "chest", "Objekt → Form + Kollision", CHEST),
]:
    ex(_rel, _key, _title, inputs={122: _img}, shot=True, seed=None, timeout=7200)
# MultiView wants calibrated rig renders (90 degrees apart, same scale, FOV 20, black background), not invented views:
# tools/examples/blender_multiview_views.py renders a procedural mailbox with ComfyUI's own camera rig
MV_VIEWS = {327: "mv_mailbox_front.png", 328: "mv_mailbox_left.png", 329: "mv_mailbox_back.png",
            330: "mv_mailbox_right.png"}
ex("Game Development/Pixal3D_INT8-MultiView-PBR-Collision.json", "mailbox", "Vier Blender-Ansichten → PBR-Mesh + Kollision",
   inputs=MV_VIEWS, shot=True, seed=None, timeout=7200,
   params={"Ansichten": "vorne, links, hinten, rechts · 90° Abstand · FOV 20° · schwarzer Hintergrund",
           "Quelle": "Blender-Render eines prozeduralen Briefkastens (tools/examples/blender_multiview_views.py)"})

# ------------------------------------------------------------------------------------------------ Pose & Depth
R = "Pose & Depth/DepthAnything3-Depth-from-Image.json"
ex(R, "room", "Bild → Tiefenkarte", inputs={2: ROOM}, shot=True, seed=None, use_defaults=False)
R = "Pose & Depth/DepthAnything3-Depth-from-Video.json"
ex(R, "room", "Video → Tiefenvideo", inputs={3: ROOMVID}, shot=True, seed=None, use_defaults=False)
R = "Pose & Depth/SDPose-Pose-from-Image.json"
ex(R, "woman", "Bild → Pose", inputs={3: FB}, shot=True, seed=None, use_defaults=False)
R = "Pose & Depth/SDPose-Pose-from-Video.json"
ex(R, "dance", "Video → Pose-Video", inputs={4: DANCE}, shot=True, seed=None, use_defaults=False,
   asset="pose_dance.mp4", asset_node="9")

# ------------------------------------------------------------------------------------------------ Prompt Enhancer
R = "Prompt Enhancer/LLM_Qwen3_8_27B-Image-Prompt-Enhancer.json"
T_RUN, T_TEXT, T_TAGS, T_EDIT = ("Fließtext (Z-Image, FLUX, Qwen Image, Krea)", "Text im Bild (Poster, Logo, Schild)",
                                 "Tags (SDXL, Pony, Illustrious)", "Bearbeiten (Anweisung für Edit-Modelle)")
for _key, _title, _draft, _target, _detail, _lang, _shot in [
    ("storm", "Fließtext · Leuchtturm im Sturm", "Ein alter Leuchtturm bei Sturm, Möwen, dramatisches Licht", T_RUN,
     "mittel", "English", True),
    ("poster", "Text im Bild · Konzertplakat", 'Plakat für ein Jazzkonzert "BLUE NOTES" am 12. Oktober im Hafen', T_TEXT,
     "mittel", "English", False),
    ("tags", "Tags · Anime-Szene", "Mädchen mit Katzenohren sitzt im Regen an einer Bushaltestelle", T_TAGS, "mittel",
     "English", False),
    ("short-de", "Fließtext · kurz auf Deutsch", "Katze schläft auf einem Stapel alter Bücher", T_RUN, "kurz",
     "Deutsch", False),
]:
    ex(R, _key, _title, prompts={1: _draft}, seed=None, shot=_shot, use_defaults=False,
       extra=w(3, "target", _target) + w(3, "detail", _detail) + w(3, "language", _lang) + w(3, "seed", 42),
       params={"prompt": _draft, "target": _target, "detail": _detail, "language": _lang, "seed": 42})
ex(R, "edit", "Bearbeiten · mit Bild", prompts={1: "gib ihr eine rote Lederjacke und lass sie lächeln"}, seed=None,
   inputs={2: PW}, use_defaults=False,
   extra=[{"select": {"id": 2, "path": ""}, "mode": 0}] + w(3, "target", T_EDIT) + w(3, "detail", "mittel")
   + w(3, "language", "English") + w(3, "seed", 42),
   params={"prompt": "gib ihr eine rote Lederjacke und lass sie lächeln", "target": T_EDIT, "detail": "mittel",
           "language": "English", "seed": 42},
   changes="Bild-Loader eingeschaltet (Strg+M), damit Qwen das zu bearbeitende Bild sieht.")

_GEN = ("You are a prompt engineer for AI image and video models. Take the user's short idea and expand it into ONE "
        "vivid, concrete prompt: subject, setting, lighting, composition, lens/camera, mood, and (for video) camera "
        "movement. Use natural descriptive sentences, no tag lists, no preamble. Output only the final prompt.\n\n"
        "User idea: ")
R = "Prompt Enhancer/LLM_General-Prompt-Enhancer.json"
for _key, _idea in [("knight", "a knight resting by a campfire in a snowy forest"),
                    ("drone", "drone flight over a neon city at night, for a video")]:
    ex(R, _key, "Idee → Prompt", seed=None, shot=_key == "knight", use_defaults=False,
       extra=w(2, "prompt", _GEN + _idea), params={"prompt": _idea})
R = "Prompt Enhancer/LLM_Qwen3_5_4B-Text-to-Prompt.json"
for _key, _idea in [("bunny", "a cute cartoon 3d white bunny wearing an orange t-shirt, on a beach, palm trees"),
                    ("library", "an ancient underground library lit by floating lanterns")]:
    ex(R, _key, "Idee → Prompt", prompts={230: _idea}, seed=None, shot=_key == "bunny", use_defaults=False)
for _rel, _key, _idea in [
    ("Prompt Enhancer/MiniMax_H3_Base_FL2VA-Official-Guide-Prompt-Enhancer.json", "lighthouse",
     "a lighthouse keeper climbs the spiral stairs during a storm and switches on the lamp"),
    ("Prompt Enhancer/MiniMax_H3_Ref2VA-Official-Guide-Prompt-Enhancer.json", "cafe",
     "the woman from my reference photo orders a coffee in a busy café and laughs with the barista"),
    ("Prompt Enhancer/Qwen3VL_8b_fp8_scaled-Krea2-Prompt-Enhancer.json", "icon",
     "an app icon for a local AI code-safety benchmark called SuperCalc, simple but cool"),
]:
    ex(_rel, _key, "Idee → Prompt", prompts={9: _idea}, seed=None, shot=True, use_defaults=False)
R = "Prompt Enhancer/MiniMax_Music3-Official-Skill-Caption-Enhancer.json"
ex(R, "synthpop", "Musikidee → Caption", prompts={9: "nostalgic 80s synth-pop song about a summer night drive"},
   seed=None, shot=True, use_defaults=False)
for _rel, _node, _inp, _title in [
    ("Prompt Enhancer/LLM_Gemma4_e4b-Image-to-Prompt.json", 4, ROOM, "Bild → Prompt"),
    ("Prompt Enhancer/LLM_Qwen3_5_4B-Image-to-Prompt.json", 211, DOG, "Bild → Prompt"),
    ("Prompt Enhancer/LLM_Gemma4_e4b-Audio-to-Text.json", 12, SPEECH_EN, "Sprache → Text"),
    ("Prompt Enhancer/LLM_Gemma4_e4b-Video-to-Description.json", 13, DANCE, "Video → Beschreibung"),
    ("Prompt Enhancer/LLM_Gemma4_e4b-Video-to-Prompt.json", 13, DANCE, "Video → Prompt"),
    ("Prompt Tools/LLM_Qwen3_5_4B_abliterated-Text-Generation.json", 2, TEAPOT, "Bild → Beschreibung"),
]:
    ex(_rel, "default", _title, inputs={_node: _inp}, seed=None, shot=True, use_defaults=False)
R = "Prompt Tools/LLM_Qwen3_4B-Text-Generation.json"
ex(R, "haiku", "Text → Text", seed=None, shot=True, use_defaults=False,
   extra=w(7, "prompt", "Write a short haiku about a GPU that renders images all night."),
   params={"prompt": "Write a short haiku about a GPU that renders images all night."})
IDEA_IDEO = "Werbeplakat für eine Limonade namens \"ZITRO\": gelber Hintergrund, Zitronenscheiben, frecher Slogan \"Sauer macht froh\""
for _rel in ("Prompt Tools/Ideogram4_Qwen3_5-Field-Text-Builder.json", "Prompt Tools/Ideogram4_Qwen3_5-JSON-Prompt-Builder.json"):
    ex(_rel, "zitro", "Idee → Ideogram-Felder", seed=None, shot=True, use_defaults=False,
       extra=w(1, "value", IDEA_IDEO), params={"prompt": IDEA_IDEO})
R = "Prompt Enhancer/Ideogram4_Qwen3_5-Auto-Prompt-to-Image.json"
ex(R, "zitro", "Idee → Ideogram-JSON → Bild", seed=None, shot=True, extra=w(206, "value", IDEA_IDEO)
   + w(165, "noise_seed", 42), params={"prompt": IDEA_IDEO, "seed": 42},
   show=["202"])  # the workflow also previews its sigma schedule as a chart (node 189)

# ------------------------------------------------------------------------------------------------ Text to Image with an LLM step (pause gate)
R = "Text to Image/FLUX2_Klein_9B_Qwen3_5-Text-to-Prompt-to-Image.json"
ex(R, "bunny", "Idee → Prompt (Pause) → Bild", prompts={235: "a cute cartoon 3d white bunny in an orange t-shirt on a beach"},
   seed=42, shot=True, gates=1, changes="Der Prompt von Qwen3.5 wird am Pause-Knoten unverändert übernommen („Continue“).")
R = "Image Editing/FLUX2_Klein_9B_Qwen3_5-Image-to-Prompt-to-Image.json"
ex(R, "room", "Bild → Prompt (Pause) → neues Bild", inputs={211: ROOM}, seed=42, shot=True, gates=1,
   changes="Die Bildbeschreibung von Qwen3.5 wird am Pause-Knoten unverändert übernommen („Continue“).")
R = "Text to Image/Krea2_turbo-2K-Text-to-Image.json"
ex(R, "bunny", "Idee → Prompt (Pause) → 2K-Bild", prompts={229: "macro photo of a baby white bunny in a meadow with a little pink bow"},
   seed=35, shot=True, gates=1, changes="Der Prompt von Qwen3-VL wird am Pause-Knoten unverändert übernommen („Continue“).")
R = "Text to Image/Krea2_turbo-Uncensored-Prompt-Enhanced-Text-to-Image.json"
ex(R, "sailor", "Idee → Prompt (Pause) → Bild", prompts={229: "portrait photo of an old sailor with a pipe on a foggy harbor"},
   seed=35, shot=True, gates=1, changes="Der Prompt wird am Pause-Knoten unverändert übernommen („Continue“).")
R = "Text to Image/Ideogram4-Text-to-Image.json"
# The KJ prompt builder is a layout editor: every region (box) carries its own type (obj / text), text and description,
# and the style fields apply to the whole picture. The shipped workflow still holds the template's macro-eye regions and
# photo style, so only replacing the description rendered an eye again. The example fills every field for a poster.
POSTER_REGIONS = [
    {"x": 0.06, "y": 0.04, "w": 0.88, "h": 0.15, "type": "text", "text": "ALPENBAHN",
     "desc": "huge bold vintage poster title in cream letters with a dark outline, centered", "palette": []},
    {"x": 0.28, "y": 0.2, "w": 0.44, "h": 0.06, "type": "text", "text": "SEIT 1926",
     "desc": "small subtitle in the same lettering, centered below the title", "palette": []},
    {"x": 0.04, "y": 0.46, "w": 0.92, "h": 0.4, "type": "obj", "text": "",
     "desc": "a red steam locomotive with three carriages crossing a curved stone viaduct, white steam clouds", "palette": []},
]
POSTER_FIELDS = {2: "A vintage travel poster for a Swiss mountain railway.",
                 3: "snowy alpine peaks and green valleys under a clear blue sky",
                 4: "art_style", 5: "1930s vintage travel poster, stylized illustration",
                 6: "bold flat colors, strong simple graphic shapes, retro lithograph texture",
                 7: "bright clear mountain daylight", 8: "screen-printed travel poster"}


def ideogram_poster(wf: dict) -> dict:
    """prepare() hook: fill the prompt builder (node 6) - fields in widget order, regions in elements_data. The KJ
    frontend restores its boxes from the node's own "ideo" state and only falls back to elements_data, so both change."""
    import json
    node = next(n for n in wf["nodes"] if n["id"] == 6)
    for index, value in POSTER_FIELDS.items():
        node["widgets_values"][index] = value
    node["widgets_values"][10] = json.dumps(POSTER_REGIONS)
    node.setdefault("ideo", {})["boxes"] = json.loads(json.dumps(POSTER_REGIONS))
    return wf


_poster = ex(R, "poster", "Reiseplakat mit Text-Kästen", seed=42, shot=True,
   params={"prompt": POSTER_FIELDS[2], "background": POSTER_FIELDS[3], "style": "art_style · " + POSTER_FIELDS[5],
           "Kasten 1 (Text)": "ALPENBAHN – großer Titel oben", "Kasten 2 (Text)": "SEIT 1926 – Untertitel",
           "Kasten 3 (Objekt)": POSTER_REGIONS[2]["desc"]},
   changes="Der Prompt-Builder ist ein Layout-Editor: Jeder Kasten hat eigenen Typ, Text und Beschreibung. Das Beispiel "
           "ersetzt die Makro-Auge-Kästen und den Foto-Stil der Vorlage durch Titel-, Untertitel- und Zug-Kasten.")
_poster.prepare = ideogram_poster
R = "Text to Image/Ming_Image_0_1_Design_INT8-Text-to-Image.json"
_ming = 'Poster für ein Sommerfest am See: großer Titel "SEEFEST 2026", darunter "Samstag 18. Juli · Musik · Essen · Boote", illustrierter See mit Segelbooten, fröhliche Farben'
ex(R, "seefest", "Design-Idee → Poster (2048²)", prompts={5: _ming}, seed=42, shot=True, extra=w(7, "seed", 42))
ex(R, "seefest-1024", "Design-Idee → Poster (1024²)", prompts={5: _ming}, seed=42,
   extra=w(7, "seed", 42) + w(10, "width", 1024) + w(10, "height", 1024), params={"width": 1024, "height": 1024})
R = "Text to Image/Ming_Image_0_1_Design_INT8-Transparent-RGBA.json"
ex(R, "fox-sticker", "Sticker mit Transparenz", prompts={5: (
    "A cute red fox mascot sitting upright and waving, flat vector sticker with a white outline")}, seed=42, shot=True,
   extra=w(7, "seed", 42))

# ------------------------------------------------------------------------------------------------ Pixaroma demos and prompt tools
# Group-Compare, Labels and Change-Node-Color have no output node (canvas features): screenshot only (shots_only.py).
# 3D-Builder, Crop, Image-Composer and Paint ship with an empty editor: a run only returns a blank canvas, so they get
# the screenshot and a note as well.
for _rel in ["Pixaroma Node Demos/Pixaroma-Combine-Two-Images.json",
             "Pixaroma Node Demos/Pixaroma-Loop-Build-Image-Batch.json", "Pixaroma Node Demos/Pixaroma-Loop-Build-List.json",
             "Pixaroma Node Demos/Pixaroma-Loop-Carry-Two-Values.json",
             "Prompt Tools/Pixaroma-Prompt-Multi-From-List.json",
             "Prompt Tools/Pixaroma-Prompt-Multi-Queue-Text.json", "Prompt Tools/Pixaroma-Prompt-Pack-Line.json",
             "Prompt Tools/Pixaroma-Prompt-Pack-Paragraph.json", "Prompt Tools/Pixaroma-Prompt-Stack.json"]:
    ex(_rel, "default", "Mitgelieferte Demo", seed=None, shot=True, use_defaults=False,
       changes="Unverändert – die Demo-Daten stecken im Workflow.")
ex("Pixaroma Node Demos/Pixaroma-Image-Compare.json", "winter", "Zwei Bilder vergleichen",
   inputs={2: LAKE, 3: "landscape_lake_winter.png"}, seed=None, shot=True, use_defaults=False)
ex("Pixaroma Node Demos/Pixaroma-LoadImage-Notify-Switch-Export-v3.json", "snow", "Laden, bearbeiten, benachrichtigen",
   inputs={239: PW}, seed=42, shot=True)
ex("Prompt Tools/Pixaroma-Switch-Value.json", "switch", "Wert umschalten", inputs={12: PW, 13: PM}, seed=None, shot=True,
   use_defaults=False)
ex("Prompt Tools/Pixaroma-Text-Overlay.json", "overlay", "Text über ein Bild legen", inputs={1: LAKE}, seed=None,
   shot=True, use_defaults=False)
ex("Prompt Tools/Pixaroma-Read-Prompt-From-Image.json", "read", "Prompt aus PNG lesen",
   inputs={1: "zimage_robot_with_metadata.png"}, seed=None, shot=True, use_defaults=False,
   input_captions={"ex_zimage_robot_with_metadata.png": "PNG aus dem Z-Image-Turbo-Beispiel (mit Workflow-Metadaten)"})
ex("Prompt Tools/Pixaroma-Find-and-Replace+ZImage.json", "bunny", "Prompt-Varianten per Suchen/Ersetzen", seed=42,
   shot=True, gates=1, changes="Der LLM-Text wird am Pause-Knoten unverändert übernommen („Continue“).")
ex("Prompt Tools/Pixaroma-XY-Plot+ZImage.json", "robot", "XY-Plot (Sampler × Schritte)", seed=42, shot=True)

# ------------------------------------------------------------------------------------------------ Live Avatar (non-realtime workflows)
ex("Live Avatar/LiveAvatar-01-SDXL-Avatar-Generation.json", "default", "Avatar-Quellbild erzeugen", seed=123456789,
   shot=True, changes="Mitgelieferter Avatar-Prompt.")
ex("Live Avatar/LiveAvatar-02-RMBG-Transparency.json", "woman", "Avatar freistellen", inputs={1: PW}, seed=None,
   shot=True, use_defaults=False)
ex("Live Avatar/LiveAvatar-10-Realistic-Adult-Character-Reference-Prompt+Image.json", "default",
   "Charakter-Referenz (bekleidet)", seed=27031991, shot=True, changes="Mitgelieferter Preset 1; der optionale Zweig bleibt aus.")
ex("Live Avatar/LiveAvatar-13-Synthetic-Character-Sheet.json", "woman", "Charakterblatt aus einem Ganzkörperfoto",
   inputs={25: FB}, seed=None, shot=True, timeout=7200)
ex("Live Avatar/LiveAvatar-15-Local-High-Realism-VRM.json", "woman", "Ganzkörperfoto → 3D-Mesh (ohne Rig)",
   inputs={2: FB}, seed=42, shot=True)

# ------------------------------------------------------------------------------------------------ NSFW category: defused examples
# User decision (2026-09-30): no nude pictures on the public page, but each example shows what the workflow does.
# The image-to-image workflows turn the generated, clothed full-body woman (fullbody_woman.png: fictional, clearly
# adult, thirties) into the same woman in a bikini instead of undressing her completely; the text-to-image ones render
# a clearly adult woman in swimwear on a beach. No nudity, no suggestive pose. Illustrious models tend to render people
# younger, so every prompt says "mature female, 35 years old" and the negatives exclude nudity and childlike looks.
# AniToReal v1 combines a fixed base prompt (node 47, explicit tags) into the positive conditioning; the example
# replaces it as well.
SAFE_NOTE = ("Entschärftes Beispiel: generierte, eindeutig erwachsene Person, Bademode statt Nacktheit; der Workflow "
             "selbst ist für die NSFW-Kategorie gedacht.")
SAFE_NEG = (", nsfw, nude, naked, topless, nipples, see-through, lingerie, underwear, sexual, child, children, teen, "
            "teenager, young girl, loli, childlike, small body")
_beach_anime = ("masterpiece, best quality, good quality, detailed face, 1woman, solo, adult woman, mature female, "
                "35 years old, tall, shoulder-length auburn hair, green eyes, dark green bikini, sandy beach, ocean, sunny "
                "day, daylight, smile, standing, cowboy shot, looking at viewer")
_beach_real = ("photo of an adult woman, 35 years old, shoulder-length auburn hair, green eyes, dark green bikini, "
               "sandy beach, ocean, sunny day, natural daylight, smile, standing, cowboy shot")


def _safe_negatives(rel: str, *node_ids: int) -> list:
    nodes = {n["id"]: n for n in wf_json(rel)["nodes"]}
    return [p for i in node_ids for p in widget(i, "text", nodes[i]["widgets_values"][0].rstrip(", ") + SAFE_NEG)]


for _rel, _p1, _p2, _base in [("NSFW/SDXL_AniToReal_v1-Image-to-Image.json", 160, 161, 47),
                              ("NSFW/SDXL_AniToReal_v2-Image-to-Image.json", 169, 170, None)]:
    ex(_rel, "beach", "Anime-Bild → realistische Version", prompts={_p1: _beach_anime, _p2: _beach_real}, seed=66,
       shot=True, changes=SAFE_NOTE,
       extra=(widget(_base, "value", _beach_anime) if _base else []) + _safe_negatives(_rel, 73, 86))
ex("NSFW/SDXL_Illustrious_v2-Text-to-Image.json", "bikini", "Bekleidete Person → Bademode", inputs={36: FB},
   prompts={66: "1woman, solo, adult, mature female, 35 years old, shoulder-length auburn hair, dark green bikini, "
                "barefoot, standing, full body, facing viewer, arms at sides, plain grey background"},
   seed=42, shot=True, changes=SAFE_NOTE, extra=_safe_negatives("NSFW/SDXL_Illustrious_v2-Text-to-Image.json", 7))
ex("NSFW/SDXL_Multi-Checkpoint_v1-Text-to-Image.json", "bikini", "Bekleidete Person → Bademode (drei Checkpoints)",
   inputs={36: FB},
   prompts={84: "photo of the same adult woman, 35 years old, shoulder-length auburn hair, dark green bikini, barefoot, "
                "standing, full body, plain grey background",
            85: "1woman, adult, mature female, 35 years old, auburn hair, dark green bikini, barefoot, standing, full body",
            86: "correct anatomy, real look, hyperrealistic, adult woman, 35 years old, auburn hair, dark green bikini, "
                "full body",
            87: "adult woman, 35 years old, auburn hair, dark green bikini, full body"}, seed=42, shot=True,
   changes=SAFE_NOTE, extra=_safe_negatives("NSFW/SDXL_Multi-Checkpoint_v1-Text-to-Image.json", 7, 14, 21))

# Image Editing · Illustrious super composite: like AniToReal v1 it mixes a hard-wired base prompt (node 47, explicit
# tags) into the positive conditioning; the example replaces it and stays clothed (this is not the NSFW category).
R = "Image Editing/SDXL_Illustrious-Super-Composite.json"
_comp_base = ("absurdres, masterpiece, best quality, good quality, detailed face, 1woman, solo, adult woman, mature female, "
              "30 years old, fully clothed")
_comp_scene = ("1woman, adult, mature female, 30 years old, shoulder-length auburn hair, dark green sweater, blue jeans, "
               "white sneakers, standing in a sunny park with trees and a lake, full body, fully clothed")
ex(R, "park", "Bild in neue Szene komponieren (16 MP)", inputs={103: FB}, seed=None, shot=True,
   prompts={141: _comp_scene, 142: "photo of " + _comp_scene + ", realistic"},
   extra=widget(47, "value", _comp_base) + _safe_negatives(R, 73, 86),
   changes="Jugendfreies Beispiel: der fest verdrahtete Basis-Prompt (Node 47) ist ersetzt, die Person bleibt bekleidet.")

# ------------------------------------------------------------------------------------------------ Templates & Tests
ex("Templates & Tests/FLUX1_vs_FLUX2-Model-Comparison.json", "robot", "FLUX.2 dev (Standardzweig)", seed=None,
   shot=True, extra=w(135, "text", "A cute small robot barista made of brushed copper and cream enamel pouring latte "
                                   "art in a cozy café, 3D render, soft studio lighting") + w(134, "noise_seed", 303),
   params={"prompt": "A cute small robot barista made of brushed copper and cream enamel pouring latte art in a cozy "
                     "café, 3D render, soft studio lighting", "seed": 303})

# ------------------------------------------------------------------------------------------------ hidden input assets from edit / TTS workflows
ex("Image Editing/FLUX2_Klein_9B_KV-One-Image-Edit-Same-Ratio.json", "asset-ball-end", "Eingabe-Asset",
   inputs={198: "physics_ball_start.png"}, group="asset", asset="physics_ball_end.png", seed=42, prompts={231: (
       "The red ball now lies on the concrete floor about one meter to the right of the bottom of the ramp, everything "
       "else unchanged")})
for _key, _text, _lang, _voice, _asset in [
    ("asset-hello-de", "Hallo! Schön, dich zu sehen.", "German", "A warm, friendly female voice in her thirties, clear "
     "German pronunciation, natural pace", "hello_de_short.mp3"),
    ("asset-hello-en", "Hi! Great to see you too.", "English", "A deep, calm male voice in his forties, warm and relaxed",
     "hello_en_short.mp3")]:
    ex("Voice Design/QwenTTS_VoiceDesign-Voice-Generation.json", _key, "Eingabe-Asset", prompts={10: _voice}, seed=None,
       group="asset", asset=_asset, extra=w(2, "text", _text) + w(2, "language", _lang) + w(2, "seed", 7))

# ------------------------------------------------------------------------------------------------ two-speaker talking video
_talk = ("Two people sit at a podcast table and talk to each other: first the woman on the left greets, then the man "
         "on the right answers, natural lip movement, small head movements, static camera")
ex("Talking Video/WAN21_InfiniteTalk-Multi-Speaker.json", "podcast", "Bild + zwei Stimmen → Gespräch",
   inputs={32: "podcast_two_mask_left.png", 137: "podcast_two_mask_right.png", 24: "hello_de_short.mp3",
           90: "hello_en_short.mp3"}, prompts={214: _talk}, seed=42, shot=True,
   input_captions={"ex_podcast_two_mask_left.png": "Bild + Maske Sprecherin (links)",
                   "ex_podcast_two_mask_right.png": "Maske Sprecher (rechts)",
                   "ex_hello_de_short.mp3": "Stimme 1", "ex_hello_en_short.mp3": "Stimme 2"})
ex("Live Avatar/LiveAvatar-14-Local-Hunyuan3D-Multiview-Mesh-Unrigged.json", "woman",
   "Charakterblatt (Workflow 13) → 3D-Mesh aus vier Ansichten", seed=42, shot=True,
   changes="Liest die neuesten Ansichten aus dem Charakterblatt-Beispiel (Workflow 13).")
