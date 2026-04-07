# Talos Abstract Architecture

This document provides a comprehensive, detailed graph of Talos’s abstract architecture: layers, components, data flow, and control flow.

---

## 1. High-Level System Context

Talos is a **Django-based mission control system** for orchestrating Unreal Engine 5 build pipelines across a distributed fleet. It combines:

- **Orchestration:** Graph-based protocols (spellbooks) executed as missions (spawns) with discrete steps (heads).
- **Execution:** Local and remote execution via Talos Agents over a custom TCP protocol.
- **Cognitive layer:** Reasoning sessions, tools (MCP-style), and memory (engrams) driven by a “frontal lobe” spell.
- **User surface:** Mission Control dashboard (HTMX), REST API, and MCP endpoint.

---

## 2. Layered Architecture Diagram

```mermaid
flowchart TB
    subgraph external["External / Clients"]
        Browser[Browser Mission Control]
        MCPClient[MCP Client]
        RESTClient[REST API Client]
    end

    subgraph transport["Transport and API"]
        Daphne[Daphne ASGI]
        REST[api v1 DRF Routers]
        MCP[mcp djangorestframework_mcp]
        Daphne --> REST
        Daphne --> MCP
    end

    subgraph config_core["Config and Core"]
        Settings[config settings]
        Urls[config urls]
        CeleryApp[config celery]
        ASGI[config asgi]
        ConfigManager[core config sync]
        SeedTalos[core seed_talos]
        Settings --> Urls
        Settings --> CeleryApp
    end

    subgraph common["Common Shared Foundation"]
        Mixins[BigIdMixin NameMixin Created Modified]
        Constants[Constants]
        LookupPattern[Lookup Model Static ID Mixin]
    end

    subgraph env_layer["Environments Layer"]
        PE[ProjectEnvironment]
        CV[ContextVariable]
        TE[TalosExecutable]
        TEA[TalosExecutableArgument Switch]
        VR[VariableRenderer]
        PE --> CV
        TE --> TEA
        VR --> PE
        VR --> TE
    end

    subgraph hydra_lib["Hydra Library Definitions"]
        HSB[HydraSpellbook]
        HSN[HydraSpellbookNode]
        HSP[HydraSpell]
        HST[HydraSpellTarget Argument Context]
        HWT[HydraWireType]
        HSW[HydraSpellbookConnectionWire]
        HDM[HydraDistributionMode]
        HSS[HydraSpawnStatus HydraHeadStatus]
        HSB --> HSN
        HSN --> HSP
        HSN --> HSW
        HSW --> HSN
        HSP --> TE
        HSP --> HDM
        HSP --> HST
    end

    subgraph hydra_runtime["Hydra Runtime Execution State"]
        HSp[HydraSpawn]
        HH[HydraHead]
        HSp --> HH
        HH --> HSN
        HH --> HSP
        HH --> TAR
        HSp --> HSB
        HSp --> PE
    end

    subgraph hydra_engine["Hydra Engine Orchestration"]
        HydraClass[Hydra class]
        GW[GraphWalker]
        GSC[GenericSpellCaster]
        cast_task[cast_hydra_spell Celery]
        wave_task[check_next_wave Celery]
        HydraClass --> GW
        GW --> GSC
        GSC --> cast_task
        cast_task --> wave_task
        wave_task --> HydraClass
    end

    subgraph celery_layer["Task Queue"]
        Redis[Redis broker results]
        CeleryWorker[Celery Worker]
        Redis --> CeleryWorker
        CeleryWorker --> cast_task
    end

    subgraph agent_layer["Talos Agent Fleet"]
        TAR[TalosAgentRegistry]
        TA[TalosAgent TCP execute_remote execute_local]
        Discovery[scan_and_register]
        TA --> TAR
        Discovery --> TAR
    end

    subgraph dashboard_layer["Dashboard Mission Control"]
        DHV[DashboardHomeView]
        DVS[DashboardViewSet summary recent_missions]
        DHV --> DVS
        DVS --> HSp
    end

    subgraph thalamus["talos_thalamus"]
        ThalSignals[Hydra signals spawn_failed spawn_success]
    end

    subgraph frontal["frontal_lobe"]
        FLHandler[run_frontal_lobe native spell handler]
        ConsciousStream[ConsciousStream]
        SystemDirective[SystemDirective]
    end

    subgraph parietal["talos_parietal"]
        ToolDef[ToolDefinition ToolCall]
        ParietalMCP[ParietalMCP execute mcp tools]
        Ollama[OllamaClient]
    end

    subgraph occipital["talos_occipital"]
        ReadLog[read_build_log extract_error_blocks]
    end

    subgraph reasoning["Reasoning sessions"]
        RS[ReasoningSession]
        RT[ReasoningTurn]
        SC[SessionConclusion]
        RG[ReasoningGoal]
        RS --> RT
        RS --> SC
        RS --> RG
    end

    subgraph hippocampus["talos_hippocampus"]
        Engram[TalosEngram]
    end

    subgraph temporal["talos_temporal"]
        TemporalStub[placeholder]
    end

    FLHandler --> RS
    FLHandler --> ParietalMCP
    FLHandler --> Ollama
    ParietalMCP --> ToolDef
    ParietalMCP --> Engram
    ReadLog --> HH

    subgraph persistence["Persistence"]
        DB[PostgreSQL SQLite]
    end

    Browser --> Daphne
    MCPClient --> MCP
    RESTClient --> REST
    REST --> DHV
    REST --> DVS
    REST --> HSp
    REST --> RS
    env_layer --> hydra_lib
    env_layer --> hydra_runtime
    hydra_lib --> hydra_runtime
    hydra_runtime --> hydra_engine
    GSC --> TA
    GSC --> FLHandler
    GSC --> VR
    config_core --> env_layer
    config_core --> hydra_engine
    common --> env_layer
    common --> hydra_lib
    common --> agent_layer
    PE --> DB
    HSp --> DB
    HH --> DB
    TAR --> DB
    RS --> DB
    Engram --> DB
```

---

## 3. Control and Data Flow (Simplified)

```mermaid
sequenceDiagram
    participant User
    participant Dashboard
    participant Hydra
    participant Celery
    participant SpellCaster
    participant Agent
    participant Brain

    User->>Dashboard: Select spellbook and Launch
    Dashboard->>Hydra: Hydra start with spellbook_id
    Hydra->>Hydra: Create HydraSpawn set RUNNING
    Hydra->>Hydra: dispatch_next_wave GraphWalker
    Hydra->>Celery: cast_hydra_spell delay head_id
    Celery->>SpellCaster: GenericSpellCaster execute

    alt Native handler run_frontal_lobe
        SpellCaster->>Brain: Frontal Lobe to ReasoningSession ParietalMCP Ollama
        Brain-->>SpellCaster: conclusion and tool results
    else Executable local or remote
        SpellCaster->>SpellCaster: VariableRenderer get_full_command
        SpellCaster->>Agent: execute_remote or execute_local
        Agent-->>SpellCaster: logs and exit code
    end

    SpellCaster-->>Celery: head status updated
    Celery->>Hydra: check_next_wave spawn_id
    Hydra->>Hydra: traverse wires create new heads or child spawns
    Hydra->>Celery: cast_hydra_spell delay new_head_id
    Hydra->>Dashboard: spawn and heads visible via API
    Dashboard->>User: Mission Control updates HTMX poll
```

---

## 4. Component Summary

| Layer | Key components | Responsibility |
|-------|-----------------|----------------|
| **Transport** | Daphne, REST (`api/v1/`), MCP (`/mcp/`) | HTTP/ASGI entry, routing to apps |
| **Config & Core** | settings, urls, celery, asgi, config_manager, seed_talos | Project config, bootstrap, DB seed |
| **Common** | Mixins, constants, lookup pattern | Shared model base and conventions |
| **Environments** | ProjectEnvironment, TalosExecutable, VariableRenderer | Context and path resolution for spells |
| **Hydra Library** | Spellbook, Node, Spell, Wire, DistributionMode, Status lookups | Protocol and spell definitions |
| **Hydra Runtime** | HydraSpawn, HydraHead | One mission run and per-step execution state |
| **Hydra Engine** | Hydra class, GraphWalker, GenericSpellCaster, Celery tasks | Start, wave dispatch, spell execution, next wave |
| **Celery** | Redis, cast_hydra_spell, check_next_wave | Async execution and chaining |
| **Talos Agent** | TalosAgentRegistry, TalosAgent TCP server, discovery | Fleet registry and remote/local execution |
| **Dashboard** | DashboardHomeView, DashboardViewSet | Mission Control UI and summary API |
| **Brain** | Thalamus (signals), Frontal (directives, frontal spell), Parietal (tools, MCP, Ollama), Occipital (log reading), Reasoning (sessions/turns/conclusions), Hippocampus (engrams), Temporal (stub) | Routing, reasoning, tools, log vision, memory |

---

## 5. Key Conventions Reflected in the Graph

- **Strict ID pattern:** Status and mode fields use **Lookup models + static ID class + Mixin** (e.g. `HydraStatusID`, `HydraHeadStatus`); no `TextChoices` or string literals for status.
- **Environment scoping:** Spellbooks, nodes, and spawns use **ProjectEnvironmentMixin**; commands and paths are rendered via **VariableRenderer** with environment context.
- **Execution model:** One **HydraHead** per graph node execution; heads run in Celery via **cast_hydra_spell**; **check_next_wave** drives the next wave and sub-spawns.
- **Brain integration:** The **run_frontal_lobe** native handler creates/resumes a **ReasoningSession**, uses **OllamaClient** and **ParietalMCP** for tools (including engrams), and completes when the model calls **mcp_conclude_session**.

This graph and the tables above describe the **abstract architecture** of Talos; for file-level detail and app responsibilities, see [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md).
