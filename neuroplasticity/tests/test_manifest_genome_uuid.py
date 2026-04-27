"""Manifest-pinned genome UUID validation + collision tests.

Every NeuralModifier bundle declares a stable UUID in its
``manifest.json`` under ``"genome"``. The loader treats that UUID as
the authoritative PK for the bundle's ``NeuralModifier`` row, so the
bundle's identity is portable across machines and across versions.

Covers:

* ``_validate_manifest`` rejects manifests with no ``genome`` key,
  manifests with a non-UUID ``genome`` value, and accepts a valid
  UUID string.
* Fresh install creates the ``NeuralModifier`` row with PK equal to
  the manifest's declared genome UUID — not a fresh ``uuid4()``.
* Install refuses (cleanly, no DB row, no graft) when the manifest's
  declared UUID is already in use by a different installed slug.
"""

from __future__ import annotations

import json
import uuid

from neuroplasticity import loader
from neuroplasticity.loader import _validate_manifest
from neuroplasticity.models import NeuralModifier
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
    build_fake_bundle,
)


def _base_manifest(**overrides) -> dict:
    """Minimal valid manifest dict; tests pass overrides for the field
    they're exercising."""
    manifest = {
        'slug': 'fakeslug',
        'name': 'Fake',
        'version': '0.0.1',
        'genome': str(uuid.uuid4()),
        'author': 'tests',
        'license': 'MIT',
        'entry_modules': [],
    }
    manifest.update(overrides)
    return manifest


class ValidateManifestGenomeKeyTest(ModifierLifecycleTestCase):
    def test_validate_manifest_rejects_missing_genome_key(self):
        """Assert _validate_manifest refuses a manifest with no genome key."""
        manifest = _base_manifest()
        del manifest['genome']

        with self.assertRaisesRegex(ValueError, 'genome'):
            _validate_manifest(manifest)

    def test_validate_manifest_rejects_non_uuid_genome(self):
        """Assert _validate_manifest refuses a non-UUID genome string."""
        manifest = _base_manifest(genome='not-a-uuid')

        with self.assertRaisesRegex(ValueError, 'not a valid UUID'):
            _validate_manifest(manifest)

    def test_validate_manifest_rejects_non_string_genome(self):
        """Assert _validate_manifest refuses a non-string genome (e.g. int)."""
        manifest = _base_manifest(genome=12345)

        with self.assertRaisesRegex(ValueError, 'genome'):
            _validate_manifest(manifest)

    def test_validate_manifest_accepts_valid_uuid_genome(self):
        """Assert _validate_manifest accepts a well-formed UUID string."""
        manifest = _base_manifest(genome=str(uuid.uuid4()))

        # Should not raise.
        _validate_manifest(manifest)


class InstallPinsManifestGenomeAsPkTest(ModifierLifecycleTestCase):
    def test_install_uses_manifest_genome_as_pk(self):
        """Assert install creates the NeuralModifier row with PK == manifest genome."""
        bundle = build_fake_bundle(self.scratch_root, 'pinme')
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        declared_uuid = uuid.UUID(manifest['genome'])

        modifier = self.install_fake('pinme')

        self.assertEqual(modifier.pk, declared_uuid)
        self.assertEqual(
            NeuralModifier.objects.get(slug='pinme').pk, declared_uuid
        )

    def test_install_pk_survives_fixed_value_across_runs(self):
        """Assert the install path honours a fixed UUID literal.

        Manifests carry stable UUIDs across machines; this proves the
        loader doesn't quietly swap one in for ``uuid4()``.
        """
        fixed_uuid = uuid.UUID('12345678-1234-5678-1234-567812345678')
        bundle = build_fake_bundle(self.scratch_root, 'fixed')
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['genome'] = str(fixed_uuid)
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        modifier = self.install_fake('fixed')

        self.assertEqual(modifier.pk, fixed_uuid)


class InstallRefusesUuidCollisionTest(ModifierLifecycleTestCase):
    def test_install_refuses_when_uuid_belongs_to_other_slug(self):
        """Assert install refuses a bundle whose declared UUID is already in
        use by an installed bundle with a different slug. Same UUID +
        same slug stays the upgrade/reinstall path and is not blocked."""
        shared_uuid = str(uuid.uuid4())

        first = build_fake_bundle(self.scratch_root, 'firsty')
        first_manifest = first / 'manifest.json'
        first_data = json.loads(first_manifest.read_text())
        first_data['genome'] = shared_uuid
        first_manifest.write_text(json.dumps(first_data, indent=2) + '\n')
        self.install_fake('firsty')

        second = build_fake_bundle(self.scratch_root, 'secondy')
        second_manifest = second / 'manifest.json'
        second_data = json.loads(second_manifest.read_text())
        second_data['genome'] = shared_uuid
        second_manifest.write_text(json.dumps(second_data, indent=2) + '\n')

        with self.assertRaisesRegex(ValueError, 'firsty'):
            self.install_fake('secondy')

        # Refusal is clean: no DB row, no graft dir.
        self.assertFalse(
            NeuralModifier.objects.filter(slug='secondy').exists()
        )
        self.assertFalse((self.grafts_root / 'secondy').exists())
        # First bundle is unaffected.
        self.assertTrue(
            NeuralModifier.objects.filter(slug='firsty').exists()
        )

    def test_install_allows_same_uuid_on_reinstall_after_uninstall(self):
        """Assert reinstalling a bundle reuses its manifest UUID without
        being blocked by the collision guard.

        The guard excludes the same slug from the lookup, so an uninstall
        followed by an archive reinstall lands on the original PK every
        time — that's the whole point of pinning the UUID in the
        manifest."""
        bundle = build_fake_bundle(self.scratch_root, 'reusable')
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        declared_uuid = uuid.UUID(manifest['genome'])

        first = self.install_fake('reusable')
        self.assertEqual(first.pk, declared_uuid)

        loader.uninstall_bundle('reusable')
        # boot_bundles' orphan sweep clears the deferred runtime dir
        # before the reinstall — same restart simulation other lifecycle
        # tests use.
        loader.boot_bundles()

        second = self.install_fake('reusable')
        self.assertEqual(second.pk, declared_uuid)
