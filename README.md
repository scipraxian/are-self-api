# Are-Self

**Autonomous AI reasoning on hardware you already own.**

Are-Self lets small, free, local language models work together as a swarm — reasoning autonomously, using tools, forming
memories, and managing their own work. It runs on consumer hardware via Ollama, with cloud models as optional failover.

The architecture is modeled after the human brain. Each component maps to a real brain region and does what that region
actually does. This isn't a metaphor for marketing — it's a design principle that makes the system teachable,
debuggable, and honest about what each piece is responsible for.

## 📺 See It In Action

[![Are-Self — The Grid Is Free](https://img.youtube.com/vi/UUX-T2aTZlI/maxresdefault.jpg)](https://youtu.be/UUX-T2aTZlI)

**Full documentation, guides, and FAQ:** [are-self.com](https://are-self.com)

---

## Why This Exists

AI shouldn't require a credit card or a computer science degree. Are-Self is built so that a student with a laptop and
curiosity can run an AI reasoning swarm — for free, locally, privately. The models are free. The software is MIT
licensed. The hardware is whatever you have.

## What It Does

You create AI personas (**Identities**), give them tools and personality, deploy them into work cycles (**Iterations**),
assign them tasks, and let them reason autonomously. They select their own models, call tools, form memories, and learn
from experience. You watch it happen in real time.

The system compensates for small models' limitations — short context windows, poor instruction following — with
mechanical structure rather than raw capability. A 7B parameter model can do real work when the architecture handles the
hard parts.

## Quick Start

### Prerequisites

- **Python 3.12+**
- **Docker Desktop** (for PostgreSQL + Redis)
- **Node.js 20+** (for the frontend — see [are-self-ui](https://github.com/scipraxian/are-self-ui))

Ollama is installed automatically by the install script if not already present.

#### Installing Python

Python runs the entire Are-Self backend — the Django server, Celery workers, and all AI/ML integrations.

1. Go to [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. Download Python **3.12 or higher** (the big yellow button usually has the latest version — check that the number starts with 3.12 or above).
3. Run the installer:
   - **Windows:** Run the `.exe` file. **Important:** On the very first screen, check the box that says "Add python.exe to PATH" — this is easy to miss and things will break without it. Then click "Install Now".
   - **Mac:** Run the `.pkg` file and follow the prompts. Python will be installed to `/usr/local/bin`. If you have Homebrew, you can also run:
     ```bash
     brew install python@3.12
     ```
   - **Linux (Ubuntu/Debian):**
     ```bash
     sudo apt update
     sudo apt install python3.12 python3.12-venv python3-pip
     ```
     For other distros, see [https://www.python.org/downloads/](https://www.python.org/downloads/) or use your package manager.
4. Verify it works by opening a **new** terminal window and running:
   ```
   python --version
   ```
   You should see `Python 3.12.x` or higher. On Linux/Mac you may need to use `python3 --version` instead.

#### Installing Docker Desktop

Docker runs the PostgreSQL database and Redis message broker that Are-Self depends on.

1. Go to [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
2. Download the installer for your operating system:
   - **Windows:** Click "Download for Windows". Run the `.exe` installer and follow the prompts. You may need to enable WSL 2 when asked — the installer will guide you.
   - **Mac:** Click "Download for Mac". Choose **Apple chip** if you have an M1/M2/M3/M4 Mac, or **Intel chip** if you have an older Mac. Open the `.dmg` file and drag Docker to your Applications folder.
   - **Linux:** Follow the instructions for your distro at [https://docs.docker.com/desktop/install/linux/](https://docs.docker.com/desktop/install/linux/). For Ubuntu/Debian, there's a `.deb` package you can download and install directly.
3. Open Docker Desktop after installing. It needs to be running before you start Are-Self.
4. Verify it works by opening a terminal and running:
   ```
   docker --version
   ```
   You should see something like `Docker version 27.x.x`.

#### Installing Node.js

Node.js is needed for the React frontend ([are-self-ui](https://github.com/scipraxian/are-self-ui)).

1. Go to [https://nodejs.org](https://nodejs.org)
2. Download the **LTS** version (make sure it's 20 or higher — it will say the version number on the button).
3. Run the installer:
   - **Windows:** Run the `.msi` file. Click Next through the prompts. Make sure "Add to PATH" is checked (it is by default).
   - **Mac:** Run the `.pkg` file. Follow the prompts — it installs everything you need.
   - **Linux:** The easiest way is through NodeSource. Run these commands in your terminal:
     ```bash
     curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
     sudo apt-get install -y nodejs
     ```
     For other distros, see [https://nodejs.org/en/download/package-manager](https://nodejs.org/en/download/package-manager).
4. Verify it works by opening a **new** terminal window and running:
   ```
   node --version
   ```
   You should see `v20.x.x` or higher.

### First-Time Install (Windows)

```
git clone https://github.com/scipraxian/are-self.git
cd are-self
are-self-install.bat
```

This handles everything: creates a virtual environment, installs dependencies, starts Docker, enables pgvector,
runs migrations, loads fixture data, creates an admin superuser (`admin`/`admin`), installs Ollama if needed, and
pulls the embedding model.

### Launch

```
are-self.bat
```

Starts Docker, the Celery worker, the Django server, and the frontend dev server. Opens the browser automatically.

Open `http://localhost:5173`. You'll see a brain.

### Manual Setup (Non-Windows)

If you're not on Windows, the install script shows the exact sequence. The key steps:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
docker compose up -d
docker exec -it are_self_db psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
python manage.py migrate
python manage.py loaddata initial_data.json
ollama pull nomic-embed-text
python manage.py runserver
```

In separate terminals, start the Celery worker and frontend:

```bash
celery -A config worker -l info -E -P threads --concurrency=4
cd ../are-self-ui && npm install && npm run dev
```

## The Brain

Every part of Are-Self maps to a brain region. This is how you navigate the system.

| Region | Route | What It Does |
|---|---|---|
| **Identity** | `/identity` | Create AI personas with tools, personality, and budget |
| **Temporal Lobe** | `/temporal` | Set up work cycles with shifts and participants |
| **Prefrontal Cortex** | `/pfc` | Assign and manage tasks (epics, stories, tasks) |
| **Hypothalamus** | `/hypothalamus` | Model catalog, pricing, selection, circuit breakers |
| **Central Nervous System** | `/cns` | Execution engine — pathways, spike trains, neurons |
| **Frontal Lobe** | `/frontal` | Reasoning sessions — watch AI think in real time |
| **Hippocampus** | `/hippocampus` | Memory — vector-embedded facts that persist across sessions |
| **Parietal Lobe** | — | Tool execution gateway (no UI, runs server-side) |
| **Peripheral Nervous System** | `/pns` | Worker fleet monitoring |
| **Thalamus** | floating bubble | Chat interface — talk to the system from any page |

## The Lifecycle

1. **Create an Identity** — a persona with a system prompt, tools, and model preferences
2. **Configure models** — the Hypothalamus manages which LLMs are available and how much they cost
3. **Build an Iteration** — a work cycle with shifts (planning, executing, reviewing) and turn limits
4. **Forge Identities into Discs** — deploy personas into the iteration as working instances
5. **Assign tasks** — the Prefrontal Cortex manages the backlog
6. **Let it tick** — the PNS heartbeat triggers the cycle: temporal lobe wakes → CNS fires → frontal lobe reasons →
   tools execute → memories form
7. **Watch and interact** — monitor spike trains, read reasoning logs, inject messages into active sessions

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the brain regions connect.
See [GETTING_STARTED.md](GETTING_STARTED.md) for a hands-on walkthrough.
See [FEATURES.md](FEATURES.md) for a complete list of what's built.
See [TASKS.md](TASKS.md) for what's next.
See [are-self.com](https://are-self.com) for the full documentation site with guides, FAQ, and videos.

## Stack

- **Backend:** Django 6.x, Daphne (ASGI), Celery 5.x, Redis, PostgreSQL + pgvector
- **Frontend:** React, Vite, TypeScript ([separate repo](https://github.com/scipraxian/are-self-ui))
- **LLM Providers:** Ollama (local), OpenRouter (cloud failover), via LiteLLM
- **Embeddings:** nomic-embed-text (768-dim, runs locally via Ollama)
- **Real-time:** Django Channels (WebSocket) with typed neurotransmitter events

## Built With

Are-Self stands on the shoulders of these projects and communities:

| Project | Role in Are-Self |
|---|---|
| [Ollama](https://ollama.com) | Local model inference — the engine that makes "AI on your hardware" real |
| [LiteLLM](https://github.com/BerriAI/litellm) | Universal LLM routing — one interface for every model provider |
| [OpenRouter](https://openrouter.ai) | Cloud failover when local isn't enough |
| [Gemma](https://ai.google.dev/gemma) | Tool-calling workhorse from Google DeepMind |
| [Llama](https://llama.meta.com) | The model family that opened the floodgates |
| [Mistral](https://mistral.ai) | Efficient models that punch above their weight |
| [Qwen](https://github.com/QwenLM/Qwen) | Multilingual reasoning and strong tool use |
| [nomic-embed-text](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) | 768-dim embeddings powering the Hippocampus memory system |
| [Django](https://www.djangoproject.com) | Backend framework — the skeleton of the brain |
| [React](https://react.dev) | Frontend UI ([are-self-ui](https://github.com/scipraxian/are-self-ui)) |
| [Celery](https://docs.celeryq.dev) + [Redis](https://redis.io) | Task orchestration and message brokering |
| [PostgreSQL](https://www.postgresql.org) + [pgvector](https://github.com/pgvector/pgvector) | Relational storage + vector similarity search |

Full acknowledgments with details: [are-self.com/docs/acknowledgments](https://are-self.com/docs/acknowledgments)

## License

MIT. Free as in freedom, free as in beer.

## Contributing

Are-Self is built by [Michael](https://github.com/scipraxian) with the mission of making AI accessible to underserved
communities. Contributions welcome — especially from educators, students, and anyone who believes AI should be a public
good.

See [STYLE_GUIDE.md](STYLE_GUIDE.md) for coding standards.
