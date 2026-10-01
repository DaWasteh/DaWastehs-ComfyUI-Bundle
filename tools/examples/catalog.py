"""The example catalog of the gallery: which workflow runs with which prompt, seed, size and inputs.

Patches are generated from the workflow file itself (prompt node, latent/size nodes, seed widgets), so a catalog entry
only names the idea. Keys are stable ids inside one workflow; the first example with ``shot=True`` becomes the
screenshot and the main example of the workflow page.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / "workflows"


@dataclass
class Example:
    workflow: str
    key: str
    title: str
    patches: list = field(default_factory=list)
    params: dict = field(default_factory=dict)
    uploads: dict = field(default_factory=dict)  # asset path (relative to assets/) -> input file name
    group: str = ""
    shot: bool = False
    shot_opts: dict = field(default_factory=dict)
    timeout: int = 5400
    gates: int = 0
    prepare: Callable | None = None
    # gallery presentation
    variant: str | None = None          # label inside a group of related examples (e.g. a size)
    show: list = field(default_factory=list)          # node ids whose files are shown (default: saved outputs)
    captions: dict = field(default_factory=dict)      # node id -> caption (or one caption per file)
    show_texts: list = field(default_factory=list)    # node ids whose text outputs are shown (default: all)
    input_captions: dict = field(default_factory=dict)
    text_inputs: list = field(default_factory=list)   # [{"caption": ..., "text": ...}]
    changes: str | None = None          # what differs from the shipped workflow besides prompt/seed/size
    use_defaults: bool = False          # show the workflow's sampler settings next to the example params
    asset: str | None = None            # copy the output to assets/<name> (input for other examples)
    asset_node: str | None = None


CATALOG: list[Example] = []

# ---------------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------------
SIZE_TYPES = {"EmptyLatentImage", "EmptySD3LatentImage", "EmptyFlux2LatentImage", "ModelSamplingFlux", "Flux2Scheduler",
              "EmptyHunyuanLatentVideo", "EmptyChromaRadianceLatentImage"}
SEED_WIDGETS = {"KSampler": "seed", "KSamplerAdvanced": "noise_seed", "RandomNoise": "noise_seed",
                "SamplerCustom": "noise_seed", "FaceDetailer": "seed"}
_cache: dict[str, dict] = {}


def wf_path(rel: str) -> Path:
    """Catalog entries keep the v1.3.0 names; after the v1.3.1 rename the file is found through the rename map."""
    if (WF / rel).exists():
        return WF / rel
    renames = json.loads((ROOT / "tools" / "workflow_renames_v131.json").read_text(encoding="utf-8"))["renames"]
    return WF / renames.get(rel, rel)


def wf_json(rel: str) -> dict:
    if rel not in _cache:
        _cache[rel] = json.loads(wf_path(rel).read_text(encoding="utf-8"))
    return _cache[rel]


def top_nodes(rel: str, types=None, active=True):
    for node in wf_json(rel).get("nodes", []):
        if types and node["type"] not in types:
            continue
        if active and node.get("mode", 0) in (2, 4):
            continue
        yield node


def prompt_nodes(rel: str, title_re: str | None = None):
    nodes = [n for n in top_nodes(rel, {"PixaromaPrompt"})
             if not re.search(r"NEGATIV|NEGATIVE", n.get("title") or "", re.I)]
    if title_re:
        nodes = [n for n in nodes if re.search(title_re, n.get("title") or "", re.I)]
    return nodes


def p_prompt(rel: str, text: str, title_re: str | None = None) -> list:
    nodes = prompt_nodes(rel, title_re)
    if len(nodes) != 1:
        raise ValueError(f"{rel}: expected one prompt node, found {[(n['id'], n.get('title')) for n in nodes]}")
    return [{"select": {"id": nodes[0]["id"], "path": ""}, "prompt": text}]


def p_size(rel: str, width: int, height: int) -> list:
    out = []
    for node in top_nodes(rel, SIZE_TYPES):
        out.append({"select": {"id": node["id"], "path": ""}, "widget": "width", "value": width})
        out.append({"select": {"id": node["id"], "path": ""}, "widget": "height", "value": height})
    if not out:
        raise ValueError(f"{rel}: no size node")
    return out


def p_seed(rel: str, seed: int) -> list:
    out = []
    for node in top_nodes(rel, set(SEED_WIDGETS)):
        out.append({"select": {"id": node["id"], "path": ""}, "widget": SEED_WIDGETS[node["type"]], "value": seed})
    return out


def add(ex: Example) -> None:
    if any(e.workflow == ex.workflow and e.key == ex.key for e in CATALOG):
        raise ValueError(f"duplicate {ex.workflow} {ex.key}")
    CATALOG.append(ex)


# ---------------------------------------------------------------------------------------------------------------------
# Text to Image: four ideas (photo, painting, 3D render, lettering) x three sizes with the same seed
# ---------------------------------------------------------------------------------------------------------------------
T2I_IDEAS = [
    {
        "id": "portrait", "title": "Porträtfoto · Leuchtturmwärter", "seed": 101,
        "text": ("Close-up portrait photograph of an elderly lighthouse keeper with a weathered, wrinkled face and a "
                 "short grey beard, wearing a navy blue knit sweater and a dark wool cap, soft window light from the "
                 "left, shallow depth of field, 85 mm lens, natural skin texture, calm expression"),
        "tags": ("1boy, solo, old man, grey beard, wrinkled skin, lighthouse keeper, navy blue sweater, knit cap, "
                 "portrait, upper body, window light, looking to the side, calm, realistic"),
    },
    {
        "id": "fantasy", "title": "Fantasy-Gemälde · Stadt über den Wolken", "seed": 202,
        "text": ("A floating island city high above the clouds at golden hour, white stone towers and arched bridges, "
                 "waterfalls pouring off the island edges into the clouds, two wooden airships with canvas sails, "
                 "warm sunlight, highly detailed fantasy digital painting"),
        "tags": ("scenery, no humans, floating island, sky city, white towers, stone bridge, waterfall, clouds, "
                 "airship, golden hour, sunset, fantasy, detailed background"),
    },
    {
        "id": "robot", "title": "3D-Render · Roboter-Barista", "seed": 303,
        "text": ("A cute small robot barista made of brushed copper and cream enamel with big round glowing eyes, "
                 "carefully pouring latte art into a cappuccino cup on a wooden café counter, cozy café in the "
                 "background, 3D render, soft studio lighting, pastel colors"),
        "tags": ("no humans, robot, cute, copper robot, glowing eyes, barista, latte art, cappuccino, coffee cup, "
                 "cafe, wooden counter, indoors, 3d, pastel colors, soft lighting"),
    },
    {
        "id": "poster", "title": "Schrift · Reiseplakat „ALPENBAHN“", "seed": 404,
        "text": ('Vintage 1920s travel poster for a mountain railway, bold art deco lettering at the top that reads '
                 '"ALPENBAHN" and smaller text at the bottom that reads "SEIT 1926", a red steam train crossing a '
                 'stone viaduct, snowy alpine peaks, flat colors, lithograph print texture'),
        "tags": ('poster, vintage, art deco, text "ALPENBAHN", red train, steam locomotive, viaduct, snowy mountains, '
                 'alps, flat color, lithograph, no humans'),
    },
]

TAG_PREFIX = {
    "illustrious": "masterpiece, best quality, amazing quality, ",
    "pony": "score_9, score_8_up, score_7_up, ",
}

SIZES = {
    "sd15": [(512, 512), (768, 768), (1024, 1024)],
    "1mp": [(768, 768), (1024, 1024), (1536, 1536)],
    "2k": [(1024, 1024), (1536, 1536), (2048, 2048)],
}
NATIVE = {"sd15": (512, 512), "1mp": (1024, 1024), "2k": (1024, 1024)}

# file, prompt style, size class, speed ("fast" = every idea at every size, "slow" = sizes only for two ideas)
T2I = [
    ("Text to Image/Anima_base_v1-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/Anima_hosekiLustrousmix_v10-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/Boogu_image_base-Text-to-Image.json", "text", "1mp", "slow"),
    ("Text to Image/Boogu_turbo_via_LoRA-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/Cosmos_Predict2_2B-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX1_EclecticEuphoria_Distilled_v2-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX1_EclecticEuphoria_Libre_v2-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX1_Kontext_dev-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX1_dev_Q6_K-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX1_dev_abliterated_Q8-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX1_dev_fp8-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX2_Klein_4b-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX2_Klein_9b_Q6_K-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX2_Klein_9b_dare_merged-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX2_Klein_9b_kv_fp8-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX2_Klein_base_4b-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/FLUX2_dev_Q6_K-Text-to-Image.json", "text", "1mp", "slow"),
    ("Text to Image/FLUX2_dev_fp8mixed-Text-to-Image.json", "text", "1mp", "slow"),
    ("Text to Image/FLUX2_dev_fp8mixed_v2-Text-to-Image.json", "text", "1mp", "slow"),
    ("Text to Image/Krea2_raw-Text-to-Image.json", "text", "1mp", "slow"),
    ("Text to Image/Krea2_turbo-Extra-Pass-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/Krea2_turbo-Low-VRAM-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/Krea2_turbo_via_LoRA-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/LongCat_image-Text-to-Image.json", "text", "1mp", "slow"),
    ("Text to Image/LongCat_image_turbo-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/Qwen_Image_2_1_BF16-Text-to-Image.json", "text", "2k", "slow"),
    ("Text to Image/SD15_v1-5-pruned-emaonly-Text-to-Image.json", "text", "sd15", "fast"),
    ("Text to Image/SD21_wd-1-5-beta2-unclip-Text-to-Image.json", "text", "sd15", "fast"),
    ("Text to Image/SDXL_EclecticEuphoria_Illus_Real_v3-Text-to-Image.json", "illustrious", "1mp", "fast"),
    ("Text to Image/SDXL_EclecticEuphoria_Illustrious_v2-Text-to-Image.json", "illustrious", "1mp", "fast"),
    ("Text to Image/SDXL_NoobAI_XL_v1_1-Text-to-Image.json", "illustrious", "1mp", "fast"),
    ("Text to Image/SDXL_RealVisXL_V4-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/SDXL_animij_v8-Text-to-Image.json", "illustrious", "1mp", "fast"),
    ("Text to Image/SDXL_moodyRealMix_zitV4DPO-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/SDXL_novaAnimeXL_ilV190-Text-to-Image.json", "illustrious", "1mp", "fast"),
    ("Text to Image/SDXL_oneObsession_v20Bold-Text-to-Image.json", "illustrious", "1mp", "fast"),
    ("Text to Image/SDXL_ponyDiffusionV6XL-Text-to-Image.json", "pony", "1mp", "fast"),
    ("Text to Image/SDXL_ultrarealFineTune_v4-Text-to-Image.json", "text", "1mp", "fast"),
    ("Text to Image/ZImage_base-Text-to-Image.json", "text", "1mp", "slow"),
    ("Text to Image/ZImage_turbo-Text-to-Image.json", "text", "1mp", "fast"),
]
MAIN_IDEA = "robot"


def idea_prompt(idea: dict, style: str) -> str:
    if style == "text":
        return idea["text"]
    return TAG_PREFIX[style] + idea["tags"]


def t2i_examples(rel: str, style: str, size_class: str, speed: str, title_re: str | None = None) -> None:
    native = NATIVE[size_class]
    ideas = sorted(T2I_IDEAS, key=lambda i: i["id"] != MAIN_IDEA)
    runs = [(idea, native) for idea in ideas]
    for idea in ideas:
        if speed == "slow" and idea["id"] not in ("portrait", MAIN_IDEA):
            continue
        runs += [(idea, size) for size in SIZES[size_class] if size != native]
    for idea, (w, h) in runs:
        prompt = idea_prompt(idea, style)
        patches = p_prompt(rel, prompt, title_re) + p_size(rel, w, h) + p_seed(rel, idea["seed"])
        main = idea["id"] == MAIN_IDEA and (w, h) == native
        add(Example(
            workflow=rel, key=f"{idea['id']}-{w}x{h}", title=idea["title"], patches=patches,
            params={"prompt": prompt, "seed": idea["seed"], "width": w, "height": h, "idea": idea["id"]},
            group="t2i", shot=main))


for _rel, _style, _size, _speed in T2I:
    t2i_examples(_rel, _style, _size, _speed, title_re="PHYSICS" if "Cosmos" in _rel else None)


# ---------------------------------------------------------------------------------------------------------------------
# Input assets: generated with bundle workflows (no third-party photos, voices or songs). Not shown as gallery examples.
# ---------------------------------------------------------------------------------------------------------------------
ZIT = "Text to Image/ZImage_turbo-Text-to-Image.json"
NOOB = "Text to Image/SDXL_NoobAI_XL_v1_1-Text-to-Image.json"
ASSET_IMAGES = [
    (ZIT, "portrait_woman.png", 1024, 1024, 11,
     "Studio portrait photograph of a friendly woman in her thirties with shoulder-length auburn hair, wearing a dark "
     "green knit sweater, looking directly at the camera with a gentle closed-mouth smile, plain light grey background, "
     "soft even lighting, head and shoulders, sharp focus, natural skin texture"),
    (ZIT, "portrait_man.png", 1024, 1024, 12,
     "Studio portrait photograph of a calm man in his forties with short dark hair and a trimmed beard, wearing a navy "
     "blue shirt, looking directly at the camera, plain light grey background, soft even lighting, head and shoulders, "
     "sharp focus, natural skin texture"),
    (ZIT, "fullbody_woman.png", 832, 1216, 13,
     "Full-body photograph of a woman in her thirties with shoulder-length auburn hair, dark green knit sweater, blue "
     "jeans and white sneakers, standing upright facing the camera, arms relaxed and slightly away from the body, "
     "whole body from head to shoes visible, plain light grey studio background, even soft lighting"),
    (ZIT, "product_teapot.png", 1024, 1024, 14,
     "Product photograph of a glossy turquoise ceramic teapot with a curved bamboo handle, centered, isolated on a pure "
     "white background, soft contact shadow, studio lighting, sharp focus"),
    (ZIT, "asset_chest.png", 1024, 1024, 15,
     "A stylized fantasy wooden treasure chest with iron bands and a golden lock, slightly open with gold coins inside, "
     "game asset, centered, isolated on a plain white background, three-quarter view, soft even lighting, no shadow"),
    (ZIT, "asset_house.png", 1024, 1024, 16,
     "A small medieval timber-frame cottage with white plaster walls, dark wooden beams, a red tiled roof and a stone "
     "chimney, game asset, centered, isolated on a plain white background, three-quarter view from slightly above, "
     "soft even lighting"),
    (ZIT, "character_fox.png", 1024, 1024, 17,
     "A cute cartoon fox adventurer character standing upright on two legs, orange fur, green scarf and brown leather "
     "boots, full body, front view, arms slightly away from the body, game character, isolated on a plain white "
     "background, 3D render, soft even lighting"),
    (ZIT, "living_room.png", 1024, 1024, 18,
     "Photograph of a bright modern living room seen from the entrance: a grey fabric sofa against the wall, a round "
     "wooden coffee table in front of it, a black floor lamp, a large potted fiddle-leaf fig plant, a television on a "
     "low white sideboard, light oak floor, soft daylight from a large window"),
    (ZIT, "landscape_lake.png", 1344, 768, 19,
     "Landscape photograph of a calm alpine lake at sunrise, a small wooden boathouse on the shore, dark pine trees and "
     "snowy mountains reflected in the still water, soft golden light, light morning mist"),
    (ZIT, "kitchen_table.png", 1024, 1024, 20,
     "Photograph of an empty rustic wooden kitchen table in front of a sunny window, blurred green garden outside, warm "
     "morning light, nothing on the table, eye-level view"),
    (ZIT, "jacket_yellow.png", 1024, 1024, 21,
     "Product photograph of a bright yellow hooded rain jacket laid flat, front view, isolated on a plain white "
     "background, even studio lighting"),
    (ZIT, "dog_photo.png", 1024, 1024, 22,
     "Photograph of a happy golden retriever sitting on green grass in a park, looking at the camera, natural daylight, "
     "shallow depth of field"),
    ("Text to Image/Qwen_Image_2_1_BF16-Text-to-Image.json", "design_card.png", 1024, 1024, 23,
     'Flat vector graphic design of a summer party invitation card, pastel yellow background, a large bold headline '
     'that reads "SOMMERFEST", below it smaller text that reads "SAMSTAG 12. JULI", an illustrated smiling sun in the '
     'top right corner and three colorful balloons on the left, clean modern layout'),
    (ZIT, "physics_ball_start.png", 1024, 576, 25,
     "Photograph of a small wooden ramp standing on a grey concrete floor in front of a plain white wall, a shiny red "
     "rubber ball resting at the top of the ramp, soft daylight from the left, locked-off wide shot, nothing else in "
     "the room"),
    (ZIT, "podcast_two.png", 1344, 768, 26,
     "Photograph of a small podcast studio: on the left a friendly woman in her thirties with shoulder-length auburn "
     "hair and a dark green sweater, on the right a calm man in his forties with short dark hair, a trimmed beard and a "
     "navy blue shirt, both sit at a wooden table with microphones and face the camera, clearly separated, warm soft "
     "light, acoustic panels in the background"),
    # clearly adult: realistic re-renders (anime -> photo) and the dance/replace videos start from this figure
    (NOOB, "anime_woman.png", 832, 1216, 24,
     "masterpiece, best quality, amazing quality, 1woman, solo, adult woman, mature female, 25 years old, tall, long "
     "silver hair, green eyes, red hoodie, blue jeans, sneakers, smile, standing, full body, looking at viewer, simple "
     "background, white background"),
]
for _rel, _name, _w, _h, _seed, _prompt in ASSET_IMAGES:
    add(Example(workflow=_rel, key="asset-" + _name.removesuffix(".png").replace("_", "-"), title="Eingabe-Asset",
                patches=p_prompt(_rel, _prompt) + p_size(_rel, _w, _h) + p_seed(_rel, _seed),
                params={"prompt": _prompt, "seed": _seed, "width": _w, "height": _h}, group="asset", asset=_name))


# Category modules register their examples on import.
import catalog_image  # noqa: E402,F401
import catalog_video  # noqa: E402,F401
import catalog_audio  # noqa: E402,F401
import catalog_misc  # noqa: E402,F401
