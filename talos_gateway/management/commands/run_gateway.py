"""Run the gateway orchestrator (Layer 4 §6.2)."""

import asyncio
import logging

from django.core.management.base import BaseCommand

from talos_gateway.gateway import GatewayOrchestrator

logger = logging.getLogger('talos_gateway.management.run_gateway')


class Command(BaseCommand):
    """``python manage.py run_gateway`` — load adapters and start async loop."""

    help = 'Start Talos gateway adapters (blocks until interrupted).'

    def handle(self, *args, **options):
        orchestrator = GatewayOrchestrator()
        orchestrator.load_adapters()

        async def _run() -> None:
            await orchestrator.start_all()
            try:
                await asyncio.Event().wait()
            finally:
                await orchestrator.stop_all()

        asyncio.run(_run())
