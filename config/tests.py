"""Health probe smoke tests.

Frontend uses ``/api/v2/health/`` to flip the disconnect overlay off
during install / uninstall / move-to-genome restarts, so the contract
is: GET, no auth, no DB, plain JSON ``{"status": "ok"}``.
"""

from __future__ import annotations

from django.test import Client, TestCase


class HealthProbeTest(TestCase):
    def test_health_returns_200_ok(self):
        """Assert GET /api/v2/health/ returns 200 with status ok."""
        client = Client()
        res = client.get('/api/v2/health/')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {'status': 'ok'})

    def test_health_works_without_authentication(self):
        """Assert the unauthenticated client still gets 200."""
        # Client() with no force_login / force_authenticate.
        client = Client()
        res = client.get('/api/v2/health/')

        self.assertEqual(res.status_code, 200)

    def test_health_returns_json_content_type(self):
        """Assert the probe responds with application/json."""
        client = Client()
        res = client.get('/api/v2/health/')

        self.assertIn('application/json', res['Content-Type'])
