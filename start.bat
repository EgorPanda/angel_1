@echo off
setlocal
title Angel AI - Server
cd /d "%~dp0backend"

set PYLOCAL=%~dp0backend\.venv\Scripts\python.exe

if not exist "%PYLOCAL%" (
  echo [Angel] First run: creating virtual environment...
  py -3 -m venv .venv 2>nul
  if not exist "%PYLOCAL%" python -m venv .venv
  if not exist "%PYLOCAL%" (
    echo [Angel] Python not found. Install Python 3.11+ from python.org and run again.
    pause
    exit /b 1
  )
)

if not exist ".venv\.deps_ok" (
  echo [Angel] Installing dependencies, one time only, needs internet...
  "%PYLOCAL%" -m pip install --upgrade pip >nul
  "%PYLOCAL%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [Angel] Dependencies install failed. Check internet connection and run again.
    pause
    exit /b 1
  )
  echo ok > ".venv\.deps_ok"
)

echo [Angel] Preparing database...
"%PYLOCAL%" -m alembic upgrade head
if errorlevel 1 (
  echo [Angel] Database migration failed.
  pause
  exit /b 1
)

echo [Angel] Starting server at http://127.0.0.1:8000
powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'" >nul 2>nul

"%PYLOCAL%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo [Angel] Server stopped. Close this window to exit.
pause