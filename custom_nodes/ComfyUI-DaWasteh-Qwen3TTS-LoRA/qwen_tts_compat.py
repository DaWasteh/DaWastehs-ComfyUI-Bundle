"""Keep the two third-party Qwen3-TTS node packs from breaking each other's saved voices (process-wide).

Both packs ship their own, slightly different copy of the ``qwen_tts`` package:

* ``qwen3-tts-comfyui`` (FB_Qwen3TTS* nodes) imports ``qwen_tts`` when ComfyUI starts;
* ``ComfyUI-QwenTTS`` (AILab_Qwen3TTS* nodes) executes its own ``qwen3_tts_model.py`` at first use and registers it
  under the same module name, ``qwen_tts.inference.qwen3_tts_model``.

After any AILab node has run, the FB "Save Voice" node fails (``torch.save`` pickles ``VoiceClonePromptItem`` by module
name and finds the AILab class: "Can't pickle ...: it's not the same object as ..."), and FB voices loaded later would
come back as AILab objects. Found by the v1.3.1 example runs (CustomVoice, then Save Voice in one ComfyUI process).

The shim wraps the AILab loader: the AILab model module keeps working (it holds its classes by reference and now finds
its prompt-item class on its own module), and the module name goes back to the pack that imported it first. Without
the AILab pack, or without an earlier owner of the name, nothing changes. It is applied once per process on the first
queued prompt, when every node pack is loaded; importing this module has no side effect.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Iterable

MODEL_MODULE = "qwen_tts.inference.qwen3_tts_model"
MARK = "_dawasteh_qwen_compat"
OWN_MODULE = "_dawasteh_qwen_model_module"

_STATE = {"installed": False, "patched": 0}


def _item_class(core_ns: dict) -> Any:
    try:
        core_ns["_load_qwen3_model"]()
        module = core_ns.get(OWN_MODULE) or sys.modules.get(MODEL_MODULE)
        return getattr(module, "VoiceClonePromptItem", None)
    except Exception:
        return None


def patch_core_namespace(ns: dict) -> bool:
    """Patch the globals of one AILab_QwenTTS module copy (the pack loads the file twice); idempotent."""
    if ns.get(MARK) or not callable(ns.get("_load_qwen3_model")) or "qwen_pkg_dir" not in ns:
        return False
    original: Callable = ns["_load_qwen3_model"]

    def _load_qwen3_model():
        before = sys.modules.get(MODEL_MODULE)
        result = original()
        loaded = sys.modules.get(MODEL_MODULE)
        if loaded is not None and loaded is not before:
            ns[OWN_MODULE] = loaded
            if before is not None:
                sys.modules[MODEL_MODULE] = before  # the first importer (FB pack) keeps its module name
        return result

    ns["_load_qwen3_model"] = _load_qwen3_model
    if callable(ns.get("_get_prompt_item_class")):
        ns["_get_prompt_item_class"] = lambda: _item_class(ns)
    ns[MARK] = True
    return True


def patch_tools_namespace(ns: dict) -> bool:
    """Patch AILab_QwenTTS_Tools: its prompt-item lookup goes through the core module it imported."""
    core = ns.get("core")
    if ns.get(MARK) or core is None or not callable(ns.get("_get_prompt_item_class")):
        return False
    core_ns = vars(core)
    patch_core_namespace(core_ns)
    ns["_get_prompt_item_class"] = lambda: _item_class(core_ns)
    ns[MARK] = True
    return True


def _namespaces(classes: Iterable[type]) -> list[dict]:
    seen: dict[int, dict] = {}
    for cls in classes:
        for attr in vars(cls).values():
            func = getattr(attr, "__func__", attr)
            ns = getattr(func, "__globals__", None)
            if isinstance(ns, dict):
                seen.setdefault(id(ns), ns)
    for name in ("AILab_QwenTTS", "AILab_QwenTTS_Tools"):
        module = sys.modules.get(name)
        if module is not None:
            seen.setdefault(id(vars(module)), vars(module))
    return list(seen.values())


def apply(classes: Iterable[type]) -> int:
    """Patch every AILab QwenTTS module reachable from ``classes`` (the node classes); returns the patched count."""
    count = 0
    for ns in _namespaces(classes):
        if "qwen_pkg_dir" in ns:
            count += patch_core_namespace(ns)
        elif "core" in ns and "_get_prompt_item_class" in ns:
            count += patch_tools_namespace(ns)
    _STATE["patched"] += count
    return count


def install() -> bool:
    """Register the one-time patch on the first queued prompt; safe without ComfyUI's server or the AILab pack."""
    if _STATE["installed"]:
        return False
    try:
        from server import PromptServer
        import nodes
    except Exception:
        return False
    done = {"value": False}

    def on_prompt(json_data):
        if not done["value"]:
            done["value"] = True
            try:
                count = apply(nodes.NODE_CLASS_MAPPINGS.values())
                if count:
                    logging.info("[DaWasteh qwen_tts_compat] AILab QwenTTS loader isolated (%d module copies)", count)
            except Exception as exc:  # never block a prompt
                logging.warning("[DaWasteh qwen_tts_compat] not applied: %s", exc)
        return json_data

    PromptServer.instance.add_on_prompt_handler(on_prompt)
    _STATE["installed"] = True
    return True
