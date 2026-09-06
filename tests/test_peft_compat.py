"""v1.1.2: process-wide PEFT/torchao compatibility shim of the Qwen3-TTS LoRA node pack."""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-Qwen3TTS-LoRA"


def _load():
    spec = importlib.util.spec_from_file_location("peft_compat_under_test", PACK / "peft_compat.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_modules(torchao_version: str):
    torchao = types.ModuleType("torchao")
    torchao.__version__ = torchao_version
    peft = types.ModuleType("peft")
    import_utils = types.ModuleType("peft.import_utils")
    import_utils.is_torchao_available = lambda: (_ for _ in ()).throw(ImportError("incompatible torchao"))
    tuners = types.ModuleType("peft.tuners")
    lora = types.ModuleType("peft.tuners.lora")
    lora_torchao = types.ModuleType("peft.tuners.lora.torchao")
    lora_torchao.is_torchao_available = import_utils.is_torchao_available
    peft.import_utils = import_utils
    peft.tuners = tuners
    tuners.lora = lora
    lora.torchao = lora_torchao
    return {
        "torchao": torchao,
        "peft": peft,
        "peft.import_utils": import_utils,
        "peft.tuners": tuners,
        "peft.tuners.lora": lora,
        "peft.tuners.lora.torchao": lora_torchao,
    }


class PeftCompatTests(unittest.TestCase):
    def _with_modules(self, mods):
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)

        def restore():
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        self.addCleanup(restore)

    def test_old_torchao_disables_only_the_dispatcher(self):
        mods = _fake_modules("0.9.0")
        self._with_modules(mods)
        pc = _load()
        self.assertTrue(pc.torchao_needs_shim())
        self.assertTrue(pc.disable_incompatible_torchao_dispatcher())
        self.assertFalse(mods["peft.tuners.lora.torchao"].is_torchao_available())
        self.assertFalse(mods["peft.import_utils"].is_torchao_available())
        # idempotent
        self.assertTrue(pc.disable_incompatible_torchao_dispatcher())

    def test_new_torchao_is_left_alone(self):
        mods = _fake_modules("0.16.0")
        self._with_modules(mods)
        pc = _load()
        self.assertFalse(pc.torchao_needs_shim())
        self.assertFalse(pc.disable_incompatible_torchao_dispatcher())
        with self.assertRaises(ImportError):
            mods["peft.tuners.lora.torchao"].is_torchao_available()

    def test_missing_packages_are_harmless(self):
        mods = _fake_modules("0.9.0")
        mods.pop("peft.tuners.lora.torchao")
        mods["peft.tuners.lora"].torchao = None
        self._with_modules(mods)
        sys.modules.pop("peft.tuners.lora.torchao", None)
        pc = _load()
        self.assertFalse(pc.disable_incompatible_torchao_dispatcher())

    def test_node_pack_applies_shim_at_import_and_nodes_delegate(self):
        init_src = (PACK / "__init__.py").read_text(encoding="utf-8")
        nodes_src = (PACK / "nodes.py").read_text(encoding="utf-8")
        self.assertIn("disable_incompatible_torchao_dispatcher()", init_src)
        self.assertIn("from .peft_compat import disable_incompatible_torchao_dispatcher", nodes_src)
        # the two historical call sites (train + inference) still run the shim before PEFT is used
        self.assertEqual(nodes_src.count("            _disable_incompatible_torchao_dispatcher()\n"), 2)


if __name__ == "__main__":
    unittest.main()
