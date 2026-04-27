@echo off
TITLE Are-Self Launcher

echo ========================================================
echo   ARE-SELF
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

:: Start Docker Containers (Postgres, Redis, NGINX)
:: NGINX reverse-proxies to Daphne on ports 80/443. Cert autodetect:
:: drop cert.pem + key.pem in .\nginx\certs\ for HTTPS, otherwise HTTP.
if not exist ".\nginx\certs" mkdir ".\nginx\certs"
docker compose up -d

:: Wait for Postgres to accept connections. `docker compose up -d` returns
:: when containers are created, not when Postgres is ready — Daphne and
:: Celery would otherwise race the DB and fail their first connect.
:check_postgres
docker exec are_self_db pg_isready -U postgres -d are_self >nul 2>&1
if %errorlevel% neq 0 (
    echo Waiting for Postgres to accept connections...
    timeout /t 2 >nul
    goto check_postgres
)

:: 1. Start Celery Worker in a new window
echo Starting Celery Worker...
start "Are-Self Worker" cmd /c ".\venv\Scripts\celery -A config worker --loglevel=info --concurrency=4 -P threads -E"
:: 1.5 Start Celery Beats Worker
echo Starting Celery Beats Worker...
:: start "Are-Self Heartbeat" cmd /c ".\venv\Scripts\celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler"

:: 2. Start Django Server in its own window
echo Starting Django Server...
start "Are-Self Django Server" cmd /k ".\venv\Scripts\python.exe manage.py runserver"

timeout /t 3 >nul
echo Start RJS Server
:: UI lives in a sibling repo. Use a path relative to this script so the
:: launcher works on any machine, not just Michael's.
set "UI_DIR=%~dp0..\are-self-ui"
if exist "%UI_DIR%\package.json" (
    start "RJS Server" cmd /k "cd /d ""%UI_DIR%"" && npm run dev"
) else (
    echo   WARNING: are-self-ui not found at %UI_DIR%.
    echo   Clone https://github.com/scipraxian/are-self-ui next to this repo
    echo   and re-run this launcher.
)
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://localhost:5173
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    start "" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" --app=http://localhost:5173
) else (
    :: No Chrome detected — fall back to the default browser.
    start "" "http://localhost:5173"
)


:: If runserver exits, pause so we can see the error
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server stopped with error code %ERRORLEVEL%
    pause
)
