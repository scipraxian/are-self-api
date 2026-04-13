# Architecture — The Brain of Are-Self

Are-Self is built as a brain. Not metaphorically — structurally. Each Django app is a brain region, and each region does
what its biological namesake actually does. This document is your map.

## Why a Brain?

Because brains are the best architecture for autonomous reasoning that we know of. The separation of concerns in a real
brain — memory formation separate from motor control separate from decision-making separate from sensory relay — maps
almost perfectly onto the engineering problems of an AI swarm manager.

It also makes the system teachable. When someone asks "where do memories live?", the answer is the same whether you're
talking about a brain or about Are-Self: the hippocampus.

## The Tick Cycle

Everything in Are-Self exists to support one loop: **the tick cycle**. This is one heartbeat of the system.

```
PNS (Celery Beat ticks)
  → Temporal Lobe (wakes the active iteration, picks the current shift)
    → CNS (fires a spike train through the neural pathway)
      → Spikes cascade through neurons
        → Frontal Lobe (starts a reasoning session)
          → The LLM reasons in a while-True loop
            → Parietal Lobe (executes tools)
            → Hippocampus (stores and retrieves memories)
            → Hypothalamus (selects the right model)
          → Session concludes or yields
        → Control returns up the spike chain
      → Next spike fires
    → Shift turn count increments
  → Next tick
```

```
celery beat schedule (periodic task)
  → temporal_lobe/temporal_lobe.py → trigger_temporal_metronomes()
    → fetch_canonical_temporal_pathway() → returns NeuralPathway
      → central_nervous_system/central_nervous_system.py → CNS builds SpikeTrain
        → neuromuscular_junction.py → fire_spike() (Celery task entry point)
          → _execute_spike() → dispatches to effector
            → frontal_lobe/ → ReasoningSession while-True loop
              → identity/identity_prompt.py → build_identity_prompt()
              → _build_turn_payload() → LLM call via LiteLLM
              → parietal_lobe/parietal_mcp/mcp_*.py → ParietalMCP gateway
              → hippocampus/hippocampus.py → Hippocampus.save_engram() / read_engram()
              → hypothalamus/ → model selection + budget gating
            → mcp_done() or mcp_respond_to_user(yield_turn=True)
          → spike.result_code set → synaptic_cleft/ → fire_neurotransmitter()
        → next spike in train fires
      → shift turn count increments
    → iteration advances or sleeps
  → next beat tick
```

The tick is a **Celery Beat schedule**. Every N seconds, the PNS fires. If there's an active iteration in the current
environment, the temporal lobe wakes it and the cascade begins. If nothing's active, the tick is a no-op.

## The Regions

### Identity (`identity/`)

The personnel department. An **Identity** is a blueprint for an AI persona — a system prompt template, a set of enabled
tools, addon phases that layer context during prompt assembly, and model routing preferences.

Identities don't do work directly. They get **forged** into **IdentityDiscs** — deployed instances with their own level,
XP, success/failure record, and memory. A single Identity blueprint can produce many Discs, each accumulating their own
experience. Think of it like a class and its instances.

The system prompt template supports Django template syntax. Variables like `{{identity_disc.name}}` and
XP, success/failure record, and memory. A single Identity blueprint can produce many Discs, each accumulating their own
experience. Think of it like a class and its instances.

The system prompt template supports Django template syntax. Variables like `{{identity_disc.name}}` and
`{{iteration.name}}` are rendered at runtime with the full ORM context.

IdentityDiscs are vector-embedded (768-dim, nomic-embed-text). The vector is auto-regenerated when the prompt, type,
tags, or addons change. This embedding is what the Hypothalamus uses for model matching.

### Temporal Lobe (`temporal_lobe/`)

The scheduler. Manages **Iterations** — work cycles divided into **Shifts**.

An **Iteration Definition** is a blueprint: a sequence of shift columns (Sifting → Pre-Planning → Planning → Executing →
Post-Execution → Sleeping), each with a turn limit. You drag IdentityDiscs into shift columns to assign participants.

**Incepting** a definition creates a live **Iteration** bound to an **Environment**. The iteration tracks which shift is
current and how many turns have been consumed. The temporal lobe advances through shifts as turn limits are reached.

Shifts correspond to project phases. During Sifting, the PM identity refines the backlog. During Executing, worker
identities tackle assigned stories. During Sleeping, identities review their memories and grow. The shift type
determines what the Identity is expected to do — enforced by the system prompt template, not by code.

### Central Nervous System (`central_nervous_system/`)

The execution engine. Everything that actually happens in Are-Self happens through spikes.

A **Neural Pathway** is a graph of **Neurons** connected by **Axons**. Each neuron has an **Effector** — either a native
Python handler or a Celery task. A **Spike Train** is a single traversal of a pathway. As the train moves through the
graph, it creates **Spikes** — one per neuron — which execute their effectors.

The CNS doesn't know about reasoning or AI. It's a generic directed-graph execution engine. The fact that one of its
effectors happens to start a reasoning session in the Frontal Lobe is just configuration. Other effectors launch
processes, push code, or call APIs.

Spikes carry **axoplasm** — a JSON dict that accumulates data as the train passes through neurons. Each effector can
read from and write to the axoplasm. This is how context flows through the execution graph without tight coupling
between neurons.

### Frontal Lobe (`frontal_lobe/`)

The thinker. Runs **Reasoning Sessions** — the actual LLM inference loop.

A session is a `while True` loop: assemble the prompt (identity + addons + history + terminal), call the LLM, parse tool
calls, dispatch to the Parietal Lobe, record the turn, repeat. The loop breaks when the LLM calls `mcp_done` (terminal)
or `mcp_respond_to_user` with `yield_turn=True` (pauses for human input).

Each iteration of the loop is a **Reasoning Turn** with full telemetry: token counts, inference time, model used, tool
calls made. The frontend can watch turns appear in real time via WebSocket.

Sessions have a **Focus** economy — a budget that decreases with each turn and tool call. When focus runs out, the
session must conclude. Novel memory formation grants focus back, incentivizing the LLM to learn.

### Parietal Lobe (`parietal_lobe/`)

The hands. Executes tools on behalf of the Frontal Lobe.

Tool definitions live in the database as `ToolDefinition` records with typed parameters. The **ParietalMCP** gateway
dynamically imports and calls the matching Python function from `parietal_mcp/mcp_*.py`. Each function receives
`session_id` and `turn_id` injected by the gateway.

The gateway includes **hallucination armor** — validation that the tool name exists, parameters match their types, and
required parameters are present. LLMs hallucinate tool calls; the Parietal Lobe catches them.

Key tools:

- `mcp_respond_to_user` — the universal communication tool. Has `thought`, `message_to_user`, `note_for_next_turn`, and
  `yield_turn`.
- `mcp_done` — files a conclusion and ends the session.
- `mcp_engram_save/read/search/update` — memory operations via the Hippocampus.

### Hippocampus (`hippocampus/`)

Long-term memory. Stores **Engrams** — vector-embedded facts extracted during reasoning.

Each engram has a name (a unique hash for dedup), a description (the actual fact), tags, a relevance score, and a
768-dimensional vector embedding. On save, the Hippocampus checks cosine similarity against existing engrams — if a new
memory is ≥90% similar to an existing one, the save is rejected with a message pointing to the duplicate. This prevents
the LLM from endlessly re-saving things it already knows.

Engrams are linked to sessions, turns, spikes, and IdentityDiscs. This provenance chain lets you trace any memory back
to exactly when and why it was formed.

The vector embedding auto-regenerates when an engram's description or tags change, using nomic-embed-text via Ollama.
Future sessions retrieve relevant engrams during the HISTORY addon phase by vector similarity search.

### Hypothalamus (`hypothalamus/`)

Model selection and routing. The Hypothalamus maintains a catalog of available models (synced from Ollama and
OpenRouter), their pricing, capabilities, and health status.

When the Frontal Lobe needs to make an LLM call, it asks the Hypothalamus to select a model. Selection uses
vector-similarity matching between the IdentityDisc's embedding and the model catalog embeddings, filtered by budget
constraints and circuit breaker status.

Circuit breakers track model failures with **scar tissue logic** — a model that fails gets a cooldown period that
increases with each subsequent failure. This prevents the system from hammering a broken endpoint.

Budget constraints are per-IdentityDisc and can be scoped to specific selection filters. The Hypothalamus enforces
per-token cost ceilings and per-period spend limits.

### Synaptic Cleft (`synaptic_cleft/`)

The real-time event bus. Built on Django Channels (WebSocket).

Events are typed as **neurotransmitters**, each carrying a specific kind of signal:

- **Dopamine** — success states (task completed, session concluded)
- **Cortisol** — errors and halts (spike failed, circuit breaker tripped)
- **Acetylcholine** — data sync (model refreshed, new turn recorded)
- **Glutamate** — streaming data (log lines, execution output)
- **Norepinephrine** — alertness/monitoring (worker heartbeats, orchestration narrative)

The frontend subscribes via `useDendrite(receptorClass, dendriteId)`. When a signal fires, the hook returns a new ref,
triggering a React effect that refetches data. No polling anywhere in the system.

### Prefrontal Cortex (`prefrontal_cortex/`)

Project management. Epics → Stories → Tasks, assigned to IdentityDiscs. The PFC is how work gets into the system — the
Frontal Lobe picks up tasks from the PFC backlog when a reasoning session starts.

### Peripheral Nervous System (`peripheral_nervous_system/`)

Fleet management and the heartbeat. The PNS monitors Celery workers via in-process signals (`task_prerun`,
`task_postrun`, `worker_ready`) that fire Norepinephrine through the Synaptic Cleft. The frontend shows worker cards
with real-time status.

Celery Beat is the PNS heartbeat — the metronome that drives the tick cycle.

### Thalamus (`thalamus/`)

The sensory relay. Translates between the internal reasoning format and the chat UI. The ThalamusChat bubble on every
page lets you talk to a standing session — inject messages, ask questions, get status. It's the human-facing surface of
the entire system.

### Environments (`environments/`)

Project context. An environment has a name and a set of context variables (key-value pairs). When the CNS resolves
executable paths, Django's template engine renders the variables: `{{project_root}}\build.bat` becomes a real path.

Only one environment is active at a time. Switching environments changes what every view shows — different iterations,
different pathways, different sessions.

## Data Flow Principles

- **The frontend adapts to the API, never the reverse.** If the UI needs data in a different shape, transform it in the
  frontend.
- **The URL is the single source of truth.** Every navigation action changes the URL. F5 returns exactly where you were.
- **No polling.** All real-time updates flow through the Synaptic Cleft via WebSocket. The frontend uses `useDendrite`
  hooks, never `setInterval`.
- **Spikes are the unit of work.** Everything that happens passes through the CNS as a spike. If you can't find it in
  the spike log, it didn't happen.
- **Engrams are the unit of memory.** Everything the system learns is an engram in the Hippocampus with full provenance.