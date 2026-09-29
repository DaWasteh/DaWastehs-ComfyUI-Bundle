"""Pure helpers for the v1.3.0 image prompt enhancer (no ComfyUI import, unit-testable).

The enhancer turns a rough draft into the finished prompt for an image model. The system prompt is assembled from a
common rule block, one target block (which family of image models the prompt is for), a length rule and a language rule;
answers are cleaned (labels, fences, quotes, line breaks) and checked before they are used. Everything that talks to the
model goes through llm_backend.LlamaServer of the H3-MusicVideo pack (Qwen3.8 27B GGUF via llama.cpp).
"""
from __future__ import annotations

import re

TARGET_NATURAL = "Fließtext (Z-Image, FLUX, Qwen Image, Krea)"
TARGET_TEXT = "Text im Bild (Poster, Logo, Schild)"
TARGET_TAGS = "Tags (SDXL, Pony, Illustrious)"
TARGET_EDIT = "Bearbeiten (Anweisung für Edit-Modelle)"
TARGETS = [TARGET_NATURAL, TARGET_TEXT, TARGET_TAGS, TARGET_EDIT]
DETAILS = ["kurz", "mittel", "ausführlich"]
LANGUAGES = ["English", "Deutsch", "wie der Entwurf"]
DEFAULT_TARGET, DEFAULT_DETAIL, DEFAULT_LANGUAGE = TARGET_NATURAL, "mittel", "English"

COMMON_RULES = """You are the prompt writer of a local AI image generator. The user gives you a rough draft; you turn it into the finished prompt that is sent to the image model.

Rules:
- Output only the finished prompt: no preface, no label, no quotation marks around it, no markdown, no explanation, no alternatives.
- Keep everything the draft asks for: every subject, the number of people or objects, colours, style, mood, place and every text that has to be shown. Never contradict the draft and never change its main subject.
- Fill the gaps with concrete choices that fit the draft and can be seen in the image: setting, materials, light, colours, composition. Decide; never write "or", "maybe" or "such as".
- Do not add a new main subject, a brand, the name of a real person or any text in the image that the draft did not ask for.
- If the draft is already detailed, keep its details and only sharpen the wording; do not pad it.
- Do not add comments, warnings or disclaimers."""

TARGET_RULES = {
    TARGET_NATURAL: """Target: a natural-language prompt for modern text-to-image models (Z-Image, FLUX, Qwen Image, Krea).
Format: one continuous paragraph of full descriptive sentences. No lists, no tags, no line breaks, no headings.
Order: the main subject with pose, action and expression first; then clothing, materials and details; then the setting and background; then light and colour; then framing, camera angle and lens; then the medium or style and the mood.
Style: use the style the draft names (photograph, illustration, anime, oil painting, 3D render, ...) and describe it with that medium's vocabulary. If the draft names none, choose what suits the subject and default to a realistic photograph, described like a photographer would (camera, lens, light).
Describe what is visible, in the positive. No negations ("no", "without"), no quality buzzwords (masterpiece, 8k, ultra detailed, trending on artstation) and no "image of" or "picture of".
If the draft or the notes exclude something (no people, no text), do not name it, because image models tend to draw what the prompt mentions: describe the scene without it instead (a deserted street, an empty room, a bare wall).""",
    TARGET_TEXT: """Target: a prompt for a design with lettering (poster, logo, sign, packaging, book cover, UI, sticker) for models that render text well (Qwen Image, Ideogram).
Format: one continuous paragraph of descriptive sentences, no lists, no line breaks.
Order: first what the piece is, its format and layout; then the background, colour palette and mood; then each text element in reading order: its exact wording in double quotes, where it sits and how the lettering looks (typeface style, weight, size relative to the other texts, colour, effects); then illustrations, icons or photos and where they sit; finally the material or rendering style (flat vector, screen print, embossed, neon, ...).
Every text that has to appear is copied character by character from the draft, in double quotes, in its original language and spelling. If the draft names no text, do not invent one: describe a design without lettering. Keep the amount of text small.
If the draft or the notes exclude something ("no photos", "without people"), do not name it and do not write "without": image models tend to draw what the prompt mentions. Describe only what the design consists of (pure typography on a flat yellow ground).""",
    TARGET_TAGS: """Target: a tag prompt for SDXL-family models (SDXL, Pony, Illustrious; Danbooru-style tags).
Format: lowercase English tags separated by ", " on a single line. No sentences, no line breaks, no weights, no brackets, no negatives.
Order: quality tags first (masterpiece, best quality, highly detailed), then subject and count in the Danbooru forms (1girl, 1boy, 2girls, solo, ...), then appearance, clothing and pose, then the setting, then light and colour, then camera or framing tags, then the style tags.
Use common short tags instead of long phrases and never repeat a tag. A short text that has to appear in the image stays in double quotes; longer texts are dropped.""",
    TARGET_EDIT: """Target: an instruction for an image-editing model. The model receives the input image together with your text; you see the same image when one is attached.
Format: plain imperative sentences, no lists, no line breaks.
Say exactly what to change and name the element the way it looks in the input image ("the green sweater", "the sign above the door"). Describe the new element concretely: colour, material, shape, position. Then state what stays untouched, and only name parts that really are in the picture ("Keep the face, the pose and the background exactly as they are." for a portrait, "Keep the lettering style and everything else exactly as it is." for a sign).
For a text change give the old and the new text in double quotes.
Do not describe the whole image again. If no image is attached, work from the draft alone and close with "Keep everything else exactly as it is.".""",
}

LENGTH_RULES = {
    TARGET_NATURAL: {"kurz": "about 40 to 70 words", "mittel": "about 90 to 140 words", "ausführlich": "about 180 to 260 words"},
    TARGET_TEXT: {"kurz": "about 60 to 100 words", "mittel": "about 110 to 170 words", "ausführlich": "about 200 to 280 words"},
    TARGET_TAGS: {"kurz": "about 15 to 25 tags", "mittel": "about 25 to 40 tags", "ausführlich": "about 40 to 60 tags"},
    TARGET_EDIT: {"kurz": "one or two short sentences (the change and what stays)", "mittel": "two to three sentences",
                  "ausführlich": "up to five sentences, with more detail about the new element and how it blends in (light, shadow, perspective)"},
}
# Smallest answer that counts as complete: words (tags: tags) per target and detail level. The sampler occasionally
# draws a wrong first token and the model then ends its answer right there (v1.2.5), so short ones are retried.
MIN_SIZE = {
    TARGET_NATURAL: {"kurz": 20, "mittel": 45, "ausführlich": 90},
    TARGET_TEXT: {"kurz": 25, "mittel": 50, "ausführlich": 100},
    TARGET_TAGS: {"kurz": 8, "mittel": 14, "ausführlich": 24},
    TARGET_EDIT: {"kurz": 4, "mittel": 8, "ausführlich": 12},
}
LANGUAGE_RULES = {
    "English": "Write the prompt in English. Texts that have to appear in the image stay exactly as the draft spells them.",
    "Deutsch": "Write the prompt in German. Texts that have to appear in the image stay exactly as the draft spells them.",
    "wie der Entwurf": "Write the prompt in the language of the draft. Texts that have to appear in the image stay exactly as the draft spells them.",
}
TAGS_LANGUAGE = "The tags are always English, whatever language the draft is in."

REFUSALS = re.compile(r"^\W*(i can(?:'|’)?t|i cannot|i(?:'|’)m sorry|i am sorry|sorry[,.! ]|i(?:'|’)m unable|i am unable|as an ai)", re.I)
LABEL = re.compile(r"^\W*(?:final |finished |enhanced |image |edit |rewritten )?(?:prompt|instruction|tags)\s*[:：\-–]\s*", re.I)
FENCE = re.compile(r"```[a-zA-Z]*\s*(.*?)\s*```", re.S)
END_MARKS = ".!?…)]}\"'”’»。"


def check_options(target: str, detail: str, language: str) -> None:
    for value, options, name in ((target, TARGETS, "target"), (detail, DETAILS, "detail"), (language, LANGUAGES, "language")):
        if value not in options:
            raise ValueError(f"unbekannter Wert für {name}: {value!r} (erlaubt: {', '.join(options)})")


def system_prompt(target: str, detail: str, language: str) -> str:
    check_options(target, detail, language)
    language_rule = TAGS_LANGUAGE if target == TARGET_TAGS else LANGUAGE_RULES[language]
    return "\n\n".join([COMMON_RULES, TARGET_RULES[target], f"Length: {LENGTH_RULES[target][detail]}. Stay inside that range.", language_rule])


def user_message(draft: str, notes: str = "", has_image: bool = False, target: str = TARGET_NATURAL) -> str:
    draft = (draft or "").strip()
    if not draft:
        raise ValueError("Bitte einen Entwurf eingeben (Knoten ENTWURF). / Please enter a draft.")
    parts = [f"Draft:\n{draft}"]
    notes = (notes or "").strip()
    if notes:
        parts.append(f"Additional notes from the user (follow them):\n{notes}")
    if has_image:
        if target == TARGET_EDIT:
            parts.append("The input image of the edit is attached. Name the elements the way they look in it.")
        else:
            parts.append("A reference image is attached and the draft refers to it. Use it as visual reference for the subject, "
                         "style or scene the draft mentions, and describe those things concretely in the prompt.")
    parts.append("Write the finished prompt now.")
    return "\n\n".join(parts)


def clean_answer(text: str, target: str = TARGET_NATURAL) -> str:
    """The model's answer without label, fences, wrapping quotes, markdown emphasis and line breaks (one line)."""
    text = (text or "").split("</think>")[-1].strip()
    fenced = FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1 and len(lines[0]) < 90 and lines[0].endswith((":", "：")):
        lines = lines[1:]   # "Here is the prompt:"
    text = " ".join(re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line) for line in lines)
    text = LABEL.sub("", text).replace("**", "").replace("__", "")
    for opening, closing in (('"', '"'), ("“", "”"), ("'", "'"), ("«", "»")):
        inner = text[1:-1]
        if len(text) > 2 and text[0] == opening and text[-1] == closing and opening not in inner and closing not in inner:
            text = inner.strip()
            break
    text = re.sub(r"\s+", " ", text).strip()
    if target == TARGET_TAGS:
        seen, tags = set(), []
        for tag in re.split(r"[,\n;]", text):
            tag = tag.strip().strip(".").strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                tags.append(tag)
        text = ", ".join(tags)
    return text


def size_of(text: str, target: str) -> int:
    """Tags for the tag target, words for all others."""
    return len([t for t in text.split(",") if t.strip()]) if target == TARGET_TAGS else len(text.split())


def usable(text: str, target: str, detail: str) -> bool:
    """A cleaned answer that is neither empty, a refusal, cut short nor cut off in the middle of a sentence."""
    if not text or REFUSALS.match(text):
        return False
    if size_of(text, target) < MIN_SIZE[target][detail]:
        return False
    if target != TARGET_TAGS and text[-1] not in END_MARKS:
        return False
    return True


def first_usable(generate, target: str, detail: str, seed: int):
    """Cleaned answer of generate(seed) that passes usable(), else one retry with seed + 1000 (the v1.2.5 fix for answers
    that stop early), else None. Returns (answer or None, list of rejected cleaned answers)."""
    rejected = []
    for attempt_seed in (int(seed), int(seed) + 1000):
        answer = clean_answer(generate(attempt_seed), target)
        if usable(answer, target, detail):
            return answer, rejected
        rejected.append(answer)
    return None, rejected


def enhance_prompt(draft: str, target: str, detail: str, language: str, notes: str, enhance: bool, seed: int, generate,
                   has_image: bool = False) -> tuple[str, str, list[str]]:
    """(prompt, source, rejected answers). source: "llm", "draft" (enhance off) or "draft: answer unusable".

    generate(system, user, seed) -> raw answer of the model; only called with enhance on. The draft is returned
    unchanged when the enhancer is off or has no usable answer (also after a refusal), never a broken half answer.
    """
    check_options(target, detail, language)
    user = user_message(draft, notes, has_image, target)
    if not enhance:
        return draft.strip(), "draft", []
    system = system_prompt(target, detail, language)
    answer, rejected = first_usable(lambda attempt_seed: generate(system, user, attempt_seed), target, detail, seed)
    if answer is None:
        return draft.strip(), "draft: answer unusable", rejected
    return answer, "llm", rejected


def looks_like_qwen38_27b(model_name: str) -> bool:
    name = (model_name or "").lower().replace("_", "-")
    return "qwen3.8" in name and "27b" in name


def info_line(model_name: str, target: str, detail: str, source: str, prompt: str, seconds: float) -> str:
    if source == "llm":
        unit = "Tags" if target == TARGET_TAGS else "Wörter"
        line = f"{model_name} · {target.split(' (')[0]} · {detail} · {size_of(prompt, target)} {unit} · {seconds:.0f} s"
        return line if looks_like_qwen38_27b(model_name) else line + " · ACHTUNG: kein Qwen3.8 27B im Startprofil"
    if source == "draft":
        return "Enhancer aus: Entwurf unverändert"
    return "Entwurf unverändert: keine brauchbare Antwort des Modells (Details im ComfyUI-Log)"
