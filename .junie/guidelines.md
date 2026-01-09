# Talos Project Guidelines

These guidelines define the coding standards, architectural principles, and testing requirements for the Talos orchestration platform.

## 🐍 Python Coding Standards
*   **Style Guide:** Strictly adhere to the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
*   **Type Hinting:** Use type hints for all function signatures and complex variables.
*   **Docstrings:** Use Google-style docstrings for all classes and public methods.
*   **No Placeholders:** All code must be functional; avoid `TODO` or `pass` in production logic.

## 🏗 Architecture & Logic
*   **Async First:** No blocking `time.sleep` calls in the UI thread. All long-running or external operations must flow through **Celery**.
*   **Database:** Use Django models for data persistence. Ensure migrations are descriptive.
*   **Agent Protocol:** Maintain the custom lightweight socket-based protocol (`v2.1.4`) for agent communication.

## 🎨 Frontend & UX (HTMX)
*   **High Interactivity:** Use **HTMX** for dynamic UI updates and streaming (logs/status).
*   **Minimal Javascript:** Avoid custom JS unless absolutely necessary; leverage HTMX attributes.
*   **Single-Line Tags:** Keep Django template tags single-line to prevent rendering artifacts.
*   **Visual Integrity:** Maintain the dark-mode theme, Inter & Outfit typography, and glassmorphism style.

## 🧪 Testing & Verification
*   **Test-Driven Development (TDD):** New logic must be accompanied by matching tests. If logic changes and no test fails, the mission is violated.
*   **Protocol Robustness:** Every agent command must be tested for malformed payloads and concurrency in `test_agent_robust.py`.
*   **UI Testing:** Use Playwright for browser-level verification, including visual checks (e.g., button colors).
*   **Integration:** Verify Celery task sequences before implementation.

## ⚙️ Workflow
*   **Environment:** Use PowerShell for terminal commands on Windows.
*   **Dependencies:** Manage via `requirements.txt` and `pyproject.toml`.
*   **Separators:** Do not use `&&` as a statement separator in scripts or batch files.
