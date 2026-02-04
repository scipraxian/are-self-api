import uuid
from django.test import TestCase
from django.urls import resolve, reverse
from hydra.views import LaunchSpellbookView
from hydra.models import HydraSpellbook


class HydraRoutingTest(TestCase):

    def test_uuid_url_resolves(self):
        """
        Verify that a valid UUID URL resolves to the view.
        """
        test_uuid = uuid.uuid4()
        url = f'/hydra/launch/{test_uuid}/'
        resolver = resolve(url)

        self.assertEqual(resolver.func.view_class, LaunchSpellbookView)
        self.assertEqual(resolver.kwargs['spellbook_id'], test_uuid)

    def test_view_404s_on_missing_id(self):
        """
        Ensure the View returns 404 for a valid UUID format that isn't in DB.
        """
        # A random UUID that definitely isn't in the DB
        random_uuid = uuid.uuid4()

        url = reverse('hydra:hydra_launch', args=[random_uuid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'hydra/partials/error.html')
