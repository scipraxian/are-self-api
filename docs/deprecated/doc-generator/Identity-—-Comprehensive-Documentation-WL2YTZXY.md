---
tags: []
parent: 'Talos Detailed Codebase Notes'
collections:
    - Architecture
$version: 3179
$libraryID: 1
$itemKey: WL2YTZXY

---
# Identity — Comprehensive Documentation

## Summary

The **identity** module defines who the AI agent is: system prompt, tools, addons, budget, and embedding vector for routing. Model selection is driven by `Hypothalamus.pick_optimal_model`, not by a static `ai_model` field. Addons are dynamically composed via a registry; the agile addon injects shift-specific work instructions; **hippocampus\_addon** injects engram catalog text.

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

## Target: identity/

### Overview

**Purpose:** Identity defines who the AI agent is: system prompt, tools, addons, budget, and embedding vector for routing. IdentityDisc is the runtime instance used by ReasoningSession; addons inject dynamic context (focus, deadline, agile work, **hippocampus** catalog) per turn.

**Connections in the wider system:**

*   **frontal\_lobe**: `FrontalLobe._build_turn_payload` loads `identity_disc.addons` ordered by `IdentityAddonPhase`, runs `ADDON_REGISTRY[slug](AddonPackage)` (and native description-only addons); no separate `collect_addon_blocks` API

*   **hypothalamus**: `IdentityDisc.vector`, `budget`, `category`; consumed by `pick_optimal_model`

*   **parietal\_lobe**: `IdentityDisc.enabled_tools` for tool schema build

*   **temporal\_lobe**: IdentityDisc as IterationShiftParticipant

*   **hippocampus**: IdentityDisc.memories (M2M to TalosEngram); **hippocampus\_addon** for catalog injection when enabled

***

### Directory / Module Map

```
identity/
├── __init__.py
├── admin.py
├── api.py, api_urls.py
├── forge.py
├── identity_prompt.py   # build_identity_prompt, render_base_identity
├── models.py            # Identity, IdentityDisc, IdentityType, IdentityAddon
├── addons/
│   ├── addon_registry.py # ADDON_REGISTRY
│   ├── addon_package.py  # AddonPackage
│   ├── identity_info_addon.py  # IDENTIFY: wraps build_identity_prompt → system ChatMessage
│   ├── normal_chat_addon.py    # HISTORY: prior non-volatile ChatMessage rows
│   ├── focus_addon.py
│   ├── deadline_addon.py
│   ├── agile_addon.py
│   ├── hippocampus_addon.py
│   ├── telemetry_addon.py, your_move_addon.py, river_of_six_addon.py
│   └── ...
├── serializers.py
├── urls.py
└── tests/
```

***

### Public Interfaces

| Interface                                   | Type      | Purpose                                                                                                                                                  |
| ------------------------------------------- | --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_identity_prompt(identity_disc, ...)` | Function  | Rendered system text from`system_prompt_template`(+ turn-1`last_message_to_self`); used by**identity\_info\_addon**, not called directly by`FrontalLobe` |
| `IdentityDisc`                              | Model     | `vector`(768),`budget`→`IdentityBudget`,`category`→`hypothalamus.AIModelCategory`, enabled\_tools, addons, system\_prompt\_template                      |
| `IdentityBudget`                            | Model     | `max_input_cost_per_token`(hypothalamus routing cap)                                                                                                     |
| `ADDON_REGISTRY`                            | Dict      | `function_slug`→`Callable[[AddonPackage], List[ChatMessage]]`(sync)                                                                                      |
| `AddonPackage`                              | dataclass | Turn context:`session_id`,`spike_id`,`identity_disc`,`turn_number`,`reasoning_turn_id`,`iteration`,`environment_id`,`shift_id`                           |


***

### Execution and Control Flow

1.  **Per turn:** `FrontalLobe._build_turn_payload` builds an `AddonPackage` for the current `ReasoningTurn`.

2.  **Ordering:** `identity_disc.addons` are evaluated in `IdentityAddonPhase.id` order (IDENTIFY → CONTEXT → HISTORY → …).

3.  **Native addons:** If `function_slug` is empty but `description` is set, a volatile **system** `ChatMessage` is created from the description text.

4.  **Registered addons:** Otherwise `ADDON_REGISTRY[function_slug](package)` must return a `list[ChatMessage]` (may be empty). Examples: `identity_info_addon` (system prompt via `build_identity_prompt`), `normal_chat_addon` (full non-volatile history), `hippocampus_addon` (catalog), `focus_addon` (calls `ReasoningTurn.apply_efficiency_bonus()` then injects focus stats).

5.  **Persistence:** New volatile messages are `bulk_create`d before `_serialize_messages_sync` builds the LLM payload.

***

### Data Flow

```
IdentityDisc (system_prompt_template, addons, enabled_tools, budget, vector, category)
    → AddonPackage + ordered IdentityAddon rows
    → ADDON_REGISTRY[slug](package) → list[ChatMessage]
    → (optional bulk_create volatile rows)
    → chat_message_to_llm_dict (tool-call pruning by age vs ToolParameter.prune_after_turns)
```

***

### Integration Points

| Consumer            | Usage                                                                              |
| ------------------- | ---------------------------------------------------------------------------------- |
| `FrontalLobe`       | `_build_turn_payload`drives addons;`identity_info_addon`/`normal_chat_addon`/ etc. |
| `ParietalLobe`      | `identity_disc.enabled_tools`                                                      |
| `agile_addon`       | Injects shift-specific work (SIFTING, EXECUTING, etc.)                             |
| `hippocampus_addon` | Injects engram catalog (`TalosHippocampus`) as volatile messages                   |
| `hypothalamus`      | Reads`vector`, budget, category for`pick_optimal_model`                            |


***

### Configuration and Conventions

*   **IdentityType:** PM (1), WORKER (2) — used by Prefrontal Cortex for work-eligibility

*   **Addon slug:** Must match key in ADDON\_REGISTRY

***

### Extension and Testing Guidance

**Extension points:**

*   Add new addons: implement `(AddonPackage) -> list[ChatMessage]`, register in `ADDON_REGISTRY`

*   Extend IdentityFields for new persona attributes

**Tests:** `identity/tests/`

***

## Visualizations

### Addon pipeline per turn

`AddonPackage` is passed through `identity_disc.addons` ordered by `IdentityAddonPhase`; each row is either a native description system message or a registry callable.

```
flowchart TB
    pkg[AddonPackage]
    ord[Order by IdentityAddonPhase id]
    row[Each IdentityAddon row]
    pkg --> ord
    ord --> row
    row --> choice{function_slug empty and description set?}
    choice -->|yes| native[Volatile system ChatMessage from description]
    choice -->|no| reg[ADDON_REGISTRY slug package]
    reg --> msgs[List of ChatMessage]
    native --> merge[Concatenate all addon messages]
    msgs --> merge
    merge --> bulk[Optional bulk_create volatile rows]
```

### Persona fields to hypothalamus routing

Semantic model choice uses the disc embedding and budget; no duplication of cosine math here.

```
flowchart LR
    disc[IdentityDisc]
    v[vector 768]
    b[budget max_input_cost_per_token]
    c[category AIModelCategory]
    disc --> v
    disc --> b
    disc --> c
    v --> pick[Hypothalamus.pick_optimal_model]
    b --> pick
    c --> pick
    pick --> sel[ModelSelection or None]
```

***

## Mathematical Framing

### IdentityDisc Composition

An IdentityDisc $D$ is a tuple:

$$
D = (\text{name}, \text{system\_prompt}, \mathbf{v}_p, b, \mathcal{T}, \mathcal{A}, \ldots)
$$

Where:

*   $\mathbf{v}_p \in \mathbb{R}^{768}$  = persona embedding (`vector`) for hypothalamus routing

*   $b$  = budget cap on input cost per token (`IdentityBudget`)

*   $\mathcal{T}$  = enabled tools (ToolDefinition set)

*   $\mathcal{A}$  = addons (IdentityAddon set)

### Addon Resolution

For addon $a \in \mathcal{A}$ with $\text{function\_slug} = s$:

$$
\text{messages}(a) = \begin{cases}
\text{ADDON\_REGISTRY}[s](\text{AddonPackage}) & \text{if } s \in \text{ADDON\_REGISTRY} \\
[\text{ChatMessage}(\text{system}, a.\text{description})] & \text{if } s \text{ empty and } a.\text{description} \\
[] & \text{otherwise}
\end{cases}
$$

### AddonPackage

Fields match `identity/addons/addon_package.py`: `iteration`, `identity_disc` (UUID), `turn_number`, `reasoning_turn_id`, optional `session_id`, `spike_id`, `environment_id`, `shift_id`.

Registry callables are **synchronous**; `FrontalLobe` wraps them with `sync_to_async`.

### Agile Addon Shift Mapping

The agile addon produces different content per shift:

*   **SIFTING:** PM refinement, Worker bidding

*   **PRE\_PLANNING:** PM backlog selection, Worker sifting

*   **EXECUTING:** Worker owned/available stories

*   **SLEEPING:** Reflection/growth

Formally, $\text{agile\_addon}(p) = f(\text{shift\_id}, \text{identity\_type}, \text{environment\_id})$ where $f$ queries PFC and temporal models.

### Invariants (from code)

1.  **Addon uniqueness:** Each addon has at most one function\_slug; slug maps to one callable.

2.  **IdentityDisc required:** ReasoningSession requires identity\_disc for tool resolution.
