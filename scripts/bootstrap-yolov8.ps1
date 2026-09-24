[CmdletBinding()]
param(
    [string]$Python = "python"
)

# Backward-compatible entry point. The repository now uses one environment
# for PaddleOCR and YOLO: .venv-ocr. `$Python` is retained for callers of the
# old script, but the unified bootstrap should be preferred.
$bootstrapScript = Join-Path $PSScriptRoot "bootstrap-ocr.ps1"
& $bootstrapScript -PythonLauncher "py" -PythonVersion "3.13" -PaddleMode "gpu" -CudaWheel "cu126"
exit $LASTEXITCODE
