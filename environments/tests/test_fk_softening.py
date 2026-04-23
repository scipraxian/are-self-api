"""FK-softening tests for environments -> owned-row edges.

Covers two softened PROTECT edges at once:

1. ``ProjectEnvironmentMixin.environment`` -> SET_NULL. Consumers
   (Neuron, SpikeTrain, NeuralPathway) survive when a bundle-owned
   environment goes away, falling back to default resolution.

2. ``ProjectEnvironment.default_iteration_definition`` -> SET_NULL.
   Cross-bundle case: Bundle A's env pointing at Bundle B's iteration
   definition. Uninstalling B leaves A's env intact with the default
   iteration definition nulled.
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
    ProjectEnvironmentType,
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


def _make_project_env(name: str, modifier: NeuralModifier) -> ProjectEnvironment:
    return ProjectEnvironment.objects.create(
        name=name,
        description='',
        type=ProjectEnvironmentType.objects.first(),
        status=ProjectEnvironmentStatus.objects.first(),
        genome=modifier,
    )


class NeuronEnvironmentSetNullOnBundleRemovalTest(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.modifier = _make_modifier('fk-test-env-setnull')
        self.bundle_env = _make_project_env(
            'FK Test Bundle Env', self.modifier
        )
        effector = Effector.objects.create(
            name='FK Test Effector',
            executable=Executable.objects.first(),
        )
        pathway = NeuralPathway.objects.create(
            name='FK Test Pathway', environment=self.bundle_env
        )
        self.neuron = Neuron.objects.create(
            pathway=pathway,
            effector=effector,
            environment=self.bundle_env,
        )

    def test_uninstall_nulls_environment_on_consumers(self):
        """Assert Neuron survives with environment=None after bundle uninstall."""
        self.assertEqual(self.neuron.environment_id, self.bundle_env.pk)

        loader.uninstall_bundle(self.modifier.slug)

        self.assertFalse(
            ProjectEnvironment.objects.filter(pk=self.bundle_env.pk).exists()
        )
        self.neuron.refresh_from_db()
        self.assertIsNone(self.neuron.environment_id)


class CrossBundleDefaultIterationDefinitionSetNullTest(
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
        self.env_a.save(
            update_fields=['default_iteration_definition']
        )

    def test_uninstall_b_nulls_default_iteration_definition_on_a(self):
        """Assert A's env survives with the cross-bundle pointer nulled."""
        self.assertEqual(
            self.env_a.default_iteration_definition_id, self.iter_def_b.pk
        )

        loader.uninstall_bundle(self.modifier_b.slug)

        self.assertFalse(
            IterationDefinition.objects.filter(pk=self.iter_def_b.pk).exists()
        )
        self.env_a.refresh_from_db()
        self.assertIsNone(self.env_a.default_iteration_definition_id)
        # A itself survived.
        self.assertTrue(
            ProjectEnvironment.objects.filter(pk=self.env_a.pk).exists()
        )
        self.assertTrue(
            NeuralModifier.objects.filter(pk=self.modifier_a.pk).exists()
        )
