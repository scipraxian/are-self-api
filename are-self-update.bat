@echo off
TITLE Are-Self Updater

echo ========================================================
echo   ARE-SELF UPDATER
echo   Stopping services, pulling latest, restarting...
echo ========================================================
echo.

:: Ensure we are in the right directory (the are-self-api root).
cd /d "%~dp0"

:: Step 1: Stop the running launcher windows.
:: Match by exact title prefix so we don't accidentally kill an
:: unrelated cmd window. Suppress all output -- taskkill on a
:: non-existent window prints to stderr but it's not a real error.
echo [1/7] Stopping running services...
taskkill /FI "WINDOWTITLE eq Are-Self Worker*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Are-Self Django Server*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq RJS Server*" /T /F >nul 2>&1

:: Docker stays up -- bringing the Postgres / Redis / NGINX
:: containers down here would add ~30s of pg_isready loop on the
:: relaunch in are-self.bat. The Daphne / Celery / Vite processes
:: are the ones the user actually expects to restart on update.

:: Step 2: Pull latest for are-self-api.
echo [2/7] Pulling latest for are-self-api...
git pull --ff-only
if %errorlevel% neq 0 (
    echo.
    echo ERROR: git pull failed in are-self-api. Resolve any
    echo conflict or local-commit divergence in your terminal,
    echo then re-run are-self-update.bat.
    pause
    exit /b 1
)

:: Step 3: Pull latest for any sibling repos that exist.
:: All five live next to are-self-api/. The user may not have
:: cloned all of them -- skip-with-message rather than fail.
echo [3/7] Pulling latest for sibling repos...
call :pull_sibling are-self-ui
call :pull_sibling are-self-docs
call :pull_sibling are-self-research
call :pull_sibling are-self-learn

:: Step 4: Update Python dependencies in the existing venv.
echo [4/7] Updating Python dependencies...
.\venv\Scripts\pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. Check requirements.txt and
    echo your network connection, then re-run.
    pause
    exit /b 1
)

:: Step 5: Run migrations.
:: A failed migration is the one place we MUST stop -- relaunching
:: onto a half-migrated DB produces opaque runtime errors.
echo [5/7] Running database migrations...
.\venv\Scripts\python.exe manage.py migrate
if %errorlevel% neq 0 (
    echo ERROR: Migrations failed. Do not relaunch until resolved.
    pause
    exit /b 1
)

:: Step 6: Reload canonical fixtures.
:: loaddata is upsert-by-PK -- safe to re-run on every update so
:: schema-coupled fixture rows (protocol enums, class-constant rows,
:: zygote boot rows, initial-phenotype structural rows) stay in sync
:: with the new code. Frozen UUIDs in fixtures keep this idempotent;
:: a new release that adds rows lands them, existing rows get any
:: field-level updates from upstream.
echo [6/7] Loading canonical fixtures...
.\venv\Scripts\python.exe manage.py loaddata genetic_immutables.json
.\venv\Scripts\python.exe manage.py loaddata zygote.json
.\venv\Scripts\python.exe manage.py loaddata initial_phenotypes.json
if %errorlevel% neq 0 (
    echo ERROR: Fixture load failed. Do not relaunch until resolved.
    pause
    exit /b 1
)

:: Step 7: Update UI dependencies, then relaunch.
echo [7/7] Updating UI dependencies...
set "UI_DIR=%~dp0..\are-self-ui"
if exist "%UI_DIR%\package.json" (
    pushd "%UI_DIR%"
    call npm install --silent
    popd
)

echo.
echo ========================================================
echo   UPDATE COMPLETE -- relaunching Are-Self...
echo ========================================================
call "%~dp0are-self.bat"
exit /b 0


:pull_sibling
:: %~1 = sibling repo name (e.g. are-self-ui).
set "SIB_DIR=%~dp0..\%~1"
if not exist "%SIB_DIR%\.git" (
    echo   Skipping %~1 -- not cloned next to are-self-api.
    goto :eof
)
pushd "%SIB_DIR%"
git pull --ff-only
if %errorlevel% neq 0 (
    echo   WARNING: git pull failed in %~1. Resolve manually.
)
popd
goto :eof
