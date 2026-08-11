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

$Root = "L:\ComfyUI"
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
    "ComfyUI-DaWasteh-H3-AutoLength",
    "ComfyUI-DaWasteh-H3-MusicVideo",
    "ComfyUI-DaWasteh-LiveAvatar",
    "ComfyUI-DaWasteh-MultiGPU-Control",
    "ComfyUI-DaWasteh-Qwen3TTS-LoRA"
)

$PixaromaNodeName = "ComfyUI-Pixaroma"
$PixaromaRepoUrl = "https://github.com/pixaroma/ComfyUI-Pixaroma.git"
$PixaromaTarget = Join-Path $Repo ("custom_nodes\\{0}" -f $PixaromaNodeName)

$BackupRoot = Join-Path $Root ("_update_backups\{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$BackupCreated = $false
$PreviousManifestFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$AllDeployedFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$DeploymentCommit = $null

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

        throw "Pixaroma-Ziel existiert, ist aber kein Git-Repository und wird nicht automatisch geloescht: $Path"
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
            $isIdentical = $false
            if (Test-Path -LiteralPath $targetFile -PathType Leaf) {
                $sourceInfo = Get-Item -LiteralPath $temporaryBlob
                $targetInfo = Get-Item -LiteralPath $targetFile
                if ($sourceInfo.Length -eq $targetInfo.Length) {
                    $sourceHash = Get-Sha256 -Path $temporaryBlob
                    $targetHash = Get-Sha256 -Path $targetFile
                    $isIdentical = $sourceHash -eq $targetHash
                }
            }

            if ($isIdentical) {
                $unchanged++
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
            Backup-ChangedFile -Path $targetFile -BackupGroup $BackupGroup -RelativeFile $relativeFile
            Remove-Item -LiteralPath $targetFile -Force
            Remove-EmptyParentDirectories -TargetRoot $Target -RemovedFile $targetFile
            $removed++
        }
    }

    Write-Host "Synchronisiert: $changed geaendert, $removed entfernt, $unchanged unveraendert -> $Target" -ForegroundColor Green
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
    foreach ($path in @($manifest.files)) {
        if ($path -is [string]) {
            [void]$script:PreviousManifestFiles.Add($path)
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
        $manifest = [ordered]@{
            version = 1
            source_repository = $OwnRepo
            source_commit = $DeploymentCommit
            updated_at = (Get-Date).ToString("o")
            files = @($AllDeployedFiles | Sort-Object)
        }
        $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $SyncManifestPath -Force
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
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

Assert-ComfyServersStopped
Assert-CanonicalOwnRepository
Assert-CleanOwnRepository
Remove-LegacyOwnRepository

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Update ComfyUI Core" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Update-GitRepository $Repo

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Update Pixaroma direkt von GitHub" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Warn-PixaromaManagerCopies
Ensure-GitDirectory -Path $PixaromaTarget -RepositoryUrl $PixaromaRepoUrl

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Update eigene DaWasteh Workflows und Custom Nodes" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan

Update-GitRepository $OwnRepo
Assert-CleanOwnRepository
$DeploymentCommit = & git -C $OwnRepo rev-parse --verify HEAD
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($DeploymentCommit)) {
    throw "Deployment-Commit konnte nicht festgelegt werden: $OwnRepo"
}
$DeploymentCommit = $DeploymentCommit.Trim()
Update-InstalledUpdater
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
Export-SyncManifest

if ($BackupCreated) {
    Write-Host "Backup der wirklich geaenderten Dateien: $BackupRoot" -ForegroundColor Yellow
}
else {
    Write-Host "Eigene Workflows und Nodes sind bereits aktuell; kein Backup notwendig." -ForegroundColor DarkGreen
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Update Python Basis" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Invoke-NativeCommand $PythonExe "-m" "pip" "install" "--upgrade" "pip" "wheel" "setuptools<82"

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Update PyTorch ROCm RDNA4 gfx1201" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Invoke-NativeCommand $PythonExe "-m" "pip" "install" "--upgrade" "--no-cache-dir" "--index-url" $TorchIndex `
    "torch[device-gfx1201]" `
    "torchvision[device-gfx1201]" `
    "torchaudio"

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "Update ComfyUI + eigene Node-Abhaengigkeiten" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" (Join-Path $Repo "requirements.txt")
Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" (Join-Path $Repo "manager_requirements.txt")

foreach ($nodeName in $ChangedCustomNodeNames) {
    $nodeRequirements = Join-Path $Repo "custom_nodes\$nodeName\requirements.txt"
    if (Test-Path -LiteralPath $nodeRequirements) {
        Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" $nodeRequirements
    }
}
if ($ChangedCustomNodeNames.Count -eq 0) {
    Write-Host "Keine eigenen Custom Nodes geaendert; deren requirements werden uebersprungen." -ForegroundColor DarkGreen
}

# Apply these pins last because several Qwen3-TTS node packs otherwise upgrade
# transformers/huggingface-hub to mutually incompatible versions.
if (Test-Path -LiteralPath $QwenTtsConstraints) {
    Write-Host "Apply Qwen3-TTS compatibility constraints" -ForegroundColor Cyan
    Invoke-NativeCommand $PythonExe "-m" "pip" "install" "-r" $QwenTtsConstraints
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
if not isinstance(manifest_files, list) or set(manifest_files) != set(tracked):
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
Write-Host "Update fertig. Nur geaenderte Workflows und eigene Custom Nodes wurden aus $OwnRepo synchronisiert; Pixaroma wurde direkt von GitHub aktualisiert." -ForegroundColor Green
