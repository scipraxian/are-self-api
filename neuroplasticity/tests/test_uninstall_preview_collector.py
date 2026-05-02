"""Uninstall-preview tests — verifies the ``Collector`` tree payload.

The uninstall preview must mirror what ``modifier.delete()`` would
actually do: direct rows, cascaded rows via every CASCADE FK the
collector walks, SET_NULL rollovers, and any PROTECT blockers. This
test pins down that the Collector-based preview finds transitive
cascades (EffectorContext, Neuron, EffectorArgumentAssignment when
an Effector goes away) and does not stop at direct-owned rows.
"""

from __future__ import annotations

from central_nervous_system.models import (
    Effector,
    EffectorContext,
    NeuralPathway,
    Neuron,
)
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
)


class UninstallPreviewIncludesCascadesTest(ModifierLifecycleTestCase):
    # CNS genetic_immutables seeds CNSDistributionMode and the status
    # lookup rows Effector/Neuron FKs default to. Environments ones
    # seed the Executable rows referenced by Effector class constants.
    fixtures = [
        'neuroplasticity/fixtures/genetic_immutables.json',
        'central_nervous_system/fixtures/genetic_immutables.json',
        'environments/fixtures/genetic_immutables.json',
    ]

    def test_preview_returns_direct_and_cascade_buckets(self):
        """Assert preview payload walks CASCADE FKs beyond direct-owned rows."""
        modifier = NeuralModifier.objects.create(
            slug='preview_bundle',
            name='Preview',
            version='1.0.0',
            author='tests',
            license='MIT',
            manifest_hash='0' * 64,
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )
        effector = Effector.objects.create(
            name='preview-effector', genome=modifier
        )
        EffectorContext.objects.create(
            effector=effector, key='k', value='v'
        )
        pathway = NeuralPathway.objects.create(
            name='preview-pathway', genome=modifier
        )
        Neuron.objects.create(pathway=pathway, effector=effector)

        preview = loader.genome_uninstall_preview('preview_bundle')

        self.assertEqual(preview['slug'], 'preview_bundle')
        direct_models = {row['model'] for row in preview['direct']}
        self.assertIn('central_nervous_system.effector', direct_models)
        self.assertIn('central_nervous_system.neuralpathway', direct_models)

        # EffectorContext + Neuron were NOT genome-stamped but both
        # CASCADE with their parents — Collector must find them.
        cascade_models = {row['model'] for row in preview['cascade']}
        self.assertIn(
            'central_nervous_system.effectorcontext', cascade_models
        )
        self.assertIn('central_nervous_system.neuron', cascade_models)

        # Payload shape contract.
        for bucket in ('direct', 'cascade', 'set_null', 'protected'):
            self.assertIn(bucket, preview)
            for row in preview[bucket]:
                self.assertIn('app_label', row)
                self.assertIn('model', row)
                self.assertIn('pk', row)
                self.assertIn('name_or_repr', row)
                self.assertIn('reason', row)

    def test_empty_bundle_returns_empty_buckets(self):
        """Assert a bundle with no owned rows yields empty tree but valid shape."""
        NeuralModifier.objects.create(
            slug='empty_bundle',
            name='Empty',
            version='1.0.0',
            author='tests',
            license='MIT',
            manifest_hash='0' * 64,
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )

        preview = loader.genome_uninstall_preview('empty_bundle')

        self.assertEqual(preview['slug'], 'empty_bundle')
        self.assertEqual(preview['row_count'], 0)
        self.assertEqual(preview['direct'], [])
        self.assertEqual(preview['cascade'], [])
        self.assertEqual(preview['set_null'], [])
        self.assertEqual(preview['protected'], [])
