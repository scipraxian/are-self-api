# Are-Self API — Features

What's built and working in the backend. Organized by brain region.

## Central Nervous System

Directed-graph execution engine. Neural Pathways define graphs of Neurons connected by Axons. Spike Trains traverse
pathways, creating Spikes that execute Effectors (native Python handlers or Celery tasks). Spikes carry a blackboard
(JSON dict) that accumulates context as the train passes through neurons. The CNS is generic — it doesn't know about
AI. It just fires graphs.

NeuroMuscularJunction handles spike dispatch with proper logging (bracketed component tags, `%s` formatting). N-way
spike log merge API with cursor-based delta updates for the forensics UI.

## Frontal Lobe

Reasoning session engine. `FrontalLobe.run()` executes a `while True` loop: assemble prompt → call LLM → parse tool
calls → dispatch to Parietal Lobe → record turn → repeat. Sessions break on `mcp_done` (terminal) or
`mcp_respond_to_user(yield_turn=True)` (pauses for human input).

Each turn records full telemetry: token counts, inference time, model used, tool calls. Focus economy gates session
length — novel memory formation grants focus back.

## Parietal Lobe

Tool execution gateway. `ParietalMCP` dynamically imports and calls MCP tool functions from `parietal_mcp/mcp_*.py`.
Hallucination armor validates tool names, parameter types, and required parameters before execution. Session and turn
IDs are injected automatically.

All MCP tools accept an optional `thought` parameter — logged but not consumed functionally. Forces local models to
reason inline with every action. Fixture `ToolParameterAssignment` records updated for all work tools.

## Hippocampus

Vector-embedded long-term memory. Engrams store facts as 768-dimensional vectors (nomic-embed-text via Ollama). 90%
cosine similarity dedup on save prevents the LLM from re-saving known facts. Full provenance chain: each engram links
to sessions, turns, spikes, and IdentityDiscs.

Auto-revectorization signal fires on description change and tag M2M change. Query param filtering on EngramViewSet
(`?identity_discs=`). Renamed from TalosEngram → Engram, TalosEngramTag → EngramTag, TalosHippocampus → Hippocampus
with RenameModel migration preserving DB compatibility.

## Hypothalamus

Model selection, routing, and catalog management.

**Catalog sync:** `sync_local` detects installed Ollama models (stores raw name as canonical, no `:latest` stripping).
`fetch_catalog` scrapes ollama.com/library via regex scraper. Both parse model strings once and pass results to the
enrichment pipeline.

**Semantic parser:** Standalone, Django-free, MIT-licensed module at
`hypothalamus/parsing_tools/llm_provider_parser/model_semantic_parser.py` (1121 lines, 98.4% accuracy, 83 tests).
Parses model identifier strings into family, parent family, creator, roles, quantizations, sizes. `FAMILY_PATTERNS`
uses 3-tuples with sub-family ordering. Sub-families with parent linkage: Qwen Coder→Qwen, CodeLlama→Llama,
Mixtral→Mistral, and more.

**Resolver:** `_enrich_from_parser(ai_model, parsed)` accepts a parse result dataclass. Uses `get_or_create` on all
reference tables (family, creator, version, roles, quantizations, tags). Wires `parent` FK on AIModelFamily. Batches
scalar saves. Ollama's `details.parameter_size` overrides parser's name-extracted value for precision.

**Routing engine:** `pick_optimal_model` with vector-similarity matching between IdentityDisc embeddings and model
catalog. Failover strategies with typed steps. Circuit breakers with scar tissue logic (cooldown increases with
repeated failures). Per-IdentityDisc budget constraints.

**API:** AIModelViewSet (pull, remove, toggle_enabled, sync_local, fetch_catalog), AIModelProviderViewSet
(reset_circuit_breaker, toggle_enabled), FailoverType/Strategy ViewSets, SelectionFilter ViewSet,
AIModelDescription ViewSet with full M2M CRUD. `current_description` resolves model-specific → family fallback.

**Fixtures:** 167-entry initial_data.json. 4 starter models with $0 pricing, 44 families with descriptions, 35
creators, 48 AIModelDescription records, full routing engine (3 strategies, 4 failover types, 8 steps, 3 selection
filters). Tiered catalog fixtures: ollama_popular.json (39 models), ollama_complete.json (74 models).

## Identity

Blueprint system for AI personas. Identities define system prompt templates (Django template syntax with runtime
variables), enabled tools (M2M to ToolDefinition), addon phases (IDENTIFY, CONTEXT, HISTORY, TERMINAL), and model
routing preferences via AIModelSelectionFilter.

Identities forge into IdentityDiscs — deployed instances with their own level, XP, success/failure record, and memory.
IdentityDiscs are vector-embedded (768-dim, nomic-embed-text) with auto-regeneration on prompt, type, tag, or addon
changes.

M2M write fix applied: PrimaryKeyRelatedField write-only counterparts for enabled_tools, addons, and tags on both
serializers. Budget system: 3 periods, 4 budgets in identity fixtures.

## Temporal Lobe

Iteration lifecycle management. Iteration Definitions are blueprints with shift columns (Sifting → Pre-Planning →
Planning → Executing → Post-Execution → Sleeping), each with turn limits. Incepting a definition creates a live
Iteration bound to an Environment. The temporal lobe advances through shifts as turn limits are reached.

ShiftViewSet (read-only reference data). Auto-populate definitions with all 6 shift types on create.
IterationShiftDefinition FK write fix applied.

## Synaptic Cleft

Real-time event bus on Django Channels (WebSocket). Typed neurotransmitter events: Dopamine (success), Cortisol
(errors), Acetylcholine (data sync), Glutamate (streaming), Norepinephrine (monitoring).

Norepinephrine neurotransmitter with celery_signals.py (in-process signal handlers for task_prerun, task_postrun,
worker_ready). NorepinephrineHandler with async/sync detection for log streaming.

## Peripheral Nervous System

Fleet management. CeleryWorkerViewSet with real-time worker status via Norepinephrine through the Synaptic Cleft.
CELERY_WORKER_SEND_TASK_EVENTS enabled. Celery Beat drives the tick cycle as the system heartbeat.

## Environments

Project context with CRUD. Context variables (key-value pairs) resolve in executable paths and templates via Django's
template engine. Single active environment at a time — switching changes what every view shows.

## Prefrontal Cortex

Task management. Epics → Stories → Tasks assigned to IdentityDiscs. The Frontal Lobe picks up tasks from the PFC
backlog when reasoning sessions start.

## Thalamus

Chat relay. Formats messages with `reasoning` and `text` parts for the Vercel AI SDK schema. Standing session support
via ThalamusChat. Message injection into active sessions via `swarm_message_queue`.

## Project Infrastructure

**Naming migration complete.** All `Talos`-prefixed classes, variables, and references renamed to Are-Self equivalents.
`TalosEngram` → `Engram`, `TalosEngramTag` → `EngramTag`, `TalosExecutable` → `Executable`, `talos_bin` path
references cleaned from fixtures. DB migration compatibility preserved with `db_table` Meta and RenameModel migrations.

**HTMX removed.** All HTMX-specific views, templates, and URL patterns cleaned out. The frontend is React consuming
DRF. Django is a pure API server.

**Install and launch scripts.** `are-self-install.bat` handles first-time setup end-to-end: venv creation, dependency
install, Docker startup, pgvector extension, migrations, fixture loading, superuser creation, Ollama install, and
embedding model pull. `are-self.bat` launches the full stack: Docker, Celery worker, Django server, and frontend dev
server.

Style guide established (STYLE_GUIDE.md). Google Python Style Guide baseline with Are-Self overrides: no nested
functions, no repeated string literals, constants on model classes, targeted error handling, verbose bracketed logging,
intentional async policy, established mixin hierarchy, real-database testing with fixtures.
