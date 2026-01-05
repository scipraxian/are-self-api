# TALOS: Async Build Orchestrator for UE5

Talos is a Django-based build system designed to replace the procedural "Builder 2" scripts with a robust, database-driven, asynchronous job runner.

## Core Architecture
* **Framework:** Django 6.x
* **Async Task Queue:** Celery + Redis (or Django DB Backend for simple dev)
* **Real-time Comms:** Django Channels (Daphne) + HTMX
* **Database:** SQLite (Dev) / PostgreSQL (Prod)

* **Redis:** docker run --name redis -p 6379:6379 -d redis

## Coding Standards

### Python Style
* **Google Python Style Guide:** We adhere strictly to [Google's Style Guide](https://google.github.io/styleguide/pyguide.html).
* **Docstrings:** All modules, classes, and functions must have docstrings.
* **Quotes:** Single quotes `'` are preferred over double quotes `"` for strings, unless the string contains a single quote.

### Imports
* **Explicit Imports:** Do **not** use `from . import views`. Import the specific class or function required.
    * *Bad:* `from . import views` -> `views.home`
    * *Good:* `from .views import HomeView`
* **Grouping:** Standard library first, then third-party (Django), then local apps.

### File Formatting
* **Newline:** Every source file must end with exactly one newline character.
* **Line Length:** Target 80 chars, hard limit 100.

## Operational Guide
1.  **Launch:** Run `talos.bat` in the root directory. This spins up the Web Server and Celery Worker.
2.  **Dashboard:** Access the UI at `http://127.0.0.1:8000`.