# TALOS: Async Build Orchestrator for UE5

Talos is a Django-based build system designed to replace procedural "Builder 2" scripts with a robust, asynchronous job runner. It provides a centralized command center for monitoring and triggering complex Unreal Engine 5 build pipelines.

## 🚀 Key Features

*   **Premium Command Center:** A modern, dark-mode dashboard tailored for build monitoring.
*   **The Big Red Button:** Trigger UE5 builds with a single click.
*   **Reactive UI (HTMX):** Real-time status polling ensures the dashboard reflects task states without manual page refreshes.
*   **True Async Execution:** Tasks are offloaded to Celery workers via Redis, keeping the UI responsive during resource-intensive builds.
*   **System-Wide Shutdown:** A single "Exit" button orchestrates a clean termination of both the Django server and all connected Celery workers.
*   **High Standards:** strictly adheres to the Google Python Style Guide and comprehensive unit/integration testing.

## 🛠 Core Architecture

*   **Framework:** Django 6.x (Running on Daphne ASGI)
*   **Task Queue:** Celery 5.x + Redis
*   **Frontend:** HTMX (Low-JavaScript, high-interactivity)
*   **Database:** SQLite (Local Development)

### Local Environment Setup
To run the required Redis broker via Docker:
```bash
docker run --name redis -p 6379:6379 -d redis
```

## 📋 Operational Guide

1.  **Launch:** Execute `.\talos.bat` from the root directory.
    *   This will launch the **Django Server** (Daphne).
    *   This will launch the **Celery Worker** in a separate window.
    *   This will automatically open your **Web Browser** to the dashboard.
2.  **Trigger Build:** Click the **Execute Build** button. The button will enter a "Queued" state and automatically return to "Execute" once the task completes.
3.  **Shut Down:** Click the **Exit** button in the top right. This will broadcast a termination signal to the Celery workers and then stop the Django process.

## 🖋 Coding Standards

### Python Style
*   **Google Python Style Guide:** Strict adherence to [Google's Style Guide](https://google.github.io/styleguide/pyguide.html).
*   **Docstrings:** Mandatory for all modules, classes, and functions.
*   **Quotes:** Single quotes `'` are preferred for strings.

### Imports
*   **Explicit Imports:** Always import specific classes/functions. Avoid `from . import views`.
*   **Grouping:** Standard library -> Third-party (Django/Celery) -> Local apps.

### File Formatting
*   **Line Length:** Target 80 chars, hard limit 100.
*   **Persistence:** Every source file must end with exactly one newline character.