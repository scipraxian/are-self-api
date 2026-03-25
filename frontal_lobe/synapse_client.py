import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import litellm
from django.conf import settings
from litellm import ModelResponse
from litellm.exceptions import (
    APIConnectionError,
    BadRequestError,
    NotFoundError,
    OpenAIError,
    RateLimitError,
)

from hypothalamus.models import AIModelCapabilities, AIModelProviderUsageRecord

# ------------------------------------------------------------------ #
#  LiteLLM Global Config                                             #
# ------------------------------------------------------------------ #

litellm.telemetry = False
litellm.set_verbose = False
litellm.drop_params = True

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Provider Identity                                                  #
# ------------------------------------------------------------------ #

PROVIDER_OLLAMA = 'ollama'

# ------------------------------------------------------------------ #
#  LiteLLM kwarg keys                                                #
# ------------------------------------------------------------------ #

KWARG_MODEL = 'model'
KWARG_MESSAGES = 'messages'
KWARG_STREAM = 'stream'
KWARG_API_KEY = 'api_key'
KWARG_API_BASE = 'api_base'
KWARG_TOOLS = 'tools'
KWARG_TOOL_CHOICE = 'tool_choice'
KWARG_MAX_TOKENS = 'max_tokens'
KWARG_NUM_KEEP_ALIVE = 'num_keep_alive'

TOOL_CHOICE_AUTO = 'auto'

# ------------------------------------------------------------------ #
#  LiteLLM Usage / Telemetry dict keys                               #
# ------------------------------------------------------------------ #

USAGE_PROMPT_TOKENS = 'prompt_tokens'
USAGE_COMPLETION_TOKENS = 'completion_tokens'
USAGE_PROMPT_TOKENS_DETAILS = 'prompt_tokens_details'
USAGE_COMPLETION_TOKENS_DETAILS = 'completion_tokens_details'
USAGE_CACHE_CREATION_INPUT_TOKENS = 'cache_creation_input_tokens'

DETAIL_REASONING_TOKENS = 'reasoning_tokens'
DETAIL_CACHED_TOKENS = 'cached_tokens'
DETAIL_AUDIO_TOKENS = 'audio_tokens'

# ------------------------------------------------------------------ #
#  Unload Sentinel Payload                                           #
# ------------------------------------------------------------------ #

UNLOAD_ROLE = 'system'
UNLOAD_CONTENT = 'unload'
UNLOAD_MAX_TOKENS = 1
UNLOAD_KEEP_ALIVE = 0

# ------------------------------------------------------------------ #
#  Error Messages                                                    #
# ------------------------------------------------------------------ #

ERR_CONTEXT_WINDOW = 'Context Window Exceeded.'


# ------------------------------------------------------------------ #
#  Dataclasses                                                       #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class TelemetryMetrics:
    """Strictly maps to AIModelProviderUsageRecord fields."""

    reasoning_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    audio_tokens: int = 0


@dataclass(frozen=True)
class SynapseResponse:
    """Immutable FinOps receipt and content payload."""

    content: str
    model: str
    tokens_input: int
    tokens_output: int
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    metrics: TelemetryMetrics = field(default_factory=TelemetryMetrics)
    is_error: bool = False
    error_message: str = ''
    request_payload: Dict[str, Any] = field(default_factory=dict)
    response_payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def error(cls, model_id: str, message: str) -> 'SynapseResponse':
        return cls(
            content='',
            model=model_id,
            tokens_input=0,
            tokens_output=0,
            is_error=True,
            error_message=message,
        )


# ------------------------------------------------------------------ #
#  Testable Pure Functions (Zero side-effects, Zero DB hits)         #
# ------------------------------------------------------------------ #


def resolve_api_key(env_var_name: Optional[str]) -> Optional[str]:
    """Resolves an OS or Django setting environment variable cleanly."""
    if not env_var_name:
        return None
    return getattr(settings, env_var_name, None) or os.environ.get(env_var_name)


def normalize_tool_calls(message: Any) -> List[Dict[str, Any]]:
    """Normalizes unpredictable Pydantic/Dict objects from LiteLLM into flat dicts."""
    tool_calls = getattr(message, 'tool_calls', None)
    if not tool_calls:
        return []

    return [
        tc.model_dump()
        if hasattr(tc, 'model_dump')
        else tc.dict()
        if hasattr(tc, 'dict')
        else tc
        for tc in tool_calls
    ]


def parse_telemetry(usage: Any) -> TelemetryMetrics:
    """Safely extracts granular FinOps data from the LiteLLM usage block."""
    if not usage:
        return TelemetryMetrics()

    usage_dict = (
        usage.model_dump()
        if hasattr(usage, 'model_dump')
        else (usage.dict() if hasattr(usage, 'dict') else dict(usage))
    )

    prompt_details: Dict[str, Any] = (
        usage_dict.get(USAGE_PROMPT_TOKENS_DETAILS) or {}
    )
    comp_details: Dict[str, Any] = (
        usage_dict.get(USAGE_COMPLETION_TOKENS_DETAILS) or {}
    )

    return TelemetryMetrics(
        reasoning_tokens=comp_details.get(DETAIL_REASONING_TOKENS, 0),
        cache_read_input_tokens=prompt_details.get(DETAIL_CACHED_TOKENS, 0),
        cache_creation_input_tokens=usage_dict.get(
            USAGE_CACHE_CREATION_INPUT_TOKENS, 0
        ),
        audio_tokens=(
            prompt_details.get(DETAIL_AUDIO_TOKENS, 0)
            + comp_details.get(DETAIL_AUDIO_TOKENS, 0)
        ),
    )


# ------------------------------------------------------------------ #
#  The Client                                                        #
# ------------------------------------------------------------------ #


class SynapseClient:
    """
    Stateful execution conduit.
    Mutates the AIModelProviderUsageRecord in place with exact FinOps and Response data.
    """

    def __init__(self, ledger: AIModelProviderUsageRecord):
        self.ledger = ledger
        self.model_id = self.ledger.ai_model_provider.provider_unique_model_id
        self.ai_model_provider = self.ledger.ai_model_provider
        self.network_config = self.ai_model_provider.provider

    def chat(self, **kwargs) -> (bool, List[Dict[str, Any]]):
        """
        Executes inference. Trips Postgres Circuit Breaker on ANY failure.
        Returns a normalized list of tool_calls (empty list if none).
        """
        messages = self.ledger.request_payload
        tools = self.ledger.tool_payload if self.ledger.tool_payload else None

        litellm_kwargs = self._build_kwargs(messages, tools, kwargs)

        try:
            response = litellm.completion(**litellm_kwargs)
        except Exception as e:  # YES. CATCH EVERYTHING.
            error_str = str(e).lower()
            error_type = e.__class__.__name__.lower()

            # --- SCAR TISSUE LOGIC (Permanent Bench) ---
            # We use the class name to mimic your old isinstance(e, NotFoundError) check
            if 'notfound' in error_type and (
                'tool' in error_str or 'function' in error_str
            ):
                if self.ai_model_provider:
                    cap = AIModelCapabilities.objects.filter(
                        name='function_calling'
                    ).first()
                    if cap:
                        self.ai_model_provider.disabled_capabilities.add(cap)
                        logger.warning(
                            f'[Synapse] SCAR TISSUE: Permanently disabled function_calling '
                            f'for {self.model_id} due to 404 endpoint rejection.'
                        )
                # Failover
                return False, []

            # --- CIRCUIT BREAKER LOGIC (Temporary Bench - Catch-All) ---
            # If the API failed for ANY other reason (502, 429, timeouts, parsing errors), bench it.
            if self.ai_model_provider:
                self.ai_model_provider.trip_circuit_breaker()

                logger.warning(
                    f'[Synapse] ROUTING FAILURE. Circuit Breaker tripped for {self.model_id}.\r'
                    f'Error: {error_type} | Reason: {error_str}...\r'
                    f'Cooldown until: {self.ai_model_provider.rate_limit_reset_time}\r\r'
                )

            # Failover
            return False, []
        # --- SUCCESS: CLEAR THE BREAKER ---
        if (
            self.ai_model_provider
            and self.ai_model_provider.rate_limit_counter > 0
        ):
            self.ai_model_provider.reset_circuit_breaker()
            logger.info(f'[Synapse] Circuit Breaker reset for {self.model_id}')

        # Stamp the ledger and return tool calls
        return True, self._process_response(response)

    def _process_response(
        self, response: ModelResponse
    ) -> List[Dict[str, Any]]:
        """Stamps the FinOps receipt directly onto the ledger."""

        # 1. Stamp Raw Output
        self.ledger.response_payload = (
            response.model_dump()
            if hasattr(response, 'model_dump')
            else (
                response.dict() if hasattr(response, 'dict') else dict(response)
            )
        )

        # 2. Extract Data
        message = response.choices[0].message
        usage = getattr(response, 'usage', None)
        metrics = parse_telemetry(usage)

        # 3. Stamp Token Usage
        self.ledger.input_tokens = (
            getattr(usage, USAGE_PROMPT_TOKENS, 0) if usage else 0
        )
        self.ledger.output_tokens = (
            getattr(usage, USAGE_COMPLETION_TOKENS, 0) if usage else 0
        )
        self.ledger.reasoning_tokens = metrics.reasoning_tokens
        self.ledger.cache_read_input_tokens = metrics.cache_read_input_tokens
        self.ledger.cache_creation_input_tokens = (
            metrics.cache_creation_input_tokens
        )
        self.ledger.audio_tokens = metrics.audio_tokens

        # Return tool calls so the Frontal Lobe can immediately execute them
        return normalize_tool_calls(message)

    def unload(self) -> None:
        """Issues an explicit VRAM drop command for local hardware models."""
        if self.network_config.key.lower() != PROVIDER_OLLAMA:
            return

        try:
            litellm.completion(
                **{
                    KWARG_MODEL: self.model_id,
                    KWARG_MESSAGES: [
                        {
                            'role': UNLOAD_ROLE,
                            'content': UNLOAD_CONTENT,
                        }
                    ],
                    KWARG_MAX_TOKENS: UNLOAD_MAX_TOKENS,
                    KWARG_NUM_KEEP_ALIVE: UNLOAD_KEEP_ALIVE,
                    KWARG_API_BASE: (
                        self.network_config.base_url.rstrip('/')
                        if self.network_config.base_url
                        else None
                    ),
                    KWARG_API_KEY: resolve_api_key(
                        self.network_config.api_key_env_var
                    ),
                }
            )
        except Exception as exc:
            logger.warning(
                '[Synapse] VRAM unload signal failed for %s: %s',
                self.model_id,
                exc,
            )

    def _build_kwargs(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Maps standard inputs and DB configuration to LiteLLM kwargs."""
        kwargs: Dict[str, Any] = {
            KWARG_MODEL: self.model_id,
            KWARG_MESSAGES: messages,
            KWARG_STREAM: False,
            **options,
        }

        if self.network_config.requires_api_key:
            kwargs[KWARG_API_KEY] = resolve_api_key(
                self.network_config.api_key_env_var
            )

        if self.network_config.base_url:
            kwargs[KWARG_API_BASE] = self.network_config.base_url.rstrip('/')

        if tools:
            kwargs[KWARG_TOOLS] = tools
            kwargs[KWARG_TOOL_CHOICE] = TOOL_CHOICE_AUTO

        return kwargs
