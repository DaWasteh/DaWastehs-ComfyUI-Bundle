<#
.SYNOPSIS
    Uebernimmt die freigegebenen Projektdateien dieses Repositories in eine ComfyUI-Installation.

.DESCRIPTION
    Aktualisiert im Standardlauf ComfyUI-Core, Pixaroma und Spectrum MiniMax H3 per Fast-Forward,
    die Python-/Torch-/ROCm-Abhaengigkeiten sowie die eigenen Workflows und Node-Packs aus dem
    Bundle-Repository. Modelle, input/, output/, Zugangsdaten und private Einstellungen werden
    nie angefasst. Mit -SkipUpstream bzw. -SkipDependencies lassen sich die Upstream-Pulls und
    die pip-Aktualisierung gezielt auslassen (v1.1.3 bis v1.1.5 waren beide faelschlich Opt-in).

.PARAMETER ComfyUIRoot
    Wurzel der ComfyUI-Installation (enthaelt ComfyUI\ und .venv\). Standard: L:\ComfyUI

.PARAMETER ReleaseVersion
    Erwartete Release-Version. Das Skript prueft vor jedem Schreibzugriff, dass der
    Bundle-Checkout diese Version tatsaechlich enthaelt. Ohne Angabe wird der neueste
    von HEAD erreichbare Tag des Bundle-Checkouts verwendet.

.PARAMETER DryRun
    Trockenlauf: zeigt Aktionen ohne persistente Aenderungen an. Kurzlebige Git-Blob-Dateien
    in TEMP werden nach der Inhaltspruefung entfernt; es wird kein Update-Log geschrieben.

.PARAMETER LogPath
    Logdatei. Standard: <ComfyUIRoot>\logs\update-<Zeitstempel>.log

.PARAMETER RestoreFrom
    Stellt einen frueheren Lauf aus dessen Backup-Verzeichnis wieder her und beendet sich danach.

.PARAMETER SkipUpstream
    ComfyUI-Core, Pixaroma und Spectrum NICHT aktualisieren (Standard: werden aktualisiert).

.PARAMETER SkipDependencies
    Python-Umgebung NICHT veraendern: auch Qwen3-TTS- und DirectML-Pins sowie pip-Uninstall
    werden ausgelassen (Standard: Abhaengigkeiten werden aktualisiert).

.PARAMETER Force
    Ueberschreibt auch Dateien, die seit dem letzten Lauf lokal veraendert wurden.

.EXAMPLE
    .\update-comfyui-rdna4.ps1 -DryRun
.EXAMPLE
    .\update-comfyui-rdna4.ps1
.EXAMPLE
    .\update-comfyui-rdna4.ps1 -SkipUpstream -SkipDependencies
.EXAMPLE
    .\update-comfyui-rdna4.ps1 -RestoreFrom "L:\ComfyUI\_update_backups\20260906-171500"
#>
[CmdletBinding()]
param(
    [string] $ComfyUIRoot = "L:\ComfyUI",
    [string] $ReleaseVersion = "",
    [switch] $DryRun,
    [string] $LogPath,
    [string] $RestoreFrom,
    [switch] $SkipUpstream,
    [switch] $SkipDependencies,
    [switch] $Force
)

# v1.1.6: Upstream-Pulls und pip-Updates sind wieder Standard; die Schalter sind Opt-out.
$IncludeUpstream = -not $SkipUpstream
$UpdateDependencies = -not $SkipDependencies

# ============================================================
# ComfyUI RDNA4 SAFE Update Script
# Root: L:\ComfyUI
# Core: L:\ComfyUI\ComfyUI
# Own workflows/nodes: L:\GitHub\DaWastehs-ComfyUI-Bundle
# venv: L:\ComfyUI\.venv
#
# Safety rules:
# - requires both ComfyUI servers to be stopped
# - no git reset --hard and no git clean
# - only fast-forward pulls with autostash
# - uses the existing canonical bundle clone; never creates a second clone
# - synchronizes only changed Git-tracked files
# - backs up only files that are replaced or removed
# - removes only files known from the previous deployment manifest
# ============================================================

$ErrorActionPreference = "Stop"

$Root = $ComfyUIRoot
$Repo = Join-Path $Root "ComfyUI"
$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$TorchIndex = "https://rocm.nightlies.amd.com/whl-multi-arch/"
$QwenTtsConstraints = Join-Path $Root "qwen3-tts-constraints.txt"
$OwnRepo = "L:\GitHub\DaWastehs-ComfyUI-Bundle"
$OwnRepoUrl = "https://github.com/DaWasteh/DaWastehs-ComfyUI-Bundle.git"
$LegacyOwnRepo = "L:\GitHub\DaWasteh ComfyUI Nodes"
$LegacyOwnRepoUrl = "https://github.com/DaWasteh/DaWasteh-ComfyUI-Workflows.git"
$WorkflowTarget = Join-Path $Repo "user\default\workflows\DaWasteh"
$SyncManifestPath = Join-Path $Root "config\dawasteh-bundle-sync-manifest.json"
$CustomNodeNames = @(
    "ComfyUI-DaWasteh-AutoSongwriter",
    "ComfyUI-DaWasteh-GamePhysics",
    "ComfyUI-DaWasteh-H3-AutoLength",
    "ComfyUI-DaWasteh-H3-MusicVideo",
    "ComfyUI-DaWasteh-LiveAvatar",
    "ComfyUI-DaWasteh-MingImage",
    "ComfyUI-DaWasteh-MiraScene",
    "ComfyUI-DaWasteh-MultiGPU-Control",
    "ComfyUI-DaWasteh-PromptEnhancer",
    "ComfyUI-DaWasteh-Qwen3TTS-LoRA",
    "ComfyUI-DaWasteh-VisionTools"
)

# v1.2.9: ComfyUI-DaWasteh-MiraScene loads Mira-Scene's CCM code from a pinned checkout (the upstream repository has
# no license file yet: private use; nothing of it is copied into the bundle). Pinned like a lock file, independent of
# -SkipUpstream, because the node pack was tested against exactly this commit.
$MiraSceneRepoUrl = "https://github.com/VAST-AI-Research/Mira-Scene.git"
$MiraSceneCommit = "18f42656f3b6f96ef61d9b291c93d1036bdaa016"

$PixaromaNodeName = "ComfyUI-Pixaroma"
$PixaromaRepoUrl = "https://github.com/pixaroma/ComfyUI-Pixaroma.git"

# Third-party node packs that are tracked directly from GitHub (fast-forward
# only). Spectrum MiniMax H3 v0.1.x breaks on ComfyUI >= 0.34 (PDD FinalLayer
# contract); v0.2.21+ restores forecast execution, so the pack must move with
# the ComfyUI core instead of staying pinned to a Manager snapshot.
$GitTrackedNodes = @(
    @{ Name = $PixaromaNodeName; Url = $PixaromaRepoUrl },
    @{ Name = "comfyui-spectrum-minimax-h3"; Url = "https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3.git" },
    @{ Name = "Comfyui-PlagueKind-Nodes"; Url = "https://github.com/PlagueKind/Comfyui-PlagueKind-Nodes.git" },
    @{ Name = "Comfyui_Minimax_h3_latent_Upscaler"; Url = "https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler.git" },
    # v1.3.2: LanPaint (>= 2.2.0 for Qwen Image 2.1) and the AnyAngle Studio workbench. Neither needs a pip install here:
    # LanPaint has no dependencies, the studio needs onnxruntime (onnxruntime-directml provides it), OpenCV and
    # huggingface_hub, all part of the bundle environment. Its own requirements.txt would pull the plain onnxruntime
    # wheel over the DirectML one, so it is deliberately not installed.
    @{ Name = "LanPaint"; Url = "https://github.com/scraed/LanPaint.git" },
    @{ Name = "ComfyUI-AnyAngle-Studio-T8"; Url = "https://github.com/T8mars/Comfyui-Qwen-Image-2.1-MultiAngle-T8.git" }
)

$BackupRoot = Join-Path $Root ("_update_backups\{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$BackupCreated = $false
$PreviousManifestFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$AllDeployedFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$DeploymentCommit = $null
$script:DeployedHashes = @{}
$script:PreservedFileHashes = @{}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string] $FilePath,

        [Parameter(ValueFromRemainingArguments = $true, Position = 1)]
        [string[]] $Arguments
    )

    $displayArgs = ($Arguments | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    }) -join " "

    Write-Host "> $FilePath $displayArgs" -ForegroundColor DarkGray
    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE

    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Befehl fehlgeschlagen (ExitCode $exitCode): $FilePath $displayArgs"
    }
}

function Assert-ComfyServersStopped {
    foreach ($port in @(8188, 8189)) {
        $connection = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $connection) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction SilentlyContinue
            $details = if ($null -ne $process) { "$($process.Name): $($process.CommandLine)" } else { "unbekannter Prozess" }
            throw "Port $port ist noch aktiv (PID $($connection.OwningProcess), $details). Beide ComfyUI-Server vor dem Update mit Strg+C oder dem passenden Stop-Skript beenden."
        }
    }

    # A launcher can be active for a while before ComfyUI binds its port (Torch
    # probe, imports, custom-node initialization). Detect that startup window as
    # well, otherwise the updater could replace files in an already running venv.
    $normalizedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/').ToLowerInvariant().Replace('/', '\')
    $activeLaunchers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        if ($_.Name -notin @("python.exe", "pythonw.exe", "powershell.exe", "pwsh.exe")) {
            return $false
        }
        $command = ([string]$_.CommandLine).ToLowerInvariant().Replace('/', '\')
        return $command.Contains("$normalizedRoot\start-r9700.ps1") -or
            $command.Contains("$normalizedRoot\start-9070xt.ps1") -or
            $command.Contains("$normalizedRoot\start-multigpu.ps1") -or
            $command.Contains("$normalizedRoot\scripts\windows_comfy_launcher.py") -or
            $command.Contains("$normalizedRoot\comfyui\main.py")
    }
    if ($null -ne $activeLaunchers) {
        $details = ($activeLaunchers | ForEach-Object { "PID $($_.ProcessId) $($_.Name): $($_.CommandLine)" }) -join "`n"
        throw "Ein ComfyUI-Start- oder Serverprozess ist bereits aktiv, auch wenn der Port noch nicht lauscht:`n$details"
    }
}

function Update-GitRepository {
    param([Parameter(Mandatory = $true)][string] $Path)

    Assert-SafeRepositoryPath -Path $Path
    Invoke-NativeCommand "git" "-C" $Path "fetch" "--all" "--prune"
    Invoke-NativeCommand "git" "-C" $Path "pull" "--ff-only" "--autostash"
}

function Ensure-GitDirectory {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][string] $RepositoryUrl
    )

    $parent = Split-Path -Parent $Path
    Assert-NoReparsePoints -TargetRoot $parent -Candidate $Path
    if (Test-Path -LiteralPath $Path) {
        if (Test-Path -LiteralPath (Join-Path $Path ".git")) {
            $remote = & git -C $Path remote get-url origin
            if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remote) -or
                (Normalize-GitRemote $remote.Trim()) -ne (Normalize-GitRemote $RepositoryUrl)) {
                throw "Git-Repository unter '$Path' hat nicht den erwarteten Remote '$RepositoryUrl'."
            }
            Update-GitRepository $Path
            return
        }

        throw "Node-Ziel existiert, ist aber kein Git-Repository und wird nicht automatisch geloescht: $Path"
    }

    Invoke-NativeCommand "git" "clone" $RepositoryUrl $Path
}

function Ensure-PinnedCheckout {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][string] $RepositoryUrl,
        [Parameter(Mandatory = $true)][string] $Commit
    )

    $parent = Split-Path -Parent $Path
    if (!(Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    Assert-NoReparsePoints -TargetRoot $parent -Candidate $Path
    $initialize = !(Test-Path -LiteralPath $Path)
    if (!$initialize -and !(Test-Path -LiteralPath (Join-Path $Path ".git"))) {
        if (Get-ChildItem -LiteralPath $Path -Force | Select-Object -First 1) {
            throw "Ziel existiert, ist aber kein Git-Repository und wird nicht automatisch geloescht: $Path"
        }
        $initialize = $true
    }
    if ($initialize) {
        Invoke-NativeCommand "git" "init" "-q" $Path
        Invoke-NativeCommand "git" "-C" $Path "remote" "add" "origin" $RepositoryUrl
    }
    else {
        $remote = & git -C $Path remote get-url origin
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remote) -or
            (Normalize-GitRemote $remote.Trim()) -ne (Normalize-GitRemote $RepositoryUrl)) {
            throw "Git-Repository unter '$Path' hat nicht den erwarteten Remote '$RepositoryUrl'."
        }
        # --verify --quiet: no stderr for a repository without commits (PS 5.1 + Stop treats native stderr as fatal).
        $head = & git -C $Path rev-parse --verify --quiet HEAD
        if ($LASTEXITCODE -eq 0 -and "$head".Trim() -eq $Commit) {
            Write-Log "Mira-Scene bereits auf $($Commit.Substring(0, 12)): $Path" -Color DarkGray
            return
        }
        $changes = @(& git -C $Path status --porcelain --untracked-files=no)
        if ($changes.Count -gt 0) {
            throw "Lokale Aenderungen in '$Path'; der gepinnte Stand $Commit wird nicht erzwungen."
        }
    }
    Invoke-NativeCommand "git" "-C" $Path "fetch" "--depth" "1" "origin" $Commit
    Invoke-NativeCommand "git" "-C" $Path "checkout" "-q" "--detach" $Commit
}

function Warn-PixaromaManagerCopies {
    $customNodesRoot = Join-Path $Repo "custom_nodes"
    if (!(Test-Path -LiteralPath $customNodesRoot)) {
        return
    }

    Get-ChildItem -LiteralPath $customNodesRoot -Directory |
        Where-Object {
            $_.Name -like "$($PixaromaNodeName)*" -and
            $_.Name -ne $PixaromaNodeName
        } |
        ForEach-Object {
            Write-Warning "Zusaetzliche Pixaroma-Installation erkannt und aus Sicherheitsgruenden nicht automatisch geloescht: $($_.FullName)"
        }
}

function Normalize-GitRemote {
    param([Parameter(Mandatory = $true)][string] $Url)

    return (($Url.Trim().TrimEnd('/') -replace '\.git$', '').ToLowerInvariant())
}

function Assert-CanonicalOwnRepository {
    if (!(Test-Path -LiteralPath (Join-Path $OwnRepo ".git"))) {
        throw "Das echte Bundle-Repository fehlt: $OwnRepo. Der Updater erstellt absichtlich keinen zweiten Klon."
    }
    Assert-SafeRepositoryPath -Path $OwnRepo

    $remote = & git -C $OwnRepo remote get-url origin
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remote)) {
        throw "Git-Remote konnte nicht gelesen werden: $OwnRepo"
    }
    $remote = $remote.Trim()
    if ((Normalize-GitRemote $remote) -ne (Normalize-GitRemote $OwnRepoUrl)) {
        throw "Falsches Repository unter ${OwnRepo}: origin ist '$remote', erwartet wird '$OwnRepoUrl'."
    }
}

function Assert-CleanOwnRepository {
    $changes = @(& git -C $OwnRepo status --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0) {
        throw "Git-Status konnte nicht gelesen werden: $OwnRepo"
    }
    if ($changes.Count -gt 0) {
        throw "Das Bundle-Repository enthaelt lokale Aenderungen. Bitte zuerst committen oder bewusst sichern; der Updater verteilt nur einen sauberen HEAD: $OwnRepo"
    }
}

function Remove-LegacyOwnRepository {
    if (!(Test-Path -LiteralPath $LegacyOwnRepo)) {
        return
    }
    if (!(Test-Path -LiteralPath (Join-Path $LegacyOwnRepo ".git"))) {
        Write-Warning "Der alte Pfad bleibt aus Sicherheitsgruenden bestehen, weil er kein Git-Klon ist: $LegacyOwnRepo"
        return
    }
    $legacyItem = Get-Item -LiteralPath $LegacyOwnRepo -Force
    $nestedReparsePoint = Get-ChildItem -LiteralPath $LegacyOwnRepo -Force -Recurse |
        Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } |
        Select-Object -First 1
    if (($legacyItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $null -ne $nestedReparsePoint) {
        Write-Warning "Der alte Update-Klon enthaelt einen Symlink oder Junction und wird nicht automatisch geloescht: $LegacyOwnRepo"
        return
    }

    $remote = & git -C $LegacyOwnRepo remote get-url origin
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remote)) {
        Write-Warning "Der alte Pfad bleibt bestehen, weil sein Git-Remote nicht gelesen werden konnte: $LegacyOwnRepo"
        return
    }
    $remote = $remote.Trim()
    if ((Normalize-GitRemote $remote) -ne (Normalize-GitRemote $LegacyOwnRepoUrl)) {
        Write-Warning "Der alte Pfad bleibt bestehen, weil sein Git-Remote nicht dem frueheren Update-Klon entspricht: $LegacyOwnRepo"
        return
    }

    $localChanges = @(& git -C $LegacyOwnRepo status --porcelain --untracked-files=all --ignored)
    if ($LASTEXITCODE -ne 0 -or $localChanges.Count -gt 0) {
        Write-Warning "Der alte Update-Klon enthaelt lokale Aenderungen und wird nicht automatisch geloescht: $LegacyOwnRepo"
        return
    }

    if ($DryRun) {
        Write-DryRun "wuerde den alten, sauberen Update-Klon entfernen: $LegacyOwnRepo"
        return
    }
    Remove-Item -LiteralPath $LegacyOwnRepo -Recurse -Force
    Write-Host "Alten, sauberen Update-Klon entfernt: $LegacyOwnRepo" -ForegroundColor Yellow
}

function Get-GitBlobId {
    param([Parameter(Mandatory = $true)][string] $TrackedFile)

    if ([string]::IsNullOrWhiteSpace($DeploymentCommit)) {
        throw "Deployment-Commit wurde nicht festgelegt."
    }
    $blob = & git -C $OwnRepo rev-parse --verify "${DeploymentCommit}:$TrackedFile"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($blob)) {
        throw "Commit-Blob konnte nicht gelesen werden: $TrackedFile"
    }
    $blob = $blob.Trim()
    if ($blob -notmatch '^[0-9a-fA-F]{40,64}$') {
        throw "Ungueltige Git-Blob-ID fuer ${TrackedFile}: $blob"
    }
    return $blob
}

function Test-KnownLauncherContent {
    param([string] $TrackedFile, [string] $TargetFile)

    # Older updater manifests did not include launchers. Recognize only exact
    # historical source content (allow Windows CRLF/BOM), never arbitrary edits.
    $installedText = [IO.File]::ReadAllText($TargetFile).Replace("`r`n", "`n")
    $commits = @(& git -C $OwnRepo log '--format=%H' '--diff-filter=AM' $DeploymentCommit -- $TrackedFile)
    if ($LASTEXITCODE -ne 0) { throw "Launcher-Historie konnte nicht gelesen werden: $TrackedFile" }
    $temporary = [IO.Path]::GetTempFileName()
    try {
        # v1.2.0 adopts the shared console supervisor, used by all GPU profiles.
        # Only the exact previously captured baseline is safe to auto-upgrade.
        if ($TrackedFile -eq "tools/scripts/windows_comfy_launcher.py") {
            $legacy = "performance/rdna4/baseline_state/windows_comfy_launcher.py.orig"
            $legacyBlob = & git -C $OwnRepo rev-parse --verify "${DeploymentCommit}:$legacy" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Export-GitBlob -BlobId $legacyBlob.Trim() -Destination $temporary
                if ($installedText -ceq [IO.File]::ReadAllText($temporary).Replace("`r`n", "`n")) {
                    return $true
                }
            }
        }
        foreach ($commit in $commits) {
            $blob = & git -C $OwnRepo rev-parse --verify "${commit}:$TrackedFile"
            if ($LASTEXITCODE -ne 0) { throw "Launcher-Blob fehlt: ${commit}:$TrackedFile" }
            Export-GitBlob -BlobId $blob.Trim() -Destination $temporary
            if ($installedText -ceq [IO.File]::ReadAllText($temporary).Replace("`r`n", "`n")) {
                return $true
            }
        }
        return $false
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Export-GitBlob {
    param(
        [Parameter(Mandatory = $true)][string] $BlobId,
        [Parameter(Mandatory = $true)][string] $Destination
    )

    if ($BlobId -notmatch '^[0-9a-fA-F]{40,64}$') {
        throw "Ungueltige Git-Blob-ID: $BlobId"
    }
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = "git"
    $startInfo.Arguments = "cat-file blob $BlobId"
    $startInfo.WorkingDirectory = $OwnRepo
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [Diagnostics.Process]::Start($startInfo)
    $output = $null
    try {
        $output = [IO.File]::Create($Destination)
        $process.StandardOutput.BaseStream.CopyTo($output)
        $output.Dispose()
        $output = $null
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "git cat-file fehlgeschlagen fuer Blob $BlobId`: $stderr"
        }
    }
    finally {
        if ($null -ne $output) {
            $output.Dispose()
        }
        if ($null -ne $process) {
            if (!$process.HasExited) {
                $process.Kill()
            }
            $process.Dispose()
        }
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string] $Path)

    $stream = [System.IO.File]::OpenRead($Path)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($stream))).Replace("-", "")
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Assert-NoReparsePoints {
    param(
        [Parameter(Mandatory = $true)][string] $TargetRoot,
        [Parameter(Mandatory = $true)][string] $Candidate
    )

    $root = [IO.Path]::GetFullPath($TargetRoot).TrimEnd('\', '/')
    $relative = $Candidate.Substring($root.Length).TrimStart('\', '/')
    $paths = [System.Collections.Generic.List[string]]::new()
    $ancestor = $root
    while (![string]::IsNullOrWhiteSpace($ancestor)) {
        $paths.Add($ancestor)
        $parent = Split-Path -Parent $ancestor
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $ancestor) {
            break
        }
        $ancestor = $parent
    }
    $current = $root
    foreach ($segment in ($relative -split '[\\/]')) {
        if ([string]::IsNullOrWhiteSpace($segment)) {
            continue
        }
        $current = Join-Path $current $segment
        $paths.Add($current)
    }

    foreach ($path in $paths) {
        if (!(Test-Path -LiteralPath $path)) {
            continue
        }
        $item = Get-Item -LiteralPath $path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Sync-Pfad enthaelt einen nicht erlaubten Symlink oder Junction: $path"
        }
    }
}

function Assert-SafeRepositoryPath {
    param([Parameter(Mandatory = $true)][string] $Path)

    if (!(Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Git-Repository fehlt: $Path"
    }
    Assert-NoReparsePoints -TargetRoot $Path -Candidate (Join-Path $Path ".git")
}

function Resolve-SafeTargetFile {
    param(
        [Parameter(Mandatory = $true)][string] $TargetRoot,
        [Parameter(Mandatory = $true)][string] $RelativeFile
    )

    if ([string]::IsNullOrWhiteSpace($RelativeFile) -or [IO.Path]::IsPathRooted($RelativeFile)) {
        throw "Unsicherer relativer Sync-Pfad: $RelativeFile"
    }
    $segments = $RelativeFile -split '[\\/]'
    if ($segments | Where-Object { $_ -eq "" -or $_ -eq "." -or $_ -eq ".." }) {
        throw "Unsicherer relativer Sync-Pfad: $RelativeFile"
    }

    $root = [IO.Path]::GetFullPath($TargetRoot).TrimEnd('\', '/')
    $candidate = [IO.Path]::GetFullPath((Join-Path $root $RelativeFile))
    $requiredPrefix = $root + [IO.Path]::DirectorySeparatorChar
    if (!$candidate.StartsWith($requiredPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Sync-Pfad verlaesst das Zielverzeichnis: $RelativeFile"
    }
    Assert-NoReparsePoints -TargetRoot $root -Candidate $candidate
    return $candidate
}

function Backup-ChangedFile {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][string] $BackupGroup,
        [Parameter(Mandatory = $true)][string] $RelativeFile
    )

    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $backupGroupRoot = Join-Path $BackupRoot $BackupGroup
    Assert-NoReparsePoints -TargetRoot $backupGroupRoot -Candidate (Join-Path $backupGroupRoot ".dawasteh-backup-preflight")
    New-Item -ItemType Directory -Path $backupGroupRoot -Force | Out-Null
    $backupTarget = Resolve-SafeTargetFile -TargetRoot $backupGroupRoot -RelativeFile $RelativeFile
    New-Item -ItemType Directory -Path (Split-Path -Parent $backupTarget) -Force | Out-Null
    Copy-Item -LiteralPath $Path -Destination $backupTarget -Force
    $script:BackupCreated = $true
    # v1.1.3: Zuordnung Backup -> Originalpfad, damit -RestoreFrom automatisch zurueckspielen kann.
    $mapPath = Join-Path $BackupRoot "restore-map.json"
    $entries = @()
    if (Test-Path -LiteralPath $mapPath -PathType Leaf) {
        $entries = @((Get-Content -LiteralPath $mapPath -Raw | ConvertFrom-Json).entries)
    }
    $entries += [pscustomobject]@{
        backup   = (Join-Path $BackupGroup $RelativeFile)
        original = $Path
    }
    [pscustomobject]@{ version = 1; created = (Get-Date).ToString("o"); entries = $entries } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $mapPath -Encoding UTF8
}

function Remove-EmptyParentDirectories {
    param(
        [Parameter(Mandatory = $true)][string] $TargetRoot,
        [Parameter(Mandatory = $true)][string] $RemovedFile
    )

    $root = [IO.Path]::GetFullPath($TargetRoot).TrimEnd('\', '/')
    $requiredPrefix = $root + [IO.Path]::DirectorySeparatorChar
    $current = Split-Path -Parent $RemovedFile
    while ($current.StartsWith($requiredPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        Assert-NoReparsePoints -TargetRoot $root -Candidate $current
        if (@(Get-ChildItem -LiteralPath $current -Force).Count -gt 0) {
            break
        }
        Remove-Item -LiteralPath $current -Force
        $current = Split-Path -Parent $current
    }
}

function Install-GitTrackedDirectory {
    param(
        [Parameter(Mandatory = $true)][string] $RelativeSource,
        [Parameter(Mandatory = $true)][string] $Target,
        [Parameter(Mandatory = $true)][string] $BackupGroup,
        [string[]] $IncludeFiles = @()
    )

    # Explicit allowlist for tools: never copy the complete tools tree to the runtime root.
    [string[]] $sourcePaths = if ($IncludeFiles.Count -gt 0) { $IncludeFiles } else { @($RelativeSource) }
    $trackedFiles = @(& git -C $OwnRepo ls-tree -r --name-only $DeploymentCommit -- @sourcePaths)
    if ($LASTEXITCODE -ne 0) {
        throw "git ls-tree fehlgeschlagen fuer $RelativeSource bei Commit $DeploymentCommit"
    }
    if ($trackedFiles.Count -eq 0) {
        throw "Keine getrackten Dateien gefunden: $RelativeSource"
    }

    Assert-NoReparsePoints -TargetRoot $Target -Candidate (Join-Path $Target ".dawasteh-sync-preflight")
    if (-not $DryRun) { New-Item -ItemType Directory -Path $Target -Force | Out-Null }
    $prefix = ($RelativeSource.TrimEnd('/', '\') + "/")
    $currentFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $changed = 0
    $unchanged = 0
    $removed = 0
    $skipped = 0

    foreach ($trackedFile in $trackedFiles) {
        if (!$trackedFile.StartsWith($prefix, [StringComparison]::Ordinal)) {
            throw "Unerwarteter git-Pfad ausserhalb von ${RelativeSource}: $trackedFile"
        }
        [void]$currentFiles.Add($trackedFile)
        [void]$script:AllDeployedFiles.Add($trackedFile)

        $relativeFile = $trackedFile.Substring($prefix.Length).Replace('/', '\')
        $targetFile = Resolve-SafeTargetFile -TargetRoot $Target -RelativeFile $relativeFile
        if ((Test-Path -LiteralPath $targetFile) -and !(Test-Path -LiteralPath $targetFile -PathType Leaf)) {
            throw "Dateiziel ist kein regulaeres File: $targetFile"
        }

        $blobId = Get-GitBlobId -TrackedFile $trackedFile
        $temporaryBlob = [IO.Path]::GetTempFileName()
        try {
            Export-GitBlob -BlobId $blobId -Destination $temporaryBlob
            $sourceHash = Get-Sha256 -Path $temporaryBlob
            $script:DeployedHashes[$trackedFile] = $sourceHash
            $isIdentical = $false
            if (Test-Path -LiteralPath $targetFile -PathType Leaf) {
                $isIdentical = ((Get-Sha256 -Path $targetFile) -eq $sourceHash)
            }

            if ($isIdentical) {
                $unchanged++
                continue
            }

            # When first adopting a launcher, no manifest hash proves that an
            # existing different file is unmodified. Preserve it unless -Force.
            $unknownLauncher = $IncludeFiles.Count -gt 0 -and
                (Test-Path -LiteralPath $targetFile -PathType Leaf) -and
                [string]::IsNullOrWhiteSpace($script:PreviousManifestHashes[$trackedFile])
            if ($unknownLauncher -and (Test-KnownLauncherContent -TrackedFile $trackedFile -TargetFile $targetFile)) {
                $script:PreviousManifestHashes[$trackedFile] = Get-Sha256 -Path $targetFile
                $unknownLauncher = $false
            }
            if (!$Force -and ($unknownLauncher -or (Test-UserModifiedFile -TargetFile $targetFile -TrackedFile $trackedFile -CurrentHash $sourceHash))) {
                Write-Log ("Uebersprungen (lokal veraendert): $targetFile") -Level "WARN"
                [void]$script:SkippedUserFiles.Add($targetFile)
                $script:PreservedFileHashes[$trackedFile] = Get-Sha256 -Path $targetFile
                $skipped++
                continue
            }

            if ($DryRun) {
                Write-DryRun "wuerde schreiben: $targetFile"
                $changed++
                continue
            }

            Backup-ChangedFile -Path $targetFile -BackupGroup $BackupGroup -RelativeFile $relativeFile
            New-Item -ItemType Directory -Path (Split-Path -Parent $targetFile) -Force | Out-Null
            Copy-Item -LiteralPath $temporaryBlob -Destination $targetFile -Force
            $changed++
        }
        finally {
            Remove-Item -LiteralPath $temporaryBlob -Force -ErrorAction SilentlyContinue
        }
    }

    foreach ($previousFile in $PreviousManifestFiles) {
        if ($IncludeFiles.Count -gt 0 -and $previousFile -notin $IncludeFiles) { continue }
        if (!$previousFile.StartsWith($prefix, [StringComparison]::Ordinal) -or $currentFiles.Contains($previousFile)) {
            continue
        }
        $relativeFile = $previousFile.Substring($prefix.Length).Replace('/', '\')
        $targetFile = Resolve-SafeTargetFile -TargetRoot $Target -RelativeFile $relativeFile
        if (Test-Path -LiteralPath $targetFile -PathType Leaf) {
            # v1.1.3: abgeloeste, aber persoenlich veraenderte Dateien bleiben liegen.
            $previousHash = $script:PreviousManifestHashes[$previousFile]
            if (!$Force -and ![string]::IsNullOrWhiteSpace($previousHash) -and
                (Get-Sha256 -Path $targetFile) -ne $previousHash) {
                $replacement = $WorkflowMigrationMap[($previousFile -replace '^workflows/', '')]
                $hint = if ($replacement) { " Ersatz: $replacement" } else { "" }
                Write-Log ("Nicht geloescht (lokal veraendert): $targetFile.$hint") -Level "WARN"
                [void]$script:SkippedUserFiles.Add($targetFile)
                continue
            }
            if ($DryRun) {
                Write-DryRun "wuerde entfernen: $targetFile"
                $removed++
                continue
            }
            Backup-ChangedFile -Path $targetFile -BackupGroup $BackupGroup -RelativeFile $relativeFile
            Remove-Item -LiteralPath $targetFile -Force
            Remove-EmptyParentDirectories -TargetRoot $Target -RemovedFile $targetFile
            $removed++
        }
    }

    Write-Log "Synchronisiert: $changed geaendert, $removed entfernt, $unchanged unveraendert, $skipped uebersprungen -> $Target" -Color Green
    return [pscustomobject]@{
        Changed = $changed
        Removed = $removed
        HasChanges = ($changed + $removed) -gt 0
    }
}

function Update-InstalledUpdater {
    $trackedFile = "tools/update-comfyui-rdna4.ps1"
    $installed = Join-Path $Root "update-comfyui-rdna4.ps1"
    $temporaryBlob = [IO.Path]::GetTempFileName()
    try {
        $installed = Resolve-SafeTargetFile -TargetRoot $Root -RelativeFile "update-comfyui-rdna4.ps1"
        Export-GitBlob -BlobId (Get-GitBlobId -TrackedFile $trackedFile) -Destination $temporaryBlob
        if ((Test-Path -LiteralPath $installed -PathType Leaf) -and
            (Get-Sha256 -Path $temporaryBlob) -eq (Get-Sha256 -Path $installed)) {
            return
        }
        Copy-Item -LiteralPath $temporaryBlob -Destination $installed -Force
        Write-Host "PowerShell-Updater fuer den naechsten Lauf aktualisiert: $installed" -ForegroundColor Green
    }
    catch {
        Write-Warning "PowerShell-Updater konnte waehrend dieses Laufs nicht ersetzt werden und wird beim naechsten Lauf erneut versucht: $installed ($($_.Exception.Message))"
    }
    finally {
        Remove-Item -LiteralPath $temporaryBlob -Force -ErrorAction SilentlyContinue
    }
}

function Import-SyncManifest {
    $manifestParent = Split-Path -Parent $SyncManifestPath
    Assert-NoReparsePoints -TargetRoot $manifestParent -Candidate $SyncManifestPath
    if (!(Test-Path -LiteralPath $SyncManifestPath -PathType Leaf)) {
        return
    }
    $manifest = Get-Content -LiteralPath $SyncManifestPath -Raw | ConvertFrom-Json
    foreach ($entry in @($manifest.files)) {
        if ($entry -is [string]) {
            # Manifest v1: nur Pfade, keine Hashes -> keine Erkennung eigener Aenderungen moeglich
            [void]$script:PreviousManifestFiles.Add($entry)
        }
        elseif ($entry -and $entry.path) {
            [void]$script:PreviousManifestFiles.Add([string]$entry.path)
            if ($entry.sha256) {
                $script:PreviousManifestHashes[[string]$entry.path] = [string]$entry.sha256
            }
        }
    }
}

function Export-SyncManifest {
    $manifestParent = Split-Path -Parent $SyncManifestPath
    Assert-NoReparsePoints -TargetRoot $manifestParent -Candidate $SyncManifestPath
    New-Item -ItemType Directory -Path $manifestParent -Force | Out-Null
    $temporaryName = ".dawasteh-bundle-sync-{0}.tmp" -f ([guid]::NewGuid().ToString("N"))
    $temporary = Resolve-SafeTargetFile -TargetRoot $manifestParent -RelativeFile $temporaryName
    try {
        if ([string]::IsNullOrWhiteSpace($DeploymentCommit)) {
            throw "Git-Commit fuer das Sync-Manifest wurde nicht festgelegt."
        }
        $fileEntries = @()
        foreach ($tracked in ($AllDeployedFiles | Sort-Object)) {
            $entry = [ordered]@{ path = $tracked }
            $hash = $script:DeployedHashes[$tracked]
            if (![string]::IsNullOrWhiteSpace($hash)) { $entry["sha256"] = $hash }
            # sha256 remains the expected source hash, not a new permission to
            # overwrite a user's edit on the next run. Record retained bytes separately.
            $preserved = $script:PreservedFileHashes[$tracked]
            if ($preserved) { $entry["preserved_sha256"] = $preserved }
            $fileEntries += [pscustomobject]$entry
        }
        $manifest = [ordered]@{
            version = 2
            release = $ReleaseVersion
            source_repository = $OwnRepo
            source_commit = $DeploymentCommit
            updated_at = (Get-Date).ToString("o")
            files = $fileEntries
        }
        $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $SyncManifestPath -Force
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------
# v1.1.3: Logdatei, Trockenlauf, Versionspruefung, Wiederherstellung,
#         Erkennung persoenlich veraenderter Dateien, Alt->Neu-Migration
# ------------------------------------------------------------

# Alt -> Neu fuer die in v1.1.3 abgeloesten, projektverwalteten Workflows.
# Quelle: tools/consolidate_workflows_v113.py (MIGRATION_MAP).
$WorkflowMigrationMap = [ordered]@{
    "Prompt Enhancer/LLM_Gemma3_12B_General-Prompt-Enhancer.json"             = "Prompt Enhancer/LLM_Gemma4_E4B_FP8-Idea-to-Prompt.json"
    "Prompt Enhancer/LLM_Gemma4_e4b_General-Prompt-Enhancer.json"             = "Prompt Enhancer/LLM_Gemma4_E4B_FP8-Idea-to-Prompt.json"
    "Prompt Enhancer/LLM_Gemma4_e4b_abliterated_General-Prompt-Enhancer.json" = "Prompt Enhancer/LLM_Gemma4_E4B_FP8-Idea-to-Prompt.json"
    "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_All_Reference_Inputs.json" = "Reference to Video/MiniMax_H3_Ref2VA_INT8-All-References-to-Video.json"
    # v1.3.1: einheitliches Namensschema (Modell_Quant-Eingabe-to-Ausgabe), tools/workflow_renames_v131.json
    "Audio to Image/FLUX2_Klein_4B_Gemma4-Audio-Context-to-Image.json"                             = "Audio to Image/FLUX2_Klein_4B_BF16+Gemma4_E4B-Audio-to-Image.json"
    "Audio to Video/FLUX2_Klein_4B_Gemma4-Audio-Context-to-AudioReact-Video.json"                  = "Audio to Video/FLUX2_Klein_4B_BF16+Gemma4_E4B-Audio-to-AudioReact-Video.json"
    "Audio to Video/LTX23-Image+Audio-to-Generative-Matching-Length-Video.json"                    = "Audio to Video/LTX23_22B_FP8-Image+Audio-to-Video.json"
    "Batch Processing/FLUX2_Klein_9B-Batch-Image-Edit.json"                                        = "Batch Processing/FLUX2_Klein_9B_KV_FP8-Folder-to-Images-Batch-Edit.json"
    "Batch Processing/Load-Images-From-Folder-and-Crop.json"                                       = "Batch Processing/Folder-to-Cropped-Images.json"
    "Character & Consistency/FLUX1_Kontext-Character-Keep.json"                                    = "Character & Consistency/FLUX1_Kontext_Dev_FP8-Image+Text-to-Image-Character-Keep.json"
    "Character & Consistency/SDXL_IPAdapter-Character-Keep.json"                                   = "Character & Consistency/SDXL_RealVisXL_V4_FP16+IPAdapter-Image+Text-to-Image-Character-Keep.json"
    "Character & Consistency/SDXL_IPAdapter_FaceID-Character-Keep.json"                            = "Character & Consistency/SDXL_FP16+IPAdapter_FaceID-Image+Text-to-Image-Character-Keep.json"
    "Character Animation/SCAIL2-Character-Animation.json"                                          = "Character Animation/WAN21_SCAIL2_14B_FP8-Image+Video-to-Video-Character-Animation.json"
    "Character Animation/SCAIL2-Character-Replacement.json"                                        = "Character Animation/WAN21_SCAIL2_14B_FP8-Image+Video-to-Video-Character-Replacement.json"
    "Character Animation/WAN21_SCAIL2-Character-Replacement.json"                                  = "Character Animation/WAN21_SCAIL2_14B_FP8+DPO-Image+Video-to-Long-Video-Character-Replacement.json"
    "Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json"                            = "Character Animation/WanAnimate2_14B_INT8-Image+Video-to-Video-Motion-Transfer.json"
    "Controlled Video/Cosmos_Predict2_2B-First-Last-Frame.json"                                    = "Controlled Video/Cosmos_Predict2_2B_BF16-First+Last-Frame-to-Video.json"
    "Controlled Video/Cosmos_Predict2_2B-Image-to-Video.json"                                      = "Controlled Video/Cosmos_Predict2_2B_BF16-Image-to-Video.json"
    "Controlled Video/Cosmos_Predict2_2B-Text-to-Video.json"                                       = "Controlled Video/Cosmos_Predict2_2B_BF16-Text-to-Video.json"
    "Controlled Video/Cosmos_Predict2_2B-Video-Continuation.json"                                  = "Controlled Video/Cosmos_Predict2_2B_BF16-Video-to-Video-Continuation.json"
    "Controlled Video/WAN22_5B_Fun-Control-to-Video.json"                                          = "Controlled Video/WAN22_Fun_Control_5B_BF16-Image+Control-Video-to-Video.json"
    "Game Development/FLUX2_Klein_4B-PS1-Texture-Concept.json"                                     = "Game Development/FLUX2_Klein_4B_BF16-Text-to-PS1-Texture.json"
    "Game Development/Hunyuan3D_v2_1-Low-Poly-Static-Mesh-for-Godot.json"                          = "Game Development/Hunyuan3D_2_1_FP16-Image-to-LowPoly-Mesh-Godot.json"
    "Game Development/Pixal3D_INT8-Buildings-and-Environment-PBR-for-Godot.json"                   = "Game Development/Pixal3D_INT8-Image-to-PBR-Mesh-Buildings-Godot.json"
    "Game Development/Pixal3D_INT8-Humanoids-and-Animals-PBR-for-Godot.json"                       = "Game Development/Pixal3D_INT8-Image-to-PBR-Mesh-Characters-Godot.json"
    "Game Development/Pixal3D_INT8-MultiView-PBR-Collision.json"                                   = "Game Development/Pixal3D_MultiView_INT8-4-Views-to-PBR-Mesh+Collision.json"
    "Game Development/Pixal3D_INT8-PBR-Collision.json"                                             = "Game Development/Pixal3D_INT8-Image-to-PBR-Mesh+Collision.json"
    "Game Development/Pixal3D_INT8-Shape-Collision.json"                                           = "Game Development/Pixal3D_INT8-Image-to-Mesh+Collision.json"
    "Game Development/TRELLIS2_INT8-PBR-Collision.json"                                            = "Game Development/TRELLIS2_INT8-Image-to-PBR-Mesh+Collision.json"
    "Game Development/TRELLIS2_INT8-Shape-Collision.json"                                          = "Game Development/TRELLIS2_INT8-Image-to-Mesh+Collision.json"
    "Image Editing/Bernini_R-Image-Edit.json"                                                      = "Image Editing/Bernini_R_14B_FP8-Image-Edit.json"
    "Image Editing/FLUX2_Klein_4B-One-Image-Edit.json"                                             = "Image Editing/FLUX2_Klein_4B_BF16-Image-Edit.json"
    "Image Editing/FLUX2_Klein_4B-Two-Image-Edit.json"                                             = "Image Editing/FLUX2_Klein_4B_BF16-Two-Image-Edit.json"
    "Image Editing/FLUX2_Klein_9B-Multi-Step-Edit.json"                                            = "Image Editing/FLUX2_Klein_9B_KV_FP8-Multi-Step-Image-Edit.json"
    "Image Editing/FLUX2_Klein_9B-Pixaroma-3D-Builder-Edit.json"                                   = "Image Editing/FLUX2_Klein_9B_KV_FP8-Pixaroma-3D-Scene-to-Image.json"
    "Image Editing/FLUX2_Klein_9B-Pixaroma-Composer-Edit.json"                                     = "Image Editing/FLUX2_Klein_9B_KV_FP8-Pixaroma-Composition-to-Image.json"
    "Image Editing/FLUX2_Klein_9B-Pixaroma-Paint-Edit.json"                                        = "Image Editing/FLUX2_Klein_9B_KV_FP8-Pixaroma-Sketch-to-Image.json"
    "Image Editing/FLUX2_Klein_9B_KV-Four-Image-Edit.json"                                         = "Image Editing/FLUX2_Klein_9B_KV_FP8-Four-Image-Edit.json"
    "Image Editing/FLUX2_Klein_9B_KV-Image-Blend.json"                                             = "Image Editing/FLUX2_Klein_9B_KV_FP8-Two-Images-to-Image-Blend.json"
    "Image Editing/FLUX2_Klein_9B_KV-One-Image-Edit-Custom-Ratio.json"                             = "Image Editing/FLUX2_Klein_9B_Dare_BF16-Image-Edit-Custom-Ratio.json"
    "Image Editing/FLUX2_Klein_9B_KV-One-Image-Edit-Same-Ratio.json"                               = "Image Editing/FLUX2_Klein_9B_KV_FP8-Image-Edit.json"
    "Image Editing/FLUX2_Klein_9B_KV-Three-Image-Edit.json"                                        = "Image Editing/FLUX2_Klein_9B_KV_FP8-Three-Image-Edit.json"
    "Image Editing/FLUX2_Klein_9B_KV-Two-Image-Edit.json"                                          = "Image Editing/FLUX2_Klein_9B_KV_FP8-Two-Image-Edit.json"
    "Image Editing/FLUX2_Klein_9B_Qwen3_5-Image-to-Prompt-to-Image.json"                           = "Image Editing/FLUX2_Klein_9B_KV_FP8+Qwen3_5_4B-Image-to-Prompt-to-Image.json"
    "Image Editing/Multi-Character-Angles-One-Click.json"                                          = "Image Editing/Qwen_Image_Edit_2511_BF16-Image-to-8-Camera-Angles.json"
    "Image Editing/Qwen_Image_Edit_2509-Image-Edit.json"                                           = "Image Editing/Qwen_Image_Edit_2509_FP8-Image-Edit.json"
    "Image Editing/Qwen_Image_Edit_2511_Action-LoRA-Image-Edit.json"                               = "Image Editing/Qwen_Image_Edit_2511_BF16+Action_LoRA-Image-Edit.json"
    "Image Editing/SDXL_Illustrious-Face-and-Hand-Detailer.json"                                   = "Image Editing/SDXL_Illustrious_V2_FP16-Text-to-Image-Face+Hand-Detailer.json"
    "Image Editing/SDXL_Illustrious-Simple-Image-to-Image.json"                                    = "Image Editing/SDXL_Illustrious_V2_FP16-Image-to-Image.json"
    "Image Editing/SDXL_Illustrious-Super-Composite.json"                                          = "Image Editing/SDXL_Illustrious_FP16-Image-to-Image-Composite.json"
    "Image Editing/SDXL_Illustrious-to-RealVis-Detailer-Chain.json"                                = "Image Editing/SDXL_Illustrious+RealVisXL_FP16-Image-to-Realistic-Image.json"
    "Image Fusion/Krea2_INT8_3-Reference_Fusion.json"                                              = "Image Fusion/Krea2_Turbo_FP8-Three-Images-to-Image-Fusion.json"
    "Image Inpainting/FLUX2_Klein_4B-Inpaint.json"                                                 = "Image Inpainting/FLUX2_Klein_4B_BF16-Image+Mask-Inpaint.json"
    "Image Inpainting/FLUX2_Klein_9B-Pixaroma-Inpaint.json"                                        = "Image Inpainting/FLUX2_Klein_9B_KV_FP8-Image+Mask-Pixaroma-Inpaint.json"
    "Image Inpainting/FLUX2_Klein_9B_KV-Inpaint.json"                                              = "Image Inpainting/FLUX2_Klein_9B_KV_FP8-Image+Mask-Inpaint.json"
    "Image Inpainting/Qwen_Image_2_1_BF16-Mask-Inpaint.json"                                       = "Image Inpainting/Qwen_Image_2_1_BF16-Image+Mask-Inpaint.json"
    "Image Outpainting/FLUX2_Klein_9B_KV-Outpaint-Custom-Ratio.json"                               = "Image Outpainting/FLUX2_Klein_9B_KV_FP8-Image-Outpaint-Custom-Ratio.json"
    "Image Upscaling/Image-4x_NMKD_Siax-Model-Upscale.json"                                        = "Image Upscaling/NMKD_Siax_4x-Image-Upscale.json"
    "Image Upscaling/Image-Simple-Bicubic-Upscale.json"                                            = "Image Upscaling/Bicubic-Image-Upscale.json"
    "Image Upscaling/ZImage_Turbo-Tiled-Upscale.json"                                              = "Image Upscaling/ZImage_Turbo_BF16+NMKD_Siax-Image-Tiled-Upscale.json"
    "Image Utilities/Lama-Object-Remover.json"                                                     = "Image Utilities/LaMa-Image+Mask-Object-Remover.json"
    "Image Utilities/Ming_Image_0_1_Design_Layer_INT8-Layer-Decompose.json"                        = "Image Utilities/Ming_Image_0_1_Design_Layer_INT8-Image-to-Layers.json"
    "Image Utilities/Remove-Background-RMBG.json"                                                  = "Image Utilities/RMBG-Image-to-Transparent-PNG.json"
    "Image Utilities/Remove-Background-Transparent-Items.json"                                     = "Image Utilities/RMBG-Image-to-Transparent-Items.json"
    "Image to 3D-Mesh/Hunyuan3D_v2_1-Image-to-3D-Mesh.json"                                        = "Image to 3D-Mesh/Hunyuan3D_2_1_FP16-Image-to-Mesh.json"
    "Image to 3D-Mesh/Mira_Scene-Image-to-3D-Scene.json"                                           = "Image to 3D-Mesh/Mira_Scene+TRELLIS2_INT8-Image-to-3D-Scene.json"
    "Image to 3D-Mesh/Mira_Scene-Layout-Preview.json"                                              = "Image to 3D-Mesh/Mira_Scene-Image-to-3D-Layout-Preview.json"
    "LoRA Generation/ACE-Step1_5_XL-Voice-LoRA-Training.json"                                      = "LoRA Generation/ACE_Step1_5_XL_SFT_BF16-Songs-to-Voice-LoRA.json"
    "LoRA Generation/Boogu_Image_Base-LoRA-Training.json"                                          = "LoRA Generation/Boogu_Image_Base_BF16-Images-to-LoRA.json"
    "LoRA Generation/FLUX1_Dev-LoRA-Training.json"                                                 = "LoRA Generation/FLUX1_Dev_FP8-Images-to-LoRA.json"
    "LoRA Generation/FLUX2_Klein_4B_Base-LoRA-Training.json"                                       = "LoRA Generation/FLUX2_Klein_Base_4B_BF16-Images-to-LoRA.json"
    "LoRA Generation/Qwen3-TTS_0.6B-Voice-LoRA-Training.json"                                      = "LoRA Generation/Qwen3_TTS_0_6B_Base-Recordings-to-Voice-LoRA.json"
    "LoRA Generation/SDXL-LoRA-Training.json"                                                      = "LoRA Generation/SDXL_RealVisXL_V4_FP16-Images-to-LoRA.json"
    "LoRA Generation/YuE2_3B_BF16-PRIVATE-Style-LoRA-Training.json"                                = "LoRA Generation/YuE2_3B_BF16-PRIVATE-Songs-to-Style-LoRA.json"
    "LoRA Generation/ZImage_Base-LoRA-Training.json"                                               = "LoRA Generation/ZImage_Base_BF16-Images-to-LoRA.json"
    "Music Generation/ACE-Step1_5_Turbo_4B-Music-Generation.json"                                  = "Music Generation/ACE_Step1_5_Turbo_BF16-Tags+Lyrics-to-Song.json"
    "Music Generation/ACE-Step1_5_XL-LoRA-Music-Generation.json"                                   = "Music Generation/ACE_Step1_5_XL_SFT_BF16+LoRA-Tags+Lyrics-to-Song.json"
    "Music Generation/ACE-Step1_5_XL_SFT-Music-Generation.json"                                    = "Music Generation/ACE_Step1_5_XL_SFT_BF16-Tags+Lyrics-to-Song.json"
    "Music Generation/ACE-Step1_5_XL_SFT_APG-Reference-Audio-Music-Generation.json"                = "Music Generation/ACE_Step1_5_XL_SFT_BF16-Reference-Song+Lyrics-to-Song.json"
    "Music Generation/ACE-Step1_5_XL_SFT_Gemma4_e4B-AutoSongwriter-Genre-Selector.json"            = "Music Generation/ACE_Step1_5_XL_SFT_BF16+Gemma4_E4B-Idea-to-Lyrics-to-Song.json"
    "Music Generation/ACE-Step1_5_XL_SFT_INT8_ConvRot-Music-Generation.json"                       = "Music Generation/ACE_Step1_5_XL_SFT_INT8-Tags+Lyrics-to-Song.json"
    "Music Generation/ACE-Step1_5_XL_SFT_Qwen3_5_4B-AutoSongwriter-Genre-Selector.json"            = "Music Generation/ACE_Step1_5_XL_SFT_BF16+Qwen3_5_4B-Idea-to-Lyrics-to-Song.json"
    "Music Generation/HeartMuLa_HappyNewYear_3B_Gemma4_e4B-Idea-to-Lyrics-to-Music.json"           = "Music Generation/HeartMuLa_3B_HappyNewYear+Gemma4_E4B-Idea-to-Lyrics-to-Song.json"
    "Music Generation/HeartMuLa_HappyNewYear_3B_Qwen3_5_4B-Idea-to-Lyrics-to-Music.json"           = "Music Generation/HeartMuLa_3B_HappyNewYear+Qwen3_5_4B-Idea-to-Lyrics-to-Song.json"
    "Music Generation/HeartMuLa_HappyNewYear_3B_R9700-Music-Generation.json"                       = "Music Generation/HeartMuLa_3B_HappyNewYear-Tags+Lyrics-to-Song.json"
    "Music Generation/MiniMax_Music3_FP32-BF16-Text-to-Music.json"                                 = "Music Generation/MiniMax_Music3_FP32-Tags+Lyrics-to-Song.json"
    "Music Generation/StableAudio3_Medium-Audio-Generation.json"                                   = "Music Generation/StableAudio3_Medium_FP32+Qwen3_5_2B-Text-to-Audio.json"
    "Music Generation/StableAudio3_Medium_Gemma4-Image-to-Music.json"                              = "Music Generation/StableAudio3_Medium_FP32+Gemma4_E4B-Image-to-Music.json"
    "Music Generation/StableAudio3_Medium_Gemma4-Text-to-Music.json"                               = "Music Generation/StableAudio3_Medium_FP32+Gemma4_E4B-Text-to-Music.json"
    "Music Generation/StableAudio3_Medium_Gemma4-Text-to-Sound.json"                               = "Music Generation/StableAudio3_Medium_FP32+Gemma4_E4B-Text-to-Sound.json"
    "Music Generation/StableAudio3_Medium_INT8_ConvRot-Audio-Generation.json"                      = "Music Generation/StableAudio3_Medium_INT8+Qwen3_5_2B-Text-to-Audio.json"
    "Music Generation/YuE2_3B_BF16-PRIVATE-LoRA-Music-Generation.json"                             = "Music Generation/YuE2_3B_BF16+LoRA-PRIVATE-Tags+Lyrics-to-Song.json"
    "Music Generation/YuE2_3B_INT8-PRIVATE-ABC-to-Music.json"                                      = "Music Generation/YuE2_3B_INT8-PRIVATE-ABC+Lyrics-to-Song.json"
    "Music Generation/YuE2_3B_INT8-PRIVATE-Audio-Cover.json"                                       = "Music Generation/YuE2_3B_INT8-PRIVATE-Song+Lyrics-to-Cover-Song.json"
    "Music Generation/YuE2_3B_INT8-PRIVATE-Text-to-Music.json"                                     = "Music Generation/YuE2_3B_INT8-PRIVATE-Tags+Lyrics-to-Song.json"
    "Music Generation/YuE_7B-FP16_R9700-Music-Generation.json"                                     = "Music Generation/YuE_7B_FP16-Tags+Lyrics-to-Song.json"
    "Music Generation/YuE_7B-FP16_R9700-Reference-Voice-ICL-Music-Generation.json"                 = "Music Generation/YuE_7B_ICL_FP16-Voice+Lyrics-to-Song.json"
    "Music Generation/YuE_7B-INT8_R9700-Music-Generation.json"                                     = "Music Generation/YuE_7B_INT8-Tags+Lyrics-to-Song.json"
    "NSFW/SDXL_AniToReal_v1-Image-to-Image.json"                                                   = "NSFW/SDXL_OneObsession+IllusReal_FP16-Text-to-Anime-to-Real-Image.json"
    "NSFW/SDXL_AniToReal_v2-Image-to-Image.json"                                                   = "NSFW/SDXL_OneObsession+RealVisXL_FP16-Text-to-Anime-to-Real-Image.json"
    "NSFW/SDXL_Illustrious_v2-Text-to-Image.json"                                                  = "NSFW/SDXL_Illustrious_V2_FP16-Image+Text-to-Image.json"
    "NSFW/SDXL_Multi-Checkpoint_v1-Text-to-Image.json"                                             = "NSFW/SDXL_Illustrious+RealVisXL_FP16-Image+Text-to-Image-Multi-Checkpoint.json"
    "Pose & Depth/DepthAnything3-Depth-from-Image.json"                                            = "Pose & Depth/DepthAnything3_Large_FP32-Image-to-Depth.json"
    "Pose & Depth/DepthAnything3-Depth-from-Video.json"                                            = "Pose & Depth/DepthAnything3_Large_FP32-Video-to-Depth-Video.json"
    "Pose & Depth/SDPose-Pose-from-Image.json"                                                     = "Pose & Depth/SDPose_WholeBody_FP16-Image-to-Pose.json"
    "Pose & Depth/SDPose-Pose-from-Video.json"                                                     = "Pose & Depth/SDPose_WholeBody_FP16-Video-to-Pose-Video.json"
    "Prompt Enhancer/Ideogram4_Qwen3_5-Auto-Prompt-to-Image.json"                                  = "Prompt Enhancer/Ideogram4_FP8+Qwen3_5_4B-Idea-to-Prompt-to-Image.json"
    "Prompt Enhancer/LLM_Gemma4_e4b-Audio-to-Text.json"                                            = "Prompt Enhancer/LLM_Gemma4_E4B_FP8-Audio-to-Text.json"
    "Prompt Enhancer/LLM_Gemma4_e4b-Image-to-Prompt.json"                                          = "Prompt Enhancer/LLM_Gemma4_E4B_FP8-Image-to-Prompt.json"
    "Prompt Enhancer/LLM_Gemma4_e4b-Video-to-Description.json"                                     = "Prompt Enhancer/LLM_Gemma4_E4B_FP8-Video-to-Description.json"
    "Prompt Enhancer/LLM_Gemma4_e4b-Video-to-Prompt.json"                                          = "Prompt Enhancer/LLM_Gemma4_E4B_FP8-Video-to-Prompt.json"
    "Prompt Enhancer/LLM_General-Prompt-Enhancer.json"                                             = "Prompt Enhancer/LLM_Gemma4_E4B_FP8-Idea-to-Prompt.json"
    "Prompt Enhancer/LLM_Qwen3_5_4B-Image-to-Prompt.json"                                          = "Prompt Enhancer/LLM_Qwen3_5_4B_BF16-Image-to-Prompt.json"
    "Prompt Enhancer/LLM_Qwen3_5_4B-Text-to-Prompt.json"                                           = "Prompt Enhancer/LLM_Qwen3_5_4B_BF16-Text-to-Prompt.json"
    "Prompt Enhancer/LLM_Qwen3_8_27B-Image-Prompt-Enhancer.json"                                   = "Prompt Enhancer/LLM_Qwen3_8_27B_IQ4_XS-Draft-to-Image-Prompt.json"
    "Prompt Enhancer/MiniMax_H3_Base_FL2VA-Official-Guide-Prompt-Enhancer.json"                    = "Prompt Enhancer/LLM_Qwen3_5_4B_BF16-Idea-to-H3-FL2VA-Prompt.json"
    "Prompt Enhancer/MiniMax_H3_Ref2VA-Official-Guide-Prompt-Enhancer.json"                        = "Prompt Enhancer/LLM_Qwen3_5_4B_BF16-Idea-to-H3-Ref2VA-Prompt.json"
    "Prompt Enhancer/MiniMax_Music3-Official-Skill-Caption-Enhancer.json"                          = "Prompt Enhancer/LLM_Qwen3_5_4B_BF16-Idea-to-Music3-Caption.json"
    "Prompt Enhancer/Qwen3VL_8b_fp8_scaled-Krea2-Prompt-Enhancer.json"                             = "Prompt Enhancer/LLM_Qwen3VL_8B_FP8-Idea-to-Krea2-Prompt.json"
    "Prompt Tools/Ideogram4_Qwen3_5-Field-Text-Builder.json"                                       = "Prompt Tools/LLM_Qwen3_5_4B_BF16-Idea-to-Ideogram4-Fields.json"
    "Prompt Tools/Ideogram4_Qwen3_5-JSON-Prompt-Builder.json"                                      = "Prompt Tools/LLM_Qwen3_5_4B_BF16-Idea-to-Ideogram4-JSON.json"
    "Prompt Tools/LLM_Qwen3_4B-Text-Generation.json"                                               = "Prompt Tools/LLM_Qwen3_4B_BF16-Text-to-Text.json"
    "Prompt Tools/LLM_Qwen3_5_4B_abliterated-Text-Generation.json"                                 = "Prompt Tools/LLM_Qwen3_5_4B_Abliterated_BF16-Image-to-Text.json"
    "Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json"                    = "Reference to Video/MiniMax_FastH3_INT8-Song+Lyrics-to-Music-Video.json"
    "Reference to Video/MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json"            = "Reference to Video/MiniMax_H3_FL2VA_INT8-First+Last-Frame-to-Video.json"
    "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json"              = "Reference to Video/MiniMax_H3_Ref2VA_INT8-All-References-to-Video.json"
    "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_Picture_and_Video_to_Video_LOCAL.json"          = "Reference to Video/MiniMax_H3_Ref2VA_INT8-Image+Video-to-Video.json"
    "Reference to Video/MiniMax_H3_Spectrum_RefImage_Audio_to_Video_OriginalAudio_AutoLength.json" = "Reference to Video/MiniMax_H3_Ref2VA_INT8-Image+Audio-to-Video.json"
    "Reference to Video/MiniMax_H3_Spectrum_RefImage_RefVideo_to_Video_Audio_AutoLength.json"      = "Reference to Video/MiniMax_H3_Ref2VA_INT8-Image+Video-to-Video-Keep-Sound.json"
    "Talking Video/WAN21_InfiniteTalk-Multi-Speaker.json"                                          = "Talking Video/WAN21_InfiniteTalk_14B_FP8-Images+Voices-to-Talking-Video.json"
    "Templates & Tests/FLUX1_vs_FLUX2-Model-Comparison.json"                                       = "Templates & Tests/FLUX1_vs_FLUX2_Dev-Text-to-Image-Comparison.json"
    "Text to Image/Anima_base_v1-Text-to-Image.json"                                               = "Text to Image/Anima_Base_V1_BF16-Text-to-Image.json"
    "Text to Image/Anima_hosekiLustrousmix_v10-Text-to-Image.json"                                 = "Text to Image/Anima_HosekiLustrousmix_V10_BF16-Text-to-Image.json"
    "Text to Image/Boogu_image_base-Text-to-Image.json"                                            = "Text to Image/Boogu_Image_Base_BF16-Text-to-Image.json"
    "Text to Image/Boogu_turbo_via_LoRA-Text-to-Image.json"                                        = "Text to Image/Boogu_Image_Base_BF16+Turbo_LoRA-Text-to-Image.json"
    "Text to Image/Cosmos_Predict2_2B-Text-to-Image.json"                                          = "Text to Image/Cosmos_Predict2_2B_BF16-Text-to-Image.json"
    "Text to Image/FLUX1_EclecticEuphoria_Distilled_v2-Text-to-Image.json"                         = "Text to Image/FLUX1_EclecticEuphoria_Distilled_V2_Q6_K-Text-to-Image.json"
    "Text to Image/FLUX1_EclecticEuphoria_Libre_v2-Text-to-Image.json"                             = "Text to Image/FLUX1_EclecticEuphoria_Libre_V2_FP8-Text-to-Image.json"
    "Text to Image/FLUX1_Kontext_dev-Text-to-Image.json"                                           = "Text to Image/FLUX1_Kontext_Dev_FP8-Text-to-Image.json"
    "Text to Image/FLUX1_dev_Q6_K-Text-to-Image.json"                                              = "Text to Image/FLUX1_Dev_Q6_K-Text-to-Image.json"
    "Text to Image/FLUX1_dev_abliterated_Q8-Text-to-Image.json"                                    = "Text to Image/FLUX1_Dev_Abliterated_Q8_0-Text-to-Image.json"
    "Text to Image/FLUX1_dev_fp8-Text-to-Image.json"                                               = "Text to Image/FLUX1_Dev_FP8-Text-to-Image.json"
    "Text to Image/FLUX2_Klein_4b-Text-to-Image.json"                                              = "Text to Image/FLUX2_Klein_4B_BF16-Text-to-Image.json"
    "Text to Image/FLUX2_Klein_9B_Qwen3_5-Text-to-Prompt-to-Image.json"                            = "Text to Image/FLUX2_Klein_9B_KV_FP8+Qwen3_5_4B-Idea-to-Prompt-to-Image.json"
    "Text to Image/FLUX2_Klein_9b_Q6_K-Text-to-Image.json"                                         = "Text to Image/FLUX2_Klein_9B_Q6_K-Text-to-Image.json"
    "Text to Image/FLUX2_Klein_9b_dare_merged-Text-to-Image.json"                                  = "Text to Image/FLUX2_Klein_9B_Dare_BF16-Text-to-Image.json"
    "Text to Image/FLUX2_Klein_9b_kv_fp8-Text-to-Image.json"                                       = "Text to Image/FLUX2_Klein_9B_KV_FP8-Text-to-Image.json"
    "Text to Image/FLUX2_Klein_base_4b-Text-to-Image.json"                                         = "Text to Image/FLUX2_Klein_Base_4B_BF16-Text-to-Image.json"
    "Text to Image/FLUX2_dev_Q6_K-Text-to-Image.json"                                              = "Text to Image/FLUX2_Dev_Q6_K-Text-to-Image.json"
    "Text to Image/FLUX2_dev_fp8mixed-Text-to-Image.json"                                          = "Text to Image/FLUX2_Dev_FP8mixed-Text-to-Image.json"
    "Text to Image/FLUX2_dev_fp8mixed_v2-Text-to-Image.json"                                       = "Text to Image/FLUX2_Dev_FP8mixed_V2-Text-to-Image.json"
    "Text to Image/Ideogram4-Text-to-Image.json"                                                   = "Text to Image/Ideogram4_FP8-Text-to-Image.json"
    "Text to Image/Krea2_raw-Text-to-Image.json"                                                   = "Text to Image/Krea2_Raw_BF16-Text-to-Image.json"
    "Text to Image/Krea2_turbo-2K-Text-to-Image.json"                                              = "Text to Image/Krea2_Turbo_FP8-Idea-to-Prompt-to-2K-Image.json"
    "Text to Image/Krea2_turbo-Extra-Pass-Text-to-Image.json"                                      = "Text to Image/Krea2_Turbo_FP8-Text-to-Image-Extra-Pass.json"
    "Text to Image/Krea2_turbo-Low-VRAM-Text-to-Image.json"                                        = "Text to Image/Krea2_Turbo_FP8-Text-to-Image-Low-VRAM.json"
    "Text to Image/Krea2_turbo-Uncensored-Prompt-Enhanced-Text-to-Image.json"                      = "Text to Image/Krea2_Turbo_FP8+Qwen3VL_4B_Abliterated-Idea-to-Prompt-to-Image.json"
    "Text to Image/Krea2_turbo_via_LoRA-Text-to-Image.json"                                        = "Text to Image/Krea2_Raw_BF16+Turbo_LoRA-Text-to-Image.json"
    "Text to Image/LongCat_image-Text-to-Image.json"                                               = "Text to Image/LongCat_Image_BF16-Text-to-Image.json"
    "Text to Image/LongCat_image_turbo-Text-to-Image.json"                                         = "Text to Image/LongCat_Image_Turbo_BF16-Text-to-Image.json"
    "Text to Image/Ming_Image_0_1_Design_INT8-Transparent-RGBA.json"                               = "Text to Image/Ming_Image_0_1_Design_INT8-Text-to-Transparent-Image.json"
    "Text to Image/SD15_v1-5-pruned-emaonly-Text-to-Image.json"                                    = "Text to Image/SD15_Base_FP16-Text-to-Image.json"
    "Text to Image/SD21_wd-1-5-beta2-unclip-Text-to-Image.json"                                    = "Text to Image/SD21_WaifuDiffusion_1_5_Beta2_FP16-Text-to-Image.json"
    "Text to Image/SDXL_EclecticEuphoria_Illus_Real_v3-Text-to-Image.json"                         = "Text to Image/SDXL_EclecticEuphoria_IllusReal_V3_FP16-Text-to-Image.json"
    "Text to Image/SDXL_EclecticEuphoria_Illustrious_v2-Text-to-Image.json"                        = "Text to Image/SDXL_EclecticEuphoria_Illustrious_V2_FP16-Text-to-Image.json"
    "Text to Image/SDXL_NoobAI_XL_v1_1-Text-to-Image.json"                                         = "Text to Image/SDXL_NoobAI_XL_V1_1_BF16-Text-to-Image.json"
    "Text to Image/SDXL_RealVisXL_V4-Text-to-Image.json"                                           = "Text to Image/SDXL_RealVisXL_V4_FP16-Text-to-Image.json"
    "Text to Image/SDXL_animij_v8-Text-to-Image.json"                                              = "Text to Image/SDXL_Animij_V8_FP16-Text-to-Image.json"
    "Text to Image/SDXL_moodyRealMix_zitV4DPO-Text-to-Image.json"                                  = "Text to Image/ZImage_Turbo_MoodyRealMix_V4_DPO_BF16-Text-to-Image.json"
    "Text to Image/SDXL_novaAnimeXL_ilV190-Text-to-Image.json"                                     = "Text to Image/SDXL_NovaAnimeXL_IL_V190_FP16-Text-to-Image.json"
    "Text to Image/SDXL_oneObsession_v20Bold-Text-to-Image.json"                                   = "Text to Image/SDXL_OneObsession_V20_Bold_FP16-Text-to-Image.json"
    "Text to Image/SDXL_ponyDiffusionV6XL-Text-to-Image.json"                                      = "Text to Image/SDXL_PonyDiffusion_V6_FP16-Text-to-Image.json"
    "Text to Image/SDXL_ultrarealFineTune_v4-Text-to-Image.json"                                   = "Text to Image/FLUX1_Dev_UltraReal_V4_FP8-Text-to-Image.json"
    "Text to Image/ZImage_base-Text-to-Image.json"                                                 = "Text to Image/ZImage_Base_BF16-Text-to-Image.json"
    "Text to Image/ZImage_turbo-Text-to-Image.json"                                                = "Text to Image/ZImage_Turbo_BF16-Text-to-Image.json"
    "Text to Video/LTX23_dev_Q8_GGUF-Text-to-Video.json"                                           = "Text to Video/LTX23_22B_Dev_Q8_0-Text-to-Video.json"
    "Text to Video/LTX23_dev_mxfp8-Text-to-Video.json"                                             = "Text to Video/LTX23_22B_Dev_MXFP8-Text-to-Video.json"
    "Text to Video/LTX23_distilled_fp8-Text-to-Video.json"                                         = "Text to Video/LTX23_22B_Distilled_FP8-Text-to-Video.json"
    "Text to Video/LTX23_distilled_mxfp8-Text-to-Video.json"                                       = "Text to Video/LTX23_22B_Distilled_MXFP8-Text-to-Video.json"
    "Text to Video/LTX25_INT8_ConvRot-Text-to-Video.json"                                          = "Text to Video/LTX25_22B_INT8-Text-to-Video.json"
    "Text to Video/WAN22_14B_fp8_lightx2v-Text-to-Video.json"                                      = "Text to Video/WAN22_14B_FP8+LightX2V-Text-to-Video.json"
    "Text+Image to Video/Kandinsky5_Lite-Text+Image-to-Video.json"                                 = "Text+Image to Video/Kandinsky5_Lite_BF16-Text+Image-to-Video.json"
    "Text+Image to Video/LTX23-Image-to-Video.json"                                                = "Text+Image to Video/LTX23_22B_FP8-Text+Image-to-Video.json"
    "Text+Image to Video/LTX23_Director-Prompt-Replay.json"                                        = "Text+Image to Video/LTX23_22B_Distilled_FP8-Text+Image-to-Video-Director-Replay.json"
    "Text+Image to Video/LTX23_Director_Q8_GGUF-Tiled-Video-Generation.json"                       = "Text+Image to Video/LTX23_22B_Dev_Q8_0-Text+Image-to-Video-Director-Tiled.json"
    "Text+Image to Video/LTX23_Director_fp8-2-Stage.json"                                          = "Text+Image to Video/LTX23_22B_FP8-Text+Image-to-Video-Director-2-Stage.json"
    "Text+Image to Video/LTX23_First+Last-Frame-Custom-Audio.json"                                 = "Text+Image to Video/LTX23_22B_FP8-First+Last-Frame+Audio-to-Video.json"
    "Text+Image to Video/LTX25_INT8_ConvRot-First+Last-Frame-to-Video.json"                        = "Text+Image to Video/LTX25_22B_INT8-First+Last-Frame-to-Video.json"
    "Text+Image to Video/LTX25_INT8_ConvRot-Image-to-Video.json"                                   = "Text+Image to Video/LTX25_22B_INT8-Text+Image-to-Video.json"
    "Text+Image to Video/WAN22_5B-Text+Image-to-Video.json"                                        = "Text+Image to Video/WAN22_TI2V_5B_FP16-Text+Image-to-Video.json"
    "Text+Image to Video/WAN22_bernini_i2v-Text+Image-to-Video.json"                               = "Text+Image to Video/Bernini_R_14B_FP8-Text+Image-to-Video.json"
    "Text+Image to Video/WAN22_i2v_14B_Q8_GGUF_lightx2v-Text+Image-to-Video.json"                  = "Text+Image to Video/WAN22_I2V_14B_Q8_0_LightX2V-Text+Image-to-Video.json"
    "Text+Image to Video/WAN22_i2v_14B_fp8_lightx2v-Text+Image-to-Video.json"                      = "Text+Image to Video/WAN22_I2V_14B_FP8+LightX2V-Text+Image-to-Video.json"
    "Video Editing/Bernini_R-Video-Editing.json"                                                   = "Video Editing/Bernini_R_14B_FP8-Video+Text-to-Video-Edit.json"
    "Video Upscaling/MiniMax_H3-Latent-Upscaler-3D-FastH3.json"                                    = "Video Upscaling/MiniMax_FastH3_INT8-Video-Latent-Upscale.json"
    "Video Upscaling/MiniMax_H3-Ultimate-Upscale-FastH3.json"                                      = "Video Upscaling/MiniMax_FastH3_INT8-Video-Ultimate-Upscale.json"
    "Video Upscaling/WAN22_14B_LowNoise-Video-Upscale.json"                                        = "Video Upscaling/WAN22_T2V_14B_LowNoise_FP8-Video-Upscale.json"
    "Video to Audio/MMAudio_Video-to-Audio.json"                                                   = "Video to Audio/MMAudio_Large_FP32-Video-to-Audio.json"
    "Vocal Separation/Local_Vocal_Remover_MelBandRoFormer.json"                                    = "Vocal Separation/MelBandRoFormer_FP16-Song-to-Vocals+Instrumental.json"
    "Voice Design/MOSS-TTS_Local_v1.5-Audio+Transcript-to-Speech-Continuation.json"                = "Voice Design/MOSS_TTS_V1_5_BF16-Voice+Transcript-to-Speech-Continuation.json"
    "Voice Design/MOSS-TTS_Local_v1.5-Text+Voice-Reference-to-Speech.json"                         = "Voice Design/MOSS_TTS_V1_5_BF16-Text+Voice-to-Speech.json"
    "Voice Design/Qwen3-TTS_LoRA-Low-Latency-Live-Voice.json"                                      = "Voice Design/Qwen3_TTS_0_6B_Base+LoRA-Text-to-Speech-Live.json"
    "Voice Design/QwenTTS_CustomVoice-Text-to-Voice.json"                                          = "Voice Design/Qwen3_TTS_1_7B_CustomVoice_BF16-Text-to-Speech.json"
    "Voice Design/QwenTTS_VoiceClone-Load-Saved-Voice.json"                                        = "Voice Design/Qwen3_TTS_1_7B_Base_BF16-Saved-Voice+Text-to-Speech.json"
    "Voice Design/QwenTTS_VoiceClone-Multi-Voice-Dialogue.json"                                    = "Voice Design/Qwen3_TTS_1_7B_Base_BF16-Voices+Script-to-Dialogue.json"
    "Voice Design/QwenTTS_VoiceClone-Save-Voice.json"                                              = "Voice Design/Qwen3_TTS_1_7B_Base_BF16-Voice-to-Saved-Voice.json"
    "Voice Design/QwenTTS_VoiceClone-Voice-Generation.json"                                        = "Voice Design/Qwen3_TTS_1_7B_Base_BF16-Voice+Text-to-Speech.json"
    "Voice Design/QwenTTS_VoiceDesign-Dialogue.json"                                               = "Voice Design/Qwen3_TTS_1_7B_VoiceDesign_BF16-Descriptions+Script-to-Dialogue.json"
    "Voice Design/QwenTTS_VoiceDesign-Save-Voice.json"                                             = "Voice Design/Qwen3_TTS_1_7B_VoiceDesign_BF16-Description-to-Saved-Voice.json"
    "Voice Design/QwenTTS_VoiceDesign-Voice-Generation.json"                                       = "Voice Design/Qwen3_TTS_1_7B_VoiceDesign_BF16-Description+Text-to-Speech.json"
    "Voice Design/RVC_DirectML-Live-Microphone-Voice-Swap.json"                                    = "Voice Design/RVC_DirectML-Microphone-to-Voice-Swap-Live.json"
}

$script:LogFile = $null
$script:SkippedUserFiles = [System.Collections.Generic.List[string]]::new()
$script:PreviousManifestHashes = @{}

function Initialize-UpdateLog {
    if ($DryRun) {
        $script:LogFile = $null
        return
    }
    if ([string]::IsNullOrWhiteSpace($LogPath)) {
        $logDir = Join-Path $Root "logs"
        $script:LogFile = Join-Path $logDir ("update-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    }
    else {
        $script:LogFile = $LogPath
    }
    $script:LogFile = [IO.Path]::GetFullPath($script:LogFile)
    $parent = Split-Path -Parent $script:LogFile
    Assert-NoReparsePoints -TargetRoot $parent -Candidate $script:LogFile
    if ($parent -and !(Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $header = @(
        "=== DaWasteh ComfyUI Bundle Update ===",
        "Zeit:        $((Get-Date).ToString('o'))",
        "Release:     $(if ([string]::IsNullOrWhiteSpace($ReleaseVersion)) { '(neuester Tag)' } else { $ReleaseVersion })",
        "ComfyUIRoot: $Root",
        "Bundle:      $OwnRepo",
        "DryRun:      $($DryRun.IsPresent)",
        "Upstream:    $IncludeUpstream",
        "Deps:        $UpdateDependencies",
        "Force:       $($Force.IsPresent)",
        ""
    )
    Set-Content -LiteralPath $script:LogFile -Value $header -Encoding UTF8
}

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string] $Message,
        [string] $Level = "INFO",
        [System.ConsoleColor] $Color = [System.ConsoleColor]::Gray
    )
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "HH:mm:ss"), $Level, $Message
    if ($script:LogFile) {
        Add-Content -LiteralPath $script:LogFile -Value $line -Encoding UTF8
    }
    switch ($Level) {
        "WARN"   { Write-Warning $Message }
        "ERROR"  { Write-Host $Message -ForegroundColor Red }
        default  { Write-Host $Message -ForegroundColor $Color }
    }
}

function Write-DryRun {
    param([Parameter(Mandatory = $true)][string] $Message)
    Write-Log -Message "TROCKENLAUF: $Message" -Level "DRY" -Color DarkYellow
}

function Assert-ReleaseVersion {
    <#  Prueft, dass der Bundle-Checkout die angeforderte Release-Version wirklich enthaelt,
        bevor irgendetwas geschrieben wird. Akzeptiert den Tag selbst oder einen Nachfahren. #>
    if ([string]::IsNullOrWhiteSpace($ReleaseVersion)) {
        $latestTag = & git -C $OwnRepo describe --tags --abbrev=0 --match "v*" 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($latestTag)) {
            Write-Log "Kein Release-Tag im Bundle-Checkout erreichbar; HEAD wird ohne Versionspruefung uebernommen." -Level "WARN"
            return
        }
        $script:ReleaseVersion = ([string]$latestTag).Trim()
        Write-Log "Release-Version aus dem neuesten Tag bestimmt: $ReleaseVersion" -Color DarkGray
    }
    $tagExists = & git -C $OwnRepo tag --list $ReleaseVersion
    if ($LASTEXITCODE -eq 0 -and ![string]::IsNullOrWhiteSpace($tagExists)) {
        & git -C $OwnRepo merge-base --is-ancestor $ReleaseVersion HEAD 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw ("Der Bundle-Checkout enthaelt $ReleaseVersion nicht. " +
                   "Erst 'git -C $OwnRepo pull' ausfuehren oder -ReleaseVersion anpassen.")
        }
        Write-Log "Release $ReleaseVersion ist im Checkout enthalten." -Color DarkGreen
        return
    }
    # Tag noch nicht veroeffentlicht: Release-Kandidat aus dem Arbeitsstand zulassen, aber melden.
    Write-Log ("Tag $ReleaseVersion existiert im Bundle-Repository noch nicht; " +
               "es wird der aktuelle HEAD als Release-Kandidat uebernommen.") -Level "WARN"
}

function Test-UserModifiedFile {
    <#  True, wenn die installierte Datei weder dem neuen Stand noch dem zuletzt
        ausgelieferten Stand entspricht - also lokal veraendert wurde. #>
    param(
        [Parameter(Mandatory = $true)][string] $TargetFile,
        [Parameter(Mandatory = $true)][string] $TrackedFile,
        [Parameter(Mandatory = $true)][string] $CurrentHash
    )
    if (!(Test-Path -LiteralPath $TargetFile -PathType Leaf)) { return $false }
    $previous = $script:PreviousManifestHashes[$TrackedFile]
    if ([string]::IsNullOrWhiteSpace($previous)) { return $false }  # ohne Vergleichsstand nicht entscheidbar
    $installed = Get-Sha256 -Path $TargetFile
    return ($installed -ne $previous -and $installed -ne $CurrentHash)
}

function Restore-FromBackup {
    param([Parameter(Mandatory = $true)][string] $BackupDirectory)
    if (!(Test-Path -LiteralPath $BackupDirectory -PathType Container)) {
        throw "Backup-Verzeichnis nicht gefunden: $BackupDirectory"
    }
    $mapPath = Join-Path $BackupDirectory "restore-map.json"
    if (!(Test-Path -LiteralPath $mapPath -PathType Leaf)) {
        throw ("Dieses Backup enthaelt keine restore-map.json und kann nicht automatisch " +
               "zurueckgespielt werden: $BackupDirectory")
    }
    $entries = @((Get-Content -LiteralPath $mapPath -Raw | ConvertFrom-Json).entries)
    $restored = 0
    $missing = 0
    foreach ($entry in $entries) {
        $from = Join-Path $BackupDirectory $entry.backup
        $to = $entry.original
        if (!(Test-Path -LiteralPath $from -PathType Leaf)) { $missing++; continue }
        if ($DryRun) {
            Write-DryRun "wuerde wiederherstellen: $to"
            $restored++
            continue
        }
        $parent = Split-Path -Parent $to
        if ($parent -and !(Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Copy-Item -LiteralPath $from -Destination $to -Force
        $restored++
    }
    Write-Log "Wiederherstellung: $restored Datei(en) zurueckgespielt, $missing fehlten im Backup." -Color Green
    Write-Log "ComfyUI neu starten, damit der zurueckgespielte Stand geladen wird." -Color Yellow
}

function Report-WorkflowMigration {
    <#  Meldet die Alt->Neu-Zuordnung fuer die in diesem Release abgeloesten Workflows.
        Das eigentliche Entfernen erledigt die manifestbasierte Loeschlogik. #>
    Write-Log "" 
    Write-Log "Abgeloeste Workflows dieses Releases (Alt -> Neu):" -Color Cyan
    foreach ($old in $WorkflowMigrationMap.Keys) {
        $installedOld = Join-Path $WorkflowTarget ($old -replace '/', '\')
        $state = if (Test-Path -LiteralPath $installedOld -PathType Leaf) { "alt noch installiert, wird entfernt" } else { "alt bereits entfernt" }
        Write-Log ("  {0}   [{2}]`n      -> {1}" -f $old, $WorkflowMigrationMap[$old], $state) -Color DarkGray
    }
}

if (!(Test-Path -LiteralPath $Repo)) { throw "ComfyUI Repo nicht gefunden: $Repo" }
if (!(Test-Path -LiteralPath $PythonExe)) { throw "Python in venv nicht gefunden: $PythonExe" }

$env:GIT_TERMINAL_PROMPT = "0"
$env:GIT_MERGE_AUTOEDIT = "no"
$env:PIP_NO_INPUT = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Remove-Item Env:HSA_OVERRIDE_GFX_VERSION -ErrorAction SilentlyContinue
Remove-Item Env:HIP_LAUNCH_BLOCKING -ErrorAction SilentlyContinue
Remove-Item Env:CUDA_LAUNCH_BLOCKING -ErrorAction SilentlyContinue
Remove-Item Env:PYTORCH_TUNABLEOP_ENABLED -ErrorAction SilentlyContinue

Initialize-UpdateLog
Write-Log "Logdatei: $($script:LogFile)" -Color DarkGray
if ($DryRun) { Write-Log "TROCKENLAUF aktiv - es wird nichts geschrieben oder geloescht." -Color Yellow }

if (![string]::IsNullOrWhiteSpace($RestoreFrom)) {
    Write-Log "Wiederherstellungsmodus: $RestoreFrom" -Color Cyan
    Assert-ComfyServersStopped
    Restore-FromBackup -BackupDirectory $RestoreFrom
    Write-Log "Fertig (Wiederherstellung)." -Color Green
    return
}

Assert-ComfyServersStopped
Assert-CanonicalOwnRepository
Assert-CleanOwnRepository
Remove-LegacyOwnRepository

if ($IncludeUpstream) {
    Write-Log ""
    Write-Log "=== Update ComfyUI Core ===" -Color Cyan
    if ($DryRun) { Write-DryRun "wuerde ComfyUI-Core per Fast-Forward aktualisieren: $Repo" }
    else { Update-GitRepository $Repo }

    Write-Log ""
    Write-Log "=== Update Pixaroma und Spectrum MiniMax H3 ===" -Color Cyan
    Warn-PixaromaManagerCopies
    foreach ($trackedNode in $GitTrackedNodes) {
        $trackedTarget = Join-Path (Join-Path $Repo "custom_nodes") $trackedNode.Name
        Write-Log "GitHub-Node: $($trackedNode.Name)" -Color DarkCyan
        if ($DryRun) { Write-DryRun "wuerde aktualisieren: $trackedTarget" }
        else { Ensure-GitDirectory -Path $trackedTarget -RepositoryUrl $trackedNode.Url }
    }
}
else {
    Write-Log ""
    Write-Log ("ComfyUI-Core und fremde Node-Packs bleiben unveraendert " +
               "(-SkipUpstream angegeben).") -Color DarkGray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Update eigene DaWasteh Workflows und Custom Nodes" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan

# v1.1.3: Im Trockenlauf wird nichts geholt; ohne konfiguriertes Upstream (z. B. auf einem
# lokalen Release-Kandidaten-Branch) wird der Pull uebersprungen statt abzubrechen.
if ($DryRun) {
    Write-DryRun "wuerde das Bundle-Repository aktualisieren: $OwnRepo"
}
else {
    # Query without expected stderr: PS 5.1 + Stop treats native stderr as fatal,
    # even with 2>$null (e.g. a local release branch without an upstream).
    $branchRef = & git -C $OwnRepo rev-parse --symbolic-full-name HEAD
    if ($LASTEXITCODE -ne 0) { throw "Bundle-Branch konnte nicht gelesen werden." }
    $upstreamRef = & git -C $OwnRepo for-each-ref '--format=%(upstream)' $branchRef
    if ($LASTEXITCODE -ne 0) { throw "Bundle-Upstream konnte nicht gelesen werden." }
    if (![string]::IsNullOrWhiteSpace($upstreamRef)) {
        Update-GitRepository $OwnRepo
    }
    else {
        Write-Log ("Kein Upstream fuer den aktuellen Branch in $OwnRepo; " +
                   "es wird der lokale Stand ausgeliefert.") -Level "WARN"
    }
}
Assert-CleanOwnRepository
$DeploymentCommit = & git -C $OwnRepo rev-parse --verify HEAD
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($DeploymentCommit)) {
    throw "Deployment-Commit konnte nicht festgelegt werden: $OwnRepo"
}
$DeploymentCommit = $DeploymentCommit.Trim()
Assert-ReleaseVersion
Write-Log "Release $ReleaseVersion, Bundle-Commit $DeploymentCommit" -Color DarkGreen
if ($DryRun) { Write-DryRun "wuerde den installierten Updater ersetzen" } else { Update-InstalledUpdater }
Import-SyncManifest

$workflowSync = Install-GitTrackedDirectory `
    -RelativeSource "workflows" `
    -Target $WorkflowTarget `
    -BackupGroup "workflows-DaWasteh"

$ChangedCustomNodeNames = [System.Collections.Generic.List[string]]::new()
foreach ($nodeName in $CustomNodeNames) {
    $nodeSync = Install-GitTrackedDirectory `
        -RelativeSource "custom_nodes/$nodeName" `
        -Target (Join-Path $Repo "custom_nodes\$nodeName") `
        -BackupGroup "custom-node-$nodeName"
    if ($nodeSync.HasChanges) {
        $ChangedCustomNodeNames.Add($nodeName)
    }
}
$MiraSceneTarget = Join-Path $Root "third_party\Mira-Scene"
Write-Log "Mira-Scene-Code (gepinnt $($MiraSceneCommit.Substring(0, 12))): $MiraSceneTarget" -Color DarkCyan
if ($DryRun) { Write-DryRun "wuerde Mira-Scene auf $MiraSceneCommit auschecken: $MiraSceneTarget" }
else { Ensure-PinnedCheckout -Path $MiraSceneTarget -RepositoryUrl $MiraSceneRepoUrl -Commit $MiraSceneCommit }

# v1.1.7: start scripts use the same commit/hash/backup/local-edit protection as nodes.
$launcherSync = Install-GitTrackedDirectory `
    -RelativeSource "tools" `
    -Target $Root `
    -BackupGroup "launchers" `
    -IncludeFiles @("tools/start-MultiGPU.ps1", "tools/start-MultiGPU.bat")
$supervisorSync = Install-GitTrackedDirectory `
    -RelativeSource "tools/scripts" `
    -Target (Join-Path $Root "scripts") `
    -BackupGroup "console-supervisor" `
    -IncludeFiles @("tools/scripts/windows_comfy_launcher.py")
Report-WorkflowMigration
if ($DryRun) { Write-DryRun "wuerde das Sync-Manifest schreiben: $SyncManifestPath" } else { Export-SyncManifest }

if ($BackupCreated) {
    Write-Log "Backup der wirklich geaenderten Dateien: $BackupRoot" -Color Yellow
    Write-Log ("Rueckweg: update-comfyui-rdna4.ps1 -RestoreFrom '" + $BackupRoot + "'") -Color Yellow
}
elseif ($DryRun) {
    Write-Log "Trockenlauf beendet; es wurde nichts geschrieben." -Color Yellow
}
else {
    Write-Log "Eigene Workflows und Nodes sind bereits aktuell; kein Backup notwendig." -Color DarkGreen
}
if ($script:SkippedUserFiles.Count -gt 0) {
    Write-Log ""
    Write-Log ("{0} Datei(en) wurden wegen lokaler Aenderungen NICHT angefasst:" -f $script:SkippedUserFiles.Count) -Level "WARN"
    foreach ($f in $script:SkippedUserFiles) { Write-Log "    $f" -Color DarkYellow }
    Write-Log "Mit -Force werden diese Dateien ueberschrieben (vorher wird gesichert)." -Color DarkYellow
}

# v1.1.6: pip/torch/requirements werden standardmaessig aktualisiert; -SkipDependencies laesst
# die funktionierende Python-/Torch-/ROCm-Umgebung unangetastet.
if (-not $UpdateDependencies) {
    Write-Log ""
    Write-Log ("Python-/Torch-/ROCm-Umgebung bleibt unveraendert " +
               "(-SkipDependencies angegeben).") -Color DarkGray
}
elseif ($DryRun) {
    Write-DryRun "wuerde pip/wheel/setuptools, torch[device-gfx1201], torchvision, torchaudio und die requirements aktualisieren"
}
else {
    Write-Log ""
    Write-Log "=== Update Python Basis ===" -Color Cyan
    Invoke-NativeCommand $PythonExe "-m" "pip" "install" "--upgrade" "pip" "wheel" "setuptools<82"

    Write-Log ""
    Write-Log "=== Update PyTorch ROCm RDNA4 gfx1201 ===" -Color Cyan
    Invoke-NativeCommand $PythonExe "-m" "pip" "install" "--upgrade" "--no-cache-dir" "--index-url" $TorchIndex `
        "torch[device-gfx1201]" `
        "torchvision[device-gfx1201]" `
        "torchaudio"

    Write-Log ""
    Write-Log "=== Update ComfyUI + eigene Node-Abhaengigkeiten ===" -Color Cyan
    Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" (Join-Path $Repo "requirements.txt")
    Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" (Join-Path $Repo "manager_requirements.txt")
}

# Re-check all owned requirements without --upgrade. A previous skipped/failed
# dependency run may already have synced the node files; changed-files-only
# would then skip the missing dependencies forever on subsequent runs.
foreach ($nodeName in ($(if ($UpdateDependencies -and -not $DryRun) { $CustomNodeNames } else { @() }))) {
    $nodeRequirements = Join-Path $Repo "custom_nodes\$nodeName\requirements.txt"
    if (Test-Path -LiteralPath $nodeRequirements) {
        Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" $nodeRequirements
    }
}
if (-not $UpdateDependencies -and $ChangedCustomNodeNames.Count -gt 0) {
    Write-Log ("requirements der geaenderten eigenen Custom Nodes werden wegen -SkipDependencies " +
               "nicht installiert: " + ($ChangedCustomNodeNames -join ", ")) -Level "WARN"
}

# Apply these pins last because several Qwen3-TTS node packs otherwise upgrade
# transformers/huggingface-hub to mutually incompatible versions.
# Both switches must also cover the last-writer compatibility pins.
if (-not $UpdateDependencies) {
    Write-Log "Qwen3-TTS- und DirectML-Pins bleiben unveraendert (-SkipDependencies)." -Color DarkGray
}
elseif ($DryRun) {
    Write-DryRun "wuerde die Qwen3-TTS-Pins, den DirectML-ONNX-Runtime-Pin und den protobuf/insightface-Pin anwenden"
}
else {
    if (Test-Path -LiteralPath $QwenTtsConstraints) {
        Write-Log "Apply Qwen3-TTS compatibility constraints" -Color Cyan
        Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" $QwenTtsConstraints
    }

    # DirectML must own the "onnxruntime" import: insightface/other packs pull the
    # CPU or CUDA wheel, which installs the same module path and silently removes
    # DmlExecutionProvider. Re-install the DirectML build last, without deps.
    Write-Log "Apply DirectML ONNX Runtime pin (last writer wins)" -Color Cyan
    Invoke-NativeCommand $PythonExe "-m" "pip" "uninstall" "-y" "onnxruntime-gpu"
    Invoke-NativeCommand $PythonExe "-m" "pip" "install" "--force-reinstall" "--no-deps" "onnxruntime-directml>=1.24.4"
    $DirectMlCheck = @'
import onnxruntime
providers = onnxruntime.get_available_providers()
print("onnxruntime", onnxruntime.__version__, providers)
if "DmlExecutionProvider" not in providers:
    raise SystemExit("DmlExecutionProvider missing after onnxruntime-directml install")
'@
    $DirectMlFile = Join-Path $env:TEMP ("comfyui-directml-check-{0}.py" -f ([guid]::NewGuid().ToString("N")))
    try {
        Set-Content -Path $DirectMlFile -Value $DirectMlCheck -Encoding UTF8
        Invoke-NativeCommand $PythonExe $DirectMlFile
    }
    finally {
        Remove-Item $DirectMlFile -Force -ErrorAction SilentlyContinue
    }

    # v1.3.1: IP-Adapter FaceID needs insightface, insightface imports onnx, and onnx needs protobuf >= 4.25 and
    # ml_dtypes. YuE's descript-audiotools still declares protobuf < 3.20 (it only imports tensorboard, which runs
    # with 5.x), so every requirements pass would pull protobuf back to 3.19.6. Pin last, without deps: the insightface
    # wheel would otherwise pull the CPU onnxruntime over the DirectML build and a second OpenCV.
    Write-Log "Apply protobuf/onnx/insightface pin for IP-Adapter FaceID (last writer wins)" -Color Cyan
    Invoke-NativeCommand $PythonExe "-m" "pip" "install" "--no-deps" "protobuf==5.29.6" "ml_dtypes==0.6.0" "insightface==1.0.1"
    $FaceIdCheck = @'
import google.protobuf, onnx, onnxruntime
from insightface.app import FaceAnalysis
print("protobuf", google.protobuf.__version__, "onnx", onnx.__version__, "insightface ok")
if "DmlExecutionProvider" not in onnxruntime.get_available_providers():
    raise SystemExit("DmlExecutionProvider missing after the insightface pin")
'@
    $FaceIdFile = Join-Path $env:TEMP ("comfyui-faceid-check-{0}.py" -f ([guid]::NewGuid().ToString("N")))
    try {
        Set-Content -Path $FaceIdFile -Value $FaceIdCheck -Encoding UTF8
        Invoke-NativeCommand $PythonExe $FaceIdFile
    }
    finally {
        Remove-Item $FaceIdFile -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Validierung" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan

# A dry run has not deployed a manifest. Validating the old installation here
# can fail on a first install or on precisely the stale files the update would fix.
if ($DryRun) {
    Write-DryRun "wuerde Commit-Identitaet, Workflow-/Node-Dateien und Torch/ROCm nach dem Update validieren"
    Write-Log "Trockenlauf fertig. Keine persistenten Aenderungen oder Paketinstallationen." -Color Green
    return
}

$ValidationScript = @'
from __future__ import annotations
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
source_repo = Path(sys.argv[3])
node_names = sys.argv[4:]
workflows = repo / "user" / "default" / "workflows" / "DaWasteh"
node_roots = [repo / "custom_nodes" / name for name in node_names]
if not node_roots:
    raise SystemExit("No custom-node packs were supplied for validation")

launcher_paths = {"tools/start-MultiGPU.ps1", "tools/start-MultiGPU.bat", "tools/scripts/windows_comfy_launcher.py"}
tracked_roots = ["workflows", *(f"custom_nodes/{name}" for name in node_names), *sorted(launcher_paths)]
manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
source_commit = manifest.get("source_commit")
if not isinstance(source_commit, str) or not source_commit:
    raise SystemExit("Deployment manifest has no source commit")
tracked = subprocess.run(
    ["git", "-C", str(source_repo), "ls-tree", "-r", "--name-only", source_commit, "--", *tracked_roots],
    check=True,
    capture_output=True,
    text=True,
    encoding="utf-8",
).stdout.splitlines()
manifest_files = manifest.get("files")
if not isinstance(manifest_files, list):
    raise SystemExit("Deployment manifest does not match the Git-tracked source file set")
# Manifest v1 fuehrt reine Pfade, v2 Objekte mit path + sha256.
manifest_paths = set()
preserved_hashes = {}
for item in manifest_files:
    if isinstance(item, str):
        manifest_paths.add(item)
    elif isinstance(item, dict) and isinstance(item.get("path"), str):
        manifest_paths.add(item["path"])
        if "preserved_sha256" in item:
            value = item["preserved_sha256"]
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in value):
                raise SystemExit("Invalid preserved-file hash in deployment manifest")
            preserved_hashes[item["path"]] = value.upper()
    else:
        raise SystemExit("Deployment manifest has an unreadable file entry")
if manifest_paths != set(tracked):
    raise SystemExit("Deployment manifest does not match the Git-tracked source file set")

for relative in tracked:
    committed_bytes = subprocess.run(
        ["git", "-C", str(source_repo), "cat-file", "blob", f"{source_commit}:{relative}"],
        check=True,
        capture_output=True,
    ).stdout
    if relative.startswith("workflows/"):
        target = workflows / Path(relative.removeprefix("workflows/"))
    elif relative in launcher_paths:
        target = repo.parent / Path(relative.removeprefix("tools/"))
    else:
        matching_name = next(
            (name for name in node_names if relative.startswith(f"custom_nodes/{name}/")),
            None,
        )
        if matching_name is None:
            raise SystemExit(f"Unmapped tracked deployment path: {relative}")
        target = repo / "custom_nodes" / matching_name / Path(
            relative.removeprefix(f"custom_nodes/{matching_name}/")
        )
    if not target.is_file():
        raise SystemExit(f"Deployed file is missing: {target}")
    target_hash = hashlib.sha256(target.read_bytes()).hexdigest().upper()
    if relative in preserved_hashes:
        if target_hash != preserved_hashes[relative]:
            raise SystemExit(f"Preserved local file changed during update: {target}")
        print(f"PRESERVED LOCAL (not synchronized to source commit): {target}")
    elif hashlib.sha256(committed_bytes).hexdigest().upper() != target_hash:
        raise SystemExit(f"Deployed file differs from committed Git blob {source_commit}: {target}")

workflow_files = sorted(workflows.rglob("*.json"))
if not workflow_files:
    raise SystemExit("No DaWasteh workflows were installed")
for path in workflow_files:
    with path.open("r", encoding="utf-8-sig") as handle:
        json.load(handle)

python_files = []
for node_root in node_roots:
    for path in sorted(node_root.rglob("*.py")):
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        python_files.append(path)

print(
    f"Validated {len(tracked)} tracked paths ({len(preserved_hashes)} explicitly preserved local files), "
    f"{len(workflow_files)} workflow JSON files, "
    f"and {len(python_files)} Python files in {len(node_roots)} custom-node packs"
)
'@
$ValidationFile = Join-Path $env:TEMP ("comfyui-dawasteh-validate-{0}.py" -f ([guid]::NewGuid().ToString("N")))
try {
    Set-Content -Path $ValidationFile -Value $ValidationScript -Encoding UTF8
    $ValidationArguments = @($ValidationFile, $Repo, $SyncManifestPath, $OwnRepo) + $CustomNodeNames
    Invoke-NativeCommand $PythonExe @ValidationArguments
}
finally {
    Remove-Item $ValidationFile -Force -ErrorAction SilentlyContinue
}

$TorchCheck = @'
import torch
print("torch:", torch.__version__)
print("hip:", getattr(torch.version, "hip", None))
print("cuda available:", torch.cuda.is_available())
print("device count:", torch.cuda.device_count())
for i in range(torch.cuda.device_count()):
    props = torch.cuda.get_device_properties(i)
    name = torch.cuda.get_device_name(i)
    arch = getattr(props, "gcnArchName", "unknown")
    vram_gib = props.total_memory / (1024 ** 3)
    print(f"{i}: {name} | arch={arch} | total_vram={vram_gib:.2f} GiB | compute={props.major}.{props.minor}")
'@
$TorchCheckFile = Join-Path $env:TEMP ("comfyui-torch-check-{0}.py" -f ([guid]::NewGuid().ToString("N")))
try {
    Set-Content -Path $TorchCheckFile -Value $TorchCheck -Encoding UTF8
    Invoke-NativeCommand $PythonExe $TorchCheckFile
}
finally {
    Remove-Item $TorchCheckFile -Force -ErrorAction SilentlyContinue
}

Write-Host ""
if ($DryRun) {
    Write-Log "Trockenlauf fertig. Es wurde nichts geschrieben, geloescht oder installiert." -Color Green
}
else {
    $upstreamNote = if ($IncludeUpstream) { "ComfyUI-Core, Pixaroma und Spectrum MiniMax H3 wurden per Fast-Forward von GitHub aktualisiert." }
                    else { "ComfyUI-Core und fremde Node-Packs blieben unveraendert (-SkipUpstream)." }
    $depsNote = if ($UpdateDependencies) { "pip/torch/requirements wurden aktualisiert." }
                else { "Python-Umgebung blieb unveraendert (-SkipDependencies)." }
    if ($script:SkippedUserFiles.Count -gt 0) {
        Write-Log "Update mit erhaltenen lokalen Anpassungen fertig: $($script:SkippedUserFiles.Count) Datei(en) NICHT synchronisiert; siehe Warnungen und Manifest. $upstreamNote $depsNote" -Level "WARN"
    }
    else {
        Write-Log "Update fertig. Geaenderte Workflows und eigene Custom Nodes wurden aus $OwnRepo synchronisiert; $upstreamNote $depsNote" -Color Green
    }
}
Write-Log "Logdatei: $($script:LogFile)" -Color DarkGray
