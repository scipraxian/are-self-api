import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union

import requests
from django.conf import settings

from frontal_lobe.models import ModelRegistry
from frontal_lobe.synapse import SynapseResponse
from identity.models import IdentityDisc

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
        self._requires_api_key: bool = True
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
                base_url = (
                    provider.base_url.rstrip('/') if provider.base_url else ''
                )
                chat_path = provider.chat_path or '/v1/chat/completions'
                if not chat_path.startswith('/'):
                    chat_path = f'/{chat_path}'
                self._chat_url = f'{base_url}{chat_path}'
                self._requires_api_key = True
                self._api_key_header = (
                    provider.api_key_header or 'Authorization'
                )
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

    def _get_api_key(self) -> Optional[str]:
        """Resolve API key from Django settings or env. Used for auth header."""
        if not self._requires_api_key:
            return None
        # Prefer Django settings so Celery workers pick up config.settings
        key = getattr(settings, 'OPENROUTER_API_KEY', None) or ''
        key = (
            key
            or os.environ.get(self._api_key_env_var or 'OPENROUTER_API_KEY')
            or ''
        ).strip()
        if not key and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                'OpenRouter API key missing: set OPENROUTER_API_KEY in Django '
                'settings or OPENROUTER_API_KEY env var (restart Celery after changing settings).'
            )
        return key or None

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            'Content-Type': 'application/json',
        }

        api_key = self._get_api_key()
        if api_key:
            if api_key.startswith('Bearer '):
                print(
                    "DEBUG: WARNING - API key already includes 'Bearer ' prefix!"
                )
                headers[self._api_key_header] = api_key
            else:
                headers[self._api_key_header] = f'Bearer {api_key}'
        else:
            print('DEBUG: No API key found, no auth header added')
            if self._requires_api_key:
                print('DEBUG: ERROR - Auth required but no key available!')

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
        if self._requires_api_key and not self._get_api_key():
            env_var = self._api_key_env_var or 'OPENROUTER_API_KEY'
            msg = (
                f'OpenRouter requires an API key. Set the {env_var} environment '
                'variable (e.g. in your Celery worker) or OPENROUTER_API_KEY in '
                'Django settings.'
            )
            logger.error(f'OpenRouter Synapse Misfire: {msg}')
            return SynapseResponse(
                content=msg,
                tool_calls=[],
                tokens_input=0,
                tokens_output=0,
                model=self.model,
            )

        options = options or {}

        # Build payload dictionary manually for better control
        payload_dict = {
            'model': self.model,
            'messages': messages,
            'stream': False,
        }

        # Only add tools if they exist AND are non-empty
        if tools:
            payload_dict['tools'] = tools
            # Add tool_choice when tools are provided (required by some models)
            payload_dict['tool_choice'] = 'auto'

        # Add optional parameters only if they have values
        if options.get('max_tokens') is not None:
            payload_dict['max_tokens'] = options['max_tokens']
        if options.get('temperature') is not None:
            payload_dict['temperature'] = options['temperature']

        # print(f'DEBUG: Sending payload: {json.dumps(payload_dict, indent=2)}')
        max_retries = 3
        try:
            while max_retries:
                max_retries -= 1
                start_time = time.time()
                logger.info(f'>>>>>>>>>>>>>Sending request to Provider...')
                response = requests.post(
                    self._chat_url,
                    json=payload_dict,
                    headers=self._build_headers(),
                    timeout=options.get('timeout', 600),
                )
                inf_duration = timedelta(seconds=time.time() - start_time)
                if response.status_code != 200:
                    logger.warning(
                        f'Retry WAIT due to Provider {response.status_code}'
                    )
                    time.sleep(4)
                    logger.warning(
                        f'Retry now due to Provider {response.status_code}'
                    )
                    continue
                break
            response.raise_for_status()
            logger.info(
                f'<<<<<<<<<<<<<Successful response from Provider {inf_duration}s.'
            )
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
            if (
                hasattr(e, 'response')
                and getattr(e, 'response', None) is not None
            ):
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

    def unload(self) -> bool:
        """Unload the OpenRouter Synapse instance.

        This is for compatibility.
        """
        return self == self
