"""``GenomeOwnedSerializerMixin`` stamps the active workspace on create.

When the request body omits ``genome``, the mixin reads the currently
``selected_for_edit=True`` ``NeuralModifier`` and stamps the new row
to that bundle. If no bundle is flagged, fall through to ``INCUBATOR``.
Explicit ``genome`` in the body always wins.

Tested through ``/api/v2/executables/`` because Executable creation has
the lightest required-field surface and exercises the mixin via
``ExecutableSerializer`` end-to-end.
"""

from __future__ import annotations

from common.tests.common_test_case import CommonFixturesAPITestCase

from environments.models import Executable
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus


def _make_user_bundle(slug: str) -> NeuralModifier:
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


class GenomeDefaultOnCreateTestCase(CommonFixturesAPITestCase):
    def test_create_without_genome_uses_incubator_by_default(self):
        """Assert with INCUBATOR selected (fixture default) a new row lands at INCUBATOR."""
        res = self.test_client.post(
            '/api/v2/executables/',
            {
                'name': 'genome-default-test',
                'executable': '/usr/bin/echo',
            },
            format='json',
        )

        self.assertEqual(res.status_code, 201, res.content)
        executable = Executable.objects.get(pk=res.json()['id'])
        self.assertEqual(executable.genome_id, NeuralModifier.INCUBATOR)

    def test_create_without_genome_uses_selected_bundle(self):
        """Assert flipping selected_for_edit moves new rows into that bundle."""
        bundle = _make_user_bundle('alpha')
        bundle.selected_for_edit = True
        bundle.save()

        res = self.test_client.post(
            '/api/v2/executables/',
            {
                'name': 'genome-selected-test',
                'executable': '/usr/bin/echo',
            },
            format='json',
        )

        self.assertEqual(res.status_code, 201, res.content)
        executable = Executable.objects.get(pk=res.json()['id'])
        self.assertEqual(executable.genome_id, bundle.id)

    def test_create_with_explicit_genome_in_body_wins(self):
        """Assert explicit ``genome`` in the request body overrides the selected default."""
        bundle = _make_user_bundle('beta')
        bundle.selected_for_edit = True
        bundle.save()
        # Pin the new row to a different bundle than the active one.
        target = _make_user_bundle('gamma')

        res = self.test_client.post(
            '/api/v2/executables/',
            {
                'name': 'genome-explicit-test',
                'executable': '/usr/bin/echo',
                'genome': str(target.id),
            },
            format='json',
        )

        self.assertEqual(res.status_code, 201, res.content)
        executable = Executable.objects.get(pk=res.json()['id'])
        self.assertEqual(executable.genome_id, target.id)

    def test_create_with_no_selected_bundle_falls_back_to_incubator(self):
        """Assert when nothing is flagged selected the row lands at INCUBATOR."""
        # Wipe the selected flag everywhere — fixture leaves INCUBATOR selected.
        NeuralModifier.objects.filter(selected_for_edit=True).update(
            selected_for_edit=False
        )

        res = self.test_client.post(
            '/api/v2/executables/',
            {
                'name': 'genome-fallback-test',
                'executable': '/usr/bin/echo',
            },
            format='json',
        )

        self.assertEqual(res.status_code, 201, res.content)
        executable = Executable.objects.get(pk=res.json()['id'])
        self.assertEqual(executable.genome_id, NeuralModifier.INCUBATOR)
