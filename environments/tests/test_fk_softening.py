"""FK-softening tests for environments -> owned-row edges.

Covers two softened PROTECT edges at once, both now CASCADE:

1. ``ProjectEnvironmentMixin.environment`` -> CASCADE. Consumers
   (Neuron, SpikeTrain, NeuralPathway) that reference a bundle-owned
   environment are removed with the bundle on uninstall.

2. ``ProjectEnvironment.default_iteration_definition`` -> CASCADE.
   Cross-bundle case: Bundle A's env pointing at Bundle B's iteration
   definition. Uninstalling B cascades A's env out too (acceptable in
   practice: the canonical env ships in genetic_immutables and is
   never cross-referenced at a bundle's default iteration definition).
"""

from central_nervous_system.models import (
    Effector,
    NeuralPathway,
    Neuron,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from environments.models import (
    Executable,
    ProjectEnvironment,
    ProjectEnvironmentStatus,
)
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from temporal_lobe.models import IterationDefinition


def _make_modifier(slug: str) -> NeuralModifier:
    return NeuralModifier.objects.create(
        name='FK Test Bundle {0}'.format(slug),
        slug=slug,
        version='1.0.0',
        author='tests',
        license='MIT',
        manifest_hash='0' * 64,
        manifest_json={},
        status_id=NeuralModifierStatus.INSTALLED,
    )


def _make_project_env(
    name: str, modifier: NeuralModifier
) -> ProjectEnvironment:
    return ProjectEnvironment.objects.create(
        name=name,
        description='',
        status=ProjectEnvironmentStatus.objects.first(),
        genome=modifier,
    )


class NeuronEnvironmentCascadeOnBundleRemovalTest(CommonFixturesAPITestCase):
    def setUp(self):
        super().setUp()
        self.modifier = _make_modifier('fk-test-env-cascade')
        self.bundle_env = _make_project_env('FK Test Bundle Env', self.modifier)
        effector = Effector.objects.create(
            name='FK Test Effector',
            executable=Executable.objects.first(),
        )
        self.pathway = NeuralPathway.objects.create(
            name='FK Test Pathway', environment=self.bundle_env
        )
        self.neuron = Neuron.objects.create(
            pathway=self.pathway,
            effector=effector,
            environment=self.bundle_env,
        )

    def test_uninstall_cascades_consumers(self):
        """Assert Neuron and Pathway are gone after bundle uninstall."""
        self.assertEqual(self.neuron.environment_id, self.bundle_env.pk)

        loader.uninstall_bundle(self.modifier.slug)

        self.assertFalse(
            ProjectEnvironment.objects.filter(pk=self.bundle_env.pk).exists()
        )
        self.assertFalse(Neuron.objects.filter(pk=self.neuron.pk).exists())
        self.assertFalse(
            NeuralPathway.objects.filter(pk=self.pathway.pk).exists()
        )


class CrossBundleDefaultIterationDefinitionCascadeTest(
    CommonFixturesAPITestCase
):
    """Bundle A's env points at Bundle B's IterationDefinition; B goes first."""

    def setUp(self):
        super().setUp()
        self.modifier_a = _make_modifier('fk-test-cross-bundle-a')
        self.modifier_b = _make_modifier('fk-test-cross-bundle-b')
        self.iter_def_b = IterationDefinition.objects.create(
            name='FK Test B Iteration Definition',
            genome=self.modifier_b,
        )
        self.env_a = _make_project_env('FK Test A Env', self.modifier_a)
        self.env_a.default_iteration_definition = self.iter_def_b
        self.env_a.save(update_fields=['default_iteration_definition'])

    def test_uninstall_b_cascades_a_env(self):
        """Assert A's env cascades away when B's IterationDefinition goes."""
        self.assertEqual(
            self.env_a.default_iteration_definition_id, self.iter_def_b.pk
        )

        loader.uninstall_bundle(self.modifier_b.slug)

        self.assertFalse(
            IterationDefinition.objects.filter(pk=self.iter_def_b.pk).exists()
        )
        # A's env cascaded out with B's IterationDefinition.
        self.assertFalse(
            ProjectEnvironment.objects.filter(pk=self.env_a.pk).exists()
        )
        # Modifier A itself is untouched; only its env row fell.
        self.assertTrue(
            NeuralModifier.objects.filter(pk=self.modifier_a.pk).exists()
        )
