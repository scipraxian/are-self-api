"""``restart_imminent: true`` is consistent across restart-triggering responses.

Frontend uses this flag as the explicit signal to flip on the
disconnect overlay rather than inferring from "I just called install".
Three endpoints carry it: install (`/install/`), uninstall
(`/<slug>/uninstall/`), and catalog_install
(`/catalog/<slug>/install/`). The fourth — move-to-genome —
includes it directly in its own dedicated tests.

All tests mock ``trigger_system_restart`` per CLAUDE.md so the suite
doesn't spawn a real Celery worker or reload the dev Daphne.
"""

from __future__ import annotations

from unittest.mock import patch

from rest_framework.test import APITestCase

from neuroplasticity import loader
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
    build_fake_bundle,
    build_fake_bundle_archive,
)


class RestartImminentFlagTest(ModifierLifecycleTestCase, APITestCase):
    @patch('neuroplasticity.api.trigger_system_restart')
    def test_install_response_has_restart_imminent(self, _restart):
        """Assert /install/ response carries restart_imminent=True."""
        build_fake_bundle_archive(self.genomes_root, 'restart_install')

        res = self.client.post(
            '/api/v2/neural-modifiers/install/', {'slug': 'restart_install'}
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIs(res.json().get('restart_imminent'), True)

    @patch('neuroplasticity.api.trigger_system_restart')
    def test_uninstall_response_has_restart_imminent(self, _restart):
        """Assert /uninstall/ response carries restart_imminent=True."""
        build_fake_bundle(self.scratch_root, 'restart_uninstall')
        self.install_fake('restart_uninstall')

        res = self.client.post(
            '/api/v2/neural-modifiers/restart_uninstall/uninstall/'
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIs(res.json().get('restart_imminent'), True)

    @patch('neuroplasticity.api.trigger_system_restart')
    def test_catalog_install_response_has_restart_imminent(self, _restart):
        """Assert /catalog/<slug>/install/ response carries restart_imminent=True."""
        build_fake_bundle_archive(self.genomes_root, 'restart_catalog')

        res = self.client.post(
            '/api/v2/neural-modifiers/catalog/restart_catalog/install/'
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIs(res.json().get('restart_imminent'), True)
