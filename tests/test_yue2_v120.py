"""Regression coverage for persistent caches, decoder fallback and instance cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("comfy_console", ROOT / "tools/scripts/windows_comfy_launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherIsolationTests(unittest.TestCase):
    def test_instances_and_duplicate_port_start_never_share_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ComfyUI"
            paths = [launcher.isolated_temp_args(["--port", port], root, pid)[-1]
                     for port, pid in [("8188", 10), ("8189", 11), ("8188", 12)]]
            self.assertEqual(len(set(paths)), 3)
            import shutil
            for value in paths:
                temp = Path(value) / "temp"
                temp.mkdir(parents=True)
                (temp / "preview").write_text("keep")
            shutil.rmtree(Path(paths[1]) / "temp")
            self.assertTrue((Path(paths[0]) / "temp/preview").is_file())
            self.assertTrue((Path(paths[2]) / "temp/preview").is_file())

    def test_explicit_temp_preserved_and_port_validated(self):
        for args in (["--temp-directory", "custom"], ["--temp-directory=custom"]):
            self.assertEqual(launcher.isolated_temp_args(args, ROOT), args)
        self.assertIn("comfyui-8190-12", launcher.isolated_temp_args(["--port=8190"], ROOT, 12)[-1])
        with self.assertRaises(ValueError):
            launcher.isolated_temp_args(["--port", "../../unsafe"], ROOT)


class WorkflowReleaseTests(unittest.TestCase):
    def test_only_exact_v120_rebuild_is_authorized(self):
        from tools import validate_workflows as validator
        from tools.build_yue2_lora_workflows import build_all
        for relative, workflow in build_all().items():
            errors = []
            with patch.object(validator, "git_head_json", return_value=workflow):
                validator.compare_head(Path("workflows") / relative, workflow, errors)
                self.assertEqual(errors, [])
                import copy
                changed = copy.deepcopy(workflow)
                changed["nodes"][0]["title"] = "unreviewed"
                validator.compare_head(Path("workflows") / relative, changed, errors)
                self.assertTrue(errors)

    def test_release_evidence_pins_current_sources(self):
        import hashlib
        report = json.loads((ROOT / "performance/rdna4/yue2-lora-v120-validation.json").read_text())
        self.assertEqual(report["release"], "v1.2.0")
        self.assertEqual(report["training"]["status"], "success")
        self.assertEqual(report["training"]["steps_completed"], 10000)
        self.assertEqual(report["dataset"]["source_files_scanned"], 612)
        for entry in report["sources"]:
            data = (ROOT / entry["path"]).read_bytes()
            if entry["path"] in ("tools/validate_workflows.py", "tools/update-comfyui-rdna4.ps1"):
                # v1.2.1 extends collection membership and v1.2.3 the updater's node list, not the
                # YuE2 runtime. Preserve the historical evidence instead of rewriting its hash.
                data = subprocess.check_output([
                    "git", "show", "651044e8c61b27df5fb043237eb65c4dc9104c65:" + entry["path"],
                ], cwd=ROOT)
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
        self.assertTrue(report["inspection"]["adapters_finite"])
        self.assertTrue(report["inspection"]["queue_idle"])


class InstallerUpgradeTests(unittest.TestCase):
    def test_verified_upgrade_backup_idempotence_and_unknown_file_protection(self):
        import hashlib
        from tools import install_yue2_lora_node as installer
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ComfyUI"
            target = root / "custom_nodes" / installer.NODE_NAME
            target.mkdir(parents=True)
            (root / "main.py").touch()
            (target / "nodes.py").write_bytes(b"old")
            manifest = Path(directory) / "trainer-manifest.json"
            meta = {"repository": "fixture", "revision": "fixed", "patch": "fixture.patch",
                    "files": {"nodes.py": hashlib.sha256(b"new").hexdigest()}}
            manifest.write_text(json.dumps(meta))
            manifest.with_name("trainer-manifest-v119.json").write_text(json.dumps({
                "files": {"nodes.py": hashlib.sha256(b"old").hexdigest()}}))
            def fake_git(args, **kwargs):
                if args[1] == "clone":
                    stage = Path(args[-1])
                    stage.mkdir()
                    (stage / "nodes.py").write_bytes(b"new")
                return subprocess.CompletedProcess(args, 0)
            with patch.object(installer, "MANIFEST", manifest), patch.object(installer.subprocess, "run", side_effect=fake_git) as git:
                with self.assertRaisesRegex(ValueError, "not overwritten"):
                    installer.install(root)
                installer.install(root, upgrade=True)
                self.assertEqual((target / "nodes.py").read_bytes(), b"new")
                backups = list((root.parent / "backups").glob("*/nodes.py"))
                self.assertEqual([p.read_bytes() for p in backups], [b"old"])
                git.reset_mock()
                installer.install(root, upgrade=True)
                git.assert_not_called()
                (target / "nodes.py").write_bytes(b"custom")
                with self.assertRaisesRegex(ValueError, "not overwritten"):
                    installer.install(root, upgrade=True)
                self.assertEqual((target / "nodes.py").read_bytes(), b"custom")
                git.assert_not_called()


@unittest.skipUnless(os.environ.get("YUE2_TRAINER_ROOT"), "set YUE2_TRAINER_ROOT for backend regressions")
class BackendReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.install_yue2_lora_node import verify_node, MANIFEST
        folder = Path(os.environ["YUE2_TRAINER_ROOT"])
        verify_node(folder, json.loads(MANIFEST.read_text()))
        spec = importlib.util.spec_from_file_location("yue2_v120_tested", folder / "__init__.py", submodule_search_locations=[str(folder)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = package
        spec.loader.exec_module(package)
        from yue2_v120_tested import nodes
        from yue2_v120_tested.trainer_core import data, train
        cls.nodes, cls.data, cls.train = nodes, data, train

    def test_persistent_default_relative_and_unsafe_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fp = types.SimpleNamespace(base_path=str(root), get_temp_directory=lambda: str(root / "instance/temp"))
            with patch.object(self.nodes, "_folder_paths", return_value=fp):
                self.assertEqual(self.nodes._latent_cache_root(""), root / "training_cache/yue2_latents")
                self.assertEqual(self.nodes._latent_cache_root('"my cache"'), root / "my cache")
                for value in ("temp", "temp/latents", str(root / "instance/temp/latents")):
                    with self.assertRaisesRegex(ValueError, "outside"):
                        self.nodes._latent_cache_root(value)

    def test_ffmpeg_fallback_and_useful_decode_failure(self):
        import torch
        with patch.dict(sys.modules, {"soundfile": types.SimpleNamespace(read=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad sndfile"))),
                                      "torchaudio": types.SimpleNamespace(load=lambda *a, **k: (_ for _ in ()).throw(ImportError("no torchcodec")))}), \
             patch.object(self.train, "_check_interrupt"), \
             patch.object(self.data, "_load_audio_ffmpeg", return_value=(torch.ones(2, 48000), 48000)) as decoder:
            self.assertEqual(tuple(self.data.load_audio(Path("test.mp3")).shape), (2, 48000))
            decoder.side_effect = RuntimeError("invalid stream")
            with self.assertRaisesRegex(RuntimeError, "test.mp3.*SoundFile.*TorchAudio.*FFmpeg"):
                self.data.load_audio(Path("test.mp3"))

    def test_ffmpeg_real_unicode_mp3_and_bad_file(self):
        import imageio_ffmpeg
        import numpy as np
        with tempfile.TemporaryDirectory() as directory, patch.object(self.train, "_check_interrupt"):
            song = Path(directory) / "Ä song (test).mp3"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=1", "-y", str(song)], check=True, capture_output=True)
            wave, rate = self.data._load_audio_ffmpeg(song)
            self.assertEqual(rate, 48000)
            self.assertEqual(wave.shape[0], 2)
            self.assertGreater(wave.shape[1], 40000)
            self.assertTrue(np.isfinite(wave.numpy()).all())
            song.write_bytes(b"not audio")
            with self.assertRaisesRegex(RuntimeError, "FFmpeg exit"):
                self.data._load_audio_ffmpeg(song)
            self.assertEqual(song.read_bytes(), b"not audio")

    def test_decoder_cancel_is_not_hidden(self):
        class Cancelled(BaseException):
            pass
        with patch.object(self.train, "_check_interrupt", side_effect=Cancelled), \
             patch.object(self.data.shutil, "which", return_value="ffmpeg"), \
             patch.object(self.data.subprocess, "Popen") as start:
            start.return_value.poll.return_value = None
            with self.assertRaises(Cancelled):
                self.data._load_audio_ffmpeg(Path("unused.mp3"))
            start.return_value.kill.assert_called_once()
            start.return_value.wait.assert_called_once()

    def test_612_file_cache_resume_and_atomic_staging(self):
        import numpy as np
        import torch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder, cache = root / "songs", root / "persistent"
            folder.mkdir()
            for i in range(612):
                (folder / f"{i:04}.mp3").touch()
            with patch.object(self.data, "load_audio", return_value=torch.zeros(2, 48000)), \
                 patch.object(self.data, "encode_file_latents", return_value=np.ones((25, 64), dtype=np.float32)) as encode:
                dataset = self.data.build_dataset(None, folder, cache, 1, "default", "metal", torch.device("cpu"))
                self.assertEqual(len(dataset.items), 612)
                self.assertEqual(encode.call_count, 612)
                encode.reset_mock()
                again = self.data.build_dataset(None, folder, cache, 1, "default", "metal", torch.device("cpu"))
                encode.assert_not_called()
                self.assertEqual(len(again.items), 612)
                self.assertEqual(len(list(cache.iterdir())), 612)
                self.assertTrue(all(p.suffix == ".npy" for p in cache.iterdir()))

    def test_deleted_cache_not_silently_accepted(self):
        import numpy as np
        import torch
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder, cache = root / "songs", root / "cache"
            folder.mkdir()
            (folder / "one.mp3").touch()
            with patch.object(self.data, "load_audio", return_value=torch.zeros(2, 48000)), \
                 patch.object(self.data, "encode_file_latents", return_value=np.ones((25, 64), dtype=np.float32)):
                with self.assertRaisesRegex(FileNotFoundError, "cache disappeared"):
                    self.data.build_dataset(None, folder, cache, 1, "none", "", torch.device("cpu"),
                                            progress_cb=lambda *_: shutil.rmtree(cache))


if __name__ == "__main__":
    unittest.main()
