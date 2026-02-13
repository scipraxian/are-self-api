import pytest
from django.test import Client
from django.urls import reverse

from hydra.models import HydraSpawn, HydraSpawnStatus, HydraSpellbook


@pytest.mark.django_db
class TestUIPersistence:
    """
    Verifies that Mission Control UI components do not vanish during HTMX updates.
    Targeting the 'Vanishing DOM' bug.
    """

    def setup_method(self):
        self.client = Client()
        # Setup minimal DB state for valid rendering
        self.status_active = HydraSpawnStatus.objects.get_or_create(
            id=3, defaults={'name': 'Running'}
        )[0]
        self.book = HydraSpellbook.objects.create(
            name='Persistence Test Protocol'
        )
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status=self.status_active
        )

    def test_view_handles_missing_spawn_gracefully(self):
        """
        Ensures that even if the spawn vanishes (race condition), the UI doesn't implode.
        It should return a 404 (handled by HTMX default) or a 200 with error block.
        """
        # Force a failure by passing a non-existent UUID
        url = '/swimlane/00000000-0000-0000-0000-000000000000/'

        response = self.client.get(url, HTTP_HX_REQUEST='true')

        # Current logic expects 404 for get_object_or_404, which HTMX ignores (keeping old DOM).
        # OR if we handled it, it returns 200 with error.
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            content = response.content.decode()
            assert 'lane-wrapper' in content, (
                'Error response missing wrapper! DOM will vanish.'
            )
