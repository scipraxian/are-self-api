# Are-Self API Reference

## Overview

Welcome to the Are-Self API—a neuro-mimetic orchestration framework that mirrors the structure and function of the human brain. Just as the brain organizes information and cognition across specialized regions, Are-Self organizes your AI execution engine around neural regions, each with distinct responsibilities.

Whether you're a seasoned developer, a neuroscience researcher, a computer science student, or someone curious about how artificial intelligence can be structured like a biological brain, this API provides the tools to orchestrate complex reasoning, manage AI identities, schedule iterations, and monitor system-wide health—all through a set of intuitive, brain-inspired endpoints.

**Base URL:** `http://localhost:8000`

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [System-Wide Statistics](#system-wide-statistics)
3. [Central Nervous System (Execution Engine)](#central-nervous-system-execution-engine)
4. [Frontal Lobe (Reasoning & Cognition)](#frontal-lobe-reasoning--cognition)
5. [Hippocampus (Memory & Engrams)](#hippocampus-memory--engrams)
6. [Hypothalamus (Model Selection & Routing)](#hypothalamus-model-selection--routing)
7. [Identity (Persona Management)](#identity-persona-management)
8. [Temporal Lobe (Scheduling & Iterations)](#temporal-lobe-scheduling--iterations)
9. [Prefrontal Cortex (Project Management)](#prefrontal-cortex-project-management)
10. [Parietal Lobe (Tools & Execution History)](#parietal-lobe-tools--execution-history)
11. [Peripheral Nervous System (Fleet Management)](#peripheral-nervous-system-fleet-management)
12. [Thalamus (Chat Relay)](#thalamus-chat-relay)
13. [Dashboard (System Monitoring)](#dashboard-system-monitoring)
14. [Environments (Execution Context)](#environments-execution-context)
15. [Common Patterns](#common-patterns)

---

## Quick Start

### Making Your First API Call

Here's the simplest way to get started with Are-Self. Let's fetch system-wide statistics:

```bash
curl -X GET http://localhost:8000/api/v2/stats/
```

**Response:**
```json
{
  "identity_disc_count": 5,
  "ai_model_count": 12,
  "reasoning_session_count": 42
}
```

### Launching a Spike Train

A **spike train** is a reasoning execution—the core unit of work in Are-Self. Here's how to launch one:

```bash
curl -X POST http://localhost:8000/api/v2/spiketrains/launch/ \
  -H "Content-Type: application/json" \
  -d '{
    "pathway_id": "my_neural_pathway",
    "identity_disc_id": "my_identity"
  }'
```

**Response (HTTP 201):**
```json
{
  "id": "spike_train_123",
  "status": "running",
  "created_at": "2026-04-04T12:00:00Z"
}
```

### Interacting with a Reasoning Session

If a reasoning session is waiting for human input (in "attention_required" state), inject a message:

```bash
curl -X POST http://localhost:8000/api/v2/thalamus/interact/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "That analysis looks good, proceed with the next step",
    "identity_disc_id": "my_identity"
  }'
```

**Response:**
```json
{
  "message": "Message received",
  "session_id": "reasoning_session_456",
  "turn_number": 3,
  "ok": true
}
```

---

## System-Wide Statistics

These endpoints provide real-time snapshots of Are-Self's overall state.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/stats/` | System statistics: count of identities, AI models, and active reasoning sessions |
| GET | `/api/v2/latest-spikes/` | Latest 10 spike trains (excluding Begin Play events) |
| GET | `/api/v2/latest-sessions/` | Latest 10 reasoning sessions across all identities |

---

## Central Nervous System (Execution Engine)

The Central Nervous System is the beating heart of Are-Self. It fires spike trains—discrete reasoning executions—through neural pathways (directed acyclic graphs of neurons and effectors). Think of it as your execution engine: spikes are the signals, neurons are the logic nodes, axons are the connections, and effectors are the actions.

### Spike Trains

Spike trains represent individual reasoning runs. Each spike train traverses a pathway, executing neurons and triggering effectors while maintaining state on shared cerebrospinal_fluid.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/spike_trains/` | List all spike trains |
| POST | `/api/v1/spike_trains/` | Create a new spike train (deprecated—use v2) |
| GET | `/api/v1/spike_trains/{id}/` | Retrieve a specific spike train |
| GET | `/api/v2/spiketrains/` | List spike trains (v2) |
| POST | `/api/v2/spiketrains/` | Create spike train (v2) |
| PATCH | `/api/v2/spiketrains/{id}/` | Update spike train metadata |
| DELETE | `/api/v2/spiketrains/{id}/` | Delete spike train |
| POST | `/api/v2/spiketrains/launch/` | **Launch a spike train (HTTP 201)** |
| POST | `/api/v2/spiketrains/{id}/stop/` | Graceful stop of a running spike train |
| POST | `/api/v2/spiketrains/{id}/terminate/` | Force terminate a spike train |

### Spikes (Individual Neural Firing Events)

Spikes are the individual firing events that occur during a spike train's execution. Each spike represents a neuron firing, an effector executing, or a state change.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/spikes/` | List spikes across all spike trains |
| GET | `/api/v1/spikes/{id}/` | Spike forensics: retrieve detailed execution trace |
| GET | `/api/v2/spikes/` | Read-only spike telemetry (includes application_log, execution_log, axoplasm) |

### Neural Pathways

Neural pathways are directed acyclic graphs (DAGs) that define the structure of execution. They're composed of neurons (nodes) connected by axons (edges), with effectors providing concrete actions.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/pathways/` | List all neural pathways |
| POST | `/api/v1/pathways/` | Create a new pathway |
| GET | `/api/v1/pathways/{id}/` | Retrieve pathway details |
| PATCH | `/api/v1/pathways/{id}/` | Update pathway |
| DELETE | `/api/v1/pathways/{id}/` | Delete pathway |
| POST | `/api/v1/pathways/{id}/toggle_favorite/` | Toggle pathway as favorite |
| GET | `/api/v1/pathways/{id}/layout/` | Flattened graph for canvas editor (node positions, connections) |
| GET | `/api/v1/pathways/{id}/library/` | Effector and sub-graph palette for this pathway |
| GET | `/api/v2/neuralpathways/` | List pathways (v2) |
| POST | `/api/v2/neuralpathways/` | Create pathway (v2) |
| PATCH | `/api/v2/neuralpathways/{id}/` | Update pathway (v2) |
| DELETE | `/api/v2/neuralpathways/{id}/` | Delete pathway (v2) |
| POST | `/api/v2/neuralpathways/{id}/toggle_favorite/` | Toggle favorite (v2) |
| POST | `/api/v2/neuralpathways/{id}/launch/` | Launch pathway as a spike train (HTTP 201) |
| GET | `/api/v2/pathways-3d/` | 3D visualization data for pathway graph |

### Neurons (Graph Nodes)

Neurons are the individual nodes in a neural pathway. They can be decision points, data transformers, or integration points with external systems.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/neurons/` | List neurons |
| POST | `/api/v1/neurons/` | Create neuron |
| GET | `/api/v1/neurons/{id}/` | Retrieve neuron details |
| PATCH | `/api/v1/neurons/{id}/` | Update neuron |
| DELETE | `/api/v1/neurons/{id}/` | Delete neuron |
| GET | `/api/v1/neurons/{id}/inspector_details/` | Resolved variable context matrix for a neuron |
| GET | `/api/v2/neurons/` | List neurons (v2) |
| POST | `/api/v2/neurons/` | Create neuron (v2) |
| PATCH | `/api/v2/neurons/{id}/` | Update neuron (v2) |
| DELETE | `/api/v2/neurons/{id}/` | Delete neuron (v2) |

### Axons (Graph Edges)

Axons are the connections between neurons. They define the flow of execution through a neural pathway.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/axons/` | Create an axon (connection) |
| DELETE | `/api/v1/axons/` | Delete an axon |
| GET | `/api/v2/axons/` | List axons (v2) |
| POST | `/api/v2/axons/` | Create axon (v2) |
| PATCH | `/api/v2/axons/{id}/` | Update axon (v2) |
| DELETE | `/api/v2/axons/{id}/` | Delete axon (v2) |

### Effectors (Action Definitions)

Effectors are concrete actions executed by neurons. They represent the actual work: API calls, database operations, tool invocations, or side effects.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/effectors/` | List effectors |
| POST | `/api/v1/effectors/` | Create effector |
| GET | `/api/v1/effectors/{id}/` | Retrieve effector |
| PATCH | `/api/v1/effectors/{id}/` | Update effector |
| DELETE | `/api/v1/effectors/{id}/` | Delete effector |
| GET | `/api/v2/effectors/` | Editor palette of available effectors (v2) |

### Node Contexts (Variable Overrides)

Node contexts allow you to set variable values at specific neurons, overriding defaults for that execution scope.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/node-contexts/` | List node contexts |
| POST | `/api/v1/node-contexts/` | Create node context |
| GET | `/api/v1/node-contexts/{id}/` | Retrieve node context |
| PATCH | `/api/v1/node-contexts/{id}/` | Update node context |
| DELETE | `/api/v1/node-contexts/{id}/` | Delete node context |

### Spike Logs & Forensics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/spike-logs/` | Merged forensic logs across all spikes |

---

## Frontal Lobe (Reasoning & Cognition)

The Frontal Lobe is where reasoning happens. It manages LLM reasoning sessions—extended conversations with AI models that can pause for human feedback, maintain memory across turns, and build complex conclusions through iterative thinking.

Reasoning sessions track every message, tool call, and decision point in a structured graph, making them fully auditable and resumable.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/reasoning_sessions/` | List reasoning sessions (lightweight response) |
| POST | `/api/v2/reasoning_sessions/` | Create a new reasoning session |
| GET | `/api/v2/reasoning_sessions/{id}/` | Retrieve full reasoning session details (heavy payload) |
| PATCH | `/api/v2/reasoning_sessions/{id}/` | Update reasoning session metadata |
| DELETE | `/api/v2/reasoning_sessions/{id}/` | Delete reasoning session |
| GET | `/api/v2/reasoning_sessions/{id}/graph_data/` | Complete graph with turns, engrams, and conclusion |
| POST | `/api/v2/reasoning_sessions/{id}/rerun/` | Restart the originating spike train |
| POST | `/api/v2/reasoning_sessions/{id}/attention_required/` | Gracefully pause session, signaling it needs human input |
| POST | `/api/v2/reasoning_sessions/{id}/resume/` | Inject a human message and wake the session |
| GET | `/api/v2/reasoning_sessions/{id}/messages/` | Flat chat pipeline suitable for UI rendering |
| GET | `/api/v2/reasoning_sessions/{id}/summary_dump/` | Forensic text dump of the entire session |
| GET | `/api/v2/reasoning_sessions/{id}/narrative_dump/` | Compact, human-readable briefing of reasoning |

### Reasoning Turns

A reasoning turn represents a single round of conversation—either an AI response or a human message.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/reasoning_turns/` | List reasoning turns |
| POST | `/api/v2/reasoning_turns/` | Create a new turn |
| GET | `/api/v2/reasoning_turns/{id}/` | Retrieve turn details (includes tool calls) |
| PATCH | `/api/v2/reasoning_turns/{id}/` | Update turn |
| DELETE | `/api/v2/reasoning_turns/{id}/` | Delete turn |

---

## Hippocampus (Memory & Engrams)

The Hippocampus stores long-term memory as vector-embedded engrams. Engrams are semantic snapshots of important information—reasoning conclusions, summaries, or key facts—that can be retrieved via vector similarity search to inform future reasoning sessions.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/engrams/` | List engrams (supports ?identity_discs={id} filter) |
| POST | `/api/v2/engrams/` | Create a new engram |
| GET | `/api/v2/engrams/{id}/` | Retrieve engram details |
| PATCH | `/api/v2/engrams/{id}/` | Update engram |
| DELETE | `/api/v2/engrams/{id}/` | Delete engram |

### Engram Tags

Tags provide semantic categorization for engrams, making them easier to organize and retrieve.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/engram_tags/` | List engram tags |
| POST | `/api/v2/engram_tags/` | Create tag |
| GET | `/api/v2/engram_tags/{id}/` | Retrieve tag |
| PATCH | `/api/v2/engram_tags/{id}/` | Update tag |
| DELETE | `/api/v2/engram_tags/{id}/` | Delete tag |

---

## Hypothalamus (Model Selection & Routing)

The Hypothalamus is the regulatory center for AI model selection, pricing, failover strategies, and usage tracking. It maintains a catalog of available AI models, tracks provider information, manages pricing tiers, and implements circuit breakers to handle model unavailability or cost overages.

Think of it as the "intelligent router" that decides which model to use for each reasoning session based on capability, availability, and cost.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/llm-providers/` | List LLM provider configurations |
| POST | `/api/v2/llm-providers/` | Create provider |
| PATCH | `/api/v2/llm-providers/{id}/` | Update provider |
| DELETE | `/api/v2/llm-providers/{id}/` | Delete provider |
| GET | `/api/v2/ai-models/` | List available AI models |
| POST | `/api/v2/ai-models/` | Create model |
| PATCH | `/api/v2/ai-models/{id}/` | Update model |
| DELETE | `/api/v2/ai-models/{id}/` | Delete model |
| GET | `/api/v2/model-categories/` | List model categories (e.g., "reasoning", "embedding") |
| POST | `/api/v2/model-categories/` | Create category |
| PATCH | `/api/v2/model-categories/{id}/` | Update category |
| DELETE | `/api/v2/model-categories/{id}/` | Delete category |
| GET | `/api/v2/model-modes/` | List model modes (e.g., "fast", "thorough") |
| POST | `/api/v2/model-modes/` | Create mode |
| PATCH | `/api/v2/model-modes/{id}/` | Update mode |
| DELETE | `/api/v2/model-modes/{id}/` | Delete mode |
| GET | `/api/v2/model-families/` | List model families (e.g., "Claude", "GPT") |
| POST | `/api/v2/model-families/` | Create family |
| PATCH | `/api/v2/model-families/{id}/` | Update family |
| DELETE | `/api/v2/model-families/{id}/` | Delete family |
| GET | `/api/v2/model-providers/` | List model provider associations |
| POST | `/api/v2/model-providers/` | Create association |
| PATCH | `/api/v2/model-providers/{id}/` | Update association |
| DELETE | `/api/v2/model-providers/{id}/` | Delete association |
| GET | `/api/v2/model-pricing/` | List pricing configurations |
| POST | `/api/v2/model-pricing/` | Create pricing |
| PATCH | `/api/v2/model-pricing/{id}/` | Update pricing |
| DELETE | `/api/v2/model-pricing/{id}/` | Delete pricing |
| GET | `/api/v2/usage-records/` | List usage records |
| POST | `/api/v2/usage-records/` | Create usage record |
| PATCH | `/api/v2/usage-records/{id}/` | Update usage record |
| DELETE | `/api/v2/usage-records/{id}/` | Delete usage record |
| GET | `/api/v2/sync-status/` | List sync status records |
| POST | `/api/v2/sync-status/` | Create sync status |
| PATCH | `/api/v2/sync-status/{id}/` | Update sync status |
| DELETE | `/api/v2/sync-status/{id}/` | Delete sync status |
| GET | `/api/v2/sync-logs/` | List sync logs |
| POST | `/api/v2/sync-logs/` | Create sync log |
| PATCH | `/api/v2/sync-logs/{id}/` | Update sync log |
| DELETE | `/api/v2/sync-logs/{id}/` | Delete sync log |
| GET | `/api/v2/model-ratings/` | List model performance ratings |
| POST | `/api/v2/model-ratings/` | Create rating |
| PATCH | `/api/v2/model-ratings/{id}/` | Update rating |
| DELETE | `/api/v2/model-ratings/{id}/` | Delete rating |
| GET | `/api/v2/failover-types/` | List failover strategy types |
| POST | `/api/v2/failover-types/` | Create failover type |
| PATCH | `/api/v2/failover-types/{id}/` | Update failover type |
| DELETE | `/api/v2/failover-types/{id}/` | Delete failover type |
| GET | `/api/v2/failover-strategies/` | List failover strategies |
| POST | `/api/v2/failover-strategies/` | Create failover strategy |
| PATCH | `/api/v2/failover-strategies/{id}/` | Update failover strategy |
| DELETE | `/api/v2/failover-strategies/{id}/` | Delete failover strategy |
| GET | `/api/v2/selection-filters/` | List model selection filters |
| POST | `/api/v2/selection-filters/` | Create filter |
| PATCH | `/api/v2/selection-filters/{id}/` | Update filter |
| DELETE | `/api/v2/selection-filters/{id}/` | Delete filter |
| GET | `/api/v2/model-descriptions/` | List model descriptions |
| POST | `/api/v2/model-descriptions/` | Create description |
| PATCH | `/api/v2/model-descriptions/{id}/` | Update description |
| DELETE | `/api/v2/model-descriptions/{id}/` | Delete description |
| GET | `/api/v2/model-tags/` | List model tags |
| POST | `/api/v2/model-tags/` | Create tag |
| PATCH | `/api/v2/model-tags/{id}/` | Update tag |
| DELETE | `/api/v2/model-tags/{id}/` | Delete tag |
| GET | `/api/v2/model-capabilities/` | List model capabilities |
| POST | `/api/v2/model-capabilities/` | Create capability |
| PATCH | `/api/v2/model-capabilities/{id}/` | Update capability |
| DELETE | `/api/v2/model-capabilities/{id}/` | Delete capability |
| GET | `/api/v2/model-roles/` | List model roles (e.g., "primary", "fallback") |
| POST | `/api/v2/model-roles/` | Create role |
| PATCH | `/api/v2/model-roles/{id}/` | Update role |
| DELETE | `/api/v2/model-roles/{id}/` | Delete role |

---

## Identity (Persona Management)

Identity manages AI personas—both base templates and leveled instances. An identity disc is a stateful instance of an AI personality with its own experience level (XP), configuration, and token budget. This allows you to nurture multiple distinct AI agents, each with its own learning trajectory and constraints.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/identities/` | List base identity templates |
| POST | `/api/v2/identities/` | Create identity template |
| GET | `/api/v2/identities/{id}/` | Retrieve identity template |
| PATCH | `/api/v2/identities/{id}/` | Update identity template |
| DELETE | `/api/v2/identities/{id}/` | Delete identity template |
| GET | `/api/v2/identity-discs/` | List identity disc instances (stateful, leveled) |
| POST | `/api/v2/identity-discs/` | Create identity disc instance |
| GET | `/api/v2/identity-discs/{id}/` | Retrieve identity disc with level and XP |
| PATCH | `/api/v2/identity-discs/{id}/` | Update identity disc |
| DELETE | `/api/v2/identity-discs/{id}/` | Delete identity disc |
| GET | `/api/v2/identity-discs/{id}/model-preview/` | Current model selection preview for this identity |

### Identity Addons & Extensions

Addons are plugins or extensions that modify identity behavior.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/identity_addons/` | List available addons |
| POST | `/api/v2/identity_addons/` | Create addon |
| GET | `/api/v2/identity_addons/{id}/` | Retrieve addon |
| PATCH | `/api/v2/identity_addons/{id}/` | Update addon |
| DELETE | `/api/v2/identity_addons/{id}/` | Delete addon |

### Identity Tags & Types

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/identity_tags/` | List identity tags |
| POST | `/api/v2/identity_tags/` | Create tag |
| GET | `/api/v2/identity_tags/{id}/` | Retrieve tag |
| PATCH | `/api/v2/identity_tags/{id}/` | Update tag |
| DELETE | `/api/v2/identity_tags/{id}/` | Delete tag |
| GET | `/api/v2/identity_types/` | List identity types |
| POST | `/api/v2/identity_types/` | Create type |
| GET | `/api/v2/identity_types/{id}/` | Retrieve type |
| PATCH | `/api/v2/identity_types/{id}/` | Update type |
| DELETE | `/api/v2/identity_types/{id}/` | Delete type |

### Identity Budgets

Token and cost budgets limit spending for identities.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/budget-periods/` | List budget period definitions (e.g., "monthly", "daily") |
| POST | `/api/v2/budget-periods/` | Create budget period |
| GET | `/api/v2/budget-periods/{id}/` | Retrieve budget period |
| PATCH | `/api/v2/budget-periods/{id}/` | Update budget period |
| DELETE | `/api/v2/budget-periods/{id}/` | Delete budget period |
| GET | `/api/v2/identity-budgets/` | List identity budgets |
| POST | `/api/v2/identity-budgets/` | Create budget |
| GET | `/api/v2/identity-budgets/{id}/` | Retrieve budget |
| PATCH | `/api/v2/identity-budgets/{id}/` | Update budget |
| DELETE | `/api/v2/identity-budgets/{id}/` | Delete budget |

---

## Temporal Lobe (Scheduling & Iterations)

The Temporal Lobe manages time-based execution. It handles iterations (runtime execution cycles) and shifts (time windows or phases within an iteration), allowing you to schedule complex, recurring workloads.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/temporal_lobe/graph_data/` | 3D visual graph of iteration and shift structure |

### Iterations

Iterations are execution cycles—discrete periods of work that can be repeated or scheduled.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/iterations/` | List iterations |
| POST | `/api/v2/iterations/` | Create iteration |
| GET | `/api/v2/iterations/{id}/` | Retrieve iteration |
| PATCH | `/api/v2/iterations/{id}/` | Update iteration |
| DELETE | `/api/v2/iterations/{id}/` | Delete iteration |

### Iteration Definitions & Shifts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/iteration-definitions/` | List iteration templates |
| POST | `/api/v2/iteration-definitions/` | Create iteration definition |
| GET | `/api/v2/iteration-definitions/{id}/` | Retrieve iteration definition |
| PATCH | `/api/v2/iteration-definitions/{id}/` | Update iteration definition |
| DELETE | `/api/v2/iteration-definitions/{id}/` | Delete iteration definition |
| GET | `/api/v2/iteration-shift-definitions/` | List shift definitions |
| POST | `/api/v2/iteration-shift-definitions/` | Create shift definition |
| GET | `/api/v2/iteration-shift-definitions/{id}/` | Retrieve shift definition |
| PATCH | `/api/v2/iteration-shift-definitions/{id}/` | Update shift definition |
| DELETE | `/api/v2/iteration-shift-definitions/{id}/` | Delete shift definition |
| GET | `/api/v2/shifts/` | List shift instances |
| POST | `/api/v2/shifts/` | Create shift |
| GET | `/api/v2/shifts/{id}/` | Retrieve shift |
| PATCH | `/api/v2/shifts/{id}/` | Update shift |
| DELETE | `/api/v2/shifts/{id}/` | Delete shift |

---

## Prefrontal Cortex (Project Management)

The Prefrontal Cortex is the planning center. It organizes work as a hierarchy: Epics → Stories → Tasks. Each level can have comments, status tracking, and full detail views, making it ideal for complex project orchestration.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/pfc-epics/` | List epics (lightweight) |
| POST | `/api/v2/pfc-epics/` | Create epic |
| GET | `/api/v2/pfc-epics/{id}/` | Retrieve epic (lightweight) |
| GET | `/api/v2/pfc-epics/{id}/full/` | Retrieve epic (full details) |
| GET | `/api/v2/pfc-epics/?full=true` | List epics with full details |
| PATCH | `/api/v2/pfc-epics/{id}/` | Update epic |
| DELETE | `/api/v2/pfc-epics/{id}/` | Delete epic |

### Stories

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/pfc-stories/` | List stories (lightweight) |
| POST | `/api/v2/pfc-stories/` | Create story |
| GET | `/api/v2/pfc-stories/{id}/` | Retrieve story (lightweight) |
| GET | `/api/v2/pfc-stories/{id}/full/` | Retrieve story (full details) |
| GET | `/api/v2/pfc-stories/?full=true` | List stories with full details |
| PATCH | `/api/v2/pfc-stories/{id}/` | Update story |
| DELETE | `/api/v2/pfc-stories/{id}/` | Delete story |

### Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/pfc-tasks/` | List tasks (lightweight) |
| POST | `/api/v2/pfc-tasks/` | Create task |
| GET | `/api/v2/pfc-tasks/{id}/` | Retrieve task (lightweight) |
| GET | `/api/v2/pfc-tasks/{id}/full/` | Retrieve task (full details) |
| GET | `/api/v2/pfc-tasks/?full=true` | List tasks with full details |
| PATCH | `/api/v2/pfc-tasks/{id}/` | Update task |
| DELETE | `/api/v2/pfc-tasks/{id}/` | Delete task |

### Comments

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/pfc-comments/` | List comments (lightweight) |
| POST | `/api/v2/pfc-comments/` | Create comment |
| GET | `/api/v2/pfc-comments/{id}/` | Retrieve comment (lightweight) |
| GET | `/api/v2/pfc-comments/{id}/full/` | Retrieve comment (full details) |
| GET | `/api/v2/pfc-comments/?full=true` | List comments with full details |
| PATCH | `/api/v2/pfc-comments/{id}/` | Update comment |
| DELETE | `/api/v2/pfc-comments/{id}/` | Delete comment |

### Status & Tags

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/pre-frontal-item-status/` | List item statuses (e.g., "open", "in progress", "closed") |
| POST | `/api/v2/pre-frontal-item-status/` | Create status |
| GET | `/api/v2/pre-frontal-item-status/{id}/` | Retrieve status |
| PATCH | `/api/v2/pre-frontal-item-status/{id}/` | Update status |
| DELETE | `/api/v2/pre-frontal-item-status/{id}/` | Delete status |
| GET | `/api/v2/pfc-tags/` | List PFC tags |
| POST | `/api/v2/pfc-tags/` | Create tag |
| GET | `/api/v2/pfc-tags/{id}/` | Retrieve tag |
| PATCH | `/api/v2/pfc-tags/{id}/` | Update tag |
| DELETE | `/api/v2/pfc-tags/{id}/` | Delete tag |

---

## Parietal Lobe (Tools & Execution History)

The Parietal Lobe manages tool definitions and their execution history. Tools are the concrete actions that neurons can invoke—API calls, system commands, external integrations, or custom workflows. This region tracks what tools are available, how they're parameterized, and how they've been invoked across all reasoning sessions.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/tool-definitions/` | List tool definitions |
| POST | `/api/v2/tool-definitions/` | Create tool definition |
| GET | `/api/v2/tool-definitions/{id}/` | Retrieve tool definition |
| PATCH | `/api/v2/tool-definitions/{id}/` | Update tool definition |
| DELETE | `/api/v2/tool-definitions/{id}/` | Delete tool definition |

### Tool Parameters

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/tool-parameters/` | List tool parameters |
| POST | `/api/v2/tool-parameters/` | Create parameter |
| GET | `/api/v2/tool-parameters/{id}/` | Retrieve parameter |
| PATCH | `/api/v2/tool-parameters/{id}/` | Update parameter |
| DELETE | `/api/v2/tool-parameters/{id}/` | Delete parameter |

### Parameter Types & Enums

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/tool-parameter-types/` | List parameter types (e.g., "string", "number", "boolean") |
| POST | `/api/v2/tool-parameter-types/` | Create parameter type |
| GET | `/api/v2/tool-parameter-types/{id}/` | Retrieve parameter type |
| PATCH | `/api/v2/tool-parameter-types/{id}/` | Update parameter type |
| DELETE | `/api/v2/tool-parameter-types/{id}/` | Delete parameter type |
| GET | `/api/v2/parameter-enums/` | List parameter enum values |
| POST | `/api/v2/parameter-enums/` | Create enum |
| GET | `/api/v2/parameter-enums/{id}/` | Retrieve enum |
| PATCH | `/api/v2/parameter-enums/{id}/` | Update enum |
| DELETE | `/api/v2/parameter-enums/{id}/` | Delete enum |

### Tool Use & Assignments

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/tool-use-types/` | List tool use types (e.g., "synchronous", "async") |
| POST | `/api/v2/tool-use-types/` | Create tool use type |
| GET | `/api/v2/tool-use-types/{id}/` | Retrieve tool use type |
| PATCH | `/api/v2/tool-use-types/{id}/` | Update tool use type |
| DELETE | `/api/v2/tool-use-types/{id}/` | Delete tool use type |
| GET | `/api/v2/tool-parameter-assignments/` | List parameter assignments to tools |
| POST | `/api/v2/tool-parameter-assignments/` | Create assignment |
| GET | `/api/v2/tool-parameter-assignments/{id}/` | Retrieve assignment |
| PATCH | `/api/v2/tool-parameter-assignments/{id}/` | Update assignment |
| DELETE | `/api/v2/tool-parameter-assignments/{id}/` | Delete assignment |

### Tool Calls (Execution History)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/tool-calls/` | List all tool call executions |
| POST | `/api/v2/tool-calls/` | Record tool call execution |
| GET | `/api/v2/tool-calls/{id}/` | Retrieve tool call record |
| PATCH | `/api/v2/tool-calls/{id}/` | Update tool call record |
| DELETE | `/api/v2/tool-calls/{id}/` | Delete tool call record |

---

## Peripheral Nervous System (Fleet Management)

The Peripheral Nervous System manages the distributed execution infrastructure—the worker nodes, compute hosts, and system control. It monitors health, tracks events, and manages the Celery task queue that powers async execution across Are-Self.

### Celery Beat & Worker Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/beat/` | Celery Beat scheduler status |
| POST | `/api/v2/beat/` | Control Celery Beat |
| POST | `/api/v2/beat/start/` | Start Celery Beat |
| POST | `/api/v2/beat/stop/` | Stop Celery Beat |
| POST | `/api/v2/beat/restart/` | Restart Celery Beat |
| GET | `/api/v2/celery-workers/` | List active Celery workers |

### System Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v2/system-control/shutdown/` | Graceful system shutdown |

### Nerve Terminal Management

Nerve terminals are the execution hosts—individual machines or containers that run spike trains and carry out work.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/nerve_terminal_statuses/` | List terminal status records |
| POST | `/api/v2/nerve_terminal_statuses/` | Create status record |
| GET | `/api/v2/nerve_terminal_statuses/{id}/` | Retrieve status record |
| PATCH | `/api/v2/nerve_terminal_statuses/{id}/` | Update status record |
| DELETE | `/api/v2/nerve_terminal_statuses/{id}/` | Delete status record |
| GET | `/api/v2/nerve_terminal_registry/` | List registered execution hosts |
| POST | `/api/v2/nerve_terminal_registry/` | Register host |
| GET | `/api/v2/nerve_terminal_registry/{id}/` | Retrieve host registration |
| PATCH | `/api/v2/nerve_terminal_registry/{id}/` | Update registration |
| DELETE | `/api/v2/nerve_terminal_registry/{id}/` | Unregister host |
| GET | `/api/v2/nerve_terminal_telemetry/` | List host metrics (CPU, memory, disk) |
| POST | `/api/v2/nerve_terminal_telemetry/` | Record metrics |
| GET | `/api/v2/nerve_terminal_telemetry/{id}/` | Retrieve metrics |
| PATCH | `/api/v2/nerve_terminal_telemetry/{id}/` | Update metrics |
| DELETE | `/api/v2/nerve_terminal_telemetry/{id}/` | Delete metrics |
| GET | `/api/v2/nerve_terminal_events/` | List host events (startup, shutdown, error) |
| POST | `/api/v2/nerve_terminal_events/` | Create event |
| GET | `/api/v2/nerve_terminal_events/{id}/` | Retrieve event |
| PATCH | `/api/v2/nerve_terminal_events/{id}/` | Update event |
| DELETE | `/api/v2/nerve_terminal_events/{id}/` | Delete event |

---

## Thalamus (Chat Relay)

The Thalamus is the gateway for human-AI interaction. It relays messages between humans and reasoning sessions, handling the complex task of injecting human input into an ongoing reasoning process without losing context or interrupting critical thinking.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v2/thalamus/interact/` | Inject message into a standing reasoning session |

**Request Format:**
```json
{
  "message": "Your message here",
  "identity_disc_id": "optional_identity_id"
}
```

**Response:**
```json
{
  "message": "Message received and processed",
  "session_id": "reasoning_session_123",
  "turn_number": 5,
  "ok": true
}
```

---

## Dashboard (System Monitoring)

The Dashboard provides real-time visibility into Are-Self's health and activity. It aggregates metrics from all brain regions and presents a holistic view of the system state.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/dashboard/summary/` | Real-time system summary (?static=true/false, ?last_sync=ISO8601) |

**Query Parameters:**
- `static`: Boolean. If true, return cached data; if false, compute fresh metrics.
- `last_sync`: ISO 8601 timestamp. Only return changes since this time.

---

## Environments (Execution Context)

Environments represent distinct execution contexts—development, staging, production, or custom sandboxes. Each environment can have its own configuration, variable overrides, and executable tooling.

### Environment Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/environments/` | List environments |
| POST | `/api/v2/environments/` | Create environment |
| GET | `/api/v2/environments/{id}/` | Retrieve environment |
| PATCH | `/api/v2/environments/{id}/` | Update environment |
| DELETE | `/api/v2/environments/{id}/` | Delete environment |
| POST | `/api/v2/environments/{id}/select/` | Set as active context |

### Environment Types & Statuses

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/environment-types/` | List environment types (e.g., "dev", "staging", "prod") |
| POST | `/api/v2/environment-types/` | Create type |
| GET | `/api/v2/environment-types/{id}/` | Retrieve type |
| PATCH | `/api/v2/environment-types/{id}/` | Update type |
| DELETE | `/api/v2/environment-types/{id}/` | Delete type |
| GET | `/api/v2/environment-statuses/` | List environment statuses (e.g., "healthy", "degraded") |
| POST | `/api/v2/environment-statuses/` | Create status |
| GET | `/api/v2/environment-statuses/{id}/` | Retrieve status |
| PATCH | `/api/v2/environment-statuses/{id}/` | Update status |
| DELETE | `/api/v2/environment-statuses/{id}/` | Delete status |

### Context Variables & Keys

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/context-variables/` | List context variables (?environment={id} to filter by environment) |
| POST | `/api/v2/context-variables/` | Create variable |
| GET | `/api/v2/context-variables/{id}/` | Retrieve variable |
| PATCH | `/api/v2/context-variables/{id}/` | Update variable |
| DELETE | `/api/v2/context-variables/{id}/` | Delete variable |
| GET | `/api/v2/context-keys/` | List variable key definitions |
| POST | `/api/v2/context-keys/` | Create key definition |
| GET | `/api/v2/context-keys/{id}/` | Retrieve key definition |
| PATCH | `/api/v2/context-keys/{id}/` | Update key definition |
| DELETE | `/api/v2/context-keys/{id}/` | Delete key definition |

### Executables

Executables define how tools and commands are run in an environment, including command-line switches and argument templates.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v2/executables/` | List tool executables for current environment |
| PATCH | `/api/v2/executables/` | Update executable configuration |

---

## Common Patterns

### Pagination

Most list endpoints support pagination to handle large result sets efficiently.

**Query Parameters:**
- `limit`: Number of records per page (default: 20, max: 100)
- `offset`: Number of records to skip (default: 0)

**Example:**
```bash
curl http://localhost:8000/api/v2/reasoning_sessions/?limit=50&offset=100
```

**Response:**
```json
{
  "count": 524,
  "next": "http://localhost:8000/api/v2/reasoning_sessions/?limit=50&offset=150",
  "previous": "http://localhost:8000/api/v2/reasoning_sessions/?limit=50&offset=50",
  "results": [
    { "id": "session_1", "status": "completed" },
    { "id": "session_2", "status": "running" }
  ]
}
```

### Filtering

List endpoints support filtering via query parameters. Common filters include:

- `?status={value}` — Filter by status (e.g., "running", "completed", "paused")
- `?identity_discs={id}` — Filter by identity disc
- `?environment={id}` — Filter by environment
- `?search={query}` — Full-text search on name/description

**Example:**
```bash
curl http://localhost:8000/api/v2/reasoning_sessions/?status=completed&identity_discs=my_identity
```

### Detail vs. Lightweight Responses

Some endpoints support both lightweight and detailed responses. Use the `?full=true` query parameter or append `/full/` to the path for complete data.

**Example (Lightweight):**
```bash
curl http://localhost:8000/api/v2/pfc-epics/epic_1/
```

**Example (Full Detail):**
```bash
curl http://localhost:8000/api/v2/pfc-epics/epic_1/full/
```

### WebSocket Events

Many long-running operations (spike trains, reasoning sessions) emit real-time events via WebSocket. Subscribe to monitor progress:

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v2/spike_train_events/');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Spike train event:', data);
};
```

**Common Event Types:**
- `spike_fired` — A neuron or effector executed
- `session_paused` — Reasoning session paused for human input
- `session_resumed` — Reasoning resumed after human input
- `spike_completed` — Spike train finished (success or failure)

### Error Handling

All endpoints follow standard HTTP status codes:

- **200 OK** — Request succeeded
- **201 Created** — Resource created (typically for POST/launch operations)
- **400 Bad Request** — Invalid parameters or malformed request
- **404 Not Found** — Resource does not exist
- **409 Conflict** — Operation conflicts with current state
- **500 Internal Server Error** — Server-side error

**Error Response Format:**
```json
{
  "error": "Invalid spike train ID",
  "details": "Spike train 'missing_id' does not exist",
  "code": "SPIKE_TRAIN_NOT_FOUND"
}
```

### Batch Operations

For bulk updates, POST to list endpoints with an array of objects:

```bash
curl -X POST http://localhost:8000/api/v2/neurons/ \
  -H "Content-Type: application/json" \
  -d '[
    { "pathway_id": "path_1", "type": "decision", "name": "Check Status" },
    { "pathway_id": "path_1", "type": "effector", "name": "Send Alert" }
  ]'
```

### State Transitions

Certain resources have state machines. Examples:

- **Spike Train States:** pending → running → completed/failed/stopped
- **Reasoning Session States:** active → attention_required → running → completed
- **Task States:** open → in_progress → closed

State transitions are typically enforced via specific endpoints (e.g., POST `/api/v2/reasoning_sessions/{id}/attention_required/`).

---

## Next Steps

- **Getting Started:** Review the [Quick Start](#quick-start) section to make your first API call.
- **Integration:** Build a client library in your language of choice using the endpoint patterns above.
- **Monitoring:** Set up webhooks or WebSocket connections to monitor system state in real-time.
- **Advanced Patterns:** Combine spike trains with reasoning sessions and identity discs to build complex, multi-agent workflows.

For questions or contributions, refer to the Are-Self GitHub repository or community forums.

---

**Are-Self API Reference** | Version 2.0 | Last Updated: April 4, 2026
