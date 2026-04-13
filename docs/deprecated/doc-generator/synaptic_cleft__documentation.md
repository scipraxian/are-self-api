# Synaptic Cleft — Comprehensive Documentation

## Summary

The **synaptic_cleft** module is the typed websocket event bus. It converts log chunks, status changes, and blackboard mutations into Channels group messages keyed by spike UUID. Event types form a discrete signal taxonomy: Glutamate (log), Dopamine/Cortisol (status), Acetylcholine (blackboard).

---

## Table of Contents

1. [Overview](#overview)
2. [Directory / Module Map](#directory--module-map)
3. [Public Interfaces](#public-interfaces)
4. [Execution and Control Flow](#execution-and-control-flow)
5. [Data Flow](#data-flow)
6. [Integration Points](#integration-points)
7. [Configuration and Conventions](#configuration-and-conventions)
8. [Extension and Testing Guidance](#extension-and-testing-guidance)
9. [Mathematical Framing](#mathematical-framing)

---

## Target: synaptic_cleft/

### Overview

**Purpose:** The synaptic cleft provides real-time push of execution state to the UI. Websocket clients subscribe to `spike_log_{spike_id}` and receive neurotransmitter events. Biologically themed: Glutamate (excitatory log), Dopamine (positive status), Cortisol (negative status), Acetylcholine (memory/blackboard).

**Connections in the wider system:**
- **GenericEffectorCaster**: Fires Glutamate (log), Dopamine/Cortisol (status), Acetylcholine (blackboard)
- **dashboard**: Websocket consumer subscribes to spike groups

---

### Directory / Module Map

```
synaptic_cleft/
├── __init__.py
├── admin.py
├── axons.py
├── axon_hillok.py       # fire_neurotransmitter
├── constants.py         # NeurotransmitterEvent, LogChannel
├── dendrites.py
├── models.py
├── neurotransmitters.py # Glutamate, Dopamine, Cortisol, Acetylcholine
├── views.py
└── tests.py
```

---

### Public Interfaces

| Interface | Type | Purpose |
|-----------|------|---------|
| `fire_neurotransmitter(transmitter)` | Async function | Sends to Channels group `spike_log_{spike_id}` |
| `Glutamate` | Pydantic model | event=LOG, channel, message |
| `Dopamine` | Pydantic model | event=STATUS, status_id (positive) |
| `Cortisol` | Pydantic model | event=STATUS, status_id (negative) |
| `Acetylcholine` | Pydantic model | event=BLACKBOARD, key, value |

---

### Execution and Control Flow

1. **Emit:** Caller constructs neurotransmitter, calls `fire_neurotransmitter(transmitter)`
2. **Route:** `group_name = f"spike_log_{transmitter.spike_id}"`
3. **Send:** `channel_layer.group_send(group_name, transmitter.to_synapse_dict())`
4. **Consume:** Websocket consumer receives `type=release_neurotransmitter`, `payload=...`

---

### Data Flow

```
GenericEffectorCaster / AsyncLogManager
    → Glutamate(spike_id, channel=EXECUTION|APPLICATION, message)
    → Dopamine(spike_id, status_id) | Cortisol(spike_id, status_id)
    → Acetylcholine(spike_id, key, value)
    → fire_neurotransmitter
    → Channels group_send
    → Websocket consumer
```

---

### Integration Points

| Consumer | Usage |
|----------|-------|
| `GenericEffectorCaster` | `_mirror_to_socket` (Glutamate), `_update_status` (Dopamine/Cortisol), blackboard update (Acetylcholine) |

---

### Configuration and Conventions

- **Group prefix:** `spike_log_`
- **Release method:** `release_neurotransmitter`
- **NeurotransmitterEvent:** LOG, STATUS, BLACKBOARD

---

### Extension and Testing Guidance

**Extension points:**
- Add new neurotransmitter subtypes (inherit Neurotransmitter, set event)
- Extend LogChannel for new log categories

**Tests:** `synaptic_cleft/tests.py`

---

## Mathematical Framing

### Event Type Taxonomy

Let $\mathcal{E}$ be the set of neurotransmitter event types:
$$
\mathcal{E} = \{\text{LOG}, \text{STATUS}, \text{BLACKBOARD}\}
$$

Mapping to neurotransmitter classes:
$$
\text{Glutamate} \mapsto \text{LOG}, \quad \text{Dopamine}, \text{Cortisol} \mapsto \text{STATUS}, \quad \text{Acetylcholine} \mapsto \text{BLACKBOARD}
$$

### Signal Space

Each neurotransmitter $n$ has:
- $\text{spike\_id} \in \text{UUID}$
- $\text{event} \in \mathcal{E}$
- $\text{timestamp} \in \text{datetime}$

Additional fields by type:
- Glutamate: $\text{channel} \in \{\text{execution}, \text{application}\}$, $\text{message} \in \text{str}$
- Dopamine/Cortisol: $\text{status\_id} \in \mathbb{Z}$
- Acetylcholine: $\text{key} \in \text{str}$, $\text{value} \in \text{Any}$

### Group Routing

$$
G(s) = \text{``spike\_log\_''} \oplus \text{str}(s)
$$

where $s$ = spike_id. All neurotransmitters for spike $s$ are sent to group $G(s)$.

### Invariants (from code)

1. **Strict typing:** All neurotransmitters inherit `Neurotransmitter` (Pydantic BaseModel).
2. **Channel layer required:** If no channel layer, neurotransmitter is dropped (logged).
