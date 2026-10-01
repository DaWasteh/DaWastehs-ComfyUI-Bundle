"""v1.3.1: the FB and AILab Qwen3-TTS packs share the module name qwen_tts.inference.qwen3_tts_model.

Rebuilds the conflict with two stand-in modules: the FB pack imports the name at start-up, the AILab loader later
executes its own copy under the same name. Without the shim the FB voice item can no longer be pickled."""
from __future__ import annotations

import dataclasses
import importlib.util
import pickle
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-Qwen3TTS-LoRA"
NAME = "qwen_tts.inference.qwen3_tts_model"


def compat():
    spec = importlib.util.spec_from_file_location("dawasteh_qwen_tts_compat_test", PACK / "qwen_tts_compat.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model_module(tag: str) -> types.ModuleType:
    module = types.ModuleType(NAME)

    @dataclasses.dataclass
    class VoiceClonePromptItem:
        ref_code: object = None
        source: str = tag

    VoiceClonePromptItem.__module__ = NAME
    VoiceClonePromptItem.__qualname__ = "VoiceClonePromptItem"
    module.VoiceClonePromptItem = VoiceClonePromptItem
    return module


def ailab_namespace() -> dict:
    """Globals of AILab_QwenTTS: a cached loader that registers its own model module under NAME."""
    ns = {"qwen_pkg_dir": Path("ComfyUI-QwenTTS/qwen_tts"), "Qwen3TTSModel": None}

    def _load_qwen3_model():
        if ns["Qwen3TTSModel"] is not None:
            return ns["Qwen3TTSModel"]
        module = model_module("ailab")
        sys.modules[NAME] = module
        ns["Qwen3TTSModel"] = object()
        return ns["Qwen3TTSModel"]

    def _get_prompt_item_class():
        _load_qwen3_model()
        return getattr(__import__(NAME, fromlist=["VoiceClonePromptItem"]), "VoiceClonePromptItem", None)

    ns["_load_qwen3_model"] = _load_qwen3_model
    ns["_get_prompt_item_class"] = _get_prompt_item_class
    return ns


class QwenTTSCompatTests(unittest.TestCase):
    PARENTS = ("qwen_tts", "qwen_tts.inference")

    def setUp(self):
        self.saved = {name: sys.modules.get(name) for name in (*self.PARENTS, NAME)}
        for name in self.PARENTS:  # pickle imports the parents of the class module
            package = types.ModuleType(name)
            package.__path__ = []
            sys.modules[name] = package
        self.fb = model_module("fb")
        sys.modules[NAME] = self.fb

    def tearDown(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_without_the_shim_the_fb_voice_item_cannot_be_pickled(self):
        ns = ailab_namespace()
        ns["_load_qwen3_model"]()
        with self.assertRaises(pickle.PicklingError):
            pickle.dumps(self.fb.VoiceClonePromptItem(ref_code=[1, 2]))

    def test_with_the_shim_fb_keeps_its_module_and_ailab_finds_its_own_class(self):
        shim = compat()
        ns = ailab_namespace()
        self.assertTrue(shim.patch_core_namespace(ns))
        self.assertFalse(shim.patch_core_namespace(ns))  # idempotent
        ns["_load_qwen3_model"]()
        self.assertIs(sys.modules[NAME], self.fb)
        item = pickle.loads(pickle.dumps(self.fb.VoiceClonePromptItem(ref_code=[1, 2])))
        self.assertEqual((item.ref_code, item.source), ([1, 2], "fb"))
        ailab_cls = ns["_get_prompt_item_class"]()
        self.assertEqual(ailab_cls().source, "ailab")
        self.assertIs(sys.modules[NAME], self.fb)

    def test_tools_module_goes_through_the_core_copy(self):
        shim = compat()
        core_ns = ailab_namespace()
        core = types.ModuleType("AILab_QwenTTS")
        vars(core).update(core_ns)
        tools_ns = {"core": core, "_get_prompt_item_class": lambda: None}
        self.assertTrue(shim.patch_tools_namespace(tools_ns))
        self.assertEqual(tools_ns["_get_prompt_item_class"]().source, "ailab")
        self.assertIs(sys.modules[NAME], self.fb)

    def test_without_an_earlier_owner_the_ailab_module_stays_registered(self):
        sys.modules.pop(NAME, None)
        shim = compat()
        ns = ailab_namespace()
        shim.patch_core_namespace(ns)
        ns["_load_qwen3_model"]()
        self.assertEqual(sys.modules[NAME].VoiceClonePromptItem().source, "ailab")

    def test_apply_finds_the_namespaces_through_node_classes(self):
        shim = compat()
        core_ns = ailab_namespace()
        exec("def generate(self):\n    return _load_qwen3_model()\n", core_ns)
        node = type("AILab_Qwen3TTSCustomVoice", (), {"generate": core_ns["generate"]})
        self.assertEqual(shim.apply([node, int]), 1)
        self.assertEqual(shim.apply([node]), 0)

    def test_the_pack_installs_the_shim_without_blocking_registration(self):
        init = (PACK / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("from .qwen_tts_compat import install as install_qwen_tts_compat", init)
        self.assertIn("never block node registration", init.split("from .qwen_tts_compat import")[1])


if __name__ == "__main__":
    unittest.main()
