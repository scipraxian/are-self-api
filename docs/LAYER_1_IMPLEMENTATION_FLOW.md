# Layer 1 implementation flow

This document captures **Mermaid flow diagrams** for the Layer 1 core MCP tool suite: how tools connect to the gateway, how `mcp_session_search` routes queries across corpora and databases, and how `mcp_browser` manages Playwright pages, `@eN` refs, and actions.

See also [LAYER_1_CORE_TOOLS_PLAN.md](LAYER_1_CORE_TOOLS_PLAN.md) for the full tool list and specifications.

---

## 1. Layer 1 in the execution stack (gateway to tools)

```mermaid
flowchart TB
  subgraph entry [Entry]
    IdentityDisc[IdentityDisc enabled_tools M2M]
    ParietalMCP[ParietalMCP.execute]
  end

  subgraph layer1 [Layer 1 Core MCP Tools]
    FS[mcp_fs_write / patch / read family]
    Mem[mcp_memory]
    Term[mcp_terminal]
    Web[mcp_web_search]
    Code[mcp_code_exec]
    Search[mcp_session_search]
    Br[mcp_browser]
    Vis[mcp_vision]
  end

  subgraph deps [Typical dependencies]
    Hippocampus[Hippocampus Engrams / embeddings]
    FSys[Project filesystem]
    Net[HTTP search providers]
    PG[(PostgreSQL FTS)]
    SQLite[(SQLite fallback)]
    PW[Playwright Chromium]
    LLM[LiteLLM vision]
  end

  IdentityDisc --> ParietalMCP
  ParietalMCP --> FS
  ParietalMCP --> Mem
  ParietalMCP --> Term
  ParietalMCP --> Web
  ParietalMCP --> Code
  ParietalMCP --> Search
  ParietalMCP --> Br
  ParietalMCP --> Vis

  Mem --> Hippocampus
  FS --> FSys
  Web --> Net
  Search --> PG
  Search --> SQLite
  Br --> PW
  Vis --> LLM
```

---

## 2. `mcp_session_search` — query to corpora to rank to response

```mermaid
flowchart LR
  subgraph inputs [Inputs]
    Q[query string]
    L[limit capped at 10]
    RF[role_filter optional]
  end

  subgraph norm [Normalize]
    RFN[Normalize role_filter user assistant tool or all]
    SQ[Build SearchQuery websearch on PG or keywords on SQLite]
  end

  subgraph corpora [Search corpora]
    TC[ToolCall arguments plus result_payload]
    RT[ReasoningTurn via AIModelProviderUsageRecord]
    SID[str session_id in ledger vector]
  end

  subgraph pgPath [PostgreSQL]
    Vtc[SearchVector on ToolCall text fields]
    Vrt[SearchVector on request_payload response_payload session_id]
    Rnk[SearchRank merge]
  end

  subgraph sqlitePath [SQLite]
    Like[icontains chains on JSON text]
    Static[Static score placeholders]
  end

  subgraph refine [Role refinement Python]
    U[extract_user_text_from_request_payload]
    A[extract_assistant_corpus]
    T[extract_tool_messages_from_request_payload]
    C[ledger_combined_search_text when RF is null]
    KW[corpus_matches_keywords per lane]
  end

  subgraph out [Response]
    M[matches list]
    Fields[session_id turn_number snippet timestamp score role]
  end

  Q --> norm
  L --> norm
  RF --> RFN
  RFN --> SQ

  SQ --> pgPath
  SQ --> sqlitePath

  TC --> Vtc
  RT --> Vrt
  SID --> Vrt

  pgPath --> Rnk
  sqlitePath --> Static

  Rnk --> refine
  Static --> refine

  RFN --> U
  RFN --> A
  RFN --> T
  RFN --> C
  U --> KW
  A --> KW
  T --> KW

  refine --> M
  M --> Fields
```

---

## 3. `mcp_session_search` — which lanes run (role and vendor)

```mermaid
flowchart TD
  Start[session_search_sync]
  Empty{query empty?}
  Vendor{connection.vendor}

  Start --> Empty
  Empty -->|yes| Z[return count 0]
  Empty -->|no| Vendor

  Vendor -->|postgresql| PG[SearchQuery websearch plus FTS annotate]
  Vendor -->|other| SL[SQLite icontains fallback]

  PG --> RF{role_filter}
  SL --> RF

  RF -->|null| All[ToolCall FTS plus Ledger FTS merge]
  RF -->|tool| ToolLane[ToolCall FTS plus Ledger tool messages refine]
  RF -->|user| UserLane[Ledger FTS then user corpus refine]
  RF -->|assistant| AsstLane[Ledger FTS then assistant corpus refine]

  All --> Merge[Sort by score desc slice limit]
  ToolLane --> Merge
  UserLane --> Merge
  AsstLane --> Merge

  Merge --> Out[matches query count]
```

---

## 4. `mcp_browser` — session page lifecycle and actions

```mermaid
flowchart TB
  subgraph state [Process state]
    SK[session_key from session_id or default]
    Pages[_pages dict by session_key]
    Brws[_browser lazy singleton]
    PW[_playwright instance]
  end

  subgraph getPage [_get_page]
    Hit{session_key in _pages?}
    Hit -->|yes| Ret[return existing page]
    Hit -->|no| Ens[ensure_browser launch chromium]
    Ens --> New[new_page into _pages]
    New --> Ret
  end

  subgraph inject [Snapshot path]
    Inj[inject_ref_markers page.evaluate sequential data-parietal-browser-ref]
    Snap[Human readable lines at eN tag name text]
    Cap[Truncate to SNAPSHOT_MAX_CHARS]
  end

  subgraph refResolve [ref resolution]
    RefIn[ref string]
    Pat{matches eN or e12 pattern?}
    Pat -->|yes| LocAttr["locator data-parietal-browser-ref equals N"]
    Pat -->|no| LocCss[locator CSS string]
  end

  subgraph actions [Actions]
    Nav[navigate goto NAVIGATION_TIMEOUT_MS]
    SnapA[snapshot]
    Cl[click]
    Ty[type fill]
    Pr[press key]
    Sc[scroll]
    Ba[back]
    Gi[get_images with refs after inject]
    Vi[vision screenshot to temp file then mcp_vision]
    Close[close page.remove from _pages]
  end

  SK --> getPage
  Ret --> actions

  Nav --> Inj
  SnapA --> Inj
  Cl --> refResolve
  Ty --> refResolve
  Inj --> Snap
  Snap --> Cap

  Nav --> actions
  Close --> Pages
```

---

## 5. `mcp_browser` — ref vs CSS (interaction sequence)

```mermaid
sequenceDiagram
  participant Caller
  participant mcp_browser
  participant Page
  participant Locator

  Caller->>mcp_browser: action click ref
  mcp_browser->>Page: _get_page session_key
  alt ref is eN token
    mcp_browser->>Locator: page.locator data-parietal-browser-ref N
  else ref is CSS
    mcp_browser->>Locator: page.locator ref string
  end
  Locator->>Locator: click INTERACTION_TIMEOUT_MS
  mcp_browser->>Page: _snapshot_text inject then lines
  mcp_browser-->>Caller: success snapshot
```

---

## 6. Session search data model (ORM relationships)

```mermaid
erDiagram
  ReasoningSession ||--o{ ReasoningTurn : has
  ReasoningTurn }o--|| AIModelProviderUsageRecord : model_usage_record
  ReasoningTurn ||--o{ ToolCall : tool_calls

  AIModelProviderUsageRecord {
    json request_payload
    json response_payload
  }

  ToolCall {
    text arguments
    text result_payload
  }

  ReasoningSession {
    uuid id PK
  }
```
