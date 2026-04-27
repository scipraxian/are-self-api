"""``selected_for_edit`` workspace toggle on ``NeuralModifier``.

The frontend switches the active edit workspace by PATCH-ing
``selected_for_edit=true`` on the target bundle. ``NeuralModifier.save()``
clears the flag on every other row in a single atomic transaction so
exactly one bundle is selected at a time. INCUBATOR is the post-fixture
default; CANONICAL is read-only and refuses the flag with 400.
"""

from __future__ import annotations

import uuid

from rest_framework.test import APITestCase

from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from neuroplasticity.tests.test_modifier_lifecycle import (
    ModifierLifecycleTestCase,
)


class SelectedForEditTestCase(ModifierLifecycleTestCase, APITestCase):
    def _make_user_bundle(self, slug: str) -> NeuralModifier:
        """Insert a stand-in INSTALLED bundle row for selection tests."""
        return NeuralModifier.objects.create(
            slug=slug,
            name=slug,
            version='0.1.0',
            author='test',
            license='MIT',
            manifest_hash='',
            manifest_json={},
            status=NeuralModifierStatus.objects.get(
                pk=NeuralModifierStatus.INSTALLED
            ),
        )

    def test_incubator_is_selected_after_fixture_load(self):
        """Assert INCUBATOR ships with selected_for_edit=True."""
        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)
        self.assertTrue(incubator.selected_for_edit)

    def test_canonical_is_not_selected_by_default(self):
        """Assert CANONICAL ships with selected_for_edit=False."""
        canonical = NeuralModifier.objects.get(pk=NeuralModifier.CANONICAL)
        self.assertFalse(canonical.selected_for_edit)

    def test_setting_selected_clears_others(self):
        """Assert flipping a bundle's flag clears every other selected row."""
        bundle_a = self._make_user_bundle('alpha')
        bundle_b = self._make_user_bundle('beta')

        bundle_a.selected_for_edit = True
        bundle_a.save()

        bundle_a.refresh_from_db()
        bundle_b.refresh_from_db()
        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)

        self.assertTrue(bundle_a.selected_for_edit)
        self.assertFalse(bundle_b.selected_for_edit)
        self.assertFalse(incubator.selected_for_edit)

    def test_patch_switches_active_genome(self):
        """Assert PATCH selected_for_edit=true on bundle A clears bundle B."""
        bundle_a = self._make_user_bundle('alpha')
        bundle_b = self._make_user_bundle('beta')
        # Start state: B is selected.
        bundle_b.selected_for_edit = True
        bundle_b.save()

        res = self.client.patch(
            '/api/v2/neural-modifiers/{0}/'.format(bundle_a.slug),
            {'selected_for_edit': True},
            format='json',
        )

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['selected_for_edit'])
        bundle_b.refresh_from_db()
        self.assertFalse(bundle_b.selected_for_edit)

    def test_patch_canonical_returns_400(self):
        """Assert PATCH selected_for_edit=true on canonical returns 400."""
        res = self.client.patch(
            '/api/v2/neural-modifiers/{0}/'.format(
                NeuralModifier.CANONICAL_SLUG
            ),
            {'selected_for_edit': True},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn('Canonical', res.json()['detail'])
        # And the row is unchanged.
        canonical = NeuralModifier.objects.get(pk=NeuralModifier.CANONICAL)
        self.assertFalse(canonical.selected_for_edit)

    def test_patch_selected_false_on_already_false_is_noop(self):
        """Assert PATCH selected_for_edit=false on an unselected row stays unselected."""
        bundle = self._make_user_bundle('gamma')
        # bundle starts at False (default).

        res = self.client.patch(
            '/api/v2/neural-modifiers/{0}/'.format(bundle.slug),
            {'selected_for_edit': False},
            format='json',
        )

        self.assertEqual(res.status_code, 200)
        bundle.refresh_from_db()
        self.assertFalse(bundle.selected_for_edit)
        # Incubator is still selected — the no-op did not disturb it.
        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)
        self.assertTrue(incubator.selected_for_edit)

    def test_patch_unknown_field_is_ignored(self):
        """Assert read-only fields silently drop on PATCH (DRF default)."""
        bundle = self._make_user_bundle('delta')
        original_slug = bundle.slug

        res = self.client.patch(
            '/api/v2/neural-modifiers/{0}/'.format(bundle.slug),
            {'slug': 'renamed-by-attacker', 'selected_for_edit': True},
            format='json',
        )

        self.assertEqual(res.status_code, 200)
        bundle.refresh_from_db()
        self.assertEqual(bundle.slug, original_slug)
        self.assertTrue(bundle.selected_for_edit)
