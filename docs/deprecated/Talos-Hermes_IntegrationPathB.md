   **Core principle:** Talos stays what it is — an orchestration engine with a rich data layer. You add operational self-sufficiency by building
   natively, not by transplanting bad Hermes code. The interactive chat experience is a thin layer on top of Talos, not a second architecture grafted in.

   ---

   **Layer 1: Core MCP Tools (Build ~10, natively)**

   These are the tools FrontalLobe needs to be operationally useful. Not ports — clean implementations against Talos's existing patterns:

   1. **mcp_terminal** — subprocess execution, background process tracking, dangerous command detection. This is ~400 lines of straightforward Python
   regardless of which codebase it lives in.
   2. **mcp_fs_write** — file creation (complements existing mcp_fs_read, mcp_fs_patch, mcp_fs_grep, mcp_fs_list)
   3. **mcp_fs_patch enhancement** — add fuzzy matching strategies to the existing patch tool
   4. **mcp_web_search** — SearXNG wrapper, returns structured results
   5. **mcp_web_extract** — URL to markdown conversion
   6. **mcp_code_exec** — sandboxed Python execution with timeout and output caps
   7. **mcp_browser** — Playwright interaction (navigate, snapshot, click, type, screenshot)
   8. **mcp_memory** — thin adapter mapping add/replace/remove to Hippocampus Engram CRUD, with two tagged collections (agent notes, user profile)
   9. **mcp_session_search** — PostgreSQL full-text search across ReasoningSession/Turn history
   10. **mcp_skill** — skill lookup and loading (design the SkillEngram model first, then build the tool)

   Each gets a ToolDefinition fixture row. IdentityDisc.enabled_tools controls which persona gets which tools. Existing Focus/XP gamification carries
   over automatically.

   **Estimated scope:** ~3,000-4,000 lines total across all 10 tools. 2-3 weeks.

   ---

   **Layer 2: FrontalLobe Enhancements (3 capabilities)**

   These make the reasoning loop production-grade for interactive use:

   1. **Context compression** — New service class. When token usage approaches the model's context window, prune old tool results and LLM-summarize
   the middle of the conversation. FrontalLobe calls this between turns. Works against the ReasoningTurn records in DB rather than in-memory message
   lists.

   2. **Streaming** — Extend SynapseClient to accept a `stream_callback` parameter. When present, LiteLLM streams tokens and the callback fires
   per-chunk. FrontalLobe passes a callback that writes to a Django Channels group. This is the bridge between the reasoning engine and real-time
   delivery.

   3. **Interrupt** — Check Spike.status for STOPPING between turns and between streaming chunks. The gateway sets this flag when the user cancels.
   Clean and simple —

   **Path B: Talos as Brain, Thin Client as Mouth**

   ---

   **Principle:** Talos becomes operationally self-sufficient by building what it
   actually needs natively, not by absorbing Hermes wholesale. The interactive
   conversational layer is a thin skin over the existing FrontalLobe reasoning
   engine.

   ---

   **Layer 1: Core Tool Suite (build 10, skip the rest)**

   Build these as native parietal_mcp modules from scratch:

   1. mcp_terminal — subprocess execution, background process tracking, dangerous
      command detection. Single backend (local) first. Docker/SSH later only if
      needed for NerveTerminal dispatch.

   2. mcp_fs_write — file creation (complements existing mcp_fs_read, mcp_fs_patch,
      mcp_fs_grep, mcp_fs_list which already exist).

   3. mcp_fs_patch enhancement — port the 9-strategy fuzzy matching from Hermes.
      This is genuinely useful and only ~300 lines of algorithm code.

   4. mcp_web_search — Tavily or SearXNG wrapper. Straightforward API client.

   5. mcp_web_extract — URL to markdown extraction. Can use trafilatura or similar.

   6. mcp_code_exec — sandboxed Python execution. Write-execute-capture pattern
      with timeout and output limits.

   7. mcp_memory — thin interface over Hippocampus Engrams that presents the
      add/replace/remove operations familiar from Hermes, but stored as proper
      Engrams with vector embeddings and relational links.

   8. mcp_session_search — PostgreSQL full-text search across ReasoningSession
      and ReasoningTurn history. Replaces SQLite FTS5.

   9. mcp_browser — Playwright with accessibility tree snapshots. Navigate, click,
      type, scroll, screenshot+vision. This is the most complex single tool.

   10. mcp_vision — image analysis via multi-provider API. Relatively simple
       HTTP wrapper.

   ToolDefinition fixtures for all 10, registered in DB.

   **What you skip:** image generation, TTS, GIF search, polymarket, find-nearby,
   send_message (cross-platform), homeassistant, transcription, MCP bridge,
   mixture-of-agents, RL training tool. Build any of these later if a specific
   workflow demands it.

   ---

   **Layer 2: FrontalLobe Enhancements (make reasoning production-grade)**

   Three additions to the existing FrontalLobe.run() loop:

   A. **Context compression.** When approaching the model's context window, prune
      old tool results first, then LLM-summarize the middle of conversation
      history. This is a new service class called from _execute_turn() when token
      count exceeds a threshold. The compressed history replaces the original
      ReasoningTurn records (or gets stored as a summary turn).

   B. **Streaming.** Extend SynapseClient to accept a stream_callback parameter.
      When provided, LiteLLM streams token-by-token and SynapseClient calls the
      callback with each delta. FrontalLobe passes a callback that sends to a
      Django Channels group. This is the critical bridge between the reasoning
      engine and the interactive layer.

   C. **Interrupt.** Between streaming chunks and between tool calls, check
      Spike.status for STOPPING. If set, gracefully terminate the conversation.
      This already half-exists in the CNS stop_gracefully path but needs to
      propagate into FrontalLobe's inner loop.

   ---

   **Layer 3: Identity Addons (replace prompt builder with addon functions)**

   Instead of porting Hermes's 816-line prompt_builder.py, express each prompt
   section as an identity addon:

   - memory_snapshot_addon — queries Hippocampus for the IdentityDisc's linked
     engrams, formats them into a memory block, injects at CONTEXT phase
   - skills_index_addon — builds compact skill catalog from SkillEngram records
     (or tagged engrams), injects at CONTEXT phase
   - platform_hint_addon — injects platform-specific instructions based on which
     gateway adapter initiated the session, CONTEXT phase
   - tool_guidance_addon — for models that need explicit tool-use encouragement,
     TERMINAL phase

   The Julianna persona itself lives in IdentityDisc.system_prompt_template.
   The addons compose around it.

   ---

   **Layer 4: Interactive Gateway (new, thin, Channels-native)**

   This is NOT a port of Hermes's gateway/run.py. It is a new ~500-line Channels
   consumer:

   **talos_gateway app structure:**
   ```
   talos_gateway/
     consumers.py      — WebSocket consumer for interactive sessions
     adapters/
       base.py          — BasePlatformAdapter (translate platform ↔ Stimulus)
       cli.py           — Local terminal WebSocket client
       discord.py       — discord.py bot → WebSocket bridge
       telegram.py      — python-telegram-bot → WebSocket bridge
     session_store.py   — Redis-backed session state (active IdentityDisc,
                          conversation history pointer, interrupt flag)
     delivery.py        — Route FrontalLobe output to the right adapter
   ```

   **The key design decision:** Interactive sessions do NOT go through Celery.
   The WebSocket consumer creates a FrontalLobe instance and runs it synchronously
   in the ASGI thread with streaming callbacks. This gives you sub-second token
   delivery without fighting Celery's task queue model.

   Graph-based orchestration (CNS NeuralPathways, SpikeTrain dispatch) still
   uses Celery. The two paths coexist cleanly because they enter FrontalLobe
   through different doors but use the same reasoning engine.

   **The CLI** is a standalone Python script (~200 lines) that connects to
   Talos's Daphne WebSocket endpoint, sends user messages, receives streamed
   tokens, and renders them in the terminal. Not a port of Hermes's cli.py.

   ---

   **Layer 5: Skills as Knowledge (design decision needed)**

   Two options, recommend deciding before implementation:

   **Option A: SkillEngram model** — new model with name, description, body
   (markdown), yaml_frontmatter (JSON), plus FileAttachment records for
   scripts/templates/references. Vector-embedded for semantic retrieval.
   Clean, typed, queryable.

   **Option B: Tagged Engrams with convention** — use regular Engrams tagged
   "skill", store SKILL.md content in description, store metadata in a JSON
   field. Simpler, no new model, but less type-safe.

   Either way, the existing ~/.hermes/skills/ directory gets a one-time migration
   script that creates the records.

   ---

   **Sequencing:**

   ```
   Week 1-2:  Layer 1 (core tools) — terminal, file ops, web, code exec
   Week 3:    Layer 1 continued (browser, vision) + Layer 2A (compression)
   Week 4:    Layer 2B+C (streaming + interrupt) + Layer 3 (addons)
   Week 5-6:  Layer 4 (gateway + CLI adapter)
   Week 7:    Layer 4 (Discord adapter) + Layer 5 (skills)
   Week 8:    Integration testing, migration scripts, stabilization
   ```

   8 weeks instead of 16. Half the scope, all of the value.

   ---

   **What Hermes remains:** A reference implementation you can consult for
   behavioral details (how does fuzzy patching handle indentation? what regex
   patterns detect dangerous commands?) but not a codebase you are merging.
   It stays running as-is during the build. Once Talos's interactive path
   is validated, Hermes goes read-only.