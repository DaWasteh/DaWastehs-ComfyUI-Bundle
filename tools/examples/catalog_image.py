"""Gallery examples: image editing, inpainting, outpainting, fusion, upscaling, utilities, character consistency, batch."""
from __future__ import annotations

from pathlib import Path

from catalog import Example, add, p_seed, top_nodes, wf_json

MEDIA_WIDGET = {"LoadImage": "image", "PixaromaLoadImage": "image", "AILab_LoadImage": "image",
                "DaWAdaptiveLoadImage": "image", "PixaromaPromptReader": "image", "LoadAudio": "audio",
                "LoadAudioUI": "audio", "DaWH3LoadAudioAutoLength": "audio", "LoadVideo": "file",
                "DaWAdaptiveLoadVideo": "file", "VHS_LoadVideo": "video", "DaWLoadVideoBatches": "video",
                "DaWVideoFrames": "video", "DaWMV2Planner": "song"}


def node(rel: str, node_id: int) -> dict:
    for n in wf_json(rel).get("nodes", []):
        if n["id"] == node_id:
            return n
    raise KeyError(f"{rel}: node {node_id}")


def media(rel: str, inputs: dict) -> tuple[list, dict]:
    """inputs: {node_id: asset file name} -> (patches, uploads). Input files are named ex_<asset>."""
    patches, uploads = [], {}
    for node_id, asset in inputs.items():
        widget = MEDIA_WIDGET[node(rel, node_id)["type"]]
        name = "ex_" + asset
        patches.append({"select": {"id": node_id, "path": ""}, "widget": widget, "value": name})
        uploads[asset] = name
    return patches, uploads


def prompt(node_id: int, text: str) -> list:
    return [{"select": {"id": node_id, "path": ""}, "prompt": text}]


def widget(node_id: int, name: str, value) -> list:
    return [{"select": {"id": node_id, "path": ""}, "widget": name, "value": value}]


def unmute(rel: str, keep_muted=()) -> list:
    return [{"select": {"id": n["id"], "path": ""}, "mode": 0} for n in wf_json(rel)["nodes"]
            if n.get("mode", 0) == 2 and n["id"] not in keep_muted]


def ex(rel: str, key: str, title: str, *, inputs: dict | None = None, prompts: dict | None = None,
       extra: list | None = None, seed: int | None = 7, params: dict | None = None, shot: bool = False,
       captions: dict | None = None, input_captions: dict | None = None, show: list | None = None,
       changes: str | None = None, timeout: int = 5400, asset: str | None = None, asset_node: str | None = None,
       show_texts: list | None = None, use_defaults: bool = True, gates=0, variant: str | None = None,
       group: str = "image") -> Example:
    patches, uploads = media(rel, inputs or {})
    shown = dict(params or {})
    for node_id, text in (prompts or {}).items():
        patches += prompt(node_id, text)
        shown.setdefault("prompt", text)
    patches += extra or []
    if seed is not None:
        patches += p_seed(rel, seed)
        shown.setdefault("seed", seed)
    e = Example(workflow=rel, key=key, title=title, patches=patches, params=shown, uploads=uploads, shot=shot,
                captions=captions or {}, input_captions=input_captions or {}, show=show or [], changes=changes,
                timeout=timeout, asset=asset, asset_node=asset_node, show_texts=show_texts or [],
                use_defaults=use_defaults, group=group, gates=gates, variant=variant)
    add(e)
    return e


PW, PM, FB = "portrait_woman.png", "portrait_man.png", "fullbody_woman.png"
TEAPOT, JACKET, DOG, LAKE = "product_teapot.png", "jacket_yellow.png", "dog_photo.png", "landscape_lake.png"
KITCHEN, ROOM, CARD, ANIME, FOX = "kitchen_table.png", "living_room.png", "design_card.png", "anime_woman.png", "character_fox.png"
KEEP = ("keep the woman, her face, hair, sweater and pose exactly the same")

# ------------------------------------------------------------------------------------------------ Image Editing
R = "Image Editing/FLUX2_Klein_4B-One-Image-Edit.json"
ex(R, "bookshop", "Hintergrund tauschen", inputs={198: PW}, shot=True, prompts={226: (
    "Replace the plain grey background with a cozy bookshop interior with warm fairy lights and wooden shelves, " + KEEP)})
ex(R, "watercolor", "Stil ändern · Aquarell", inputs={198: PW}, prompts={226: (
    "Turn this photo into a loose watercolor painting with soft washes and visible paper texture, keep the composition "
    "and the woman's likeness")})
ex(R, "teapot-black", "Objekt umfärben", inputs={198: TEAPOT}, prompts={226: (
    "Change the teapot to matte black ceramic with thin gold accents, keep the shape, the bamboo handle and the white "
    "background")})

R = "Image Editing/FLUX2_Klein_4B-Two-Image-Edit.json"
ex(R, "jacket", "Kleidung aus Bild 2 anziehen", inputs={198: PW, 213: JACKET}, shot=True, prompts={234: (
    "The woman from image 1 now wears the yellow rain jacket from image 2 over her sweater, same face, same hair, same "
    "grey background, same framing")}, input_captions={"ex_" + PW: "Bild 1", "ex_" + JACKET: "Bild 2"})

R = "Image Editing/FLUX2_Klein_9B-Multi-Step-Edit.json"
ex(R, "teapot-scene", "Freistellen, einsetzen, zweimal bearbeiten", inputs={210: KITCHEN, 211: TEAPOT}, shot=True,
   prompts={295: "Place the teapot naturally on the wooden table, add a soft shadow under it that matches the morning sun",
            296: "Add thin steam rising from the spout and a small matching tea cup next to the teapot, warm morning light"},
   extra=unmute(R, keep_muted=(248, 249, 250, 251, 252)), seed=None,
   changes="Beide Klein-9B-Gruppen eingeschaltet (im ausgelieferten Workflow per „Fast Groups Muter“ aus); der Filter-Schritt bleibt aus.")

for _rel in ("Image Editing/FLUX2_Klein_9B-Pixaroma-3D-Builder-Edit.json",
             "Image Editing/FLUX2_Klein_9B-Pixaroma-Composer-Edit.json",
             "Image Editing/FLUX2_Klein_9B-Pixaroma-Paint-Edit.json"):
    ex(_rel, "default", "Mitgelieferte Szene", shot=True,
       changes="Unverändert mit der im Workflow gespeicherten Pixaroma-Szene; eigene Szenen baust du im Editor-Knoten.")

R = "Image Editing/FLUX2_Klein_9B_KV-Four-Image-Edit.json"
ex(R, "family", "Vier Bilder zu einer Szene", inputs={198: PW, 213: PM, 219: DOG, 225: KITCHEN}, shot=True,
   prompts={260: ("A warm lifestyle photograph: the woman from image 1 and the man from image 2 sit side by side at the "
                  "wooden kitchen table from image 4, the golden retriever from image 3 sits next to them, morning light, "
                  "natural smiles")})

R = "Image Editing/FLUX2_Klein_9B_KV-Image-Blend.json"
ex(R, "teapot-table", "Objekt in Hintergrund einfügen", inputs={210: KITCHEN, 211: TEAPOT}, shot=True,
   prompts={280: "Place the teapot naturally on the kitchen table, matching the light, perspective and shadows"})

R = "Image Editing/FLUX2_Klein_9B_KV-One-Image-Edit-Custom-Ratio.json"
ex(R, "anime-style", "Stil ändern · freies Seitenverhältnis", inputs={198: PW}, shot=True,
   prompts={232: "Turn the photo into a 1990s anime cel illustration with clean line art and flat shading, keep her likeness"})

R = "Image Editing/FLUX2_Klein_9B_KV-One-Image-Edit-Same-Ratio.json"
ex(R, "winter", "Jahreszeit ändern", inputs={198: LAKE}, shot=True, asset="landscape_lake_winter.png",
   prompts={231: ("Change the season to a snowy winter morning: snow on the boathouse roof, the pines and the mountains, "
                  "thin ice at the shore, keep the composition")})
ex(R, "night", "Tag → Nacht", inputs={198: LAKE}, asset="landscape_lake_night.png",
   prompts={231: ("Turn the scene into a clear night: dark blue sky with stars, a warm light in the boathouse window, "
                  "moonlight on the water, keep the composition")})

R = "Image Editing/FLUX2_Klein_9B_KV-Three-Image-Edit.json"
ex(R, "lake-trip", "Person + Jacke + Ort", inputs={198: PW, 213: JACKET, 219: LAKE}, shot=True,
   prompts={249: ("The woman from image 1 wearing the yellow rain jacket from image 2 stands on the shore of the alpine "
                  "lake from image 3, full-body travel photograph, natural light")})

R = "Image Editing/FLUX2_Klein_9B_KV-Two-Image-Edit.json"
ex(R, "dog-lake", "Motiv aus Bild 1 in die Szene aus Bild 2", inputs={198: DOG, 213: LAKE}, shot=True,
   prompts={239: ("The golden retriever from image 1 sits on the wooden jetty in front of the boathouse at the lake from "
                  "image 2, facing the camera, same warm evening light and colours as image 2, photorealistic")})

R = "Image Editing/Ming_Image_0_1_Design_INT8-Image-Edit.json"
ex(R, "herbstfest", "Texte und Motiv im Design ändern", inputs={5: CARD}, shot=True, prompts={7: (
    'Change the headline "SOMMERFEST" to "HERBSTFEST" and the date "SAMSTAG 12. JULI" to "SAMSTAG 4. OKTOBER", replace '
    'the sun with an orange maple leaf, keep the layout, fonts and colors')})

R = "Image Editing/Multi-Character-Angles-One-Click.json"
ex(R, "fox", "Acht Kamerawinkel", inputs={25: FOX}, shot=True, timeout=7200, variant="BF16", params={"idea": "angles"},
   changes="Eingabe ist die Fuchs-Figur; die acht Kamera-Anweisungen stehen fest im Workflow.")
ex(R, "fox-int8", "Acht Kamerawinkel", inputs={25: FOX}, timeout=7200, variant="INT8 ConvRot", params={"idea": "angles"},
   extra=widget(427, "unet_name", "Qwen" + chr(92) + "qwen_image_edit_2511_int8_convrot.safetensors"),
   changes="Wie BF16, aber mit qwen_image_edit_2511_int8_convrot (20,5 GB) im Feld unet_name.")

R = "Image Editing/Qwen_Image_2_1_BF16-Background-Remover.json"
ex(R, "dog", "Hund freistellen", inputs={4: DOG}, shot=True)

R = "Image Editing/Qwen_Image_2_1_BF16-Multi-Image-Edit.json"
ex(R, "jacket", "Kleidung aus Bild 2", inputs={9: PW, 10: JACKET}, shot=True, prompts={4: (
    "Keep the woman, her face and her pose in <image1> unchanged, dress her in the yellow rain jacket from <image2>, keep "
    "the grey background")})

R = "Image Editing/Qwen_Image_Edit_2509-Image-Edit.json"
ex(R, "anime-to-photo", "Anime → Foto", inputs={78: ANIME}, shot=True, extra=widget(435, "value", (
    "Turn this anime illustration into a realistic photograph of a young woman with short silver hair, green eyes, a red "
    "hoodie and black shorts, same pose, plain white studio background")),
   params={"prompt": ("Turn this anime illustration into a realistic photograph of a young woman with short silver hair, "
                      "green eyes, a red hoodie and black shorts, same pose, plain white studio background")})

R = "Image Editing/Qwen_Image_Edit_2511_Action-LoRA-Image-Edit.json"
ex(R, "wave", "Pose ändern", inputs={223: FB}, shot=True,
   prompts={275: "The woman raises her right hand and waves at the camera with a big smile, everything else unchanged"})

R = "Image Editing/SDXL_Illustrious-Face-and-Hand-Detailer.json"
ex(R, "witch", "Text → Bild mit Gesichts-/Hand-Detailer", shot=True, prompts={53: (
    "masterpiece, best quality, amazing quality, 1girl, solo, long red hair, green eyes, witch hat, dark purple dress, "
    "holding a glowing staff with both hands, forest, night, fireflies, upper body, detailed hands")})

R = "Image Editing/SDXL_Illustrious-Simple-Image-to-Image.json"
# the workflow turns anime into photos (its negative prompt excludes painting, illustration, sketch); the first example
# asked for a watercolor, got a photo anyway and a face that read younger than the adult input figure
ex(R, "photo", "Anime → Foto", inputs={25: ANIME}, shot=True, prompts={44: (
    "masterpiece, best quality, realistic photo of an adult woman in her mid-thirties, mature face, long silver hair, "
    "green eyes, red hoodie, blue jeans, white sneakers, full body, standing, plain white studio background")})

R = "Image Editing/SDXL_Illustrious-to-RealVis-Detailer-Chain.json"
ex(R, "anime-to-real", "Anime → realistisch (Kette)", inputs={25: ANIME}, shot=True,
   prompts={76: "photo of a young woman, short silver hair, green eyes, red hoodie, black shorts, sneakers, standing, full body, white studio background, realistic",
            77: "realistic skin texture, photograph, detailed face, natural light"})

# ------------------------------------------------------------------------------------------------ Image Fusion
R = "Image Fusion/Krea2_INT8_3-Reference_Fusion.json"
ex(R, "lake-walk", "Drei Referenzen verschmelzen", inputs={213: PW, 214: DOG, 215: LAKE}, shot=True, prompts={233: (
    "EDIT PICTURE 3 into one completely new, coherent photograph: the woman from picture 1 walks with the golden "
    "retriever from picture 2 along the shore of the lake in picture 3, same identities, natural morning light")},
   input_captions={"ex_" + PW: "Bild 2 · Person", "ex_" + DOG: "Bild 3 · Hund", "ex_" + LAKE: "Bild 1 · Komposition"})

# ------------------------------------------------------------------------------------------------ Inpainting / Outpainting
R = "Image Inpainting/FLUX2_Klein_4B-Inpaint.json"
ex(R, "necklace", "Maske: Halskette ergänzen", inputs={198: "portrait_woman_mask_neck.png"}, shot=True,
   prompts={229: "add a delicate pearl necklace on her neck"},
   input_captions={"ex_portrait_woman_mask_neck.png": "Bild mit Maske (Alphakanal)"})
ex(R, "hair", "Maske: Haarfarbe", inputs={198: "portrait_woman_mask_hair.png"},  # same task as 9B KV below
   prompts={229: "change her hair to platinum blonde, same haircut"},
   input_captions={"ex_portrait_woman_mask_hair.png": "Bild mit Maske (Alphakanal)"})
R = "Image Inpainting/FLUX2_Klein_9B-Pixaroma-Inpaint.json"
ex(R, "glasses", "Maske: Brille ergänzen", inputs={247: "portrait_woman_mask_eyes.png"}, shot=True,
   prompts={323: "give her round tortoiseshell glasses"}, show=["250", "257"],
   captions={"250": ["Ergebnis", "Vorher"], "257": "Generierter Ausschnitt"},
   input_captions={"ex_portrait_woman_mask_eyes.png": "Bild mit Maske (Alphakanal)"})
R = "Image Inpainting/FLUX2_Klein_9B_KV-Inpaint.json"
ex(R, "hair", "Maske: Haarfarbe", inputs={198: "portrait_woman_mask_hair.png"}, shot=True,
   prompts={236: "change her hair to platinum blonde, same haircut"},
   input_captions={"ex_portrait_woman_mask_hair.png": "Bild mit Maske (Alphakanal)"})
R = "Image Inpainting/Qwen_Image_2_1_BF16-Mask-Inpaint.json"
ex(R, "jacket", "Maske: Kleidung tauschen", inputs={6: "portrait_woman_mask_sweater.png"}, shot=True,
   prompts={9: "Change the green sweater into a red leather jacket with a silver zipper"},
   input_captions={"ex_portrait_woman_mask_sweater.png": "Bild mit Maske (Alphakanal)"})
R = "Image Outpainting/FLUX2_Klein_9B_KV-Outpaint-Custom-Ratio.json"
ex(R, "wide", "Quadrat → 16:9", inputs={198: PW}, shot=True)
ex(R, "portrait-lake", "Querformat → 9:16", inputs={198: LAKE}, extra=widget(214, "aspect_ratio", "9:16 (Portrait Widescreen)"))

# ------------------------------------------------------------------------------------------------ Upscaling
R = "Image Upscaling/Image-4x_NMKD_Siax-Model-Upscale.json"
ex(R, "portrait", "256 px → 1024 px", inputs={2: "portrait_woman_256.png"}, shot=True, seed=None)
R = "Image Upscaling/Image-Simple-Bicubic-Upscale.json"
ex(R, "portrait", "256 px → 1024 px", inputs={2: "portrait_woman_256.png"}, shot=True, seed=None)
R = "Image Upscaling/ZImage_Turbo-Tiled-Upscale.json"
ex(R, "dog", "Kachel-Upscale mit Z-Image (512 → 2048 px)", inputs={186: "dog_photo_512.png"}, shot=True)

# ------------------------------------------------------------------------------------------------ Utilities
for _rel, _key, _title, _inp in [
    ("Image Utilities/Image-Blend.json", "teapot", "Vordergrund auf Hintergrund", {25: KITCHEN, 24: TEAPOT}),
    ("Image Utilities/Image-Combiner.json", "teapot", "Bilder kombinieren", {25: KITCHEN, 24: TEAPOT}),
    ("Image Utilities/Image-Combiner-Transparent-Items.json", "fox", "Freigestelltes Objekt einsetzen", {25: LAKE, 24: FOX}),
    ("Image Utilities/Image-Compare.json", "winter", "Zwei Bilder vergleichen", {19: LAKE, 17: "landscape_lake_winter.png"}),
    ("Image Utilities/Image-Filters-Catalog.json", "lake", "Filterkatalog", {32: LAKE}),
    ("Image Utilities/Image-Filters-Example.json", "portrait", "Filter + Overlay-Textur", {11: PW, 12: KITCHEN}),
    ("Image Utilities/Image-Scale.json", "lake", "Skalieren (vier Methoden)", {2: LAKE}),
    ("Image Utilities/Image-Stitch.json", "portraits", "Zwei Bilder zusammensetzen", {10: PW, 11: PM}),
    ("Image Utilities/Image-Transformation.json", "dog", "Drehen/Spiegeln/Zuschneiden", {2: DOG}),
    ("Image Utilities/Lama-Object-Remover.json", "plant", "Objekt entfernen (LaMa)", {1: "living_room_mask_plant.png"}),
    ("Image Utilities/Remove-Background-RMBG.json", "dog", "Hintergrund entfernen (RMBG-2.0)", {1: DOG}),
    ("Image Utilities/Remove-Background-Transparent-Items.json", "teapot", "Freisteller für Objekte", {1: TEAPOT}),
]:
    ex(_rel, _key, _title, inputs=_inp, shot=True, seed=None, use_defaults=False)

R = "Image Utilities/Ming_Image_0_1_Design_Layer_INT8-Layer-Decompose.json"
ex(R, "card", "Design in Ebenen zerlegen", inputs={5: CARD}, shot=True,
   prompts={7: "Layer 1: all text\nLayer 2: smiling sun illustration\nLayer 3: balloons\nLayer 4: background"})

# ------------------------------------------------------------------------------------------------ Character & Consistency
R = "Character & Consistency/FLUX1_Kontext-Character-Keep.json"
ex(R, "tokyo", "Gleiche Person, neue Szene", inputs={4: PW}, shot=True, prompts={28: (
    "The same woman stands in a busy Tokyo street at night with colorful neon signs behind her, keep her face, hair and "
    "green sweater identical, photographic style")})
R = "Character & Consistency/SDXL_IPAdapter-Character-Keep.json"
ex(R, "beach", "Referenzgesicht, neue Szene", inputs={2: PW}, shot=True, prompts={63: (
    "photo of the same woman, auburn shoulder-length hair, walking on a beach at sunset, light summer dress, smiling, "
    "same face")})
R = "Character & Consistency/SDXL_IPAdapter_FaceID-Character-Keep.json"  # needs insightface (v1.3.1 updater pin)
ex(R, "cafe", "FaceID, neue Szene", inputs={25: PW}, shot=True,
   prompts={107: "photo of a woman sitting in a cozy café with a cup of coffee, auburn hair, smiling, warm light",
            108: "1girl, cafe, coffee cup, smile, auburn hair, sweater"},
   captions={"67": "Gesichtsausschnitt (FaceID-Eingang)"})

# ------------------------------------------------------------------------------------------------ Batch Processing
_BATCH = {"version": 1, "folder": "L:/ComfyUI/tmp/examples-v131/input/batch_demo", "recursive": False,
          "keepFolders": False, "sort": "name", "sort_dir": "asc", "mode": "max_mp", "max_mp": 1.0,
          "longest_side": 1024, "scale_factor": 1.0, "fit_w": 1024, "fit_h": 1024, "cover_w": 1024, "cover_h": 1024,
          "ratio_preset": "1:1", "ratio_w": 1, "ratio_h": 1, "ratio_action": "crop", "pad_color": "#808080",
          "pad_top": 0, "pad_bottom": 0, "pad_left": 0, "pad_right": 0, "crop_anchor": "center", "crop_scale": True,
          "snap": 0, "resample": "auto", "allow_upscale": True}
_BATCH_FILES = {PW: "batch_demo/01_portrait.png", DOG: "batch_demo/02_dog.png", TEAPOT: "batch_demo/03_teapot.png"}
_BATCH["selected"] = [Path(v).name for v in _BATCH_FILES.values()]  # "Pick images": all three
import json as _json  # noqa: E402

R = "Batch Processing/FLUX2_Klein_9B-Batch-Image-Edit.json"
_e = ex(R, "winter", "Ein Prompt für einen ganzen Ordner", shot=True, seed=None,
        prompts={253: ("Replace the background with a snowy winter landscape with soft falling snow, keep the main subject "
                       "identical and keep the same framing")},
        extra=[{"select": {"id": 239, "path": ""}, "props": {"loadImagesFolderState": _json.dumps(_BATCH)}}],
        changes="Ordner mit drei Beispielbildern (Porträt, Hund, Teekanne); jedes Bild wird nacheinander bearbeitet.")
_e.uploads.update(_BATCH_FILES)
R = "Batch Processing/Load-Images-From-Folder-and-Crop.json"
_crop = dict(_BATCH, mode="ratio", ratio_preset="16:9", ratio_w=16, ratio_h=9, ratio_action="crop")
_e = ex(R, "crop", "Ordner laden und auf 16:9 zuschneiden", shot=True, seed=None, use_defaults=False,
        extra=[{"select": {"id": 240, "path": ""}, "props": {"loadImagesFolderState": _json.dumps(_crop)}}],
        changes="Ordner mit drei Beispielbildern, Zuschnitt 16:9 aus der Mitte.")
_e.uploads.update(_BATCH_FILES)
