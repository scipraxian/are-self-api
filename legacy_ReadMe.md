# ⚡ TALOS: Next-Gen UE5 Build Fleet Orchestrator

Talos is a premium, Django-based command center designed to manage, monitor, and orchestrate Unreal Engine 5 build
pipelines across a distributed fleet of remote agents. It replaces legacy procedural scripts with a robust, asynchronous
architecture and a high-fidelity dashboard.

---

## 💎 Core Philosophy: "Build with Confidence"

Talos isn't just a build runner—it's a mission control center. Every interaction is designed to be visceral and
responsive, ensuring that developers can focus on building games while Talos handles the heavy lifting of distribution,
execution, and observability.

### ✨ Key Features

#### 🚀 The Central Nervous System (CNS)

* **Mission Control:** A centralized "Launch Protocol" interface to trigger complex build sequences (e.g., "Fast
  Validate", "Staging Build").
* **Embedded Monitoring:** Real-time visualization of the build pipeline directly on the dashboard. Watch steps progress
  with precise duration metrics and automatic state finalization.
* **Enhanced Log Viewer:** High-fidelity log streaming with "Smart Scroll" (Tail Follow), one-click **Copy to Clipboard
  **, and **Download as .log** functionality.
* **Recent Missions:** Instant dashboard visibility into the last 5 orchestration runs, with color-coded status
  indicators and deep-links to mission logs.

#### ⚡ Native Effector Architecture

* **Parallel Distributor:** High-performance fleet distribution using multi-threaded Robocopy synchronization.
* **Version Stamper:** Automated build metadata generation (Hex Hashes, Builder ID, Timestamps) that preserves static
  versioning.
* **Context-Aware:** All effectors use the `EffectorContext` for robust path resolution across different project
  environments.

#### 📡 Sonar & Fleet Management

* **Auto-Discovery:** Automatically scans the subnet to identify and register Talos Remote Agents via custom handshake
  protocol.
* **Remote Control:**
    * **Launch:** Start UE5 instances remotely with optimized flags (`-AutoStart`, `-resX=1280`, etc.).
    * **Kill:** Graceful, multi-stage process termination across Windows machines.
    * **Log Attachment:** View live logs from any agent in the fleet via HTMX streaming.
* **Phoenix Update Protocol:** One-click "Push Update" securely transmits new code to remote agents, causing them to
  self-update and restart automatically.

#### 🎨 Premium User Experience

* **Visual Integrity:** Dark-mode interface featuring **Inter** & **Outfit** typography, glassmorphism, and
  hardware-accelerated animations.
* **State Awareness:** Visual "Update Needed" badges pulse when a remote agent's code drifts from the server's version.
* **Responsive Feedback:** Buttons transform based on state (Stop vs Done), and UI elements poll intelligently to
  avoid "thrashing."

---

## 🏗 Architecture & Tech Stack

Talos is built for speed, stability, and maximum responsiveness:

* **Backend:** Django 6.x (running on **Daphne ASGI** for high-concurrency).
* **Task Queue:** **Celery 5.x** + **Redis** for true non-blocking execution and dynamic task chaining.
* **Native Spells:** Python-native orchestration tasks (Distributor, Versioning) that execute within the worker context
  for maximum performance.
* **Fleet Protocol:** Custom lightweight socket-based protocol (`v2.1.4`) for low-latency agent communication.
* **Frontend:** **HTMX** for high-interactivity with near-zero Javascript.
* **Databases:** PostgreSQL and Redis for persisting Protocols, Missions, and Agent Telemetry.

---

## 🧪 Extreme Verification (The Test Suite)

We don't trust—we verify. Talos maintains strict testing tiers:

1. **Protocol Robustness (`test_agent_robust.py`):** Stress tests the agent against simultaneous connections, large
   payloads, and malformed command arguments.
2. **UI & Visual Integrity:** Playwright-driven browser tests that physically verify button colors, ensure responsive
   wrapping of log actions, and validate in-place monitor refreshes.
3. **Integration Core:** Strict TDD approach for the CNS state machine. Tests prove that mission finalization, outcome
   processing, and wave dispatching work before code is committed.

---

## 🚀 Quick Start: Zero to Transmission

### 1. Infrastructure (The Grid)

Talos requires a robust backend to handle asynchronous orchestration. The fastest way to provision the environment is
using **Docker Compose**.

```powershell
# 1. Ignite the Services (PostgreSQL & Redis)
docker compose up -d

# 2. Enable Vector Memory (Required for Hippocampus)
docker exec -it talos_db psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 3. Pull Ollama Models (Reasoning & Embeddings)
# Ensure Ollama is running before executing at least the following:
ollama pull qwen2.5-coder:32b
ollama pull nomic-embed-text
```

#### Manual Configuration (Alternative)

Ensure you have the following services **online**:

* **PostgreSQL**: The persistent memory. Talos enables connection pooling by default.
    * *Default Config:* User: `postgres`, Password: `frith` (See `config/settings.py`).
    * *Requirement:* Must have the `pgvector` extension installed and enabled (`CREATE EXTENSION vector;`).
* **Redis**: The nervous system. Handles Celery task queues and channel layers.
    * *Default Port:* `6379`.

### 2. Environment Initialization

Talos operates in a strict environment. Initialize your virtual environment and dependencies:

```powershell
# 1. Forge the Virtual Environment
python -m venv venv

# 2. Activate (Windows)
.\venv\Scripts\activate

# 3. Equip Fleet Dependencies
pip install -r requirements.txt
```

### 3. Database Genesis & The `talos_bin` Pattern

Talos doesn't just migrate; it *seeds* complex execution graphs. We explicitly use the **`C:\talos_bin`** directory
pattern for all build artifacts, staging areas, and shader caches.

* *See `initial_data.json` fixtures for the exact mapping of `talos_bin` paths to Talos Executables.*

```powershell
# 1. Apply Schema
python manage.py migrate

# 2. Seed CNS Neural Pathways (Loads initial_data.json)
python manage.py seed_talos
```

### 4. Create Poweruser (Fast Track)

To quickly provision a superuser that matches the standard Talos environment variables (bypassing the interactive
prompt):

```powershell
# Set Environment Variables for Auto-Creation
$env:DJANGO_SUPERUSER_USERNAME="admin"
$env:DJANGO_SUPERUSER_EMAIL="admin@talos.dev"
$env:DJANGO_SUPERUSER_PASSWORD="admin"

# Execute Creation
python manage.py createsuperuser --noinput
```

### 5. Launch Mission Control

Execute the primary startup script to spin up the **Daphne ASGI Server** and **Celery Worker**:

```powershell
.\talos.bat
```

> **Pro Tip:** The dashboard will launch at `http://127.0.0.1:8000`. Use your Poweruser credentials to access the Admin
> panel if needed (`/admin`), though the main dashboard is open for monitoring.

---

## 🖥️ The Dashboard: Visceral Control

The Talos Dashboard is designed to be **visually stunning** and **highly responsive**. It is not just a list of tables;
it is a living view of your fleet.

* **Real-Time Telemetry:** The interface uses HTMX to poll for state changes without full page reloads, ensuring a "
  glitch-free" experience.
* **Mission Control:** Initiate **Neural Pathways** (Build, Cook, Deploy) directly from the command center.
* **Log Streaming:** Watch logs flow in real-time with our "Matrix-style" dark mode viewer, complete with auto-scroll
  and ANSI color parsing.

---

## 🛠 Operation Guide

2. **Neural Pathways:** Select a mission (e.g., **🚀 Fast Validate**) on the dashboard to begin.
3. **Monitoring:** Watch the live mission progress in the embedded dashboard monitor. Click any protocol row to expand
   real-time log streams.
4. **Audit History:** Scroll down to **Recent Missions** to review logs and result codes from past build sequences.
5. **Fleet Mgmt:** Drill down into specific agents to Launch/Kill processes or push code updates via the Sonar grid.

---

## 🖋 Coding Standards: The Talos Way

* **Google Style:** We strictly adhere to
  the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
* **No Placeholders:** If it's in the code, it's functional.
* **Single-Line Tags:** Django template tags are kept elegant and single-line to prevent rendering artifacts.
* **Async First:** No blocking `time.sleep` calls in the UI thread—everything flows through Celery.
* **Test Driven:** If you change logic and no test fails, you have violated the mission.
* **UI and Unit Tests:** Everything must be tested, including the UI. No implementations without matching tests.

**NOTE:** The token `&&` is not a valid statement separator in this version. One command per line here.

---

*Built for the future of game development by the Talos Engineering Team.*
