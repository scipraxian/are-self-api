import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class OllamaConstants:
    """Centralized string literals and configuration for the Ollama Synapse."""

    # TODO: Get this from environments.models.Environment
    BASE_URL = getattr(settings, 'OLLAMA_URL', 'http://localhost:11434').rstrip(
        '/'
    )
    CHAT_URL = f'{BASE_URL}/api/chat'
    TIMEOUT_SECONDS = 600

    # Payload Keys
    KEY_MODEL = 'model'
    KEY_MESSAGES = 'messages'
    KEY_STREAM = 'stream'
    KEY_OPTIONS = 'options'
    KEY_TOOLS = 'tools'

    # Response Keys
    KEY_MESSAGE = 'message'
    KEY_CONTENT = 'content'
    KEY_TOOL_CALLS = 'tool_calls'
    KEY_PROMPT_EVAL_COUNT = 'prompt_eval_count'
    KEY_EVAL_COUNT = 'eval_count'

    # System Strings
    ERR_MSG_PREFIX = 'Error communicating with local LLM:'


@dataclass
class OllamaChatPayload:
    """Strictly typed payload for the /api/chat endpoint."""

    model: str
    messages: List[Dict[str, Any]]
    options: Dict[str, Any]
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None


@dataclass
class ChatMessage:
    """Strictly typed representation of a single message in a Chat array."""

    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    name: Optional[str] = None  # Used exclusively when role='tool'

    def to_dict(self) -> Dict[str, Any]:
        """Serializes to dict, stripping None values to satisfy strict JSON parsers."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class OllamaResponse:
    """Strictly typed return structure for the reasoning engine."""

    content: str
    tool_calls: List[Dict[str, Any]]
    tokens_input: int
    tokens_output: int
    model: str


class OllamaClient:
    """Synaptic interface to the local AI. Supports Native Tool Calling."""

    def __init__(self, model: str):
        self.model = model

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> OllamaResponse:
        """Transmits message history to the model, optionally with tool schemas."""

        payload_obj = OllamaChatPayload(
            model=self.model,
            messages=messages,
            options=options or {},
            tools=tools,
        )

        # Strip None values
        payload_dict = {
            k: v for k, v in asdict(payload_obj).items() if v is not None
        }

        logger.info(
            f'[Synapse] Firing API payload: [ {len(str(payload_dict))} chars ]'
        )

        try:
            response = requests.post(
                OllamaConstants.CHAT_URL,
                json=payload_dict,
                timeout=OllamaConstants.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()

            msg_data = data.get(OllamaConstants.KEY_MESSAGE, {})

            return OllamaResponse(
                content=msg_data.get(OllamaConstants.KEY_CONTENT, ''),
                tool_calls=msg_data.get(OllamaConstants.KEY_TOOL_CALLS, []),
                tokens_input=data.get(OllamaConstants.KEY_PROMPT_EVAL_COUNT, 0),
                tokens_output=data.get(OllamaConstants.KEY_EVAL_COUNT, 0),
                model=data.get(OllamaConstants.KEY_MODEL, self.model),
            )

        except requests.RequestException as e:
            error_details = str(e)
            if hasattr(e, 'response') and e.response is not None:
                error_details += f' | Details: {e.response.text}'
            logger.error(f'Ollama Synapse Misfire: {error_details}')

            # Return a safe fallback response so the loop doesn't explode
            return OllamaResponse(
                content=f'{OllamaConstants.ERR_MSG_PREFIX} {error_details}',
                tool_calls=[],
                tokens_input=0,
                tokens_output=0,
                model=self.model,
            )

    def unload(self) -> bool:
        """Forces Ollama to immediately unload the model from VRAM."""
        try:
            payload = {'model': self.model, 'keep_alive': 0}
            requests.post(OllamaConstants.CHAT_URL, json=payload, timeout=2)
            logger.info(f'[Synapse] Successfully unloaded model {self.model}')
            return True
        except requests.RequestException as e:
            logger.warning(f'[Synapse] Unload warning (non-fatal): {e}')
            return False
