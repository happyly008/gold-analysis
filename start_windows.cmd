@echo off
setlocal
cd /d "%~dp0"

chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Windows virtual environment is missing.
    echo Run setup_windows.cmd first.
    pause
    exit /b 1
)

if "%~1"=="" (
    start "" /b ".venv\Scripts\pythonw.exe" main.py --gui
    exit /b 0
) else (
    ".venv\Scripts\python.exe" main.py %*
)

if errorlevel 1 (
    echo.
    echo Program exited with an error. See logs\error.log for details.
    pause
)
