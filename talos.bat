@echo off
TITLE Talos Launcher

echo ========================================================
echo   TALOS BUILD SYSTEM
echo   Initializing Django Server and Celery Worker...
echo ========================================================

:: Ensure we are in the right directory
cd /d "%~dp0"

:: 1. Start Celery Worker in a new window
echo Starting Celery Worker...
start "Talos Worker" cmd /c ".\venv\Scripts\celery -A config worker --loglevel=info --pool=solo"

:: 2. Start Django Server in this window
echo Starting Django Server...
start "" "http://127.0.0.1:8000"
.\venv\Scripts\python.exe manage.py runserver

:: If runserver exits, pause so we can see the error
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server stopped with error code %ERRORLEVEL%
    pause
)