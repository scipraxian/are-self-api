"""``PATCH /api/v2/executables/<id>/`` — promote executable + cascade children.

A genome PATCH on the executable fans out to its direct cascade
children (``ExecutableArgumentAssignment``,
``ExecutableSupplementaryFileOrPath``) inside one ``transaction.atomic``
block, then triggers the standard install / uninstall coordinated
restart.

Tests mock ``trigger_system_restart`` on every method that hits the
PATCH endpoint per CLAUDE.md.
"""

from __future__ import annotations

from unittest.mock import patch

from common.tests.common_test_case import CommonFixturesAPITestCase
from environments.models import (
    Executable,
    ExecutableArgument,
    ExecutableArgumentAssignment,
    ExecutableSupplementaryFileOrPath,
)
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus


def _make_bundle(slug: str) -> NeuralModifier:
    return NeuralModifier.objects.create(
        slug=slug,
        name=slug,
        version='0.1.0',
        author='test',
        license='MIT',
        manifest_hash='',
        manifest_json={},
        status_id=NeuralModifierStatus.INSTALLED,
    )


def _make_broken_bundle(slug: str) -> NeuralModifier:
    return NeuralModifier.objects.create(
        slug=slug,
        name=slug,
        version='0.1.0',
        author='test',
        license='MIT',
        manifest_hash='',
        manifest_json={},
        status_id=NeuralModifierStatus.BROKEN,
    )


_PATCH_PATH = (
    'neuroplasticity.serializer_mixins.trigger_system_restart'
)


class ExecutableGenomePromoteTestCase(CommonFixturesAPITestCase):
    def setUp(self):
        super().setUp()
        self.target_bundle = _make_bundle('executable-target')

        self.executable = Executable.objects.create(
            name='Promote Executable',
            description='',
            executable='dummy',
        )
        argument = ExecutableArgument.objects.create(
            name='Promote Argument', argument='--flag'
        )
        self.assignment_a = ExecutableArgumentAssignment.objects.create(
            executable=self.executable, argument=argument, order=1
        )
        self.assignment_b = ExecutableArgumentAssignment.objects.create(
            executable=self.executable, argument=argument, order=2
        )
        self.file_a = ExecutableSupplementaryFileOrPath.objects.create(
            executable=self.executable,
            name='destination_a',
            path='c:/temp/a.txt',
        )
        self.file_b = ExecutableSupplementaryFileOrPath.objects.create(
            executable=self.executable,
            name='destination_b',
            path='c:/temp/b.txt',
        )
        self._url = '/api/v2/executables/{0}/'.format(self.executable.id)

    @patch(_PATCH_PATH)
    def test_genome_change_fans_out_to_children(self, mock_restart):
        """Assert PATCH genome fans the new value to assignments and supplementary files."""
        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.executable.refresh_from_db()
        self.assertEqual(self.executable.genome_id, self.target_bundle.id)
        for child in (
            self.assignment_a,
            self.assignment_b,
            self.file_a,
            self.file_b,
        ):
            child.refresh_from_db()
            self.assertEqual(child.genome_id, self.target_bundle.id)

    @patch(_PATCH_PATH)
    def test_no_op_patch_does_not_fan_out_or_restart(self, mock_restart):
        """Assert PATCH genome to the current value does not restart or touch children."""
        original_genome_id = self.executable.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(original_genome_id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn('restart_imminent', res.json())
        mock_restart.assert_not_called()
        for child in (self.assignment_a, self.file_a):
            child.refresh_from_db()
            self.assertEqual(child.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_patch_into_canonical_refused(self, mock_restart):
        """Assert PATCH genome=CANONICAL returns 400 and leaves rows unchanged."""
        original_genome_id = self.executable.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(NeuralModifier.CANONICAL)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.executable.refresh_from_db()
        self.assertEqual(self.executable.genome_id, original_genome_id)
        for child in (self.assignment_a, self.file_a):
            child.refresh_from_db()
            self.assertEqual(child.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_patch_out_of_canonical_refused(self, mock_restart):
        """Assert PATCH on a CANONICAL-owned executable returns 400."""
        Executable.objects.filter(pk=self.executable.pk).update(
            genome=NeuralModifier.CANONICAL,
        )

        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.executable.refresh_from_db()
        self.assertEqual(self.executable.genome_id, NeuralModifier.CANONICAL)

    @patch(_PATCH_PATH)
    def test_patch_to_non_installed_genome_refused(self, mock_restart):
        """Assert PATCH genome to a BROKEN bundle returns 400."""
        broken = _make_broken_bundle('executable-broken')
        original_genome_id = self.executable.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(broken.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.executable.refresh_from_db()
        self.assertEqual(self.executable.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_response_includes_restart_imminent_when_genome_moved(
        self, mock_restart,
    ):
        """Assert response payload carries restart_imminent=True on a real move."""
        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json().get('restart_imminent'))
        mock_restart.assert_called_once()

    @patch(_PATCH_PATH)
    def test_child_in_other_bundle_picks_up_new_genome(self, mock_restart):
        """Assert children that started in a different bundle still pick up the new genome."""
        other_bundle = _make_bundle('executable-other')
        ExecutableArgumentAssignment.objects.filter(
            pk=self.assignment_b.pk,
        ).update(genome=other_bundle)
        ExecutableSupplementaryFileOrPath.objects.filter(
            pk=self.file_b.pk,
        ).update(genome=other_bundle)

        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assignment_b.refresh_from_db()
        self.file_b.refresh_from_db()
        self.assertEqual(self.assignment_b.genome_id, self.target_bundle.id)
        self.assertEqual(self.file_b.genome_id, self.target_bundle.id)

