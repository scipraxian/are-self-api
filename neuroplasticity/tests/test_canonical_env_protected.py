"""The canonical ProjectEnvironment survives every bundle install cycle.

Michael's ruling: bundles MAY contribute their own ProjectEnvironment
rows (unreal does), but the zygote-shipped default environment is
canonical-owned and untouchable. This test locks both halves of that
invariant:

* A bundle whose ``modifier_data.json`` tries to overwrite the
  canonical env's PK is rejected by the install-collision guard.
* A bundle-contributed env cascades away on uninstall (proves the
  bundle-contributed-env path is NOT broken by the canonical guard).
"""

from __future__ import annotations

from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
)
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
    build_fake_bundle,
)


class _CanonicalEnvSetupMixin:
    """Programmatic canonical-env setup — skips the full fixture chain.

    The cross-app fixture chain (zygote → initial_phenotypes etc.) has
    dependencies in unrelated apps we don't care about here; the
    targeted test just needs a ProjectEnvironment row stamped with
    ``genome=canonical``. Building it directly keeps the test focused.
    """

    def _ensure_canonical_env(self) -> ProjectEnvironment:
        env_status = ProjectEnvironmentStatus.objects.create(name='Test Status')
        canonical = NeuralModifier.objects.get(pk=NeuralModifier.CANONICAL)
        env, _ = ProjectEnvironment.objects.update_or_create(
            pk=ProjectEnvironment.DEFAULT_ENVIRONMENT,
            defaults={
                'name': 'Canonical Env',
                'status': env_status,
                'available': True,
                'selected': False,
                'genome': canonical,
            },
        )
        return env


class CanonicalEnvIsProtectedTest(
    _CanonicalEnvSetupMixin, ModifierLifecycleTestCase
):
    """Bundle trying to overwrite the canonical env PK is rejected."""

    def test_bundle_cannot_overwrite_canonical_environment(self):
        """Assert install refuses to overwrite ProjectEnvironment.DEFAULT_ENVIRONMENT."""
        canonical_env = self._ensure_canonical_env()
        default_pk = str(ProjectEnvironment.DEFAULT_ENVIRONMENT)
        original_name = canonical_env.name
        self.assertEqual(canonical_env.genome_id, NeuralModifier.CANONICAL)

        payload = [
            {
                'model': 'environments.projectenvironment',
                'pk': default_pk,
                'fields': {
                    'created': '2026-04-23T00:00:00Z',
                    'modified': '2026-04-23T00:00:00Z',
                    'description': 'bundle trying to steal canonical env',
                    'name': 'stolen-env',
                    'status': str(canonical_env.status_id),
                    'available': True,
                    'selected': False,
                    'default_iteration_definition': None,
                },
            }
        ]
        build_fake_bundle(self.scratch_root, 'envthief', modifier_data=payload)

        with self.assertRaisesRegex(RuntimeError, 'canonical'):
            self.install_fake('envthief')

        self.assertFalse(
            NeuralModifier.objects.filter(slug='envthief').exists()
        )
        survivor = ProjectEnvironment.objects.get(pk=default_pk)
        self.assertEqual(survivor.name, original_name)
        self.assertEqual(survivor.genome_id, NeuralModifier.CANONICAL)


class BundleContributedEnvCascadesOnUninstallTest(
    _CanonicalEnvSetupMixin, ModifierLifecycleTestCase
):
    """A bundle's own ProjectEnvironment row cascades away with the bundle."""

    def test_bundle_env_cascades_on_uninstall_and_canonical_survives(self):
        """Assert uninstall deletes the bundle env but not the canonical env."""
        canonical_env = self._ensure_canonical_env()
        bundle_env_pk = '11111111-2222-3333-4444-555555555555'

        payload = [
            {
                'model': 'environments.projectenvironment',
                'pk': bundle_env_pk,
                'fields': {
                    'created': '2026-04-23T00:00:00Z',
                    'modified': '2026-04-23T00:00:00Z',
                    'description': 'bundle-contributed env',
                    'name': 'bundle-env',
                    'status': str(canonical_env.status_id),
                    'available': True,
                    'selected': False,
                    'default_iteration_definition': None,
                },
            }
        ]
        build_fake_bundle(self.scratch_root, 'envbundle', modifier_data=payload)

        self.install_fake('envbundle')
        self.assertTrue(
            ProjectEnvironment.objects.filter(pk=bundle_env_pk).exists()
        )

        loader.uninstall_bundle('envbundle')

        self.assertFalse(
            ProjectEnvironment.objects.filter(pk=bundle_env_pk).exists()
        )
        # Canonical env untouched.
        self.assertTrue(
            ProjectEnvironment.objects.filter(
                pk=ProjectEnvironment.DEFAULT_ENVIRONMENT
            ).exists()
        )
