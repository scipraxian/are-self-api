# CLAUDE.md — Are-Self API

The single source of truth for any AI agent working on the are-self-api codebase.
Read completely before making any changes.

> **Active work lives elsewhere.** See `TASKS.md` for in-progress items,
> `NEURAL_MODIFIER_COMPLETION_PLAN.md` for the NeuralModifier roadmap, and
> `git log` for what landed recently. Do NOT replay session diaries in this
> file — when work lands, lift the durable rule into the appropriate section
> below, then delete the notes. This file is the *standing reference*, not the
> changelog.

## Standing rulings (project-wide)

Michael-rulings that outlive any one task. Do not re-litigate or forget these:

- `initial_data.json` and fixture files are **Michael-only-delete** — never
  propose removing them.
- NeuralModifier bundles install via the modifier-garden UI, not `install.bat`.
- NeuralModifier layout is locked: **`neuroplasticity/genomes/<slug>.zip`**
  (committed source of truth), **`neuroplasticity/grafts/<slug>/`** (gitignored
  runtime install tree), **`neuroplasticity/operating_room/`** (gitignored
  transient scratch — empty between operations). No sibling root-level dirs;
  no unzipped source tree under `modifier_genome/`.
- Uninstall DELETES the `NeuralModifier` row (AVAILABLE = zip exists + no DB
  row). Contributions, logs, and events all CASCADE away. A failed fresh
  install also deletes the row it created — never leaves a BROKEN or
  DISCOVERED stub behind. BROKEN is reserved for boot-time drift on a
  previously-working install.
- UUIDs are `uuid.uuid4()` random literals — no UUIDv5, namespaces, or
  deterministic seeding. Existing UUID literals in fixtures are frozen; do not
  regenerate.
- No polling. Real-time sync goes through Acetylcholine push; a REST pull
  fallback (e.g. `graph_data?since_turn_number=N`) is a safety net, never the
  primary path. No `setInterval`, no Celery-beat refresh loops on the UI.
- `receptor_class` must be a domain entity or brain region name (e.g.
  `'ReasoningTurnDigest'`, `'Hypothalamus'`, `'PFCEpic'`), NEVER an internal
  ORM model name (`'AIModel'`, `'LLMProvider'`) or a molecule type
  (`'Acetylcholine'`, `'Dopamine'`). Full convention in Common Pitfalls.
- Digests and side-cars are discardable — nuke-and-rebuild, never backfill.
  The authoritative entity is the turn; the digest can be rebuilt from it.
- Do not bypass `_update_status` in `neuromuscular_junction.py` — it is the
  single source of truth for spike status (sets `self.status` AND saves).
- Never delete `AIModel` or `AIModelProvider` records — disable them
  (`enabled=False`, `is_enabled=False`).
- Fixture tiers — general rule: **rows referenced by model class constants
  live in `genetic_immutables` regardless of which table they live in.**
  Their UUIDs are sacred, non-negotiable, and must always resolve — including
  under the minimal `CommonTestCase` fixture load. That covers
  `Effector.BEGIN_PLAY` / `LOGIC_GATE` / `LOGIC_RETRY` / `LOGIC_DELAY` /
  `FRONTAL_LOBE` / `DEBUG`, `Executable.BEGIN_PLAY` / `PYTHON` / `DJANGO`,
  and `SyncStatus.RUNNING` / `SUCCESS` / `FAILED`. NeuralModifier-contributed
  rows in those same tables go to `initial_phenotypes` or bundle fixtures
  instead — the rule is about the *row*, not the table.
- Other fixture-tier rulings: definition rows (e.g. `IterationDefinition`) →
  `zygote`, instance rows (e.g. `Iteration`) → `initial_phenotypes`; entire
  parietal tool suite → `zygote`; hypothalamus zygote = 3 models
  (`nomic-embed-text`, `qwen2.5-coder:7b`, `qwen2.5-coder:32b`);
  `django_celery_beat` stays in `genetic_immutables`; `petri_dish.json` is
  intentionally non-empty and composes with `genetic_immutables.json` via
  the common test class.

## The Developer

Michael is a 40+ year engineer (born 1968, started coding in 1980 at age 12) building
Are-Self as an MIT-licensed AI reasoning engine. The project's mission is bringing free
AI to underserved youth, with
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
MIT licensed. Runs on consumer hardware via Ollama. Released by Michael personally under
[scipraxian](https://github.com/scipraxian) — not a company or nonprofit. Would pitch TO
nonprofits and churches as a free tool they can use.

**Target user:** A 10-year-old with no money (or their grandma). Every design decision flows
from this. If it requires a credit card, a powerful GPU, or a CS degree — it's wrong. The
system must run on whatever hardware they have, use free models, and be approachable enough
that a child can make art and games with it.

## The Five Repositories

| Repo | Purpose |
|------|---------|
| [are-self-api](https://github.com/scipraxian/are-self-api) | Django backend (this repo) |
| [are-self-ui](https://github.com/scipraxian/are-self-ui) | React frontend |
| [are-self-docs](https://github.com/scipraxian/are-self-docs) | Docusaurus documentation site → [are-self.com](https://are-self.com) |
| [are-self-research](https://github.com/scipraxian/are-self-research) | LaTeX whitepapers (APA 7th edition) |
| [are-self-learn](https://github.com/scipraxian/are-self-learn) | Curriculum layer for kids and the grownups who teach them (launched 2026-04-14) |

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

Legacy app still present: `dashboard/` (old HTMX views) — deprecated, will be removed.

`ue_tools/` is **not** deprecated. It contains the Unreal Engine build orchestration flow
and is being extracted as the first `NeuralModifier` bundle in the Pass 2 neuroplasticity
architecture — the committed bundle archive lives at `neuroplasticity/genomes/unreal.zip`.
`occipital_lobe/` is **not** a placeholder — it is the home for OS-level file-watcher
intake (visual-cortex-style event detection that routes folder changes to the associated
environment's neural pathways) and now also hosts the generic log-merge utilities and the
`LogParserFactory` registry (moved out of `ue_tools/` in Pass 2 Task 3/4).

`neuroplasticity/` is the Pass 2 install / lifecycle registry for `NeuralModifier` bundles
(Are-Self's word for an installable extension bundle). The app owns `NeuralModifier`,
`NeuralModifierContribution` (GFK with UUIDField object_id — the uninstall manifest),
`NeuralModifierInstallationLog`, and the `NeuralModifierStatus` /
`NeuralModifierInstallationEventType` enums. `INSTALLED_APPS` is never mutated at runtime —
contributions are data.

**Three directories, three roles** (all under `neuroplasticity/`; the latter two are
gitignored):

- `neuroplasticity/genomes/<slug>.zip` — **committed** user-facing archives. The zip IS the
  bundle; there is no unzipped source tree anywhere. Each zip holds `manifest.json`,
  `modifier_data.json`, and `code/` at its top level. The Modifier Garden UI drives install
  / delete against these zips. A fresh clone ships `genomes/unreal.zip` → one AVAILABLE row.
- `neuroplasticity/grafts/<slug>/` — runtime install tree that persists the bundle's live
  code on `sys.path` after install. `install_bundle_from_archive` is the single install
  entry; it extracts into `operating_room/` then copies into `grafts/<slug>/`.
- `neuroplasticity/operating_room/` — transient scratch root for install / upgrade
  extractions. Every op creates a fresh `tempfile.mkdtemp` under this dir and nukes it in a
  `try/finally` — after any operation (success OR failure), `operating_room/` is empty.

**State machine:** AVAILABLE (zip in `genomes/`, **no DB row**) → Install → INSTALLED →
Enable → ENABLED → Disable → INSTALLED → Uninstall → AVAILABLE → (delete the zip to remove
the bundle entirely). Uninstall **deletes** the `NeuralModifier` row — contributions, logs,
and events all CASCADE away. BROKEN surfaces only from boot-time hash drift or load failure
on a previously-installed bundle; a failed fresh install deletes its row instead of
flipping BROKEN. `DISCOVERED` is retired as a surfaced status (enum value stays in fixtures
for backwards compat of historical log events; never assigned to new rows).

Bundle-time registration surfaces are in place: `register_parietal_tool` /
`unregister_parietal_tool` in `parietal_lobe/parietal_mcp/gateway.py` (module-level
`_PARIETAL_TOOL_REGISTRY` checked first in `ParietalMCP.execute()`, falls through to the
importlib path on miss); `register_native_handler` / `unregister_native_handler` in
`central_nervous_system/effectors/effector_casters/neuromuscular_junction.py` (backed by
the single `NATIVE_HANDLERS` dict, collisions raise `RuntimeError`, unregister is idempotent).
`LogParserFactory.register()` at `occipital_lobe/log_parser.py` is the equivalent surface
for parsers.

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

**Digest side-car:** `frontal_lobe/digest_builder.py` builds `ReasoningTurnDigest` rows
idempotently; `frontal_lobe/signals.py` fires a `post_save(ReasoningTurn)` handler that
skips raw fixture loads and skips when `model_usage_record_id is None`, then broadcasts
Acetylcholine with `receptor_class='ReasoningTurnDigest'` and the full digest as vesicle.

## API Endpoints

All at `/api/v2/`. Most use hyphens; a few legacy routes use underscores. Do not "fix" casing.

```
# CNS
spiketrains, spikes, neuralpathways, neurons, axons, effectors
effector-contexts, effector-argument-assignments, distribution-modes

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
executable-arguments, executable-argument-assignments
```

## MCP Server (Model Context Protocol)

Are-Self exposes an MCP-compliant endpoint at `/mcp` that allows external clients
(Claude Desktop, Cowork, Claude Code) to discover and invoke Are-Self tools via
JSON-RPC 2.0 over Streamable HTTP. This replaces the old `django-rest-framework-mcp`
library with a custom implementation built on the official MCP protocol spec.

**Architecture:** A thin `MCPToolRegistry` in `mcp_server/server.py` stores tool schemas
and async handlers. The `mcp_server/django_bridge.py` Django async view implements
the Streamable HTTP transport — routing `initialize`, `tools/list`, and `tools/call`
JSON-RPC methods. All tool handlers use `sync_to_async` for Django ORM compatibility.

**Phase 1 Tools (Implemented):**

| Tool | Module | Description |
|------|--------|-------------|
| `list_neural_pathways` | cns_tools | List available pathways |
| `get_neural_pathway` | cns_tools | Pathway detail with neurons/axons |
| `launch_spike_train` | cns_tools | Fire a pathway, returns spike_train_id |
| `get_spike_train_status` | cns_tools | Monitor running spike trains |
| `stop_spike_train` | cns_tools | Graceful stop signal |
| `list_effectors` | cns_tools | Available effector building blocks |
| `list_identity_discs` | identity_tools | Deployed identity instances |
| `list_environments` | environment_tools | Available project environments |
| `search_engrams` | hippocampus_tools | Text search of memory store |
| `read_engram` | hippocampus_tools | Read specific memory by ID |
| `save_engram` | hippocampus_tools | Create new memory with tags |
| `list_pfc_tasks` | pfc_tools | List tasks from prefrontal cortex |
| `create_pfc_task` | pfc_tools | Create task assigned to story |
| `send_thalamus_message` | thalamus_tools | Message through chat relay |

**Phase 2 Planned:**
- Cerebrospinal fluid write tool (pre-load context before launching spike trains)
- SSE streaming via neurotransmitter callbacks (real-time execution updates)
- Vector similarity search for engrams (instead of text-only)
- Full Thalamus message pipeline (WebSocket delivery)
- Authentication/authorization layer
- Cowork custom connector registration

**Key Files:**
- `mcp_server/server.py` — MCPToolRegistry class and factory
- `mcp_server/django_bridge.py` — Django async view (JSON-RPC 2.0 dispatch)
- `mcp_server/urls.py` — URL routing (`/mcp`)
- `mcp_server/tools/*.py` — Tool implementations by brain region

**Connecting as a Local MCP Server:**

Are-Self's `/mcp` endpoint speaks standard MCP Streamable HTTP. The canonical local URL
is `https://local.are-self.com/mcp` — a Cloudflare DNS A record points `local.are-self.com`
at `127.0.0.1`, so the hostname works on the user's own machine without any hosts-file
editing and a real publicly-trusted cert (ZeroSSL) can be issued for it.

NGINX runs in Docker (`docker compose up`) as a reverse proxy in front of Daphne, Vite,
and the Docusaurus dev server. Routing:

| Path | Upstream |
|------|---------|
| `/` (exact)              | Static landing page (`nginx/html/index.html`) |
| `/mcp`, `/mcp/`          | Daphne (Django) — MCP JSON-RPC |
| `/api/`, `/api-auth/`    | Daphne |
| `/admin/`, `/static/`    | Daphne |
| `/ws/`                   | Daphne (Channels websockets) |
| everything else          | Vite dev server on `host:5173` (React app) |

(Docusaurus is intentionally NOT reverse-proxied. The public site at
`https://are-self.com` is GitHub Pages with Docusaurus `baseUrl: '/'`, and
changing `baseUrl` to make a path-based proxy work breaks the Pages build.
The landing page probes `http://localhost:3000/` via an `<img>` onload
trick and opens the dev server in a new tab directly.)

NGINX auto-detects TLS: if `nginx/certs/cert.pem` and `nginx/certs/key.pem` exist it
serves HTTPS on 443 with an HTTP→HTTPS redirect on 80. Otherwise it serves plain HTTP
on 80. The detection runs in `nginx/entrypoint.sh`, which is mounted and invoked via
an explicit `docker compose` entrypoint override (Windows bind mounts don't preserve
the exec bit, so the stock `/docker-entrypoint.d/` scanner is bypassed).

**Connecting Claude Code:**
```
claude mcp add --transport http are-self https://local.are-self.com/mcp
```
Run from inside the repo root so the config scopes to the project. The 14 Phase 1 tools
appear as `mcp__are-self__*` inside any `claude` session started in that directory.

**Cowork → local MCP:** Adding `https://local.are-self.com/mcp` as a custom connector in
the claude.ai Connectors UI fails because the connector fetch happens from Anthropic's
cloud, which resolves `local.are-self.com → 127.0.0.1` to its own loopback, not the
user's. Fixing this requires an outbound tunnel (Cloudflare Tunnel, ngrok, tailscale
funnel) to expose `/mcp` on a publicly-reachable hostname. This works per-user; it is
not a distribution mechanism. Tracking at
`github.com/anthropics/claude-ai-mcp/issues/9`.

**Django settings required for the NGINX fronting:**
- `CSRF_TRUSTED_ORIGINS` must include `http(s)://local.are-self.com` and plain
  `http(s)://localhost` (admin POSTs originate from whichever scheme/host the browser
  used to reach NGINX).
- URL routing registers **both** `path('mcp', ...)` and `path('mcp/', ...)` because
  `APPEND_SLASH` middleware cannot redirect POST requests (it would lose the body),
  so MCP clients hitting either form need an explicit route.

**Testing the endpoint manually (PowerShell):**
```powershell
# PowerShell's `curl` is aliased to Invoke-WebRequest; use Invoke-RestMethod for
# JSON-RPC, or `curl.exe` with single quotes to avoid escape-hell.

$body = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
Invoke-RestMethod -Uri https://local.are-self.com/mcp `
  -Method Post -ContentType application/json -Body $body
```

## Current State

Released as MIT open source on April 7, 2026. All four public repos live under
[scipraxian](https://github.com/scipraxian); the site is at are-self.com; social
accounts live under the `scipraxian` handle across the usual platforms. The full
tick cycle runs end-to-end (Identity → IdentityDisc → iteration → task pickup →
autonomous reasoning → tool calls → memory formation → narrative dumps). MCP
server at `/mcp` with 14 tools across 6 brain regions (Phase 1 request/response).
NGINX reverse proxy with HTTP/HTTPS autodetect and a real ZeroSSL cert for
`local.are-self.com`.

For current-state specifics, in-flight work, and priorities: see `TASKS.md`.

**Legacy / deprecation state:**
- `dashboard/` (original UE5 build orchestrator, HTMX views) is deprecated and
  will be removed.
- `parietal_lobe/registry.py` is superseded by Hypothalamus DB-driven routing.
- `synapse_open_router.py` is deprecated (no production callers).
- `ue_tools/` stays, being extracted as the first `NeuralModifier` bundle at
  `neuroplasticity/genomes/unreal.zip`. Its generic log-merge utilities
  already moved to `occipital_lobe/`; its parser split into generic core + UE
  strategies registered via `LogParserFactory`. `deploy_release_test` is slated
  for removal during that extraction.
- `ollama_fixture_generator.py` has been deleted — its output is captured as
  frozen literals in `hypothalamus/fixtures/zygote.json`.
- Talos → Are-Self rename complete (only migration history retains the old name).
  Spell/Cast naming sweep complete across CNS. HTMX removed.

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

**Immutability directive (project-wide standing rule):** anything not truly immutable uses
UUID primary keys. The only things that keep integer PKs are protocol enums and canonical
vocabulary tables with class-level integer constants that core owns exclusively. Everything
else — and especially anything a `NeuralModifier` might ever contribute rows to — is
UUID-keyed.

**Fixtures — four biological tiers (Pass 2, in progress):**

1. **`genetic_immutables.json`** — protocol enums, canonical vocabulary tables,
   and **any row referenced by a model class constant** (regardless of which
   table it lives in — the rule is about the *row*, not the table).
   Integer-PK (core-owned, never contributed to by NeuralModifiers):
   `SpikeStatus`, `AxonType`, `CNSDistributionMode`, `NeuralModifierStatus`,
   `NeuralModifierInstallationEventType`, `IdentityAddonPhase`, `BudgetPeriod`,
   etc.
   UUID-PK vocabulary (NeuralModifier-extensible, all hypothalamus vocab flipped
   in Pass 2): `AIMode`, `AIModelCategory`, `AIModelCapabilities`, `AIModelTags`,
   `AIModelFamily`, `AIModelVersion`, `AIModelCreator`, `AIModelRole`,
   `AIModelQuantization`, `LLMProvider`, `FailoverType`, `FailoverStrategy`,
   `FailoverStrategyStep`, `SyncStatus`.
   Class-constant rows from otherwise-NeuralModifier-extensible tables (the
   reason this rule exists: code referencing `Effector.BEGIN_PLAY` must
   resolve it even under the minimal `CommonTestCase` fixture load):
   `Effector.BEGIN_PLAY`, `LOGIC_GATE`, `LOGIC_RETRY`, `LOGIC_DELAY`,
   `FRONTAL_LOBE`, `DEBUG`; `Executable.BEGIN_PLAY`, `PYTHON`, `DJANGO`;
   `SyncStatus.RUNNING`, `SUCCESS`, `FAILED`. NeuralModifier-contributed rows
   in those same tables go to `initial_phenotypes` or bundle fixtures.
   Loaded by install, Docker, and tests. Never renumber (for integer-PK rows),
   never delete.
2. **`zygote.json`** — the minimum UUID-keyed rows the system needs to boot and bind
   one end-to-end identity thread for tests: `nomic-embed-text` (hippocampus hard
   dependency), the canonical `Identity`/`IdentityDisc`, the default `ProjectEnvironment`.
   Loaded by install, Docker, and tests.
3. **`initial_phenotypes.json`** — the rest of the committed-to-core structural rows that
   ship to end users out-of-the-box (context variables, core Effectors/Neurons/Axons/
   NeuralPathways that stay in core, reference iteration definitions, etc.). Loaded by
   install and Docker. **Not loaded by tests.**
4. **`petri_dish.json`** — test-only instance rows. Loaded by `CommonFixturesAPITestCase`
   only. Self-contained, must not depend on `initial_phenotypes.json`.

Load order — install/Docker: `genetic_immutables` → `zygote` → `initial_phenotypes`.
Tests: `genetic_immutables` → `zygote` → `petri_dish`. `CommonTestCase` loads only
`genetic_immutables`. None of these filenames are Django magic names; test base classes
and `are-self-install.bat` list per-app paths explicitly.

*UUID PKs (`NeuralModifier`-extensible):* `Effector`, `EffectorContext`,
`EffectorArgumentAssignment`, `Neuron`, `NeuronContext`, `Axon`, `Executable`,
`ExecutableSwitch`, `ExecutableArgument`, `ExecutableArgumentAssignment`, `ContextVariable`,
`ToolDefinition`, `ToolParameter`, `ToolParameterAssignment`, `ParameterEnum`,
`AIModelDescription`, `IterationDefinition`, `IterationShiftDefinition` (all flipped in
Pass 1), plus `ProjectEnvironmentContextKey`, `ProjectEnvironmentStatus`, and
`ProjectEnvironmentType` (flipped in Pass 2 Task 4.5), plus every model in
`hypothalamus/models.py` — `LLMProvider`, `AIModelCategory`, `AIModelCapabilities`,
`AIModelTags`, `AIMode`, `AIModelFamily`, `AIModelVersion`, `AIModelCreator`,
`AIModelRole`, `AIModelQuantization`, `AIModel`, `AIModelVector`, `AIModelProvider`,
`AIModelPricing`, `AIModelProviderUsageRecord`, `FailoverStrategy`, `FailoverType`,
`FailoverStrategyStep`, `AIModelSelectionFilter`, `SyncStatus`, `AIModelSyncLog`,
`AIModelRating`, `LiteLLMCache`, `AIModelDescriptionCache`, `AIModelSyncReport`
(whole-app flip in Pass 2, "consider the entire `hypothalamus/models.py` volatile and
mutable by neuroplasticity" — Michael), plus the already-UUID models (`Identity`,
`IdentityDisc`, `ProjectEnvironment`, `NeuralPathway`).

`SyncStatus.RUNNING`, `SyncStatus.SUCCESS`, `SyncStatus.FAILED` are UUID class constants
(same pattern as `Effector.BEGIN_PLAY`) — used by `hypothalamus.py`'s `sync_remote` flow
to look up status rows by stable PK. Do not renumber or regenerate.

**Canonical Effector / Executable constants:** Important effectors and executables have
model-class UUID constants (`central_nervous_system/models.py`, `environments/models.py`):
`Effector.BEGIN_PLAY`, `LOGIC_GATE`, `LOGIC_RETRY`, `LOGIC_DELAY`, `FRONTAL_LOBE`, `DEBUG`;
`Executable.BEGIN_PLAY`, `PYTHON`, `DJANGO`. These are `uuid.UUID(...)` literals — the
names stay stable but values are UUIDs, not integers. **The rows themselves live in
`genetic_immutables` fixtures** (class-constant rule — see Fixture tiers above) so that
code referencing them by constant always resolves, including under the minimal
`CommonTestCase` load. The frontend `nodeConstants.ts` must mirror these as UUID strings
(companion PR gates the branch merge). The frontend uses these to determine which custom
React Flow node component to render. (The legacy `Executable.UNREAL_CMD` /
`UNREAL_AUTOMATION_TOOL` / `UNREAL_STAGING` / `UNREAL_RELEASE_TEST` / `UNREAL_SHADER_TOOL` /
`VERSION_HANDLER` / `DEPLOY_RELEASE` class constants were removed — had no live Python
callers.)

**Debug node:** Effector UUID constant `DEBUG`. Native handler `debug_node` in
`central_nervous_system/effectors/effector_casters/debug_node.py`. Logs axoplasm state and
neuron context at INFO level. Useful for diagnosing axoplasm data flow between spikes.
Configurable via NeuronContext key `debug_label` (defaults to "DEBUG").

**Formatting:** 88-char lines (Black default). Single quotes. No trailing commas in function
signatures. `isort`-compatible imports.

**Type hints:** All function signatures including return types. `Optional[X]` not `X | None`.
Built-in generics (`list`, `dict`) not `typing.List`, `typing.Dict`.

## Addon System (Identity Addons)

Class-based handlers registered in `identity/addons/_handler_registry.py`
(`HANDLER_REGISTRY` dict, keyed by `IdentityAddon.addon_class_name`). Each
handler inherits `IdentityAddonHandler` (in `identity/addons/_handler.py`)
and implements one or more lifecycle hooks:

| Hook | Called by | Contract |
|------|-----------|----------|
| `on_identify(turn)` | phase dispatch (phase 1) | returns `List[Dict]` messages |
| `on_context(turn)`  | phase dispatch (phase 2) | returns `List[Dict]` messages |
| `on_history(turn)`  | phase dispatch (phase 3) | returns `List[Dict]` messages |
| `on_terminal(turn)` | phase dispatch (phase 4) | returns `List[Dict]` messages |
| `on_tool_pre(session, mechanics)`  | parietal_lobe before tool exec | returns `str` fizzle msg or `None` |
| `on_tool_post(session, mechanics, result)` | parietal_lobe after tool exec | side-effect only (no return) |

Handlers are stateless singletons — one instance per class, constructed once
at module import. If you need per-disc state, put it on the disc or session,
not the handler.

### Dispatch

Phase dispatch (`dispatch_phase` in `_handler_registry.py`) looks up the
handler by `IdentityAddon.addon_class_name`, then calls the lifecycle method
whose name matches `IdentityAddon.phase_id`
(`PHASE_METHOD = {1: 'on_identify', 2: 'on_context', 3: 'on_history', 4: 'on_terminal'}`).
The frontal_lobe dispatch loop is phase-agnostic — it just iterates the
disc's addon rows in phase order and calls `dispatch_phase` on each.

Tool lifecycle dispatch (`dispatch_tool_pre`, `dispatch_tool_post` in the
same file) iterates handlers attached to the disc. `on_tool_pre` is
**first-veto** — any non-None return fizzles the tool. `on_tool_post` is
**collect-all** — every handler sees every tool result.

### Three-branch fallback in `_build_turn_payload`

The frontal_lobe addon loop handles each `IdentityAddon` row by checking,
in order:

1. **Handler path (preferred):** `addon_class_name` populated and present in
   `HANDLER_REGISTRY` → call `dispatch_phase(addon, turn)`.
2. **Legacy function path (deprecated):** `function_slug` populated and
   present in `ADDON_REGISTRY` → call the function, append its messages.
3. **Native text path:** `description` populated → inject it as a single
   `role: system` message.

Once every row carries `addon_class_name`, branches 2 and 3 can be removed
along with `identity/addons/*_addon.py` and `addon_registry.py`. Until then
they stay on disk as a safety net for any row that wasn't migrated.

### Turn Assembly Order
1. Phase 1→2→3→4 addons execute in order, each appending messages.
2. `swarm_message_queue` messages are tagged with `<<h>>` prefix and appended.
3. `compile_system_messages()` hoists all system messages to index 0.

### The `<<h>>` Human Message Tagging System
**Problem solved:** the `Prompt` handler (Phase 4 TERMINAL) injects the task
prompt as a `role: user` message every turn. `RiverOfSix` (Phase 3 HISTORY)
replays previous turns' user messages from `request_payload`. Without
differentiation, the same prompt appeared twice from turn 2 onward.

**Solution:** human messages from `swarm_message_queue` get `<<h>>\n`
prepended to their content in `_build_turn_payload`. The `RiverOfSix`
handler's `_extract_user_messages()` only replays user messages that start
with `<<h>>`. Addon-injected user messages (Prompt, etc.) have no tag and
are skipped — the addon re-injects them fresh each turn.

**Constants:** `HUMAN_TAG = '<<h>>'` lives in `common/constants.py` and is
imported everywhere it's needed. `ROLE = 'role'` and `CONTENT = 'content'`
are defined in `frontal_lobe/frontal_lobe.py`.

### Focus Game — single source of truth

The `Focus` handler owns the Focus Game end-to-end:

- `on_context` — injects the per-turn Focus Pool prompt block.
- `on_tool_pre` — returns a fizzle message if `session.current_focus +
  mechanics.focus_modifier < 0` (and the cost is negative; synthesis tools
  always pass).
- `on_tool_post` — applies the Focus/XP delta. `result.focus_yield` /
  `result.xp_yield` attribute overrides on the raw tool_result object
  supersede the `mechanics.focus_modifier` / `mechanics.xp_reward` defaults.
  Clamps focus to `[0, max_focus]`; `total_xp` is unbounded.

If the disc has no `Focus` addon attached, the game is off — no pool block,
no fizzle, no ledger. The dispatcher simply doesn't invoke a handler that
isn't on the disc.

### River of Six (Phase 3 HISTORY)
`identity/addons/handlers/river_of_six.py` — sliding window of 6 turns with
age-based decay.

- **Reconstruction sources (atomic, non-duplicating):**
  - `response_payload` → assistant message
  - `ToolCall` DB records → tool call metadata + tool result messages
  - `request_payload` → only `<<h>>`-tagged user messages

- **Age-based decay (age = current_turn - past_turn):**
  - Age ≥ 4 (`EVICTION_THRESHOLD`): tool results evicted, `tool_calls` stripped from assistant msg
  - Age 3 (`EVICTION_WARNING_AGE`): eviction warning appended to tool results
  - Age 2 (`DECAY_WARNING_AGE`): decay warning appended to tool results

### Handler Class Reference
| Class | Phase | File |
|-------|-------|------|
| `Agile`         | 2 (CONTEXT)  | `identity/addons/handlers/agile.py` |
| `Deadline`      | 2 (CONTEXT)  | `identity/addons/handlers/deadline.py` |
| `Focus`         | 2 (CONTEXT) + tool pre/post | `identity/addons/handlers/focus.py` |
| `Hippocampus_`  | 2 (CONTEXT)  | `identity/addons/handlers/hippocampus.py` |
| `IdentityInfo`  | 1 (IDENTIFY) | `identity/addons/handlers/identity_info.py` |
| `NormalChat`    | 3 (HISTORY)  | `identity/addons/handlers/normal_chat.py` |
| `Prompt`        | 4 (TERMINAL) | `identity/addons/handlers/prompt.py` |
| `RiverOfSix`    | 3 (HISTORY)  | `identity/addons/handlers/river_of_six.py` |
| `Telemetry`     | 2 (CONTEXT)  | `identity/addons/handlers/telemetry.py` |
| `YourMove`      | 4 (TERMINAL) | `identity/addons/handlers/your_move.py` |

`Hippocampus_` has a trailing underscore to avoid colliding with the
`hippocampus.hippocampus.Hippocampus` service class it calls into.
`addon_class_name` on the fixture row matches the class name exactly.

Five native-text addons (The Focus Game rules ×2, Worker, PM, Are-Self
persona) intentionally have no class — they're pure description text and
flow through the branch-3 fallback above.

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
   signals. These are domain entities: `PFCEpic`, `IdentityDisc`, `ReasoningTurn`,
   `ReasoningTurnDigest`, `SpikeTrain`, `Engram`, `Iteration`. The frontend subscribes via
   `useDendrite('PFCEpic', null)`.

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

**Zero-agent dispatch:** `_dispatch_fleet_wave` and `_dispatch_first_responder` in
`central_nervous_system.py` succeed silently (`SpikeStatus.SUCCESS`, `logger.info`) when
the NerveTerminalRegistry is empty — the local server is not an agent, and zero targets
is a no-op, not an error. `_dispatch_pinned_wave` (SPECIFIC_TARGETS) is the exception:
pinned targets are explicit user intent and failure there is a real failure.

## Scipraxianism

The philosophy this project lives inside. When a design question touches *why*
something is free, local, or shaped the way it is, the answer usually traces back
here. **Twelve Variables, not three** — the three-variable version is the
kid-scale compression used in the curriculum only. Are-Self is Michael's solo
handiwork; the sister franchise Haunted Space Hotel
([hauntedspacehotel.com](https://hauntedspacehotel.com)) is a joint effort with
Andrew Piper and is deliberately kept off the scipraxian GitHub profile. Full
Claude-facing briefing: `are-self-documents/scipraxian/scipraxian-tldr.md`.
