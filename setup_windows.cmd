@echo off
setlocal
cd /d "%~dp0"

chcp 65001 >nul
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Windows environment is ready. Double-click start_windows.cmd to open the GUI.
exit /b 0

:failed
echo.
echo Setup failed. Install Python 3.9 or newer from https://www.python.org/downloads/windows/
pause
exit /b 1

