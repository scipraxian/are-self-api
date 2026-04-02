# Are-Self

**Autonomous AI reasoning on hardware you already own.**

Are-Self lets small, free, local language models work together as a swarm — reasoning autonomously, using tools, forming
memories, and managing their own work. It runs on consumer hardware via Ollama, with cloud models as optional failover.

The architecture is modeled after the human brain. Each component maps to a real brain region and does what that region
actually does. This isn't a metaphor for marketing — it's a design principle that makes the system teachable,
debuggable, and honest about what each piece is responsible for.

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

- Python 3.12+
- Docker Desktop (for PostgreSQL + Redis)
- Node.js 20+ (for the frontend — see [are-self-ui](https://github.com/scipraxian/are-self-ui))

Ollama is installed automatically by the install script if not already present.

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

## Stack

- **Backend:** Django 6.x, Daphne (ASGI), Celery 5.x, Redis, PostgreSQL + pgvector
- **Frontend:** React, Vite, TypeScript ([separate repo](https://github.com/scipraxian/are-self-ui))
- **LLM Providers:** Ollama (local), OpenRouter (cloud failover), via LiteLLM
- **Embeddings:** nomic-embed-text (768-dim, runs locally via Ollama)
- **Real-time:** Django Channels (WebSocket) with typed neurotransmitter events

## License

MIT. Free as in freedom, free as in beer.

## Contributing

Are-Self is built by [Michael](https://github.com/scipraxian) with the mission of making AI accessible to underserved
communities. Contributions welcome — especially from educators, students, and anyone who believes AI should be a public
good.

See [STYLE_GUIDE.md](STYLE_GUIDE.md) for coding standards.
