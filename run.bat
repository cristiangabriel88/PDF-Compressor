@echo off
REM Launch the PDF Compressor app from source.
cd /d "%~dp0"
python main.py
if errorlevel 1 pause
