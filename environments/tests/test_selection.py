from django.test import Client, TestCase
from django.urls import reverse

from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)


class EnvironmentSelectionTest(TestCase):
    def setUp(self):
        self.type_ue = ProjectEnvironmentType.objects.create(name='UE5')
        self.status_ok = ProjectEnvironmentStatus.objects.create(name='Ready')

        self.env1 = ProjectEnvironment.objects.create(
            name='HSH Vacancy',
            type=self.type_ue,
            status=self.status_ok,
            available=True,
            selected=True,  # Start selected
        )

        self.env2 = ProjectEnvironment.objects.create(
            name='Project Titan',
            type=self.type_ue,
            status=self.status_ok,
            available=True,
            selected=False,
        )

        self.client = Client()

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

    def test_view_selection_logic(self):
        """Verify the view performs the switch correctly."""
        url = reverse('environments:select_environment', args=[self.env2.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            ProjectEnvironment.objects.get(pk=self.env1.pk).selected
        )
        self.assertTrue(
            ProjectEnvironment.objects.get(pk=self.env2.pk).selected
        )
