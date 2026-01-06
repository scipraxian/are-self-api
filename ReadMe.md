# ⚡ TALOS: Next-Gen UE5 Build Fleet Orchestrator

Talos is a premium, Django-based command center designed to manage, monitor, and orchestrate Unreal Engine 5 build pipelines across a distributed fleet of remote agents. It replaces legacy procedural scripts with a robust, asynchronous architecture and a high-fidelity dashboard.

---

## 💎 Core Philosophy: "Build with Confidence"

Talos isn't just a build runner—it's a mission control center. Every interaction is designed to be visceral and responsive, ensuring that developers can focus on building games while Talos handles the heavy lifting of distribution and execution.

### ✨ Key Features

*   **🔴 The Big Red Button:** A single, high-vibrancy trigger for complex UE5 builds. 
*   **📡 Sonar Agent Discovery:** Automatically scans the network to identify and register Talos Remote Agents.
*   **🛠 Remote Fleet Control:** 
    *   **Launch:** Start UE5 builds remotely with optimized flags (`-AutoStart`, `-resX=1280`, etc.).
    *   **Kill:** Graceful, multi-stage process termination across Windows machines.
    *   **Log Streaming:** Real-time log "Attach" functionality using HTMX streaming.
*   **🔄 Self-Updating Fleet:** One-click "Push Update" securely transmits and restarts the remote agent code across the entire fleet.
*   **⚠️ Version Integrity:** Visual "Update Needed" badges pulse when a remote agent's code drifts from the server's version (v2.1.2).
*   **🎨 Premium Aesthetics:** Dark-mode interface featuring **Inter** & **Outfit** typography, glassmorphism, and hardware-accelerated animations.

---

## 🏗 Architecture & Tech Stack

Talos is built for speed, stability, and maximum responsiveness:

*   **Backend:** Django 6.x (running on **Daphne ASGI** for high-concurrency).
*   **Task Queue:** **Celery 5.x** + **Redis** for true non-blocking execution.
*   **Fleet Protocol:** Custom lightweight socket-based protocol (`v2.1.2`) for low-latency agent communication.
*   **Frontend:** **HTMX** for high-interactivity with near-zero Javascript.
*   **Design:** Vanilla CSS with modern tokens (linear gradients, box-shadows, and micro-animations).

---

## 🧪 Extreme Verification (The Test Suite)

We don't trust—we verify. Talos maintains three distinct testing tiers:

1.  **Protocol Robustness (`test_agent_robust.py`):** Stress tests the agent against simultaneous connections, large payloads, and malformed command arguments.
2.  **UI & Visual Integrity (`test_ui_integrity.py` / `test_visual_integrity.py`):** Playwright-driven browser tests that physically verify button colors (by hex value) and ensure no raw Django template tags leak into the UI.
3.  **Integration Core:** 22+ Django tests covering the asset discovery logic, storage health checks, and task queuing.

---

## 🚀 Getting Started

### 1. The Environment
Ensure you have a Redis broker running:
```bash
docker run --name redis -p 6379:6379 -d redis
```

### 2. Launching the Command Center
Execute the main orchestrator:
```powershell
.\talos.bat
```
This launches the **Daphne server**, starts the **Celery worker**, and opens the dashboard in your default browser.

### 3. Deploying Agents
Run the agent on any remote machine in the build fleet:
```powershell
python talos_agent/bin/agent_service.py
```

---

## 🛠 Operation Guide

1.  **Scanning:** Click **Scan Network** in the top right to discover new agents.
2.  **Drill-Down:** Click any agent card to enter its monitoring station.
3.  **Command:** Use the **Launch**, **Kill**, or **Update** buttons to control the remote environment.
4.  **Logging:** Click **Attach Logs** to stream the live `.log` output directly from the remote agent's disk to your dashboard.

---

## 🖋 Coding Standards: The Talos Way

*   **Google Style:** We strictly adhere to the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
*   **No Placeholders:** If it's in the code, it's functional.
*   **Single-Line Tags:** Django template tags are kept elegant and single-line to prevent rendering artifacts.
*   **Async First:** No blocking `time.sleep` calls in the UI thread—everything flows through Celery.

---
*Built for the future of game development by the Talos Engineering Team.*
