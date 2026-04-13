# Layer 3: Identity Addons

**Path B — Layer 3 Implementation Plan**  
**Date:** 2026-04-07  
**Estimated Scope:** 4 addon functions, ~400-600 lines, 3-4 days  
**Prerequisites:** Layer 1 (mcp_memory, mcp_session_search), Layer 2A (context compression - for the system prompt).  
Existing Talos Identity addon system (`identity/addons/`) is the foundation.

---

## 1. Design Philosophy

Hermes's `agent/prompt_builder.py` is 816 lines of imperative prompt assembly. Instead of porting it, express each prompt section as a discrete **identity addon** — a registered function that returns a string injected into the system prompt at a specific phase.

The Julianna persona lives in `IdentityDisc.system_prompt_template`. Addons compose around it, injecting context-specific guidance. This is already how Talos's Identity system works — we're just adding 4 specialized addons that replace Hermes's prompt builder behavior.

---

## 2. Current State: Identity Addon System

Talos already has the addon infrastructure in `identity/`:

- `IdentityAddon` model: name, function reference, phase, conditions
- Phase enum: `BASELINE` → `CONTEXT` → `TERMINAL` → `POST`
- Addon registry: functions that take `(identity_disc, session, context)` and return `str`
- Addon execution: sorted by phase order, results concatenated into the system prompt

We add 4 new addon functions to this system.

---

## 3. Addon 3.1: memory_snapshot_addon

**File:** `identity/addons/memory_snapshot_addon.py` (~100 lines)

**Phase:** `CONTEXT`  
**Purpose:** Query Hippocampus for the IdentityDisc's linked engrams and format them into a memory block injected into the system prompt.

**Specification:**
```python
def memory_snapshot_addon(
    identity_disc: IdentityDisc,
    reasoning_session: ReasoningSession,
    context: dict,
) -> str:
```

**Implementation:**
- Query Engrms linked to this IdentityDisc (via FK or shared tags)
- Two collections: `agent_memory` and `user_profile`
- Filter by `is_active=True`
- Order by most recently modified (most relevant to current conversation)
- Format:
```
## Active Memory

### User Profile
- [snippet 1]
- [snippet 2]

### Agent Notes
- [snippet 1]
- [snippet 2]
- [snippet 3]
```
- Character limit: 1500 chars total for the entire memory block
- If no engrams exist: return empty string (skip this section)

**Why this over Hermes MEMORY.md:** In Hermes, memory is frozen at session start from flat files. Here, memory is live — the addon queries the DB each time, picking up any changes made during the conversation (e.g., if the memory tool added a new entry mid-session).

**Tests:**
- With memory entries: formatted block within 1500 chars
- No memory entries: empty string
- Mixed collections: both sections rendered
- Long entries truncated with ellipsis
- Only active engrams included (is_active=False excluded)

---

## 4. Addon 3.2: skills_index_addon

**File:** `identity/addons/skills_index_addon.py` (~100 lines)

**Phase:** `CONTEXT`  
**Purpose:** Build a compact skill catalog from available skills (SkillEngram records or tagged Engrams) for injection into the system prompt.

**Specification:**
```python
def skills_index_addon(
    identity_disc: IdentityDisc,
    reasoning_session: ReasoningSession,
    context: dict,
) -> str:
```

**Implementation:**
- Query skills: either new `SkillEngram` model or Engrams tagged `skill` (depends on Layer 5 decision)
- Filter by tools enabled for this IdentityDisc: `identity_disc.enabled_tools.all()`
- Format as compact list:
```
## Available Skills

| Skill | Description |
|-------|-------------|
| hermes-agent | Complete guide to using and extending Hermes Agent... |
| coding-tutor | Personalized coding tutorials that build on your existing... |
```
- Character limit: 2000 chars total — enough for ~30-40 skills in compact form
- Only include skills relevant to the current context (if context hints are available)
- If no skills available: return empty string

**Note:** This addon depends on the Layer 5 skills model design decision. The addon logic is the same regardless — only the query changes:
- **Option A (SkillEngram):** `SkillEngram.objects.filter(is_active=True)`
- **Option B (tagged Engrams):** `Engram.objects.filter(tags__name='skill')`

**Tests:**
- With skills: formatted table within 2000 chars
- No skills: empty string
- Skills exceeding char limit: truncated with notice ("...and 5 more")
- Skills filtered by IdentityDisc tool configuration

---

## 5. Addon 3.3: platform_hint_addon

**File:** `identity/addons/platform_hint_addon.py` (~80 lines)

**Phase:** `CONTEXT`  
**Purpose:** Inject platform-specific behavioral guidance based on which gateway adapter initiated the session.

**Specification:**
```python
def platform_hint_addon(
    identity_disc: IdentityDisc,
    reasoning_session: ReasoningSession,
    context: dict,
) -> str:
```

**Implementation:**
- Platform is passed in `context` dict from `talos_gateway`: `context.get('platform')` → one of `'discord'`, `'telegram'`, `'cli'`, etc.
- Platform hints are stored as string constants in this addon module:

```python
PLATFORM_HINTS = {
    'discord': """
## Platform: Discord
- User messages may include attachments, voice audio, and replies.
- Use media delivery for images and audio files (reference with MEDIA: path).
- Responses over 2000 characters will be auto-chunked.
- Voice responses are supported — generate voice if the user sends voice.
""",
    'telegram': """
## Platform: Telegram
- MarkdownV2 formatting is required. Escape: _, *, [, ], (, ), ~, `, >, #, +, -, =, |, {, }, ., !
- Code blocks use triple backticks with language tag.
- Max message length: 4096 characters.
""",
    'cli': """
## Platform: CLI (Terminal)
- Full-length responses are fine (no character limit).
- Code blocks render natively. Markdown and ANSI colors supported.
- Interactive file path completion is available.
""",
}
```
- If platform is not recognized or not set: return empty string
- **Why this matters:** Without platform hints, the model generates responses that don't respect platform constraints (e.g., Markdown on Discord without escaping, or exceeding 4096 chars on Telegram).

**Tests:**
- Discord platform → Discord hint injected
- Unknown platform → empty string
- No context platform key → empty string

---

## 6. Addon 3.4: tool_guidance_addon

**File:** `identity/addons/tool_guidance_addon.py` (~80 lines)

**Phase:** `TERMINAL`  
**Purpose:** For models that need explicit tool-use encouragement, inject guidance about available tools and when to use them.

**Specification:**
```python
def tool_guidance_addon(
    identity_disc: IdentityDisc,
    reasoning_session: ReasoningSession,
    context: dict,
) -> str:
```

**Implementation:**
- Only activates when context indicates a non-tool-oriented model:
  - Check `context.get('model_id')` against a list of models that need tool guidance
  - Models like GPT-4 and Codex sometimes underuse tools without explicit encouragement
  - Strong models (Claude Opus, Claude 4) typically don't need this
- Format:
```
## Available Tools
You have access to the following tools. Use them when:
- **mcp_terminal** — Run shell commands, check progress, inspect files.
- **mcp_fs_write** — Create or modify files.
- **mcp_search_files** — Search files by name or contents.
- ... (list enabled tools)

When you need to accomplish something, prefer using a tool over guessing.
After each action, verify the result before continuing.
```
- List only tools in `identity_disc.enabled_tools.all()`
- Character limit: 1000 chars
- If model is strong enough or no tools available: return empty string

**Model classification logic:**
```python
WEAK_TOOL_USERS = {
    'gpt-4', 'gpt-4o-mini', 'codex',
    'claude-sonnet-3.5',  # sometimes needs encouragement
}
# Models not in this set are assumed to use tools well without prompting
```

**Tests:**
- Weak model + tools available → guidance injected
- Strong model + tools available → empty string
- Weak model + no tools → empty string (nothing to recommend)
- Tool list matches IdentityDisc.enabled_tools exactly

---

## 7. Addon Registration

### 7.1 Database Fixtures

Create `identity/fixtures/layer3_addons.json` to register all 4 addons:

```json
{
  "model": "identity.identityaddon",
  "fields": {
    "name": "memory_snapshot",
    "addon_function": "identity.addons.memory_snapshot_addon.memory_snapshot_addon",
    "phase": 2,
    "description": "Inject active memory entries from Hippocampus",
    "is_active": true
  }
}
```

One fixture row per addon (4 rows total). Phase numbers:
- `memory_snapshot_addon`: phase 2 (CONTEXT)
- `skills_index_addon`: phase 2 (CONTEXT)
- `platform_hint_addon`: phase 2 (CONTEXT)
- `tool_guidance_addon`: phase 3 (TERMINAL)

### 7.2 IdentityDisc Configuration

For the Julianna IdentityDisc, ensure all 4 addons are enabled:
```python
identity_disc.identity_addons.add(*Addon.objects.filter(
    name__in=['memory_snapshot', 'skills_index', 'platform_hint', 'tool_guidance']
))
```

---

## 8. Julianna Persona in IdentityDisc

The Julianna persona itself goes into `IdentityDisc.system_prompt_template`. This is where the core personality, capabilities, and behavioral instructions live:

```
You are Julianna, a CLI AI assistant and coding partner.
[... full Julianna persona definition ...]

## Core Instructions
- Always verify before and after operations
- Prefer building over explaining when implementation is feasible
- Be honest about limitations and uncertainties
- Frame self-care as workflow quality maintenance

## Response Format
- Use markdown code blocks for code
- Use terminal-appropriate formatting
- Keep responses concise and actionable
```

The addons layer on top of this, adding memory context, skill awareness, platform hints, and tool guidance.

---

## 9. Addon Execution Order

When FrontalLobe builds a system prompt, the sequence is:

1. `BASELINE` — IdentityDisc system_prompt_template (Julianna persona)
2. `CONTEXT` — memory_snapshot_addon + skills_index_addon + platform_hint_addon
3. `TERMINAL` — tool_guidance_addon (if applicable)
4. `POST` — Any post-processing addons (none currently, but reserved)

The CONTEXT addons run in registration order. If `memory_snapshot` is registered before `skills_index`, memory appears first in the prompt. This matters because the LLM processes instructions top-to-bottom, with later instructions having slightly higher attention weight.

**Recommended order:** memory_snapshot → skills_index → platform_hint → tool_guidance

---

## 10. File Changes Summary

| File | Action | Est. Lines |
|------|--------|-----------|
| `identity/addons/memory_snapshot_addon.py` | NEW | ~100 |
| `identity/addons/skills_index_addon.py` | NEW | ~100 |
| `identity/addons/platform_hint_addon.py` | NEW | ~80 |
| `identity/addons/tool_guidance_addon.py` | NEW | ~80 |
| `identity/addons/__init__.py` | ENHANCE (register addons) | ~20 |
| `identity/fixtures/layer3_addons.json` | NEW | ~60 |
| `identity/tests/test_addons_layer3.py` | NEW | ~150 |

**Total:** ~590 new lines.

---

## 11. Acceptance Criteria

1. All 4 addons exist and are importable
2. Each addon returns the expected string content for a configured IdentityDisc
3. Each addon returns empty string when conditions aren't met (no memory, no platform, etc.)
4. Addons are registered in DB via fixtures
5. System prompt composition includes all 4 addons in the correct phase order
6. Character limits are respected (memory: 1500, skills: 2000, platform: ~500, tools: 1000)
7. Platform hints correctly differentiate between Discord, Telegram, and CLI contexts
8. Tool guidance activates only for designated weak-tool-use models

---

*End of Layer 3 Plan*
