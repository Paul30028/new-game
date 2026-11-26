@echo off
cd /d "%~dp0"
python tools\relay\control.py
if errorlevel 1 pause
