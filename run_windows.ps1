# Run this from PowerShell in the project folder:
#   powershell -ExecutionPolicy Bypass -File .\run_windows.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonExe = "py"
    $PythonArgs = @("-3.11")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = "python"
    $PythonArgs = @()
} else {
    Write-Host "Python was not found. Install Python 3.11 (64-bit), then run this file again." -ForegroundColor Red
    exit 1
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvWorks = $false
if (Test-Path $VenvPython) {
    try {
        & $VenvPython --version *> $null
        $VenvWorks = ($LASTEXITCODE -eq 0)
    } catch {
        $VenvWorks = $false
    }
}

if (-not $VenvWorks) {
    if (Test-Path ".venv") {
        Write-Host "Replacing an environment linked to an unavailable Python installation..."
        Remove-Item -Recurse -Force ".venv"
    }
    Write-Host "Creating the project environment..."
    & $PythonExe @PythonArgs -m venv .venv
}

Write-Host "Installing or checking project packages..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

Write-Host "Running quick logic checks..."
& $VenvPython -m unittest discover -s tests -v

Write-Host "Starting Gesture Controlled Computer..."
& $VenvPython app.py
