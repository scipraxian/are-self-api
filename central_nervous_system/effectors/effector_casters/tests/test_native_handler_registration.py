from central_nervous_system.effectors.effector_casters.neuromuscular_junction import (
    NATIVE_HANDLERS,
    register_native_handler,
    unregister_native_handler,
)
from common.tests.common_test_case import CommonTestCase


def _bundle_handler(spike_id):
    """Bundle-style native handler stub used by registration tests."""
    return (200, 'stub')


class NativeHandlerRegistrationTest(CommonTestCase):
    """Assert register_native_handler and unregister_native_handler extend NATIVE_HANDLERS."""

    def setUp(self):
        super().setUp()
        self._handlers_snapshot = dict(NATIVE_HANDLERS)

    def tearDown(self):
        NATIVE_HANDLERS.clear()
        NATIVE_HANDLERS.update(self._handlers_snapshot)
        super().tearDown()

    def test_register_and_lookup(self):
        """Assert a registered slug is retrievable via NATIVE_HANDLERS.get()."""
        register_native_handler('bundle_test_handler', _bundle_handler)

        self.assertIs(
            NATIVE_HANDLERS.get('bundle_test_handler'), _bundle_handler
        )

    def test_register_rejects_duplicate(self):
        """Assert re-registering an existing slug raises RuntimeError."""
        register_native_handler('bundle_once', _bundle_handler)

        with self.assertRaises(RuntimeError):
            register_native_handler('bundle_once', _bundle_handler)

    def test_register_rejects_core_slug_collision(self):
        """Assert a bundle cannot shadow a core-declared slug like begin_play."""
        with self.assertRaises(RuntimeError):
            register_native_handler('begin_play', _bundle_handler)

    def test_unregister_removes_handler(self):
        """Assert unregister_native_handler removes the registered slug."""
        register_native_handler('bundle_ghost', _bundle_handler)
        unregister_native_handler('bundle_ghost')

        self.assertIsNone(NATIVE_HANDLERS.get('bundle_ghost'))

    def test_unregister_is_idempotent(self):
        """Assert unregister_native_handler is a no-op on absent slugs."""
        unregister_native_handler('not_present_slug')
