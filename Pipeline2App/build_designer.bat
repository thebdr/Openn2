@echo off
REM Build the standalone "I/O List Checker" (one-folder) from gui_designer.spec.
REM Prerequisite (one time):  pip install pyinstaller
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Install it first:  pip install pyinstaller
    pause
    exit /b 1
)

pyinstaller --noconfirm gui_designer.spec

REM --- OPTIONAL: code-sign (the durable fix for corporate AV / SmartScreen) -------------
REM If your company has a code-signing certificate, uncomment + set CERT/timestamp and IT
REM can sign the exe so it is trusted. Needs the Windows SDK (signtool.exe).
REM set "CERT=path\to\cert.pfx"
REM signtool sign /f "%CERT%" /p "PFX_PASSWORD" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\IOListChecker\IOListChecker.exe"

echo.
echo Build complete -^> dist\IOListChecker\IOListChecker.exe
echo Ship the whole dist\IOListChecker\ folder (or zip it).
echo If antivirus quarantines it, give IT the file hash to allow-list:
powershell -NoProfile -Command "Get-FileHash 'dist\IOListChecker\IOListChecker.exe' -Algorithm SHA256 | Select-Object -ExpandProperty Hash"
pause
