$ErrorActionPreference = "Stop"
$venvDir = Join-Path $PSScriptRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found. Initializing setup..." -ForegroundColor Cyan
    
    $pythonCmd = Get-Command python, py -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pythonCmd) {
        Write-Error "Python was not found on your system. Please install Python 3.10+ from https://www.python.org/"
        exit 1
    }
    
    Write-Host "Creating virtual environment with $($pythonCmd.Name)..." -ForegroundColor Cyan
    & $pythonCmd.Source -m venv "$venvDir"
    
    Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Cyan
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    Write-Host "Setup complete!" -ForegroundColor Green
}

& "$venvPython" (Join-Path $PSScriptRoot "main.py") @args
