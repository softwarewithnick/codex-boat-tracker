@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py --demo
) else (
    python main.py --demo
)
if errorlevel 1 pause

