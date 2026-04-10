# Are-Self API — Tasks

Remaining work, sifted for the backend. See FEATURES.md for what's built.

## Release Day Update (April 7, 2026)

**Gemma4 rollback:** Gemma4 changed its output format, breaking the Frontal Lobe reasoning loop.
Empirical testing showed Qwen outperformed Gemma4 on the Are-Self framework. Rolled back to Qwen
for release. A parser is being developed to handle Gemma4's new output format post-release.

**OpenRouter sync restored:** The OpenRouter provider sync feature has been brought back but is
untested. Shipping with this feature enabled — needs documentation in are-self-docs.

**READMEs updated:** All four repo READMEs have been updated for release.

## Top Priority — Release Day Documentation (April 7, 2026)

Documentation is the release-day focus. The Docusaurus site has 34 solid pages and 11 UI walkthrough
stubs. See "Ship-Blocking — Documentation Infrastructure" below. Docstrings and drf-spectacular are
also ship-blocking for the API reference.

## Top Priority — Funding & Sponsorship Infrastructure

- [ ] **Set up GitHub FUNDING.yml.** Create `.github/FUNDING.yml` in are-self-api (org-level). Populate
  with active platform usernames. Platforms to evaluate and set up accounts on:
  - **GitHub Sponsors** (`github: scipraxian`) — native to where the code lives, lowest friction
  - **Ko-fi** — no fees on donations, good for one-time tips, easy setup
  - **Buy Me a Coffee** — similar to Ko-fi, large casual donor base
  - **Patreon** — recurring memberships, good for building a community tier
  - **Open Collective** — transparent finances, good for open-source credibility
  - **Polar** — built for open-source, ties funding to issues/features
  - **LFX Crowdfunding** — Linux Foundation backed, good for institutional credibility
  - **Custom links** — PayPal.me, Venmo, or direct donation page on are-self.com
  Each platform added to FUNDING.yml creates a "Sponsor" button on the GitHub repo. More platforms =
  more eyeballs. Priority: GitHub Sponsors + Ko-fi first, then expand.
- [ ] **Add donation/sponsor links to docs site.** Add a "Support Are-Self" page or section to the
  Docusaurus site with all funding links. Also add to the Discord welcome message.
- [ ] **Explore 501(c)(3) path with Len Lanzi.** Long-term: tax-deductible donations unlock
  institutional and grant funding. Len is the nonprofit connection.

## Top Priority — Remove Legacy `central_nervous_system/` URL Prefix

- [ ] **The `/central_nervous_system/` URL prefix must GO.** It's a legacy holdover living in the
  wrong place from the old pre-`/api/v2/` routing scheme. The app itself stays (that's the CNS
  brain region); only the URL prefix needs to die. Migrate any still-live endpoints onto
  `/api/v2/` and delete `central_nervous_system.urls.urls` from `config/urls.py`.
- [ ] **After removal, touch nginx again.** `are-self-api/nginx/entrypoint.sh` currently has a
  `location /central_nervous_system/` block proxying to Daphne. Delete that block once the
  Django side is cleaned up, and `docker compose restart nginx` to pick it up.

## Top Priority — PNS Expansion

- [ ] **Multiple Ollama endpoints.** Secondary machine running Ollama should be usable. These are
  **AIModelProviders** — the Hypothalamus already supports multiple providers per model. Add a second
  AIModelProvider record pointing to the secondary machine's `host:port`. The failover strategy handles
  routing. May need a UI affordance in the Hypothalamus to add/edit provider endpoints. Create a scanner
  similar to the scan for agents executable.
- [ ] **Live agent monitoring.** PNS should show active reasoning agents — which IdentityDiscs are
  currently in a session, what they're doing, session duration, turn count. Real-time via existing
  dendrite infrastructure.

## NGINX & MCP Follow-ups

- [ ] **IPv6 upstream noise in nginx logs.** `host.docker.internal` resolves to both IPv4 and
  IPv6; nginx tries the IPv6 address first, fails (`[fdc4:f303:9324::254]:8000 failed`), and
  falls back to IPv4 successfully. Harmless but noisy. Fix by pinning `resolver` to IPv4 only
  in `nginx/entrypoint.sh`, or by using `host-gateway` with an explicit IPv4 alias.
- [ ] **Set up Cloudflare Tunnel so Cowork can reach the MCP (Michael's personal box).**
  Cowork's custom connector flow fetches the endpoint from Anthropic's cloud, so `127.0.0.1`
  is unreachable. Cloudflare Tunnel gives us a publicly-routable hostname backed by an
  outbound-only connection from the local machine — no router/firewall changes, no public
  IP exposure. Steps:
  1. Install `cloudflared` on Windows (MSI from
     `https://github.com/cloudflare/cloudflared/releases` — `cloudflared-windows-amd64.msi`).
     Verify: `cloudflared --version`.
  2. `cloudflared tunnel login` — opens browser, pick `are-self.com`, writes
     `%USERPROFILE%\.cloudflared\cert.pem` (the account credential).
  3. `cloudflared tunnel create are-self-mcp` — prints a UUID and writes
     `%USERPROFILE%\.cloudflared\<uuid>.json` (the tunnel credential).
  4. Create `%USERPROFILE%\.cloudflared\config.yml`:
     ```yaml
     tunnel: are-self-mcp
     credentials-file: C:\Users\micha\.cloudflared\<uuid>.json
     ingress:
       - hostname: mcp.are-self.com
         service: https://local.are-self.com
         originRequest:
           noTLSVerify: false
       - service: http_status:404
     ```
     The origin is `https://local.are-self.com` (not `localhost`) so cloudflared hits the
     upstream with a hostname that matches our real ZeroSSL cert — strict TLS verify stays on.
  5. `cloudflared tunnel route dns are-self-mcp mcp.are-self.com` — creates a Cloudflare
     CNAME to `<uuid>.cfargotunnel.com`. Record is proxied (orange cloud) automatically,
     which is correct for tunnels (unlike the grey-cloud `local.are-self.com` A record).
  6. Foreground test: `cloudflared tunnel run are-self-mcp`, then
     `Invoke-RestMethod -Uri https://mcp.are-self.com/mcp -Method Post -ContentType application/json -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'`
     should return the same 14 tools as the direct-local probe.
  7. Service install (runs on boot, no terminal): `cloudflared service install`.
  8. Add `https://mcp.are-self.com/mcp` as a custom connector in the claude.ai Connectors
     UI. Are-Self must be running (`are-self.bat` + `docker compose up -d`) for Cowork to
     get responses — tunnel alone doesn't start the stack.
  **Per-user only.** This is not a distribution mechanism; each Are-Self user who wants
  Cowork access would have to run their own tunnel with their own subdomain. A real
  shareable "Cowork connects to Are-Self" story is still open and is NOT this task.
- [ ] **Repo cert distribution decision.** Currently `nginx/certs/cert.pem` + `key.pem` live
  outside git. Michael plans to ship the ZeroSSL cert + key in the repo so the 10yo target
  user doesn't have to re-issue one — the cert is for `local.are-self.com` which resolves to
  `127.0.0.1`, so publicly-exposed private-key revocation risk is real but limited (worst case
  an attacker can MITM the user's own localhost traffic, which they already control). Decide
  and document the rationale in `mcp-server.md`. Re-issue + re-commit every ~80 days to stay
  ahead of the 90-day expiry.
## Ship-Blocking — Security Remediation (Before Tuesday Release)

- [ ] **Pin Django to >=6.0.2.** CVE-2025-64459 (CVSS 9.1) — SQL injection via QuerySet.filter(). Affects
  6.0.0 and 6.0.1. Change `Django>=6.0` to `Django>=6.0.2` in requirements.txt.
- [ ] **Pin LiteLLM to verified-safe version with hash.** Supply chain compromise in March 2026 (versions
  1.82.7 and 1.82.8 stole cloud credentials). Pin to a post-incident version and use `--hash` verification.
  Are-Self's default Ollama-only config limits exposure, but cloud users are at risk.
- [ ] **Update Docker Compose Redis image.** CVE-2025-49844 (CVSS 10.0) — RCE in Redis server Lua engine.
  Pin to a patched Redis image in docker-compose.yml.
- [ ] **Pin DRF to >=3.15.2.** CVE-2024-21520 — XSS in break_long_headers filter.
- [ ] **Remove pygtail from requirements.txt.** Deprecated, not imported anywhere.
- [ ] **Remove unused packages.** Audit and remove if confirmed: django-htmx (migrated to React),
  scapy (possibly unused), yapf (redundant with Ruff), aiosmtpd (verify usage).
- [ ] **Separate dev dependencies.** Move pytest, coverage, ruff, isort, yapf, ipython, type stubs,
  playwright into `requirements-dev.txt`.
- [ ] **Document Ollama security posture.** Users must keep Ollama updated independently. The install
  script should recommend a minimum Ollama version. See DEPENDENCY_AUDIT.md for full CVE list.

## Ship-Blocking — Documentation Infrastructure

- [ ] **Google-style docstrings for all viewsets, serializers, and public methods.** Prerequisite for
  Swagger/OpenAPI auto-generation. Run through each Django app and add docstrings to every ViewSet class,
  every serializer class, and every public method. Format: Google-style (`Args:`, `Returns:`, `Raises:`).
  Priority order: Frontal Lobe, CNS, Hippocampus, Hypothalamus, Identity, then the rest.
- [ ] **drf-spectacular integration for /api/docs/.** Install `drf-spectacular`, add to INSTALLED_APPS,
  wire `SpectacularAPIView` + `SpectacularSwaggerView` at `/api/docs/`. Generates interactive OpenAPI
  docs from DRF viewsets + docstrings. This gives scientists and developers a try-it-in-the-browser
  API explorer on the running server itself.
- [ ] **Docusaurus docs site (are-self-docs repo).** React-based documentation site deployed via GitHub
  Pages at `are-self.com`. Pulls content from markdown docs in are-self-api and are-self-ui. Sidebar
  navigation, search, versioning. Scaffold is ready — needs content migration and styling.
- [ ] **are-self-research repo.** Separate GitHub repo for whitepapers and academic papers. LaTeX format
  for formal publications. Papers: Focus Economy, Neuro-Mimetic Architecture, LLM Testing Harness,
  CI/CD Sovereignty, Hippocampus Hypergraph Migration (Samuel), Unreal Engine Integration.

## Ship-Blocking — Existing

- [ ] **Hypothalamus — manual model addition.** Need the ability to add a missing model to the
  Hypothalamus by hand through the UI.
- [ ] **CNS / Pathway Editor — favorites and groups.** Cannot set favorites or groups in CNS nor in the
  pathway editor. Need UI affordances for both.
- [ ] **Thalamus message polling.** `api/v2/thalamus/messages` polls excessively when talking to the
  Thalamus. Needs throttling or WebSocket replacement.
- [ ] **Frontal Lobe session Parietal tab — drill-through broken.** Items in the Parietal tab of a
  Frontal Lobe session are not clickable/drillable. Same issue for Parietal actions in the right
  inspector window. Proposed fix: drill to zoom the matching 3D node so the full call is visible.
- [ ] **Reasoning session deletion.** Need the ability to delete a reasoning session.
- [ ] **Reasoning session pruning.** Pick a turn number and click "Prune" to delete all turns from that
  point to the end of the session.
- [ ] **Remove synapse module.** Remove synapse entirely in favor of the new synapse_client.
- [ ] **Tool call `thought` parameter — make required or improve prompting.** Local models often call
  tools silently (no assistant text). The `thought` parameter exists but isn't required. Either:
  (a) make it required in the tool schema so models must explain themselves, or (b) add system prompt
  instructions demanding tool explanations.
- [ ] **Remove deprecated `parietal_lobe/registry.py`.** Hardcoded model map still exists. Superseded by
  Hypothalamus DB-driven routing.
- [ ] **Consolidate and improve MCP engram functions.** The Hippocampus tool functions need cleanup —
  reduce redundancy, improve the interface, make the tool descriptions clearer for small models.
- [ ] **Fix linters / Ruff configuration.** Ensure linting is consistent across the project. Pin Ruff
  config, resolve any conflicting rules.
- [ ] **Rename `system-control` endpoint — off style guide.** "System Control" violates the biological
  naming rule (mechanical/military). Candidates: `homeostasis`, `brainstem`, `medulla`, `autonomic`.
  Coordinated rename with frontend (`SystemControlPanel` → matching name). Frontend task filed under
  are-self-ui/TASKS.md.
- [x] **~~Migrate shutdown endpoint out of dashboard.~~** Canonical endpoint lives at
  `/api/v2/system-control/` (`peripheral_nervous_system/autonomic_nervous_system.py::SystemControlViewSet`)
  with shutdown, restart, and status actions. Deprecated shim in `dashboard/api.py` has been removed along
  with its now-unused imports (`os`, `threading`, `time`, `celery_app`, `AllowAny`-only permission). The
  `/api/v2/system-control/` URL rename (off biological style guide) is tracked separately above.
- [ ] **Standardize API URLs to hyphens.** Legacy underscore routes: `engram_tags`, `reasoning_sessions`,
  `reasoning_turns`, `nerve_terminal_*`. Coordinated with frontend — both repos change together.
- [ ] **Hypothalamus fixture initial state.** The 4 fixture AIModelProvider records have `is_enabled: true`,
  showing as "Installed" before sync_local runs. Should default to `is_enabled: false` (Available until
  confirmed by sync).
- [ ] **Share HUMAN_TAG constant.** `HUMAN_TAG = '<<h>>'` lives in `river_of_six_addon.py` but
  `frontal_lobe.py` uses the raw string `'<<h>>\n'`. Move to a shared constants file. Also use existing
  `ROLE` constant instead of raw `'user'` string in frontal_lobe.py.
- [ ] **IdentityAddonPhase — optional API endpoint.** No ViewSet/router exists for IdentityAddonPhase.
  Frontend hardcodes the 4 phases. If phases ever become user-configurable, a read-only endpoint will
  be needed. Low priority since phases are fixed constants.
- [ ] **`prompt` context variable injection.** The `prompt` context variable is NOT being injected into
  the session's prompt. The context variable resolution chain (spike blackboard → effector context →
  neuron context) needs auditing — variables are stored but not consumed by `_get_rendered_objective()`
  or wherever the prompt is assembled.

## Known Bugs

- [x] **~~Infinite loop on retry LIMIT REACHED.~~** FIXED (April 10, 2026). Root cause was
  `_process_graph_triggers` unconditionally appending `TYPE_FLOW` to `valid_wire_types` before adding
  SUCCESS or FAILURE, so any FLOW axon wired from a logic node (Gate, Retry, Delay) always fired
  alongside the status-driven axon. Fix: added `Effector.LOGIC_EFFECTORS = frozenset({LOGIC_GATE,
  LOGIC_RETRY, LOGIC_DELAY})` and gated FLOW in `_process_graph_triggers` — logic nodes now emit only
  SUCCESS or FAILURE; non-logic effectors retain the existing FLOW+SUCCESS / FLOW+FAILURE behavior.
  Added three regression tests in `central_nervous_system/tests/test_routing.py`:
  `test_logic_retry_failure_does_not_fire_flow_axon`,
  `test_logic_gate_success_does_not_fire_flow_axon`, and
  `test_non_logic_success_still_fires_flow_axon`. **Run locally:**
  `venv\Scripts\pytest central_nervous_system/tests/test_routing.py -v` on Windows.

## Next Up

- [ ] **Swarm message queue — delivery + persistence bug.** Typing a message in the Thalamus chat window
  of a running Frontal Lobe session does not deliver to the session. On refresh, the message is gone — not
  persisted as a ReasoningTurn. Two bugs: (1) swarm_message_queue not receiving/processing inbound messages
  during a live session, (2) messages not saved. **Paired with UI task.**
- [ ] **Error Handler Effector.** A native handler that fires when a spike fails (wired via TYPE_FAILURE
  axon). Reads error context from the blackboard (`error_message`, `failed_effector`, `result_code`).
  Can dispatch notifications — log to engram, fire a Cortisol neurotransmitter, write a PFC comment on
  the failed task, or escalate to the Thalamus standing session.
- [ ] **Clean requirements.txt.** Pin versions, remove unused/deprecated packages. Verify every package
  is actually imported somewhere. Group by purpose.
- [ ] **Compress fixtures before release.** Compress `initial_data.json` files to single-line JSON for
  Docker release. Keep readable versions in version control.
- [ ] **Expose tool calls in Thalamus chat history.** Check the Vercel AI SDK `parts` schema — tool calls
  should be `tool-call` and `tool-result` parts.
- [ ] **Prompt_addon state awareness.** The prompt_addon should check session ToolCall history and adapt
  the injected objective accordingly. Without this, small models get stuck in loops re-attempting completed
  steps.
- [ ] **MCP Server.** Have Are-Self be an MCP server, allowing other MCP clients to connect and execute
  commands like Execute Neural Pathway.
- [ ] **MCP Client.** Have Are-Self be an MCP client, calling other MCP servers.

## MCP Server — Phase 2

- [ ] **Blackboard write tool** — Pre-load context data onto spike train blackboard before launch. Requires wiring into NeuronContext or a new blackboard field on SpikeTrain.
- [ ] **SSE streaming via neurotransmitters** — Use the Synaptic Cleft's neurotransmitter system to stream real-time execution updates back through the MCP SSE endpoint. Map Dopamine (success), Cortisol (error), Glutamate (streaming) to MCP notifications.
- [ ] **Vector similarity engram search** — Replace text-only search with pgvector cosine similarity search. Requires embedding the query via Ollama/Nomic before searching.
- [ ] **Full Thalamus integration** — Wire send_thalamus_message into the actual Thalamus message pipeline with WebSocket delivery via Channels.
- [ ] **Authentication layer** — Add token-based auth for the /mcp endpoint. Required before any public deployment.
- [x] **~~Cowork custom connector registration~~** — **DEFERRED.** Claude Desktop/Cowork
  custom connectors require `https://` with strict CA validation. Self-signed certs are
  rejected. Localhost `http://` is rejected. No viable workaround exists without either a
  CA-signed cert for a real domain or Anthropic adding a localhost exception. Tracked
  upstream: `github.com/anthropics/claude-ai-mcp/issues/9`. Are-Self's MCP endpoint
  works correctly — the blocker is on Anthropic's side. Claude Code CAN connect to
  local HTTP MCP servers (no HTTPS needed). NGINX in Docker is configured to auto-upgrade
  to HTTPS if a user provides their own cert in `nginx/certs/`.
- [ ] **Write blackboard tool** — Allow writing arbitrary key-value context data that gets passed to spike train execution. This enables programmatic setup of execution context.
- [ ] **Read reasoning session tool** — Expose reasoning session history (turns, tool calls, responses) for post-execution analysis.
- [ ] **Migrate are-self-install.bat to Python.** Cross-platform install script (replaces Windows-only .bat). Must handle: Python venv, pip install, PostgreSQL check, Redis check, Ollama check. Detect OS via `platform.system()`. Target: a 10-year-old runs `python install.py` and everything works.

## Future

- [ ] **Image Generation Effector.** CNS effector pattern: artist LLM writes generation prompt to
  blackboard, effector POSTs to `{{image_gen_endpoint}}`, saves result, writes path back to blackboard.
  Decoupled from any specific backend (InvokeAI, ComfyUI, etc.). TTS is already built as Parietal Lobe
  tool — that's the PoC for binary creation.
- [ ] **Branching Canonical Pathway.** Modality routing via logic node. PM/dispatcher inspects PFC task,
  logic node routes based on blackboard state: code → worker branch, art → artist branch. Depends on
  image generation effector.
- [ ] **Self-improving pathway testing harness.** The testing harness IS a CNS neural pathway — no new
  framework. 7B model + 30B evaluator in a loop. The spike train IS the test run, the blackboard IS the
  assertion state, the summary_dump IS the test report.
- [ ] **Addon stage/lifecycle system.** Addons fire conditionally based on session state instead of every
  turn. Would allow moving focus mechanics into a dedicated focus addon.

## Backlog

- [ ] **Test coverage: reasoning loop.** Integration tests for `FrontalLobe.run()` with fixture-backed
  sessions. Verify: turn creation, tool dispatch, `yield_turn` breaks the loop, `mcp_done` creates a
  conclusion, max turns halts, stop signal halts.
- [ ] **Test coverage: Hypothalamus routing.** Unit tests for `pick_optimal_model`: preferred model
  selection, failover strategy steps, budget gate filtering, vector similarity fallback.
  **Partial:** Circuit breaker tests added (April 9, 2026): trip_circuit_breaker increments/backoff,
  cap at 5 min, overflow protection at extreme counter values, trip_resource_cooldown flat 60s with
  no counter change. See `hypothalamus/tests/test_api.py::TestAIModelProviderActions`.
- [ ] **Test coverage: Hippocampus.** Integration tests for engram CRUD: save with vector dedup at 90%
  threshold, update appends text, read links session/spike/identity, search by text and tags.
- [ ] **Test coverage: Parietal Lobe tools.** Test each MCP tool function in isolation with fixture data.
  Verify hallucination armor, focus fizzle gating, XP/focus accounting.
- [ ] **Budget enforcement at request time.** Wire actual spend tracking (sum
  `AIModelProviderUsageRecord.estimated_cost` per period) into the Hypothalamus pre-filter so budgets are
  enforced, not just defined.
- [ ] **Hypothalamus subfamily routing.** Update `pick_optimal_model` to prefer same-subfamily first, then
  parent-family, then vector search.
- [ ] **Audit async usage.** Identify `sync_to_async` wrapping that adds ceremony without value. Primary
  candidates: Frontal Lobe loop, Hippocampus, Parietal Lobe tool execution. Keep async for WebSocket
  streaming (Glutamate), Nerve Terminal, and genuine concurrent I/O. Convert the rest to synchronous with
  a single `sync_to_async` wrap at the Celery boundary.
- [ ] **Stabilize DRF API contract.** Audit all ViewSets and serializers for consistency. Ensure Thalamus
  chat history endpoint returns the Vercel AI SDK `parts