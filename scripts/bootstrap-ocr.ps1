[CmdletBinding()]
param(
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "3.13",
    [ValidateSet("cpu", "gpu")]
    [string]$PaddleMode = "gpu",
    [ValidateSet("cu118", "cu126", "cu129")]
    [string]$CudaWheel = "cu126"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $repositoryRoot ".venv-ocr"
$ocrRequirementsPath = Join-Path $repositoryRoot "training\yolov8s\ocr-requirements.txt"
$yoloRequirementsPath = Join-Path $repositoryRoot "training\yolov8s\requirements.txt"

if (-not (Test-Path -LiteralPath $ocrRequirementsPath)) {
    throw "OCR requirements were not found at $ocrRequirementsPath"
}
if (-not (Test-Path -LiteralPath $yoloRequirementsPath)) {
    throw "YOLO requirements were not found at $yoloRequirementsPath"
}

Write-Host "Checking Python $PythonVersion..."
& $PythonLauncher "-$PythonVersion" -c "import sys; print(sys.executable); assert sys.version_info[:2] == (3, 13)"
if ($LASTEXITCODE -ne 0) {
    throw "Python $PythonVersion was not found. Install a 64-bit Python 3.13 runtime, then rerun this script."
}

if (-not (Test-Path -LiteralPath $environmentPath)) {
    & $PythonLauncher "-$PythonVersion" -m venv $environmentPath
}

$venvPython = Join-Path $environmentPath "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip

# The runtime package is selected here rather than in ocr-requirements.txt so
# CPU and GPU PaddlePaddle packages cannot be installed together accidentally.
& $venvPython -m pip uninstall -y paddlepaddle paddlepaddle-gpu
if ($PaddleMode -eq "gpu") {
    $paddlePackage = "paddlepaddle-gpu==3.3.0"
    $paddleIndex = "https://www.paddlepaddle.org.cn/packages/stable/$CudaWheel/"
} else {
    $paddlePackage = "paddlepaddle==3.3.0"
    $paddleIndex = "https://www.paddlepaddle.org.cn/packages/stable/cpu/"
}
& $venvPython -m pip install $paddlePackage -i $paddleIndex
& $venvPython -m pip install -r $ocrRequirementsPath
& $venvPython -m pip install -r $yoloRequirementsPath
# PaddleX/ModelScope imports PyTorch when PaddleOCR is constructed. On Windows,
# both runtimes must see the same cuDNN major/minor DLL set; otherwise the first
# loaded cudnn_cnn64_9.dll wins and the other framework fails with WinError 127.
# PyTorch 2.10.0+cu128 bundles cuDNN 9.10, so align Paddle's shared runtime
# package after installing both stacks. Keep this GPU-only to avoid a large
# unnecessary download for CPU environments.
if ($PaddleMode -eq "gpu") {
    & $venvPython -m pip install --force-reinstall --no-deps nvidia-cudnn-cu12==9.10.2.21
}
& $venvPython -c "import paddle; print('Paddle version:', paddle.__version__); print('CUDA build:', paddle.device.is_compiled_with_cuda()); paddle.utils.run_check()"
if ($PaddleMode -eq "gpu") {
    & $venvPython -c "import torch; import paddle; import paddleocr; assert torch.cuda.is_available(), 'PyTorch GPU runtime was not installed'; assert paddle.device.is_compiled_with_cuda(), 'Paddle GPU runtime was not installed'; print('Unified GPU import check: torch + paddleocr OK')"
}

Write-Host "Unified environment is ready: $environmentPath ($PaddleMode, $CudaWheel)"
