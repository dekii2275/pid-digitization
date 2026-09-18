[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $repositoryRoot ".venv-yolov8s"
$requirementsPath = Join-Path $repositoryRoot "training\yolov8s\requirements.txt"

if (-not (Test-Path -LiteralPath $requirementsPath)) {
    throw "Training requirements were not found at $requirementsPath"
}

& $Python -m venv $environmentPath
$venvPython = Join-Path $environmentPath "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r $requirementsPath

Write-Host "YOLOv8 environment is ready: $environmentPath"
