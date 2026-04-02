@echo off
TITLE Are-Self Installer

echo ========================================================
echo   ARE-SELF INSTALLER
echo   Setting up the AI Reasoning Engine...
echo ========================================================
echo.

:: Ensure we are in the right directory
cd /d "%~dp0"

:: Step 1: Virtual Environment
echo [1/9] Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment. Is Python 3.12+ installed?
    pause
    exit /b 1
)

:: Step 2: Activate and install dependencies
echo [2/9] Installing dependencies...
call .\venv\Scripts\activate
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

:: Step 3: Launch Docker Desktop
echo [3/9] Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

:check_docker
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo   Waiting for Docker Engine...
    timeout /t 3 >nul
    goto check_docker
)

:: Step 4: Start containers
echo [4/9] Starting PostgreSQL and Redis containers...
docker compose up -d

:: Step 5: Enable pgvector
echo [5/9] Enabling pgvector extension...
docker exec -it are_self_db psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;" >nul 2>&1

:: Step 6: Run migrations
echo [6/9] Running database migrations...
.\venv\Scripts\python.exe manage.py migrate
if %errorlevel% neq 0 (
    echo ERROR: Migrations failed.
    pause
    exit /b 1
)

:: Step 7: Load fixtures
echo [7/9] Loading initial data...
for /d %%D in (*) do (
    if exist "%%D\fixtures\initial_data.json" (
        echo   Loading %%D fixtures...
        .\venv\Scripts\python.exe manage.py loaddata "%%D/fixtures/initial_data.json"
    )
)

:: Step 8: Create superuser
echo [8/9] Creating admin superuser...
set DJANGO_SUPERUSER_USERNAME=admin
set DJANGO_SUPERUSER_EMAIL=admin@are-self.com
set DJANGO_SUPERUSER_PASSWORD=admin
.\venv\Scripts\python.exe manage.py createsuperuser --noinput 2>nul
if %errorlevel% equ 0 (
    echo   Superuser created (admin/admin).
) else (
    echo   Superuser already exists, skipping.
)

:: Step 9: Ollama + Embedding Model
echo [9/9] Checking Ollama...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Ollama not found. Installing...
    winget install Ollama.Ollama --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo   WARNING: Could not install Ollama automatically.
        echo   Please install manually from https://ollama.com/download
        pause
    )
)

echo   Pulling embedding model...
ollama pull nomic-embed-text

echo.
echo ========================================================
echo   INSTALLATION COMPLETE
echo.
echo   Launch Are-Self:
echo     .\are_self.bat
echo ========================================================
pause