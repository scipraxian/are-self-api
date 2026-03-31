---
tags: []
parent: ""
collections:
    - Architecture
$version: 3179
$libraryID: 1
$itemKey: PFR744KK

---
# Hypothalamus — Comprehensive Documentation

## Summary

The **hypothalamus** module maintains the universe of callable LLM endpoints (LiteLLM-aligned), attaches costs and capability flags, embeds each `AIModel` for semantic routing, and returns a `ModelSelection` for a given persona and estimated payload size. Providers are screened by budget, context length, and circuit breakers. `Hypothalamus.sync_catalog` ingests LiteLLM’s public JSON and refreshes the database.

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

## Target: hypothalamus/

### Overview

**Purpose:** Maintain the universe of callable LLM endpoints (LiteLLM-aligned), attach costs and capability flags, embed each `AIModel` for semantic routing, and return a `ModelSelection` for a given persona and estimated payload size.

**Connections in the wider system:**

*   **frontal\_lobe**: `Hypothalamus().pick_optimal_model` inside the hot-swap inference loop; `SynapseClient` consumes `ModelSelection`.

*   **parietal\_lobe**: Uses `ModelSelection` where routing is shared with tool execution paths.

*   **identity**: `IdentityDisc`, `IdentityBudget`, `IdentityFields.category` → `hypothalamus.AIModelCategory`; persona `vector` (768) drives routing.

*   **frontal\_lobe.models.ModelRegistry**: `AIModel.update_vector()` uses `OllamaClient` + Nomic embed id for embedding text derived from model name, categories, and description.

***

### Directory / Module Map

```
hypothalamus/
├── __init__.py
├── admin.py
├── apps.py
├── hypothalamus.py       # Hypothalamus class: pick_optimal_model, sync_catalog
├── models.py             # LLMProvider, AIModel, AIModelProvider, AIModelPricing, usage, sync log
├── serializers.py        # ModelSelection, SyncResult dataclasses
├── views.py
├── migrations/
└── tests.py
```

**Grouping by responsibility:**

*   **Routing:** `hypothalamus.py` (`pick_optimal_model`)

*   **Catalog sync:** `hypothalamus.py` (`sync_catalog`, `_ensure_*`, `_update_pricing`, `_trigger_vector_generation`)

*   **Persistence:** `models.py`

*   **API surface to callers:** `serializers.ModelSelection`

***

### Public Interfaces

| Interface                                             | Type          | Purpose                                                                                                         |
| ----------------------------------------------------- | ------------- | --------------------------------------------------------------------------------------------------------------- |
| `Hypothalamus.pick_optimal_model(disc, payload_size)` | Static method | Returns`ModelSelection`or`None`(pool exhausted)                                                                 |
| `Hypothalamus.sync_catalog()`                         | Class method  | Fetches LiteLLM JSON, upserts providers/models/pricing, optional vector backfill; returns`AIModelSyncLog`       |
| `ModelSelection`                                      | dataclass     | `provider_model_id`,`ai_model_name`,`distance`,`input_cost_per_token`,`is_fallback`;`ModelSelection.fallback()` |
| `LLMProvider`                                         | Model         | Provider key, base URL, chat path, API key env var;`has_active_key`                                             |
| `AIModel`                                             | Model         | Semantic model record;`vector`(768);`enabled`;`update_vector()`                                                 |
| `AIModelProvider`                                     | Model         | Join of model + provider +`provider_unique_model_id`; rate-limit mixin                                          |
| `AIModelPricing`                                      | Model         | Current/active pricing rows; LiteLLM cost fields                                                                |
| `AIModelProviderUsageRecord`                          | Model         | Audit ledger (tokens, costs, optional FKs to identity/reasoning turn)                                           |
| `AIModelSyncLog`                                      | Model         | Mutex for running sync; counts and error message                                                                |


***

### Execution and Control Flow

1.  **Routing:** Caller passes `IdentityDisc` (with `budget`, `vector`) and `payload_size`.

2.  **Filters:** `LLMProvider` must have API key if required; `AIModelProvider` must pass circuit breaker (`rate_limit_reset_time` null or elapsed); mode `chat`; `ai_model.enabled`; current active pricing; `input_cost_per_token <= budget.max_input_cost_per_token`; `ai_model.context_length >= payload_size`.

3.  **Rank:** `CosineDistance('ai_model__vector', disc.vector)` ascending, then `input_cost_per_token` ascending; first row wins.

4.  **Sync:** Single-flight via `AIModelSyncLog` status `RUNNING`; HTTP GET LiteLLM catalog; transactional upsert; tombstone pricing rows whose `provider_unique_model_id` disappeared; on success with new models, `_trigger_vector_generation()` for `AIModel` rows with null `vector`.

***

### Data Flow

```
LiteLLM JSON (HTTP)
    → AIModelSyncLog + LLMProvider / AIMode / AIModel / AIModelProvider / AIModelPricing
    → AIModel.update_vector() (Ollama embed via ModelRegistry.NOMIC_EMBED_TEXT)

IdentityDisc.vector + budget + payload_size
    → AIModelProvider queryset + CosineDistance
    → ModelSelection → SynapseClient / chat APIs
```

***

### Integration Points

| Consumer                      | Usage                                                                    |
| ----------------------------- | ------------------------------------------------------------------------ |
| `frontal_lobe.FrontalLobe`    | Hot-swap loop calls`pick_optimal_model`;`SynapseClient(model_selection)` |
| `frontal_lobe.synapse_client` | Builds client from`ModelSelection`                                       |
| `parietal_lobe`               | Imports`ModelSelection`where routing is shared                           |
| `identity.IdentityFields`     | `category`→`AIModelCategory`                                             |


***

### Configuration and Conventions

*   **LiteLLM URL:** `LITELLM_CATALOG_URL` in `hypothalamus.py` (BerriAI `model_prices_and_context_window.json`).

*   **Embedding dimension:** 768 for `AIModel.vector` (same embedding space as persona vectors when both use Nomic-style embeds).

*   **Persona vector:** `pick_optimal_model` annotates `CosineDistance('ai_model__vector', disc.vector)`; `IdentityDisc.vector`\*\* should be populated\*\* (and `budget` set appropriately) or routing may return no rows or error at the DB layer.

*   **Circuit breaker:** `AIModelProvider.trip_circuit_breaker` / `reset_circuit_breaker` (exponential backoff on rate limits); `pick_optimal_model` excludes rows still in cooldown.

***

### Extension and Testing Guidance

*   Add routing dimensions by extending the queryset filters or annotating additional fields (keep ordering deterministic).

*   Sync skips keys in `CATALOG_SKIP_KEYS` (e.g. `sample_spec`).

*   Tests should use `django.test.TestCase` and transactional DBs per Talos standards; mock HTTP for `sync_catalog` if added.

***

## Visualizations

### `pick_optimal_model` routing

Feasible `AIModelProvider` rows are filtered, ranked by `CosineDistance` to `IdentityDisc.vector`, then by input cost per token.

```
flowchart TD
    subgraph inputs [Inputs]
        disc[IdentityDisc vector budget]
        n[payload_size estimate]
    end
    subgraph filters [Query filters]
        f1[LLMProvider has key if required]
        f2[breaker rate_limit_reset_time]
        f3[mode chat ai_model enabled]
        f4[AIModelPricing current active]
        f5["input_cost lte budget.max"]
        f6["context_length gte payload_size"]
    end
    subgraph rankingBlock [Ranking]
        ann[Annotate CosineDistance ai_model vector disc vector]
        ord[order_by distance then input_cost]
        first[first row or None]
    end
    subgraph outBlock [Output]
        ms[ModelSelection]
    end
    disc --> f1
    n --> f6
    f1 --> f2
    f2 --> f3
    f3 --> f4
    f4 --> f5
    f5 --> f6
    f6 --> ann
    ann --> ord
    ord --> first
    first --> ms
```

### `sync_catalog` pipeline

Single-flight mutex via `AIModelSyncLog`; transactional upsert then tombstone stale pricing; optional embedding backfill for new models.

```
flowchart TB
    s0{Another sync RUNNING?} -->|yes| sAbort[Return None]
    s0 -->|no| s1[Create AIModelSyncLog RUNNING]
    s1 --> s2[HTTP GET LiteLLM JSON]
    s2 --> s3[Atomic transaction]
    s3 --> s4[For each catalog key skip sample_spec]
    s4 --> s5[_ensure_provider mode ai_model model_provider]
    s5 --> s6[_update_pricing version rows]
    s6 --> s7[Tombstone pricing not in active keys]
    s7 --> s8[Commit SUCCESS or FAILED]
    s8 --> s9{models_added gt 0?}
    s9 -->|yes| s10[_trigger_vector_generation]
    s9 -->|no| sDone[Save sync log]
    s10 --> sDone
```

***

## Mathematical Framing

Let $\mathbf{v}_p \in \mathbb{R}^{768}$ be `IdentityDisc.vector` and $\mathbf{v}_m$ be `AIModel.vector`. For each candidate `AIModelProvider` row $r$ with current input price $c_r$ and context limit $L_m$:

**Feasibility:** $c_r \leq c_{\max}$ (budget), $L_m \geq n$ (payload estimate tokens), and breaker inactive.

**Objective:** Minimize `CosineDistance`$(\mathbf{v}_m, \mathbf{v}_p)$, then tie-break on lower $c_r$.

$$
r^\* = \arg\min_{r \in \mathcal{F}} \left( d_{\cos}(\mathbf{v}_{m(r)}, \mathbf{v}_p),\ c_r \right) \text{ in lexicographic order}
$$

where $\mathcal{F}$ is the filtered set from `pick_optimal_model`.
