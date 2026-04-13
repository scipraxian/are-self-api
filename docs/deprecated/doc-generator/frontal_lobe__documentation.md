# Frontal Lobe — Comprehensive Documentation

## Summary

The **frontal_lobe** module implements Talos's AI reasoning loop. It orchestrates `ReasoningSession` and `ReasoningTurn` records, assembles prompts from identity + addons + L1/L2 history cache, and drives the Parietal Lobe for tool execution. Session state includes a game-like focus/XP economy with level and efficiency bonuses.

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

## Target: frontal_lobe/

### Overview

**Purpose:** The frontal lobe is the reasoning engine that staffs identity-driven AI workers, gives them tools, and runs the turn loop. It builds prompts from system identity, recent history (L1/L2 cache), volatile addons, and sensory triggers.

**Connections in the wider system:**
- **central_nervous_system**: Invoked via `run_frontal_lobe` native handler
- **parietal_lobe**: Tool schemas, `chat()`, `process_tool_calls()`
- **identity**: `IdentityDisc`, addons, `build_identity_prompt`
- **hippocampus**: Catalog injection via Thalamus
- **temporal_lobe**: `IterationShiftParticipant` for session context

---

### Directory / Module Map

```
frontal_lobe/
├── __init__.py
├── admin.py
├── api.py, api_urls.py
├── constants.py
├── frontal_lobe.py      # FrontalLobe class, run(), turn loop
├── models.py           # ReasoningSession, ReasoningTurn, ChatMessage, ModelRegistry
├── synapse.py          # OllamaClient
├── synapse_open_router.py
├── thalamus.py         # relay_sensory_state (catalog injection)
├── serializers.py
├── urls.py, views.py
└── tests/
```

---

### Public Interfaces

| Interface | Type | Purpose |
|-----------|------|---------|
| `run_frontal_lobe(spike_id)` | Async function | Entry point for GenericEffectorCaster |
| `FrontalLobe` | Class | `run()`, `_execute_turn()`, `_build_turn_payload()` |
| `ReasoningSession` | Model | Session state, `current_level`, `max_focus`, `total_xp` |
| `ReasoningTurn` | Model | `apply_efficiency_bonus()`, `was_efficient_last_turn` |
| `relay_sensory_state(turn_record)` | Function | Injects engram catalog + instructions |

---

### Execution and Control Flow

1. **Entry:** `run_frontal_lobe(spike_id)` → `FrontalLobe(spike).run()`
2. **Init:** `resolve_environment_context` → objective, max_turns; create `ReasoningSession`
3. **Parietal:** `ParietalLobe.initialize_client(identity_disc)`, `build_tool_schemas()`
4. **Turn loop:** For each turn: `_record_turn_start` → `apply_efficiency_bonus` → `_inject_addons` → `_build_turn_payload` → `parietal_lobe.chat()` → `process_tool_calls`
5. **Exit:** Session status → COMPLETED, MAXED_OUT, or ERROR

---

### Data Flow

```
Spike → resolve_environment_context → objective, max_turns
    → ReasoningSession (identity_disc, participant, spike)
    → build_identity_prompt + collect_addon_blocks
    → ChatMessage (system, history L1/L2, volatile addons, sensory)
    → ParietalLobe.chat(messages, tools)
    → ToolCall → ParietalMCP.execute
    → Session: current_focus, total_xp updated
```

---

### Integration Points

| Consumer | Usage |
|----------|-------|
| `GenericEffectorCaster` | `run_frontal_lobe` native handler |
| `PrefrontalCortex` | Creates ReasoningSession, calls `FrontalLobe.run()` |
| `frontal_lobe.thalamus` | `relay_sensory_state` for sensory trigger |
| `identity` | `build_identity_prompt`, `collect_addon_blocks` |

---

### Configuration and Conventions

- **Default max_turns:** From `FrontalLobeConstants.DEFAULT_MAX_TURNS`
- **L1 cache:** Last 2 turns full; L2 eviction for older tool results
- **Session status:** PENDING, ACTIVE, PAUSED, COMPLETED, MAXED_OUT, ERROR, ATTENTION_REQUIRED, STOPPED

---

### Extension and Testing Guidance

**Extension points:**
- Add new addons via `identity.addons.addon_registry`
- Extend `relay_sensory_state` for new sensory content
- Adjust L1/L2 cutoff in `_build_history_messages`

**Tests:** `frontal_lobe/tests/`

---

## Mathematical Framing

### Session Level and Focus Cap

$$
\text{current\_level} = \lfloor \text{total\_xp} / 100 \rfloor + 1
$$

$$
\text{max\_focus} = 10 + \lfloor (\text{current\_level} - 1) \cdot 0.5 \rfloor
$$

### Turn Efficiency Rule

Let $t$ be the current turn and $t_{\text{last}}$ the previous turn. Define:
$$
\text{target\_capacity} = \text{current\_level} \cdot 1000
$$

$$
\text{was\_efficient} \Leftrightarrow \text{len}(\text{last\_turn.thought\_process}) \leq \text{target\_capacity}
$$

If efficient:
$$
\text{current\_focus} \leftarrow \min(\text{max\_focus}, \text{current\_focus} + 1)
$$
$$
\text{total\_xp} \leftarrow \text{total\_xp} + 5
$$

### Prompt Assembly Order

Messages for each turn (in order):
1. System: `build_identity_prompt(identity_disc, ...)`
2. History: L1 (turns $t-2$ to $t-1$) full; L2 (turns $t-6$ to $t-3$) truncated
3. Volatile: Addon blocks as user messages
4. Sensory: `relay_sensory_state(turn_record)` (engram catalog + instructions)

### L1/L2 Cache Model

- **L1:** Turns with $\text{age} \leq 2$; full tool results, full internal monologue
- **L2:** Turns with $2 < \text{age} \leq 5$; tool results evicted or truncated; internal monologue pruned to `[PRUNED TO SAVE TOKENS]`
- **Eviction:** Age $> 2$ → `[DATA EVICTED FROM L1 CACHE. REQUIRES ENGRAM RETRIEVAL.]`

### Invariants (from code)

1. **Identity required:** `identity_disc` and `ai_model` must be set before `run()`.
2. **Session linkage:** ReasoningSession links to `spike` and optionally `participant` (IterationShiftParticipant).

### Assumptions

- Prompt-window heuristic in synapse: `num_ctx = floor(payload_size / 3) + 2048` (not tokenizer-accurate).
