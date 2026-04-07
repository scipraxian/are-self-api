"""Run the gateway orchestrator (Layer 4 §6.2)."""

import asyncio
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from uvicorn import Config, Server

from talos_gateway.gateway import (
    GatewayOrchestrator,
    clear_active_gateway_orchestrator,
    set_active_gateway_orchestrator,
)

logger = logging.getLogger('talos_gateway.management.run_gateway')


async def run_gateway_main_async() -> None:
    """Load adapters, serve ASGI (WebSocket CLI), block until shutdown."""
    gateway_settings = getattr(settings, 'TALOS_GATEWAY', {})
    host = gateway_settings.get('asgi_host', '127.0.0.1')
    port = int(gateway_settings.get('asgi_port', 8001))

    orchestrator = GatewayOrchestrator()
    orchestrator.load_adapters()
    await orchestrator.start_all()
    set_active_gateway_orchestrator(orchestrator)

    uv_config = Config(
        'config.asgi:application',
        host=host,
        port=port,
        loop='asyncio',
    )
    server = Server(uv_config)
    logger.info(
        '[run_gateway] ASGI listening on http://%s:%s (WebSocket CLI at '
        '/ws/gateway/stream/).',
        host,
        port,
    )
    try:
        await server.serve()
    finally:
        try:
            await orchestrator.stop_all()
        except Exception:
            logger.exception('[run_gateway] stop_all failed during shutdown.')
        clear_active_gateway_orchestrator()


class Command(BaseCommand):
    """``python manage.py run_gateway`` — adapters + embedded uvicorn ASGI."""

    help = (
        'Start Are-Self gateway adapters and an ASGI server for the CLI '
        'WebSocket (blocks until interrupted).'
    )

    def handle(self, *args, **options):
        asyncio.run(run_gateway_main_async())
