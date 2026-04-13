# Layer 2: FrontalLobe Enhancements

**Path B — Layer 2 Implementation Plan**  
**Date:** 2026-04-07  
**Estimated Scope:** 3 capabilities, ~1,000-1,500 lines, 1-2 weeks  
**Prerequisites:** Layer 1 (Core Tools) working, existing FrontalLobe and SynapseClient code.

---

## 1. Design Philosophy

Layer 2 makes the FrontalLobe reasoning loop production-grade for interactive conversational use. The existing `FrontalLobe.run()` works for batch/automated workflows but lacks the responsive qualities needed for real-time human interaction: it can overflow context windows, it blocks until the full response is done, and it can't be stopped mid-flight.

These 3 additions transform it from a batch processor into a conversational engine.

---

## 2. Layer 2A: Context Compression

**File:** `frontal_lobe/context_compressor.py` (~300 lines)

**The Problem:** LLM context windows are finite. Long conversations with extensive tool results will exceed the model's maximum context. Currently, FrontalLobe has no pressure valve — it just sends everything until the API rejects it.

**The Solution:** A service class that FrontalLobe calls between `_execute_turn()` iterations. When the estimated token count approaches ~80% of the model's context window, it compresses the conversation history.

### 2.1 Compression Strategy (in order of aggressiveness)

**Phase 1: Prune tool results (cheap, deterministic)**

- Identify `ReasoningTurn` entries where `message_role == "tool"`
- Keep the first 2 and last 2 tool results in the conversation
- For middle tool results: replace content with `"[Tool call to {tool_name} — result summarized]"`
- This is the cheapest compression: no LLM call needed, just truncation

**Phase 2: Summarize middle conversation (LLM-powered)**

- If Phase 1 isn't enough, identify the oldest `ReasoningTurn` entries (excluding the first and current turn)
- Extract just the user messages and assistant content (not tool calls)
- Send these to the model with a prompt: `"Summarize this conversation segment in 3-4 sentences. Preserve key decisions, tool call outcomes, and user corrections. Omit intermediate deliberation."`
- Replace the summarized turns with a single `ReasoningTurn` of type "summary"

**Phase 3: Aggressive pruning (last resort)**

- If still over limit after Phase 2, discard ALL tool results except the most recent
- Keep only: system prompt, first user message, recent user messages, current working context

### 2.2 Token Estimation

```python
def estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token for English text."""
    return len(text) // 4

def estimate_turn_tokens(turn: ReasoningTurn) -> int:
    """Sum tokens across role + content + any tool_calls."""
    total = estimate_tokens(turn.content)
    if turn.tool_calls:
        total += sum(estimate_tokens(tc.arguments or '') for tc in turn.tool_calls)
    return total
```

For Anthropic models, use actual token count from API response if available via `response.usage.input_tokens`.

### 2.3 Compression Check in FrontalLobe

In `FrontalLobe._execute_turn()`, before building the message list for the LLM call:

```python
def _check_and_compress(self, messages: list[dict], model_max_tokens: int) -> list[dict]:
    """Compress message list if approaching context limit."""
    threshold = int(model_max_tokens * 0.80)
    current_tokens = sum(estimate_tokens(m.get('content', '')) for m in messages)
    if current_tokens >= threshold:
        compressor = ContextCompressor(
            reasoning_session=self.reasoning_session,
            model_id=self.current_model_id,
        )
        return compressor.compress(messages, threshold)
    return messages
```

### 2.4 Database Strategy

When compressing, the `ReasoningTurn` records in the database must reflect the compressed state:

- Option: Mark original turns as `is_compressed=True`, create a new turn with `type='summary'`
- The summary turn's `content` field contains the LLM-generated summary
- Original turns are kept for audit (don't delete them — that breaks the audit trail)

### 2.5 Tests

- No compression needed when context is well below threshold
- Phase 1 compression: tool results beyond boundaries are truncated
- Phase 2 compression: middle conversation is summarized via LLM (mock)
- Phase 3 compression: aggressive pruning applied
- Compression is idempotent (calling twice doesn't double-compress)
- Summary turns are correctly created in DB
- Token estimation is within 20% of actual count

---

## 3. Layer 2B: Streaming Support

**File:** `frontal_lobe/synapse_client.py` (enhance existing)

**The Problem:** FrontalLobe's `SynapseClient.chat()` is currently a blocking call — it waits for the full LLM response, then returns. For interactive sessions, users see nothing until the entire response is complete. We need token-by-token delivery.

**The Solution:** A `stream_callback` parameter on `SynapseClient.chat()` (or a new `_stream()` method) that fires for each token delta as it arrives.

### 3.1 LiteLLM Streaming

LiteLLM supports streaming via `litellm.completion(stream=True)`. The response is an iterable of chunk objects.

```python
async def chat_stream(
    self,
    messages: list[dict],
    stream_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    interrupt_check: Optional[Callable[[], bool]] = None,
) -> str:
    """Stream LLM response, calling stream_callback per token delta.
    
    Returns the full accumulated response text when complete.
    """
    response = await litellm.acompletion(
        model=self.model_name,
        messages=messages,
        stream=True,
        **self._build_kwargs(),
    )
    
    accumulated = []
    async for chunk in response:
        delta = chunk.choices[0].delta.content or ''
        if delta:
            accumulated.append(delta)
            if stream_callback:
                await stream_callback(delta)
            if interrupt_check and interrupt_check():
                raise InterruptedError('Stream interrupted')
    
    full_text = ''.join(accumulated)
    return full_text
```

### 3.2 Channels Integration

The `stream_callback` passed by FrontalLobe sends tokens to a Django Channels group:

```python
# In talos_gateway (Layer 4):
async def on_token_delta(token: str):
    await self.channel_layer.group_send(
        f"session_{session_id}",
        {"type": "token_delta", "token": token},
    )
```

The gateway's `GatewayTokenStreamConsumer` receives these and forwards them over WebSocket to the platform adapter.

### 3.3 Streaming in FrontalLobe._execute_turn()

```python
async def _execute_turn(self, stream_callback=None, interrupt_check=None):
    messages = self._build_messages()
    messages = self._check_and_compress(messages)
    
    # Check interrupt before starting
    if interrupt_check and interrupt_check():
        self._handle_interrupt()
        return
    
    response_text = await self.synapse_client.chat_stream(
        messages,
        stream_callback=stream_callback,
        interrupt_check=interrupt_check,
    )
    
    # Process tool calls as usual (after streaming completes for this turn)
    if response_text contains tool_calls:
        tool_results = await self._process_tool_calls(response_text)
        return await self._execute_turn(stream_callback, interrupt_check)
    
    return response_text
```

### 3.4 Important Design Decision: Streaming + Tool Calls

When the model streams a tool call, it doesn't stream the tool's output — tool execution and output are separate. The streaming is for the natural-language text portions. Tool calls appear as structured data in the stream. The callback fires on text deltas only.

**Contract with stream_callback:** It receives only human-readable text tokens. Tool call structures are communicated separately through the existing `ReasoningTurn.tool_calls` mechanism.

### 3.5 Anthropic Prompt Caching (Bonus)

As part of streaming support, extend `SynapseClient._build_kwargs()` to inject `cache_control` breakpoints for Anthropic providers:

```python
def _build_kwargs(self):
    kwargs = {...}
    if self.model_provider == 'anthropic':
        kwargs['extra_headers'] = {
            'anthropic-beta': 'prompt-caching-2024-07-31',
        }
    return kwargs
```

This is ~20 lines of configuration — small but impactful for cost reduction on long conversations.

### 3.6 Tests

- Streaming callback receives each token delta (mocked LiteLLM)
- Interrupt check mid-stream raises InterruptedError
- Full accumulated text matches non-streaming response
- Tool call responses work correctly after streaming turn
- Callback is called N times for N tokens
- Anthropic prompt caching headers are added for Anthropic models
- Non-Anthropic models do NOT get cache headers (they'd error)

---

## 4. Layer 2C: Interrupt Mechanism

**File:** `frontal_lobe/frontal_lobe.py` (enhance existing `_execute_turn()`)  
**File:** `frontal_lobe/models.py` (no changes needed — Spike.status already has the states)

**The Problem:** Once FrontalLobe starts reasoning, it runs to completion. If the user cancels mid-conversation, the model may continue burning tokens and making API calls.

**The Solution:** Check `Spike.status` for STOPPING between turns and between streaming chunks.

### 4.1 Spike Status Checkpoints

The interrupt check happens at 3 points:

1. **Before starting a turn:** In `FrontalLobe._execute_turn()` entry
2. **Between streaming chunks:** In `chat_stream()`, each iteration of the async response loop
3. **Before executing tool calls:** Between `response_text` parsing and `process_tool_calls()`

```python
def _check_interrupt(self) -> bool:
    """Return True if this Spike should stop."""
    if self.spike and hasattr(self.spike, 'status'):
        spike_status = self.spike.status.name if self.spike.status else ''
        return spike_status == 'STOPPING'
    return False
```

### 4.2 Gateway-Initiated Interrupt

The `talos_gateway` sets `Spike.status = STOPPING` when it receives a cancel signal from the user (e.g., Ctrl+C on the CLI, or a cancel button in a client). This is the only external interface — everything internal is a poll.

```python
# In talos_gateway:
async def handle_interrupt(self, session_id: str):
    spike = self._resolve_spike(session_id)
    if spike:
        spike.status = SpikeStatus.objects.get(name='STOPPING')
        spike.save(update_fields=['status_id', 'modified'])
```

### 4.3 Graceful Termination

When interrupted, FrontalLobe should:

1. Not fire additional API calls
2. Not execute pending tool calls
3. Save the current `ReasoningTurn` (partial result if mid-stream)
4. Return: `{"interrupted": True, "partial_content": str, "turns_completed": int}`
5. Set `ReasoningSession.status = ReasoningStatusID.INTERRUPTED`

### 4.4 Tests

- Interrupt before turn → turn not started, status updated
- Interrupt mid-stream → partial content saved, no more API calls
- Interrupt before tool execution → tool call not executed
- Non-stopping status → execution continues normally
- Spike is None (direct call not via CNS) → interrupt check is no-op

---

## 5. Integration Flow

With all 3 capabilities working together, a turn looks like:

```
User message arrives at talos_gateway
  │
  ▼
Gateway creates/gets ReasoningSession, launches FrontalLobe
  │
  │  stream_callback: send tokens to Channels group
  │  interrupt_check: check Spike.status == STOPPING
  │
  ▼
FrontalLobe._execute_turn(stream_callback=..., interrupt_check=...)
  │
  ├── Check interrupt → STOPPING? → abort immediately
  │
  ├── Build messages from ReasoningTurn history
  │
  ├── Context compression check
  │     └── If >80% tokens: prune tool results, summarize → compressed messages
  │
  ├── SynapseClient.chat_stream(messages, stream_callback, interrupt_check)
  │     │
  │     ├── For each token delta:
  │     │     └── stream_callback(token) → Channels gateway → user
  │     ├── Check interrupt between each chunk
  │     │     └── If interrupted: stop, return partial
  │     └── Return accumulated full text
  │
  ├── If tool calls in response:
  │     ├── Check interrupt again
  │     ├── Execute tools via ParietalLobe
  │     └── Recursive _execute_turn() (same stream_callback, interrupt_check)
  │
  └── Save ReasoningTurn(s) to DB
```

---

## 6. File Changes Summary


| File                                            | Action                                                           | Est. Lines |
| ----------------------------------------------- | ---------------------------------------------------------------- | ---------- |
| `frontal_lobe/context_compressor.py`            | NEW                                                              | ~300       |
| `frontal_lobe/synapse_client.py`                | ENHANCE (add chat_stream, _build_kwargs cache)                   | ~80        |
| `frontal_lobe/frontal_lobe.py`                  | ENHANCE (_execute_turn: compression check, streaming, interrupt) | ~120       |
| `frontal_lobe/tests/test_context_compressor.py` | NEW                                                              | ~200       |
| `frontal_lobe/tests/test_streaming.py`          | NEW                                                              | ~150       |
| `frontal_lobe/tests/test_interrupt.py`          | NEW                                                              | ~80        |


**Total:** ~930 new lines, ~120 modified lines.

---

## 7. Acceptance Criteria

1. Context compression activates automatically at 80% of model context window
2. Streaming tokens are delivered via Django Channels within 200ms of LLM production
3. Interrupt check responds within 500ms of Spike status change
4. Anthropic prompt caching headers are present for Anthropic model requests
5. Compressed conversations preserve the logical thread (key decisions, corrections)
6. All 3 features work independently — removing one doesn't break the others
7. Tests cover all 3 features with mocked LLM responses

---

*End of Layer 2 Plan*