# Hermes-Agent → Talos Integration Roadmap

**Author:** Julianna (for Sam)
**Date:** 2026-04-03
**Status:** DRAFT — Requires validation decisions before implementation

---

## 1. Executive Summary

This document defines the integration path for absorbing hermes-agent's
functionality into Talos, making Talos the sole system for AI orchestration,
memory, tool execution, identity, automation, and platform integration within
JuliannaAI/ARETE.

**Current State:**
- **Hermes-agent** is a monolithic Python CLI agent (~440KB main file,
  ~90 source files) running conversation loops via OpenAI-compatible APIs.
  It handles memory (flat files), skills (SKILL.md files), tools (~35 tools),
  cron scheduling (JSON-based), platform integrations (14 platforms), identity
  (SOUL.md flat file), and context management (prompt assembly + compression).
- **Talos** is a Django 6.0 application (~75 concrete models across 17 apps)
  with PostgreSQL/pgvector, Redis, Celery, and Channels. It implements
  neuroanatomical concepts: CNS (graph orchestration), FrontalLobe (reasoning
  loops), Hippocampus (engram memory), ParietalLobe (MCP tools), Identity
  (IdentityDisc personas), Hypothalamus (model routing), TemporalLobe
  (scheduling), PrefrontalCortex (work assignment), and more.

**Key Insight:** These systems have a surprising amount of conceptual overlap
but radically different implementations. Talos is architecturally superior
(relational models, vector search, graph orchestration, budget management,
model routing) but Hermes has superior *operational breadth* (35 mature tools,
14 platform adapters, production-grade memory/skills, sub-agent delegation).

**Recommended Strategy:** Incremental absorption over 5 milestones (~12-16 weeks).
Build a Talos Gateway Adapter layer first, then migrate subsystems bottom-up:
Memory → Tools → Skills → Identity → Automation → Platforms.

**Critical Path:** The FrontalLobe reasoning loop must gain Hermes-equivalent
tool execution capability before any migration can be considered production-ready.

---

## 2. Current-State Architecture Comparison

### 2.1 Hermes-Agent Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    run_agent.py (8,723 lines)            │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  AIAgent     │  │ IterationBudget│ │PromptBuilder  │  │
│  │  (main loop) │  │ (turn limits)  │ │(system prompt)│  │
│  └──────┬───────┘  └──────────────┘  └───────────────┘  │
├─────────┼───────────────────────────────────────────────┤
│ TOOLS   │  registry.py → model_tools.py                  │
│  terminal_tool    memory_tool       skill_manager_tool   │
│  file_tools       web_tools         browser_tool         │
│  delegate_tool    cronjob_tools     vision_tools         │
│  tts_tool         image_gen_tool    honcho_tools         │
│  todo_tool        session_search    clarify_tool         │
│  code_execution   send_message      mcp_tool             │
├──────────────────────────────────────────────────────────┤
│ STATE   │  hermes_state.py (SessionDB - SQLite + FTS5)   │
│ MEMORY  │  MEMORY.md + USER.md (§-delimited flat files)  │
│ SKILLS  │  ~/.hermes/skills/**/ SKILL.md + scripts/      │
├──────────────────────────────────────────────────────────┤
│ GATEWAY │  gateway/run.py → gateway/platforms/            │
│  discord, telegram, signal, slack, whatsapp, email, SMS  │
│  matrix, mattermost, homeassistant, dingtalk, feishu     │
│  wecom, webhook, api_server                              │
├──────────────────────────────────────────────────────────┤
│ CRON    │  cron/scheduler.py + cron/jobs.py (JSON file)  │
├──────────────────────────────────────────────────────────┤
│ HONCHO  │  honcho_integration/ (cross-session memory)    │
└──────────────────────────────────────────────────────────┘
```

Key characteristics:
- **Monolithic:** Single AIAgent class with ~8,000 lines
- **Flat-file storage:** SQLite sessions, markdown memory, JSON cron jobs
- **Import-time registration:** Tools self-register via `registry.register()`
- **Frozen snapshots:** Memory/prompt captured at session start, immutable mid-session
- **Streaming-first:** All LLM calls support streaming with interrupt detection
- **Security-aware:** Injection scanning on memory/skills/context files
- **Multi-backend:** terminal tool supports local, docker, modal, ssh, singularity

### 2.2 Talos Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Django 6.0 + DRF + Channels          │
├──────────────────────────────────────────────────────────┤
│ ORCHESTRATION                                            │
│  central_nervous_system/ (CNS)                           │
│    NeuralPathway → Neuron → Axon (DAG graph)             │
│    SpikeTrain → Spike (runtime execution)                │
│    Celery dispatch: fire_spike.delay()                   │
├──────────────────────────────────────────────────────────┤
│ REASONING                                                │
│  frontal_lobe/ (FrontalLobe)                             │
│    ReasoningSession → ReasoningTurn → ToolCall           │
│    Addon system for prompt assembly                      │
│    Failover loop (max 8 attempts)                        │
│    SynapseClient (LiteLLM) for LLM calls                │
├──────────────────────────────────────────────────────────┤
│ MEMORY                                                   │
│  hippocampus/                                            │
│    Engram (name, description, vector[768], tags)          │
│    pgvector cosine similarity dedup (≥0.90)              │
│    OllamaClient embed (nomic-embed-text)                 │
├──────────────────────────────────────────────────────────┤
│ TOOLS                                                    │
│  parietal_lobe/                                          │
│    ToolDefinition → ToolParameter → ToolCall             │
│    parietal_mcp/ (MCP tool implementations)              │
│    Focus/XP gamification system                          │
├──────────────────────────────────────────────────────────┤
│ IDENTITY                                                 │
│  identity/                                               │
│    Identity (template) → IdentityDisc (runtime instance) │
│    Addons (phase-based prompt injection)                  │
│    IdentityBudget → BudgetPeriod (financial limits)      │
│    IdentityDiscVector (768-dim embedding)                │
├──────────────────────────────────────────────────────────┤
│ MODEL ROUTING                                            │
│  hypothalamus/                                           │
│    AIModel → AIModelProvider → AIModelPricing            │
│    Selection filters + failover strategies               │
│    LiteLLM catalog sync + vector-based matching          │
│    Circuit breaker per provider                          │
├──────────────────────────────────────────────────────────┤
│ SCHEDULING                                               │
│  temporal_lobe/                                          │
│    IterationDefinition → Shift → Iteration               │
│    tick() metronome + ghost cleanup                      │
│    Ouroboros Protocol (auto-restart iterations)           │
├──────────────────────────────────────────────────────────┤
│ WORK MANAGEMENT                                          │
│  prefrontal_cortex/                                      │
│    PFCEpic → PFCStory → PFCTask (agile hierarchy)       │
│    Dispatch per shift type (sifting/planning/executing)   │
├──────────────────────────────────────────────────────────┤
│ I/O & INFRA                                              │
│  peripheral_nervous_system/ (remote agent management)    │
│  synaptic_cleft/ (WebSocket messaging via Channels)      │
│  thalamus/ (sensory relay, Stimulus objects)             │
│  occipital_lobe/ (log parsing, error extraction)         │
│  environments/ (project config, executables)             │
│  dashboard/ (UI)                                         │
├──────────────────────────────────────────────────────────┤
│ INFRA: PostgreSQL/pgvector · Redis · Celery · Daphne     │
└──────────────────────────────────────────────────────────┘
```

Key characteristics:
- **Distributed:** Celery workers, WebSocket channels, remote NerveTerminals
- **Database-first:** 75+ models with full relational integrity
- **Graph-based orchestration:** DAG execution with typed edges (flow/success/failure)
- **Multi-agent:** IdentityDisc instances represent individual AI workers
- **Financial tracking:** Per-request cost tracking with budget enforcement
- **Gamified:** Focus/XP system on tool usage
- **Vector-native:** pgvector embeddings on Engrams, Models, and IdentityDiscs

---

## 3. Feature Mapping: Hermes → Talos

### 3.1 Direct Equivalents (Talos already has the concept)

| Hermes Subsystem | Talos Equivalent | Gap Assessment |
|---|---|---|
| AIAgent.run_conversation() | FrontalLobe.run() | Talos lacks streaming, context compression, interrupt. Hermes lacks graph orchestration. |
| MemoryStore (MEMORY.md/USER.md) | Hippocampus (Engram model) | Talos is superior (vector search, relational, dedup). Hermes has simpler frozen-snapshot pattern. |
| SessionDB (SQLite + FTS5) | ReasoningSession/Turn models | Talos has richer model. Hermes has FTS5 cross-session search. |
| ToolRegistry + handle_function_call | ParietalLobe + parietal_mcp/ | Talos has DB-defined tool schemas. Hermes has 35+ mature tool implementations vs Talos's ~20 MCP tools. |
| Toolsets (named groups) | IdentityDisc.enabled_tools (M2M) | Equivalent concept, different mechanism. Talos is per-identity; Hermes is per-session. |
| SOUL.md / default_soul.py | Identity + IdentityDisc + Addons | Talos is far superior (templates, addons, phases, vectors, budgets). Hermes is a flat file. |
| cron/scheduler + jobs | TemporalLobe (Iterations/Shifts) | Very different models. Hermes = simple cron. Talos = multi-phase iteration cycles with participants. |
| agent/prompt_builder.py | identity/identity_prompt.py + addons | Talos addon system is more modular. Hermes prompt builder has more operational content (memory, skills, platform hints). |
| Credential pool + fallback models | Hypothalamus (pick_optimal_model) | Talos is far superior (catalog, pricing, failover strategies, vector matching, circuit breakers). |
| ContextCompressor | (none) | **Gap.** Talos has no context window pressure management. |
| delegate_tool (sub-agents) | CNS graph + _spawn_subgraph | Different paradigms. Hermes: ad-hoc child agents. Talos: pre-defined graph with delegation edges. |
| trajectory_compressor | (none) | **Gap.** RL training data specific — may not need migration. |

### 3.2 Hermes Features with No Talos Equivalent

| Hermes Feature | Description | Migration Path |
|---|---|---|
| **Gateway (14 platforms)** | Discord, Telegram, Signal, Slack, WhatsApp, Email, SMS, Matrix, Mattermost, Home Assistant, DingTalk, Feishu, WeCom, Webhook | New Talos app or wrapped integration layer |
| **Skills system** | SKILL.md + scripts/ + templates/ + references/ | Re-express as Engrams + NeuralPathway templates, or new SkillEngram model |
| **Code execution tool** | Sandboxed Python execution with hermes_tools imports | New parietal_mcp tool |
| **Browser tool** | Playwright/Camoufox with accessibility tree snapshots | New parietal_mcp tool |
| **Streaming responses** | Real-time token-by-token output | Extend SynapseClient + WebSocket delivery |
| **Context references** | @file:, @url:, @diff, @staged, @git:N in user messages | New thalamus pre-processor |
| **Honcho integration** | Cross-session user modeling via external service | hippocampus_addon or new addon |
| **Clarify tool** | Ask user mid-conversation for clarification | WebSocket interaction pattern in FrontalLobe |
| **Todo tool** | In-session task list management | Lightweight PFC integration or session-scoped model |
| **Send message tool** | Cross-platform message delivery | PNS + gateway integration |
| **Image generation** | FLUX 2 Pro via API | New parietal_mcp tool |
| **TTS/Voice** | Text-to-speech with provider abstraction | New parietal_mcp tool |
| **Vision analysis** | Multi-provider image analysis | New parietal_mcp tool |
| **Fuzzy file patching** | 9-strategy fuzzy match for file edits | Port to parietal_mcp/mcp_fs_patch |
| **Process registry** | Background process management | Extend PNS NerveTerminal concept |
| **Interrupt mechanism** | Cancel running agent mid-conversation | Extend CNS stop_gracefully to FrontalLobe |
| **Prompt caching** | Anthropic cache_control breakpoints | Extend SynapseClient |
| **Security scanning** | Injection detection on memory/context | New middleware layer |

### 3.3 Talos Features with No Hermes Equivalent

| Talos Feature | Description | Impact on Migration |
|---|---|---|
| **DAG graph orchestration** | NeuralPathway + Neurons + Axons | Core Talos advantage — keep and extend |
| **Financial tracking** | AIModelPricing + UsageRecords + Budgets | Keep — Hermes has usage_pricing but far less sophisticated |
| **Focus/XP gamification** | Tool cost/reward system | Keep — unique Talos innovation |
| **Multi-agent shifts** | IterationShiftParticipant scheduling | Keep — extends beyond simple cron |
| **Agile work management** | PFC Epics/Stories/Tasks | Keep — no Hermes equivalent |
| **Model catalog sync** | LiteLLM + OpenRouter ETL | Keep — Hermes relies on manual config |
| **Vector-based model routing** | Cosine similarity for model selection | Keep — Hermes has no equivalent |
| **NerveTerminal fleet** | Remote agent registry + telemetry | Keep — enables distributed execution |
| **Scar tissue logic** | Auto-disable capabilities on 404 | Keep — resilience feature |

---

## 4. Recommended Target Architecture

### 4.1 Target State

```
┌──────────────────────────────────────────────────────────────┐
│                      TALOS (Unified System)                   │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ GATEWAY LAYER (New: talos_gateway/)                      │ │
│  │  Platform adapters: Discord, Telegram, CLI, etc.         │ │
│  │  Session management, streaming, interrupt                │ │
│  │  Replaces: hermes gateway/ entirely                      │ │
│  └────────────────────────┬────────────────────────────────┘ │
│                           │                                   │
│  ┌────────────────────────▼────────────────────────────────┐ │
│  │ THALAMUS (Extended)                                      │ │
│  │  Stimulus routing + context references (@file:, @url:)   │ │
│  │  Security scanning layer                                 │ │
│  │  Pre-processing pipeline                                 │ │
│  └────────────────────────┬────────────────────────────────┘ │
│                           │                                   │
│  ┌────────────────────────▼────────────────────────────────┐ │
│  │ CNS (Unchanged)                                          │ │
│  │  Graph orchestration (NeuralPathway/Neuron/Axon)         │ │
│  │  SpikeTrain/Spike execution                              │ │
│  └────────────────────────┬────────────────────────────────┘ │
│                           │                                   │
│  ┌────────────────────────▼────────────────────────────────┐ │
│  │ FRONTAL LOBE (Extended)                                  │ │
│  │  Reasoning loop + context compression                    │ │
│  │  Streaming support via Channels                          │ │
│  │  Interrupt mechanism via Spike status                    │ │
│  │  Prompt caching (Anthropic cache_control)                │ │
│  └─────┬──────────────┬───────────────┬────────────────────┘ │
│         │              │               │                      │
│  ┌──────▼──────┐ ┌────▼─────┐  ┌─────▼──────────────────┐  │
│  │ HIPPOCAMPUS │ │HYPOTHAL. │  │ PARIETAL LOBE          │  │
│  │ (Extended)  │ │(Unchanged│  │ (Extended)              │  │
│  │ +Hermes mem │ │ mostly)  │  │ +35 Hermes tools       │  │
│  │ +Skills as  │ │          │  │ +code execution         │  │
│  │  Engrams    │ │          │  │ +browser                │  │
│  │ +Session    │ │          │  │ +delegation (child CNS) │  │
│  │  search     │ │          │  │ +streaming results      │  │
│  └─────────────┘ └──────────┘  └────────────────────────┘  │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ IDENTITY (Extended)                                      │ │
│  │  Full Hermes persona (SOUL.md) as IdentityDisc fields   │ │
│  │  Platform hints as addons                                │ │
│  │  Memory/Skills guidance as addons                        │ │
│  │  Honcho integration as addon                             │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ TEMPORAL LOBE (Extended)                                 │ │
│  │  Existing iteration/shift system                         │ │
│  │  + Simple cron-style scheduling (absorbed from Hermes)   │ │
│  │  + Time-triggered Spike dispatch                         │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ PERIPHERAL NERVOUS SYSTEM (Extended)                     │ │
│  │  NerveTerminal fleet + process registry                  │ │
│  │  Multi-backend terminal (local/docker/ssh/modal)         │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  INFRA: PostgreSQL/pgvector · Redis · Celery · Daphne/ASGI  │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Design Principles for Unification

1. **Database is truth.** All state moves from flat files to PostgreSQL models.
   No more MEMORY.md, jobs.json, or SQLite session stores.

2. **Tools are registered in DB, implemented in parietal_mcp/.** Each Hermes
   tool becomes a parietal_mcp module with a corresponding ToolDefinition row.

3. **Skills become Engram-based procedural knowledge.** A new `EngramType` or
   specialized model links engrams to execution templates (replacing SKILL.md).

4. **Identity is fully modeled.** SOUL.md content becomes IdentityDisc fields
   and addons. Platform hints become addons.

5. **Gateway adapters are thin.** They translate platform events into Thalamus
   Stimulus objects, which the existing pipeline processes.

6. **Streaming via Channels.** WebSocket consumers deliver token-by-token
   output from FrontalLobe through the gateway to platform adapters.

---

## 5. Migration Strategy

### 5.1 Per-Subsystem Recommendation

| Hermes Subsystem | Strategy | Rationale |
|---|---|---|
| **Memory (MEMORY.md/USER.md)** | REPLACE with Hippocampus Engrams | Talos Engram model is superior. Map § entries to individual Engrams with a "memory" tag. |
| **Session storage (SQLite)** | REPLACE with ReasoningSession/Turn | Direct model mapping. Add FTS capabilities via PostgreSQL full-text search. |
| **Tool registry** | REPLACE with ParietalLobe ToolDefinition | DB-defined schemas are better. Tool implementations migrate to parietal_mcp/. |
| **Tool implementations** | ADAPT — port each tool to parietal_mcp module | ~35 tools need individual porting. Some already have Talos equivalents. |
| **Skills system** | REPLACE with new SkillEngram concept | Skills become tagged Engrams with attached file references. Execution logic moves to parietal_mcp. |
| **Identity (SOUL.md)** | REPLACE with IdentityDisc | Map SOUL.md content to system_prompt_template + addons. Hermes persona fields become identity configuration. |
| **Prompt builder** | REPLACE with Identity addon pipeline | Each prompt section becomes an addon function. |
| **Context compression** | ADAPT into FrontalLobe | New service class consumed by FrontalLobe._execute_turn(). |
| **Cron scheduler** | ADAPT into TemporalLobe | Add simple time-trigger model alongside existing iteration system. |
| **Gateway** | SHIM then REPLACE | Initially wrap Hermes adapters with Talos API calls. Later rewrite as native Talos app. |
| **Honcho integration** | ADAPT as Identity addon | New hippocampus_honcho_addon function in addon_registry. |
| **Delegate tool** | REPLACE with CNS subgraph | Map delegation to programmatic NeuralPathway creation + SpikeTrain launch. |
| **Context references** | ADAPT into Thalamus | New Stimulus pre-processor for @-references. |
| **Streaming** | BUILD NEW in FrontalLobe | Extend SynapseClient + Channels consumer. |
| **Process registry** | ADAPT into PNS | Background processes tracked via NerveTerminal-like records. |
| **Code execution** | PORT to parietal_mcp | New mcp_code_execution module. |
| **Browser tool** | PORT to parietal_mcp | New mcp_browser module. |
| **Batch runner / RL** | DEPRECATE | Hermes-specific. Not needed in Talos unless RL training is required. |
| **ACP adapter** | DEPRECATE | Protocol-specific to Hermes ecosystem. |

### 5.2 Sequencing Constraints (Dependency Graph)

```
FOUNDATION (must be first):
  [M1] Tool system unification
    ├── parietal_mcp tool ports (terminal, file ops, web, memory)
    └── ToolDefinition fixtures for all ported tools
           │
           ▼
  [M2] Memory system unification
    ├── Hermes memory → Engram migration
    ├── Session search via PostgreSQL FTS
    └── Skills → SkillEngram model
           │
           ▼
  [M3] Identity + Prompt unification
    ├── SOUL.md → IdentityDisc migration
    ├── Prompt builder sections → Addons
    ├── Context compression in FrontalLobe
    └── Streaming support
           │
           ▼
  [M4] Automation + Gateway
    ├── Cron → TemporalLobe time triggers
    ├── Gateway adapter framework
    └── Platform-specific adapters (Discord, Telegram)
           │
           ▼
  [M5] Full cutover
    ├── Hermes wrapper pointing to Talos backend
    ├── Data migration tooling
    └── Deprecation of Hermes standalone
```

---

## 6. Milestones / Epics

### Milestone 1: Tool System Unification (Weeks 1-3)
**Goal:** Talos ParietalLobe can execute all critical Hermes tools.
**Success Criteria:** FrontalLobe reasoning session can run terminal commands,
read/write files, search files, make web requests, and manage memory — all
through parietal_mcp modules backed by ToolDefinition DB rows.

### Milestone 2: Memory & Knowledge Unification (Weeks 3-5)
**Goal:** All persistent memory lives in Hippocampus Engrams. Skills are
queryable procedural knowledge units.
**Success Criteria:** No flat-file memory storage. Session search works via
PostgreSQL. Skills loadable as Engram-backed knowledge.

### Milestone 3: Identity & Reasoning Unification (Weeks 5-8)
**Goal:** Talos IdentityDisc fully replaces Hermes SOUL.md and prompt builder.
FrontalLobe supports streaming, context compression, and interrupt.
**Success Criteria:** Full conversational reasoning session with Julianna
persona, streaming output, and context window management — all via Talos.

### Milestone 4: Automation & Gateway (Weeks 8-12)
**Goal:** Talos can run scheduled jobs and accept messages from Discord/Telegram.
**Success Criteria:** Cron-equivalent scheduling via TemporalLobe. At least
Discord + CLI gateway adapters operational.

### Milestone 5: Full Cutover & Deprecation (Weeks 12-16)
**Goal:** Hermes CLI becomes a thin client to Talos backend. All data migrated.
**Success Criteria:** `hermes` CLI command routes through Talos APIs. Hermes
standalone is deprecated.

---

## 7. Issue Breakdown Per Milestone

### Milestone 1: Tool System Unification

**Epic 1.1: Core Tool Porting**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 1.1.1 | P0-Critical | Medium | **Port terminal_tool to parietal_mcp/mcp_terminal.py** — Multi-backend (local/docker/ssh) terminal execution with background process support, dangerous command detection, sudo handling. Port from hermes tools/terminal_tool.py (1,358 lines) + tools/environments/*.py. |
| 1.1.2 | P0-Critical | Low | **Port file_tools to parietal_mcp/mcp_fs.py** — Already partially exists (mcp_fs_read, mcp_fs_patch, mcp_fs_list, mcp_fs_grep). Add write_file, fuzzy match patch (9 strategies from tools/fuzzy_match.py). |
| 1.1.3 | P0-Critical | Low | **Port web_tools to parietal_mcp/mcp_web.py** — Web search (Tavily/SearXNG) + web extract (URL to markdown). Port from tools/web_tools.py. |
| 1.1.4 | P1-High | Medium | **Port code_execution_tool to parietal_mcp/mcp_code_exec.py** — Sandboxed Python execution with hermes_tools-equivalent imports. Must handle 5-minute timeout, 50KB stdout cap, 50 tool call limit per script. |
| 1.1.5 | P1-High | High | **Port browser_tool to parietal_mcp/mcp_browser.py** — Playwright/Camoufox with accessibility tree snapshots, navigation, click, type, scroll, vision screenshot. Port from tools/browser_tool.py + browser_camofox.py + browser_providers/. |
| 1.1.6 | P1-High | Low | **Port vision_tools to parietal_mcp/mcp_vision.py** — Multi-provider image analysis. Port from tools/vision_tools.py. |
| 1.1.7 | P2-Medium | Low | **Port image_generation_tool to parietal_mcp/mcp_image_gen.py** — FLUX 2 Pro generation. |
| 1.1.8 | P2-Medium | Low | **Port tts_tool to parietal_mcp/mcp_tts.py** — Text-to-speech with provider abstraction. |
| 1.1.9 | P2-Medium | Low | **Port search_files to enhance mcp_fs_grep.py** — Ensure ripgrep-backed content and file-name search parity. |

**Epic 1.2: Tool Registration Infrastructure**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 1.2.1 | P0-Critical | Medium | **Create ToolDefinition fixtures for all ported tools** — Django fixture file with ToolDefinition, ToolParameter, ToolParameterAssignment rows matching Hermes tool schemas. |
| 1.2.2 | P1-High | Medium | **Implement parallel tool execution in ParietalLobe** — Hermes parallelizes read-only tools (up to 8 workers). ParietalLobe.process_tool_calls() needs ThreadPoolExecutor with safety classification. |
| 1.2.3 | P1-High | Low | **Add tool result size limits** — Hermes truncates tool results at various thresholds. ParietalLobe needs equivalent guardrails. |
| 1.2.4 | P2-Medium | Low | **Tool availability checks** — Hermes tools have check_fn() that validates runtime availability. Add equivalent to ToolDefinition or ParietalLobe. |

**Epic 1.3: Delegation via CNS**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 1.3.1 | P1-High | High | **Implement dynamic NeuralPathway creation for delegation** — When FrontalLobe needs to delegate, programmatically create a NeuralPathway + Neuron + SpikeTrain, analogous to Hermes delegate_tool child agent spawning. |
| 1.3.2 | P2-Medium | Medium | **Implement delegation depth limits** — Hermes has MAX_DEPTH=2. Add equivalent in CNS _spawn_subgraph. |
| 1.3.3 | P2-Medium | Medium | **Implement concurrent delegation limits** — Hermes has MAX_CONCURRENT_CHILDREN=3. Add to SpikeTrain tracking. |

### Milestone 2: Memory & Knowledge Unification

**Epic 2.1: Memory Migration**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 2.1.1 | P0-Critical | Medium | **Implement Hermes-style memory tool via Engrams** — New parietal_mcp/mcp_memory.py that maps add/replace/remove operations to Engram CRUD. Two tagged collections: "agent_memory" and "user_profile". Character limits enforced. |
| 2.1.2 | P0-Critical | Medium | **Implement memory snapshot injection** — Hermes freezes memory at session start and injects into system prompt. Implement as hippocampus_addon or extend existing hippocampus_addon.py. |
| 2.1.3 | P1-High | Low | **MEMORY.md → Engram migration script** — Parse §-delimited entries from MEMORY.md and USER.md, create Engrams with appropriate tags and vectors. |
| 2.1.4 | P1-High | Medium | **Session search via PostgreSQL** — Replace SQLite FTS5 with PostgreSQL full-text search across ReasoningSession + ReasoningTurn history. New parietal_mcp/mcp_session_search.py. |

**Epic 2.2: Skills as Engrams**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 2.2.1 | P0-Critical | High | **Design SkillEngram model** — New model (or Engram subtype) that represents procedural knowledge: YAML frontmatter fields (name, description, trigger), markdown body, linked files (scripts/, templates/, references/). Needs vector embedding for semantic skill matching. |
| 2.2.2 | P1-High | Medium | **Implement skill CRUD via parietal_mcp** — New mcp_skill_manage.py with create/patch/edit/delete/write_file/remove_file operations. Validates YAML frontmatter, enforces size limits. |
| 2.2.3 | P1-High | Medium | **Implement skill index for system prompt** — Build compact skill catalog (name + description) for injection into system prompt, equivalent to Hermes build_skills_system_prompt(). |
| 2.2.4 | P1-High | Low | **Skill migration script** — Walk ~/.hermes/skills/, parse each SKILL.md + supporting files, create SkillEngram records with vectors. |
| 2.2.5 | P2-Medium | Low | **Implement skill view tool** — parietal_mcp/mcp_skill_view.py for loading skill content and linked files at runtime. |

### Milestone 3: Identity & Reasoning Unification

**Epic 3.1: Identity Migration**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 3.1.1 | P0-Critical | Medium | **Map SOUL.md to IdentityDisc** — Parse SOUL.md content into system_prompt_template field. Create Julianna IdentityDisc with correct identity_type, addons, enabled_tools, selection_filter. |
| 3.1.2 | P0-Critical | Medium | **Create platform hint addons** — For each platform (CLI, Discord, Telegram, etc.), create an IdentityAddon that injects Hermes PLATFORM_HINTS content. Phase: CONTEXT. |
| 3.1.3 | P1-High | Medium | **Create memory guidance addon** — Addon that injects MEMORY_GUIDANCE + SESSION_SEARCH_GUIDANCE. Phase: CONTEXT. |
| 3.1.4 | P1-High | Medium | **Create skills guidance addon** — Addon that injects SKILLS_GUIDANCE + skill index. Phase: CONTEXT. |
| 3.1.5 | P1-High | Low | **Create tool enforcement addon** — For GPT/Codex models, inject TOOL_USE_ENFORCEMENT_GUIDANCE. Phase: TERMINAL. |

**Epic 3.2: FrontalLobe Enhancements**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 3.2.1 | P0-Critical | High | **Add context compression to FrontalLobe** — Port Hermes ContextCompressor logic: detect token pressure, prune old tool results, LLM-powered middle summarization. Integrate into _execute_turn() flow. |
| 3.2.2 | P0-Critical | High | **Add streaming support to FrontalLobe** — Extend SynapseClient to support LiteLLM streaming. Deliver tokens via Django Channels WebSocket consumer. |
| 3.2.3 | P1-High | Medium | **Add interrupt mechanism to FrontalLobe** — Check Spike.status for STOPPING between turns and between streaming chunks. Graceful conversation termination. |
| 3.2.4 | P1-High | Medium | **Add prompt caching (Anthropic)** — Extend SynapseClient._build_kwargs() to inject cache_control breakpoints on system prompt for Anthropic providers. |
| 3.2.5 | P2-Medium | Medium | **Add iteration budget to FrontalLobe** — Port Hermes IterationBudget concept (max turns with progressive warnings). Currently Talos has max_turns on ReasoningSession but no progressive pressure. |

**Epic 3.3: Context Reference System**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 3.3.1 | P1-High | Medium | **Implement @-reference pre-processor in Thalamus** — Parse @file:, @url:, @diff, @staged, @git:N patterns from user messages. Expand into context blocks before FrontalLobe processes them. |
| 3.3.2 | P2-Medium | Low | **Token budget for context references** — Enforce 50% hard limit, 25% soft warning on expanded reference content. |

### Milestone 4: Automation & Gateway

**Epic 4.1: Scheduling Extension**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 4.1.1 | P0-Critical | Medium | **Add CronSchedule model to TemporalLobe** — New model for simple time-triggered jobs: cron expression, one-shot timestamp, interval. Links to NeuralPathway or direct Spike dispatch. |
| 4.1.2 | P1-High | Medium | **Implement cron tick via Celery Beat** — Periodic task that evaluates CronSchedule records and fires SpikeTrain for due jobs. |
| 4.1.3 | P1-High | Low | **Migrate Hermes cron jobs** — Parse ~/.hermes/cron/jobs.json, create CronSchedule records. |
| 4.1.4 | P2-Medium | Low | **Implement [SILENT] suppression** — Cron jobs that return [SILENT] suppress delivery. |

**Epic 4.2: Gateway Framework**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 4.2.1 | P0-Critical | High | **Create talos_gateway Django app** — New app with: BasePlatformAdapter (abstract), GatewaySession model, message routing, delivery pipeline. Modeled after Hermes gateway/ but using Django Channels. |
| 4.2.2 | P0-Critical | High | **Port Discord adapter** — Translate Hermes gateway/platforms/discord.py to Talos gateway framework. Maintain feature parity: threads, DMs, voice, media. |
| 4.2.3 | P1-High | High | **Port Telegram adapter** — Translate Hermes gateway/platforms/telegram.py. |
| 4.2.4 | P1-High | Medium | **Implement CLI adapter** — Local terminal interface for Talos, equivalent to hermes CLI mode. |
| 4.2.5 | P2-Medium | Medium | **Port remaining adapters** — Signal, Slack, WhatsApp, Email, etc. as needed. |

**Epic 4.3: Gateway Infrastructure**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 4.3.1 | P1-High | Medium | **Session management in gateway** — Agent cache (preserve FrontalLobe state per session), conversation history from ReasoningSession/Turn models. |
| 4.3.2 | P1-High | Medium | **Delivery pipeline** — Route FrontalLobe output through appropriate platform adapter. Handle MEDIA: tags for file attachments. |
| 4.3.3 | P2-Medium | Medium | **Dangerous command approval** — Interactive approval flow for terminal commands via gateway (currently Hermes uses tools/approval.py). |

### Milestone 5: Full Cutover

**Epic 5.1: Hermes CLI Wrapper**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 5.1.1 | P0-Critical | Medium | **Create Talos CLI entry point** — Management command or standalone script that provides Hermes-equivalent CLI experience backed by Talos APIs. |
| 5.1.2 | P1-High | Medium | **Implement config migration** — Map Hermes config.yaml to Talos Django settings + environment models. |

**Epic 5.2: Data Migration**

| Issue | Priority | Complexity | Description |
|---|---|---|---|
| 5.2.1 | P1-High | Medium | **Full session history migration** — SQLite SessionDB → ReasoningSession/Turn/ToolCall models. |
| 5.2.2 | P1-High | Low | **Verify all tool parity** — Automated test suite confirming each Hermes tool has a working Talos equivalent. |
| 5.2.3 | P2-Medium | Low | **Deprecation documentation** — Document what was deprecated and why. |

---

## 8. Risks, Blockers, and Open Questions

### 8.1 Major Architectural Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Monolith decomposition complexity** | HIGH | run_agent.py is 8,723 lines with deep internal coupling. Many behaviors are side effects within the main loop. Extracting them cleanly for Talos integration requires careful interface design. Mitigation: Port behavior-by-behavior, not line-by-line. |
| **Streaming architecture mismatch** | HIGH | Hermes uses synchronous streaming with interrupt checking. Talos uses async Celery workers + Channels. Achieving the same real-time responsiveness requires WebSocket infrastructure that doesn't currently exist in FrontalLobe. Mitigation: Prototype streaming early in M3. |
| **Tool execution environment differences** | MEDIUM | Hermes tools run in-process with direct filesystem access. Talos tools run inside Celery workers which may have different filesystem views, especially in distributed setups. Mitigation: Ensure tool environment parity in development before tackling distributed. |
| **Context compression timing** | MEDIUM | Hermes compresses mid-conversation synchronously. Talos FrontalLobe persists each turn to DB. Compression needs to modify persisted conversation history, which is more complex than in-memory modification. Mitigation: Design compression as a DB-level operation early. |
| **Skills model design risk** | MEDIUM | Skills are complex (YAML + markdown + scripts + templates). No existing Talos model handles this. The SkillEngram design must be validated before implementation. Mitigation: Design doc review before coding. |
| **Gateway platform state management** | MEDIUM | Hermes gateway maintains long-lived agent instances per session. Talos workers are stateless Celery tasks. Bridging this gap requires a session cache layer. Mitigation: Redis-backed session store. |

### 8.2 Open Design Questions (Require Validation)

| Question | Options | Recommendation |
|---|---|---|
| **How should Skills be modeled?** | (A) New SkillEngram model with file attachments, (B) Tagged Engrams with JSON metadata, (C) New Django app `skill_library/` | **(A) New SkillEngram model** — Skills have unique structure (YAML frontmatter, execution templates) that doesn't map cleanly to generic Engrams. A dedicated model preserves type safety. |
| **Should the Gateway be a Django app or standalone?** | (A) Django app within Talos, (B) Separate service calling Talos APIs, (C) Embedded in Talos process via Channels | **(C) Embedded via Channels** — Keeps everything in one deployment unit, leverages Daphne ASGI for WebSockets, avoids network overhead. Platform adapters register as Channels consumers. |
| **How should streaming work?** | (A) SynapseClient streams → Channels group → gateway → platform, (B) FrontalLobe polls SynapseClient → pushes via Channels, (C) Direct WebSocket from SynapseClient to client | **(A) SynapseClient → Channels** — Cleanest separation. SynapseClient gets a `stream_callback` parameter. FrontalLobe passes a callback that sends to a Channels group. Gateway consumers in that group forward to platform adapters. |
| **What about the CLI experience?** | (A) Keep hermes CLI calling Talos via HTTP, (B) Build native Talos management commands, (C) Build a new standalone CLI that connects via WebSocket | **(C) WebSocket CLI client** — Provides real-time streaming experience equivalent to current Hermes CLI. Can be a lightweight Python script connecting to Talos Daphne. |
| **Where does Honcho integration live?** | (A) hippocampus_addon, (B) identity addon, (C) new app honcho_integration/ | **(B) identity addon** — Honcho provides cross-session context about the user and AI peer. This naturally fits as an addon in the CONTEXT phase, injecting Honcho-retrieved context into the system prompt. |
| **How to handle tool execution in non-Celery contexts?** | (A) Always use Celery, (B) Sync fallback for CLI, (C) Separate execution mode | **(B) Sync fallback** — For CLI/interactive use, tools should execute synchronously in the request thread. For CNS graph execution, use Celery. FrontalLobe needs a configurable execution mode. |

### 8.3 Blockers

| Blocker | Impact | Resolution Path |
|---|---|---|
| **Ollama dependency for embeddings** | Hippocampus requires local Ollama for nomic-embed-text. If Talos runs on a server without Ollama, embedding generation fails. | Add fallback embedding provider (OpenAI/Cohere API) to Hippocampus, similar to how Hypothalamus handles multi-provider. |
| **PostgreSQL pgvector dependency** | Skills/Memory search relies on vector similarity. Dev environment must have pgvector extension. | Already present in Talos. Non-issue for this migration. |
| **LiteLLM catalog sync** | Hypothalamus sync_catalog() depends on external LiteLLM data. Outages block model routing. | Already handled by Talos with cached catalog. Non-issue. |

---

## 9. Recommended First Implementation Steps

### Week 1: Foundation Sprint

**Day 1-2: Tool Porting Setup**
1. Create skeleton parietal_mcp modules for the 5 highest-priority tools:
   - mcp_terminal.py (from terminal_tool.py)
   - mcp_web.py (from web_tools.py)
   - mcp_memory.py (new, mapping to Hippocampus)
   - mcp_code_exec.py (from code_execution_tool.py)
   - mcp_vision.py (from vision_tools.py)
2. Create ToolDefinition fixtures matching Hermes schemas
3. Write integration test: FrontalLobe can discover and call each tool

**Day 3-4: Terminal Tool Port**
1. Port tools/terminal_tool.py → parietal_mcp/mcp_terminal.py
2. Port tools/environments/local.py (local backend only — defer docker/ssh)
3. Port tools/process_registry.py (background process management)
4. Port dangerous command detection and approval flow

**Day 5: File Operations Parity**
1. Enhance existing mcp_fs_read.py with line-numbered output format
2. Port tools/fuzzy_match.py and enhance mcp_fs_patch.py
3. Add write_file capability (mcp_fs_write.py or extend mcp_fs.py)
4. Ensure search_files parity with ripgrep-backed search

### Week 2: Memory + Web + Testing

**Day 6-7: Memory Tool**
1. Implement mcp_memory.py with add/replace/remove operations
2. Map to Hippocampus Engram model with "agent_memory" and "user_profile" tags
3. Implement character limits, §-delimiter compatibility
4. Write memory snapshot addon for system prompt injection

**Day 8-9: Web Tools + Code Execution**
1. Port web search and web extract
2. Port code execution with sandboxing
3. Test FrontalLobe can chain: search → read → edit → verify

**Day 10: Integration Testing**
1. End-to-end test: User message → FrontalLobe → tool calls → response
2. Verify tool execution parity with Hermes for common workflows
3. Document any behavioral differences

### Week 3: Stabilization + Skills Design

**Day 11-12: Browser Tool Port**
1. Port browser tool (complex, high LOC)
2. Test with real web interactions

**Day 13-14: Skills Model Design**
1. Draft SkillEngram model design document
2. Review with Sam
3. Create migration plan for existing skills

**Day 15: Milestone 1 Checkpoint**
1. Run full test suite
2. Document achieved vs. planned coverage
3. Identify blockers for Milestone 2

---

## Appendix A: File Size Reference (Hermes Hotspots)

These files represent the bulk of the logic that must be absorbed:

| File | Lines | Priority | Notes |
|---|---|---|---|
| run_agent.py | 8,723 | Critical | Main loop. Most logic extracted via behavior porting, not line migration. |
| cli.py | ~7,000 | Low | CLI UI code. Replaced by Talos CLI client. |
| gateway/run.py | 6,410 | M4 | Gateway controller. Port framework, not line-by-line. |
| trajectory_compressor.py | 1,518 | Deprecate | RL-specific. Not needed in Talos. |
| hermes_state.py | 1,274 | M2 | SessionDB. Replaced by Django models. |
| tools/terminal_tool.py | 1,358 | M1 | Core tool. Full port required. |
| agent/prompt_builder.py | 816 | M3 | Becomes addon functions. |
| tools/delegate_tool.py | 794 | M1 | Becomes CNS subgraph creation. |
| cron/jobs.py | 746 | M4 | Becomes TemporalLobe model. |
| tools/skill_manager_tool.py | 742 | M2 | Becomes SkillEngram CRUD. |
| toolsets.py | 641 | M1 | Becomes IdentityDisc.enabled_tools config. |
| cron/scheduler.py | 628 | M4 | Becomes Celery Beat integration. |
| tools/memory_tool.py | 548 | M2 | Becomes Hippocampus tool. |
| agent/context_references.py | 492 | M3 | Becomes Thalamus pre-processor. |

## Appendix B: Talos Model Counts

| App | Models | Status |
|---|---|---|
| hippocampus | 2 | Active — core to memory migration |
| frontal_lobe | 6 | Active — core to reasoning |
| central_nervous_system | 15 | Active — orchestration backbone |
| identity | 10 | Active — core to identity migration |
| temporal_lobe | 10 | Active — extends with cron |
| parietal_lobe | 7 | Active — core to tool migration |
| prefrontal_cortex | 7 | Active — work management |
| hypothalamus | 24 | Active — model routing (unchanged) |
| peripheral_nervous_system | 4 | Active — I/O management |
| environments | 10 | Active — project config |
| synaptic_cleft | 0 | Active — Channels messaging |
| thalamus | 0 (Stimulus class) | Active — sensory relay |
| occipital_lobe | 0 (utility fns) | Active — log parsing |
| dashboard | 0 | Active — UI |
| **TOTAL** | **~95** | |

## Appendix C: Hermes Tool → Talos MCP Mapping

| Hermes Tool | Existing Talos MCP | Action |
|---|---|---|
| terminal | (none) | PORT → mcp_terminal |
| process | (none) | PORT → mcp_process |
| read_file | mcp_read_file ✓ | VERIFY parity |
| write_file | (none) | PORT → mcp_fs_write |
| patch | mcp_fs_patch (partial) | ENHANCE |
| search_files | mcp_fs_grep + mcp_fs_list (partial) | ENHANCE |
| web_search | mcp_internet_query (partial) | ENHANCE/REPLACE |
| web_extract | (none) | PORT → mcp_web_extract |
| browser_navigate | mcp_browser_read (partial) | ENHANCE |
| browser_click/type/etc | (none) | PORT → mcp_browser_interact |
| browser_vision | (none) | PORT → mcp_browser_vision |
| memory | mcp_engram_save/read/search/update ✓ | ADAPT interface |
| skill_manage | (none) | PORT → mcp_skill_manage |
| skill_view | (none) | PORT → mcp_skill_view |
| skills_list | (none) | PORT → mcp_skill_list |
| session_search | (none) | PORT → mcp_session_search |
| delegate_task | (none — CNS subgraph) | BUILD → mcp_delegate |
| execute_code | (none) | PORT → mcp_code_exec |
| cronjob | (none — TemporalLobe) | BUILD → mcp_schedule |
| todo | (none) | PORT → mcp_todo |
| clarify | mcp_ask_user ✓ | VERIFY parity |
| vision_analyze | (none) | PORT → mcp_vision |
| image_generate | (none) | PORT → mcp_image_gen |
| text_to_speech | (none) | PORT → mcp_tts |
| send_message | mcp_respond_to_user (partial) | ENHANCE |
| honcho_context | (none) | PORT → mcp_honcho |
| honcho_search | (none) | PORT → mcp_honcho |
| browser_console | (none) | PORT → mcp_browser |
| browser_get_images | (none) | PORT → mcp_browser |

**Summary:** 7 tools have existing Talos equivalents. ~28 tools need porting or building.

---

*End of document. This is a living plan — update as implementation progresses.*
