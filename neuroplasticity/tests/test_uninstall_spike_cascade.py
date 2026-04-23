"""SpikeTrain / Spike behavior around bundle uninstall.

Michael's ruling: bundle uninstall is a clean removal. A SpikeTrain
referencing a bundle-contributed ``ProjectEnvironment`` cascades away
with the bundle, and its Spikes go with it — no orphan rows left over.

Current FK config (``ProjectEnvironmentMixin.environment`` is
``CASCADE``, ``Spike.spike_train`` is ``CASCADE``) means:

* The bundle's env deletion cascades into SpikeTrain.
* SpikeTrain deletion cascades into its Spikes.
* No orphan Spike / SpikeTrain rows after uninstall.

The control case proves canonical-env SpikeTrains are untouched by
bundle ops — only bundle-env trains cascade.
"""

from __future__ import annotations

from central_nervous_system.models import (
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
    build_fake_bundle,
)


class _SpikeCascadeSetupMixin:
    """Programmatic setup for canonical env + minimal SpikeTrain status rows."""

    def _ensure_env_and_status(self):
        env_type = ProjectEnvironmentType.objects.create(name='Test Type')
        env_status = ProjectEnvironmentStatus.objects.create(name='Test Status')
        canonical_modifier = NeuralModifier.objects.get(
            pk=NeuralModifier.CANONICAL
        )
        canonical_env, _ = ProjectEnvironment.objects.update_or_create(
            pk=ProjectEnvironment.DEFAULT_ENVIRONMENT,
            defaults={
                'name': 'Canonical Env',
                'type': env_type,
                'status': env_status,
                'available': True,
                'selected': False,
                'genome': canonical_modifier,
            },
        )
        # SpikeTrainStatus + SpikeStatus rows live in the CNS
        # genetic_immutables fixture; reference a handful by PK to
        # seed only what we need.
        SpikeTrainStatus.objects.get_or_create(
            pk=SpikeTrainStatus.CREATED, defaults={'name': 'Created'}
        )
        SpikeStatus.objects.get_or_create(
            pk=SpikeStatus.CREATED, defaults={'name': 'Created'}
        )
        return canonical_env, env_type, env_status


class BundleEnvUninstallCascadesSpikeTrainTest(
    _SpikeCascadeSetupMixin, ModifierLifecycleTestCase
):
    """Uninstalling a bundle's env CASCADE-deletes SpikeTrain AND its Spikes."""

    def test_bundle_env_uninstall_cascades_spiketrain_and_spikes(self):
        """Assert bundle env uninstall cascades train and all its spikes away."""
        canonical_env, env_type, env_status = self._ensure_env_and_status()
        bundle_env_pk = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

        payload = [{
            'model': 'environments.projectenvironment',
            'pk': bundle_env_pk,
            'fields': {
                'created': '2026-04-23T00:00:00Z',
                'modified': '2026-04-23T00:00:00Z',
                'description': 'bundle-contributed env',
                'name': 'bundle-env',
                'type': str(env_type.pk),
                'status': str(env_status.pk),
                'available': True,
                'selected': False,
                'default_iteration_definition': None,
            },
        }]
        build_fake_bundle(
            self.scratch_root, 'envspikes', modifier_data=payload
        )
        self.install_fake('envspikes')

        bundle_env = ProjectEnvironment.objects.get(pk=bundle_env_pk)
        train = SpikeTrain.objects.create(
            environment=bundle_env,
            status_id=SpikeTrainStatus.CREATED,
        )
        spike = Spike.objects.create(
            spike_train=train,
            status_id=SpikeStatus.CREATED,
        )
        train_pk = train.pk
        spike_pk = spike.pk

        loader.uninstall_bundle('envspikes')

        self.assertFalse(
            ProjectEnvironment.objects.filter(pk=bundle_env_pk).exists(),
            'Bundle env should be gone after uninstall.',
        )
        self.assertFalse(
            SpikeTrain.objects.filter(pk=train_pk).exists(),
            'SpikeTrain should cascade with its bundle-owned environment.',
        )
        self.assertFalse(
            Spike.objects.filter(pk=spike_pk).exists(),
            'Spikes should cascade with their SpikeTrain — no orphans.',
        )


class CanonicalEnvSpikeTrainSurvivesUninstallTest(
    _SpikeCascadeSetupMixin, ModifierLifecycleTestCase
):
    """Control case: a SpikeTrain pinned to canonical env is untouched."""

    def test_canonical_env_spiketrain_unaffected_by_uninstall(self):
        """Assert canonical-env SpikeTrain and its Spikes survive uninstall."""
        canonical_env, _, _ = self._ensure_env_and_status()
        train = SpikeTrain.objects.create(
            environment=canonical_env,
            status_id=SpikeTrainStatus.CREATED,
        )
        spike = Spike.objects.create(
            spike_train=train,
            status_id=SpikeStatus.CREATED,
        )

        build_fake_bundle(self.scratch_root, 'unrelated')
        self.install_fake('unrelated')
        loader.uninstall_bundle('unrelated')

        train.refresh_from_db()
        self.assertEqual(train.environment_id, canonical_env.pk)
        self.assertTrue(Spike.objects.filter(pk=spike.pk).exists())
        self.assertTrue(
            ProjectEnvironment.objects.filter(pk=canonical_env.pk).exists()
        )
        self.assertEqual(
            ProjectEnvironment.objects.get(pk=canonical_env.pk).genome_id,
            NeuralModifier.CANONICAL,
        )
