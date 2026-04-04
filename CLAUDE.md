# CLAUDE.md — Are-Self API

The single source of truth for any AI agent working on the are-self-api codebase.
Read completely before making any changes.

## The Developer

Michael is a 30+ year programming veteran building Are-Self as an MIT-licensed AI reasoning
engine. The project's mission is providing free AI technology to underserved youth, with
academic interest from MIT and a PhD student collaborator at UPA. Michael has exceptional
product instincts and will actively correct architectural drift. He values ergonomics over
cleverness, biological naming over mechanical metaphors, and clean separation of concerns.

**Workflow:** Claude (Projects chat) for planning and architecture. Claude Code for
implementation via self-contained prompts. Each Claude Code session gets a fresh prompt with
all necessary context. This CLAUDE.md file is read first every session.

## What This Is

A Django 6.x backend for **Are-Self**, an open-source AI reasoning engine with
neurologically-inspired architecture. Every Django app is a brain region. The frontend is
React + Vite + TypeScript (repo: `are-self-ui`). This repo serves a DRF API consumed by
that frontend, plus Celery workers that drive the autonomous reasoning loop.

**Mission:** Empower underprivileged youth in remote areas with free access to AI technology.
MIT licensed. Runs on consumer hardware via Ollama.

**Target user:** A 10-year-old with no money (or their grandma). Every design decision flows
from this. If it requires a credit card, a powerful GPU, or a CS degree — it's wrong. The
system must run on whatever hardware they have, use free models, and be approachable enough
that a child can make art and games with it.

## The Tick Cycle

Everything exists to support this loop — one heartbeat of the system:

```
PNS (Celery Beat ticks)
  → Temporal Lobe (wakes the active iteration, picks current shift)
    → CNS (fires a spike train through the neural pathway)
      → Spikes cascade through neurons
        → Frontal Lobe (starts a reasoning session)
          → LLM reasons in a while-True loop
            → Parietal Lobe (executes tools)
            → Hippocampus (stores and retrieves memories)
            → Hypothalamus (selects the right model)
          → Session concludes or yields
        → Control returns up the spike chain
      → Next spike fires
    → Shift turn count increments
  → Next tick
```

## Django Apps (Brain Regions)

| App | Brain Region | Responsibility |
|-----|-------------|----------------|
| `identity/` | Identity | Persona blueprints → IdentityDiscs (deployed instances) |
| `temporal_lobe/` | Temporal Lobe | Iterations, shifts, turn management |
| `central_nervous_system/` | CNS | Directed-graph execution engine (pathways, spikes) |
| `frontal_lobe/` | Frontal Lobe | Reasoning sessions (LLM inference loop) |
| `parietal_lobe/` | Parietal Lobe | Tool execution gateway (ParietalMCP) |
| `hippocampus/` | Hippocampus | Vector-embedded memory (Engrams, pgvector) |
| `hypothalamus/` | Hypothalamus | Model catalog, routing, budgets, circuit breakers |
| `synaptic_cleft/` | Synaptic Cleft | WebSocket event bus (typed neurotransmitters) |
| `peripheral_nervous_system/` | PNS | Celery fleet monitoring |
| `prefrontal_cortex/` | Prefrontal Cortex | Task management (Epics → Stories → Tasks) |
| `thalamus/` | Thalamus | Chat relay (human ↔ system interface) |
| `environments/` | — | Project context (active environment, context variables) |
| `common/` | — | Shared mixins, constants, base test classes |
| `config/` | — | Django settings, URL routing, Celery config |

Legacy apps still present: `dashboard/` (old HTMX views), `ue_tools/` (UE5 build tools),
`occipital_lobe/` (placeholder). These are deprecated and will be removed.

## Key Code Paths

**Reasoning session:** `frontal_lobe/frontal_lobe.py` → `FrontalLobe.run()` — the while-True
loop. Assembles prompt via `identity/identity_prompt.py` → `build_identity_prompt()`. Calls
LLM via LiteLLM. Parses tool calls → dispatches to `parietal_lobe/parietal_mcp/mcp_*.py`.

**Spike execution:** `central_nervous_system/neuromuscular_junction.py` → `fire_spike()` is the
Celery task entry point. `_execute_spike()` dispatches to effectors.

**Model selection:** `hypothalamus/hypothalamus.py` → `pick_optimal_model()`. Vector-similarity
matching + failover strategies + circuit breakers + budget gates.

**Memory:** `hippocampus/hippocampus.py` → `Hippocampus.save_engram()` / `read_engram()`.
90% cosine similarity dedup. Auto-revectorization on change.

**Real-time events:** `synaptic_cleft/synaptic_cleft.py` → `fire_neurotransmitter()`. Types:
Dopamine (success), Cortisol (error), Acetylcholine (data sync), Glutamate (streaming),
Norepinephrine (monitoring).

**Temporal tick:** `temporal_lobe/temporal_lobe.py` → `trigger_temporal_metronomes()` →
`fetch_canonical_temporal_pathway()` → CNS builds SpikeTrain.

## API Endpoints

All at `/api/v2/`. Most use hyphens; a few legacy routes use underscores. Do not "fix" casing.

```
# CNS
spiketrains, spikes, neuralpathways, neurons, axons, effectors

# Temporal Lobe
iterations, iteration-definitions, iteration-shift-definitions, shifts

# Identity
identities, identity-discs, identity-addons, identity-tags, identity-types
budget-periods, identity-budgets

# Prefrontal Cortex
pre-frontal-item-status, pfc-tags, pfc-epics, pfc-stories, pfc-tasks, pfc-comments

# Hippocampus
engram_tags, engrams

# Frontal Lobe
reasoning_sessions, reasoning_turns

# Parietal Lobe (Tools)
tool-parameter-types, tool-use-types, tool-definitions, tool-parameters
tool-parameter-assignments, parameter-enums, tool-calls

# PNS
celery-workers

# Hypothalamus
llm-providers, model-categories, model-modes, model-families
ai-models, model-providers, model-pricing, model-descriptions
usage-records, sync-status, sync-logs, model-ratings
failover-types, failover-strategies, selection-filters

# Environments
environments, executables, context-variables, context-keys
environment-types, environment-statuses
```

## Current State (April 2026)

**What works:** The full tick cycle runs end-to-end. Identities create, forge into discs,
get slotted into iterations, pick up tasks, reason autonomously, call tools, form memories.
The Hypothalamus semantic parser (83 tests, 98.4% accuracy) enriches models automatically.
Real-time events flow through the Synaptic Cleft. All brain regions have working API endpoints.

**Top priority:** Image and audio manipulation capabilities via **CNS effectors** (not Parietal
Lobe tools). The artist LLM writes a generation prompt to the blackboard, a generation effector
POSTs to whatever image/audio server is configured via environment context variables, and the
result path goes back on the blackboard. This decouples Are-Self from any specific backend
(InvokeAI, ComfyUI, etc.). TTS is already built as a Parietal Lobe tool (`mcp_tts`) using Piper.
The logic node (retry/gate/wait) enables conditional branching for modality routing.

**What's in progress:** See TASKS.md for full task list. Backend items: image generation effector
PoC, error handler effector, branching canonical pathway, spell/cast naming sweep (~9 files in CNS),
engram function consolidation, linter standardization, API URL standardization (underscores → hyphens),
shutdown/restart scripts, prompt_addon state awareness. Recently completed (Session 4): logic node
rewritten to 3 modes (retry/gate/wait) with 16 tests, `mcp_tts` tool built with Piper TTS,
efficiency bonus re-enabled, shallow blackboard copy → deepcopy fix, fixture constraint fix,
EnvironmentEditor "+ Key" button, image/audio architecture documented as CNS effectors.

**Completed renames:** Talos → Are-Self naming sweep is done (only migration history retains
old names). HTMX views fully removed. `TalosEngram` → `Engram`, `TalosExecutable` →
`Executable`, `talos_bin` references cleaned.

**Legacy remnants:** `spell`/`cast`/`Caster` terminology still live in ~9 CNS files.
`parietal_lobe/registry.py` still exists (superseded by Hypothalamus DB-driven routing).
`synapse_open_router.py` is deprecated (no production callers, only test coverage).
The `dashboard/` and `ue_tools/` apps are from the original UE5 build orchestrator and should
not be modified — they'll be removed.

## Style Guide (Enforced)

Read STYLE_GUIDE.md for the full guide. Key rules for quick reference:

**Naming:** Are-Self, not Talos. `snake_case` functions, `PascalCase` classes,
`UPPER_SNAKE_CASE` constants. No prefix when Django app label provides namespace.

**Functions:** No nested functions. No closures. If it doesn't use `self`, it's a
module-level function. Classes are for state.

**Error handling:** Short, targeted try/except. Catch specific exceptions. Broad
`except Exception` only at Celery task or Frontal Lobe `run()` boundaries.

**Logging:** Verbose, bracketed tags: `logger.info('[FrontalLobe] Session %s started.', id)`.
Use `%s` formatting, not f-strings.

**Async:** Intentional, not infectious. Async for WebSocket, Nerve Terminal, genuine
concurrent I/O. Sync for everything else with `sync_to_async` wrap at the Celery boundary.

**Models:** Use mixin hierarchy from `common/models.py`: CreatedMixin, ModifiedMixin,
CreatedAndModifiedWithDelta, NameMixin, DefaultFieldsMixin, UUIDIdMixin, DescriptionMixin.

**Testing:** Real database with fixtures, not mocks. Inherit from `CommonTestCase` or
`CommonFixturesAPITestCase`. Test docstrings begin with "Assert". Run tests with
`venv/Scripts/pytest` from project root on Windows (`venv/bin/pytest` on Linux/Mac).

**Async testing trap:** NEVER make Django test methods async even though `asyncio_mode = "auto"` is
set in pyproject.toml. Async test methods get a SEPARATE database connection that cannot see
transaction-wrapped setUp() objects — tests will fail with IntegrityError or missing data. Instead,
keep test methods sync and use `async_to_sync` from `asgiref.sync` to call async functions:
```python
from asgiref.sync import async_to_sync
result = async_to_sync(some_async_function)(arg1, arg2)
```
This runs the async function on the SAME database connection as the test transaction.

**Fixtures:** PKs are stable integers. Never change an existing PK. Old records deprecated
in place, never deleted. Each app has its own `fixtures/initial_data.json`.

**Canonical Effector PKs:** Important effectors get fixed PKs and model constants
(`central_nervous_system/models.py`): `BEGIN_PLAY=1, LOGIC_GATE=5, LOGIC_RETRY=6,
LOGIC_DELAY=7, FRONTAL_LOBE=8`. These are mirrored in the frontend `nodeConstants.ts`.
PKs 5-100 are reserved for canonical effectors. The frontend uses these PKs (not executable
slugs) to determine which custom React Flow node component to render.

**Formatting:** 88-char lines (Black default). Single quotes. No trailing commas in function
signatures. `isort`-compatible imports.

**Type hints:** All function signatures including return types. `Optional[X]` not `X | None`.
Built-in generics (`list`, `dict`) not `typing.List`, `typing.Dict`.

## Addon System (Identity Addons)

Pure synchronous functions registered in `identity/addons/addon_registry.py` (`ADDON_REGISTRY` dict).
Each addon receives a `ReasoningTurn` and returns `List[Dict[str, Any]]` — messages to inject into
the LLM payload.

### Phases (executed in order)
| Phase | ID | Purpose |
|-------|----|---------|
| IDENTIFY | 1 | Identity/persona injection |
| CONTEXT | 2 | Environmental context |
| HISTORY | 3 | Conversation history reconstruction |
| TERMINAL | 4 | Final payload items (prompt, your_move) |

### Turn Assembly Order (`_build_turn_payload` in `frontal_lobe.py`)
1. Phase 1→2→3→4 addons execute in order, each appending messages
2. `swarm_message_queue` messages are tagged with `<<h>>` prefix and appended
3. `compile_system_messages()` hoists all system messages to index 0

### The `<<h>>` Human Message Tagging System
**Problem solved:** The prompt_addon (Phase 4 TERMINAL) injects the task prompt as a `role: user`
message every turn. The river_of_six addon (Phase 3 HISTORY) replays previous turns' user messages
from `request_payload`. Without differentiation, the same prompt appeared twice from turn 2 onward.

**Solution:** Human messages from `swarm_message_queue` get `<<h>>\n` prepended to their content
in `_build_turn_payload`. The river_of_six addon's `_extract_user_messages()` only replays user
messages that start with `<<h>>`. Addon-injected user messages (prompt_addon, etc.) have no tag
and are skipped — the addon re-injects them fresh each turn.

**Constants:** `HUMAN_TAG = '<<h>>'` is defined in `identity/addons/river_of_six_addon.py`.
`ROLE = 'role'` and `CONTENT = 'content'` are defined in `frontal_lobe/frontal_lobe.py`.
TODO: Move `HUMAN_TAG` to a shared constants file and import everywhere.

### River of Six (Phase 3 HISTORY)
`identity/addons/river_of_six_addon.py` — sliding window of 6 turns with age-based decay.

- **Reconstruction sources (atomic, non-duplicating):**
  - `response_payload` → assistant message
  - `ToolCall` DB records → tool call metadata + tool result messages
  - `request_payload` → only `<<h>>`-tagged user messages

- **Age-based decay (age = current_turn - past_turn):**
  - Age ≥ 4 (`EVICTION_THRESHOLD`): tool results evicted, `tool_calls` stripped from assistant msg
  - Age 3 (`EVICTION_WARNING_AGE`): eviction warning appended to tool results
  - Age 2 (`DECAY_WARNING_AGE`): decay warning appended to tool results

### Key Addons Reference
| PK | Name | Phase | Slug |
|----|------|-------|------|
| 8 | Normal Chat | 3 (HISTORY) | `normal_chat_addon` |
| 13 | River of Six | 3 (HISTORY) | `river_of_six_addon` |
| 14 | Prompt | 4 (TERMINAL) | `prompt_addon` |
| 12 | Your Move | 4 (TERMINAL) | `your_move_addon` |

### response_payload Format
Provider-agnostic. Can be direct `{role, content, ...}` or OpenAI-style
`{choices: [{message: {...}}]}`. The `choices` array should be preserved for the frontend —
don't hardcode `choices[0]`. Extract assistant message by checking `'role' in resp` first,
then falling back to `resp.get('choices', [])[0].get('message', {})`.

## Common Pitfalls

**DRF M2M writes:** Nested serializers with `read_only=True` silently ignore writes. Any
writable FK/M2M needs a `PrimaryKeyRelatedField` write-only counterpart. This pattern is
already applied on Identity, Temporal, Hypothalamus, and AIModelDescription serializers.

**AIModel.description is null.** Use `current_description` (resolved from AIModelDescription:
model-specific first, family fallback second). Never read the deprecated `description` field.

**Never delete AIModel or AIModelProvider records.** Disable them (enabled=False,
is_enabled=False).

**Model string parsing:** Import and use the standalone parser at
`hypothalamus/parsing_tools/llm_provider_parser/model_semantic_parser.py`. Never reinvent
model string parsing.

**Neurotransmitter receptor_class convention:** The `receptor_class` determines the Channels
group (`synapse_{receptor_class}`) and MUST be a domain entity or brain region — never a raw
internal model. Two valid patterns:

1. **Thalamus auto-signals** (`thalamus/signals.py`): Use `sender.__name__` for `post_save`
   signals. These are domain entities: `PFCEpic`, `IdentityDisc`, `ReasoningTurn`, `SpikeTrain`,
   `Engram`, `Iteration`. The frontend subscribes via `useDendrite('PFCEpic', null)`.

2. **Manual brain-region signals** (e.g., `hypothalamus/api.py`): Use the brain region name
   itself: `receptor_class='Hypothalamus'`. The frontend subscribes via
   `useDendrite('Hypothalamus', null)`. Use `dendrite_id` for sub-scoping (specific entity PK)
   and `vesicle` for action metadata (`{'action': 'sync_local'}`).

**NEVER** use internal ORM models like `AIModel`, `AIModelProvider`, or `LLMProvider` as
receptor_class values. These are plumbing — the Hypothalamus brain region owns them, and
signals about them flow through `receptor_class='Hypothalamus'`. Similarly, molecule types
(`Acetylcholine`, `Dopamine`, etc.) are NOT receptor classes — they are Layer 3 routing.

The `useDendrite(receptorClass, dendriteId)` first arg is the receptor class (Layer 1),
not the molecule type (Layer 3). Both sides must agree on receptor_class.
