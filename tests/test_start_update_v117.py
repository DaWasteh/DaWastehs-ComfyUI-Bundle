"""Windows runtime regressions; all updater writes/pip/git pulls stay in a fixture."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "tools/update-comfyui-rdna4.ps1"
LAUNCHER = ROOT / "tools/start-MultiGPU.ps1"
WINDOWS = os.name == "nt" and shutil.which("powershell.exe")


def run_ps(code: str, directory: Path) -> subprocess.CompletedProcess:
    script = directory / "harness.ps1"
    script.write_text(code, encoding="utf-8-sig")
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )


def ps_string(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(WINDOWS, "Windows PowerShell runtime tests")
class UpdateV117Tests(unittest.TestCase):
    def run_fixture(self, switches: str, *, stale: bool = False, legacy_launcher: bool = False) -> tuple[str, list[str]]:
        with tempfile.TemporaryDirectory(prefix="dawasteh-v117-") as tmp:
            root = Path(tmp)
            own = root / "bundle"
            own.mkdir()
            install = root / "install"
            (install / "ComfyUI").mkdir(parents=True)
            python = install / ".venv/Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.touch()  # Never executed: native commands are recorded, not run.
            nodes = [
                "AutoSongwriter", "H3-AutoLength", "H3-MusicVideo", "LiveAvatar",
                "MultiGPU-Control", "Qwen3TTS-LoRA",
            ]
            files = {"workflows/example.json": b"{}\n"}
            files.update({f"custom_nodes/ComfyUI-DaWasteh-{name}/__init__.py": b"# fixture\n" for name in nodes})
            files.update({f"custom_nodes/ComfyUI-DaWasteh-{name}/requirements.txt": b"# fixture\n" for name in nodes})
            files.update({f"tools/{name}": (ROOT / "tools" / name).read_bytes() for name in (
                "start-MultiGPU.ps1", "start-MultiGPU.bat", "update-comfyui-rdna4.ps1",
            )})
            for relative, data in files.items():
                path = own / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            if legacy_launcher:
                old_launcher = subprocess.check_output(["git", "show", "v1.1.6:tools/start-MultiGPU.ps1"], cwd=ROOT)
                (own / "tools/start-MultiGPU.ps1").write_bytes(old_launcher)
            for args in (["init", "-q"], ["config", "core.autocrlf", "false"], ["add", "."],
                         ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
                         ["tag", "v1.1.6" if legacy_launcher else "v1.1.7"], ["remote", "add", "origin", "https://github.com/DaWasteh/DaWastehs-ComfyUI-Bundle.git"]):
                subprocess.run(["git", "-C", str(own), *args], capture_output=True, check=True)
            if legacy_launcher:
                import json
                old_commit = subprocess.check_output(["git", "-C", str(own), "rev-parse", "HEAD"], text=True).strip()
                # Old manifests did not track launchers; installed PS1s often use CRLF/BOM.
                (install / "start-MultiGPU.ps1").write_bytes(b"\xef\xbb\xbf" + old_launcher.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
                (install / "config").mkdir()
                (install / "config/dawasteh-bundle-sync-manifest.json").write_text(json.dumps({"version": 2, "release": "v1.1.6", "source_commit": old_commit, "files": []}))
                (own / "tools/start-MultiGPU.ps1").write_bytes(files["tools/start-MultiGPU.ps1"])
                for args in (["add", "tools"], ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "v117"], ["tag", "v1.1.7"]):
                    subprocess.run(["git", "-C", str(own), *args], capture_output=True, check=True)
            # Redirect only the canonical fixture paths; execute the real main flow.
            source = UPDATER.read_text(encoding="utf-8-sig")
            source = source.replace('$OwnRepo = "L:\\GitHub\\DaWastehs-ComfyUI-Bundle"', "$OwnRepo = " + ps_string(own))
            source = source.replace('$LegacyOwnRepo = "L:\\GitHub\\DaWasteh ComfyUI Nodes"', "$LegacyOwnRepo = " + ps_string(root / "absent-legacy"))
            overrides = r'''
function Assert-ComfyServersStopped {}
function Update-GitRepository { param($Path) Write-Output "MOCK_PULL:$Path" }
function Ensure-GitDirectory { param($Path, $RepositoryUrl) Write-Output "MOCK_NODE:$Path" }
function Invoke-NativeCommand {
    param($FilePath, [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    Write-Output ("MOCK_NATIVE:" + ($Arguments -join "|"))
    if ($Arguments[0] -like '*comfyui-dawasteh-validate-*') {
        & __REAL_PYTHON__ -B @Arguments
        if ($LASTEXITCODE -ne 0) { throw 'Real deployment validation failed' }
    }
}
'''.replace('__REAL_PYTHON__', ps_string(sys.executable))
            source = source.replace('if (!(Test-Path -LiteralPath $Repo))', overrides + '\nif (!(Test-Path -LiteralPath $Repo))', 1)
            fixture = root / "updater.ps1"
            fixture.write_text(source, encoding="utf-8-sig")
            if stale:
                target = install / "ComfyUI/user/default/workflows/DaWasteh/example.json"
                target.parent.mkdir(parents=True)
                target.write_text('{"old":true}')
            if "-DryRun" in switches:
                switches += " -LogPath " + ps_string(root / "no-log/explicit.log")
                legacy = root / "absent-legacy"
                subprocess.run(["git", "clone", "-q", "--local", str(own), str(legacy)], capture_output=True, check=True)
                subprocess.run(["git", "-C", str(legacy), "remote", "set-url", "origin", "https://github.com/DaWasteh/DaWasteh-ComfyUI-Workflows.git"], capture_output=True, check=True)
            before = sorted(str(p.relative_to(install)) for p in install.rglob("*"))
            before_bytes = {str(p.relative_to(install)): p.read_bytes() for p in install.rglob("*") if p.is_file()}
            proc = run_ps(f"$ErrorActionPreference='Stop'\n& {ps_string(fixture)} -ComfyUIRoot {ps_string(install)} {switches}\n", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            after = sorted(str(p.relative_to(install)) for p in install.rglob("*"))
            if "-DryRun" in switches:
                self.assertFalse((root / "no-log").exists())
                self.assertTrue((root / "absent-legacy/.git").is_dir())
                self.assertEqual(before, after, proc.stdout)
                self.assertEqual(before_bytes, {str(p.relative_to(install)): p.read_bytes() for p in install.rglob("*") if p.is_file()})
            else:
                for name in ("start-MultiGPU.ps1", "start-MultiGPU.bat"):
                    self.assertEqual((install / name).read_bytes(), files[f"tools/{name}"])
                import json
                manifest = json.loads((install / "config/dawasteh-bundle-sync-manifest.json").read_text(encoding="utf-8-sig"))
                paths = {entry["path"] for entry in manifest["files"]}
                self.assertIn("tools/start-MultiGPU.ps1", paths)
                self.assertNotIn("tools/update-comfyui-rdna4.ps1", paths)
            return proc.stdout, after

    def test_dry_run_first_install_has_no_persistent_writes_or_native_commands(self):
        stdout, _ = self.run_fixture("-DryRun")
        self.assertNotIn("MOCK_NATIVE:", stdout)
        self.assertNotIn("MOCK_PULL:", stdout)
        self.assertNotIn("MOCK_NODE:", stdout)

    def test_dry_run_stale_install_does_not_validate_old_manifest_or_modify_files(self):
        stdout, _ = self.run_fixture("-DryRun -SkipDependencies", stale=True)
        self.assertNotIn("MOCK_NATIVE:", stdout)

    def test_skip_dependencies_never_calls_pip_and_installs_only_allowlisted_launchers(self):
        stdout, _ = self.run_fixture("-SkipDependencies -SkipUpstream")
        self.assertNotIn("MOCK_NATIVE:-m|pip", stdout)
        self.assertNotIn("MOCK_PULL:", stdout)

    def test_existing_release_launcher_is_adopted_without_force(self):
        stdout, after = self.run_fixture("-SkipDependencies -SkipUpstream", legacy_launcher=True)
        self.assertIn("Validated ", stdout)
        self.assertTrue(any("launchers" in p and p.endswith("start-MultiGPU.ps1") for p in after))
        self.assertNotIn("Uebersprungen", stdout)

    def test_existing_release_dry_run_preserves_manifest_and_launcher(self):
        stdout, _ = self.run_fixture("-DryRun", legacy_launcher=True)
        self.assertNotIn("MOCK_NATIVE:", stdout)

    def test_default_run_keeps_dependency_updates_and_pins_enabled(self):
        stdout, _ = self.run_fixture("")
        self.assertIn("MOCK_NATIVE:-m|pip|install|--upgrade", stdout)
        self.assertIn("MOCK_NATIVE:-m|pip|uninstall|-y|onnxruntime-gpu", stdout)
        self.assertIn("onnxruntime-directml>=1.24.4", stdout)
        self.assertIn("MOCK_PULL:", stdout)
        self.assertIn("Validated ", stdout)

    def test_startup_window_detects_multigpu_launcher_at_custom_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = f"$source = {ps_string(UPDATER)}\n" + r'''
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors -join "`n") }
$fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Assert-ComfyServersStopped'},$true)
Invoke-Expression $fn.Extent.Text
$Root='C:\fixture[1]\Comfy UI'
function Get-NetTCPConnection {}
function Get-CimInstance {
    [pscustomobject]@{ Name='powershell.exe'; ProcessId=42; CommandLine='powershell -File "C:/fixture[1]/Comfy UI/start-MultiGPU.ps1"' }
}
$blocked=$false
try { Assert-ComfyServersStopped } catch { $blocked=$_.Exception.Message -match 'PID 42' }
if (-not $blocked) { throw 'MultiGPU startup window was not blocked' }
$Root='C:\unrelated'
Assert-ComfyServersStopped
'''
            proc = run_ps(code, Path(tmp))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_launcher_uses_literal_custom_installation_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = root / "fixture[1]" / "Comfy UI"
            (install / "ComfyUI").mkdir(parents=True)
            (install / "scripts").mkdir()
            (install / "scripts/windows_comfy_launcher.py").touch()
            fake_python = install / ".venv/Scripts/python.exe"
            fake_python.parent.mkdir(parents=True)
            fake_python.touch()
            source = LAUNCHER.read_text(encoding="utf-8-sig")
            # Only native execution is stubbed; path checks and Set-Location are real.
            source = source.replace('& $PythonExe ', 'Mock-Python ')
            fixture = install / "start-MultiGPU.ps1"
            fixture.write_text(source, encoding="utf-8-sig")
            code = r'''
$ErrorActionPreference='Stop'
function Get-NetTCPConnection {}
function Mock-Python { $global:LASTEXITCODE=0 }
''' + f"\n& {ps_string(fixture)} -CheckOnly\nWrite-Output ('FINAL_CWD:' + (Get-Location).Path)\n"
            proc = run_ps(code, root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("FINAL_CWD:" + str(install / "ComfyUI"), proc.stdout)
            self.assertIn("CheckOnly: no server started", proc.stdout)

    def test_launcher_preflight_failures_never_start_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = LAUNCHER.read_text(encoding="utf-8-sig")
            source = source.replace('$PythonExe = Join-Path $Root ".venv\\Scripts\\python.exe"', '$PythonExe = "Mock-Python"')
            source = source.replace('Set-Location -LiteralPath $ComfyPath', '# no cwd change in fixture')
            fixture = root / "launcher.ps1"
            fixture.write_text(source, encoding="utf-8-sig")
            for fail_at in (1, 2):
                code = r'''
$ErrorActionPreference='Stop'
$global:probeCount=0
function Test-Path { return $true }
function Get-NetTCPConnection {}
function Mock-Python {
    if ($args -contains '--python') { throw 'Unexpected server launch' }
    $global:probeCount++
    Write-Output 'PROBE_CALLED'
    $global:LASTEXITCODE = if ($global:probeCount -eq __FAIL_AT__) { 9 } else { 0 }
}
'''.replace('__FAIL_AT__', str(fail_at))
                code += f"\n& {ps_string(fixture)} -ComfyUIRoot {ps_string(root / 'explicit-install')}\n"
                proc = run_ps(code, root)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout.count("PROBE_CALLED"), fail_at)
                self.assertIn("preflight failed", proc.stderr)
                self.assertIn(str(root / "explicit-install/ComfyUI"), proc.stdout)

    def test_launcher_flag_matrix_and_check_only_with_stub_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for ck, fp8, dynamic, streams, cache in (
                (False, False, False, 0, "ram"), (True, True, True, 2, "classic"),
            ):
                source = LAUNCHER.read_text(encoding="utf-8-sig")
                source = source.replace('$UseComfyKitchenAttention = $false', f'$UseComfyKitchenAttention = ${str(ck).lower()}')
                source = source.replace('$FastFp8MatrixMult = $false', f'$FastFp8MatrixMult = ${str(fp8).lower()}')
                source = source.replace('$EnableDynamicVram = $false', f'$EnableDynamicVram = ${str(dynamic).lower()}')
                source = source.replace('$AsyncOffloadStreams = 0', f'$AsyncOffloadStreams = {streams}')
                source = source.replace('$CacheMode = "ram"', f'$CacheMode = "{cache}"')
                source = source.replace('$PythonExe = Join-Path $Root ".venv\\Scripts\\python.exe"', '$PythonExe = "Mock-Python"')
                source = source.replace('Set-Location -LiteralPath $ComfyPath', '# fixture: no cwd change')
                fixture = root / "launcher.ps1"
                fixture.write_text(source, encoding="utf-8-sig")
                code = r'''
$ErrorActionPreference='Stop'
function Test-Path { return $true }
function Get-NetTCPConnection { [pscustomobject]@{ OwningProcess=42 } }
function Mock-Python {
    if ($args -contains '--python') { throw 'Server launched in CheckOnly' }
    if ($args -contains '--use-ck-attention' -and $args -contains '--use-pytorch-cross-attention') { throw 'Attention conflict' }
    Write-Output ('PYTHON_ARGS:' + ($args -join '|'))
    $global:LASTEXITCODE=0
}
''' + f"\n& {ps_string(fixture)} -CheckOnly\n"
                proc = run_ps(code, root)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("CheckOnly: no server started", proc.stdout)
                self.assertEqual(proc.stdout.count("PYTHON_ARGS:"), 2)
                self.assertIn(str(root / "ComfyUI"), proc.stdout)
                self.assertIn("--cache-" + cache, proc.stdout)
                self.assertIn("--enable-dynamic-vram" if dynamic else "--disable-dynamic-vram", proc.stdout)
                self.assertIn("--use-ck-attention" if ck else "--use-pytorch-cross-attention", proc.stdout)


if __name__ == "__main__":
    unittest.main()
