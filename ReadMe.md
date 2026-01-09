# ⚡ TALOS: Next-Gen UE5 Build Fleet Orchestrator

Talos is a premium, Django-based command center designed to manage, monitor, and orchestrate Unreal Engine 5 build pipelines across a distributed fleet of remote agents. It replaces legacy procedural scripts with a robust, asynchronous architecture and a high-fidelity dashboard.

---

## 💎 Core Philosophy: "Build with Confidence"

Talos isn't just a build runner—it's a mission control center. Every interaction is designed to be visceral and responsive, ensuring that developers can focus on building games while Talos handles the heavy lifting of distribution, execution, and observability.

### ✨ Key Features

#### 🚀 The Hydra Orchestrator
* **Mission Control:** A centralized "Launch Protocol" interface to trigger complex build sequences (e.g., "Fast Validate", "Staging Build").
* **Embedded Monitoring:** Real-time visualization of the build pipeline directly on the dashboard. Watch steps progress with precise duration metrics and automatic state finalization.
* **Enhanced Log Viewer:** High-fidelity log streaming with "Smart Scroll" (Tail Follow), one-click **Copy to Clipboard**, and **Download as .log** functionality.
* **Recent Missions:** Instant dashboard visibility into the last 5 orchestration runs, with color-coded status indicators and deep-links to mission logs.

#### ⚡ Native Spell Architecture
* **Parallel Distributor:** High-performance fleet distribution using multi-threaded Robocopy synchronization.
* **Version Stamper:** Automated build metadata generation (Hex Hashes, Builder ID, Timestamps) that preserves static versioning.
* **Context-Aware:** All spells use the `HydraContext` for robust path resolution across different project environments.

#### 📡 Sonar & Fleet Management
* **Auto-Discovery:** Automatically scans the subnet to identify and register Talos Remote Agents via custom handshake protocol.
* **Remote Control:** 
    * **Launch:** Start UE5 instances remotely with optimized flags (`-AutoStart`, `-resX=1280`, etc.).
    * **Kill:** Graceful, multi-stage process termination across Windows machines.
    * **Log Attachment:** View live logs from any agent in the fleet via HTMX streaming.
* **Phoenix Update Protocol:** One-click "Push Update" securely transmits new code to remote agents, causing them to self-update and restart automatically.

#### 🎨 Premium User Experience
* **Visual Integrity:** Dark-mode interface featuring **Inter** & **Outfit** typography, glassmorphism, and hardware-accelerated animations.
* **State Awareness:** Visual "Update Needed" badges pulse when a remote agent's code drifts from the server's version.
* **Responsive Feedback:** Buttons transform based on state (Stop vs Done), and UI elements poll intelligently to avoid "thrashing."

---

## 🏗 Architecture & Tech Stack

Talos is built for speed, stability, and maximum responsiveness:

* **Backend:** Django 6.x (running on **Daphne ASGI** for high-concurrency).
* **Task Queue:** **Celery 5.x** + **Redis** for true non-blocking execution and dynamic task chaining.
* **Native Spells:** Python-native orchestration tasks (Distributor, Versioning) that execute within the worker context for maximum performance.
* **Fleet Protocol:** Custom lightweight socket-based protocol (`v2.1.4`) for low-latency agent communication.
* **Frontend:** **HTMX** for high-interactivity with near-zero Javascript.
* **Database:** SQLite (Dev) / PostgreSQL (Prod) for persisting Protocols, Missions, and Agent Telemetry.

---

## 🧪 Extreme Verification (The Test Suite)

We don't trust—we verify. Talos maintains strict testing tiers:

1.  **Protocol Robustness (`test_agent_robust.py`):** Stress tests the agent against simultaneous connections, large payloads, and malformed command arguments.
2.  **UI & Visual Integrity:** Playwright-driven browser tests that physically verify button colors, ensure responsive wrapping of log actions, and validate in-place monitor refreshes.
3.  **Integration Core:** Strict TDD approach for the Hydra state machine. Tests prove that mission finalization, outcome processing, and wave dispatching work before code is committed.

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

1.  **Sonar Scan:** Click **Scan Network** in the top right to discover and probe new agents.
2.  **Hydra Protocols:** Select a mission (e.g., **🚀 Fast Validate**) on the dashboard to begin.
3.  **Monitoring:** Watch the live mission progress in the embedded dashboard monitor. Click any protocol row to expand real-time log streams.
4.  **Audit History:** Scroll down to **Recent Missions** to review logs and result codes from past build sequences.
5.  **Fleet Mgmt:** Drill down into specific agents to Launch/Kill processes or push code updates via the Sonar grid.

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