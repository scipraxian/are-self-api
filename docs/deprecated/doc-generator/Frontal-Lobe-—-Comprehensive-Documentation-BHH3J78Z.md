---
tags: []
parent: 'Talos Detailed Codebase Notes'
collections:
    - Architecture
$version: 3179
$libraryID: 1
$itemKey: BHH3J78Z

---
# Frontal Lobe — Comprehensive Documentation

## Summary

The **frontal\_lobe** module is the reasoning engine that staffs identity-driven AI workers, gives them tools, and runs the turn loop. Each turn assembles LLM messages via ordered identity addons and routes inference through the hypothalamus hot-swap loop. Session state includes a game-like focus/XP economy with level and efficiency bonuses.

***

## Table of Contents

1.  [Overview](#overview)
2.  [Directory / Module Map](#directory--module-map)
3.  [Public Interfaces](#public-interfaces)
4.  [Execution and Control Flow](#execution-and-control-flow)
5.  [Data Flow](#data-flow)
6.  [Integration Points](#integration-points)
7.  [Configuration and Conventions](#configuration-and-conventions)
8.  [Extension and Testing Guidance](#extension-and-testing-guidance)
9.  [Visualizations](#visualizations)
10. [Mathematical Framing](#mathematical-framing)

***

## Target: frontal\_lobe/

### Overview

**Purpose:** The frontal lobe is the reasoning engine that staffs identity-driven AI workers, gives them tools, and runs the turn loop. Each turn’s LLM messages are assembled in `_build_turn_payload`: identity **addons** (ordered by `IdentityAddonPhase`) produce `ChatMessage` rows—typically `identity_info_addon` (system prompt via `build_identity_prompt`), `normal_chat_addon` (non-volatile history), **CONTEXT** addons such as `hippocampus_addon`, and `focus_addon` (applies `ReasoningTurn.apply_efficiency_bonus()` then injects focus stats). Messages are serialized with `chat_message_to_llm_dict`, which applies tool-argument pruning by age vs `ToolParameter.prune_after_turns`.

**Connections in the wider system:**

*   **central\_nervous\_system**: Invoked via `run_frontal_lobe` native handler

*   **parietal\_lobe**: Tool schemas, `chat()`, `process_tool_calls()`

*   **identity**: `IdentityDisc`, `ADDON_REGISTRY` addons, `AddonPackage`; `build_identity_prompt` is used inside `identity_info_addon`, not as a direct `FrontalLobe` call

*   **hippocampus**: Engram catalog text via `identity.addons.hippocampus_addon` (`TalosHippocampus.get_turn_1_catalog` / `get_recent_catalog`) as volatile user messages

*   **hypothalamus**: `Hypothalamus().pick_optimal_model` + `ModelSelection` → `SynapseClient`

*   **temporal\_lobe**: `IterationShiftParticipant` for session context

***

### Directory / Module Map

```
frontal_lobe/
├── __init__.py
├── admin.py
├── api.py, api_urls.py
├── constants.py
├── frontal_lobe.py      # FrontalLobe class, run(), turn loop
├── models.py           # ReasoningSession, ReasoningTurn, ChatMessage, ModelRegistry
├── synapse.py          # OllamaClient
├── synapse_open_router.py
├── synapse_client.py   # SynapseClient(model_selection)
├── serializers.py
├── urls.py, views.py
└── tests/
```

***

### Public Interfaces

| Interface                           | Type           | Purpose                                                                                         |
| ----------------------------------- | -------------- | ----------------------------------------------------------------------------------------------- |
| `run_frontal_lobe(spike_id)`        | Async function | Entry point for GenericEffectorCaster                                                           |
| `FrontalLobe`                       | Class          | `run()`,`_execute_turn()`,`_build_turn_payload()`                                               |
| `ReasoningSession`                  | Model          | Session state,`current_level`,`max_focus`,`total_xp`                                            |
| `ReasoningTurn`                     | Model          | `apply_efficiency_bonus()`,`was_efficient_last_turn`                                            |
| `Hypothalamus().pick_optimal_model` | Callable       | Chooses`AIModelProvider`by persona vector, budget, context; used in`_execute_turn`hot-swap loop |
| `SynapseClient(model_selection)`    | Class          | Chat client bound to routed LiteLLM id                                                          |


***

### Execution and Control Flow

1.  **Entry:** `run_frontal_lobe(spike_id)` → `FrontalLobe(spike).run()`

2.  **Init:** `resolve_environment_context` → objective, max\_turns; create `ReasoningSession`

3.  **Parietal:** `ParietalLobe.initialize_client(identity_disc)`, `build_tool_schemas()`

4.  **Turn loop:** For each turn: `_record_turn_start` → `_build_turn_payload` (addons; may include `focus_addon` → `apply_efficiency_bonus`) → `pick_optimal_model`\*\* + **`SynapseClient.chat`** (up to 8 failovers on rate limit / connection errors)\*\* → `process_tool_calls` or yield (`ATTENTION_REQUIRED` when no tools)

5.  **Exit:** Session status → COMPLETED, MAXED\_OUT, or ERROR

See [Visualizations](#visualizations) for flowcharts of `run()`, `_execute_turn`, addons, and hot-swap.

***

### Data Flow

```
Spike → resolve_environment_context → objective, max_turns
    → ReasoningSession (identity_disc, participant, spike)
    → _build_turn_payload: AddonPackage → ordered addons → list[ChatMessage]
       (identity_info + normal_chat + hippocampus + focus + …)
    → bulk_create volatile messages → _serialize_messages_sync → chat_message_to_llm_dict
    → pick_optimal_model → SynapseClient.chat (ParietalLobe.chat)
    → ToolCall → ParietalMCP.execute
    → Session: current_focus, total_xp updated (when focus_addon / parietal tools run)
```

***

### Integration Points

| Consumer                | Usage                                                                                                             |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `GenericEffectorCaster` | `run_frontal_lobe`native handler                                                                                  |
| `PrefrontalCortex`      | Creates ReasoningSession, calls`FrontalLobe.run()`                                                                |
| `hypothalamus`          | `pick_optimal_model`,`ModelSelection`                                                                             |
| `identity`              | `ADDON_REGISTRY`addons,`AddonPackage`;`hippocampus_addon`/`identity_info_addon`/`normal_chat_addon`/`focus_addon` |


***

### Configuration and Conventions

*   **Default max\_turns:** From `FrontalLobeConstants.DEFAULT_MAX_TURNS`

*   **History:** Typically `normal_chat_addon` (full non-volatile thread); long threads rely on tool `prune_after_turns` and model context limits

*   **Session status:** PENDING, ACTIVE, PAUSED, COMPLETED, MAXED\_OUT, ERROR, ATTENTION\_REQUIRED, STOPPED

***

### Extension and Testing Guidance

**Extension points:**

*   Add new addons via `identity.addons.addon_registry` (`Callable[[AddonPackage], List[ChatMessage]]`)

*   Extend hippocampus catalog behavior via `identity.addons.hippocampus_addon` / `TalosHippocampus`

*   Adjust history strategy in `normal_chat_addon` or tool pruning via `ToolParameter.prune_after_turns` in `chat_message_to_llm_dict`

**Tests:** `frontal_lobe/tests/`

***

## Visualizations

### `FrontalLobe.run()` lifecycle

Startup resolves context and tools; the turn loop stops early on `Spike` STOPPING, non-`ACTIVE` session, or `should_continue == False`. After the loop, an still-`ACTIVE` session is marked `COMPLETED`. Errors set `ERROR` and return 500. `finally` always calls `unload_client`.

```
flowchart TB
    subgraph startup [Startup]
        a1[run_frontal_lobe spike_id] --> a2[FrontalLobe.run]
        a2 --> a3[resolve_environment_context]
        a3 --> a4[_get_rendered_objective]
        a4 --> a5[_initialize_session max_turns]
        a5 --> a6[_fetch_disc_sync IdentityDisc]
        a6 --> a7[ParietalLobe session log_cb]
        a7 --> a8[build_tool_schemas]
    end
    a8 --> loopAnchor[For each turn in range max_turns]
    loopAnchor --> b1[refresh Spike from DB]
    b1 --> b2{Spike status STOPPING?}
    b2 -->|yes| loopExit[break]
    b2 -->|no| b3[_execute_turn]
    b3 --> b4[refresh ReasoningSession status]
    b4 --> b5{status is ACTIVE?}
    b5 -->|no| loopExit
    b5 -->|yes| b6{should_continue?}
    b6 -->|no| loopExit
    b6 -->|yes| b7{turn equals max_turns minus 1?}
    b7 -->|yes| b8[Set session MAXED_OUT and save]
    b7 -->|no| loopAnchor
    b8 --> loopExit
    loopExit --> c1[refresh session]
    c1 --> c2{status still ACTIVE?}
    c2 -->|yes| c3[Set COMPLETED]
    c2 -->|no| c4[leave status]
    c3 --> finallyBlk[finally unload_client return 200]
    c4 --> finallyBlk
```

### Single turn: `_execute_turn`

After inference succeeds, tool calls go to Parietal; otherwise the session yields to the user with `ATTENTION_REQUIRED`.

```
flowchart TD
    t1[_record_turn_start] --> t2[_build_turn_payload]
    t2 --> t3[estimated_tokens from serialized message size]
    t3 --> t4["Hot-swap loop: pick_optimal_model + SynapseClient.chat"]
    t4 --> t5[_record_turn_completion + mint usage if applicable]
    t5 --> t6[Create assistant ChatMessage]
    t6 --> t7{response.tool_calls and parietal_lobe?}
    t7 -->|yes| t8[process_tool_calls]
    t8 --> t9["return True continue loop"]
    t7 -->|no| t10[Set session ATTENTION_REQUIRED]
    t10 --> t11["return False stop loop"]
```

### Addon pipeline: `_build_turn_payload`

`llm_payload` is built only inside `if unsaved_volatile` after `bulk_create`; typical stacks include at least one addon that emits **new volatile** messages each turn (e.g. `identity_info_addon`).

```
flowchart TB
    p1[Build AddonPackage] --> p2[Query addons order_by phase__id]
    p2 --> p3[For each addon native SYSTEM text OR ADDON_REGISTRY slug OR log missing slug]
    p3 --> p4[Accumulate all_messages]
    p4 --> p5[Filter unsaved_volatile new and volatile]
    p5 --> p6{non-empty?}
    p6 -->|yes| p7[bulk_create then _serialize_messages_sync]
    p7 --> p8[chat_message_to_llm_dict per message prune_after_turns]
    p8 --> p9[Return LLM dict list]
    p6 -->|no| p10[llm_payload not assigned see Assumptions]
```

### Hypothalamus hot-swap loop

Up to **8** attempts (`MAX_FAILOVERS`). Only `RateLimitError` and `APIConnectionError` trigger retry; other exceptions abort immediately.

```
flowchart TD
    h1[attempt 0 to 7] --> h2[sync_to_async pick_optimal_model]
    h2 --> h3{selection is None?}
    h3 -->|yes| h4[raise no available models]
    h3 -->|no| h5[SynapseClient chat messages tools]
    h5 --> h6{Success?}
    h6 -->|yes| h7[break out of loop]
    h6 -->|RateLimitError or APIConnectionError| h7a{attempt lt 7?}
    h7a -->|yes| h1
    h7a -->|no| h8[re-raise]
    h6 -->|any other Exception| h9[raise fatal inference]
```

### Integration context

How `FrontalLobe` sits between CNS and peer apps.

```
flowchart LR
    subgraph cns [CNS]
        sp[Spike]
    end
    subgraph fl [frontal_lobe]
        FL[FrontalLobe]
    end
    subgraph peers [Peers]
        id[identity addons]
        hypo[hypothalamus routing]
        par[parietal_lobe tools]
        hip[hippocampus via hippocampus_addon]
    end
    sp -->|run_frontal_lobe| FL
    FL --> id
    FL --> hypo
    FL --> par
    id --> hip
```

***

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

**Addon order** is determined by `IdentityAddonPhase` on each `IdentityAddon` row. Typical stack:

1.  **IDENTIFY:** `identity_info_addon` → system message from `build_identity_prompt`

2.  **CONTEXT / telemetry:** e.g. `hippocampus_addon`, `telemetry_addon`, etc.

3.  **HISTORY:** `normal_chat_addon` loads all non-volatile `ChatMessage` rows for the session in chronological order (full history; no L1/L2 tiering in that addon today)

4.  **TERMINAL:** e.g. `your_move_addon` if configured

**Inference:** After `_build_turn_payload` produces the LLM dict list, `Hypothalamus.pick_optimal_model` → `SynapseClient.chat`.

### Tool argument pruning (assistant messages)

In `chat_message_to_llm_dict`, for each `ToolCall` on assistant messages, parameters may be replaced with `[PRUNED TO SAVE TOKENS]` when $\text{age} = \text{current\_turn} - \text{message.turn} \geq \text{prune\_after\_turns}$ for that parameter assignment—this replaces the older fixed L1/L2 narrative for tool arguments.

### Invariants (from code)

1.  **Identity required:** `identity_disc` must be set before `run()`; chat models are chosen at runtime via **hypothalamus** (not `IdentityDisc.ai_model()`, which is not used for selection).

2.  **Session linkage:** ReasoningSession links to `spike` and optionally `participant` (IterationShiftParticipant).

### Assumptions

*   Prompt-window heuristic in synapse: `num_ctx = floor(payload_size / 3) + 2048` (not tokenizer-accurate).

*   `_build_turn_payload` only assigns `llm_payload` inside `if unsaved_volatile`; turns should include addons that create **new volatile** `ChatMessage` rows (e.g. `identity_info_addon` on each turn). If nothing is both new and volatile, serialization may not run—keep addon stacks coherent with this pattern.
