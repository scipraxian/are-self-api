"""
Multimodal image Q&A via LiteLLM (Anthropic / OpenAI style).
"""
import base64
import logging
import os
from typing import Any, Dict, Optional

import httpx
import litellm
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

DEFAULT_ORDER = (
    'anthropic/claude-3-5-sonnet-20241022',
    'openai/gpt-4o',
)


def _load_image_bytes(image_path: str) -> bytes:
    if image_path.startswith(('http://', 'https://')):
        response = httpx.get(image_path, timeout=60.0)
        response.raise_for_status()
        return response.content
    with open(image_path, 'rb') as handle:
        return handle.read()


def _vision_sync(
    image_path: str,
    question: str,
    provider: Optional[str],
) -> Dict[str, Any]:
    try:
        data = _load_image_bytes(image_path)
    except OSError as exc:
        return {'error': str(exc), 'analysis': '', 'provider': ''}
    except httpx.HTTPError as exc:
        return {'error': str(exc), 'analysis': '', 'provider': ''}

    b64 = base64.b64encode(data).decode('ascii')
    models = [provider] if provider else list(DEFAULT_ORDER)

    last_err = ''
    for model in models:
        if not model:
            continue
        try:
            response = litellm.completion(
                model=model,
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'image_url',
                                'image_url': {
                                    'url': 'data:image/png;base64,%s' % b64,
                                },
                            },
                            {'type': 'text', 'text': question},
                        ],
                    }
                ],
                timeout=60,
            )
            text = response['choices'][0]['message']['content']
            return {'analysis': text, 'provider': model}
        except Exception as exc:
            last_err = str(exc)
            logger.warning('[mcp_vision] Provider %s failed: %s', model, exc)

    return {
        'error': 'All vision providers failed. Last: %s' % last_err,
        'analysis': '',
        'provider': '',
    }


async def mcp_vision(
    image_path: str,
    question: str,
    provider: Optional[str] = None,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Analyze an image with a vision-capable model."""
    return await sync_to_async(_vision_sync)(image_path, question, provider)
