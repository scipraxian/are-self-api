# Are-Self API — Tasks

Remaining work, sifted for the backend. See FEATURES.md for what's built.

## In Progress — Nerve Terminal Scan Reconcile (April 11, 2026)

**Status:** Shipped initial fix with test coverage (8 tests, all passing against standalone
smoke harness — Postgres unavailable in sandbox). A regression was caught before close-out:
the UI agent cards "blink on/off" and the refresh button flashes constantly. Root cause is
known, fix is scoped, not yet applied.

**What was shipped:**

- `NerveTerminalStatus.CHECKING = 4` (model const + fixture + data migration
  `peripheral_nervous_system/migrations/0002_checking_status.py`).
- `_run_async_scan` in `peripheral_nervous_system/peripheral_nervous_system.py` now flips
  every live row to CHECKING, probes, upserts pongs to ONLINE, then flips stragglers to
  OFFLINE. Guarded by module-level `_SCAN_LOCK = asyncio.Lock()` to prevent stampede.
- `NerveTerminalRegistryViewSet.list()` (in `peripheral_nervous_system/api.py`) kicks a scan
  via `async_to_sync`, degrades gracefully on scan failure (try/except, logs warning, still
  returns DB state).
- `peripheral_nervous_system/tests/test_nerve_terminal_scan_reconcile.py` — 8 tests
  covering found→online, online→offline, mixed, already-offline untouched, CHECKING is
  transient, concurrent-scan skip, list() triggers scan, list() resilient to scan failure.

**The regression (highest priority when session resumes):**
The scan does per-row `.save()` in three phases, each firing its own acetylcholine. The
frontend subscribes to `NerveTerminalRegistry` broadcasts (`PNSPage.tsx:220`) and calls
`handleRefresh()` on each one, which hits the list endpoint → rekicks the scan (lock skips
the work but the DB returns partially-reconciled CHECKING rows to the UI). Result: UI churn,
blinking cards, blinking refresh button.

**Planned surgical fix (scoped, not started):**

1. Drop `_mark_live_terminals_checking` entirely. No CHECKING transient write — too noisy.
2. `_register_agent_in_db`: compare-then-save. No `.save()` when (status, ip, version)
   already match the discovered identity — kills the "ONLINE over ONLINE" broadcast storm.
3. `_mark_unreachable_offline` stays — these are real state transitions and SHOULD broadcast.
4. Remove the `list()` → scan kick. The scan is already wired to spike execution + the
   explicit `POST /scan` endpoint; piggybacking on every list() means every dendrite
   refetch rekicks a scan.
5. Update tests to match the new broadcast-on-change-only semantics (the CHECKING-transient
   test becomes "CHECKING is never written by the scan" instead).

**Follow-up pass (separate, if Michael wants):**

- Split the monolithic `handleRefresh` on the frontend into per-topic refetchers so a
  `NerveTerminalRegistry` broadcast doesn't also refetch celery-workers / beat / spikes.
- Convert vitals (`/api/v2/vital-signs/vitals/`) from 3s polling to event-driven
  neurotransmitter push from the vitals collector. Currently the ONE sanctioned polling
  exception in PNSPage (line 125). Browser does NOT already have this data.
- Investigate `/api/v2/celery-workers/` 3s response time — likely a synchronous broker
  round-trip inside the view.

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

update the docs with the norepinephrine in the pns for django.

- [ ] **Set up GitHub FUNDING.yml.** _Partially done — `are-self-api/.github/FUNDING.yml` exists with
  `github: [scipraxian]` active. The other platforms are commented out pending account creation (to
  avoid GitHub rendering broken Sponsor buttons). Remaining work is account creation + uncommenting,
  which is out-of-repo._ Create `.github/FUNDING.yml` in are-self-api (org-level). Populate
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

- [x] **~~Pin Django to >=6.0.2.~~** Done — `Django>=6.0.2` is pinned in `requirements.txt` with the
  CVE-2025-64459 comment.
- [x] **~~Pin LiteLLM past the supply chain incident.~~** Done — `litellm>=1.83.0` is pinned in
  `requirements.txt` with a comment calling out the compromised 1.82.7/1.82.8 versions. `--hash`
  verification is still not in place; if we want hash pinning we can do it as a separate pass.
- [x] **~~Update Docker Compose Redis image.~~** Done — `docker-compose.yml` now pins
  `image: redis:7.4.2-alpine` (was `image: redis`, floating to `:latest`). Patched against
  CVE-2025-49844 (CVSS 10.0 RCE in the Redis server Lua scripting engine). Needs a
  `docker compose pull redis && docker compose up -d redis` on the live stack to actually
  swap the running container — the edit alone only affects fresh `up`s.
- [x] **~~Pin DRF to >=3.15.2.~~** Done — `djangorestframework>=3.15.2` is pinned in `requirements.txt`
  with the CVE-2024-21520 comment.
- [x] **~~Remove pygtail from requirements.txt.~~** Done — `pygtail` is no longer in `requirements.txt`.
  Still referenced in TASKS.md (now this line) and `DEPENDENCY_AUDIT.md` as historical notes only.
- [x] **~~Remove unused packages.~~** Done — audited on April 10, 2026. None of `django-htmx`,
  `scapy`, `yapf`, or `aiosmtpd` are present in `requirements.txt` or imported anywhere in
  `are-self-api/`. Only residual references are in TASKS.md and `DEPENDENCY_AUDIT.md` as
  historical notes.
- [x] **~~Separate dev dependencies.~~** Done — `requirements-dev.txt` exists and pulls main via
  `-r requirements.txt`. Contains pytest, pytest-django, pytest-asyncio, coverage, playwright, ruff,
  isort, ipython, plus a type-stubs block (django-stubs, djangorestframework-stubs, celery-types).
  yapf correctly absent (redundant with ruff — tracked under the unused-packages audit above).
- [ ] **Document Ollama security posture.** Users must keep Ollama updated independently. The install
  script should recommend a minimum Ollama version. See DEPENDENCY_AUDIT.md for full CVE list.

## Ship-Blocking — Documentation Infrastructure

- [ ] **Google-style docstrings for all viewsets, serializers, and public methods.** Prerequisite for
  Swagger/OpenAPI auto-generation. Run through each Django app and add docstrings to every ViewSet class,
  every serializer class, and every public method. Format: Google-style (`Args:`, `Returns:`, `Raises:`).
  _Baseline April 10, 2026: 76 ViewSets total, ~25 currently carry a docstring._
  _Biggest gaps — work here first: Hypothalamus (20 VS, ~1 documented), Parietal Lobe (7/0),_
  _PFC (6/0), Hippocampus (2/0). Already in good shape: Temporal Lobe (5/5), Frontal Lobe (2/2)._
  _Priority order: Hypothalamus → Parietal Lobe → PFC → Hippocampus → CNS (9/6) → Identity (7/2) →_
  _PNS (8/4) → environments (8/4) → the rest._
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
  _Re-verified April 10, 2026. Five live importers, but the real blocker is narrower than a rename:_
  _- `hippocampus/models.py`, `hippocampus/hippocampus.py`, `identity/models.py`,_
  _  `hypothalamus/models.py` all import `OllamaClient` for one purpose only: calling `.embed()`_
  _ to build vectors. `synapse_client.SynapseClient` has no `embed()` method, so there is no_
  _ drop-in replacement._
  _- `frontal_lobe/synapse_open_router.py` imports `SynapseResponse`, which **does** exist on_
  _  `synapse_client` — that one is a mechanical rename._
  _Real first step: add an embeddings surface (either `SynapseClient.embed()` or a small_
  _dedicated `frontal_lobe/embeddings.py` helper), cut the four model files over, then retire_
  _`frontal_lobe/synapse.py` along with its tests._
- [ ] **Tool call `thought` parameter — make required or improve prompting.** Local models often call
  tools silently (no assistant text). The `thought` parameter exists but isn't required. Either:
  (a) make it required in the tool schema so models must explain themselves, or (b) add system prompt
  instructions demanding tool explanations.
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
  _Verified April 10, 2026: every underscore server route has matching UI consumers_
  _(`EngramEditor.tsx`, `HippocampusPage.tsx`, `SessionChat.tsx`, `ReasoningPanels.tsx`,_
  _`FrontalLobeView.tsx`, `FrontalLobeDetail.tsx`, `ReasoningGraph3D.tsx`, `PNSPage.tsx`).Mechanical sweep — safe once
  greenlit._
- [ ] **Purge residual `/api/v1/` consumers.** Despite the v2 push, the UI still calls
  `/api/v1/node-contexts` (13 sites), `/api/v1/reasoning_sessions/` (7 sites), and
  `/api/v1/environments` (4 sites). Either re-point these to the v2 equivalents or,
  if v2 truly does not host these yet, declare the v2 gap and fill it. Pairs with a
  matching UI cleanup task.
- [ ] **Hypothalamus fixture initial state.** The 4 fixture AIModelProvider records have `is_enabled: true`,
  showing as "Installed" before sync_local runs. Should default to `is_enabled: false` (Available until
  confirmed by sync).
- [x] **~~Share HUMAN_TAG constant.~~** Done — `HUMAN_TAG` lives in `common.constants` and is imported
  into `frontal_lobe/frontal_lobe.py` (line 12) alongside `CONTENT`, `ROLE`, and `USER`. Used via
  `msg[CONTENT] = HUMAN_TAG + '\n' + msg[CONTENT]` in the human-message tagging path. Michael
  verified `river_of_six_addon.py` also imports from `common.constants` rather than defining its
  own copy. Fully consolidated.
- [ ] **IdentityAddonPhase — optional API endpoint.** No ViewSet/router exists for IdentityAddonPhase.
  Frontend hardcodes the 4 phases. If phases ever become user-configurable, a read-only endpoint will
  be needed. Low priority since phases are fixed constants.
- [ ] **`prompt` context variable injection.** The `prompt` context variable is NOT being injected into
  the session's prompt. The context variable resolution chain (spike axoplasm → effector context →
  neuron context) needs auditing — variables are stored but not consumed by `_get_rendered_objective()`
  or wherever the prompt is assembled.

## Known Bugs

- [ ] **Infinite loop on retry LIMIT REACHED — ROLLED BACK, NEEDS MORE TARGETED FIX.**
  Attempted fix on April 10, 2026 gated `TYPE_FLOW` on all logic effectors
  (LOGIC_GATE / LOGIC_RETRY / LOGIC_DELAY) inside `_process_graph_triggers`. This
  broke real pathways because in practice logic nodes are almost always wired with
  FLOW axons as the downstream connector — suppressing FLOW meant "logic nodes no
  longer fire at all." Rolled back the gating; `_process_graph_triggers` again
  unconditionally appends `AxonType.TYPE_FLOW` to `valid_wire_types` the way it did
  before. The `Effector.LOGIC_EFFECTORS` constant and the two logic-specific
  regression tests (`test_logic_retry_failure_does_not_fire_flow_axon`,
  `test_logic_gate_success_does_not_fire_flow_axon`) were removed with the
  rollback. Kept `test_non_logic_success_still_fires_flow_axon` as a regression
  test for the restored always-fire-FLOW behavior. If the retry short-circuit is
  a real observed issue, the targeted fix is probably narrower: only gate FLOW
  when `effector_id == LOGIC_RETRY` AND `status_id == FAILED` (the "LIMIT REACHED"
  path only), leaving gate/delay and retry's happy path untouched. Michael didn't
  remember this bug, so it may not be reproducible in current pathways.

## Next Up

- [ ] **Swarm message queue — delivery + persistence bug.** Typing a message in the Thalamus chat window
  of a running Frontal Lobe session does not deliver to the session. On refresh, the message is gone — not
  persisted as a ReasoningTurn. Two bugs: (1) swarm_message_queue not receiving/processing inbound messages
  during a live session, (2) messages not saved. **Paired with UI task.**
- [ ] **Error Handler Effector.** A native handler that fires when a spike fails (wired via TYPE_FAILURE
  axon). Reads error context from the axoplasm (`error_message`, `failed_effector`, `result_code`).
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
- [ ] **Remove redundant `CREATE EXTENSION vector` steps.** As of Pass 1 UUID migration,
  `common/migrations/0001_initial.py` calls `pgvector.django.VectorExtension()` and every
  `VectorField`-using app depends on it transitively. The manual `CREATE EXTENSION IF NOT EXISTS vector`
  step in `are-self-install.bat` (line 58) and the matching line in the README manual-install
  instructions are now redundant and actively misleading — someone troubleshooting a fresh install
  could waste time chasing whether the extension "ran properly" when Django migrations handle it.
  Remove both. (README already cleaned; `.bat` pending.)
- [ ] **UUID migration Pass 2 — fixture separation + plugin extraction.** Pass 1 flipped 18
  plugin-extensible models from integer to UUID PKs (`uuid-migration` branch, gated on frontend
  companion PR). Pass 2 splits monolithic `initial_data.json` into per-tier files (starter / test /
  plugin bundles), extracts the Unreal flow as the first installable plugin bundle, moves generic
  log-merge utilities from `ue_tools/` to `occipital_lobe/`, splits `log_parser.py` into generic
  core + UE-specific plugin pieces, removes `ollama_fixture_generator.py`, and wires the `plugins`
  Django app (Michael is doing the `startapp` himself). Requires Pass 1 merged to `main` first.
- [ ] **Plugin Garden — 3rd-party plugin marketplace.** Are-Self ships with 3–4 first-party plugins
  (Unreal first, others TBD), all install/uninstall-able via the plugins API. Beyond the shipped set,
  stand up a "garden" where 3rd parties can publish plugins and users can browse/install them.
  NASA doesn't want Unreal; someone else might. Everything past core is a plugin, every plugin is
  toggleable, and the garden is the discovery layer. Needs: publication format (signed bundle?),
  registry/index service, trust model, versioning/compat checks against core, install UI. Priority:
  wanted now, not later.
- [ ] **Move generic log-merge utilities to occipital_lobe.** `ue_tools/merge_logs.py` and
  `ue_tools/merge_logs_nway.py` are format-agnostic timeline correlators (heap-sorted entries,
  tolerance-window row grouping, `(label, content)` tuples in → `MergedRow`/`NWayMergeResult` out).
  Only the underlying `log_parser.py` is UE-flavored. Move the merge functions to `occipital_lobe/`,
  keep/rename the parser layer so non-UE callers can plug in their own `LogEntry` producers, and
  update imports. Pattern: same shape as extracting `mcp_run_unreal_diagnostic_parser` for the
  Unreal plugin — generic stays in core, UE-specific goes to the plugin bundle.

## MCP Server — Phase 2

- [ ] **Cerebrospinal fluid write tool** — Pre-load context data onto spike train cerebrospinal_fluid before launch. Requires wiring into
  NeuronContext or a new cerebrospinal_fluid field on SpikeTrain.
- [ ] **SSE streaming via neurotransmitters** — Use the Synaptic Cleft's neurotransmitter system to stream real-time
  execution updates back through the MCP SSE endpoint. Map Dopamine (success), Cortisol (error), Glutamate (streaming)
  to MCP notifications.
- [ ] **Vector similarity engram search** — Replace text-only search with pgvector cosine similarity search. Requires
  embedding the query via Ollama/Nomic before searching.
- [ ] **Full Thalamus integration** — Wire send_thalamus_message into the actual Thalamus message pipeline with
  WebSocket delivery via Channels.
- [ ] **Authentication layer** — Add token-based auth for the /mcp endpoint. Required before any public deployment.
- [x] **~~Cowork custom connector registration~~** — **DEFERRED.** Claude Desktop/Cowork
  custom connectors require `https://` with strict CA validation. Self-signed certs are
  rejected. Localhost `http://` is rejected. No viable workaround exists without either a
  CA-signed cert for a real domain or Anthropic adding a localhost exception. Tracked
  upstream: `github.com/anthropics/claude-ai-mcp/issues/9`. Are-Self's MCP endpoint
  works correctly — the blocker is on Anthropic's side. Claude Code CAN connect to
  local HTTP MCP servers (no HTTPS needed). NGINX in Docker is configured to auto-upgrade
  to HTTPS if a user provides their own cert in `nginx/certs/`.
- [ ] **Write cerebrospinal fluid tool** — Allow writing arbitrary key-value context data that gets passed to spike train
  execution. This enables programmatic setup of execution context.
- [ ] **Read reasoning session tool** — Expose reasoning session history (turns, tool calls, responses) for
  post-execution analysis.
- [ ] **Migrate are-self-install.bat to Python.** Cross-platform install script (replaces Windows-only .bat). Must
  handle: Python venv, pip install, PostgreSQL check, Redis check, Ollama check. Detect OS via `platform.system()`.
  Target: a 10-year-old runs `python install.py` and everything works.

## Future

- [ ] **Image Generation Effector.** CNS effector pattern: artist LLM writes generation prompt to
  axoplasm, effector POSTs to `{{image_gen_endpoint}}`, saves result, writes path back to axoplasm.
  Decoupled from any specific backend (InvokeAI, ComfyUI, etc.). TTS is already built as Parietal Lobe
  tool — that's the PoC for binary creation.
- [ ] **Branching Canonical Pathway.** Modality routing via logic node. PM/dispatcher inspects PFC task,
  logic node routes based on axoplasm state: code → worker branch, art → artist branch. Depends on
  image generation effector.
- [ ] **Self-improving pathway testing harness.** The testing harness IS a CNS neural pathway — no new
  framework. 7B model + 30B evaluator in a loop. The spike train IS the test run, the axoplasm IS the
  assertion state, the summary_dump IS the test report.
- [ ] **Occipital lobe folder-change detection → environment test pathway.** OS-level file watcher
  (inotify / FSEvents / ReadDirectoryChangesW) lives in `occipital_lobe/` as a visual-cortex-style
  intake layer. Folder change events route to the associated `ProjectEnvironment`'s test-suite
  neural pathway and fire it automatically. Reactive, per-environment — edit a file in a checkout,
  that environment's tests run, results land in the existing spike/neuron/context graph. No new
  models required — uses existing effector/pathway machinery end-to-end. Generalizable beyond
  tests: "watch a folder, fire a pathway" is useful for research dirs, download folders,
  screenshot folders, etc. Occipital lobe as the general OS-event intake region.
- [ ] **Addon stage/lifecycle system.** Addons fire conditionally based on session state instead of every
  turn. Would allow moving focus mechanics into a dedicated focus addon.
- [ ] **Nerve Terminal video stream.** Add a third stream alongside STDOUT and log-file tailing: live video
  of the application the terminal is running. Brings the Nerve Terminal to 3 streams total (stdout, log
  file, video). Capture the target app's window/screen on the agent side, encode, and pipe back over the
  existing async generator contract so consumers get frames the same way they get log lines. Needs: capture
  backend (per-OS — likely ffmpeg/gdigrab on Windows, avfoundation on macOS, x11grab on Linux), encoding
  choice (H.264/WebRTC vs. MJPEG over WS), a new `StreamEvent` source (`'video'`) with binary payload
  support, frontend player wired into the existing terminal view, and backpressure/frame-drop handling so
  a slow consumer doesn't stall stdout or log streams.

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
- [ ] **Stabilize DRF API contract.** Audit all ViewSets and serializers for consistency. Ensure the
  Thalamus chat history endpoint returns the Vercel AI SDK `parts` schema
  (`text` / `reasoning` / `tool-call` / `tool-result`) so the backend matches what
  `are-self-ui/src/components/SessionChat.tsx` already parses. Frontend side is done; this is the
  server-side parity pass.