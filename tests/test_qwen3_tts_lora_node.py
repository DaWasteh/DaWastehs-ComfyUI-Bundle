from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
UTILS_PATH = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-Qwen3TTS-LoRA" / "adapter_utils.py"
SPEC = importlib.util.spec_from_file_location("qwen3_tts_lora_adapter_utils", UTILS_PATH)
assert SPEC is not None and SPEC.loader is not None
UTILS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UTILS)
INSTALLER_PATH = ROOT / "tools" / "install_qwen3_tts_lora_node.py"
INSTALLER_SPEC = importlib.util.spec_from_file_location("qwen3_tts_lora_installer", INSTALLER_PATH)
assert INSTALLER_SPEC is not None and INSTALLER_SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(INSTALLER_SPEC)
INSTALLER_SPEC.loader.exec_module(INSTALLER)


class Qwen3TTSLoRAUtilityTests(unittest.TestCase):
    def test_adapter_signature_changes_after_checkpoint_republish(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = Path(temp_dir)
            for name in UTILS.ADAPTER_FILES:
                (adapter / name).write_bytes(name.encode("utf-8"))
            before = UTILS.adapter_signature(adapter)
            (adapter / "adapter_model.safetensors").write_bytes(b"new-adapter-weights")
            after = UTILS.adapter_signature(adapter)
            self.assertNotEqual(before, after)
            self.assertEqual([item[0] for item in after], list(UTILS.ADAPTER_FILES))

    def test_accumulation_tail_uses_actual_group_size(self):
        self.assertEqual(UTILS.accumulation_group_size(0, 1, 4), 1)
        self.assertEqual([UTILS.accumulation_group_size(step, 5, 4) for step in range(5)], [4, 4, 4, 4, 1])
        self.assertEqual([UTILS.accumulation_group_size(step, 6, 4) for step in range(6)], [4, 4, 4, 4, 2, 2])
        with self.assertRaises(ValueError):
            UTILS.accumulation_group_size(0, 0, 4)

    def test_lora_rank_normalizes_string_combo_values(self):
        self.assertEqual(UTILS.normalize_lora_rank("16"), 16)
        self.assertEqual(UTILS.normalize_lora_rank(32), 32)
        with self.assertRaisesRegex(ValueError, "Unsupported LoRA rank"):
            UTILS.normalize_lora_rank("12")

    def test_audio_transcripts_accept_exact_and_text_suffix_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            exact_audio = root / "001.wav"
            exact_audio.touch()
            (root / "001.txt").write_text("Exact transcript", encoding="utf-8")
            suffix_audio = root / "TaylorSwift_Ref_Audio.mp3"
            suffix_audio.touch()
            suffix_text = root / "TaylorSwift_Ref_Audio_Text.txt"
            suffix_text.write_text("Suffixed transcript", encoding="utf-8")
            (root / "unmatched.wav").touch()

            pairs = UTILS.find_audio_transcript_pairs(root, {".wav", ".mp3"})
            self.assertEqual(pairs, [
                (exact_audio, root / "001.txt"),
                (suffix_audio, suffix_text),
            ])

    def test_checkpoint_publish_replaces_complete_directory_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "checkpoint-epoch-1"
            destination.mkdir()
            (destination / "marker").write_text("old", encoding="utf-8")
            staging = root / ".staging-success"
            staging.mkdir()
            (staging / "marker").write_text("new", encoding="utf-8")
            UTILS.publish_directory(staging, destination)
            self.assertEqual((destination / "marker").read_text(encoding="utf-8"), "new")
            self.assertFalse(staging.exists())
            self.assertFalse((root / ".checkpoint-epoch-1.previous").exists())

            failed_staging = root / ".staging-failure"
            failed_staging.mkdir()
            (failed_staging / "marker").write_text("broken", encoding="utf-8")
            real_replace = Path.replace

            def fail_staging_replace(path: Path, target: Path):
                if path == failed_staging:
                    raise OSError("simulated publish failure")
                return real_replace(path, target)

            with patch.object(Path, "replace", new=fail_staging_replace):
                with self.assertRaisesRegex(OSError, "simulated"):
                    UTILS.publish_directory(failed_staging, destination)
            self.assertEqual((destination / "marker").read_text(encoding="utf-8"), "new")
            self.assertTrue(failed_staging.exists())

    def test_generator_emits_refined_byte_identical_workflows(self):
        generator = ROOT / "tools" / "generate_voice_lora_workflows.py"
        paths = [
            ROOT / "workflows" / "LoRA Generation" / "Qwen3_TTS_0_6B_Base-Recordings-to-Voice-LoRA.json",
            ROOT / "workflows" / "Voice Design" / "Qwen3_TTS_0_6B_Base+LoRA-Text-to-Speech-Live.json",
            ROOT / "workflows" / "Live Avatar" / "LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA.json",
        ]
        before = [path.read_bytes() for path in paths]
        subprocess.run([sys.executable, str(generator)], cwd=ROOT, check=True)
        first = [path.read_bytes() for path in paths]
        self.assertEqual(before, first)
        subprocess.run([sys.executable, str(generator)], cwd=ROOT, check=True)
        self.assertEqual(first, [path.read_bytes() for path in paths])
        for path in paths:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            marker = workflow["extra"]["dawasteh_workflow_refinement"]
            generated_notes = [
                node for node in workflow["nodes"]
                if node.get("properties", {}).get("dawasteh_generated_note")
            ]
            self.assertEqual(marker["generated_notes"], len(generated_notes), path.name)

    def test_installer_validates_concrete_qwen_runtime_classes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "main.py").write_text("", encoding="utf-8")
            package = root / "custom_nodes" / "qwen3-tts-comfyui" / "qwen_tts"
            (package / "finetuning").mkdir(parents=True)
            (package / "__init__.py").write_text(
                "class Qwen3TTSModel: pass\nclass Qwen3TTSTokenizer: pass\n", encoding="utf-8"
            )
            (package / "finetuning" / "__init__.py").write_text("", encoding="utf-8")
            dataset = package / "finetuning" / "dataset.py"
            dataset.write_text("class TTSDataset: pass\n", encoding="utf-8")
            found = INSTALLER.find_qwen_implementation(root)
            self.assertEqual(found, package)
            INSTALLER.validate_qwen_runtime(Path(sys.executable), found)
            dataset.write_text("class WrongDataset: pass\n", encoding="utf-8")
            with self.assertRaises(subprocess.CalledProcessError):
                INSTALLER.validate_qwen_runtime(Path(sys.executable), found)

    def test_installer_executes_bounded_dependency_and_import_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            requirements = Path(temp_dir) / "requirements.txt"
            requirements.write_text("peft>=0.19.1,<0.20\n", encoding="utf-8")
            with patch.object(INSTALLER.subprocess, "run") as run:
                INSTALLER.install_dependencies(Path(sys.executable), requirements)
            self.assertEqual(run.call_count, 2)
            pip_args = run.call_args_list[0].args[0]
            import_args = run.call_args_list[1].args[0]
            self.assertEqual(pip_args[:4], [sys.executable, "-m", "pip", "install"])
            self.assertIn(str(requirements), pip_args)
            self.assertEqual(import_args[:2], [sys.executable, "-c"])
            self.assertIn("peft", import_args[2])

    def test_node_source_integrates_signature_and_atomic_publication(self):
        nodes = (ROOT / "custom_nodes" / "ComfyUI-DaWasteh-Qwen3TTS-LoRA" / "nodes.py").read_text(encoding="utf-8")
        self.assertIn("def IS_CHANGED", nodes)
        self.assertIn("cache_key = (str(base_path), str(adapter), signature", nodes)
        self.assertIn("_MODEL_CACHE.clear()\n        model_management.unload_all_models()", nodes)
        self.assertIn("accumulation_group_size(step, len(dataloader)", nodes)
        self.assertIn('"lora_rank": (["8", "16", "32", "64"]', nodes)
        self.assertIn("rank = normalize_lora_rank(lora_rank)", nodes)
        self.assertIn("find_audio_transcript_pairs(audio_folder", nodes)
        self.assertIn("publish_directory(staging_path, final_path)", nodes)


if __name__ == "__main__":
    unittest.main()
