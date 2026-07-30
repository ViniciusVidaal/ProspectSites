@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python nao encontrado. Execute a instalacao primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" agent\main.py
pause
