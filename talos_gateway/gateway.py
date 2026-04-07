"""Gateway orchestrator: adapter lifecycle and inbound dispatch."""

import importlib
import logging
from typing import Any, Optional, Type

from django.conf import settings

from talos_gateway.contracts import PlatformEnvelope
from talos_gateway.message_router import MessageRouter
from talos_gateway.session_manager import SessionManager

logger = logging.getLogger('talos_gateway.gateway')

_active_gateway_orchestrator: Optional[Any] = None


def set_active_gateway_orchestrator(orchestrator: Optional[Any]) -> None:
    """Register global gateway orchestrator for ASGI consumers (e.g. CLI WS)."""
    global _active_gateway_orchestrator
    _active_gateway_orchestrator = orchestrator


def get_active_gateway_orchestrator() -> Optional[Any]:
    """Return the orchestrator set by ``run_gateway`` or tests, if any."""
    return _active_gateway_orchestrator


def clear_active_gateway_orchestrator() -> None:
    """Clear the active orchestrator (shutdown)."""
    set_active_gateway_orchestrator(None)


def discover_adapter_class(platform_key: str) -> Type[Any]:
    """Import ``<platform_key>_adapter`` and return the ``*Adapter`` class."""
    module_name = 'talos_gateway.adapters.%s_adapter' % platform_key
    # Dynamic import of adapter modules
    module = importlib.import_module(module_name)
    for attr_name in dir(module):
        if not attr_name.endswith('Adapter'):
            continue
        obj = getattr(module, attr_name)
        if isinstance(obj, type) and getattr(obj, 'PLATFORM_NAME', None):
            return obj
    raise ImportError('No Adapter class found in %s' % module_name)


class GatewayOrchestrator(object):
    """Load platform adapters, run lifecycle, route inbound envelopes."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self.config = config or getattr(settings, 'TALOS_GATEWAY', {})
        self.adapters: dict[str, Any] = {}
        self.session_manager = SessionManager(self.config)
        self.message_router = MessageRouter(self.session_manager)

    def load_adapters(self) -> None:
        """Instantiate enabled adapters from ``TALOS_GATEWAY['platforms']``."""
        platforms = self.config.get('platforms', {})
        for name, platform_cfg in platforms.items():
            if not platform_cfg.get('enabled', True):
                continue
            try:
                cls = discover_adapter_class(name)
                self.adapters[name] = cls(platform_cfg)
                logger.info('[GatewayOrchestrator] Loaded adapter %s.', name)
            except Exception:
                logger.exception(
                    '[GatewayOrchestrator] Failed to load adapter %s.', name
                )

    async def start_all(self) -> None:
        """Call ``start()`` on each adapter; drop adapters that raise."""
        for name in list(self.adapters.keys()):
            adapter = self.adapters[name]
            try:
                await adapter.start()
            except Exception:
                logger.exception(
                    '[GatewayOrchestrator] adapter.start failed for %s; skip.',
                    name,
                )
                del self.adapters[name]

    async def stop_all(self) -> None:
        """Call ``stop()`` on each remaining adapter."""
        for name, adapter in self.adapters.items():
            try:
                await adapter.stop()
            except Exception:
                logger.exception(
                    '[GatewayOrchestrator] adapter.stop failed for %s.', name
                )

    async def handle_inbound(
        self,
        envelope: PlatformEnvelope,
    ) -> dict[str, Any]:
        """Resolve session and queue inbound user content."""
        gs, rs = self.session_manager.resolve_session(
            envelope.platform,
            envelope.channel_id,
            envelope,
        )
        return await self.message_router.dispatch_inbound(gs, rs, envelope)
