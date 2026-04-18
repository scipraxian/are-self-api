from asgiref.sync import async_to_sync

from common.tests.common_test_case import CommonTestCase
from parietal_lobe.parietal_mcp import gateway as gateway_module
from parietal_lobe.parietal_mcp.gateway import (
    ParietalMCP,
    register_parietal_tool,
    unregister_parietal_tool,
)


async def _stub_echo(greeting: str = '') -> str:
    """Bundle-style stub that echoes its single keyword arg."""
    return f'stub-echo:{greeting}'


async def _stub_collision() -> str:
    """Bundle-style stub that collides with a real core module name."""
    return 'stub-from-registry'


class ParietalToolRegistrationTest(CommonTestCase):
    """Assert register_parietal_tool and unregister_parietal_tool extend the gateway."""

    def setUp(self):
        super().setUp()
        self._registry_snapshot = dict(
            gateway_module._PARIETAL_TOOL_REGISTRY
        )

    def tearDown(self):
        gateway_module._PARIETAL_TOOL_REGISTRY.clear()
        gateway_module._PARIETAL_TOOL_REGISTRY.update(
            self._registry_snapshot
        )
        super().tearDown()

    def test_register_and_dispatch_bundle_tool(self):
        """Assert a bundle-registered tool is dispatched by ParietalMCP.execute()."""
        register_parietal_tool('mcp_bundle_echo', _stub_echo)

        result = async_to_sync(ParietalMCP.execute)(
            'mcp_bundle_echo', {'greeting': 'hi'}
        )

        self.assertEqual(result, 'stub-echo:hi')

    def test_registry_takes_precedence_over_dynamic_import(self):
        """Assert registry lookup wins over the dynamic-import fallback."""
        register_parietal_tool('mcp_grep', _stub_collision)

        result = async_to_sync(ParietalMCP.execute)('mcp_grep', {})

        self.assertEqual(result, 'stub-from-registry')

    def test_unregistered_tool_falls_through_to_dynamic_import(self):
        """Assert an empty registry falls through to the core dynamic import."""
        result = async_to_sync(ParietalMCP.execute)('mcp_pass', {})

        self.assertIn('Turn passed', result)

    def test_register_rejects_missing_mcp_prefix(self):
        """Assert register_parietal_tool rejects names missing the 'mcp_' prefix."""
        with self.assertRaises(ValueError):
            register_parietal_tool('bundle_echo', _stub_echo)

    def test_register_rejects_duplicate_registration(self):
        """Assert re-registering the same tool name raises RuntimeError."""
        register_parietal_tool('mcp_bundle_once', _stub_echo)

        with self.assertRaises(RuntimeError):
            register_parietal_tool('mcp_bundle_once', _stub_echo)

    def test_unregister_is_idempotent(self):
        """Assert unregister_parietal_tool is a no-op on absent names."""
        unregister_parietal_tool('mcp_not_there')

    def test_unregister_removes_registered_entry(self):
        """Assert unregistering restores the dynamic-import fallback path."""
        register_parietal_tool('mcp_bundle_ghost', _stub_echo)
        unregister_parietal_tool('mcp_bundle_ghost')

        result = async_to_sync(ParietalMCP.execute)(
            'mcp_bundle_ghost', {}
        )

        self.assertIn('does not exist', result)
