"""``genome_slug`` is exposed on every V2 owned-model serializer.

The Modifier Garden / per-row genome chips use this read-only mirror
of the ``genome`` FK to label rows. The mixin lives in
``neuroplasticity/serializer_mixins.py`` and is layered onto every
owned-model V2 serializer.

Three representative serializers are checked end-to-end via the live
URL: Effector (CNS), Executable (environments), ToolDefinition
(parietal_lobe). Spot-check is sufficient — every consumer goes
through the same mixin.
"""

from __future__ import annotations

from common.tests.common_test_case import CommonFixturesAPITestCase

from central_nervous_system.models import Effector
from environments.models import Executable
from parietal_lobe.models import ToolDefinition


class GenomeSlugInV2SerializersTestCase(CommonFixturesAPITestCase):
    def _expected_slug(self, instance):
        return instance.genome.slug

    def test_effector_v2_includes_genome_slug(self):
        """Assert /api/v2/effectors/<id>/ returns genome_slug matching row.genome.slug."""
        effector = Effector.objects.exclude(genome__isnull=True).first()
        self.assertIsNotNone(effector, 'Need at least one Effector fixture row.')

        res = self.test_client.get('/api/v2/effectors/{0}/'.format(effector.id))

        self.assertEqual(res.status_code, 200)
        self.assertIn('genome_slug', res.json())
        self.assertEqual(res.json()['genome_slug'], self._expected_slug(effector))

    def test_executable_includes_genome_slug(self):
        """Assert /api/v2/executables/<id>/ returns genome_slug matching row.genome.slug."""
        executable = Executable.objects.exclude(genome__isnull=True).first()
        self.assertIsNotNone(
            executable, 'Need at least one Executable fixture row.'
        )

        res = self.test_client.get(
            '/api/v2/executables/{0}/'.format(executable.id)
        )

        self.assertEqual(res.status_code, 200)
        self.assertIn('genome_slug', res.json())
        self.assertEqual(
            res.json()['genome_slug'], self._expected_slug(executable)
        )

    def test_tool_definition_includes_genome_slug(self):
        """Assert /api/v2/tool-definitions/<id>/ returns genome_slug matching row.genome.slug."""
        tool = ToolDefinition.objects.exclude(genome__isnull=True).first()
        self.assertIsNotNone(
            tool, 'Need at least one ToolDefinition fixture row.'
        )

        res = self.test_client.get(
            '/api/v2/tool-definitions/{0}/'.format(tool.id)
        )

        self.assertEqual(res.status_code, 200)
        self.assertIn('genome_slug', res.json())
        self.assertEqual(res.json()['genome_slug'], self._expected_slug(tool))
