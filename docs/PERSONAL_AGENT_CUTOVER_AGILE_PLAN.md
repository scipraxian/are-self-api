# Personal Agent Cutover Agile Plan

Date: 2026-04-12
Branch analyzed: `claude/gallant-maxwell`
Scope: Talos as the primary personal-agent runtime delivered through CLI, Discord, and the Are-Self web app with a user experience comparable to Hermes/OpenClaw, while preserving Talos-native advantages.

## Executive Summary

The codebase is no longer at the “should we do this?” stage. It is already in the “finish the productization and cutover path” stage.

After analyzing the current Talos working tree, the state is this:

- Talos already has most of the core personal-agent primitives.
- The reasoning substrate is stronger and more modular than Hermes/OpenClaw.
- The system already contains Talos-native implementations for memory, session search, skills CRUD, browser/code/web/terminal tools, prompt addons, token streaming, and gateway/session scaffolding.
- The remaining gap is not conceptual architecture. The remaining gap is end-to-end integration, adapter completion, orchestration wiring, UX delivery consistency, and production hardening.

In plain language: the “brain” is mostly there. The “nervous system” is partly there. The “body” that users actually inhabit across CLI, Discord, and web is still incomplete.

## Target Product Definition

The target state is a Talos-native personal agent that:

- accepts user messages from CLI, Discord, and Are-Self web UI
- binds each platform thread/channel/session to a persistent Talos `ReasoningSession`
- streams token deltas live to the client
- uses Talos-native tool execution through Parietal MCP
- uses Talos-native memory through Hippocampus
- uses Talos-native skill retrieval and management
- uses Talos-native model routing through Hypothalamus
- uses Talos-native prompt composition through Identity addons
- can deliver plain text, chunked long-form messages, voice/TTS, and media safely
- feels like one coherent personal-agent runtime rather than a collection of disconnected subsystems

## What Is Already Implemented

### 1. Core personal-agent tools exist inside Talos

Under `parietal_lobe/parietal_mcp/`, the branch already contains a large Hermes-style tool surface, including:

- `mcp_memory`
- `mcp_session_search`
- `mcp_code_exec`
- `mcp_browser`
- `mcp_terminal`
- `mcp_web_search`
- `mcp_web_extract`
- filesystem + fuzzy patching
- `mcp_vision`
- `mcp_skill_manage`
- `mcp_skill_view`
- `mcp_skills_list`

This means the system already has real internal operator capabilities, not just placeholders.

### 2. Memory is Talos-native already

`mcp_memory.py` delegates to `mcp_memory_sync.py`, which maps memory actions into Hippocampus Engrams rather than using an external flat-file memory store.

That is a major milestone. Personal memory is already being absorbed into Talos’ own substrate.

### 3. Session search is real and fairly mature

`mcp_session_search.py` searches:

- `ToolCall` rows
- `ReasoningTurn` ledgers / model usage payloads

It supports:

- role filtering (`user`, `assistant`, `tool`)
- PostgreSQL full-text search
- SQLite fallback behavior
- ranking/scoring
- request/response corpus extraction and refinement

This is not stub logic. It is real recall/search infrastructure.

### 4. Skills are farther along than earlier summary docs imply

The working tree contains:

- `mcp_skill_manage.py`
- `mcp_skill_manage_sync.py`
- `mcp_skill_view.py`
- `mcp_skill_view_sync.py`
- `mcp_skills_list.py`
- `mcp_skills_list_sync.py`
- `parietal_lobe/tests/test_skills_tools.py`

The branch therefore already has skill CRUD/list/view behavior implemented against Talos/Hippocampus models.

### 5. Identity-layer prompt parity is real

`identity/addons/addon_registry.py` includes the key personal-agent-oriented addons:

- `memory_snapshot_addon`
- `skills_index_addon`
- `platform_hint_addon`
- `tool_guidance_addon`

This means prompt composition is already Talos-native and aware of memory, skills, and platform context.

### 6. Context compression exists

`frontal_lobe/context_compressor.py` contains real context pressure management:

- token estimation
- tool-output pruning
- summary insertion
- aggressive fallback pruning
- idempotence handling

This is important for maintaining long-lived personal-agent sessions.

### 7. Gateway/session/token-streaming foundation exists

The `talos_gateway/` app already includes:

- `gateway.py` orchestrator
- `session_manager.py`
- `message_router.py`
- `delivery.py`
- `stream_consumer.py`
- `ws_protocol.py`
- adapter modules for CLI, Discord, Signal, Webhook
- tests for gateway/session/stream behavior

There is already a WebSocket flow at `/ws/gateway/stream/` that:

- accepts inbound messages
- normalizes them into `PlatformEnvelope`
- routes them through the active gateway orchestrator
- persists them into `ReasoningSession.swarm_message_queue`

There is also Frontal Lobe channel-stream support via:

- `frontal_lobe/channels_streaming.py`
- `TokenChannelSender`
- `stream_to_channels=True`

So token streaming infrastructure exists.

### 8. Voice/STT/TTS substrate exists

`vocal_auditory_cortex/` already provides:

- `stt.py`
- `tts.py`
- provider modules for `edge`, `elevenlabs`, `voxtral`, `faster_whisper`, etc.

So voice is not just a future idea. The provider abstraction layer is already in the codebase.

## What Is Not Complete Yet

## 1. The gateway does not yet complete the full reasoning loop

This is the biggest current product gap.

Right now the gateway can:

- create/resolve session mappings
- queue inbound messages into `swarm_message_queue`
- expose a WebSocket path for inbound payloads
- support token streaming infrastructure

But the current gateway tests explicitly assert that the Phase 1 gateway modules do **not** invoke `FrontalLobe` or `fire_spike` directly.

That means the gateway is currently a session-and-queue transport layer, not yet the fully wired personal-agent runtime entrypoint.

In practical terms: user input can enter Talos, but the branch does not yet demonstrate a complete “message in -> Talos reasons -> response out” path through the gateway itself.

## 2. CLI and Discord adapters are still largely transport stubs

The adapters exist, but the important ones are not fully wired.

Examples:

- `talos_gateway/adapters/cli_adapter.py` is explicitly a minimal stub transport
- `talos_gateway/adapters/discord_adapter.py` is explicitly a stub until Discord SDK wiring lands

So the platform abstraction is there, but the user-facing platform integrations are not finished.

## 3. The web app path exists at the transport layer, but not yet as a complete product experience

The Are-Self web app integration path is promising because:

- ASGI includes `talos_gateway.routing`
- `/ws/gateway/stream/` exists
- session-based token group streaming exists

But this is still low-level transport infrastructure, not a complete web personal-agent experience. The following still needs explicit productization:

- authenticated browser session binding
- front-end session lifecycle UX
- reconnect/resume behavior
- render semantics for tool calls / thoughts / streamed answers
- web-native controls for interrupts, attachments, and voice

## 4. External MCP exposure is not unified with internal Parietal MCP

The codebase currently has two related but distinct stories:

1. internal personal-agent tool execution under `parietal_lobe/parietal_mcp/`
2. external MCP server at `/mcp` via `mcp_server/`

The `/mcp` server registers domain-oriented tool sets (`cns_tools`, `identity_tools`, `environment_tools`, etc.), but the working tree does not yet show a clean unification where the full personal-agent tool surface is exposed through the same outward-facing MCP interface.

This is a major integration seam.

## 5. Voice/media delivery is not yet fully connected to platform adapters

The voice substrate exists, and delivery payloads include `is_voice` and `voice_audio_path`, but the end-to-end platform behavior is not complete:

- adapter-specific media upload behavior is not fully wired
- TTS narration policies are not fully productized
- Discord/media attachment parity is not evidently complete
- STT inbound voice handling is not shown as fully platform-integrated

## 6. Runtime hardening and production validation are still incomplete

The code has many tests, but there are still operational gaps for cutover:

- environment-specific provider validation
- process lifecycle robustness
- long-session load behavior
- failure recovery across adapters
- multi-platform concurrency validation
- true end-to-end acceptance tests from adapter -> reasoning -> tools -> delivery

## 7. Some docs are already stale relative to the code

For example, earlier progress documentation understates skills progress. That matters because stale planning docs make cutover sequencing less reliable.

## Architectural Diagnosis

Talos is already superior as the long-term personal-agent substrate because it gives:

- better modularity
- stronger persistence models
- cleaner subsystem ownership
- richer model routing
- native memory abstractions
- stronger path toward multi-agent / graph-based orchestration

The remaining work is therefore mostly about operational integration and user-surface coherence.

This should be treated as a cutover program, not a research project.

---

# Agile Delivery Plan

The following backlog is organized as Agile epics, features, stories, tasks, dependencies, and acceptance criteria.

The intent is to drive Talos from “personal-agent-capable infrastructure” to “complete personal-agent product.”

## Program Goal

Deliver a Talos-native personal agent that provides Hermes/OpenClaw-like live conversational experience through:

- CLI
- Discord
- Are-Self web app

while using Talos-native:

- reasoning
- memory
- skills
- routing
- tool execution
- streaming
- identity
- voice

## Definition of Done for the Program

The program is complete when all of the following are true:

- A user can message Talos from CLI, Discord, or web UI and receive a live streamed answer.
- The same Talos personal-agent behavior is preserved across all adapters.
- Session continuity, memory, and skills work consistently across surfaces.
- Tool calls are executed through Talos-native Parietal MCP.
- Long responses are chunked safely and delivered correctly.
- Voice input/output works on at least one platform path end-to-end.
- Interrupts, retries, and session recovery behave predictably.
- End-to-end tests prove the personal-agent loop works.

---

## Epic 1: Complete the Personal-Agent Runtime Loop

### Objective
Turn gateway transport/session plumbing into a complete Talos personal-agent loop.

### Why this matters
This is the single biggest gap between current infrastructure and actual product behavior.

### Stories

#### Story 1.1 — Define the canonical gateway-to-reasoning entrypoint
Tasks:
- identify the single canonical path that should wake Talos reasoning for a gateway session
- decide whether gateway triggers `FrontalLobe.run`, a CNS spike, or a Thalamus-mediated orchestration layer
- document the decision and remove competing entrypoint ambiguity

Acceptance criteria:
- one documented entrypoint exists for adapter-driven personal-agent interactions
- no parallel ambiguous runtime paths remain for the same product surface

Dependencies:
- none

#### Story 1.2 — Wire inbound gateway messages into active reasoning execution
Tasks:
- connect `swarm_message_queue` ingestion to actual session wake-up
- ensure queued user messages are consumed in deterministic order
- ensure no duplicate wake-ups occur for the same session/channel
- ensure idle sessions can resume when new messages arrive

Acceptance criteria:
- inbound adapter message causes Talos reasoning to run without manual intervention
- response generation begins after queue insertion
- repeated inbound messages during an active turn are handled safely

Dependencies:
- Story 1.1

#### Story 1.3 — Wire outbound assistant responses back through gateway delivery
Tasks:
- define the canonical outbound emission path from reasoning result to `DeliveryService`
- support both streamed deltas and final message completion
- support reply threading metadata consistently across adapters

Acceptance criteria:
- assistant response arrives on originating platform without out-of-band glue
- final answer delivery is platform-correct and session-correct

Dependencies:
- Story 1.2

#### Story 1.4 — Add interrupts/cancel semantics for live sessions
Tasks:
- expose session interruption through CLI/web/Discord surface actions
- map interrupt to existing Frontal Lobe interruption logic
- ensure partial assistant output is handled consistently

Acceptance criteria:
- user can interrupt an in-flight response
- session is left in a recoverable state
- next user turn can continue cleanly

Dependencies:
- Story 1.2

---

## Epic 2: Make CLI a First-Class Personal-Agent Surface

### Objective
Turn the existing CLI transport into a complete daily-driver experience.

### Why this matters
CLI is the fastest path to a fully operational reference implementation.

### Stories

#### Story 2.1 — Replace CLI adapter stub with a real local transport
Tasks:
- define the actual CLI runtime contract
- implement inbound event loop / outbound rendering path
- support streamed token display
- support message IDs, session IDs, and reconnect semantics

Acceptance criteria:
- CLI adapter is no longer a stub
- local user can hold a multi-turn conversation through the gateway
- streamed token updates render correctly

Dependencies:
- Epic 1

#### Story 2.2 — Add CLI UX for session lifecycle
Tasks:
- support session create/select/resume
- show current session identity / target channel context
- expose status for model/tool activity where appropriate

Acceptance criteria:
- CLI user can manage personal-agent sessions intentionally
- session continuity is obvious and inspectable

Dependencies:
- Story 2.1

#### Story 2.3 — Add CLI controls for interrupts, voice, and attachments
Tasks:
- add interrupt command
- add file attach / artifact receive path
- add voice-output toggle if TTS is enabled

Acceptance criteria:
- CLI supports core personal-agent controls beyond plain text

Dependencies:
- Story 2.1

---

## Epic 3: Deliver a Real Discord Personal-Agent Experience

### Objective
Turn the Discord adapter from scaffold to production-capable platform integration.

### Why this matters
Discord is one of the clearest benchmarks for Hermes/OpenClaw-like personal-agent UX.

### Stories

#### Story 3.1 — Implement real Discord adapter transport
Tasks:
- wire Discord SDK lifecycle into `DiscordAdapter.start/stop`
- implement inbound message parsing into `PlatformEnvelope`
- support channels, DMs, and threads as needed

Acceptance criteria:
- Discord inbound messages reach Talos through the adapter
- adapter maintains platform identity and thread metadata

Dependencies:
- Epic 1

#### Story 3.2 — Implement robust Discord outbound delivery
Tasks:
- support chunked text delivery respecting Discord limits
- preserve formatting and code fences
- support reply-to semantics and thread delivery

Acceptance criteria:
- long responses deliver correctly
- code blocks are not mangled
- thread routing is correct

Dependencies:
- Story 3.1

#### Story 3.3 — Implement Discord media and voice parity
Tasks:
- support attachment upload/download path
- support voice/TTS delivery where intended
- support future STT inbound voice path if desired

Acceptance criteria:
- Discord can deliver Talos-generated voice/media outputs end-to-end

Dependencies:
- Story 3.2

#### Story 3.4 — Add Discord operational hardening
Tasks:
- handle rate limits
- handle reconnects
- handle bot auth/config errors gracefully
- add observability for failed sends and dropped sessions

Acceptance criteria:
- Discord adapter remains stable under normal platform failure conditions

Dependencies:
- Story 3.1

---

## Epic 4: Deliver the Are-Self Web Personal-Agent Experience

### Objective
Turn the existing websocket/session foundations into a coherent in-app personal-agent UX.

### Why this matters
The web app is the most important long-term integrated surface for Talos itself.

### Stories

#### Story 4.1 — Define web session model and authentication behavior
Tasks:
- decide how browser identity maps to Talos `GatewaySession` and `ReasoningSession`
- define authenticated vs anonymous session rules
- define session persistence/reconnect behavior

Acceptance criteria:
- web session behavior is explicitly documented
- browser reconnects preserve or intentionally rotate sessions

Dependencies:
- Epic 1

#### Story 4.2 — Build complete websocket-driven chat loop for web UI
Tasks:
- wire front-end events to `/ws/gateway/stream/`
- support streamed tokens, acknowledgments, and error frames
- support final message completion state

Acceptance criteria:
- web app can act as a live Talos personal-agent client
- streamed responses render in real time

Dependencies:
- Story 4.1

#### Story 4.3 — Build personal-agent UX components in the web app
Tasks:
- show live streaming state
- show tool-use / status events appropriately
- show session identity and memory/skill context where useful
- add retry / interrupt / reconnect controls

Acceptance criteria:
- web app personal-agent UX feels coherent and intentional
- users can understand what Talos is doing while it reasons

Dependencies:
- Story 4.2

#### Story 4.4 — Add web-native attachments and voice support
Tasks:
- support browser file upload path
- support returned artifacts/media
- support microphone/STT path if in scope
- support browser audio playback for TTS

Acceptance criteria:
- web UI supports a modern multimodal personal-agent interaction path

Dependencies:
- Story 4.2

---

## Epic 5: Unify Internal Parietal MCP and External MCP Story

### Objective
Eliminate the split between Talos’ internal personal-agent tools and its outward-facing MCP surface.

### Why this matters
A fragmented tool story will slow both developer adoption and product coherence.

### Stories

#### Story 5.1 — Define canonical tool surface model
Tasks:
- decide relationship between `parietal_lobe/parietal_mcp/` and `mcp_server/`
- define which tools are internal-only, external-only, or shared
- document schema ownership and registration pattern

Acceptance criteria:
- one clear tool architecture exists
- developers can explain where a tool belongs without ambiguity

Dependencies:
- none

#### Story 5.2 — Expose personal-agent tools through the canonical registration path
Tasks:
- register shared personal-agent tools through a single source of truth
- avoid duplicated schema drift between internal and external MCP definitions

Acceptance criteria:
- shared tools no longer require dual manual maintenance

Dependencies:
- Story 5.1

#### Story 5.3 — Validate tool parity and permissions model
Tasks:
- define safe exposure rules for browser/fs/terminal/code/memory tools
- define adapter/platform-dependent capability restrictions
- add tests for disallowed or dangerous paths

Acceptance criteria:
- tool exposure is deliberate, safe, and test-covered

Dependencies:
- Story 5.2

---

## Epic 6: Finalize Skill-System Operationalization

### Objective
Move skills from “implemented storage + CRUD” to “full personal-agent runtime capability.”

### Why this matters
Skills are one of the defining features of the Hermes/OpenClaw-style personal-agent experience.

### Stories

#### Story 6.1 — Audit and normalize skill data model usage
Tasks:
- reconcile `SkillEngram` usage with older Engram-tag skill paths
- define canonical skill retrieval strategy in prompt/runtime flow
- remove stale or duplicate skill-path assumptions

Acceptance criteria:
- skills have one canonical runtime model and retrieval path

Dependencies:
- none

#### Story 6.2 — Strengthen runtime skill selection behavior
Tasks:
- ensure skills surface at the right time in prompt composition
- define whether retrieval is tool-aware, semantic, explicit, or hybrid
- tune truncation and ranking behavior

Acceptance criteria:
- relevant skills reliably appear in personal-agent sessions
- irrelevant skill spam is minimized

Dependencies:
- Story 6.1

#### Story 6.3 — Add end-to-end skill authoring/use feedback loop
Tasks:
- support “create skill from solved workflow” inside the runtime
- support viewing/updating skills from the personal-agent surfaces
- support future UI affordances for skill inspection

Acceptance criteria:
- users can create and benefit from Talos skills through the agent experience itself

Dependencies:
- Story 6.2

---

## Epic 7: Finish Voice and Multimodal Delivery

### Objective
Make STT/TTS/media a coherent part of the personal-agent product rather than a disconnected subsystem.

### Why this matters
Voice and media are key differentiators for a modern personal agent.

### Stories

#### Story 7.1 — Define voice product behavior
Tasks:
- specify when TTS should be automatic vs optional
- specify which adapters support audio output first
- specify whether STT is synchronous, uploaded-file based, or live-stream based

Acceptance criteria:
- voice product behavior is clearly documented and consistent

Dependencies:
- none

#### Story 7.2 — Wire TTS into adapter delivery path
Tasks:
- integrate `vocal_auditory_cortex/tts.py` into gateway outbound flow
- define payload construction for voice replies
- implement adapter-specific handling

Acceptance criteria:
- Talos can emit a spoken reply through at least one target surface end-to-end

Dependencies:
- Epic 1

#### Story 7.3 — Wire STT into inbound adapter flow
Tasks:
- define upload/transcription path for supported platforms
- integrate `vocal_auditory_cortex/stt.py` into inbound normalization

Acceptance criteria:
- Talos can accept voice input through at least one surface end-to-end

Dependencies:
- Story 7.1

#### Story 7.4 — Support media/artifact delivery semantics
Tasks:
- define attachment lifecycle
- define cache/storage policy
- define artifact references inside responses

Acceptance criteria:
- user-visible artifacts are delivered consistently and recoverably

Dependencies:
- Story 7.2

---

## Epic 8: Reliability, Observability, and Production Hardening

### Objective
Make the personal-agent runtime operationally trustworthy.

### Why this matters
Without hardening, the product will feel clever but unreliable.

### Stories

#### Story 8.1 — Add end-to-end acceptance test matrix
Tasks:
- adapter -> session -> reasoning -> tools -> response tests
- streaming tests
- interruption tests
- long-message/chunking tests
- memory persistence tests

Acceptance criteria:
- test suite proves the full personal-agent loop works

Dependencies:
- Epics 1-4 at minimum for each relevant surface

#### Story 8.2 — Add runtime observability
Tasks:
- standardize logs across gateway, adapters, streaming, tool execution, and memory
- add correlation IDs/session tracing
- add admin or API observability views if needed

Acceptance criteria:
- operators can diagnose session failures without guesswork

Dependencies:
- Epic 1

#### Story 8.3 — Add failure recovery behavior
Tasks:
- adapter reconnect handling
- websocket reconnect handling
- session timeout and resume policies
- stuck-turn detection and cleanup

Acceptance criteria:
- normal failure scenarios do not silently strand the user

Dependencies:
- Epic 1

#### Story 8.4 — Validate performance under long-running use
Tasks:
- long-session memory growth checks
- streaming throughput checks
- concurrent session checks
- context compression behavior under stress

Acceptance criteria:
- Talos remains stable under sustained personal-agent usage

Dependencies:
- Epics 1, 2, 4

---

## Recommended Sequencing

### Phase A — Finish the runtime loop
Do first:
- Epic 1
- Epic 2

Rationale:
CLI should become the reference implementation. If the personal-agent loop is not complete there, every other surface will be slower and more confusing.

### Phase B — Turn web into the flagship surface
Do second:
- Epic 4
- Epic 6

Rationale:
Once the runtime loop is real, the web app should become the best demonstration of Talos-native personal-agent UX.

### Phase C — Ship real platform parity
Do third:
- Epic 3
- Epic 7

Rationale:
Discord and voice should be built on the already-proven runtime, not used to discover the runtime shape.

### Phase D — Unify and harden
Do fourth:
- Epic 5
- Epic 8

Rationale:
Tool-surface unification and operational hardening are critical before full cutover and external-facing confidence.

---

## Highest-Priority Immediate Backlog

If only the next few sprints are considered, these are the most important tasks:

### Sprint 1
- finalize canonical gateway-to-reasoning entrypoint
- wire queue ingestion to actual reasoning wake-up
- prove end-to-end CLI message -> reasoning -> response path
- document runtime flow clearly

### Sprint 2
- replace CLI adapter stub with real transport behavior
- support outbound streaming and final message completion in CLI
- validate memory/skill behavior inside live CLI sessions

### Sprint 3
- productize web websocket session behavior
- deliver streamed Are-Self web personal-agent experience
- add interrupt/reconnect controls

### Sprint 4
- implement real Discord transport
- implement Discord delivery chunking/media behavior
- add end-to-end acceptance tests for CLI + web + Discord

---

## Major Risks

### Risk 1: Two orchestration paths emerge
If gateway interactions and internal Talos interactions use different wake-up paths, behavior drift will accumulate quickly.

Mitigation:
- choose one canonical personal-agent runtime entrypoint now

### Risk 2: Tool architecture remains split
If `parietal_mcp` and `/mcp` continue to drift, maintenance cost and developer confusion will rise.

Mitigation:
- unify registration ownership and shared tool schema policy

### Risk 3: Platform adapters become thin wrappers around ad hoc logic
If adapter behavior leaks business logic into platform modules, the platform story will become hard to maintain.

Mitigation:
- keep adapters transport-focused, keep runtime behavior centralized

### Risk 4: Web UX lands before runtime semantics are stable
If the UI is built against unstable orchestration behavior, rework cost will rise sharply.

Mitigation:
- complete CLI reference loop first

### Risk 5: Voice/media adds complexity before text loop is stable
Voice can introduce a great deal of state and adapter complexity.

Mitigation:
- treat voice as Phase C, not Phase A

---

## Product Readiness Verdict

Current state: strong internal substrate, incomplete personal-agent product.

The branch has already done the hard architectural part. Talos has most of the important raw materials needed to surpass Hermes/OpenClaw in long-term design quality. The missing work is mostly the engineering work required to make it feel unified, live, reliable, and user-facing.

That is good news.

It means Talos does not need a new conceptual redesign. It needs a disciplined cutover program.

## Recommended Next Decision

The next architectural decision that should be made explicitly is this:

**What is the single canonical runtime path for adapter-driven personal-agent messages?**

Until that is fixed and implemented, the rest of the product work will remain partially blocked by orchestration ambiguity.

Once that is settled, the fastest path is:

1. finish CLI end-to-end
2. finish web end-to-end
3. finish Discord end-to-end
4. unify external MCP/tool story
5. harden and cut over
