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
echo [4/9] Starting PostgreSQL, Redis, and NGINX containers...
:: NGINX binds ports 80/443. If either is in use on this machine, the
:: nginx container will fail to start — the rest of the stack still works.
:: The nginx/certs folder must exist for the bind mount even if empty.
if not exist ".\nginx\certs" mkdir ".\nginx\certs"
docker compose up -d
if %errorlevel% neq 0 (
    echo   WARNING: docker compose reported an error. If it was the nginx
    echo   container, check whether ports 80 or 443 are already in use.
)

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
echo [7/8] Loading initial data...
.\venv\Scripts\python.exe manage.py loaddata genetic_immutables.json
.\venv\Scripts\python.exe manage.py loaddata zygote.json

:: Step 8: Create superuser
echo [8/9] Creating admin superuser...
set DJANGO_SUPERUSER_USERNAME=admin
set DJANGO_SUPERUSER_EMAIL=admin@are-self.com
set DJANGO_SUPERUSER_PASSWORD=admin

.\venv\Scripts\python.exe manage.py createsuperuser --noinput 2>nul
if not errorlevel 1 (
    echo   Superuser created [admin/admin].
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
:: TODO: add the 2 default models.

echo.
echo ========================================================
echo   INSTALLATION COMPLETE
echo.
echo   Launch Are-Self:
echo     .\are-self.bat
echo.
echo   The Docker stack now includes NGINX as a reverse proxy:
echo     - HTTP  on port 80  (default)
echo     - HTTPS on port 443 (drop cert.pem + key.pem in nginx\certs\)
echo   See are-self-docs for the MCP server connection guide.
echo ========================================================
pause