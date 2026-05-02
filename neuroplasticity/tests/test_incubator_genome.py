"""Tests for INCUBATOR-as-real-grafted-genome architecture.

Covers:

* Clean-boot integration — graft tree exists, manifest hash matches,
  INCUBATOR row is INSTALLED after :func:`graft_incubator`.
* Idempotency — second call is a no-op when the on-disk manifest hash
  already matches.
* Media preservation — re-grafting after manifest drift does NOT clobber
  user-uploaded ``media/`` content.
* Three-mode uninstall — INCUBATOR cascade-clears + re-grafts, CANONICAL
  refused, anything else handled by the existing rename-pass tests.
* Selection mutex sanity — duplicate-fixture-load scenarios for both
  ``ProjectEnvironment.selected`` and ``NeuralModifier.selected_for_edit``.
* Save-As round-trip — owned rows are deep-cloned with fresh PKs, media
  bytes copy across, the source genome is untouched, the new zip is
  baked.

Each test owns its synthetic ``incubator.zip`` built on the fly inside
the tmp tree so the production artifact is never touched.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings

from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
)
from identity.models import (
    Avatar,
    AvatarSelectedDisplayType,
    IdentityAddon,
)
from neuroplasticity import loader
from neuroplasticity.models import (
    NeuralModifier,
    NeuralModifierStatus,
)


INCUBATOR_GENOME_UUID = '1206f5a1-7ffd-4cb2-8c5a-3a9dfb5e5340'

# Source for the synthetic incubator's entry module __init__.py — must
# be a plain no-op so re-import on every test is harmless.
_INCUBATOR_INIT_PY = '''\
"""Synthetic test stand-in for the incubator entry module."""
'''

_INCUBATOR_URLS_PY = '''\
"""Synthetic urls.py exposing a hello-world example viewset."""

from rest_framework import routers, viewsets
from rest_framework.response import Response


class IncubatorHelloViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({'genome': 'incubator', 'message': 'hello'})


V2_GENOME_ROUTER = routers.SimpleRouter()
V2_GENOME_ROUTER.register(
    r'incubator-hello',
    IncubatorHelloViewSet,
    basename='incubator-hello',
)
'''


def _build_synthetic_incubator_archive(
    archive_path: Path,
    *,
    description: str = 'synthetic incubator',
    extra_media_files: dict | None = None,
) -> Path:
    """Build a synthetic incubator.zip into ``archive_path``."""
    manifest = {
        'slug': NeuralModifier.INCUBATOR_SLUG,
        'name': 'Incubator (synthetic)',
        'version': '0.0.0',
        'genome': INCUBATOR_GENOME_UUID,
        'author': 'tests',
        'license': 'MIT',
        'description': description,
        'entry_modules': ['incubator_genome'],
    }
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f'{NeuralModifier.INCUBATOR_SLUG}/manifest.json',
            json.dumps(manifest, indent=2) + '\n',
        )
        zf.writestr(
            f'{NeuralModifier.INCUBATOR_SLUG}/modifier_data.json', '[]\n'
        )
        zf.writestr(
            f'{NeuralModifier.INCUBATOR_SLUG}/code/incubator_genome/__init__.py',
            _INCUBATOR_INIT_PY,
        )
        zf.writestr(
            f'{NeuralModifier.INCUBATOR_SLUG}/code/incubator_genome/urls.py',
            _INCUBATOR_URLS_PY,
        )
        zf.writestr(
            f'{NeuralModifier.INCUBATOR_SLUG}/media/.gitkeep',
            '# placeholder\n',
        )
        for rel, content in (extra_media_files or {}).items():
            zf.writestr(
                f'{NeuralModifier.INCUBATOR_SLUG}/media/{rel}', content,
            )
    return archive_path


class IncubatorTestCase(TestCase):
    """Common harness — tmp roots + synthetic incubator.zip."""

    fixtures = ['neuroplasticity/fixtures/genetic_immutables.json']

    def setUp(self):
        super().setUp()
        self._tmp_root = Path(tempfile.mkdtemp(prefix='incubator-test-'))
        self.genomes_root = self._tmp_root / 'genomes'
        self.grafts_root = self._tmp_root / 'grafts'
        self.operating_room_root = self._tmp_root / 'operating_room'
        self.genomes_root.mkdir()
        self.grafts_root.mkdir()
        self.operating_room_root.mkdir()
        self.archive_path = self.genomes_root / 'incubator.zip'
        _build_synthetic_incubator_archive(self.archive_path)
        self._sys_path_snapshot = list(sys.path)
        self._sys_modules_snapshot = set(sys.modules.keys())
        self._settings_override = override_settings(
            NEURAL_MODIFIER_GENOMES_ROOT=str(self.genomes_root),
            NEURAL_MODIFIER_GRAFTS_ROOT=str(self.grafts_root),
            NEURAL_MODIFIER_OPERATING_ROOM_ROOT=str(self.operating_room_root),
        )
        self._settings_override.enable()

    def tearDown(self):
        self._settings_override.disable()
        sys.path[:] = self._sys_path_snapshot
        for name in list(sys.modules.keys()):
            if name not in self._sys_modules_snapshot:
                sys.modules.pop(name, None)
        shutil.rmtree(self._tmp_root, ignore_errors=True)
        super().tearDown()


class IncubatorBootstrapTest(IncubatorTestCase):
    """Assert ``graft_incubator`` brings the incubator graft online cleanly."""

    def test_graft_incubator_extracts_archive_into_grafts(self):
        """Assert graft tree + manifest land on disk after first call."""
        self.assertFalse((self.grafts_root / 'incubator').exists())

        loader.graft_incubator()

        runtime = self.grafts_root / 'incubator'
        self.assertTrue(runtime.is_dir())
        self.assertTrue((runtime / 'manifest.json').is_file())
        self.assertTrue(
            (runtime / 'code' / 'incubator_genome' / '__init__.py').is_file(),
        )
        self.assertTrue(
            (runtime / 'code' / 'incubator_genome' / 'urls.py').is_file(),
        )
        self.assertTrue((runtime / 'media').is_dir())

    def test_graft_incubator_updates_db_row(self):
        """Assert the INCUBATOR row picks up manifest_hash + INSTALLED."""
        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)
        self.assertEqual(incubator.manifest_hash, '')

        loader.graft_incubator()

        incubator.refresh_from_db()
        self.assertNotEqual(incubator.manifest_hash, '')
        self.assertEqual(incubator.status_id, NeuralModifierStatus.INSTALLED)
        self.assertEqual(
            incubator.manifest_json.get('slug'),
            NeuralModifier.INCUBATOR_SLUG,
        )

    def test_graft_incubator_idempotent(self):
        """Assert a second call with no drift is a no-op (no rewrite)."""
        loader.graft_incubator()
        runtime_manifest = self.grafts_root / 'incubator' / 'manifest.json'
        first_mtime = runtime_manifest.stat().st_mtime_ns

        loader.graft_incubator()

        # Without drift, the manifest is not re-extracted, so mtime is
        # unchanged.
        self.assertEqual(
            runtime_manifest.stat().st_mtime_ns, first_mtime,
        )

    def test_graft_incubator_preserves_user_media_on_re_extract(self):
        """Assert a manifest drift re-extract keeps user uploads."""
        loader.graft_incubator()
        media_dir = self.grafts_root / 'incubator' / 'media'
        user_file = media_dir / 'user-upload.png'
        user_file.write_bytes(b'\x89PNG\r\nUSER-BYTES')

        # Force manifest drift by rewriting the archive with a different
        # description (changes the manifest sha256).
        _build_synthetic_incubator_archive(
            self.archive_path, description='drifted',
        )

        loader.graft_incubator()

        self.assertTrue(user_file.is_file())
        self.assertEqual(user_file.read_bytes(), b'\x89PNG\r\nUSER-BYTES')

    def test_graft_incubator_recovers_from_broken_status(self):
        """Assert a BROKEN INCUBATOR row flips back to INSTALLED."""
        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)
        incubator.status_id = NeuralModifierStatus.BROKEN
        incubator.save(update_fields=['status'])

        loader.graft_incubator()

        incubator.refresh_from_db()
        self.assertEqual(incubator.status_id, NeuralModifierStatus.INSTALLED)

    def test_graft_incubator_skips_when_archive_missing(self):
        """Assert missing incubator.zip is logged + skipped (no crash)."""
        self.archive_path.unlink()

        # Should not raise.
        loader.graft_incubator()

        # The fixture-shipped row stays as-is.
        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)
        self.assertEqual(incubator.manifest_hash, '')

    def test_graft_incubator_refuses_wrong_uuid(self):
        """Assert an archive declaring a non-INCUBATOR UUID is refused."""
        # Rebuild with a wrong UUID.
        manifest = {
            'slug': NeuralModifier.INCUBATOR_SLUG,
            'name': 'Wrong UUID',
            'version': '0.0.0',
            'genome': str(uuid.uuid4()),
            'author': 'tests',
            'license': 'MIT',
            'entry_modules': [],
        }
        with zipfile.ZipFile(self.archive_path, 'w') as zf:
            zf.writestr(
                f'{NeuralModifier.INCUBATOR_SLUG}/manifest.json',
                json.dumps(manifest) + '\n',
            )
            zf.writestr(
                f'{NeuralModifier.INCUBATOR_SLUG}/modifier_data.json', '[]\n',
            )
            zf.writestr(
                f'{NeuralModifier.INCUBATOR_SLUG}/code/.placeholder', '',
            )

        loader.graft_incubator()

        # No graft tree was created.
        self.assertFalse(
            (self.grafts_root / 'incubator' / 'manifest.json').exists(),
        )


class IncubatorUninstallResetTest(IncubatorTestCase):
    """Assert ``uninstall_genome('incubator')`` does the factory-reset semantic."""

    def test_uninstall_incubator_clears_owned_rows(self):
        """Assert IdentityAddon rows owned by INCUBATOR are removed."""
        loader.graft_incubator()
        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)
        IdentityAddon.objects.create(
            name='temp-addon', description='', genome=incubator,
        )
        self.assertEqual(
            IdentityAddon.objects.filter(genome=incubator).count(), 1,
        )

        loader.uninstall_genome(NeuralModifier.INCUBATOR_SLUG)

        # Row stays put.
        self.assertTrue(
            NeuralModifier.objects.filter(
                pk=NeuralModifier.INCUBATOR,
            ).exists(),
        )
        # Owned rows are gone.
        self.assertEqual(
            IdentityAddon.objects.filter(genome=incubator).count(), 0,
        )
        # Graft re-extracted from the archive.
        self.assertTrue(
            (self.grafts_root / 'incubator' / 'manifest.json').exists(),
        )

    def test_uninstall_incubator_status_stays_installed(self):
        """Assert the INCUBATOR row's status stays INSTALLED post-reset."""
        loader.graft_incubator()

        loader.uninstall_genome(NeuralModifier.INCUBATOR_SLUG)

        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)
        self.assertEqual(incubator.status_id, NeuralModifierStatus.INSTALLED)


class CanonicalUninstallRefusedTest(IncubatorTestCase):
    """Assert ``uninstall_genome('canonical')`` refuses with ValueError."""

    def test_uninstall_canonical_refused(self):
        with self.assertRaisesRegex(ValueError, 'canonical'):
            loader.uninstall_genome(NeuralModifier.CANONICAL_SLUG)
        # Row untouched.
        self.assertTrue(
            NeuralModifier.objects.filter(
                pk=NeuralModifier.CANONICAL,
            ).exists(),
        )


class SelectionMutexResetTest(IncubatorTestCase):
    """Assert the boot-time mutex sanity checks repair duplicate-fixture state."""

    def test_environment_selection_snaps_to_default(self):
        """Assert two ``selected=True`` envs collapse to ``DEFAULT_ENVIRONMENT``."""
        # Build the two environments via raw queryset .update() so the
        # ProjectEnvironment.save() override doesn't pre-emptively de-
        # select the first one.
        env_status = ProjectEnvironmentStatus.objects.create(name='Active')
        canonical = NeuralModifier.objects.get(pk=NeuralModifier.CANONICAL)
        ProjectEnvironment.objects.create(
            pk=ProjectEnvironment.DEFAULT_ENVIRONMENT,
            name='Default',
            status=env_status,
            available=True,
            selected=False,
            genome=canonical,
        )
        intruder = ProjectEnvironment.objects.create(
            name='Intruder',
            status=env_status,
            available=True,
            selected=False,
            genome=canonical,
        )
        ProjectEnvironment.objects.filter(
            pk__in=[
                ProjectEnvironment.DEFAULT_ENVIRONMENT, intruder.pk,
            ],
        ).update(selected=True)
        self.assertEqual(
            ProjectEnvironment.objects.filter(selected=True).count(), 2,
        )

        loader._ensure_selection_mutexes()

        self.assertEqual(
            ProjectEnvironment.objects.filter(selected=True).count(), 1,
        )
        self.assertTrue(
            ProjectEnvironment.objects.get(
                pk=ProjectEnvironment.DEFAULT_ENVIRONMENT,
            ).selected,
        )

    def test_modifier_selected_for_edit_snaps_to_incubator(self):
        """Assert two ``selected_for_edit=True`` modifiers collapse to INCUBATOR."""
        intruder = NeuralModifier.objects.create(
            slug='intruder',
            name='Intruder',
            version='0.0.0',
            author='tests',
            license='MIT',
            manifest_hash='',
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
            selected_for_edit=False,
        )
        # Force both selected via .update() to bypass the save() mutex.
        NeuralModifier.objects.filter(
            pk__in=[NeuralModifier.INCUBATOR, intruder.pk],
        ).update(selected_for_edit=True)
        self.assertEqual(
            NeuralModifier.objects.filter(selected_for_edit=True).count(), 2,
        )

        loader._ensure_selection_mutexes()

        self.assertEqual(
            NeuralModifier.objects.filter(selected_for_edit=True).count(), 1,
        )
        self.assertTrue(
            NeuralModifier.objects.get(
                pk=NeuralModifier.INCUBATOR,
            ).selected_for_edit,
        )

    def test_zero_selected_environment_snaps_to_default(self):
        """Assert no-rows-selected resolves to DEFAULT_ENVIRONMENT."""
        env_status = ProjectEnvironmentStatus.objects.create(name='Active')
        canonical = NeuralModifier.objects.get(pk=NeuralModifier.CANONICAL)
        ProjectEnvironment.objects.create(
            pk=ProjectEnvironment.DEFAULT_ENVIRONMENT,
            name='Default',
            status=env_status,
            available=True,
            selected=False,
            genome=canonical,
        )
        self.assertEqual(
            ProjectEnvironment.objects.filter(selected=True).count(), 0,
        )

        loader._ensure_selection_mutexes()

        self.assertTrue(
            ProjectEnvironment.objects.get(
                pk=ProjectEnvironment.DEFAULT_ENVIRONMENT,
            ).selected,
        )


class SaveAsRoundTripTest(TestCase):
    """Assert ``save_as_genome`` deep-clones rows + media; original untouched."""

    fixtures = ['neuroplasticity/fixtures/genetic_immutables.json']

    def setUp(self):
        super().setUp()
        self._tmp_root = Path(tempfile.mkdtemp(prefix='saveas-test-'))
        self.genomes_root = self._tmp_root / 'genomes'
        self.grafts_root = self._tmp_root / 'grafts'
        self.operating_room_root = self._tmp_root / 'operating_room'
        for d in (
            self.genomes_root, self.grafts_root, self.operating_room_root,
        ):
            d.mkdir()
        self._sys_path_snapshot = list(sys.path)
        self._sys_modules_snapshot = set(sys.modules.keys())
        self._settings_override = override_settings(
            NEURAL_MODIFIER_GENOMES_ROOT=str(self.genomes_root),
            NEURAL_MODIFIER_GRAFTS_ROOT=str(self.grafts_root),
            NEURAL_MODIFIER_OPERATING_ROOM_ROOT=str(self.operating_room_root),
        )
        self._settings_override.enable()

        # Build a source genome from scratch in the catalog + DB. Use
        # the simplest possible shape — a single IdentityAddon row + a
        # media file — so we can assert deep-clone behaviour without
        # cross-FK noise.
        from neuroplasticity.tests.test_modifier_lifecycle import (
            build_fake_bundle_archive,
        )
        self.source_archive = build_fake_bundle_archive(
            self.genomes_root, 'sourcer',
        )
        loader.install_genome_to_graft(self.source_archive)
        # Add a media file under the source graft so save-as can copy it.
        source_media = self.grafts_root / 'sourcer' / 'media'
        source_media.mkdir(parents=True, exist_ok=True)
        (source_media / 'avatar.png').write_bytes(b'PIXELS')

    def tearDown(self):
        self._settings_override.disable()
        sys.path[:] = self._sys_path_snapshot
        for name in list(sys.modules.keys()):
            if name not in self._sys_modules_snapshot:
                sys.modules.pop(name, None)
        shutil.rmtree(self._tmp_root, ignore_errors=True)
        super().tearDown()

    def _source(self) -> NeuralModifier:
        return NeuralModifier.objects.get(slug='sourcer')

    def test_save_as_creates_new_genome_with_fresh_pks(self):
        """Assert save-as makes a new modifier with fresh PKs on cloned rows."""
        source = self._source()
        source_addon_pks = set(
            IdentityAddon.objects.filter(genome=source).values_list(
                'pk', flat=True,
            )
        )
        self.assertEqual(len(source_addon_pks), 3)

        new_modifier = loader.save_as_genome(
            'sourcer', 'forge_target', new_name='Forged',
        )

        self.assertNotEqual(new_modifier.pk, source.pk)
        self.assertEqual(new_modifier.slug, 'forge_target')
        self.assertEqual(new_modifier.name, 'Forged')

        cloned_pks = set(
            IdentityAddon.objects.filter(genome=new_modifier).values_list(
                'pk', flat=True,
            )
        )
        self.assertEqual(len(cloned_pks), 3)
        # Disjoint — the rows were cloned, not moved.
        self.assertEqual(cloned_pks & source_addon_pks, set())

    def test_save_as_leaves_source_untouched(self):
        """Assert source rows + zip are unchanged post save-as."""
        source = self._source()
        before_pks = set(
            IdentityAddon.objects.filter(genome=source).values_list(
                'pk', flat=True,
            )
        )
        before_zip_bytes = self.source_archive.read_bytes()

        loader.save_as_genome('sourcer', 'forge_target_2')

        source.refresh_from_db()
        after_pks = set(
            IdentityAddon.objects.filter(genome=source).values_list(
                'pk', flat=True,
            )
        )
        self.assertEqual(before_pks, after_pks)
        self.assertEqual(self.source_archive.read_bytes(), before_zip_bytes)

    def test_save_as_copies_media_into_new_graft(self):
        """Assert media bytes are copied to the new graft tree."""
        loader.save_as_genome('sourcer', 'forge_target_3')

        copied = (
            self.grafts_root
            / 'forge_target_3'
            / 'media'
            / 'avatar.png'
        )
        self.assertTrue(copied.is_file())
        self.assertEqual(copied.read_bytes(), b'PIXELS')

    def test_save_as_bakes_new_zip_in_catalog(self):
        """Assert a new genome zip lands in genomes_root."""
        loader.save_as_genome('sourcer', 'forge_target_4')
        self.assertTrue(
            (self.genomes_root / 'forge_target_4.zip').is_file(),
        )

    def test_save_as_refuses_blank_slug(self):
        with self.assertRaisesRegex(ValueError, 'slug'):
            loader.save_as_genome('sourcer', '')

    def test_save_as_refuses_canonical_slug(self):
        with self.assertRaisesRegex(ValueError, 'reserved'):
            loader.save_as_genome('sourcer', NeuralModifier.CANONICAL_SLUG)

    def test_save_as_refuses_incubator_slug(self):
        with self.assertRaisesRegex(ValueError, 'reserved'):
            loader.save_as_genome('sourcer', NeuralModifier.INCUBATOR_SLUG)

    def test_save_as_refuses_collision(self):
        loader.save_as_genome('sourcer', 'forge_target_5')
        with self.assertRaises(FileExistsError):
            loader.save_as_genome('sourcer', 'forge_target_5')


class SaveAsApiTest(SaveAsRoundTripTest):
    """End-to-end POST /api/v2/neural-modifiers/<slug>/save-as/."""

    def test_api_save_as_201_with_restart_imminent(self):
        """Assert POST clones the source and stamps restart_imminent."""
        from rest_framework.test import APIClient

        client = APIClient()
        with patch('neuroplasticity.api.trigger_system_restart'):
            res = client.post(
                '/api/v2/neural-modifiers/sourcer/save-as/',
                {'slug': 'api_forged', 'name': 'API Forged'},
                format='json',
            )

        self.assertEqual(res.status_code, 201, res.data)
        payload = res.json()
        self.assertEqual(payload['slug'], 'api_forged')
        self.assertTrue(payload.get('restart_imminent'))
        self.assertTrue(
            NeuralModifier.objects.filter(slug='api_forged').exists(),
        )

    def test_api_save_as_400_on_blank_slug(self):
        from rest_framework.test import APIClient

        client = APIClient()
        with patch('neuroplasticity.api.trigger_system_restart'):
            res = client.post(
                '/api/v2/neural-modifiers/sourcer/save-as/',
                {'slug': '', 'name': 'Nope'},
                format='json',
            )
        self.assertEqual(res.status_code, 400, res.data)

    def test_api_save_as_409_on_collision(self):
        from rest_framework.test import APIClient

        client = APIClient()
        with patch('neuroplasticity.api.trigger_system_restart'):
            res = client.post(
                '/api/v2/neural-modifiers/sourcer/save-as/',
                {'slug': 'collide', 'name': 'First'},
                format='json',
            )
            self.assertEqual(res.status_code, 201, res.data)
            res = client.post(
                '/api/v2/neural-modifiers/sourcer/save-as/',
                {'slug': 'collide', 'name': 'Second'},
                format='json',
            )
        self.assertEqual(res.status_code, 409, res.data)
