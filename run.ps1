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

# Ensure bin\ffmpeg.exe is populated from imageio_ffmpeg if missing
$binDir = Join-Path $PSScriptRoot "bin"
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
if (-not (Test-Path $ffmpegExe)) {
    $foundFfmpeg = Get-ChildItem -Path "$venvDir\Lib\site-packages\imageio_ffmpeg\binaries" -Filter "ffmpeg*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($foundFfmpeg) {
        if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir -Force | Out-Null }
        Copy-Item $foundFfmpeg.FullName $ffmpegExe -Force
    }
}

& "$venvPython" (Join-Path $PSScriptRoot "main.py") @args
