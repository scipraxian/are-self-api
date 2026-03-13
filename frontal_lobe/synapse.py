import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Union

import requests
from django.conf import settings

from frontal_lobe.constants import FrontalLobeConstants
from identity.models import IdentityDisc

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

    EMBEDDING_KEY = 'embedding'


@dataclass
class OllamaChatPayload:
    """Strictly typed payload for the /api/chat endpoint."""

    model: str
    messages: List[Dict[str, Any]]
    options: Dict[str, Any]
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None

    def size(self):
        """Approximate payload size for context window tuning."""
        base = len(str(self.model)) + sum(len(str(msg)) for msg in self.messages)
        if not self.tools:
            return base
        return base + sum(len(str(tool)) for tool in self.tools)


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

    def __init__(self, identity_source: Union[IdentityDisc, str]):
        """
        Initialize the client using either:

        - an IdentityDisc (preferred for runtime, so we can resolve the model
          from identity_disc.ai_model and later use the disc for accounting), or
        - a raw model name string (backwards-compatible for tests and simple callers).
        """
        self.identity_disc: Optional[IdentityDisc] = None

        if isinstance(identity_source, IdentityDisc):
            identity_disc = identity_source
            if not identity_disc.ai_model:
                raise ValueError(
                    f'IdentityDisc "{identity_disc}" has no ai_model configured.'
                )
            self.identity_disc = identity_disc
            self.model = identity_disc.ai_model.name
        else:
            # Backwards-compatible path: accept a bare model name.
            self.model = str(identity_source)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> OllamaResponse:
        """Transmits message history to the model, optionally with tool
        schemas."""

        payload_obj = OllamaChatPayload(
            model=self.model,
            messages=messages,
            options=options or {},
            tools=tools,
        )

        size = payload_obj.size()
        num_ctx = int(size / 3) + 2048  # TODO: expose constants.
        payload_obj.options.update(num_ctx=num_ctx)
        logger.info(f'[Synapse] Firing API payload: [ {num_ctx} tokens ]')

        # Strip None values
        payload_dict = {
            k: v for k, v in asdict(payload_obj).items() if v is not None
        }

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

    def embed(self, text: str) -> List[float]:
        """Generates an embedding vector using the modern Ollama /api/embed endpoint."""
        # Corrected: Singular 'embed' endpoint to resolve 404
        url = f'{OllamaConstants.BASE_URL}/api/embed'

        # Corrected: Using 'input' key as required by modern Ollama API
        payload = {
            OllamaConstants.KEY_MODEL: self.model,
            'input': text,
        }

        logger.info(
            f'[Synapse] Generating embedding for text [{len(text)} chars]'
        )
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=OllamaConstants.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()

            # The 'embeddings' key in the response remains plural (returning a list of lists)
            # or 'embedding' if it was a single string. Ollama /api/embed usually returns
            # an 'embeddings' array.
            embeddings = data.get('embeddings', [])
            return embeddings[0] if embeddings else []

        except requests.RequestException as e:
            logger.error(f'Ollama Embed Misfire: {e}')
            return []
