@echo off
setlocal EnableDelayedExpansion
title Finance Wise TBM — Build
echo.
echo  ========================================================
echo   Finance Wise TBM — Full Distribution Build
echo  ========================================================
echo.

:: ── Step 1: Collect static files ─────────────────────────────────
echo [1/5] Collecting static files...
python manage.py collectstatic --noinput
if errorlevel 1 ( echo ERROR: collectstatic failed & pause & exit /b 1 )
echo   Done.

:: ── Step 2: Generate a unique SECRET_KEY into desktop.env ─────────
echo [2/5] Generating secure SECRET_KEY...
python update_secret_key.py
if errorlevel 1 ( echo   WARNING: Could not update SECRET_KEY, using existing value. )

:: ── Step 3: Generate app icon ─────────────────────────────────────
echo [3/5] Generating app icon...
python make_icon.py
if errorlevel 1 ( echo   WARNING: Icon generation failed, continuing. )

:: ── Step 4: Clean old dist then build PyInstaller executable ──────
echo [4/5] Building executable with PyInstaller...

:: Kill any running instance first — it locks the DLLs
taskkill /F /IM FinanceWiseTBM.exe >nul 2>&1
timeout /t 2 /nobreak >nul

if exist "dist\FinanceWiseTBM" (
    echo   Cleaning previous build...
    :: Take ownership + grant full control so locked DLLs can be removed
    takeown /f "dist\FinanceWiseTBM" /r /d y >nul 2>&1
    icacls "dist\FinanceWiseTBM" /grant "%USERNAME%:F" /t >nul 2>&1
    :: Robocopy /MIR with an empty folder wipes content even if some files are read-only
    set "EMPTY=%TEMP%\fwtbm_empty_%RANDOM%"
    mkdir "!EMPTY!" 2>nul
    robocopy "!EMPTY!" "dist\FinanceWiseTBM" /MIR /NFL /NDL /NJH /NJS /NC /NS >nul 2>&1
    rmdir /s /q "dist\FinanceWiseTBM" 2>nul
    rmdir /s /q "!EMPTY!" 2>nul
    echo   Old build removed.
)

python -m PyInstaller desktop.spec --noconfirm --clean
if errorlevel 1 ( echo ERROR: PyInstaller build failed & pause & exit /b 1 )
echo   Executable ready: dist\FinanceWiseTBM\FinanceWiseTBM.exe

:: ── Step 5: Build Windows Installer ───────────────────────────────
echo [5/5] Building Windows Installer...
powershell -NoProfile -ExecutionPolicy Bypass -File "compile_installer.ps1"
if errorlevel 1 (
    echo.
    echo   Installer build failed. Portable .exe is still usable:
    echo     dist\FinanceWiseTBM\FinanceWiseTBM.exe
    echo   To build the installer manually:
    echo     1. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
    echo     2. Run: compile_installer.ps1
    pause & exit /b 0
)

echo.
echo  ========================================================
echo   BUILD COMPLETE
echo   Portable:  dist\FinanceWiseTBM\FinanceWiseTBM.exe
echo   Installer: installer_output\FinanceWiseTBM_Setup_v1.0.0.exe
echo  ========================================================
echo.
pause
