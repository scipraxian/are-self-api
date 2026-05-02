"""Install-collision guard tests (Canonical Genome, Deliverable 3).

A bundle's ``modifier_data.json`` lists rows to upsert by PK. Before
the guard, an upsert against a PK already owned by canonical,
another bundle, or a user SILENTLY overwrote that row and stamped it
with the installing bundle's genome — destroying unrelated work. The
new guard refuses, and the install rolls back cleanly.
"""

from __future__ import annotations

import json

from identity.models import IdentityAddon
from neuroplasticity import loader
from neuroplasticity.models import (
    NeuralModifier,
    NeuralModifierInstallationLog,
    NeuralModifierStatus,
)
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
    build_fake_bundle,
)


class InstallRefusesOverwriteOfCanonicalRowTest(ModifierLifecycleTestCase):
    def test_install_refused_when_pk_owned_by_canonical(self):
        """Assert install refuses to overwrite a canonical-owned PK."""
        canonical = NeuralModifier.objects.get(pk=NeuralModifier.CANONICAL)
        pre_existing = IdentityAddon.objects.create(
            name='canonical-owned',
            genome=canonical,
        )

        payload = [{
            'model': 'identity.identityaddon',
            'pk': str(pre_existing.pk),
            'fields': {
                'name': 'hostile-overwrite',
                'description': 'bundle trying to steal canonical row',
                'addon_class_name': None,
                'function_slug': None,
                'phase': None,
            },
        }]
        build_fake_bundle(
            self.scratch_root, 'hostile', modifier_data=payload
        )

        with self.assertRaisesRegex(RuntimeError, 'canonical'):
            self.install_fake('hostile')

        # Install rolled back: no row, no graft, canonical row still
        # points at the original data.
        self.assertFalse(
            NeuralModifier.objects.filter(slug='hostile').exists()
        )
        self.assertFalse((self.grafts_root / 'hostile').exists())
        survivor = IdentityAddon.objects.get(pk=pre_existing.pk)
        self.assertEqual(survivor.name, 'canonical-owned')
        self.assertEqual(survivor.genome_id, NeuralModifier.CANONICAL)


class InstallRefusesOverwriteOfOtherBundleRowTest(ModifierLifecycleTestCase):
    def test_install_refused_when_pk_owned_by_other_bundle(self):
        """Assert install refuses to overwrite another bundle's PK."""
        other = NeuralModifier.objects.create(
            slug='incumbent',
            name='Incumbent',
            version='1.0.0',
            author='tests',
            license='MIT',
            manifest_hash='0' * 64,
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )
        victim = IdentityAddon.objects.create(
            name='incumbent-row', genome=other
        )

        payload = [{
            'model': 'identity.identityaddon',
            'pk': str(victim.pk),
            'fields': {
                'name': 'hostile-overwrite',
                'description': 'bundle trying to steal incumbent row',
                'addon_class_name': None,
                'function_slug': None,
                'phase': None,
            },
        }]
        build_fake_bundle(
            self.scratch_root, 'hostile2', modifier_data=payload
        )

        with self.assertRaisesRegex(RuntimeError, 'incumbent'):
            self.install_fake('hostile2')

        self.assertFalse(
            NeuralModifier.objects.filter(slug='hostile2').exists()
        )
        survivor = IdentityAddon.objects.get(pk=victim.pk)
        self.assertEqual(survivor.genome_id, other.pk)


class InstallRefusesOverwriteOfUserRowTest(ModifierLifecycleTestCase):
    def test_install_refused_when_pk_owned_by_user(self):
        """Assert install refuses to overwrite a user-created (INCUBATOR) PK."""
        user_row = IdentityAddon.objects.create(name='user-created')
        self.assertEqual(user_row.genome_id, NeuralModifier.INCUBATOR)

        payload = [{
            'model': 'identity.identityaddon',
            'pk': str(user_row.pk),
            'fields': {
                'name': 'hostile-overwrite',
                'description': 'bundle trying to steal user row',
                'addon_class_name': None,
                'function_slug': None,
                'phase': None,
            },
        }]
        build_fake_bundle(
            self.scratch_root, 'hostile3', modifier_data=payload
        )

        with self.assertRaisesRegex(RuntimeError, 'user'):
            self.install_fake('hostile3')

        self.assertFalse(
            NeuralModifier.objects.filter(slug='hostile3').exists()
        )
        survivor = IdentityAddon.objects.get(pk=user_row.pk)
        self.assertEqual(survivor.name, 'user-created')
        self.assertEqual(survivor.genome_id, NeuralModifier.INCUBATOR)


class InstallRefusesCanonicalSlugTest(ModifierLifecycleTestCase):
    def test_install_refused_when_manifest_claims_canonical_slug(self):
        """Assert install refuses a bundle whose manifest.slug is 'canonical'.

        A hostile zip naming itself ``canonical`` would otherwise slip
        past ``_get_or_create_modifier`` (which reuses the existing
        canonical row on slug match) and start stamping bundle rows onto
        it. The UUID guard matches against
        ``NeuralModifier.CANONICAL`` — the frozen anchor — and raises
        before any installation log or graft work lands on disk.
        """
        canonical_manifest_before = NeuralModifier.objects.get(
            pk=NeuralModifier.CANONICAL
        ).manifest_json
        logs_before = NeuralModifierInstallationLog.objects.filter(
            neural_modifier_id=NeuralModifier.CANONICAL
        ).count()

        build_fake_bundle(self.scratch_root, 'canonical')

        with self.assertRaisesRegex(ValueError, 'canonical'):
            self.install_fake('canonical')

        # Canonical row still exists, untouched.
        canonical_after = NeuralModifier.objects.get(
            pk=NeuralModifier.CANONICAL
        )
        self.assertEqual(
            canonical_after.manifest_json, canonical_manifest_before
        )
        # No installation log was attached to canonical.
        self.assertEqual(
            NeuralModifierInstallationLog.objects.filter(
                neural_modifier_id=NeuralModifier.CANONICAL
            ).count(),
            logs_before,
        )
        # No graft dir was created.
        self.assertFalse((self.grafts_root / 'canonical').exists())


class ReinstallSameBundleIsAllowedTest(ModifierLifecycleTestCase):
    def test_reinstall_same_bundle_allows_overwrite(self):
        """Assert a re-install of the same slug with a colliding PK succeeds.

        The guard explicitly allows writes where the existing row's
        ``genome_id`` already matches the installing modifier — a
        reinstall and an upgrade both hit this path per-row.
        """
        pk_str = 'eaeb5a7a-7cc5-4ad5-9a74-bdd0ed0c8c45'
        payload = [{
            'model': 'identity.identityaddon',
            'pk': pk_str,
            'fields': {
                'name': 'echo',
                'description': 'first install',
                'addon_class_name': None,
                'function_slug': None,
                'phase': None,
            },
        }]
        build_fake_bundle(
            self.scratch_root, 'echobundle', modifier_data=payload
        )
        self.install_fake('echobundle')
        self.assertEqual(
            IdentityAddon.objects.get(pk=pk_str).description,
            'first install',
        )

        # Upgrade the row in-place through the bundle's upgrade path.
        upgrade_payload = [{
            'model': 'identity.identityaddon',
            'pk': pk_str,
            'fields': {
                'name': 'echo',
                'description': 'second install',
                'addon_class_name': None,
                'function_slug': None,
                'phase': None,
            },
        }]
        bundle = self.scratch_root / 'echobundle'
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['version'] = '0.0.2'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        (bundle / 'modifier_data.json').write_text(
            json.dumps(upgrade_payload, indent=2) + '\n'
        )

        loader.upgrade_source_to_graft(bundle, 'echobundle')

        self.assertEqual(
            IdentityAddon.objects.get(pk=pk_str).description,
            'second install',
        )
