@echo off
REM Build PDFCompressor.exe into the dist\ folder.
REM Invoked as a module so it works even if the Scripts folder isn't on PATH.
cd /d "%~dp0"
python -m PyInstaller PDFCompressor.spec --noconfirm
if errorlevel 1 (
    echo.
    echo Build FAILED. See the errors above.
    pause
    exit /b 1
)
echo.
echo Done. The app is the folder: dist\PDFCompressor
echo Run dist\PDFCompressor\PDFCompressor.exe  -  to share, zip the whole folder.
pause
