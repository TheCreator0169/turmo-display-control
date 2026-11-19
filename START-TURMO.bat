@echo off
:: TURMO Live Hardware Monitor — one-click launcher (no WSL, no PowerShell needed)
:: Starts the continuous monitoring app with your saved settings.
:: Double-click this file. Close the window (or Ctrl+C) to stop monitoring.
setlocal
pushd "%~dp0"

set "PY=.venv-win\Scripts\python.exe"
if not exist "%PY%" (
    echo [TURMO] ERROR: Windows venv not found at %PY%
    echo [TURMO] Run:  .venv-win\Scripts\python -m pip install pyserial psutil pillow
    pause
    exit /b 1
)

:: --monitor = continuous live loop using saved settings (theme/orientation/refresh).
:: Pass-through args (e.g. --theme cyberpunk-neon) override saved settings.
echo [TURMO] Starting live hardware monitor...
echo [TURMO] Close this window to stop. USB unplug/replug auto-recovers.
echo.
"%PY%" scripts\turmo_runtime.py --monitor %*

set "RC=%ERRORLEVEL%"
popd
echo.
echo [TURMO] Monitor stopped (exit %RC%).
pause
exit /b %RC%
