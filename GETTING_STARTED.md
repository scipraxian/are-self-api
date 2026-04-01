# Getting Started — Your First Hour with Are-Self

This guide walks you through the full lifecycle: from an empty system to an autonomous AI reasoning session. By the end,
you'll have an AI persona thinking, using tools, and forming memories on your own hardware.

## Before You Start

Make sure the backend and frontend are running (see [README.md](README.md)). You should be able to open
`http://localhost:5173` and see the 3D brain landing page.

You'll also need at least one model running in Ollama:

```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

The first is for reasoning. The second is for memory embeddings — it runs automatically, you don't interact with it
directly.

## Step 1: Create an Environment

Navigate to `/environments` (or click Environments in the hamburger menu).

An environment is your project context. Click **Create**, give it a name like "My First Project", and add a context
variable:

- Key: `project_root`
- Value: the path to whatever project you want the AI to work on (e.g., `C:\my-project` or `/home/me/my-project`)

Click **Set as Active**. The environment name should appear in the NavBar. Everything you do from now on happens inside
this environment.

## Step 2: Create an Identity

Navigate to `/identity`.

An Identity is a persona blueprint — who the AI will be. Click **Create Identity**, give it a name like "Junior
Developer", and select a type (Worker or PM).

Click the new identity to open the detail editor. Switch to **Edit Mode** and configure:

- **System prompt** — This is the core instruction set. Something like: *"You are a junior developer. You write clean
  code, ask clarifying questions, and document your work. You save important discoveries as engrams."*
- **Enabled tools** — Toggle on the tools this persona should have access to. At minimum, enable `mcp_respond_to_user`
  and `mcp_done`.
- **Neural addons** — Toggle on IDENTIFY (identity context), CONTEXT (telemetry), HISTORY (memory retrieval), and
  TERMINAL (action prompt).

Click **Save Loadout**.

## Step 3: Set Up an Iteration

Navigate to `/temporal`.

You'll see two sections in the left sidebar: **Definitions** (blueprints) and **Iterations** (live runs).

### Create a definition

Click **New Definition**. It comes pre-populated with 6 shift columns: Sifting, Pre-Planning, Planning, Executing,
Post-Execution, and Sleeping. Each has a default turn limit.

The **Identity Roster** panel on the right shows your available identities and discs. Drag your "Junior Developer"
identity into the **Executing** shift column. Since it's a base identity (not yet a disc), the system automatically *
*forges** it — creating a deployed IdentityDisc with its own level, XP, and memory.

Adjust turn limits if you want. The default of 1 turn per shift is fine for a first run — it means each participant gets
one reasoning session per shift.

### Incept an iteration

Select your environment in the definition header dropdown, then click **Incept**. This creates a live iteration from the
blueprint. You should see it appear in the Iterations list on the left.

## Step 4: Create a Task

Navigate to `/pfc`.

The Prefrontal Cortex is the task manager. Click **+ Epic** to create an epic (e.g., "Explore the Project"), then drill
in and create a story, then a task. Assign the task to your IdentityDisc using the assignee field.

Keep it simple for the first run: *"Read the README and summarize what this project does."*

## Step 5: Initiate

Go back to `/temporal`. Select your iteration from the left sidebar. Click **Initiate**.

The iteration status changes to **Running**. The next time the PNS ticks (Celery Beat), the temporal lobe will wake this
iteration and fire a spike train through the CNS.

If you don't want to wait for the automatic tick, you can trigger one manually from the Temporal Lobe's deprecated API (
this will be replaced with a UI button soon):

```bash
curl -X POST http://localhost:8000/api/v2/temporal_lobe/trigger_tick/
```

## Step 6: Watch It Think

### CNS — The execution path

Navigate to `/cns`. You'll see pathway cards with sparkline activity charts. Click the active pathway to see its spike
trains. Click a spike train to see the live execution graph — spikes lighting up as they fire through neurons.

Click any spike to open **dual-terminal forensics** — the raw execution log and application log side by side in terminal
emulators.

### Frontal Lobe — The reasoning session

Navigate to `/frontal`. You'll see your reasoning session appear. Click it to open the 3D force graph showing reasoning
turns as connected nodes — or toggle to Chat mode to see the conversation as it unfolds.

In Chat mode, you can **inject messages** into the active session. Type something and it gets queued in the
`swarm_message_queue` — the LLM will see it on its next turn. This works even while the session is actively reasoning.

### Hippocampus — Memories forming

If your identity has the Hippocampus tools enabled, it will save engrams as it discovers things. Navigate to
`/hippocampus` to see memories appear in real time. Each engram shows its provenance — which session created it, which
turn, which spike.

## Step 7: Iterate

The first run is always rough. The LLM might not use tools correctly, might save bad memories, might go in circles.
That's expected — especially with small local models.

Here's how to improve:

- **Refine the system prompt.** Be specific about what you want the identity to do and not do. The prompt template
  supports Django variables: `{{identity_disc.name}}`, `{{iteration.name}}`, `{{turn_number}}`.
- **Adjust tool access.** If the LLM is misusing a tool, disable it. If it needs a capability, enable it.
- **Curate memories.** Go to the identity's Memories tab. Deactivate bad engrams, edit descriptions, adjust relevance
  scores. The LLM retrieves memories by vector similarity — clean memories mean better retrieval.
- **Add more identities.** A PM identity in the Sifting shift can prioritize work. A reviewer in Post-Execution can
  check quality. Each identity has its own perspective and tools.

## What Next

- Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand how all the brain regions connect
- Explore the CNS spike forensics to understand exactly what happens during execution
- Try running multiple identities in the same iteration — this is where swarm behavior emerges
- Connect to OpenRouter for cloud model failover when local models can't handle a task

## Troubleshooting

**Nothing happens after Initiate:**

- Check that Celery Beat is running (`celery -A talos beat -l info`)
- Check that at least one Celery worker is running (`celery -A talos worker -l info -E`)
- Check the PNS page (`/pns`) — you should see worker cards with heartbeats

**Reasoning session starts but fails immediately:**

- Check that Ollama is running and the model is pulled (`ollama list`)
- Check the Hypothalamus model catalog — the model needs to be synced
- Check the spike forensics (`/cns/spike/{id}`) for the actual error

**Memories aren't forming:**

- Make sure `mcp_engram_save` is in the identity's enabled tools
- Make sure the HISTORY addon is enabled — this injects existing memories into the prompt
- Check that `nomic-embed-text` is available in Ollama (`ollama list`)

**The UI shows stale data:**

- Check the browser console for WebSocket connection errors
- Make sure Daphne is running (not `runserver` — Daphne handles WebSocket)
- Refresh the page — if data appears, the WebSocket connection dropped