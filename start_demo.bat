@echo off
cd /d "%~dp0"
set "BUNDLED_PY=C:\Users\11869\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" run.py
) else (
  python run.py
)
pause
