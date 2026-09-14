"""Pinned installer behavior without network access or runtime model writes."""

import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import install_models_v118 as installer


class InstallerTests(unittest.TestCase):
    def test_direct_and_relocated_downloads_use_verified_bytes(self):
        data = b"test weights"
        for source, target in (
            (
                "diffusion_models/example.safetensors",
                "diffusion_models/example.safetensors",
            ),
            ("example.safetensors", "diffusion_models/example.safetensors"),
            ("split_files/vae/example.safetensors", "vae/WAN/example.safetensors"),
        ):
            with (
                self.subTest(source=source),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                item = dict(
                    repo="example/model",
                    revision="a" * 40,
                    source=source,
                    path=target,
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
                calls = []

                def download(**kwargs):
                    calls.append(kwargs)
                    path = Path(kwargs["local_dir"]) / kwargs["filename"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    return str(path)

                with (
                    patch.object(installer, "model_files", return_value=[item]),
                    patch.dict(
                        "sys.modules",
                        {"huggingface_hub": SimpleNamespace(hf_hub_download=download)},
                    ),
                ):
                    self.assertEqual(installer.install(root), 0)
                    self.assertEqual((root / "models" / target).read_bytes(), data)
                    self.assertEqual(installer.install(root, verify_only=True), 0)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(calls[0]["revision"], item["revision"])

    def test_existing_mismatch_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "models/diffusion_models/example.safetensors"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"personal file")
            item = dict(
                repo="example/model",
                path="diffusion_models/example.safetensors",
                size=1,
                sha256="0" * 64,
            )
            with patch.object(installer, "model_files", return_value=[item]):
                self.assertEqual(installer.install(root), 1)
            self.assertEqual(target.read_bytes(), b"personal file")

    def test_private_models_require_explicit_opt_in(self):
        item = dict(
            repo="Comfy-Org/YuE2",
            path="checkpoints/private.safetensors",
            size=1,
            sha256="0" * 64,
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(installer, "model_files", return_value=[item]),
        ):
            root = Path(directory)
            self.assertEqual(installer.install(root, verify_only=True), 0)
            self.assertEqual(
                installer.install(root, verify_only=True, include_private_yue2=True), 1
            )
            self.assertEqual(list(root.iterdir()), [])

    def test_missing_verify_only_does_not_create_files(self):
        item = dict(
            repo="example/model",
            path="diffusion_models/missing.safetensors",
            size=1,
            sha256="0" * 64,
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(installer, "model_files", return_value=[item]),
        ):
            root = Path(directory)
            self.assertEqual(installer.install(root, verify_only=True), 1)
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
