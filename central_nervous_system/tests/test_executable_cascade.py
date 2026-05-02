"""FK-softening test: Effector.executable cascade chain on uninstall.

When a bundle owns an Executable, uninstalling the bundle cascades
through Effector (softened from PROTECT to CASCADE) and on to any
Neuron pointing at that Effector. A Neuron without a runnable
Effector cannot execute; cleaner to remove than to leave dangling.
"""

import shutil
import tempfile
from pathlib import Path

from django.test import override_settings

from central_nervous_system.models import (
    Effector,
    NeuralPathway,
    Neuron,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from environments.models import Executable
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus


class NeuronCascadesOnBundleExecutableDeleteTest(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        # Isolate NEURAL_MODIFIER_GRAFTS_ROOT so loader.uninstall_genome's
        # path resolution can never resolve to the real grafts/ tree.
        self._tmp_grafts_root = Path(
            tempfile.mkdtemp(prefix='fk-cascade-grafts-')
        )
        self._settings_override = override_settings(
            NEURAL_MODIFIER_GRAFTS_ROOT=str(self._tmp_grafts_root),
        )
        self._settings_override.enable()
        self.modifier = NeuralModifier.objects.create(
            name='FK Test Bundle',
            slug='fk-test-executable-cascade',
            version='1.0.0',
            author='tests',
            license='MIT',
            manifest_hash='0' * 64,
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )
        self.bundle_executable = Executable.objects.create(
            name='Bundle Executable',
            description='Executable contributed by a bundle.',
            executable='bundle_exec_stub',
            genome=self.modifier,
        )
        self.bundle_effector = Effector.objects.create(
            name='Bundle Effector',
            executable=self.bundle_executable,
            genome=self.modifier,
        )
        pathway = NeuralPathway.objects.create(name='Cascade Pathway')
        self.neuron = Neuron.objects.create(
            pathway=pathway,
            effector=self.bundle_effector,
        )

    def tearDown(self):
        self._settings_override.disable()
        shutil.rmtree(self._tmp_grafts_root, ignore_errors=True)
        super().tearDown()

    def test_uninstall_cascades_neuron_when_bundle_effector_goes(self):
        """Assert Neurons go when their bundle-owned Effector/Executable go."""
        self.assertTrue(Neuron.objects.filter(pk=self.neuron.pk).exists())

        loader.uninstall_genome(self.modifier.slug)

        self.assertFalse(
            Executable.objects.filter(pk=self.bundle_executable.pk).exists()
        )
        self.assertFalse(
            Effector.objects.filter(pk=self.bundle_effector.pk).exists()
        )
        self.assertFalse(Neuron.objects.filter(pk=self.neuron.pk).exists())
