@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Initializing setup...
    where python >nul 2>&1
    if errorlevel 1 (
        where py >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] Python was not found on your system.
            echo Please install Python 3.10+ from https://www.python.org/
            pause
            exit /b 1
        ) else (
            py -m venv .venv
        )
    ) else (
        python -m venv .venv
    )
    echo [INFO] Installing dependencies from requirements.txt...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    echo [INFO] Setup complete!
)

if not exist "bin\ffmpeg.exe" (
    for /r ".venv\Lib\site-packages\imageio_ffmpeg\binaries" %%f in (ffmpeg*.exe) do (
        if not exist "bin" mkdir bin
        copy "%%f" "bin\ffmpeg.exe" >nul 2>&1
    )
)

".venv\Scripts\python.exe" main.py %*
