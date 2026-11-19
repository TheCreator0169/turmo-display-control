@echo off
REM TURMO Display Control - Portable Launcher
REM This script launches the TURMO Display Control application in portable mode.
REM All settings are stored next to the executable.

cd /d "%~dp0"

REM Check if running on Windows
ver | find "Windows" >nul
if errorlevel 1 (
    echo This launcher is for Windows only.
    pause
    exit /b 1
)

REM Set portable mode - settings will be stored in the same directory as the exe
set TURMO_PORTABLE=1

REM Launch the application
start "" "TURMO-Display-Control.exe"

echo TURMO Display Control started in portable mode.
echo Settings will be saved in: %~dp0