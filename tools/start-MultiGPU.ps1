# ============================================================
# ComfyUI - dual AMD RDNA4 GPU profile
# Repo: L:\ComfyUI\ComfyUI
# venv: L:\ComfyUI\.venv
# HIP order: gpu:0 = R9700, gpu:1 = RX 9070 XT
#
# Profile v0.9.8 (2026-09-05), re-measured on this machine with
# ComfyUI 0.34.0, PyTorch 2.13.0+rocm10.1 (HIP 7.16), comfy-kitchen 0.2.31
# (HIP/WMMA backend active on gfx1201), comfy-aimdo 0.5.2:
#
# - hipBLASLt: 100-122 TFLOPS on transformer-sized GEMMs vs. 60-95 TFLOPS
#   with classic hipBLAS. The earlier HIPBLAS_STATUS_NOT_SUPPORTED warning
#   floods for YuE/HeartCodec Conv1d shapes no longer occur on torch 2.13.
# - pinned memory: 26 GiB/s host->GPU vs. 16 GiB/s pageable (512 MiB copies),
#   but it pins up to 40 % of host RAM; keep it off while other multi-GB
#   processes (AutoTuner llama-server, 31 GB commit) share the 48 GB host.
# - AOTriton flash/efficient SDPA works on both GPUs without extra env vars;
#   ComfyUI enables it automatically for gfx1201 on ROCm >= 7.0.
# - DynamicVRAM (comfy-aimdo 0.5.2) is the ComfyUI default on ROCm >= 7.14 and
#   `--disable-dynamic-vram` is scheduled for removal. On this host it stalled
#   for more than eight minutes in "Model Initializing" with 0 % GPU load on
#   Z-Image Turbo (27 GB VRAM were usable); the same graph finished in 84 s
#   with the static loader. Re-test after every ComfyUI/comfy-aimdo update
#   before switching $EnableDynamicVram on.
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

# ---- R9700 dual-GPU profile -------------------------------------------------
$ReserveVramGb = 4
$EnableDynamicVram = $false        # comfy-aimdo DynamicVRAM; see header notes
$AsyncOffloadStreams = 0           # 0 = --disable-async-offload; ComfyUI default on AMD is 2
$DisablePinnedMemory = $true       # pinned copies are 1.6x faster, but ComfyUI locks up to 40 % of
                                   # host RAM (19 GB of 48 GB); with a resident 27B llama-server the
                                   # host swapped and Wan 2.2 14B fell to 765 s/step. Enable only with
                                   # free host RAM (no other multi-GB resident processes).
$CacheMode = "ram"                 # "ram" (ComfyUI default, RAM-pressure aware) or "classic"
$PreferHipBlasLt = $true           # measured +15-40 % GEMM throughput on gfx1201
$UseComfyKitchenAttention = $false # opt-in: --use-ck-attention (INT8 QK attention, quality trade-off)
$FastFp8MatrixMult = $false        # opt-in: --fast fp8_matrix_mult (117 TFLOPS torch._scaled_mm measured)
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
# ComfyUI gpu:0 and gpu:1 in this same order. ComfyUI >= 0.34 forces Windows
# to a single CUDA device unless --cuda-device/--default-device or
# CUDA_VISIBLE_DEVICES is set explicitly; both are set here on purpose.
$env:HIP_VISIBLE_DEVICES = "0,1"
$env:CUDA_VISIBLE_DEVICES = "0,1"
$env:TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL = "1"

if ($PreferHipBlasLt) {
    # torch default for gfx1201 since ROCm 7.15 / PyTorch 2.12; unsupported
    # shapes silently fall back to hipBLAS.
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
Write-Host "ComfyUI Dual-GPU Start Profile v0.9.8" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "ComfyUI: $ComfyPath"
Write-Host "Port:    $Port"
Write-Host "DB:      $DbUrl"
Write-Host "HIP:     HIP_VISIBLE_DEVICES=$env:HIP_VISIBLE_DEVICES"
Write-Host "Default: gpu:0 = R9700 (32 GB)"
Write-Host "Helper:  gpu:1 = RX 9070 XT (16 GB)"
Write-Host "VRAM:    reserve-vram=$ReserveVramGb GB"
Write-Host "Profile: DynamicVRAM=$EnableDynamicVram, async-offload=$AsyncOffloadStreams, pinned memory=$(-not $DisablePinnedMemory), cache=$CacheMode"
Write-Host "BLAS:    hipBLASLt=$PreferHipBlasLt"
Write-Host "Opt-in:  ck-attention=$UseComfyKitchenAttention, fp8_matrix_mult=$FastFp8MatrixMult"
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
    "--reserve-vram", "$ReserveVramGb"
)

if ($EnableDynamicVram) {
    $ComfyArgs += "--enable-dynamic-vram"
} else {
    $ComfyArgs += "--disable-dynamic-vram"
}
if ($AsyncOffloadStreams -gt 0) {
    $ComfyArgs += @("--async-offload", "$AsyncOffloadStreams")
} else {
    $ComfyArgs += "--disable-async-offload"
}
if ($DisablePinnedMemory) {
    $ComfyArgs += "--disable-pinned-memory"
}
if ($CacheMode -eq "classic") {
    $ComfyArgs += "--cache-classic"
} else {
    $ComfyArgs += "--cache-ram"
}
if ($UseComfyKitchenAttention) {
    $ComfyArgs += "--use-ck-attention"
}
if ($FastFp8MatrixMult) {
    $ComfyArgs += @("--fast", "fp8_matrix_mult")
}

Write-Host "Args:    $($ComfyArgs -join ' ')" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C once to stop ComfyUI." -ForegroundColor Green
& $PythonExe $Launcher --python $PythonExe --working-directory $ComfyPath -- @ComfyArgs
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "ComfyUI stopped. ExitCode: $ExitCode" -ForegroundColor Yellow
if ($ExitCode -ne 0) {
    pause
    exit $ExitCode
}
