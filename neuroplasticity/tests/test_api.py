"""API smoke tests for the Modifier Garden endpoints.

Narrow checks that the REST surface routes through to the loader.
Lifecycle is covered by ``test_modifier_lifecycle``. Save, graph, and
uninstall-preview live here.
"""

from __future__ import annotations

from pathlib import Path

from rest_framework.test import APITestCase

from identity.models import IdentityAddon
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
        build_fake_bundle(self.scratch_root, 'ui_alpha')
        self.install_fake('ui_alpha')

        res = self.client.get('/api/v2/neural-modifiers/')

        self.assertEqual(res.status_code, 200)
        slugs = [row['slug'] for row in res.json()]
        self.assertIn('ui_alpha', slugs)

    def test_retrieve_includes_installation_logs(self):
        """Assert detail endpoint returns the installation logs array."""
        build_fake_bundle(self.scratch_root, 'ui_retrieve')
        self.install_fake('ui_retrieve')

        res = self.client.get('/api/v2/neural-modifiers/ui_retrieve/')

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload['slug'], 'ui_retrieve')
        self.assertIn('installation_logs', payload)
        self.assertGreaterEqual(len(payload['installation_logs']), 1)

    def test_impact_endpoint(self):
        """Assert impact endpoint returns the Collector preview tree."""
        build_fake_bundle(self.scratch_root, 'ui_beta')
        self.install_fake('ui_beta')

        res = self.client.get('/api/v2/neural-modifiers/ui_beta/impact/')

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload['slug'], 'ui_beta')
        self.assertEqual(payload['row_count'], 3)
        self.assertEqual(len(payload['direct']), 3)
        self.assertEqual(
            {row['model'] for row in payload['direct']},
            {'identity.identityaddon'},
        )
        self.assertEqual(payload['protected'], [])

    def test_uninstall_preview_endpoint(self):
        """Assert /uninstall-preview/ returns the Collector tree payload."""
        build_fake_bundle(self.scratch_root, 'ui_preview')
        self.install_fake('ui_preview')

        res = self.client.get(
            '/api/v2/neural-modifiers/ui_preview/uninstall-preview/'
        )

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload['slug'], 'ui_preview')
        self.assertEqual(len(payload['direct']), 3)
        self.assertIn('cascade', payload)
        self.assertIn('set_null', payload)
        self.assertIn('protected', payload)
        for entry in payload['direct']:
            self.assertEqual(entry['reason'], 'direct')
            self.assertIn('app_label', entry)
            self.assertIn('model', entry)
            self.assertIn('pk', entry)
            self.assertIn('name_or_repr', entry)

    def test_enable_disable_actions(self):
        """Assert enable/disable endpoints flip status."""
        build_fake_bundle(self.scratch_root, 'ui_gamma')
        self.install_fake('ui_gamma')

        res = self.client.post('/api/v2/neural-modifiers/ui_gamma/enable/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status_name'], 'Enabled')

        res = self.client.post('/api/v2/neural-modifiers/ui_gamma/disable/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status_name'], 'Disabled')

    def test_uninstall_action(self):
        """Assert uninstall deletes the row and returns a minimal payload."""
        build_fake_bundle(self.scratch_root, 'ui_delta')
        self.install_fake('ui_delta')

        res = self.client.post('/api/v2/neural-modifiers/ui_delta/uninstall/')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json(), {'slug': 'ui_delta', 'uninstalled': True}
        )
        self.assertFalse(
            NeuralModifier.objects.filter(slug='ui_delta').exists()
        )

    def test_install_endpoint_rejects_missing_payload(self):
        """Assert install endpoint 400s when neither archive nor slug given."""
        res = self.client.post('/api/v2/neural-modifiers/install/')

        self.assertEqual(res.status_code, 400)
        self.assertIn('archive', res.json()['detail'].lower())

    def test_save_endpoint_writes_zip_and_reports_stats(self):
        """Assert save endpoint rebuilds ``<slug>.zip`` and returns stats."""
        build_fake_bundle(self.scratch_root, 'ui_saver')
        self.install_fake('ui_saver')

        res = self.client.post('/api/v2/neural-modifiers/ui_saver/save/')

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload['slug'], 'ui_saver')
        self.assertEqual(payload['row_count'], 3)
        self.assertTrue(Path(payload['zip_path']).exists())
        self.assertGreater(payload['bytes_written'], 0)

    def test_graph_endpoint_returns_owned_nodes(self):
        """Assert graph endpoint emits a node per owned row."""
        build_fake_bundle(self.scratch_root, 'ui_graph')
        modifier = self.install_fake('ui_graph')

        res = self.client.get('/api/v2/neural-modifiers/ui_graph/graph/')

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload['slug'], 'ui_graph')
        owned = [n for n in payload['nodes'] if n['state'] == 'owned']
        self.assertEqual(len(owned), 3)
        for node in owned:
            self.assertEqual(node['model'], 'identityaddon')
            self.assertEqual(node['owner_slug'], 'ui_graph')
            # PKs line up with the DB state.
            self.assertTrue(
                IdentityAddon.objects.filter(
                    pk=node['pk'], genome=modifier
                ).exists()
            )

    def test_graph_endpoint_404_for_unknown_slug(self):
        """Assert graph endpoint 404s when no bundle with that slug exists."""
        res = self.client.get('/api/v2/neural-modifiers/ghost/graph/')

        self.assertEqual(res.status_code, 404)


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
        build_fake_bundle_archive(self.genomes_root, 'cat_installed')
        build_fake_bundle_archive(self.genomes_root, 'cat_available')
        loader.install_bundle_from_archive(
            self.genomes_root / 'cat_installed.zip'
        )

        res = self.client.get('/api/v2/neural-modifiers/catalog/')

        self.assertEqual(res.status_code, 200)
        rows = {row['slug']: row for row in res.json()}
        self.assertIn('cat_installed', rows)
        self.assertIn('cat_available', rows)
        self.assertTrue(rows['cat_installed']['installed'])
        self.assertFalse(rows['cat_available']['installed'])
        self.assertEqual(rows['cat_available']['name'], 'Fake cat_available')
        self.assertEqual(rows['cat_available']['archive_name'], 'cat_available.zip')


class CatalogInstallCreatesRowTest(ModifierLifecycleTestCase, APITestCase):
    def test_catalog_install_creates_row_and_clears_operating_room(self):
        """Assert install creates a DB row and the operating_room is empty."""
        build_fake_bundle_archive(self.genomes_root, 'cat_install')

        res = self.client.post(
            '/api/v2/neural-modifiers/catalog/cat_install/install/'
        )

        self.assertEqual(res.status_code, 200)
        modifier = NeuralModifier.objects.get(slug='cat_install')
        self.assertEqual(
            IdentityAddon.objects.filter(genome=modifier).count(), 3
        )
        self.assertEqual(list(self.operating_room_root.iterdir()), [])
        self.assertTrue((self.genomes_root / 'cat_install.zip').exists())


class CatalogInstallConflictsWhenAlreadyInstalledTest(
    ModifierLifecycleTestCase, APITestCase
):
    def test_catalog_install_conflicts_when_already_installed(self):
        """Assert second install attempt against an installed slug is rejected."""
        build_fake_bundle_archive(self.genomes_root, 'cat_dupe')
        loader.install_bundle_from_archive(self.genomes_root / 'cat_dupe.zip')

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
        """Assert delete unlinks the genome zip when no DB row exists."""
        archive = build_fake_bundle_archive(self.genomes_root, 'cat_to_delete')
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
        archive = build_fake_bundle_archive(self.genomes_root, 'cat_locked')
        loader.install_bundle_from_archive(archive)

        res = self.client.post(
            '/api/v2/neural-modifiers/catalog/cat_locked/delete/'
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn('uninstall first', res.json()['detail'].lower())
        self.assertTrue(archive.exists())
