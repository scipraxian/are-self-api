"""Canonical is invisible through the Modifier Garden viewset.

``NeuralModifier.CANONICAL`` is a system-tier row — it owns every core
fixture row but cannot be installed, uninstalled, enabled, disabled,
saved, or graphed. The viewset's ``get_queryset()`` excludes it, and
every detail action routes through ``self.get_object()`` so DRF
returns 404 for the canonical slug on every surface.
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from neuroplasticity.models import NeuralModifier
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
)


class CanonicalHiddenFromViewSetTest(ModifierLifecycleTestCase, APITestCase):
    def test_retrieve_canonical_returns_404(self):
        """Assert retrieving the canonical slug returns 404."""
        res = self.client.get(
            '/api/v2/neural-modifiers/{0}/'.format(
                NeuralModifier.CANONICAL_SLUG
            )
        )
        self.assertEqual(res.status_code, 404)

    def test_list_omits_canonical(self):
        """Assert the list endpoint never includes canonical."""
        res = self.client.get('/api/v2/neural-modifiers/')

        self.assertEqual(res.status_code, 200)
        slugs = [row['slug'] for row in res.json()]
        self.assertNotIn(NeuralModifier.CANONICAL_SLUG, slugs)

    def test_uninstall_action_404s_for_canonical(self):
        """Assert uninstall refuses canonical with 404."""
        res = self.client.post(
            '/api/v2/neural-modifiers/{0}/uninstall/'.format(
                NeuralModifier.CANONICAL_SLUG
            )
        )
        self.assertEqual(res.status_code, 404)
        # Row is still there.
        self.assertTrue(
            NeuralModifier.objects.filter(
                pk=NeuralModifier.CANONICAL
            ).exists()
        )

    def test_save_action_404s_for_canonical(self):
        """Assert save refuses canonical with 404."""
        res = self.client.post(
            '/api/v2/neural-modifiers/{0}/save/'.format(
                NeuralModifier.CANONICAL_SLUG
            )
        )
        self.assertEqual(res.status_code, 404)

    def test_graph_action_404s_for_canonical(self):
        """Assert graph refuses canonical with 404."""
        res = self.client.get(
            '/api/v2/neural-modifiers/{0}/graph/'.format(
                NeuralModifier.CANONICAL_SLUG
            )
        )
        self.assertEqual(res.status_code, 404)

    def test_uninstall_preview_action_404s_for_canonical(self):
        """Assert uninstall-preview refuses canonical with 404."""
        res = self.client.get(
            '/api/v2/neural-modifiers/{0}/uninstall-preview/'.format(
                NeuralModifier.CANONICAL_SLUG
            )
        )
        self.assertEqual(res.status_code, 404)

    def test_impact_action_404s_for_canonical(self):
        """Assert the legacy impact alias refuses canonical with 404."""
        res = self.client.get(
            '/api/v2/neural-modifiers/{0}/impact/'.format(
                NeuralModifier.CANONICAL_SLUG
            )
        )
        self.assertEqual(res.status_code, 404)
