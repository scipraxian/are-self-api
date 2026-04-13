# Identity — Comprehensive Documentation

## Summary

The **identity** module provides persona templates (`Identity`) and live instances (`IdentityDisc`). An IdentityDisc chooses the AI model, enabled tools, addons, and system prompt. Addons are dynamically composed via a registry; the agile addon injects shift-specific work instructions.

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

## Target: identity/

### Overview

**Purpose:** Identity defines who the AI agent is: system prompt, model, tools, addons. IdentityDisc is the runtime instance used by ReasoningSession; addons inject dynamic context (focus, deadline, agile work) per turn.

**Connections in the wider system:**
- **frontal_lobe**: `build_identity_prompt`, `collect_addon_blocks` for each turn
- **parietal_lobe**: `IdentityDisc.enabled_tools` for tool schema build
- **temporal_lobe**: IdentityDisc as IterationShiftParticipant
- **hippocampus**: IdentityDisc.memories (M2M to TalosEngram)

---

### Directory / Module Map

```
identity/
├── __init__.py
├── admin.py
├── api.py, api_urls.py
├── forge.py
├── identity_prompt.py   # build_identity_prompt, collect_addon_blocks
├── models.py            # Identity, IdentityDisc, IdentityType, IdentityAddon
├── addons/
│   ├── addon_registry.py # ADDON_REGISTRY
│   ├── addon_package.py  # AddonPackage
│   ├── focus_addon.py
│   ├── deadline_addon.py
│   └── agile_addon.py
├── serializers.py
├── urls.py
└── tests/
```

---

### Public Interfaces

| Interface | Type | Purpose |
|-----------|------|---------|
| `build_identity_prompt(identity_disc, ...)` | Function | System prompt from template + last_message_to_self |
| `collect_addon_blocks(identity_disc, ...)` | Function | Returns `[(addon_name, addon_text), ...]` |
| `IdentityDisc` | Model | ai_model, enabled_tools, addons, system_prompt_template |
| `ADDON_REGISTRY` | Dict | function_slug → callable(AddonPackage) → str |

---

### Execution and Control Flow

1. **Prompt build:** FrontalLobe calls `build_identity_prompt` before each turn
2. **Addon collection:** `collect_addon_blocks` iterates `identity_disc.addons`, resolves via `ADDON_REGISTRY[slug](package)`
3. **Addon package:** `AddonPackage(iteration, identity, identity_disc, turn_number, reasoning_turn_id, environment_id, shift_id)`
4. **Injection:** Addon blocks become volatile user messages in the turn payload

---

### Data Flow

```
IdentityDisc (system_prompt_template, addons, enabled_tools, ai_model)
    → build_identity_prompt → system message
    → collect_addon_blocks → [(name, text), ...]
    → AddonPackage → ADDON_REGISTRY[slug](package) → str
    → ChatMessage(role=user, is_volatile=True)
```

---

### Integration Points

| Consumer | Usage |
|----------|-------|
| `FrontalLobe` | `build_identity_prompt`, `collect_addon_blocks` |
| `ParietalLobe` | `identity_disc.enabled_tools` |
| `agile_addon` | Injects shift-specific work (SIFTING, EXECUTING, etc.) |

---

### Configuration and Conventions

- **IdentityType:** PM (1), WORKER (2) — used by Prefrontal Cortex for work-eligibility
- **Addon slug:** Must match key in ADDON_REGISTRY

---

### Extension and Testing Guidance

**Extension points:**
- Add new addons: implement `(AddonPackage) -> str`, register in ADDON_REGISTRY
- Extend IdentityFields for new persona attributes

**Tests:** `identity/tests/`

---

## Mathematical Framing

### IdentityDisc Composition

An IdentityDisc $D$ is a tuple:
$$
D = (\text{name}, \text{system\_prompt}, \text{ai\_model}, \mathcal{T}, \mathcal{A}, \ldots)
$$

Where:
- $\mathcal{T}$ = enabled tools (ToolDefinition set)
- $\mathcal{A}$ = addons (IdentityAddon set)

### Addon Resolution

For addon $a \in \mathcal{A}$ with $\text{function\_slug} = s$:
$$
\text{content}(a) = \begin{cases}
\text{ADDON\_REGISTRY}[s](\text{AddonPackage}) & \text{if } s \in \text{ADDON\_REGISTRY} \\
a.\text{description} & \text{otherwise}
\end{cases}
$$

### AddonPackage

$$
\text{AddonPackage} = (\text{iteration\_id}, \text{identity\_id}, \text{identity\_disc\_id}, \text{turn\_number}, \text{reasoning\_turn\_id}, \text{environment\_id}, \text{shift\_id})
$$

Addons may be sync or async; async are run via `async_to_sync`.

### Agile Addon Shift Mapping

The agile addon produces different content per shift:
- **SIFTING:** PM refinement, Worker bidding
- **PRE_PLANNING:** PM backlog selection, Worker sifting
- **EXECUTING:** Worker owned/available stories
- **SLEEPING:** Reflection/growth

Formally, $\text{agile\_addon}(p) = f(\text{shift\_id}, \text{identity\_type}, \text{environment\_id})$ where $f$ queries PFC and temporal models.

### Invariants (from code)

1. **Addon uniqueness:** Each addon has at most one function_slug; slug maps to one callable.
2. **IdentityDisc required:** ReasoningSession requires identity_disc for tool resolution.
