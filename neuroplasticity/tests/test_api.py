"""API smoke tests for the Modifier Garden endpoints.

These are narrow — lifecycle is covered by test_modifier_lifecycle; here
we just confirm the REST surface routes through to it.
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
    build_fake_bundle,
    build_fake_bundle_archive,
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


class CatalogListReturnsEmptyWhenNoZipsTest(
    ModifierLifecycleTestCase, APITestCase
):
    def test_catalog_list_empty(self):
        """Assert catalog endpoint returns [] when no zips on disk."""
        res = self.client.get('/api/v2/neural-modifiers/catalog/')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])


class CatalogListReturnsInstalledFlagTest(
    ModifierLifecycleTestCase, APITestCase
):
    def test_catalog_list_marks_installed(self):
        """Assert catalog rows tag installed=true iff a DB row exists."""
        # Two zips in catalog: one we install, one we leave AVAILABLE.
        build_fake_bundle_archive(self.catalog_root, 'cat_installed')
        build_fake_bundle_archive(self.catalog_root, 'cat_available')
        # Install one of them by going through the catalog flow.
        loader.install_bundle_from_archive(
            self.catalog_root / 'cat_installed.zip'
        )

        res = self.client.get('/api/v2/neural-modifiers/catalog/')

        self.assertEqual(res.status_code, 200)
        rows = {row['slug']: row for row in res.json()}
        self.assertIn('cat_installed', rows)
        self.assertIn('cat_available', rows)
        self.assertTrue(rows['cat_installed']['installed'])
        self.assertFalse(rows['cat_available']['installed'])
        # Manifest fields surface through.
        self.assertEqual(rows['cat_available']['name'], 'Fake cat_available')
        self.assertEqual(rows['cat_available']['archive_name'], 'cat_available.zip')


class CatalogInstallCreatesRowTest(ModifierLifecycleTestCase, APITestCase):
    def test_catalog_install_creates_row_and_clears_staging(self):
        """Assert install creates a DB row and the staging tempdir is gone."""
        build_fake_bundle_archive(self.catalog_root, 'cat_install')

        res = self.client.post(
            '/api/v2/neural-modifiers/catalog/cat_install/install/'
        )

        self.assertEqual(res.status_code, 200)
        modifier = NeuralModifier.objects.get(slug='cat_install')
        self.assertEqual(modifier.contributions.count(), 3)
        # Staging tempdir cleaned up.
        staging = self.runtime_root / '_staging' / 'cat_install'
        self.assertFalse(staging.exists())
        # Catalog zip stays put.
        self.assertTrue((self.catalog_root / 'cat_install.zip').exists())


class CatalogInstallConflictsWhenAlreadyInstalledTest(
    ModifierLifecycleTestCase, APITestCase
):
    def test_catalog_install_conflicts_when_already_installed(self):
        """Assert second install attempt against an installed slug is rejected."""
        build_fake_bundle_archive(self.catalog_root, 'cat_dupe')
        loader.install_bundle_from_archive(self.catalog_root / 'cat_dupe.zip')

        res = self.client.post(
            '/api/v2/neural-modifiers/catalog/cat_dupe/install/'
        )

        self.assertEqual(res.status_code, 409)
        self.assertIn('already installed', res.json()['detail'].lower())


class CatalogInstallReturns404WhenZipMissingTest(
    ModifierLifecycleTestCase, APITestCase
):
    def test_catalog_install_404_when_zip_missing(self):
        """Assert install 404s when no zip with that slug exists."""
        res = self.client.post(
            '/api/v2/neural-modifiers/catalog/ghost/install/'
        )

        self.assertEqual(res.status_code, 404)


class CatalogDeleteRemovesZipTest(ModifierLifecycleTestCase, APITestCase):
    def test_catalog_delete_removes_zip(self):
        """Assert delete unlinks the catalog zip when no DB row exists."""
        archive = build_fake_bundle_archive(self.catalog_root, 'cat_to_delete')
        self.assertTrue(archive.exists())

        res = self.client.post(
            '/api/v2/neural-modifiers/catalog/cat_to_delete/delete/'
        )

        self.assertEqual(res.status_code, 200)
        self.assertFalse(archive.exists())


class CatalogDeleteRefusesWhenInstalledTest(
    ModifierLifecycleTestCase, APITestCase
):
    def test_catalog_delete_refuses_when_installed(self):
        """Assert delete 400s with a clear message when a DB row exists."""
        archive = build_fake_bundle_archive(self.catalog_root, 'cat_locked')
        loader.install_bundle_from_archive(archive)

        res = self.client.post(
            '/api/v2/neural-modifiers/catalog/cat_locked/delete/'
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn('uninstall first', res.json()['detail'].lower())
        self.assertTrue(archive.exists())
