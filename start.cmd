@echo off
cd /d "%~dp0"
if exist "C:\Users\Allen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "C:\Users\Allen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py --open %*
) else (
  py app.py --open %*
)
pause
