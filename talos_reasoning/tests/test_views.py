# FILE: C:\talos\talos_reasoning\tests\test_views.py
from django.test import TestCase, Client
from django.urls import reverse
from talos_reasoning.models import ReasoningSession, ReasoningStatusID
from unittest.mock import patch


class CortexViewsTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.client = Client()
        self.session = ReasoningSession.objects.create(
            goal="Test Session",
            status_id=ReasoningStatusID.ACTIVE
        )

    def test_cortex_launch_redirects(self):
        """Launch view should redirect to the active session."""
        url = reverse('talos_reasoning:cortex_launch')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('talos_reasoning:cortex_view', args=[self.session.id]))

    def test_cortex_view_loads(self):
        """Main cortex view should render."""
        url = reverse('talos_reasoning:cortex_view', args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'talos_reasoning/cortex_view.html')

    def test_cortex_stream_partial(self):
        """Stream partial should return just the cognitive stream."""
        url = reverse('talos_reasoning:cortex_stream', args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'talos_reasoning/partials/cognitive_stream.html')

    @patch('talos_reasoning.engine.ReasoningEngine.tick')
    def test_cortex_tick_action(self, mock_tick):
        """Manual tick button should trigger engine."""
        url = reverse('talos_reasoning:cortex_tick', args=[self.session.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        mock_tick.assert_called_once_with(self.session.id)