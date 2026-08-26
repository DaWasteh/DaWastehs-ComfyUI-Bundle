from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_nodes/ComfyUI-DaWasteh-LiveAvatar/voice_swap.py"
SPEC = importlib.util.spec_from_file_location("dawasteh_voice_swap", MODULE_PATH)
VOICE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VOICE)


class FakeProcess:
    def __init__(self, executable: str):
        self._executable = executable
        self.terminated = False

    def exe(self):
        return self._executable

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        return 0

    def is_running(self):
        return not self.terminated


class LiveVoiceSwapNodeTests(unittest.TestCase):
    def test_packaged_runtime_manifest_matches_installer_source(self):
        packaged = ROOT / "custom_nodes/ComfyUI-DaWasteh-LiveAvatar/assets/voice-changer-b2332-tree.json"
        source = ROOT / "assets/live-avatar-v072/voice-changer-b2332-tree.json"
        self.assertEqual(packaged.read_bytes(), source.read_bytes())

    def test_tree_digest_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runtime"
            root.mkdir()
            files = {"MMVCServerSIO.exe": b"exe", "data/model.bin": b"model"}
            records = {}
            for relative, payload in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                records[relative] = [len(payload), hashlib.sha256(payload).hexdigest()]
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps(records), encoding="utf-8")
            count, total, digest = VOICE.tree_digest(root, manifest)
            expected = hashlib.sha256()
            for relative, payload in sorted(files.items()):
                expected.update(
                    f"MMVCServerSIO/{relative}".encode()
                    + b"\0"
                    + str(len(payload)).encode()
                    + b"\0"
                    + hashlib.sha256(payload).hexdigest().encode()
                    + b"\n"
                )
            self.assertEqual((count, total, digest), (2, 8, expected.hexdigest()))
            (root / "data/model.bin").write_bytes(b"bad!!")
            self.assertEqual(VOICE.tree_digest(root, manifest), (-1, -1, ""))

    def test_manifest_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({"../escape": [0, hashlib.sha256(b"").hexdigest()]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsafe"):
                VOICE.tree_digest(Path(directory), manifest)

    def test_status_rejects_listener_from_other_executable(self):
        install = Path("L:/ComfyUI/voice-changer-dml-b2332")
        with mock.patch.object(VOICE, "_listener_pids", return_value={123}), mock.patch.object(
            VOICE.psutil, "Process", return_value=FakeProcess("C:/Other/server.exe")
        ):
            with self.assertRaisesRegex(RuntimeError, "untrusted"):
                VOICE.service_status(install)

    def test_status_accepts_only_expected_listener_and_health(self):
        install = Path("L:/ComfyUI/voice-changer-dml-b2332")
        expected = str(install.resolve() / VOICE.EXE_NAME)
        with mock.patch.object(VOICE, "_listener_pids", return_value={456}), mock.patch.object(
            VOICE.psutil, "Process", return_value=FakeProcess(expected)
        ), mock.patch.object(VOICE, "_health_ok", return_value=True):
            status = VOICE.service_status(install)
        self.assertEqual(status["state"], "ready")
        self.assertTrue(status["ready"])
        self.assertEqual(status["pid"], 456)
        self.assertEqual(status["url"], "http://127.0.0.1:18888/")

    def test_status_action_opens_only_a_verified_ready_loopback_url(self):
        ready = {"state": "ready", "ready": True, "pid": 789, "url": VOICE.UI_URL}
        with mock.patch.object(VOICE, "service_status", return_value=ready), mock.patch.object(
            VOICE.webbrowser, "open_new_tab"
        ) as opened:
            result = VOICE.run_action("status / open UI", open_browser=True)
        opened.assert_called_once_with("http://127.0.0.1:18888/")
        self.assertIn("READY", result["status"])
        with self.assertRaises(ValueError):
            VOICE.run_action("run arbitrary command")

    def test_node_contract_is_always_rechecked(self):
        inputs = VOICE.DaWastehLiveVoiceSwapLauncher.INPUT_TYPES()["required"]
        self.assertEqual(inputs["action"][0], list(VOICE.ACTIONS))
        self.assertEqual(inputs["install_path"][1]["default"], VOICE.DEFAULT_INSTALL_PATH)
        self.assertTrue(inputs["open_browser"][1]["default"])
        self.assertTrue(VOICE.DaWastehLiveVoiceSwapLauncher.OUTPUT_NODE)
        self.assertNotEqual(VOICE.DaWastehLiveVoiceSwapLauncher.IS_CHANGED(), VOICE.DaWastehLiveVoiceSwapLauncher.IS_CHANGED())


if __name__ == "__main__":
    unittest.main()
