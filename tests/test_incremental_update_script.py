from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "update-comfyui-rdna4.ps1"
BATCH = ROOT / "tools" / "update-comfyui-rdna4.bat"


class IncrementalUpdateScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8-sig")

    def test_uses_only_the_canonical_bundle_clone(self) -> None:
        self.assertIn('$OwnRepo = "L:\\GitHub\\DaWastehs-ComfyUI-Bundle"', self.source)
        self.assertIn("Assert-CanonicalOwnRepository", self.source)
        self.assertNotIn('git" "clone" $OwnRepoUrl $OwnRepo', self.source)

    def test_legacy_clone_cleanup_is_guarded(self) -> None:
        self.assertIn('$LegacyOwnRepo = "L:\\GitHub\\DaWasteh ComfyUI Nodes"', self.source)
        self.assertIn("Normalize-GitRemote $LegacyOwnRepoUrl", self.source)
        self.assertIn("status --porcelain --untracked-files=all --ignored", self.source)
        self.assertIn("enthaelt lokale Aenderungen und wird nicht automatisch geloescht", self.source)

    def test_sync_is_hash_based_and_manifest_bounded(self) -> None:
        self.assertIn("function Get-Sha256", self.source)
        self.assertIn("[System.Security.Cryptography.SHA256]::Create()", self.source)
        self.assertIn("dawasteh-bundle-sync-manifest.json", self.source)
        self.assertIn("$PreviousManifestFiles", self.source)
        self.assertIn("$currentFiles.Contains($previousFile)", self.source)
        self.assertIn("function Resolve-SafeTargetFile", self.source)
        self.assertIn("function Assert-NoReparsePoints", self.source)
        self.assertIn("Sync-Pfad verlaesst das Zielverzeichnis", self.source)
        self.assertIn("Symlink oder Junction", self.source)
        self.assertNotIn("Remove-Item -LiteralPath $Target -Recurse -Force", self.source)

    def test_reparse_preflight_precedes_filesystem_creation(self) -> None:
        target_guard = 'Assert-NoReparsePoints -TargetRoot $Target -Candidate (Join-Path $Target ".dawasteh-sync-preflight")'
        target_create = 'New-Item -ItemType Directory -Path $Target -Force'
        self.assertLess(self.source.index(target_guard), self.source.index(target_create))

        backup_guard = 'Assert-NoReparsePoints -TargetRoot $backupGroupRoot'
        backup_create = 'New-Item -ItemType Directory -Path $backupGroupRoot -Force'
        self.assertLess(self.source.index(backup_guard), self.source.index(backup_create))

        manifest_guard = 'Assert-NoReparsePoints -TargetRoot $manifestParent -Candidate $SyncManifestPath'
        manifest_create = 'New-Item -ItemType Directory -Path $manifestParent -Force'
        self.assertLess(self.source.index(manifest_guard), self.source.index(manifest_create))

    def test_deploys_only_a_clean_head_and_validates_hash_parity(self) -> None:
        self.assertGreaterEqual(self.source.count("Assert-CleanOwnRepository"), 3)
        self.assertIn("Deployment manifest does not match the Git-tracked source file set", self.source)
        self.assertIn("ls-tree -r --name-only $DeploymentCommit", self.source)
        self.assertIn("git cat-file fehlgeschlagen", self.source)
        self.assertIn("Deployed file differs from committed Git blob", self.source)

    def test_pixaroma_cleanup_is_non_destructive(self) -> None:
        self.assertIn("Warn-PixaromaManagerCopies", self.source)
        self.assertIn("nicht automatisch geloescht", self.source)
        self.assertNotIn("Entferne alte Pixaroma-Installation", self.source)

    def test_all_owned_node_packs_are_updated(self) -> None:
        for name in (
            "ComfyUI-DaWasteh-AutoSongwriter",
            "ComfyUI-DaWasteh-H3-AutoLength",
            "ComfyUI-DaWasteh-H3-MusicVideo",
            "ComfyUI-DaWasteh-LiveAvatar",
            "ComfyUI-DaWasteh-MultiGPU-Control",
            "ComfyUI-DaWasteh-Qwen3TTS-LoRA",
        ):
            self.assertIn(f'"{name}"', self.source)

    def test_v094_adaptive_nodes_arrive_through_a_v093_managed_pack(self) -> None:
        pack = ROOT / "custom_nodes" / "ComfyUI-DaWasteh-MultiGPU-Control"
        self.assertTrue((pack / "adaptive_nodes.py").is_file())
        self.assertTrue((pack / "adaptive_profiles.py").is_file())
        self.assertTrue((pack / "web" / "adaptive_media.js").is_file())
        self.assertNotIn("ComfyUI-DaWasteh-Adaptive-Media", self.source)
        previous = subprocess.check_output(
            ["git", "show", "v0.9.3:tools/update-comfyui-rdna4.ps1"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        self.assertIn('"ComfyUI-DaWasteh-MultiGPU-Control"', previous)

    def test_validation_does_not_generate_bytecode(self) -> None:
        self.assertIn("ast.parse", self.source)
        self.assertNotIn("compileall", self.source)
        self.assertNotIn("compile_dir", self.source)
        self.assertIn("$env:TEMP", self.source)
        self.assertIn("finally", self.source)

    def test_batch_launcher_is_utf8_and_propagates_exit_code(self) -> None:
        source = BATCH.read_text(encoding="utf-8-sig")
        self.assertIn("chcp 65001", source)
        self.assertIn("set \"PYTHONUTF8=1\"", source)
        self.assertIn("update-comfyui-rdna4.ps1", source)
        self.assertIn("exit /b %EXITCODE%", source)
        self.assertNotIn("update-comfyui-rdna4.bat", self.source)


if __name__ == "__main__":
    unittest.main()
