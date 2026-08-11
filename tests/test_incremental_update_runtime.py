from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "update-comfyui-rdna4.ps1"


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows PowerShell runtime test")
class IncrementalUpdateRuntimeTests(unittest.TestCase):
    def test_incremental_copy_backup_stale_removal_and_traversal_guard(self) -> None:
        harness = textwrap.dedent(
            r"""
            param(
                [Parameter(Mandatory = $true)][string] $ScriptPath,
                [Parameter(Mandatory = $true)][string] $TemporaryRoot
            )
            $ErrorActionPreference = "Stop"

            $tokens = $null
            $errors = $null
            $ast = [System.Management.Automation.Language.Parser]::ParseFile(
                $ScriptPath,
                [ref]$tokens,
                [ref]$errors
            )
            if ($errors.Count -gt 0) { throw ($errors -join "`n") }

            $functionNames = @(
                "Get-GitBlobId",
                "Export-GitBlob",
                "Get-Sha256",
                "Assert-NoReparsePoints",
                "Assert-SafeRepositoryPath",
                "Resolve-SafeTargetFile",
                "Backup-ChangedFile",
                "Remove-EmptyParentDirectories",
                "Install-GitTrackedDirectory",
                "Update-InstalledUpdater",
                "Export-SyncManifest"
            )
            $definitions = $ast.FindAll({
                param($node)
                $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                    $functionNames -contains $node.Name
            }, $true)
            if ($definitions.Count -ne $functionNames.Count) {
                throw "Not all sync functions were found in the updater AST."
            }
            foreach ($definition in $definitions) {
                Invoke-Expression $definition.Extent.Text
            }

            $OwnRepo = Join-Path $TemporaryRoot "repo"
            $target = Join-Path $TemporaryRoot "target"
            $BackupRoot = Join-Path $TemporaryRoot "backups"
            $PreviousManifestFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            $AllDeployedFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            $BackupCreated = $false
            $DeploymentCommit = $null

            New-Item -ItemType Directory -Path (Join-Path $OwnRepo "workflows") -Force | Out-Null
            New-Item -ItemType Directory -Path $target -Force | Out-Null
            & git -C $OwnRepo init --quiet
            if ($LASTEXITCODE -ne 0) { throw "git init failed" }

            $sourceFile = Join-Path $OwnRepo "workflows\a.txt"
            $targetFile = Join-Path $target "a.txt"
            Set-Content -LiteralPath $sourceFile -Value "same"
            & git -C $OwnRepo add -- "workflows/a.txt"
            if ($LASTEXITCODE -ne 0) { throw "git add failed" }
            & git -C $OwnRepo -c user.name=UpdaterTest -c user.email=updater@test.invalid commit --quiet -m initial
            if ($LASTEXITCODE -ne 0) { throw "initial git commit failed" }
            $DeploymentCommit = (& git -C $OwnRepo rev-parse HEAD).Trim()
            Export-GitBlob -BlobId (Get-GitBlobId -TrackedFile "workflows/a.txt") -Destination $targetFile
            Set-Content -LiteralPath (Join-Path $target "local-only.txt") -Value "keep"
            New-Item -ItemType Directory -Path (Join-Path $target "local-empty-directory") | Out-Null

            $first = Install-GitTrackedDirectory "workflows" $target "workflows-DaWasteh"
            if ($first.Changed -ne 0 -or $first.Removed -ne 0) {
                throw "Byte-identical files were not skipped."
            }
            if (!(Test-Path -LiteralPath (Join-Path $target "local-only.txt"))) {
                throw "A local unmanifested file was removed."
            }
            if (!(Test-Path -LiteralPath (Join-Path $target "local-empty-directory") -PathType Container)) {
                throw "A local unmanifested empty directory was removed."
            }

            Set-Content -LiteralPath $sourceFile -Value "changed"
            & git -C $OwnRepo add -- "workflows/a.txt"
            & git -C $OwnRepo -c user.name=UpdaterTest -c user.email=updater@test.invalid commit --quiet -m changed
            if ($LASTEXITCODE -ne 0) { throw "changed git commit failed" }
            $DeploymentCommit = (& git -C $OwnRepo rev-parse HEAD).Trim()
            $second = Install-GitTrackedDirectory "workflows" $target "workflows-DaWasteh"
            if ($second.Changed -ne 1 -or $second.Removed -ne 0) {
                throw "Changed file was not copied exactly once."
            }
            if (!(Test-Path -LiteralPath (Join-Path $BackupRoot "workflows-DaWasteh\a.txt"))) {
                throw "Replaced file was not backed up."
            }

            & git -C $OwnRepo update-index --assume-unchanged "workflows/a.txt"
            Set-Content -LiteralPath $sourceFile -Value "hidden working-tree change"
            if (@(& git -C $OwnRepo status --porcelain).Count -ne 0) {
                throw "assume-unchanged test setup did not hide the working-tree change"
            }
            $hidden = Install-GitTrackedDirectory "workflows" $target "workflows-DaWasteh"
            if ($hidden.Changed -ne 0 -or (Get-Content -LiteralPath $targetFile -Raw) -match "hidden") {
                throw "A hidden working-tree modification leaked into the committed deployment."
            }
            & git -C $OwnRepo update-index --no-assume-unchanged "workflows/a.txt"

            [void]$PreviousManifestFiles.Add("workflows/removed.txt")
            Set-Content -LiteralPath (Join-Path $target "removed.txt") -Value "old"
            $third = Install-GitTrackedDirectory "workflows" $target "workflows-DaWasteh"
            if ($third.Changed -ne 0 -or $third.Removed -ne 1) {
                throw "Previously manifested stale file was not removed."
            }
            if (Test-Path -LiteralPath (Join-Path $target "removed.txt")) {
                throw "Stale target file remains."
            }
            if (!(Test-Path -LiteralPath (Join-Path $BackupRoot "workflows-DaWasteh\removed.txt"))) {
                throw "Removed stale file was not backed up."
            }

            $PreviousManifestFiles.Clear()
            [void]$PreviousManifestFiles.Add("workflows/../../escape.txt")
            $escapeFile = Join-Path $TemporaryRoot "escape.txt"
            Set-Content -LiteralPath $escapeFile -Value "do not delete"
            $blocked = $false
            try {
                Install-GitTrackedDirectory "workflows" $target "workflows-DaWasteh" | Out-Null
            }
            catch {
                $blocked = $true
            }
            if (!$blocked -or !(Test-Path -LiteralPath $escapeFile)) {
                throw "Manifest path traversal was not blocked safely."
            }

            $PreviousManifestFiles.Clear()
            $outside = Join-Path $TemporaryRoot "outside"
            $junction = Join-Path $target "junction"
            New-Item -ItemType Directory -Path $outside -Force | Out-Null
            $victim = Join-Path $outside "victim.txt"
            Set-Content -LiteralPath $victim -Value "do not delete through junction"
            New-Item -ItemType Junction -Path $junction -Target $outside | Out-Null
            [void]$PreviousManifestFiles.Add("workflows/junction/victim.txt")
            $blocked = $false
            try {
                Install-GitTrackedDirectory "workflows" $target "workflows-DaWasteh" | Out-Null
            }
            catch {
                $blocked = $true
            }
            if (!$blocked -or !(Test-Path -LiteralPath $victim)) {
                throw "Junction traversal was not blocked safely."
            }

            $repoJunction = Join-Path $TemporaryRoot "repo-junction"
            New-Item -ItemType Junction -Path $repoJunction -Target $OwnRepo | Out-Null
            $blocked = $false
            try {
                Assert-SafeRepositoryPath -Path $repoJunction
            }
            catch {
                $blocked = $true
            }
            if (!$blocked) {
                throw "Repository junction was not blocked safely."
            }

            $outsideTargetParent = Join-Path $TemporaryRoot "outside-target-parent"
            $targetParentJunction = Join-Path $TemporaryRoot "target-parent-junction"
            New-Item -ItemType Directory -Path $outsideTargetParent -Force | Out-Null
            New-Item -ItemType Junction -Path $targetParentJunction -Target $outsideTargetParent | Out-Null
            $missingTarget = Join-Path $targetParentJunction "must-not-be-created"
            $blocked = $false
            try {
                Install-GitTrackedDirectory "workflows" $missingTarget "workflows-DaWasteh" | Out-Null
            }
            catch {
                $blocked = $true
            }
            if (!$blocked -or (Test-Path -LiteralPath (Join-Path $outsideTargetParent "must-not-be-created"))) {
                throw "Missing target was created through a junction before preflight."
            }

            $normalBackupRoot = $BackupRoot
            $outsideBackup = Join-Path $TemporaryRoot "outside-backup"
            $backupJunction = Join-Path $TemporaryRoot "backup-junction"
            New-Item -ItemType Directory -Path $outsideBackup -Force | Out-Null
            New-Item -ItemType Junction -Path $backupJunction -Target $outsideBackup | Out-Null
            $BackupRoot = $backupJunction
            $blocked = $false
            try {
                Backup-ChangedFile -Path $targetFile -BackupGroup "must-not-be-created" -RelativeFile "a.txt"
            }
            catch {
                $blocked = $true
            }
            if (!$blocked -or (Test-Path -LiteralPath (Join-Path $outsideBackup "must-not-be-created"))) {
                throw "Backup directory was created through a junction before preflight."
            }
            $BackupRoot = $normalBackupRoot

            $outsideManifest = Join-Path $TemporaryRoot "outside-manifest"
            $manifestJunction = Join-Path $TemporaryRoot "manifest-junction"
            New-Item -ItemType Directory -Path $outsideManifest -Force | Out-Null
            New-Item -ItemType Junction -Path $manifestJunction -Target $outsideManifest | Out-Null
            $SyncManifestPath = Join-Path $manifestJunction "manifest.json"
            $blocked = $false
            try {
                Export-SyncManifest
            }
            catch {
                $blocked = $true
            }
            if (!$blocked -or (Test-Path -LiteralPath (Join-Path $outsideManifest "manifest.json"))) {
                throw "Manifest was written through a junction before preflight."
            }

            $Root = Join-Path $TemporaryRoot "installed"
            New-Item -ItemType Directory -Path (Join-Path $OwnRepo "tools") -Force | Out-Null
            New-Item -ItemType Directory -Path $Root -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $OwnRepo "tools\update-comfyui-rdna4.ps1") -Value "committed updater"
            & git -C $OwnRepo add -- "tools/update-comfyui-rdna4.ps1"
            & git -C $OwnRepo -c user.name=UpdaterTest -c user.email=updater@test.invalid commit --quiet -m updater
            if ($LASTEXITCODE -ne 0) { throw "updater git commit failed" }
            $DeploymentCommit = (& git -C $OwnRepo rev-parse HEAD).Trim()
            $installedUpdater = Join-Path $Root "update-comfyui-rdna4.ps1"
            Set-Content -LiteralPath $installedUpdater -Value "old updater"

            $normalInstallRoot = $Root
            $outsideInstall = Join-Path $TemporaryRoot "outside-install"
            $installJunction = Join-Path $TemporaryRoot "install-junction"
            New-Item -ItemType Directory -Path $outsideInstall -Force | Out-Null
            New-Item -ItemType Junction -Path $installJunction -Target $outsideInstall | Out-Null
            $Root = $installJunction
            Update-InstalledUpdater
            if (Test-Path -LiteralPath (Join-Path $outsideInstall "update-comfyui-rdna4.ps1")) {
                throw "Installed updater was written through a junction."
            }

            $Root = $normalInstallRoot
            Update-InstalledUpdater
            if ((Get-Content -LiteralPath $installedUpdater -Raw) -notmatch "committed updater") {
                throw "Installed PowerShell updater was not refreshed from the committed blob."
            }
            "Incremental updater runtime checks passed"
            """
        )

        with tempfile.TemporaryDirectory(prefix="dawasteh-updater-test-") as temporary:
            harness_path = Path(temporary) / "runtime-test.ps1"
            harness_path.write_text(harness, encoding="utf-8")
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(harness_path),
                    "-ScriptPath",
                    str(SCRIPT),
                    "-TemporaryRoot",
                    temporary,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )

        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertIn("Incremental updater runtime checks passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
