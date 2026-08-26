@echo off
setlocal EnableExtensions
cd /d "%~dp0"

chcp 65001 >nul
set "ROOT=%~dp0"
set "APPLY=0"
set "KEEP_VENV=0"
set "FAILED=0"

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--apply" (
    set "APPLY=1"
) else if /i "%~1"=="/apply" (
    set "APPLY=1"
) else if /i "%~1"=="--keep-venv" (
    set "KEEP_VENV=1"
) else if /i "%~1"=="/keep-venv" (
    set "KEEP_VENV=1"
) else (
    echo [ERROR] Unknown option: %~1
    echo Usage: cleanup_windows.cmd [--apply] [--keep-venv]
    goto finish_error
)
shift
goto parse_args

:args_done
rem Safety check: only operate from the expected project directory.
if not exist "%ROOT%main.py" goto unsafe_root
if not exist "%ROOT%cleanup_windows.cmd" goto unsafe_root
if not exist "%ROOT%config\" goto unsafe_root

echo Project: %ROOT%
echo Always keep: source code, startup scripts, requirements, docs, and config
echo.
echo Cleanup targets:
if "%KEEP_VENV%"=="0" echo   - .venv / venv / env / ENV
echo   - logs
echo   - reports
echo   - data cache
echo   - __pycache__ and Python/test caches
echo.

if "%APPLY%"=="0" (
    echo Preview only. No files were deleted.
    echo Run cleanup_windows.cmd --apply to clean now.
    echo Add --keep-venv only when the virtual environment must be kept.
    goto finish_ok
)

if "%KEEP_VENV%"=="0" (
    call :remove_dir ".venv"
    call :remove_dir "venv"
    call :remove_dir "env"
    call :remove_dir "ENV"
)

call :remove_dir "logs"
call :remove_dir "reports"
call :remove_dir "data"
call :remove_dir ".pytest_cache"
call :remove_dir ".mypy_cache"
call :remove_dir ".ruff_cache"

rem Remove nested Python caches using the same shell and the verified root.
for /d /r "%ROOT%" %%D in (__pycache__) do (
    if exist "%%~fD\" rd /s /q "%%~fD" 2>nul
    if exist "%%~fD\" (
        echo [WARN] Could not remove: %%~fD
        set "FAILED=1"
    )
)
for /r "%ROOT%" %%F in (*.pyc *.pyo) do (
    if exist "%%~fF" del /f /q "%%~fF" 2>nul
)

rem Keep empty runtime directories so the application can start normally.
if not exist "%ROOT%logs\" md "%ROOT%logs"
if not exist "%ROOT%reports\" md "%ROOT%reports"
if not exist "%ROOT%data\" md "%ROOT%data"

if "%FAILED%"=="1" (
    echo.
    echo Cleanup was incomplete. Close the running application and try again.
    goto finish_error
)

echo Cleanup completed.
if "%KEEP_VENV%"=="0" echo Run setup_windows.cmd before starting the application again.
goto finish_ok

:remove_dir
set "TARGET=%ROOT%%~1"
if exist "%TARGET%\" rd /s /q "%TARGET%" 2>nul
if exist "%TARGET%\" (
    echo [WARN] Could not remove: %TARGET%
    set "FAILED=1"
)
exit /b 0

:unsafe_root
echo [ERROR] Safety check failed. Cleanup was cancelled.
echo Expected main.py, cleanup_windows.cmd, and config under: %ROOT%
goto finish_error

:finish_ok
echo.
pause
exit /b 0

:finish_error
echo.
pause
exit /b 1
