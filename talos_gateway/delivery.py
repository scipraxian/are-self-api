"""Outbound delivery: adapter resolution, chunking, retries."""

import asyncio
import logging
from typing import Any, Callable

from talos_gateway.adapters.base_patterns import iter_chunked_payloads
from talos_gateway.contracts import DeliveryPayload

logger = logging.getLogger('talos_gateway.delivery')

PERMANENT_FAILURE_CODES = frozenset({403, 404})
MAX_SEND_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)


async def send_with_retries(
    adapter: Any,
    payload: DeliveryPayload,
    sleep_fn: Callable[[float], Any],
) -> dict:
    """Call ``adapter.send`` with retries per Layer 4 §7.2.

    Up to three attempts. Backoff 1s then 3s after failures. No retry on
    403/404. On 429, wait ``retry_after_seconds`` from the result if set.

    Args:
        adapter: Platform adapter with ``async def send(DeliveryPayload)``.
        payload: Outbound payload.
        sleep_fn: Async sleep (injected for tests).

    Returns:
        Last adapter result dict (typically includes ``success`` and
        ``status_code``).
    """
    result: dict = {'success': False}
    for attempt in range(MAX_SEND_ATTEMPTS):
        if attempt > 0:
            await sleep_fn(BACKOFF_SECONDS[attempt - 1])
        result = await adapter.send(payload)
        if result.get('success'):
            return result
        code = result.get('status_code')
        if code in PERMANENT_FAILURE_CODES:
            return result
        if code == 429:
            retry_after = result.get('retry_after_seconds')
            if retry_after is not None:
                await sleep_fn(float(retry_after))
    return result


class DeliveryService(object):
    """Resolves adapters and sends ``DeliveryPayload`` with chunking/retries."""

    def __init__(self, adapters: dict[str, Any]) -> None:
        self.adapters = adapters

    async def send(self, payload: DeliveryPayload) -> dict:
        """Deliver payload to the configured platform adapter."""
        adapter = self.adapters.get(payload.platform)
        if adapter is None:
            logger.warning(
                '[DeliveryService] Unknown platform %s.', payload.platform
            )
            return {
                'success': False,
                'error': 'unknown_platform',
                'status_code': None,
            }
        max_len: int = int(getattr(adapter, 'MAX_MESSAGE_LENGTH', 2000))
        if len(payload.content) > max_len:
            return await self._send_chunked(adapter, payload, max_len)
        return await send_with_retries(adapter, payload, self._sleep)

    async def _send_chunked(
        self, adapter: Any, payload: DeliveryPayload, max_len: int
    ) -> dict:
        """Send long content as multiple payloads."""
        last: dict = {'success': False}
        for chunk_payload in iter_chunked_payloads(payload, max_len):
            last = await send_with_retries(adapter, chunk_payload, self._sleep)
            if not last.get('success'):
                return last
        return last

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
