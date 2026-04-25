@echo off
TITLE Are-Self Installer

echo ========================================================
echo   ARE-SELF INSTALLER
echo   Setting up the AI Swarm Engine...
echo ========================================================
echo.

:: Ensure we are in the right directory
cd /d "%~dp0"

:: Step 1: Virtual Environment
echo [1/10] Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment. Is Python 3.12+ installed?
    echo         Install from https://www.python.org/downloads/ and make sure
    echo         the "Add Python to PATH" box is checked during setup.
    pause
    exit /b 1
)

:: Step 2: Activate and install dependencies
echo [2/10] Installing Python dependencies...
call .\venv\Scripts\activate
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

:: Step 3: Launch Docker Desktop
echo [3/10] Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

:check_docker
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo   Waiting for Docker Engine...
    timeout /t 3 >nul
    goto check_docker
)

:: Step 4: Start containers
echo [4/10] Starting PostgreSQL, Redis, and NGINX containers...
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
echo [5/10] Enabling pgvector extension...
docker exec -it are_self_db psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;" >nul 2>&1

:: Step 6: Run migrations
echo [6/10] Running database migrations...
.\venv\Scripts\python.exe manage.py migrate
if %errorlevel% neq 0 (
    echo ERROR: Migrations failed.
    pause
    exit /b 1
)

:: Step 7: Ollama + Embedding Model
:: Must happen BEFORE fixtures: zygote.json seeds the nomic-embed-text AIModel row
:: that the Hippocampus uses to embed Engrams. Anything that touches an Engram
:: (including signals fired during later fixture loads or first-run health checks)
:: will hit OllamaClient.embed() and fail if the daemon isn't up and the model
:: isn't pulled.
echo [7/10] Checking Ollama...
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

:check_ollama
ollama list >nul 2>&1
if %errorlevel% neq 0 (
    echo   Waiting for Ollama daemon...
    timeout /t 3 >nul
    goto check_ollama
)

echo   Pulling embedding model...
ollama pull nomic-embed-text
if %errorlevel% neq 0 (
    echo ERROR: Failed to pull nomic-embed-text. Fixtures will fail without it.
    pause
    exit /b 1
)
:: TODO: add the 2 default models.

:: Step 8: Load fixtures
echo [8/10] Loading initial data...
.\venv\Scripts\python.exe manage.py loaddata genetic_immutables.json
.\venv\Scripts\python.exe manage.py loaddata zygote.json
.\venv\Scripts\python.exe manage.py loaddata initial_phenotypes.json

:: Step 9: Create superuser
echo [9/10] Creating admin superuser...
set DJANGO_SUPERUSER_USERNAME=admin
set DJANGO_SUPERUSER_EMAIL=admin@are-self.com
set DJANGO_SUPERUSER_PASSWORD=admin

.\venv\Scripts\python.exe manage.py createsuperuser --noinput 2>nul
if not errorlevel 1 (
    echo   Superuser created [admin/admin].
) else (
    echo   Superuser already exists, skipping.
)

:: Step 10: Frontend dependencies (are-self-ui sibling repo)
::
:: The UI lives in a sibling repo that are-self.bat launches via `npm run dev`.
:: Without its node_modules, the first launch after a fresh clone fails silently
:: in the RJS Server window. Install them here so the launcher just works.
:: The UI folder is expected at ..\are-self-ui relative to this script. If the
:: user downloaded it elsewhere (or skipped cloning it), we warn but continue —
:: the backend is still usable.
echo [10/10] Installing frontend dependencies...
set "UI_DIR=%~dp0..\are-self-ui"
if not exist "%UI_DIR%\package.json" (
    echo   WARNING: could not find are-self-ui at %UI_DIR%.
    echo   Clone https://github.com/scipraxian/are-self-ui next to this repo
    echo   and run `npm install` inside it before launching are-self.bat.
    goto install_done
)

where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo   WARNING: npm was not found on PATH. Node.js 18+ is required for the UI.
    echo   Install from https://nodejs.org/ then run `npm install` inside
    echo   %UI_DIR% before launching are-self.bat.
    goto install_done
)

pushd "%UI_DIR%"
call npm install
if %errorlevel% neq 0 (
    echo   WARNING: npm install failed. The backend is fine; re-run
    echo   `npm install` inside %UI_DIR% before launching are-self.bat.
)
popd

:install_done
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