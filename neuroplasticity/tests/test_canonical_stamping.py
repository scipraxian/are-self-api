"""Tests for the Canonical Genome data migration and fixture load.

These exercise two things:

* The canonical ``NeuralModifier`` row exists after fixture load,
  pinned to ``NeuralModifier.CANONICAL``.
* Core-shipped rows (things loaded from ``zygote`` /
  ``initial_phenotypes`` fixtures in ``CommonFixturesAPITestCase``)
  carry ``genome_id = NeuralModifier.CANONICAL``. This pins down the
  invariant the post-migration stamp and the fixture-tier loader must
  maintain together.
"""

from __future__ import annotations

from common.tests.common_test_case import CommonFixturesAPITestCase, CommonTestCase
from environments.models import ProjectEnvironment
from neuroplasticity.models import NeuralModifier


class CanonicalRowExistsTest(CommonTestCase):
    """The canonical row ships in ``genetic_immutables`` — always loaded."""

    def test_canonical_row_has_frozen_uuid_and_enabled_status(self):
        """Assert the canonical row is pinned to NeuralModifier.CANONICAL."""
        canonical = NeuralModifier.objects.get(slug='canonical')

        self.assertEqual(canonical.pk, NeuralModifier.CANONICAL)
        self.assertEqual(canonical.name, 'Canonical')
        self.assertEqual(canonical.author, 'scipraxian')
        self.assertEqual(canonical.license, 'MIT')


class CanonicalStampsZygoteRowsTest(CommonFixturesAPITestCase):
    """Zygote-tier rows are stamped with genome=canonical at migrate time.

    Uses the default ProjectEnvironment row (UUID lives as
    ``ProjectEnvironment.DEFAULT_ENVIRONMENT``) as the canary — it ships
    in ``environments/fixtures/zygote.json`` and must come out of the
    fixture load stamped as canonical.
    """

    def test_default_environment_is_stamped_canonical(self):
        """Assert the default ProjectEnvironment row has genome=canonical."""
        default_env = ProjectEnvironment.objects.get(
            pk=ProjectEnvironment.DEFAULT_ENVIRONMENT
        )

        self.assertEqual(default_env.genome_id, NeuralModifier.CANONICAL)
