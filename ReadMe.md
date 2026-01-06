# ⚡ TALOS: Next-Gen UE5 Build Fleet Orchestrator

Talos is a premium, Django-based command center designed to manage, monitor, and orchestrate Unreal Engine 5 build pipelines across a distributed fleet of remote agents. It replaces legacy procedural scripts with a robust, asynchronous architecture and a high-fidelity dashboard.

---

## 💎 Core Philosophy: "Build with Confidence"

Talos isn't just a build runner—it's a mission control center. Every interaction is designed to be visceral and responsive, ensuring that developers can focus on building games while Talos handles the heavy lifting of distribution, execution, and observability.

### ✨ Key Features

#### 🚀 The Campaign Orchestrator
* **Mission Control:** A centralized "Launcher" interface to trigger complex build profiles (e.g., "Fast Validate", "Nightly Full").
* **Live Monitoring:** Real-time visualization of the build pipeline. Watch steps (Headless, Staging, UAT) progress with precise duration metrics.
* **Dual-Stream Logging:** Simultaneously captures the Command Line output and tails the internal UE5 log files (`HSHVacancy.log`) in real-time, streaming them to the browser without page reloads.
* **Run History:** Instant access to the results and artifacts of previous missions.

#### 📡 Sonar & Fleet Management
* **Auto-Discovery:** Automatically scans the subnet to identify and register Talos Remote Agents via custom handshake protocol.
* **Remote Control:** * **Launch:** Start UE5 instances remotely with optimized flags (`-AutoStart`, `-resX=1280`, etc.).
    * **Kill:** Graceful, multi-stage process termination across Windows machines.
    * **Log Attachment:** View live logs from any agent in the fleet via HTMX streaming.
* **Phoenix Update Protocol:** One-click "Push Update" securely transmits new code to remote agents, causing them to self-update and restart automatically using a detached batch process.

#### 🎨 Premium User Experience
* **Visual Integrity:** Dark-mode interface featuring **Inter** & **Outfit** typography, glassmorphism, and hardware-accelerated animations.
* **State Awareness:** Visual "Update Needed" badges pulse when a remote agent's code drifts from the server's version.
* **Responsive Feedback:** Buttons transform based on state (Stop vs Done), and UI elements poll intelligently to avoid "thrashing."

---

## 🏗 Architecture & Tech Stack

Talos is built for speed, stability, and maximum responsiveness:

* **Backend:** Django 6.x (running on **Daphne ASGI** for high-concurrency).
* **Task Queue:** **Celery 5.x** + **Redis** for true non-blocking execution and dynamic task chaining (Canvas).
* **Fleet Protocol:** Custom lightweight socket-based protocol (`v2.1.4`) for low-latency agent communication.
* **Frontend:** **HTMX** for high-interactivity with near-zero Javascript.
* **Database:** SQLite (Dev) / PostgreSQL (Prod) for persisting Pipeline Runs, Step Logs, and Agent Telemetry.

---

## 🧪 Extreme Verification (The Test Suite)

We don't trust—we verify. Talos maintains strict testing tiers:

1.  **Protocol Robustness (`test_agent_robust.py`):** Stress tests the agent against simultaneous connections, large payloads, and malformed command arguments.
2.  **UI & Visual Integrity:** Playwright-driven browser tests that physically verify button colors (by hex value), ensure no raw Django template tags leak into the UI, and validate the "Big Red Button" is actually red.
3.  **Integration Core:** Strict TDD approach for the Pipeline logic. Tests prove that "Fast Validate" triggers the correct sequence of Celery tasks before the code is even written.

---

## 🚀 Getting Started

### 1. The Environment
Ensure you have a Redis broker running:
```powershell
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

----
## 🛠 Operation Guide

1.  **Sonar Scan:** Click **Scan Network** in the top right to discover new agents.
2.  **Campaigns:** Select a profile (e.g., **🚀 Fast Validate**) to begin a build.
3.  **Monitoring:** Watch the live steps. Click any step row to expand the real-time logs.
4.  **Fleet Mgmt:** Drill down into specific agents to Launch/Kill processes or push code updates.

---

## 🖋 Coding Standards: The Talos Way

* **Google Style:** We strictly adhere to the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
* **No Placeholders:** If it's in the code, it's functional.
* **Single-Line Tags:** Django template tags are kept elegant and single-line to prevent rendering artifacts.
* **Async First:** No blocking `time.sleep` calls in the UI thread—everything flows through Celery.
* **Test Driven:** If you change logic and no test fails, you have violated the mission.
* **UI and Unit Tests:** Everything must be tested, including the UI. No implementations without matching tests.

**NOTE:** The token `&&` is not a valid statement separator in this version. One command per line here.

---
*Built for the future of game development by the Talos Engineering Team.*