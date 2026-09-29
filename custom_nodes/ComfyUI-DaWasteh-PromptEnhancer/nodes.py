"""v1.3.0 image prompt enhancer: rough draft -> finished image prompt, written by the local Qwen3.8 27B GGUF (llama.cpp on
the second GPU, the same model and server profile as the MV 2 music-video prompt writer)."""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
import time
from pathlib import Path

from comfy_api.latest import ComfyExtension, io

from . import helpers

CATEGORY = "DaWasteh/prompt enhancer"
TAG = "[DaWasteh PromptEnhancer]"
BACKEND = Path(__file__).resolve().parent.parent / "ComfyUI-DaWasteh-H3-MusicVideo" / "llm_backend.py"


def _backend():
    """The llama.cpp helper of the H3-MusicVideo pack (same GGUF, server binary and GPU as the MV 2 prompt writer)."""
    name = "dawasteh_promptenhancer_llm_backend"
    if name in sys.modules:
        return sys.modules[name]
    if not BACKEND.is_file():
        raise FileNotFoundError(f"{BACKEND} fehlt: der Prompt Enhancer nutzt llm_backend.py aus ComfyUI-DaWasteh-H3-MusicVideo "
                                "(installiert der Bundle-Updater).")
    spec = importlib.util.spec_from_file_location(name, BACKEND)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[name] = module
    return module


def _configured(backend) -> tuple[str, str]:
    """(GGUF path, llama-server path) from the start profile, or a clear error naming what is missing."""
    gguf = backend.configured_gguf()
    server = os.environ.get(backend.ENV_SERVER, "").strip().strip('"')
    if not gguf or not server or not Path(server).is_file():
        raise RuntimeError(
            "Qwen3.8 27B ist nicht eingerichtet: Das Startprofil (start-MultiGPU.ps1) setzt "
            f"{backend.ENV_MODEL} (GGUF, aktuell: {gguf or 'nicht gesetzt oder Datei fehlt'}) und "
            f"{backend.ENV_SERVER} (llama-server.exe, aktuell: {server or 'nicht gesetzt'}) nur, wenn beide Dateien existieren. "
            "ComfyUI über start-MultiGPU.bat starten oder den Schalter 'enhance' am Knoten ausschalten (Entwurf wird unverändert genutzt).")
    return gguf, server


class DaWImagePromptEnhancer(io.ComfyNode):
    """Draft -> finished prompt for an image model with the local Qwen3.8 27B GGUF (llama.cpp), started only while writing."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWImagePromptEnhancer",
            display_name="DaW Image Prompt Enhancer (Qwen3.8 27B GGUF)",
            category=CATEGORY,
            description="Turns a rough draft (German or English) into the finished prompt for an image model. Qwen3.8 27B "
                        "runs through llama.cpp on the RX 9070 XT (GGUF from the start profile, the same model as the MV 2 "
                        "music-video prompt writer) and is stopped afterwards, so VRAM and RAM are free again. Targets: "
                        "running text for Z-Image / FLUX / Qwen Image / Krea, designs with lettering, tags for SDXL / Pony / "
                        "Illustrious, and instructions for image-edit models. An optional image is shown to the model "
                        "(required in spirit for edit instructions). Unusable answers are retried once with another seed, "
                        "then the draft is passed on unchanged; a refusal counts as unusable.",
            inputs=[
                io.String.Input("draft", multiline=True, default="",
                                tooltip="The rough idea, a few words or a paragraph, German or English. Texts that must appear "
                                        "in the image go in \"quotation marks\"."),
                io.Combo.Input("target", options=helpers.TARGETS, default=helpers.DEFAULT_TARGET,
                               tooltip="Which kind of image model the prompt is for: running text (Z-Image, FLUX, Qwen Image, "
                                       "Krea), a design with lettering, SDXL-style tags, or an instruction for an edit model."),
                io.Combo.Input("detail", options=helpers.DETAILS, default=helpers.DEFAULT_DETAIL,
                               tooltip="Length: Fließtext kurz ~55 / mittel ~115 / ausführlich ~220 words; Tags 15-25 / 25-40 / "
                                       "40-60; Bearbeiten 1 / 2-3 / up to 5 sentences."),
                io.Combo.Input("language", options=helpers.LANGUAGES, default=helpers.DEFAULT_LANGUAGE,
                               tooltip="Language of the finished prompt. English suits most image models best; tags are always "
                                       "English. Texts in quotation marks are never translated."),
                io.Boolean.Input("enhance", default=True,
                                 tooltip="On: Qwen3.8 27B writes the prompt. Off: the draft is passed on unchanged and the "
                                         "GGUF is not started."),
                io.Int.Input("seed", default=0, min=0, max=2**31 - 1, control_after_generate=True,
                             tooltip="Another seed gives another variation of the same draft."),
                io.Float.Input("temperature", default=0.7, min=0.0, max=1.5, step=0.05, advanced=True,
                               tooltip="Lower = closer to the draft, higher = more inventive."),
                io.Int.Input("max_tokens", default=1024, min=128, max=4096, advanced=True),
                io.String.Input("notes", multiline=True, default="", optional=True,
                                tooltip="Optional extra rules for the writer, e.g. \"always 35 mm film look, warm colours\" or "
                                        "\"no people in the picture\"."),
                io.Image.Input("image", optional=True,
                               tooltip="Optional. The writer sees it: as visual reference for what the draft mentions, or, for "
                                       "the edit target, as the image to be edited."),
            ],
            outputs=[io.String.Output("prompt"), io.String.Output("info")],
        )

    @classmethod
    def execute(cls, draft, target, detail, language, enhance, seed, temperature, max_tokens, notes="", image=None) -> io.NodeOutput:
        started = time.time()
        if target == helpers.TARGET_EDIT and image is None and enhance:
            logging.warning("%s Bearbeiten ohne Bild: die Anweisung entsteht nur aus dem Entwurf", TAG)
        model_name = "-"
        session = {}

        def generate(system, user, attempt_seed):
            # one server for both attempts; the context manager stops it afterwards, also on errors
            if "server" not in session:
                backend = _backend()
                gguf, _ = _configured(backend)
                session["backend"], session["gguf"] = backend, gguf
                session["server"] = backend.LlamaServer(gguf).start()
            return session["server"].generate(user, image=image, max_length=int(max_tokens), temperature=float(temperature),
                                              seed=attempt_seed, system_prompt=system)

        try:
            prompt, source, rejected = helpers.enhance_prompt(
                draft, target, detail, language, notes, bool(enhance), int(seed), generate, has_image=image is not None)
        finally:
            if "server" in session:
                model_name = Path(session["gguf"]).name
                session["server"].stop()
        for text in rejected:
            logging.warning("%s Antwort verworfen (%d Zeichen, endet mit %r)", TAG, len(text), text[-160:])
        info = helpers.info_line(model_name, target, detail, source, prompt, time.time() - started)
        logging.info("%s %s", TAG, info)
        return io.NodeOutput(prompt, info)


class PromptEnhancerExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [DaWImagePromptEnhancer]


async def comfy_entrypoint() -> PromptEnhancerExtension:
    return PromptEnhancerExtension()
