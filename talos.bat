@echo off
TITLE Talos Launcher

echo ========================================================
echo   TALOS BUILD SYSTEM
echo   Initializing Django Server and Celery Worker...
echo ========================================================

:: Ensure we are in the right directory
cd /d "%~dp0"

:: Launch Docker Desktop in the background
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

:: Loop to check if the Docker engine is running
:check_docker
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo Waiting for Docker Engine to start...
    :: Wait 3 seconds before checking again
    timeout /t 3 >nul
    goto check_docker
)

:: Start Docker Containers
docker compose up -d

:: 1. Start Celery Worker in a new window
echo Starting Celery Worker...
start "Are-Self Worker" cmd /c ".\venv\Scripts\celery -A config worker --loglevel=info --concurrency=4 -P threads"
:: 1.5 Start Celery Beats Worker
echo Starting Celery Beats Worker...
start "Are-Self Heartbeat" cmd /c ".\venv\Scripts\celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler"

:: 2. Start Django Server in its own window
echo Starting Django Server...
start "" "http://127.0.0.1:8000"
start "Talos Django Server" cmd /k ".\venv\Scripts\python.exe manage.py runserver"

timeout /t 3 >nul
echo Start RJS Server
start "RJS Server" cmd /k "cd /d c:\are-self-ui\ && npm run dev"
start "" "http://localhost:5173"


:: If runserver exits, pause so we can see the error
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server stopped with error code %ERRORLEVEL%
    pause
)

