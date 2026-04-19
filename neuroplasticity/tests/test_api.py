"""API smoke tests for the Modifier Garden endpoints.

These are narrow — lifecycle is covered by test_modifier_lifecycle; here
we just confirm the REST surface routes through to it.
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from neuroplasticity import loader
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
    build_fake_bundle,
)


class ModifierApiSmokeTest(ModifierLifecycleTestCase, APITestCase):
    def test_list_includes_installed_bundle(self):
        """Assert list endpoint returns the installed bundle."""
        build_fake_bundle(self.genome_root, 'ui_alpha')
        loader.install_bundle('ui_alpha')

        res = self.client.get('/api/v2/neural-modifiers/')

        self.assertEqual(res.status_code, 200)
        slugs = [row['slug'] for row in res.json()]
        self.assertIn('ui_alpha', slugs)

    def test_retrieve_includes_installation_logs(self):
        """Assert detail endpoint returns the installation logs array."""
        build_fake_bundle(self.genome_root, 'ui_retrieve')
        loader.install_bundle('ui_retrieve')

        res = self.client.get('/api/v2/neural-modifiers/ui_retrieve/')

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload['slug'], 'ui_retrieve')
        self.assertIn('installation_logs', payload)
        self.assertGreaterEqual(len(payload['installation_logs']), 1)

    def test_impact_endpoint(self):
        """Assert impact endpoint returns contribution breakdown."""
        build_fake_bundle(self.genome_root, 'ui_beta')
        loader.install_bundle('ui_beta')

        res = self.client.get('/api/v2/neural-modifiers/ui_beta/impact/')

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload['slug'], 'ui_beta')
        self.assertEqual(payload['contribution_count'], 3)
        self.assertTrue(
            any(
                row['content_type'] == 'hypothalamus.aimodeltags'
                for row in payload['breakdown']
            )
        )

    def test_enable_disable_actions(self):
        """Assert enable/disable endpoints flip status."""
        build_fake_bundle(self.genome_root, 'ui_gamma')
        loader.install_bundle('ui_gamma')

        res = self.client.post('/api/v2/neural-modifiers/ui_gamma/enable/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status_name'], 'Enabled')

        res = self.client.post('/api/v2/neural-modifiers/ui_gamma/disable/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status_name'], 'Disabled')

    def test_uninstall_action(self):
        """Assert uninstall flips status back to Discovered."""
        build_fake_bundle(self.genome_root, 'ui_delta')
        loader.install_bundle('ui_delta')

        res = self.client.post('/api/v2/neural-modifiers/ui_delta/uninstall/')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status_name'], 'Discovered')

    def test_install_endpoint_rejects_missing_payload(self):
        """Assert install endpoint 400s when neither archive nor slug given."""
        res = self.client.post('/api/v2/neural-modifiers/install/')

        self.assertEqual(res.status_code, 400)
        self.assertIn('archive', res.json()['detail'].lower())
