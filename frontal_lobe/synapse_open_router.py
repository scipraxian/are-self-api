import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import requests
from django.conf import settings

from identity.models import IdentityDisc
from frontal_lobe.models import ModelRegistry
from frontal_lobe.synapse import SynapseResponse


logger = logging.getLogger(__name__)


@dataclass
class OpenRouterChatPayload:
    """Strictly typed payload for OpenRouter/OpenAI-style chat completions."""

    model: str
    messages: List[Dict[str, Any]]
    tools: Optional[List[Dict[str, Any]]] = None
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


class OpenRouterClient:
    """
    Client that speaks OpenAI-compatible JSON over HTTP to OpenRouter.

    It maps OpenRouter responses back into the universal SynapseResponse
    contract so the rest of the system remains provider-agnostic.
    """

    def __init__(self, identity_disc: Union[IdentityDisc, str]):
        """
        Initialize the client.

        In normal runtime, an IdentityDisc is provided so the underlying
        ModelRegistry and its linked ModelProvider can be resolved.
        For backwards-compatible tests, a raw model name string is allowed.
        """

        self.identity_disc: Optional[IdentityDisc] = None
        self._chat_url: Optional[str] = None
        self._requires_api_key: bool = False
        self._api_key_header: str = 'Authorization'
        self._api_key_env_var: Optional[str] = None

        if isinstance(identity_disc, IdentityDisc):
            if not identity_disc.ai_model:
                raise ValueError(
                    f'IdentityDisc "{identity_disc}" has no ai_model configured.'
                )
            self.identity_disc = identity_disc
            registry: ModelRegistry = identity_disc.ai_model
            self.model = registry.name

            provider = getattr(registry, 'provider', None)
            if provider:
                base_url = provider.base_url.rstrip('/') if provider.base_url else ''
                chat_path = provider.chat_path or '/v1/chat/completions'
                if not chat_path.startswith('/'):
                    chat_path = f'/{chat_path}'
                self._chat_url = f'{base_url}{chat_path}'
                self._requires_api_key = provider.requires_api_key
                self._api_key_header = provider.api_key_header or 'Authorization'
                self._api_key_env_var = provider.api_key_env_var
        else:
            # Bare model string path; used only in narrow test scenarios.
            self.model = str(identity_disc)

        # Fallback to global settings for URL/API key if provider is not wired.
        if not self._chat_url:
            base_url = getattr(
                settings, 'OPENROUTER_BASE_URL', 'https://openrouter.ai/api'
            ).rstrip('/')
            self._chat_url = f'{base_url}/v1/chat/completions'

        if not self._api_key_env_var:
            # Prefer explicit environment variable but fall back to Django settings.
            self._api_key_env_var = 'OPENROUTER_API_KEY'

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            'Content-Type': 'application/json',
        }

        api_key: Optional[str] = None
        if self._requires_api_key:
            api_key = os.getenv(self._api_key_env_var or '') or getattr(
                settings, 'OPENROUTER_API_KEY', None
            )

        if api_key:
            # OpenRouter typically uses Bearer tokens via Authorization header.
            headers[self._api_key_header] = f'Bearer {api_key}'

        # Optional but recommended metadata headers
        site = getattr(settings, 'OPENROUTER_SITE', None)
        app_title = getattr(settings, 'OPENROUTER_APP_TITLE', None)
        if site:
            headers['HTTP-Referer'] = site
        if app_title:
            headers['X-Title'] = app_title

        return headers

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> SynapseResponse:
        """
        Send a chat completion request to OpenRouter and map it into SynapseResponse.
        """

        options = options or {}
        payload = OpenRouterChatPayload(
            model=self.model,
            messages=messages,
            tools=tools,
            stream=False,
            max_tokens=options.get('max_tokens'),
            temperature=options.get('temperature'),
        )

        # Strip None values and dataclass metadata.
        payload_dict = {
            k: v
            for k, v in payload.__dict__.items()
            if v is not None
        }

        try:
            response = requests.post(
                self._chat_url,
                json=payload_dict,
                headers=self._build_headers(),
                timeout=options.get('timeout', 600),
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get('choices', []) or []
            first_choice = choices[0] if choices else {}
            msg_data = first_choice.get('message', {}) or {}

            usage = data.get('usage', {}) or {}

            return SynapseResponse(
                content=msg_data.get('content', '') or '',
                tool_calls=msg_data.get('tool_calls', []) or [],
                tokens_input=usage.get('prompt_tokens', 0) or 0,
                tokens_output=usage.get('completion_tokens', 0) or 0,
                model=data.get('model', self.model),
            )

        except Exception as e:
            error_details = str(e)
            if hasattr(e, 'response') and getattr(e, 'response', None) is not None:
                try:
                    error_details += f' | Details: {e.response.text}'
                except Exception:
                    # If accessing response.text fails, ignore silently.
                    pass
            logger.error(f'OpenRouter Synapse Misfire: {error_details}')

            return SynapseResponse(
                content=f'Error communicating with upstream LLM: {error_details}',
                tool_calls=[],
                tokens_input=0,
                tokens_output=0,
                model=self.model,
            )

