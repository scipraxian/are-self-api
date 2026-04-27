"""``PATCH /api/v2/<leaf>/<id>/`` — promote individual leaf rows directly.

Leaf models with their own ``genome`` FK are promoted directly via
PATCH on their V2 viewset. The same canonical-refusal /
non-INSTALLED-refusal / restart-on-change rules apply as on the
parent endpoints. Spans three categories:

* ``EffectorArgumentAssignment`` parented to canonical
  ``Effector.BEGIN_PLAY`` — the user-supplement-on-canonical-parent
  scenario.
* ``ExecutableArgumentAssignment`` parented to a canonical Executable
  — same shape, different FK chain.
* ``ContextVariable`` — pure leaf with no parent in the cascade tree.

Tests mock ``trigger_system_restart`` on every method that hits the
PATCH endpoint per CLAUDE.md.
"""

from __future__ import annotations

from unittest.mock import patch

from central_nervous_system.models import (
    Effector,
    EffectorArgumentAssignment,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from environments.models import (
    ContextVariable,
    Executable,
    ExecutableArgument,
    ExecutableArgumentAssignment,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
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


class EffectorArgumentAssignmentLeafTestCase(CommonFixturesAPITestCase):
    """User-added supplement hanging off canonical ``Effector.BEGIN_PLAY``."""

    def setUp(self):
        super().setUp()
        self.target_bundle = _make_bundle('eaa-target')

        argument = ExecutableArgument.objects.create(
            name='Leaf Argument', argument='--flag'
        )
        # Effector.BEGIN_PLAY is canonical-owned; the assignment itself
        # lives in INCUBATOR by default, modelling the "user added a
        # supplement to a canonical parent" scenario.
        self.assignment = EffectorArgumentAssignment.objects.create(
            effector_id=Effector.BEGIN_PLAY,
            argument=argument,
            order=1,
        )
        self._url = '/api/v2/effector-argument-assignments/{0}/'.format(
            self.assignment.id,
        )

    @patch(_PATCH_PATH)
    def test_genome_change_promotes_leaf(self, mock_restart):
        """Assert PATCH genome on the supplement promotes it to the target bundle."""
        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.genome_id, self.target_bundle.id)
        self.assertTrue(res.json().get('restart_imminent'))
        mock_restart.assert_called_once()

    @patch(_PATCH_PATH)
    def test_no_op_patch_does_not_restart(self, mock_restart):
        """Assert PATCH genome to the current value does not restart."""
        original_genome_id = self.assignment.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(original_genome_id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn('restart_imminent', res.json())
        mock_restart.assert_not_called()

    @patch(_PATCH_PATH)
    def test_patch_into_canonical_refused(self, mock_restart):
        """Assert PATCH genome=CANONICAL on the supplement returns 400."""
        original_genome_id = self.assignment.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(NeuralModifier.CANONICAL)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_patch_out_of_canonical_refused(self, mock_restart):
        """Assert PATCH on a CANONICAL-owned supplement returns 400."""
        EffectorArgumentAssignment.objects.filter(
            pk=self.assignment.pk,
        ).update(genome=NeuralModifier.CANONICAL)

        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.genome_id, NeuralModifier.CANONICAL)

    @patch(_PATCH_PATH)
    def test_patch_to_non_installed_genome_refused(self, mock_restart):
        """Assert PATCH genome to a BROKEN bundle returns 400."""
        broken = _make_broken_bundle('eaa-broken')
        original_genome_id = self.assignment.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(broken.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.genome_id, original_genome_id)


class ExecutableArgumentAssignmentLeafTestCase(CommonFixturesAPITestCase):
    """Leaf parented to a canonical Executable (Executable.PYTHON)."""

    def setUp(self):
        super().setUp()
        self.target_bundle = _make_bundle('xaa-target')

        argument = ExecutableArgument.objects.create(
            name='Leaf XArgument', argument='--xflag'
        )
        # Executable.PYTHON ships canonical; the assignment stays in INCUBATOR.
        self.assignment = ExecutableArgumentAssignment.objects.create(
            executable_id=Executable.PYTHON,
            argument=argument,
            order=1,
        )
        self._url = '/api/v2/executable-argument-assignments/{0}/'.format(
            self.assignment.id,
        )

    @patch(_PATCH_PATH)
    def test_genome_change_promotes_leaf(self, mock_restart):
        """Assert PATCH genome on the supplement promotes it to the target bundle."""
        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.genome_id, self.target_bundle.id)
        self.assertTrue(res.json().get('restart_imminent'))
        mock_restart.assert_called_once()

    @patch(_PATCH_PATH)
    def test_no_op_patch_does_not_restart(self, mock_restart):
        """Assert PATCH genome to the current value does not restart."""
        original_genome_id = self.assignment.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(original_genome_id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn('restart_imminent', res.json())
        mock_restart.assert_not_called()

    @patch(_PATCH_PATH)
    def test_patch_into_canonical_refused(self, mock_restart):
        """Assert PATCH genome=CANONICAL on the supplement returns 400."""
        original_genome_id = self.assignment.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(NeuralModifier.CANONICAL)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_patch_out_of_canonical_refused(self, mock_restart):
        """Assert PATCH on a CANONICAL-owned supplement returns 400."""
        ExecutableArgumentAssignment.objects.filter(
            pk=self.assignment.pk,
        ).update(genome=NeuralModifier.CANONICAL)

        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.genome_id, NeuralModifier.CANONICAL)

    @patch(_PATCH_PATH)
    def test_patch_to_non_installed_genome_refused(self, mock_restart):
        """Assert PATCH genome to a BROKEN bundle returns 400."""
        broken = _make_broken_bundle('xaa-broken')
        original_genome_id = self.assignment.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(broken.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.genome_id, original_genome_id)


class ContextVariableLeafTestCase(CommonFixturesAPITestCase):
    """Pure leaf — ``ContextVariable`` has no parent in the cascade tree."""

    def setUp(self):
        super().setUp()
        self.target_bundle = _make_bundle('cv-target')

        environment = ProjectEnvironment.objects.first()
        key = ProjectEnvironmentContextKey.objects.first()
        self.assertIsNotNone(
            environment, 'Need a fixture ProjectEnvironment.',
        )
        self.assertIsNotNone(
            key, 'Need a fixture ProjectEnvironmentContextKey.',
        )

        self.variable = ContextVariable.objects.create(
            environment=environment, key=key, value='leaf-value'
        )
        self._url = '/api/v2/context-variables/{0}/'.format(self.variable.id)

    @patch(_PATCH_PATH)
    def test_genome_change_promotes_leaf(self, mock_restart):
        """Assert PATCH genome on the variable promotes it to the target bundle."""
        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.variable.refresh_from_db()
        self.assertEqual(self.variable.genome_id, self.target_bundle.id)
        self.assertTrue(res.json().get('restart_imminent'))
        mock_restart.assert_called_once()

    @patch(_PATCH_PATH)
    def test_no_op_patch_does_not_restart(self, mock_restart):
        """Assert PATCH genome to the current value does not restart."""
        original_genome_id = self.variable.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(original_genome_id)},
            format='json',
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn('restart_imminent', res.json())
        mock_restart.assert_not_called()

    @patch(_PATCH_PATH)
    def test_patch_into_canonical_refused(self, mock_restart):
        """Assert PATCH genome=CANONICAL on the variable returns 400."""
        original_genome_id = self.variable.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(NeuralModifier.CANONICAL)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.variable.refresh_from_db()
        self.assertEqual(self.variable.genome_id, original_genome_id)

    @patch(_PATCH_PATH)
    def test_patch_out_of_canonical_refused(self, mock_restart):
        """Assert PATCH on a CANONICAL-owned variable returns 400."""
        ContextVariable.objects.filter(pk=self.variable.pk).update(
            genome=NeuralModifier.CANONICAL,
        )

        res = self.test_client.patch(
            self._url,
            {'genome': str(self.target_bundle.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.variable.refresh_from_db()
        self.assertEqual(self.variable.genome_id, NeuralModifier.CANONICAL)

    @patch(_PATCH_PATH)
    def test_patch_to_non_installed_genome_refused(self, mock_restart):
        """Assert PATCH genome to a BROKEN bundle returns 400."""
        broken = _make_broken_bundle('cv-broken')
        original_genome_id = self.variable.genome_id

        res = self.test_client.patch(
            self._url,
            {'genome': str(broken.id)},
            format='json',
        )

        self.assertEqual(res.status_code, 400)
        mock_restart.assert_not_called()
        self.variable.refresh_from_db()
        self.assertEqual(self.variable.genome_id, original_genome_id)
