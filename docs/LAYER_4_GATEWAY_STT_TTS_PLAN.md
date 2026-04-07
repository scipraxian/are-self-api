# Layer 4: talos_gateway — Platform Integration, STT, and TTS

**Author:** Julianna (for Sam)
**Date:** 2026-04-03
**Status:** DRAFT — Architecture plan
**Depends on:** Layers 1-3 (core MCP tools, memory, identity+reasoning enhancements)

---

## 1. Layer 4's Role in the Architecture

Layer 4 is the sensory-motor boundary of Talos. It handles everything that
crosses the edge between the system and the outside world through messaging
platforms: text in, text out, voice in, voice out.

In the neuroanatomy, this is the skin — the place where external stimuli
become internal signals, and where internal decisions become observable
actions. It does NOT contain reasoning, memory, tool execution, or identity.
Those live in the existing brain regions. Layer 4 is transport, transduction,
and delivery.

**Three responsibilities:**

1. **Inbound transduction** — Receive platform events (Discord messages,
   Telegram updates, CLI input, voice audio), normalize them into a
   uniform internal representation, and feed them to the FrontalLobe
   reasoning engine.

2. **Outbound delivery** — Take FrontalLobe responses and route them
   back to the originating platform in the correct format (text, voice
   message, media attachment).

3. **Modality conversion** — Speech-to-text (STT) and text-to-speech (TTS)
   as services that any component can invoke, but which are primarily
   consumed by the gateway for voice interactions.

**What Layer 4 is NOT:**

- Not the reasoning engine (that is FrontalLobe)
- Not the prompt builder (that is the Identity addon pipeline)
- Not a tool system (that is ParietalLobe)
- Not a scheduler (that is TemporalLobe)
- Platform SDKs are dependencies of individual adapters, never of the core

---

## 2. Architectural Changes

### 2.1 New Django App: talos_gateway

A new top-level Django app following existing conventions (no ABCs, no
formal interfaces — convention over inheritance, Pydantic for contracts,
Django Channels for real-time).

### 2.2 New Django App: vocal_cortex

STT and TTS as a standalone service app. Named in the neuroanatomy —
the vocal cortex handles speech production and auditory processing.
Separated from the gateway because other components (TemporalLobe cron
output, PFC ticket narration) may want TTS without going through a
platform adapter.

### 2.3 Extensions to Existing Apps

- **thalamus/** — New Stimulus type for platform messages. The thalamus
  already routes signals; platform messages are just another kind of
  stimulus.
- **synaptic_cleft/** — New Neurotransmitter subclasses for streaming
  tokens from FrontalLobe to gateway consumers.
- **frontal_lobe/** — stream_callback parameter on SynapseClient.chat().
  FrontalLobe._execute_turn() accepts an optional callback that fires
  per-token during streaming.
- **identity/** — New addons: platform_hint_addon (injects platform-specific
  behavioral guidance), gateway_session_addon (injects cross-session
  history if available).

---

## 3. Component Model

### 3.1 Message Contracts (Pydantic models — matching Neurotransmitter pattern)

```python
# talos_gateway/contracts.py

class PlatformEnvelope(BaseModel):
    """Normalized inbound message from any platform."""
    platform: str               # 'discord', 'telegram', 'cli', etc.
    channel_id: str             # Platform-specific channel/chat identifier
    thread_id: str | None       # Thread/topic identifier if applicable
    sender_id: str              # Platform user identifier
    sender_name: str            # Human-readable sender name
    message_id: str             # Platform-specific message identifier
    content: str                # Text content (may be empty for voice-only)
    attachments: list[Attachment]  # Media attachments
    voice_audio: bytes | None   # Raw audio bytes for voice messages
    reply_to: str | None        # Message ID being replied to
    timestamp: datetime         # Platform-reported timestamp
    raw_event: dict | None      # Full platform event for edge cases

class Attachment(BaseModel):
    """Normalized media attachment."""
    url: str
    filename: str
    content_type: str           # MIME type
    size_bytes: int | None

class DeliveryPayload(BaseModel):
    """Outbound message to a platform."""
    platform: str
    channel_id: str
    thread_id: str | None
    content: str                # Text content
    media_paths: list[str]      # Local file paths for attachments
    voice_audio_path: str | None  # TTS-generated audio file path
    reply_to: str | None        # Platform message ID to reply to
    is_voice: bool              # Deliver as voice message if platform supports it
```

### 3.2 Platform Adapter Contract (Convention-based, no ABC)

Every adapter is a module in `talos_gateway/adapters/` that exports a class
following this convention:

```python
# talos_gateway/adapters/discord_adapter.py

class DiscordAdapter:
    """Convention: every adapter exposes these methods."""

    PLATFORM_NAME = 'discord'
    MAX_MESSAGE_LENGTH = 2000

    def __init__(self, config: dict):
        """Config comes from Django settings.TALOS_GATEWAY['platforms']['discord']."""

    async def start(self):
        """Connect to the platform. Called once at gateway startup."""

    async def stop(self):
        """Disconnect cleanly. Called on shutdown."""

    async def send(self, payload: DeliveryPayload) -> dict:
        """Deliver a message. Returns {success: bool, ...}."""

    async def send_chunked(self, payload: DeliveryPayload) -> dict:
        """Chunk long messages to fit MAX_MESSAGE_LENGTH, then send."""

    def on_message(self, callback: Callable[[PlatformEnvelope], Awaitable[None]]):
        """Register the inbound message handler. Called once at setup."""
```

No ABC. The gateway discovers adapters by convention: each module in
`talos_gateway/adapters/` is importable, and the gateway reads
`TALOS_GATEWAY['platforms']` from Django settings to know which to load.
If an adapter module exists and is enabled in config, it gets instantiated.

This is the same pattern as parietal_mcp: convention-based discovery via
importlib, no formal registration.

### 3.3 Core Services

```
talos_gateway/
  gateway.py              — GatewayOrchestrator: lifecycle management,
                            adapter loading, message routing
  session_manager.py      — Session state: maps (platform, channel_id) to
                            ReasoningSession, tracks active IdentityDisc
  message_router.py       — Inbound: PlatformEnvelope → FrontalLobe execution
                            Outbound: FrontalLobe result → DeliveryPayload
  stream_consumer.py      — Channels WebSocket consumer for streaming tokens
                            from FrontalLobe to platform adapters
  contracts.py            — Pydantic models (PlatformEnvelope, DeliveryPayload, etc.)

vocal_cortex/
  stt.py                  — Speech-to-text service (provider-agnostic)
  tts.py                  — Text-to-speech service (provider-agnostic)
  providers/
    stt_voxtral.py        — Voxtral STT provider
    stt_faster_whisper.py — faster-whisper local STT provider
    tts_edge.py           — Microsoft Edge TTS provider
    tts_elevenlabs.py     — ElevenLabs API TTS provider
    tts_voxtral.py        — Voxtral TTS provider
  models.py               — TranscriptionResult, SynthesisResult,
                            VoiceProfile (Django model for stored voices)
```

### 3.4 Neurotransmitter Extensions (synaptic_cleft pattern)

```python
# synaptic_cleft/neurotransmitters.py additions

class Serotonin(Neurotransmitter):
    """Streaming token delivery from FrontalLobe to gateway."""
    activity: str = 'token_delta'
    token: str                  # The streamed token text
    is_final: bool = False      # True on the last chunk

class Endorphin(Neurotransmitter):
    """Voice/media delivery notification."""
    activity: str = 'media_ready'
    media_type: str             # 'voice', 'image', 'document'
    media_path: str             # Local file path
```

---

## 4. Package Structure

```
talos_gateway/
├── __init__.py
├── apps.py
├── models.py                   # GatewaySession, PlatformConfig (Django models)
├── admin.py
├── contracts.py                # PlatformEnvelope, DeliveryPayload, Attachment
├── gateway.py                  # GatewayOrchestrator (lifecycle, adapter loading)
├── session_manager.py          # Session state management
├── message_router.py           # Inbound/outbound routing logic
├── stream_consumer.py          # Channels WebSocket consumer for streaming
├── delivery.py                 # Outbound chunking, media handling, retry
├── signals.py                  # Django signal handlers for gateway events
├── urls.py                     # REST API endpoints (session list, send, etc.)
├── api.py                      # DRF ViewSets
├── serializers.py              # DRF serializers
├── management/
│   └── commands/
│       └── run_gateway.py      # Management command: python manage.py run_gateway
├── adapters/
│   ├── __init__.py
│   ├── base_patterns.py        # Shared utilities (chunking, media detection)
│   ├── cli_adapter.py          # Local terminal/WebSocket adapter
│   ├── discord_adapter.py      # Discord via discord.py
│   ├── telegram_adapter.py     # Telegram via python-telegram-bot
│   ├── signal_adapter.py       # Signal via signal-cli
│   ├── slack_adapter.py        # Slack via slack-sdk
│   └── webhook_adapter.py      # Generic inbound/outbound webhooks
└── tests/
    ├── __init__.py
    ├── test_contracts.py
    ├── test_gateway.py
    ├── test_session_manager.py
    ├── test_message_router.py
    └── test_adapters/
        ├── test_cli_adapter.py
        └── test_discord_adapter.py

vocal_cortex/
├── __init__.py
├── apps.py
├── models.py                   # VoiceProfile, TranscriptionLog
├── admin.py
├── stt.py                      # STTService (provider dispatch)
├── tts.py                      # TTSService (provider dispatch)
├── api.py                      # REST endpoints for TTS/STT
├── api_urls.py
├── serializers.py
├── providers/
│   ├── __init__.py
│   ├── stt_voxtral.py
│   ├── stt_faster_whisper.py
│   ├── tts_edge.py
│   ├── tts_elevenlabs.py
│   └── tts_voxtral.py
└── tests/
    ├── __init__.py
    ├── test_stt.py
    ├── test_tts.py
    └── test_providers/
        ├── test_stt_faster_whisper.py
        └── test_tts_edge.py
```

---

## 5. End-to-End Flows

### 5.1 Inbound Text Message

```
Discord user sends "analyze this image" with attachment
  │
  ▼
DiscordAdapter.on_message_callback() fires
  │  Extracts: content, attachments, channel_id, sender_id
  │  Normalizes into PlatformEnvelope
  │
  ▼
GatewayOrchestrator.handle_inbound(envelope)
  │
  ▼
SessionManager.resolve_session(envelope)
  │  Looks up (platform, channel_id) → ReasoningSession
  │  If no session: creates new ReasoningSession + resolves IdentityDisc
  │  Returns: session, identity_disc
  │
  ▼
MessageRouter.dispatch_to_reasoning(session, envelope)
  │  1. Converts envelope.content to a user message
  │  2. If attachments: resolves URLs, adds to message context
  │  3. Injects into session.swarm_message_queue (same pattern as
  │     thalamus.inject_swarm_chatter)
  │  4. If session status == ATTENTION_REQUIRED:
  │       Wake it: set ACTIVE, fire_spike.delay(spike_id)
  │     Else if no active session:
  │       Create Spike + SpikeTrain, launch FrontalLobe directly
  │       (sync path for interactive, not Celery — see design note below)
  │
  ▼
FrontalLobe._execute_turn()
  │  Runs reasoning with addon-built prompt
  │  Tool calls dispatched through ParietalLobe
  │  stream_callback fires Serotonin neurotransmitters per token
  │
  ▼
MessageRouter.handle_reasoning_output(session, result)
  │  Extracts final assistant content
  │  Builds DeliveryPayload
  │
  ▼
Delivery.send(payload)
  │  Resolves adapter by platform name
  │  Chunks if needed (adapter.MAX_MESSAGE_LENGTH)
  │  Calls adapter.send(chunk) for each piece
  │
  ▼
DiscordAdapter.send(payload)
  │  Posts to Discord API
  │  Returns {success: True, message_id: '...'}
```

### 5.2 Outbound Cross-Platform Message

```
FrontalLobe calls mcp_send_message(target='telegram:-1001234', message='...')
  │
  ▼
parietal_mcp/mcp_send_message.py
  │  Parses target → (platform, channel_id, thread_id)
  │  Builds DeliveryPayload
  │
  ▼
Delivery.send(payload)
  │  Resolves adapter from GatewayOrchestrator.active_adapters
  │  Calls adapter.send(payload)
```

### 5.3 Voice Input → Transcription → Processing

```
Discord user sends voice message (Opus in OGG container)
  │
  ▼
DiscordAdapter.on_message_callback()
  │  Detects audio attachment or voice message
  │  Downloads to temp file
  │  Sets envelope.voice_audio = raw_bytes
  │
  ▼
GatewayOrchestrator.handle_inbound(envelope)
  │  Detects voice_audio is not None
  │
  ▼
STTService.transcribe(audio_bytes, format='ogg')
  │  Resolves provider from settings (VOCAL_CORTEX['stt_provider'])
  │  Provider options: 'faster_whisper' (local), 'voxtral' (API)
  │
  ▼
stt_faster_whisper.transcribe(audio_bytes, format='ogg')
  │  Loads faster-whisper model (cached in-process)
  │  Returns TranscriptionResult(text='analyze this image', language='en',
  │                              confidence=0.97, duration_seconds=2.1)
  │
  ▼
GatewayOrchestrator replaces envelope.content with transcription.text
  │  Normal text flow continues from here (5.1 above)
```

### 5.4 Generated Response → Speech Synthesis → Delivery

```
FrontalLobe produces response: "The image shows a network topology..."
  │
  ▼
MessageRouter.handle_reasoning_output(session, result)
  │  Checks: should this response be delivered as voice?
  │  Decision criteria:
  │    1. Original message was voice → respond in voice
  │    2. IdentityDisc has voice_response_default = True
  │    3. Explicit tool call to mcp_tts
  │
  ▼
TTSService.synthesize(text, voice_profile_id=None)
  │  Resolves provider from settings (VOCAL_CORTEX['tts_provider'])
  │  Provider options: 'edge' (Microsoft Edge), 'elevenlabs' (API),
  │                    'voxtral' (Voxtral TTS)
  │
  ▼
tts_edge.synthesize(text, voice='en-US-AriaNeural')
  │  Calls edge-tts library
  │  Returns SynthesisResult(audio_path='/tmp/talos_tts_xyz.mp3',
  │                          format='mp3', duration_seconds=4.2)
  │
  ▼
DeliveryPayload is built with:
  │  content = original text (for platforms that support both)
  │  voice_audio_path = synthesis.audio_path
  │  is_voice = True
  │
  ▼
DiscordAdapter.send(payload)
  │  Uploads audio as voice message with waveform metadata
  │  Falls back to text if voice upload fails
```

---

## 6. Configuration, Lifecycle, DI, and Extensibility

### 6.1 Configuration

All configuration lives in Django settings, matching Talos convention:

```python
# config/settings.py additions

TALOS_GATEWAY = {
    'platforms': {
        'discord': {
            'enabled': True,
            'token': env('DISCORD_BOT_TOKEN', default=''),
            'home_channel_id': env('DISCORD_HOME_CHANNEL', default=''),
            'voice_response': True,   # Auto-respond to voice with voice
        },
        'telegram': {
            'enabled': True,
            'token': env('TELEGRAM_BOT_TOKEN', default=''),
            'home_chat_id': env('TELEGRAM_HOME_CHAT', default=''),
        },
        'cli': {
            'enabled': True,
            # CLI always available, connects via WebSocket
        },
    },
    'default_identity_disc': None,  # UUID or None (auto-resolve)
    'max_concurrent_sessions': 10,
    'session_timeout_minutes': 60,
    'interactive_mode': True,       # True = sync FrontalLobe, False = Celery
}

VOCAL_CORTEX = {
    'stt_provider': 'faster_whisper',   # 'faster_whisper', 'voxtral'
    'tts_provider': 'edge',             # 'edge', 'elevenlabs', 'voxtral'
    'stt_model': 'large-v3',            # faster-whisper model size
    'tts_voice': 'en-US-AriaNeural',    # Default TTS voice
    'tts_cache_dir': '/tmp/talos_tts',  # Audio cache directory
    'elevenlabs_api_key': env('ELEVENLABS_API_KEY', default=''),
    'voxtral_api_key': env('VOXTRAL_API_KEY', default=''),
}
```

### 6.2 Lifecycle Management

```python
# talos_gateway/management/commands/run_gateway.py

class Command(BaseCommand):
    """python manage.py run_gateway"""

    def handle(self, *args, **options):
        orchestrator = GatewayOrchestrator()
        orchestrator.load_adapters()    # importlib scan of adapters/
        orchestrator.start_all()        # calls adapter.start() for each
        # Blocks on asyncio event loop
        # Ctrl+C triggers orchestrator.stop_all()
```

Adapter lifecycle:
- `__init__(config)` — Parse config, instantiate SDK client (but don't connect)
- `start()` — Connect to platform, register event handlers
- `stop()` — Disconnect cleanly, flush pending deliveries
- If adapter.start() raises, log error and continue with remaining adapters

### 6.3 Dependency Injection (Convention-Based)

Following Talos's established pattern: no DI framework, no ABCs. Dependencies
are resolved by convention:

- **STT/TTS providers:** Registry dict mapping string names to module paths.
  `STTService` does `importlib.import_module(f'vocal_cortex.providers.stt_{provider_name}')`.
  Same pattern as `ParietalMCP.execute()`.
- **Platform adapters:** Same importlib pattern. Gateway scans
  `talos_gateway/adapters/` for modules matching enabled config keys.
- **FrontalLobe access:** Gateway calls `FrontalLobe(spike).run()` directly
  for interactive mode, or `fire_spike.delay(spike_id)` for Celery mode.

### 6.4 Extensibility — Adding a New Platform

To add WhatsApp:

1. Create `talos_gateway/adapters/whatsapp_adapter.py`
2. Implement `WhatsAppAdapter` class following the convention (start, stop,
   send, on_message)
3. Add `'whatsapp': {'enabled': True, 'token': ...}` to
   `TALOS_GATEWAY['platforms']` in settings
4. The gateway auto-discovers it on next startup. No registration code needed.

To add a new TTS provider:

1. Create `vocal_cortex/providers/tts_<name>.py`
2. Export `async def synthesize(text, voice, **kwargs) -> SynthesisResult`
3. Set `VOCAL_CORTEX['tts_provider'] = '<name>'` in settings
4. Done. No registration code needed.

---

## 7. Error Handling, Retries, and Observability

### 7.1 Error Strategy

Following Talos convention: **log and continue, never crash the gateway.**

| Component | Error Behavior |
|---|---|
| Adapter.start() | Log error, skip adapter. Gateway continues with remaining adapters. |
| Adapter.send() | Retry 2x with 1s/3s backoff. On final failure, log + fire Cortisol neurotransmitter. Return error to FrontalLobe as tool result. |
| STT transcription | Return TranscriptionResult(text='', error='...') on failure. Gateway falls back to "[Voice message — transcription unavailable]" as content. |
| TTS synthesis | Return SynthesisResult(audio_path=None, error='...') on failure. Gateway falls back to text-only delivery. |
| FrontalLobe crash | Catch, log with full traceback, send error message to platform: "I hit an unexpected issue. Let me try again." |
| WebSocket disconnect | Adapter handles reconnection internally. Fire Norepinephrine neurotransmitter on disconnect/reconnect. |
| Session resolution | If IdentityDisc resolution fails, use fallback disc from settings. |

### 7.2 Retries

- **Platform send:** 2 retries with exponential backoff (1s, 3s). On rate
  limit (429), respect Retry-After header. On permanent failure (403, 404),
  do not retry.
- **STT/TTS:** 1 retry with 2s delay. Local providers (faster-whisper)
  don't retry — if the model fails, it's a systemic issue.
- **FrontalLobe execution:** No retry on tool errors (FrontalLobe handles
  its own failover via Hypothalamus). Retry once on unexpected crash.

### 7.3 Observability

- **Logging:** All gateway components log to `talos_gateway` logger namespace.
  Follows existing pattern in settings.py (console handler + Norepinephrine).
- **Neurotransmitters:** Fire Dopamine on successful delivery, Cortisol on
  failure, Norepinephrine on adapter lifecycle events. Frontend dashboard
  can subscribe to `receptor_class='gateway'` for live monitoring.
- **Metrics model:** New `GatewayDeliveryLog` model tracking: platform,
  channel_id, direction (inbound/outbound), latency_ms, success, error_message,
  tokens_streamed (for streaming responses). Lightweight — one row per message.
- **Health endpoint:** DRF ViewSet returning adapter status (connected/disconnected),
  session count, delivery stats.

---

## 8. Testing Strategy

### 8.1 Unit Tests

- **contracts.py** — Pydantic model validation, serialization/deserialization
- **session_manager.py** — Session creation, lookup, timeout, IdentityDisc resolution
- **message_router.py** — Envelope → user message conversion, swarm injection
- **delivery.py** — Chunking logic, media detection, retry behavior
- **vocal_cortex/stt.py** — Provider dispatch, error handling
- **vocal_cortex/tts.py** — Provider dispatch, caching, error handling

### 8.2 Integration Tests

- **FrontalLobe integration** — Gateway creates session, injects message,
  FrontalLobe runs reasoning, gateway captures result. Uses test IdentityDisc
  with a cheap model (ollama/tiny).
- **STT pipeline** — Feed known audio → get expected transcription text
- **TTS pipeline** — Feed known text → get valid audio file
- **Streaming** — Verify Serotonin neurotransmitters arrive via Channels
  test client as FrontalLobe streams tokens

### 8.3 Contract Tests

- **PlatformEnvelope validation** — Each adapter's normalization output
  conforms to the PlatformEnvelope schema. Parameterized test per adapter
  with sample platform events.
- **DeliveryPayload validation** — Each adapter's send() input is a valid
  DeliveryPayload. Test with edge cases (empty content, voice-only,
  oversized text, multiple attachments).

### 8.4 Adapter Tests

- **Mock-based:** Each adapter gets a test file that mocks the platform SDK
  and verifies: correct API calls, proper error handling, message chunking,
  media upload format.
- **Not end-to-end:** Adapter tests don't connect to real platforms. Real
  platform testing is manual QA.

### 8.5 Test Infrastructure

Following Talos convention: tests live in `tests/` subdirectories within
each app. Use `common.tests.common_test_case` base class where available.
Django test runner with `--parallel` for speed.

---

## 9. Phased Implementation Roadmap

### Phase 1: Foundation (Week 1)

**Goal:** Core contracts, session management, CLI adapter.

- Create `talos_gateway` app skeleton with models.py, contracts.py
- Implement GatewaySession model (platform, channel_id, session FK, identity_disc FK)
- Implement SessionManager (session resolution, creation, timeout)
- Implement PlatformEnvelope and DeliveryPayload contracts
- Implement CLI adapter (WebSocket-based local terminal)
- Implement `run_gateway` management command
- Add TALOS_GATEWAY to settings.py
- **Deliverable:** `python manage.py run_gateway` starts, CLI adapter accepts
  text input, creates ReasoningSession, but does not yet run FrontalLobe.

### Phase 2: Reasoning Integration (Week 2)

**Goal:** End-to-end text conversation via CLI.

- Implement MessageRouter (inbound dispatch, outbound capture)
- Integrate with FrontalLobe: create Spike + run reasoning synchronously
  for interactive mode (not Celery for CLI sessions)
- Implement stream_consumer.py — Channels consumer that receives Serotonin
  neurotransmitters and forwards to the CLI WebSocket
- Add Serotonin neurotransmitter to synaptic_cleft
- Extend SynapseClient.chat() with optional stream_callback
- Extend FrontalLobe._execute_turn() to pass stream_callback through
- **Deliverable:** Full text conversation via CLI with streaming responses.

### Phase 3: Vocal Cortex (Week 3)

**Goal:** STT and TTS operational.

- Create `vocal_cortex` app skeleton
- Implement STTService with provider dispatch
- Implement faster-whisper provider (local, GPU-accelerated)
- Implement Voxtral STT provider (API-based)
- Implement TTSService with provider dispatch
- Implement Edge TTS provider (Microsoft Edge, free)
- Implement ElevenLabs TTS provider (API-based)
- Implement Voxtral TTS provider
- Wire STT into gateway: voice_audio on PlatformEnvelope triggers
  transcription before FrontalLobe dispatch
- Wire TTS into gateway: voice responses generated when appropriate
- Add VOCAL_CORTEX to settings.py
- **Deliverable:** Voice message → transcription → reasoning → TTS → audio
  delivery pipeline working end-to-end via CLI.

### Phase 4: Discord Adapter (Week 4)

**Goal:** Discord platform fully operational.

- Implement DiscordAdapter (discord.py based)
  - Text messages, threads, DMs
  - Voice message reception + STT
  - Voice message delivery with waveform metadata
  - Image/file attachments
  - Message chunking for 2000-char limit
- Fire Norepinephrine on connect/disconnect/error
- Test with real Discord bot in development server
- **Deliverable:** Full Discord conversation with voice support.

### Phase 5: Telegram + Polish (Week 5)

**Goal:** Second platform, proving the adapter model works.

- Implement TelegramAdapter (python-telegram-bot based)
  - Text messages, groups, topics
  - Voice message reception + STT
  - Voice message delivery
  - Photo/document attachments
  - Message chunking for 4096-char limit
- Implement delivery.py retry logic and error handling
- Implement GatewayDeliveryLog for observability
- Implement health endpoint
- Write full test suite
- **Deliverable:** Two platforms operational, adapter model validated.

### Phase 6: Cross-Platform Messaging (Week 6)

**Goal:** MCP tool for outbound messaging across platforms.

- Implement parietal_mcp/mcp_send_message.py
- Implement parietal_mcp/mcp_tts.py (direct TTS tool for FrontalLobe)
- Implement channel directory (list available targets per platform)
- Test cron-like scenarios: TemporalLobe fires reasoning session, result
  delivered to Discord via mcp_send_message
- **Deliverable:** Full Layer 4 operational.

---

## 10. Risks, Tradeoffs, and Defaults

### 10.1 Key Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Sync FrontalLobe in ASGI thread** | HIGH | Interactive mode runs FrontalLobe synchronously in an ASGI thread for low-latency streaming. Long reasoning sessions (many tool calls) could block the event loop. Mitigation: run_in_executor for CPU-bound tool calls, configurable timeout, fallback to Celery for sessions exceeding threshold. |
| **faster-whisper GPU memory** | MEDIUM | Large STT model (large-v3) uses ~3GB VRAM. If Talos also runs Ollama for embeddings, GPU memory pressure. Mitigation: default to `base` model (150MB), let user configure up. Model cached in-process — only loaded once. |
| **Platform SDK version drift** | MEDIUM | discord.py, python-telegram-bot, etc. have independent release cycles with breaking changes. Mitigation: pin versions in requirements, isolate SDK usage to adapter modules. Core gateway never imports platform SDKs. |
| **Voice latency** | MEDIUM | STT + reasoning + TTS adds significant latency to voice interactions. Mitigation: stream text response first (low latency), then follow with voice (higher latency). User sees the text immediately. |
| **Session state in multi-worker** | LOW | If Daphne runs multiple workers, session state must be shared. Mitigation: session state lives in DB (GatewaySession model) and Redis (Channels layer), not in-process memory. |

### 10.2 Key Tradeoffs

| Decision | Tradeoff | Recommendation |
|---|---|---|
| **Sync vs. Celery for interactive** | Sync gives streaming but risks blocking ASGI. Celery gives reliability but adds latency and complexity for streaming. | **Default sync for interactive, Celery for cron/scheduled.** The TALOS_GATEWAY['interactive_mode'] flag controls this. |
| **Separate vocal_cortex app vs. embedded in gateway** | Separate is cleaner but adds import overhead. Embedded is simpler but couples voice to messaging. | **Separate app.** Other components (TemporalLobe cron narration, PFC ticket summary voices) will want TTS independently. |
| **Convention-based vs. ABC adapter pattern** | Convention matches existing Talos style but no compile-time checking. ABC gives type safety but doesn't match codebase conventions. | **Convention-based.** Matches parietal_mcp, addon_registry, and all other Talos patterns. Use comprehensive adapter tests to catch convention violations. |
| **One gateway process vs. per-platform processes** | One process is simpler but a crashing adapter could affect others. Per-platform is isolated but harder to manage. | **One process with per-adapter error isolation.** Each adapter runs in its own asyncio task. If it crashes, others continue. Matches NerveTerminal resilience pattern. |

### 10.3 Recommended Defaults

- **STT provider:** `faster_whisper` with `base` model (fast, free, local)
- **TTS provider:** `edge` (free, good quality, no API key needed)
- **Voice response policy:** Mirror — if user sends voice, respond with voice
- **Session timeout:** 60 minutes of inactivity
- **Max concurrent sessions:** 10 (increase based on available resources)
- **Interactive mode:** True (sync FrontalLobe, streaming via Channels)
- **First adapter to implement:** CLI (simplest, immediate testing)
- **Second adapter:** Discord (most feature-rich, validates the model)

---

## 11. Voxtral / Voxtral-TTS: Hermes Implementation and Optimal Talos Integration

### 11.1 [Verified] How Voxtral is implemented in Hermes

Hermes implements Voxtral in three layers:

1. **Low-level subprocess wrappers** in `tools/voxtral_tools.py`
2. **STT provider routing** in `tools/transcription_tools.py`
3. **TTS provider routing** in `tools/tts_tool.py`

This is not a network API integration. It is a **local subprocess integration**
wrapped around the `voxtral-mini-realtime-rs` native CLI.

#### A. [Verified] `tools/voxtral_tools.py` — the real integration core

Hermes's core Voxtral implementation is a pair of plain subprocess wrappers:

- `voxtral_transcribe(audio_path, ...) -> Dict[str, Any]`
- `voxtral_speak(text, output_path, ...) -> Dict[str, Any]`

Key characteristics:

- **Binary-first integration**
  - Hermes does not call a Python SDK.
  - It resolves a native Voxtral binary from:
    - `VOXTRAL_BINARY`
    - `config.yaml -> voxtral.binary`
    - hardcoded fallback candidates
    - `shutil.which('voxtral')`

- **Config-driven model resolution**
  - Model paths are resolved from env/config/defaults for:
    - ASR model
    - TTS model
    - tokenizer
  - It supports both:
    - model directories (`--model`)
    - GGUF files (`--gguf`)
  - GGUF mode is controlled by `VOXTRAL_USE_GGUF` or config.

- **WSL/Windows interop aware**
  - Hermes assumes a common deployment where the Voxtral executable is a
    Windows binary called from WSL.
  - It executes the binary using a Linux-visible mount path, but converts all
    file arguments to native Windows paths using `wslpath -w` before passing
    them to the process.
  - This path bridge is a major implementation detail, not a generic design.

- **ASR preprocessing behavior**
  - Voxtral prefers WAV/16kHz audio.
  - Hermes tries to convert non-WAV input to WAV using `ffmpeg`.
  - If conversion fails and the source is not directly usable, ASR fails.

- **TTS output staging behavior**
  - Hermes stages Voxtral TTS output to a Windows-writeable path under
    `/mnt/c/...`, then copies it back into the requested target path.
  - This exists because the Windows `.exe` cannot write directly into all WSL
    filesystem locations.
  - After synthesis, Hermes optionally converts the WAV output to the requested
    format using `ffmpeg`.

- **Timeouts and diagnostics**
  - Both ASR and TTS subprocess calls use a `300s` timeout.
  - `voxtral_available()` is implemented as a binary-resolution check.
  - The module has a small diagnostics block for printing resolved paths.

#### B. [Verified] `tools/transcription_tools.py` — STT provider integration

Hermes integrates Voxtral ASR as one provider among several:

- `local` = `faster-whisper`
- `local_command` = shell-based local whisper binary
- `groq` = Whisper via Groq API
- `openai` = Whisper via OpenAI API
- `voxtral` = local Voxtral CLI

Important behavior:

- If `stt.provider` is **explicitly** set to `voxtral`, Hermes honors it.
- If Voxtral tooling is unavailable, Hermes does **not** silently fall back to
  another provider when `voxtral` was explicitly requested.
- Auto-detection logic prefers:
  - `local` (`faster-whisper`)
  - then `local_command`
  - then `groq`
  - then `openai`
- Voxtral is therefore treated as an **explicit configured local backend**, not
  the default auto-detected STT engine.

Implementation shape:

- `_transcribe_voxtral(file_path, _model_name)` imports
  `tools.voxtral_tools.voxtral_transcribe`
- `transcribe_audio()` dispatches to Voxtral only when provider == `voxtral`

Notable code quality note:
- `transcription_tools.py` currently contains a duplicated `_transcribe_voxtral`
  function block. This is harmless but confirms the Hermes implementation grew
  pragmatically rather than from a clean provider abstraction.

#### C. [Verified] `tools/tts_tool.py` — TTS provider integration

Hermes integrates `voxtral-tts` as one TTS provider among several:

- `edge`
- `elevenlabs`
- `openai`
- `voxtral-tts`
- `neutts`

Important behavior:

- `_generate_voxtral_tts(text, output_path, tts_config)` imports
  `tools.voxtral_tools.voxtral_speak`
- It stages output to a fixed Windows-visible WAV path, then copies it back to
  the requested output path
- If the caller wants `.ogg` or `.mp3`, Hermes converts the generated WAV using
  `ffmpeg`
- The main `text_to_speech_tool()` then wraps the result in a `MEDIA:<path>` tag
  and adds `[[audio_as_voice]]` when the output is suitable for native voice
  delivery

Important routing behavior:

- Hermes defaults to `edge`, not `voxtral-tts`
- `voxtral-tts` is an explicit configured provider
- For Telegram compatibility, Hermes tries to convert outputs to Opus `.ogg`
  for voice-bubble delivery

### 11.2 [Synthesized] What this means architecturally

Hermes's Voxtral implementation is operationally useful but structurally narrow:

- It is **provider logic**, not gateway logic
- It is **host-environment-sensitive**, especially because of WSL/Windows path
  staging assumptions
- It is best understood as a local inference backend with a nontrivial file I/O
  bridge, not as a general speech abstraction

The right lesson is not "put Voxtral into talos_gateway".
The right lesson is:

- keep Voxtral inside `vocal_cortex`
- isolate OS-specific path bridging in a tiny helper layer
- expose a clean provider contract to the rest of Talos

### 11.3 [Recommended] Optimal Talos integration

#### A. Put Voxtral only in `vocal_cortex/providers/`

Recommended files:

- `vocal_cortex/providers/stt_voxtral.py`
- `vocal_cortex/providers/tts_voxtral.py`
- `vocal_cortex/providers/voxtral_runtime.py`

Responsibilities:

- `voxtral_runtime.py`
  - binary resolution
  - model/tokenizer/voices-dir resolution
  - GGUF vs directory mode
  - WSL/Windows path conversion helpers
  - subprocess invocation helpers

- `stt_voxtral.py`
  - input normalization
  - WAV conversion if needed
  - call runtime transcribe wrapper
  - return `TranscriptionResult`

- `tts_voxtral.py`
  - synthesis orchestration
  - staging path selection if needed
  - WAV-to-target-format conversion
  - return `SynthesisResult`

This keeps the gateway clean: the gateway only asks `STTService` or
`TTSService` to do work. It never knows that Voxtral is a Windows binary, a
GGUF model, or a path-conversion problem.

#### B. Treat Voxtral as an explicit local backend, not the default

Recommended Talos defaults:

- **Default STT:** `faster_whisper`
- **Default TTS:** `edge`
- **Optional local high-performance backend:** Voxtral / Voxtral-TTS

Why:

- `faster-whisper` is simpler, more portable, and less environment-coupled
- `edge` is simpler than Voxtral-TTS for default voice output
- Voxtral is strongest when you specifically want a **fully local speech stack**
  and you are willing to manage model paths, binary availability, and staging

So in Talos:

- `VOCAL_CORTEX['stt_provider'] = 'faster_whisper'` by default
- `VOCAL_CORTEX['tts_provider'] = 'edge'` by default
- users can explicitly set `voxtral` or `voxtral_tts`

#### C. Normalize provider configuration under `VOCAL_CORTEX`

Recommended settings shape:

```python
VOCAL_CORTEX = {
    'stt_provider': 'faster_whisper',
    'tts_provider': 'edge',
    'providers': {
        'voxtral': {
            'binary': '',
            'asr_model': '',
            'tts_model': '',
            'asr_gguf': '',
            'tts_gguf': '',
            'tokenizer': '',
            'voices_dir': '',
            'use_gguf': True,
            'default_voice': 'casual_female',
            'asr_delay': 6,
            'asr_max_mel_frames': 1200,
            'tts_max_frames': 2000,
            'tts_euler_steps': 6,
            'timeout_seconds': 300,
            'staging_root': '/mnt/c/Users/scfre',
        },
        'faster_whisper': {
            'model': 'base',
            'device': 'cpu',
            'compute_type': 'int8',
        },
        'edge': {
            'voice': 'en-US-AriaNeural',
        },
        'elevenlabs': {
            'voice_id': '',
            'model_id': 'eleven_multilingual_v2',
        },
    },
}
```

#### D. Introduce a tiny host-bridge abstraction

Hermes currently bakes WSL/Windows assumptions into `voxtral_tools.py`.
Talos should isolate that into a helper, for example:

- `vocal_cortex/providers/host_paths.py`

Example responsibilities:

- `to_provider_path(path: str, runtime: str) -> str`
- `provider_writable_temp(runtime: str, ext: str) -> str`
- `is_windows_interop_runtime() -> bool`

This avoids spreading `/mnt/c/` and `wslpath -w` logic across the codebase.
Only the Voxtral provider should care.

#### E. Provider result contracts should be structured, not dicts

Hermes returns raw dicts like:
- `{success, transcript, provider, error}`
- `{success, file_path, provider, error}`

Talos should instead return typed results, e.g.:

```python
class TranscriptionResult(BaseModel):
    success: bool
    text: str = ''
    provider: str
    language: str | None = None
    duration_seconds: float | None = None
    error: str | None = None

class SynthesisResult(BaseModel):
    success: bool
    audio_path: str | None = None
    provider: str
    format: str | None = None
    duration_seconds: float | None = None
    voice_name: str | None = None
    error: str | None = None
```

That matches the rest of the planned Layer 4 contract style.

### 11.4 [Recommended] End-to-end Talos flow with Voxtral

#### Inbound voice using Voxtral STT

1. Platform adapter caches inbound audio to a local file path
2. `GatewayOrchestrator` detects `voice_audio_path`
3. `STTService.transcribe(audio_path)` dispatches by configured provider
4. If provider = `voxtral`:
   - normalize input path
   - convert to WAV if needed
   - resolve binary/model/tokenizer
   - perform Windows-path translation only inside the provider runtime
   - run subprocess
5. Return typed `TranscriptionResult`
6. Replace envelope content with transcript text
7. Continue through normal FrontalLobe reasoning path

#### Outbound voice using Voxtral-TTS

1. FrontalLobe produces response text
2. `TTSService.synthesize(text)` dispatches by configured provider
3. If provider = `voxtral_tts`:
   - resolve binary/model/tokenizer/voices-dir
   - choose staging output if runtime requires it
   - synthesize to WAV
   - copy to target path if staged elsewhere
   - convert to final format (`.ogg` for voice delivery when needed)
4. Return typed `SynthesisResult`
5. `DeliveryPayload.voice_audio_path` is set
6. Platform adapter delivers as native voice or audio attachment

### 11.5 [Recommended] Failure handling and fallback rules

Talos should improve on Hermes here by making fallback explicit and typed.

Recommended behavior:

- If provider is explicitly `voxtral` and Voxtral is unavailable:
  - return a typed failure
  - do **not** silently switch providers

- If provider is `auto`:
  - STT fallback order:
    1. `faster_whisper`
    2. `voxtral`
    3. `openai` or `groq` if configured
  - TTS fallback order:
    1. `edge`
    2. `voxtral_tts`
    3. `elevenlabs` or `openai` if configured

This gives you deterministic explicit behavior for configured systems and a
clean escape hatch for `auto` mode.

### 11.6 [Recommended] Concrete implementation tasks for Talos

1. Create `vocal_cortex/providers/voxtral_runtime.py`
2. Move Hermes-style binary/model/tokenizer resolution into that runtime file
3. Create `stt_voxtral.py` and `tts_voxtral.py` with typed result contracts
4. Add `host_paths.py` helper to isolate WSL/Windows translation and staging
5. Add startup health probe:
   - binary exists
   - tokenizer path exists
   - selected model path exists
   - `ffmpeg` availability if format conversion is needed
6. Expose provider health in a gateway/vocal-cortex diagnostics endpoint
7. Add tests for:
   - binary resolution
   - GGUF vs model-directory mode
   - path translation
   - WAV conversion fallback
   - staged output copy-back
   - explicit-provider failure behavior

### 11.7 [Recommended Default]

The most optimal Talos position is:

- **Use Voxtral as a first-class optional local backend in `vocal_cortex`**
- **Do not make it the default STT/TTS engine**
- **Do not embed any Voxtral-specific logic in `talos_gateway`**
- **Do not copy Hermes's WSL assumptions into the gateway core**

That gives you the benefit of Hermes's real operational work without allowing a
host-specific local binary to become the dominant abstraction of Layer 4.

---

*End of Layer 4 implementation plan.*
