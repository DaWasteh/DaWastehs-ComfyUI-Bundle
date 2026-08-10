# ============================================================
# ComfyUI - dual AMD RDNA4 GPU profile
# Repo: L:\ComfyUI\ComfyUI
# venv: L:\ComfyUI\.venv
# HIP order: gpu:0 = R9700, gpu:1 = RX 9070 XT
# ============================================================

$ErrorActionPreference = "Stop"

$Root = "L:\ComfyUI"
$ComfyPath = Join-Path $Root "ComfyUI"
$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$Launcher = Join-Path $Root "scripts\windows_comfy_launcher.py"
$Port = 8188

# Separate DB for the dual-GPU instance.
$DbFile = Join-Path $ComfyPath "user\comfyui-multigpu.db"
$DbUrl = "sqlite:///" + ($DbFile -replace '\\', '/')

# Conservative R9700 profile for the first Windows ROCm multi-GPU tests.
$ReserveVramGb = 4
$EnableDynamicVram = $false
$AsyncOffloadStreams = 0
$DisablePinnedMemory = $true
$PreferHipBlasLt = $false
$DebugHipLaunchBlocking = $false

if (!(Test-Path $ComfyPath)) { throw "ComfyUI folder not found: $ComfyPath" }
if (!(Test-Path $PythonExe)) { throw "Python venv not found: $PythonExe" }
if (!(Test-Path $Launcher)) { throw "Windows launcher not found: $Launcher" }

$Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Listener) {
    $Pids = ($Listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "Port $Port is already in use (PID: $Pids). Stop the existing 8188 instance first."
}

Set-Location $ComfyPath

Remove-Item Env:HSA_OVERRIDE_GFX_VERSION -ErrorAction SilentlyContinue
Remove-Item Env:PYTORCH_TUNABLEOP_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:HIP_LAUNCH_BLOCKING -ErrorAction SilentlyContinue
Remove-Item Env:CUDA_LAUNCH_BLOCKING -ErrorAction SilentlyContinue

# Keep both physical HIP devices visible. HIP reindexes the visible list as
# ComfyUI gpu:0 and gpu:1 in this same order.
$env:HIP_VISIBLE_DEVICES = "0,1"
$env:CUDA_VISIBLE_DEVICES = "0,1"
$env:TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL = "1"

if ($PreferHipBlasLt) {
    $env:TORCH_BLAS_PREFER_HIPBLASLT = "1"
    Remove-Item Env:TORCH_BLAS_PREFER_CUBLASLT -ErrorAction SilentlyContinue
    Remove-Item Env:DISABLE_ADDMM_CUDA_LT -ErrorAction SilentlyContinue
} else {
    $env:TORCH_BLAS_PREFER_HIPBLASLT = "0"
    $env:TORCH_BLAS_PREFER_CUBLASLT = "0"
    $env:DISABLE_ADDMM_CUDA_LT = "1"
}

$CpuThreads = [Environment]::ProcessorCount
$env:OMP_NUM_THREADS = "$CpuThreads"
$env:MKL_NUM_THREADS = "$CpuThreads"
$env:OPENBLAS_NUM_THREADS = "$CpuThreads"
$env:NUMEXPR_NUM_THREADS = "$CpuThreads"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if ($DebugHipLaunchBlocking) {
    $env:HIP_LAUNCH_BLOCKING = "1"
    $env:CUDA_LAUNCH_BLOCKING = "1"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "ComfyUI Dual-GPU Start Profile" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "ComfyUI: $ComfyPath"
Write-Host "Port:    $Port"
Write-Host "DB:      $DbUrl"
Write-Host "HIP:     HIP_VISIBLE_DEVICES=$env:HIP_VISIBLE_DEVICES"
Write-Host "Default: gpu:0 = R9700 (32 GB)"
Write-Host "Helper:  gpu:1 = RX 9070 XT (16 GB)"
Write-Host "VRAM:    reserve-vram=$ReserveVramGb GB"
Write-Host "Profile: DynamicVRAM=$EnableDynamicVram, async-offload=$AsyncOffloadStreams, pinned memory=$(-not $DisablePinnedMemory)"
Write-Host "BLAS:    hipBLASLt=$PreferHipBlasLt"
Write-Host ""

$GpuCheck = "import torch; names=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]; print('torch:', torch.__version__); print('cuda available:', torch.cuda.is_available()); print('device count:', len(names)); [print(f'gpu:{i} = {name}') for i, name in enumerate(names)]; assert len(names) == 2, f'Expected exactly two visible HIP GPUs, found {len(names)}'; assert 'R9700' in names[0] and '9070 XT' in names[1], f'Unexpected HIP order: {names!r}'"
& $PythonExe -c $GpuCheck
if ($LASTEXITCODE -ne 0) {
    Write-Host "Torch/GPU preflight failed." -ForegroundColor Red
    pause
    exit $LASTEXITCODE
}

$ComfyArgs = @(
    "main.py",
    "--enable-manager",
    "--listen", "127.0.0.1",
    "--port", "$Port",
    "--database-url", $DbUrl,
    "--default-device", "0",
    "--use-pytorch-cross-attention",
    "--reserve-vram", "$ReserveVramGb",
    "--disable-dynamic-vram",
    "--disable-async-offload",
    "--disable-pinned-memory",
    "--cache-classic"
)

if ($EnableDynamicVram) {
    $ComfyArgs = $ComfyArgs | Where-Object { $_ -ne "--disable-dynamic-vram" }
    $ComfyArgs += "--enable-dynamic-vram"
}
if ($AsyncOffloadStreams -gt 0) {
    $ComfyArgs = $ComfyArgs | Where-Object { $_ -ne "--disable-async-offload" }
    $ComfyArgs += @("--async-offload", "$AsyncOffloadStreams")
}
if (!$DisablePinnedMemory) {
    $ComfyArgs = $ComfyArgs | Where-Object { $_ -ne "--disable-pinned-memory" }
}

Write-Host "Press Ctrl+C once to stop ComfyUI." -ForegroundColor Green
& $PythonExe $Launcher --python $PythonExe --working-directory $ComfyPath -- @ComfyArgs
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "ComfyUI stopped. ExitCode: $ExitCode" -ForegroundColor Yellow
if ($ExitCode -ne 0) {
    pause
    exit $ExitCode
}
