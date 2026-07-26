@echo off
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -m saipenview
