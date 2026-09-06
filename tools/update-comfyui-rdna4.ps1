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
    Trockenlauf: zeigt jede Aktion an, schreibt und loescht aber nichts.

.PARAMETER LogPath
    Logdatei. Standard: <ComfyUIRoot>\logs\update-<Zeitstempel>.log

.PARAMETER RestoreFrom
    Stellt einen frueheren Lauf aus dessen Backup-Verzeichnis wieder her und beendet sich danach.

.PARAMETER SkipUpstream
    ComfyUI-Core, Pixaroma und Spectrum NICHT aktualisieren (Standard: werden aktualisiert).

.PARAMETER SkipDependencies
    pip/torch/requirements NICHT aktualisieren (Standard: werden aktualisiert). Die Qwen3-TTS-
    und DirectML-Pins werden trotzdem angewendet.

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
    "ComfyUI-DaWasteh-H3-AutoLength",
    "ComfyUI-DaWasteh-H3-MusicVideo",
    "ComfyUI-DaWasteh-LiveAvatar",
    "ComfyUI-DaWasteh-MultiGPU-Control",
    "ComfyUI-DaWasteh-Qwen3TTS-LoRA"
)

$PixaromaNodeName = "ComfyUI-Pixaroma"
$PixaromaRepoUrl = "https://github.com/pixaroma/ComfyUI-Pixaroma.git"

# Third-party node packs that are tracked directly from GitHub (fast-forward
# only). Spectrum MiniMax H3 v0.1.x breaks on ComfyUI >= 0.34 (PDD FinalLayer
# contract); v0.2.21+ restores forecast execution, so the pack must move with
# the ComfyUI core instead of staying pinned to a Manager snapshot.
$GitTrackedNodes = @(
    @{ Name = $PixaromaNodeName; Url = $PixaromaRepoUrl },
    @{ Name = "comfyui-spectrum-minimax-h3"; Url = "https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3.git" }
)

$BackupRoot = Join-Path $Root ("_update_backups\{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$BackupCreated = $false
$PreviousManifestFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$AllDeployedFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$DeploymentCommit = $null
$script:DeployedHashes = @{}

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
    $activeLaunchers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        if ($_.Name -notin @("python.exe", "pythonw.exe", "powershell.exe", "pwsh.exe")) {
            return $false
        }
        $command = ([string]$_.CommandLine).ToLowerInvariant().Replace('/', '\')
        return $command -like "*l:\comfyui\start-r9700.ps1*" -or
            $command -like "*l:\comfyui\start-9070xt.ps1*" -or
            $command -like "*l:\comfyui\scripts\windows_comfy_launcher.py*" -or
            $command -like "*l:\comfyui\comfyui\main.py*"
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
        [Parameter(Mandatory = $true)][string] $BackupGroup
    )

    $trackedFiles = @(& git -C $OwnRepo ls-tree -r --name-only $DeploymentCommit -- $RelativeSource)
    if ($LASTEXITCODE -ne 0) {
        throw "git ls-tree fehlgeschlagen fuer $RelativeSource bei Commit $DeploymentCommit"
    }
    if ($trackedFiles.Count -eq 0) {
        throw "Keine getrackten Dateien gefunden: $RelativeSource"
    }

    Assert-NoReparsePoints -TargetRoot $Target -Candidate (Join-Path $Target ".dawasteh-sync-preflight")
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
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

            # v1.1.3: persoenlich veraenderte Dateien nicht ungefragt ueberschreiben.
            if (!$Force -and (Test-UserModifiedFile -TargetFile $targetFile -TrackedFile $trackedFile -CurrentHash $sourceHash)) {
                Write-Log ("Uebersprungen (lokal veraendert): $targetFile") -Level "WARN"
                [void]$script:SkippedUserFiles.Add($targetFile)
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
    "Prompt Enhancer/LLM_Gemma3_12B_General-Prompt-Enhancer.json"             = "Prompt Enhancer/LLM_General-Prompt-Enhancer.json"
    "Prompt Enhancer/LLM_Gemma4_e4b_General-Prompt-Enhancer.json"             = "Prompt Enhancer/LLM_General-Prompt-Enhancer.json"
    "Prompt Enhancer/LLM_Gemma4_e4b_abliterated_General-Prompt-Enhancer.json" = "Prompt Enhancer/LLM_General-Prompt-Enhancer.json"
    "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_All_Reference_Inputs.json" = "Reference to Video/MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json"
}

$script:LogFile = $null
$script:SkippedUserFiles = [System.Collections.Generic.List[string]]::new()
$script:PreviousManifestHashes = @{}

function Initialize-UpdateLog {
    if ([string]::IsNullOrWhiteSpace($LogPath)) {
        $logDir = Join-Path $Root "logs"
        $script:LogFile = Join-Path $logDir ("update-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    }
    else {
        $script:LogFile = $LogPath
    }
    $parent = Split-Path -Parent $script:LogFile
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
    & git -C $OwnRepo rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
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

foreach ($nodeName in ($(if ($UpdateDependencies -and -not $DryRun) { $ChangedCustomNodeNames } else { @() }))) {
    $nodeRequirements = Join-Path $Repo "custom_nodes\$nodeName\requirements.txt"
    if (Test-Path -LiteralPath $nodeRequirements) {
        Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" $nodeRequirements
    }
}
if ($ChangedCustomNodeNames.Count -eq 0) {
    Write-Host "Keine eigenen Custom Nodes geaendert; deren requirements werden uebersprungen." -ForegroundColor DarkGreen
}
elseif (-not $UpdateDependencies) {
    Write-Log ("requirements der geaenderten eigenen Custom Nodes werden wegen -SkipDependencies " +
               "nicht installiert: " + ($ChangedCustomNodeNames -join ", ")) -Level "WARN"
}

# Apply these pins last because several Qwen3-TTS node packs otherwise upgrade
# transformers/huggingface-hub to mutually incompatible versions.
# v1.1.3: Beide Pins veraendern die Umgebung und laufen deshalb nicht im Trockenlauf.
if ($DryRun) {
    Write-DryRun "wuerde die Qwen3-TTS-Pins und den DirectML-ONNX-Runtime-Pin anwenden"
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
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Validierung" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan

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

tracked_roots = ["workflows", *(f"custom_nodes/{name}" for name in node_names)]
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
for item in manifest_files:
    if isinstance(item, str):
        manifest_paths.add(item)
    elif isinstance(item, dict) and isinstance(item.get("path"), str):
        manifest_paths.add(item["path"])
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
    if hashlib.sha256(committed_bytes).digest() != hashlib.sha256(target.read_bytes()).digest():
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
    f"Validated {len(tracked)} deployed Git files, {len(workflow_files)} workflow JSON files, "
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
    Write-Log "Update fertig. Geaenderte Workflows und eigene Custom Nodes wurden aus $OwnRepo synchronisiert; $upstreamNote $depsNote" -Color Green
}
Write-Log "Logdatei: $($script:LogFile)" -Color DarkGray
