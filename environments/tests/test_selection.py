from django.test import TestCase

from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
)


class EnvironmentSelectionTest(TestCase):
    # Loads CANONICAL + INCUBATOR NeuralModifier rows so any
    # ProjectEnvironment.objects.create() call defaulting genome to
    # NeuralModifier.INCUBATOR has the FK target present in the test DB.
    fixtures = ['neuroplasticity/fixtures/genetic_immutables.json']

    def setUp(self):
        self.status_ok = ProjectEnvironmentStatus.objects.create(name='Ready')

        self.env1 = ProjectEnvironment.objects.create(
            name='HSH Vacancy',
            status=self.status_ok,
            available=True,
            selected=True,  # Start selected
        )

        self.env2 = ProjectEnvironment.objects.create(
            name='Project Titan',
            status=self.status_ok,
            available=True,
            selected=False,
        )

    def test_single_selection_enforcement(self):
        """Verify saving one environment as selected deselects others."""
        self.assertTrue(
            ProjectEnvironment.objects.get(pk=self.env1.pk).selected
        )

        # Select Env 2 via ORM
        self.env2.selected = True
        self.env2.save()

        # Env 1 should auto-deselect
        self.assertFalse(
            ProjectEnvironment.objects.get(pk=self.env1.pk).selected
        )
        self.assertTrue(
            ProjectEnvironment.objects.get(pk=self.env2.pk).selected
        )
