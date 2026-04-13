# Layer 1: Core MCP Tool Suite

**Path B — Layer 1 Implementation Plan**  
**Date:** 2026-04-07  
**Estimated Scope:** 10 new modules, ~3,000-4,000 lines, 2-3 weeks  
**Prerequisites:** Existing parietal_mcp infrastructure (`parietal_lobe/parietal_mcp/`) and ParietalLobe tool execution pipeline.

---

## 1. Design Philosophy

Build natively against Talos patterns. Do NOT port Hermes tool code line-by-line. Consult Hermes for behavioral details (what regex catches `sudo`? how does fuzzy matching handle tabs vs spaces?) but implement cleanly in the `parietal_mcp/` module style.

Each tool follows the established pattern:
1. A function in `parietal_mcp/` named `mcp_<capability>`
2. A `ToolDefinition` row (and `ToolParameter` + `ToolParameterAssignment` rows)
3. Registration via `IdentityDisc.enabled_tools` M2M
4. Existing Focus/XP system applies automatically

---

## 2. Implementation Order (Dependency-Aware)

Phase 1: Core Ops → Phase 2: Network + Code → Phase 3: Browser + Advanced

### 2.1 mcp_fs_write

**Why first:** Simplest new tool, zero external dependencies, complements 4 existing file tools.

**File:** `parietal_lobe/parietal_mcp/mcp_fs_write.py` (~30 lines)

**Specification:**
- `def mcp_fs_write(path: str, content: str) -> dict`
- Creates parent directories automatically via `os.makedirs(exist_ok=True)`
- Always overwrites. Returns: `{"path": str, "bytes_written": int}`
- Validates path: no traversal outside working directory constraint
- Uses `write_file` pattern from existing tools

**ToolDefinition:**
- name: `mcp_fs_write`
- category: `filesystem`
- description: `Write content to a file, creating parent directories as needed. Overwrites existing content.`
- parameters: `path` (string, required), `content` (string, required)
- safety: `safe` (read-only check not needed — this is inherently write)

**Tests:**
- Write to new file
- Write to existing file (overwrites)
- Write creates nested directories
- Write with empty content
- Path traversal rejection

**Dependencies:** None (standard library only)

---

### 2.2 mcp_fs_patch (Enhancement — Add Fuzzy Matching)

**File:** `parietal_lobe/parietal_mcp/mcp_fs_patch.py` (enhance existing)

**What to add:** Port the 9-strategy fuzzy matcher from Hermes `tools/fuzzy_match.py`. Current Talos patch uses exact string matching. Add these fallback strategies in order:

1. Exact match (current behavior)
2. Trim leading/trailing whitespace on old_string
3. Ignore indentation differences (strip all leading whitespace per line)
4. Expand inline `\n` to actual newlines
5. Expand inline `\t` to actual tabs
6. Normalize CRLF to LF
7. Allow for missing trailing newline
8. Regex-based fuzzy match (treat old_string as regex with `re.DOTALL`)
9. Last resort: line-by-line similarity matching using difflib

**Algorithm:** Each strategy is tried in sequence. The first that produces a valid match is used. Log which strategy matched for debugging. Return `{"strategy_used": int, "new_content": str}` with strategy number for diagnostics.

**ToolDefinition:** No change to schema. The `mcp_fs_patch` tool already exists — just enhance its implementation.

**Tests:**
- Patch with exact match (unchanged behavior)
- Patch with differing indentation
- Patch with CRLF vs LF
- Patch with extra whitespace
- Patch fails on all strategies → returns clear error
- Patch with replace_all flag
- Patch with syntax validation hook

**Dependencies:** Hermes `tools/fuzzy_match.py` for reference (line 1-365 of that file has the full strategy list)

---

### 2.3 mcp_memory

**File:** `parietal_lobe/parietal_mcp/mcp_memory.py` (~200 lines)

**Specification:** Interface over Hippocampus Engrams that presents familiar `add`/`replace`/`remove` operations, but stores as proper Engrams with vector embeddings and relational links.

Two tagged collections:
- `agent_memory` — operational notes, context facts
- `user_profile` — user preferences, communication style, environment

**Functions:**
```python
def mcp_memory_add(collection: str, content: str) -> dict
def mcp_memory_replace(collection: str, old_content: str, new_content: str) -> dict
def mcp_memory_remove(collection: str, content_snippet: str) -> dict
```

**Implementation details:**
- Validates collection is either `agent_memory` or `user_profile` (case-insensitive)
- Content limit: 400 chars per entry (matches Hermes MEMORY.md convention)
- Each entry creates an `Engram` with:
  - `name`: Truncated first 80 chars of content
  - `description`: Full content
  - `tags`: [collection, "hermes_memory"]
  - Vector embedding: Generate via Hippocampus OllamaClient (nomic-embed-text)
  - `is_active`: True
- `replace`: Search by cosine similarity (threshold 0.90) to find the entry being replaced, update its description
- `remove`: Search by cosine similarity, set `is_active` to False (soft delete)
- Character counting: Enforce per-collection limits (agent_memory: 2000 chars total, user_profile: 2000 chars total)
- Returns: `{"collection": str, "action": str, "entries_count": int, "total_chars": int}`

**ToolDefinition:**
- name: `mcp_memory`
- category: `memory`
- description: `Manage persistent memory entries. Actions: add, replace, remove. Collections: agent_memory, user_profile.`
- parameters: `action` (string, enum: add/replace/remove), `collection` (string), `content` (string, required for add, old_content for replace, content_snippet for remove), `new_content` (string, only for replace)

**Tests:**
- Add entry to agent_memory → Engram created with correct tags
- Add exceeding char limit → rejection
- Replace existing entry by similarity match
- Remove entry → soft delete (is_active=False)
- Both collections work independently
- Embedding generation (mock the OllamaClient)
- Empty content rejected
- Collection validation (invalid name → error)

**Dependencies:** `hippocampus.models.Engram`, Hippocampus OllamaClient for embedding

---

### 2.4 mcp_terminal

**Why it's the most complex Phase 1 tool:** Background processes, dangerous command detection, process registry.

**File:** `parietal_lobe/parietal_mcp/mcp_terminal.py` (~400 lines)

**Specification:**
```python
def mcp_terminal(
    command: str,
    background: bool = False,
    timeout: Optional[int] = 180,
    workdir: Optional[str] = None,
    dangerous_cmd_override: bool = False,
) -> dict
```

**Foreground mode (default):**
- Run command via `subprocess.run()`
- Capture stdout, stderr, return code
- Timeout: default 180s (configurable)
- Truncate output at 50KB with message indicating truncation
- Return: `{"output": str, "exit_code": int, "truncated": bool}`

**Background mode:**
- Start via `subprocess.Popen()` with separate process group
- Register in process registry (new model or existing pattern)
- Return: `{"pid": int, "session_id": str, "status": "running"}`
- Add companion tool: `mcp_terminal_poll(session_id: str)` → check status, get new output
- `mcp_terminal_kill(session_id: str)` → terminate process

**Dangerous command detection:**
- Block/flag: `sudo`, `rm -rf /`, `mkfs`, `dd if=`, `:(){:>};:`, `> /etc/passwd`
- Return warning with `{"is_dangerous": True, "warning": str, "override_with_flag": True}`
- User must set `dangerous_cmd_override=True` to proceed

**Implementation detail:** Use system Python for terminal commands (matches existing Hermes pattern). The tool runs in the Celery worker context, so it has the same filesystem access as Talos itself.

**ToolDefinition:**
- name: `mcp_terminal`
- category: `execution`
- description: `Run shell commands. Foreground returns output immediately. Background returns a session_id for polling. Supports timeout, working directory, and dangerous command detection.`
- parameters: `command` (string, required), `background` (boolean), `timeout` (integer), `workdir` (string), `dangerous_cmd_override` (boolean)

**Tests:**
- Simple command: `echo hello`
- Long-running command with timeout
- Background start + poll + kill
- Dangerous command detection
- Non-zero exit code
- Large output (>50KB) truncation
- Working directory setting
- Command with pipes and redirections

**Dependencies:** `subprocess`, potential new process registry model

---

### 2.5 mcp_web_search

**File:** `parietal_lobe/parietal_mcp/mcp_web_search.py` (~80 lines)

**Specification:**
```python
def mcp_web_search(query: str, max_results: int = 5) -> dict
```

**Implementation:**
- Default to SearXNG (local instance) if available (env `SEARXNG_URL`)
- Fallback to Tavily API if configured (`TAVILY_API_KEY`)
- SearXNG wrapper: GET to `{SEARXNG_URL}/search?q={query}&format=json&categories=general`
- Tavily wrapper: POST to `https://api.tavily.com/search`
- Return: `{"results": [{"title": str, "url": str, "snippet": str}], "query": str, "count": int}`
- If neither configured: `{"error": "No search provider configured. Set SEARXNG_URL or TAVILY_API_KEY."}`

**ToolDefinition:**
- name: `mcp_web_search`
- category: `web`
- description: `Search the web. Supports SearXNG (local) and Tavily (API) providers.`
- parameters: `query` (string, required), `max_results` (integer, default=5)

**Tests:**
- SearXNG search (mock HTTP)
- Tavily search (mock HTTP)
- Neither configured → error
- Zero results → empty results list
- Malformed response from provider

**Dependencies:** `requests` or `httpx` for HTTP calls

---

### 2.6 mcp_web_extract

**File:** `parietal_lobe/parietal_mcp/mcp_web_extract.py` (~60 lines)

**Specification:**
```python
def mcp_web_extract(url: str, max_length: int = 10000) -> dict
```

**Implementation:**
- Use `trafilatura` library for URL → markdown conversion (preferred — handles JS-rendered pages better)
- Fallback: simple `requests.get()` + `markdownify` / HTML text extraction
- Return: `{"url": str, "title": str, "content": str, "truncated": bool, "char_count": int}`
- Truncate to max_length with notice
- Timeout: 30s per request

**ToolDefinition:**
- name: `mcp_web_extract`
- category: `web`
- description: `Extract readable text content from a URL. Converts HTML to markdown-like text.`
- parameters: `url` (string, required), `max_length` (integer, default=10000)

**Tests:**
- Extract from a simple HTML page (mock HTTP)
- Extract timeout
- Invalid URL → error
- Truncation at max_length
- Empty page → empty content

**Dependencies:** `trafilatura` (pip install trafilatura), `requests`

---

### 2.7 mcp_code_exec

**File:** `parietal_lobe/parietal_mcp/mcp_code_exec.py` (~120 lines)

**Specification:**
```python
def mcp_code_exec(code: str, timeout: int = 300, workdir: Optional[str] = None) -> dict
```

**Implementation:**
- Write code to a temp file
- Execute with system Python: `/usr/bin/python3 <temp_file>`
- Capture stdout, stderr, return code
- Timeout: default 300s (5 min)
- Output cap: 50KB — truncate with notice
- **Available imports via `from hermes_tools import ...`:** The script can use `read_file`, `write_file`, `search_files`, `terminal`, `patch` — the same toolset available in Hermes
- Return: `{"stdout": str, "stderr": str, "exit_code": int, "truncated": bool}`

**Security note:** This runs arbitrary Python on the host. Limit to trusted users (controlled via IdentityDisc.enabled_tools). Consider containerization later.

**ToolDefinition:**
- name: `mcp_code_exec`
- category: `execution`
- description: `Execute arbitrary Python code. System Python with predefined tool imports available via 'from hermes_tools import ...'.`
- parameters: `code` (string, required), `timeout` (integer, default=300), `workdir` (string)

**Tests:**
- Simple print statement
- Code using hermes_tools imports
- Code that exceeds timeout
- Code that exceeds 50KB output
- Syntax error in code
- Code with file operations that succeed

**Dependencies:** System Python at `/usr/bin/python3`, temp file handling

---

### 2.8 mcp_session_search

**File:** `parietal_lobe/parietal_mcp/mcp_session_search.py` (~150 lines)

**Specification:**
```python
def mcp_session_search(query: str, limit: int = 5, role_filter: Optional[str] = None) -> dict
```

**Implementation:**
- PostgreSQL full-text search across `ReasoningSession` and `ReasoningTurn`
- Use Django `__search` lookup or raw SQL with `tsvector`/`tsquery`
- Parse the query: support boolean operators (`AND`, `OR`, `NOT`), prefix matching (`deploy*`), phrase matching (`"docker networking"`)
- Search across `ReasoningTurn.content`, `ReasoningSession.name`, tool call results
- Optionally filter by role: `user`, `assistant`, `tool`
- Return top N results with: `{"matches": [{"session_id": str, "turn_number": int, "content_snippet": str, "timestamp": str, "score": float}]}`
- Limit results to prevent context pollution (max 10)

**ToolDefinition:**
- name: `mcp_session_search`
- category: `search`
- description: `Search past conversation sessions. Supports boolean queries, phrase matching, and prefix matching.`
- parameters: `query` (string, required), `limit` (integer, default=5), `role_filter` (string, optional)

**Tests:**
- Simple keyword search
- Boolean AND query
- Phrase matching with quotes
- Prefix search with asterisk
- Role filter
- Empty database → no results
- Max limit enforcement

**Dependencies:** PostgreSQL with `pg_trgm` or full-text search extension

---

### 2.9 mcp_browser

**Why it's the most complex single tool:** Playwright lifecycle, accessibility tree parsing, headless browser management, concurrent session handling.

**File:** `parietal_lobe/parietal_mcp/mcp_browser.py` (~500 lines)

**Specification:**
```python
def mcp_browser(action: str, **kwargs) -> dict
```

**Actions:**
- `navigate(url: str)` → `{"title": str, "url": str, "snapshot": str}`
- `click(ref: str)` → `{"success": bool, "snapshot": str}`
- `type(ref: str, text: str)` → `{"success": bool}`
- `press(key: str)` → `{"success": bool, "snapshot": str}`
- `scroll(direction: "up" | "down")` → `{"snapshot": str}`
- `snapshot()` → `{"snapshot": str, "title": str}` — returns accessibility tree as text
- `get_images()` → `[{"url": str, "alt": str, "ref": str}]`
- `vision(question: str)` → `{"analysis": str}` — takes screenshot, sends to vision provider
- `back()` → `{"url": str, "title": str}`

**Implementation:**
- Use Playwright (async API) — `playwright` pip package
- Singleton browser instance per Celery worker (lazy initialization)
- Page is tied to the ReasoningSession (stored in thread-local or Redis)
- Accessibility tree: `page.accessibility.snapshot()` → convert to text format with ref IDs (`@e1`, `@e2`)
- Ref IDs: Assign sequential numbers to interactive elements for click/type targeting
- Screenshot: `page.screenshot()` → base64 encode → send to `mcp_vision` for analysis
- Timeout: 30s for navigation, 10s for interactions

**ToolDefinition:**
- name: `mcp_browser`
- category: `browser`
- description: `Control a headless browser. Actions: navigate, click, type, press, scroll, snapshot, get_images, vision. Returns accessibility tree with ref IDs for interaction.`
- parameters: `action` (string, required), additional kwargs based on action type

**Tests:**
- Navigate to a page (mock Playwright)
- Click on element by ref
- Type text into input
- Scroll up/down
- Snapshot returns accessibility tree with refs
- Vision screenshot + analysis (mocked)
- Browser session lifecycle (start, use, close)
- Timeout on navigation

**Dependencies:** `playwright` (requires `playwright install` for browser binaries)

---

### 2.10 mcp_vision

**File:** `parietal_lobe/parietal_mcp/mcp_vision.py` (~60 lines)

**Specification:**
```python
def mcp_vision(image_path: str, question: str, provider: Optional[str] = None) -> dict
```

**Implementation:**
- Multi-provider: Try in order → Anthropic (Claude 4), OpenAI (GPT-4o), default configured provider
- Load image file, encode to base64
- Send as multimodal message to LLM with the question
- Return: `{"analysis": str, "provider": str}`
- If image_path is a URL (http/https), download first
- Timeout: 60s per provider

**ToolDefinition:**
- name: `mcp_vision`
- category: `vision`
- description: `Analyze an image using vision AI. Supports Anthropic Claude and OpenAI GPT-4o providers.`
- parameters: `image_path` (string, required), `question` (string, required), `provider` (string, optional)

**Tests:**
- Vision with local image (mock API)
- Vision with URL image (mock HTTP + mock API)
- Provider failover (first provider fails → second tried)
- All providers fail → error with details
- Missing image file → error

**Dependencies:** LiteLLM or direct provider SDK, `httpx` for URL downloads

---

## 3. ToolDefinition Fixture

Create a single Django fixture file: `parietal_lobe/fixtures/layer1_tools.json`

Contains all 10 ToolDefinition rows with their ToolParameter and ToolParameterAssignment rows. Load with `manage.py loaddata layer1_tools`.

---

## 4. Acceptance Criteria

1. All 10 tools exist in `parietal_lobe/parietal_mcp/` as importable Python modules
2. Each tool has a corresponding `ToolDefinition` row loaded from fixtures
3. Each tool works through ParietalLobe's existing `process_tool_calls()` pipeline
4. FrontalLobe can discover and invoke each tool via the standard tool call flow
5. A minimum test suite exists for each tool (happy path + common error cases)
6. Tools are registered against the Julianna IdentityDisc via `enabled_tools` M2M
7. No Hermes tool code is copied — all implementations are native Talos

---

## 5. Migration from Hermes

Once all 10 tools are tested, verify behavioral parity with Hermes:

| Tool | Hermes Equivalent | Validation Method |
|------|-------------------|-------------------|
| mcp_terminal | terminal_tool | Run same command on both, compare output format |
| mcp_fs_write | write_file | Same file operation, same result |
| mcp_fs_patch | patch | Use Hermes fuzzy_match.py as reference for test cases |
| mcp_memory | memory_tool | Same memory entry, verify Engram stored correctly |
| mcp_session_search | session_search | Same query, compare result quality |
| mcp_web_search | web_search | Same query, compare result structure |
| mcp_web_extract | web_extract | Same URL, compare markdown quality |
| mcp_code_exec | execute_code | Same Python code, same output |
| mcp_browser | browser_tool | Same navigation sequence, same snapshot format |
| mcp_vision | vision_analyze | Same image + question, compare analysis quality |

---

*End of Layer 1 Plan*
