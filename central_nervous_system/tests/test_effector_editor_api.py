"""
Tests for the Effector Editor API endpoints (V2).

Covers:
- EffectorViewSetV2: list, retrieve (detail), create, update, partial_update, delete
- EffectorContextViewSetV2: CRUD + filtering by effector
- CNSDistributionModeViewSetV2: list, retrieve (read-only)
- ExecutableViewSet: full CRUD (POST/PUT/PATCH/DELETE)
"""

from rest_framework.test import APIClient

from common.tests.common_test_case import CommonFixturesAPITestCase
from central_nervous_system.models import (
    CNSDistributionMode,
    Effector,
    EffectorContext,
    Neuron,
    NeuralPathway,
)
from environments.models import Executable, ProjectEnvironment


class EffectorViewSetV2Test(CommonFixturesAPITestCase):
    """Tests for the upgraded EffectorViewSetV2 (ModelViewSet)."""

    def setUp(self):
        super().setUp()
        self.client = self.test_client

    def test_list_effectors(self):
        """GET /api/v2/effectors/ returns a list with light serializer fields."""
        response = self.client.get('/api/v2/effectors/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertIsInstance(results, list)
        if results:
            item = results[0]
            # Light serializer should have these keys
            self.assertIn('id', item)
            self.assertIn('name', item)
            self.assertIn('distribution_mode', item)
            # Light serializer should NOT have nested detail fields
            self.assertNotIn('executable_detail', item)

    def test_retrieve_effector_detail(self):
        """GET /api/v2/effectors/{id}/ returns the full detail serializer."""
        effector = Effector.objects.first()
        self.assertIsNotNone(effector, 'Fixtures should provide at least one Effector')

        response = self.client.get(f'/api/v2/effectors/{effector.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Detail serializer should include nested fields
        self.assertIn('executable_detail', data)
        self.assertIn('switches_detail', data)
        self.assertIn('distribution_mode_detail', data)
        self.assertIn('argument_assignments', data)
        self.assertIn('context_entries', data)
        self.assertIn('tags', data)
        self.assertIn('is_favorite', data)

        # Verify executable_detail shape
        exe = data['executable_detail']
        self.assertIn('id', exe)
        self.assertIn('name', exe)
        self.assertIn('executable', exe)

    def test_create_effector(self):
        """POST /api/v2/effectors/ creates a new effector."""
        payload = {
            'name': 'Test New Effector',
            'description': 'Created by test',
            'executable': str(Executable.BEGIN_PLAY),
            'distribution_mode': 1,
        }
        response = self.client.post(
            '/api/v2/effectors/',
            data=payload,
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['name'], 'Test New Effector')
        self.assertTrue(Effector.objects.filter(name='Test New Effector').exists())

    def test_partial_update_effector(self):
        """PATCH /api/v2/effectors/{id}/ updates selected fields."""
        effector = Effector.objects.first()
        response = self.client.patch(
            f'/api/v2/effectors/{effector.id}/',
            data={'description': 'Updated via test'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        effector.refresh_from_db()
        self.assertEqual(effector.description, 'Updated via test')

    def test_update_effector_executable_fk(self):
        """PATCH the executable FK on an effector."""
        effector = Effector.objects.first()
        exe = Executable.objects.exclude(id=effector.executable_id).first()
        if not exe:
            self.skipTest('Only one executable in fixtures')

        response = self.client.patch(
            f'/api/v2/effectors/{effector.id}/',
            data={'executable': exe.id},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        effector.refresh_from_db()
        self.assertEqual(effector.executable_id, exe.id)

    def test_delete_effector(self):
        """DELETE /api/v2/effectors/{id}/ removes the effector."""
        effector = Effector.objects.create(
            name='Disposable Effector',
            executable_id=Executable.BEGIN_PLAY,
        )
        eff_id = effector.id

        response = self.client.delete(f'/api/v2/effectors/{eff_id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Effector.objects.filter(id=eff_id).exists())


class EffectorContextViewSetV2Test(CommonFixturesAPITestCase):
    """Tests for the EffectorContextViewSetV2."""

    def setUp(self):
        super().setUp()
        self.client = self.test_client
        self.effector = Effector.objects.first()

    def test_create_context_entry(self):
        """POST /api/v2/effector-contexts/ creates a context entry."""
        payload = {
            'effector': self.effector.id,
            'key': 'test_key',
            'value': 'test_value',
        }
        response = self.client.post(
            '/api/v2/effector-contexts/',
            data=payload,
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['key'], 'test_key')
        self.assertEqual(data['value'], 'test_value')

    def test_list_context_entries_filtered(self):
        """GET /api/v2/effector-contexts/?effector={id} returns filtered results."""
        EffectorContext.objects.create(
            effector=self.effector, key='k1', value='v1'
        )
        EffectorContext.objects.create(
            effector=self.effector, key='k2', value='v2'
        )

        response = self.client.get(
            f'/api/v2/effector-contexts/?effector={self.effector.id}'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertGreaterEqual(len(results), 2)

    def test_update_context_entry(self):
        """PATCH /api/v2/effector-contexts/{id}/ updates a context entry."""
        ctx = EffectorContext.objects.create(
            effector=self.effector, key='patch_me', value='old'
        )
        response = self.client.patch(
            f'/api/v2/effector-contexts/{ctx.id}/',
            data={'value': 'new'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        ctx.refresh_from_db()
        self.assertEqual(ctx.value, 'new')

    def test_delete_context_entry(self):
        """DELETE /api/v2/effector-contexts/{id}/ removes a context entry."""
        ctx = EffectorContext.objects.create(
            effector=self.effector, key='delete_me', value='bye'
        )
        ctx_id = ctx.id
        response = self.client.delete(f'/api/v2/effector-contexts/{ctx_id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(EffectorContext.objects.filter(id=ctx_id).exists())


class CNSDistributionModeViewSetV2Test(CommonFixturesAPITestCase):
    """Tests for the distribution modes lookup endpoint."""

    def setUp(self):
        super().setUp()
        self.client = self.test_client

    def test_list_distribution_modes(self):
        """GET /api/v2/distribution-modes/ returns modes from fixtures."""
        response = self.client.get('/api/v2/distribution-modes/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0, 'Fixtures should provide distribution modes')

    def test_retrieve_distribution_mode(self):
        """GET /api/v2/distribution-modes/{id}/ returns a single mode."""
        mode = CNSDistributionMode.objects.first()
        self.assertIsNotNone(mode)
        response = self.client.get(f'/api/v2/distribution-modes/{mode.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('name', data)
        self.assertIn('description', data)


class ExecutableViewSetCRUDTest(CommonFixturesAPITestCase):
    """Tests for the upgraded ExecutableViewSet (full CRUD)."""

    def setUp(self):
        super().setUp()
        self.client = self.test_client

    def test_list_executables(self):
        """GET /api/v2/executables/ returns all executables."""
        response = self.client.get('/api/v2/executables/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_create_executable(self):
        """POST /api/v2/executables/ creates a new executable."""
        payload = {
            'name': 'Test Exe',
            'executable': '/usr/bin/test-exe',
        }
        response = self.client.post(
            '/api/v2/executables/',
            data=payload,
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['name'], 'Test Exe')
        self.assertTrue(Executable.objects.filter(name='Test Exe').exists())

    def test_update_executable(self):
        """PATCH /api/v2/executables/{id}/ updates fields."""
        exe = Executable.objects.first()
        response = self.client.patch(
            f'/api/v2/executables/{exe.id}/',
            data={'description': 'Patched'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        exe.refresh_from_db()
        self.assertEqual(exe.description, 'Patched')

    def test_delete_executable(self):
        """DELETE /api/v2/executables/{id}/ removes the executable."""
        exe = Executable.objects.create(
            name='Temp Exe',
            executable='/tmp/removeme',
        )
        exe_id = exe.id
        response = self.client.delete(f'/api/v2/executables/{exe_id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Executable.objects.filter(id=exe_id).exists())

    def test_retrieve_executable_has_nested_fields(self):
        """GET /api/v2/executables/{id}/ includes nested switch/arg details."""
        exe = Executable.objects.first()
        response = self.client.get(f'/api/v2/executables/{exe.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('switches_detail', data)
        self.assertIn('argument_assignments', data)
        self.assertIn('rendered_executable', data)


class NeuronEnvironmentAPITest(CommonFixturesAPITestCase):
    """Tests for environment and distribution_mode fields on Neuron via v2 API."""

    def setUp(self):
        super().setUp()
        self.client = self.test_client
        # Get or create a neural pathway and neuron for testing
        self.pathway = NeuralPathway.objects.first() or NeuralPathway.objects.create(
            name='Test Pathway'
        )
        self.effector = Effector.objects.first()
        self.neuron = Neuron.objects.create(
            pathway=self.pathway,
            effector=self.effector,
        )
        self.environment = ProjectEnvironment.objects.first()

    def test_neuron_retrieve_includes_environment_and_distribution_mode(self):
        """GET /api/v2/neurons/{id}/ includes environment and distribution_mode_name."""
        response = self.client.get(f'/api/v2/neurons/{self.neuron.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should have the new fields
        self.assertIn('environment', data)
        self.assertIn('environment_name', data)
        self.assertIn('distribution_mode_name', data)

    def test_neuron_patch_environment_fk(self):
        """PATCH /api/v2/neurons/{id}/ can set environment FK."""
        if not self.environment:
            self.skipTest('No ProjectEnvironment available in fixtures')

        response = self.client.patch(
            f'/api/v2/neurons/{self.neuron.id}/',
            data={'environment': str(self.environment.id)},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.neuron.refresh_from_db()
        self.assertEqual(self.neuron.environment_id, self.environment.id)

    def test_neuron_patch_environment_null(self):
        """PATCH /api/v2/neurons/{id}/ can clear environment FK (set to null)."""
        self.neuron.environment = self.environment
        self.neuron.save()

        response = self.client.patch(
            f'/api/v2/neurons/{self.neuron.id}/',
            data={'environment': None},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.neuron.refresh_from_db()
        self.assertIsNone(self.neuron.environment_id)


class NeuralPathwayEnvironmentAPITest(CommonFixturesAPITestCase):
    """Tests for environment field on NeuralPathway via v2 API."""

    def setUp(self):
        super().setUp()
        self.client = self.test_client
        self.pathway = NeuralPathway.objects.create(name='Test Pathway for Env')
        self.environment = ProjectEnvironment.objects.first()

    def test_pathway_retrieve_includes_environment(self):
        """GET /api/v2/neuralpathways/{id}/ includes environment and environment_name."""
        response = self.client.get(f'/api/v2/neuralpathways/{self.pathway.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should have the new fields
        self.assertIn('environment', data)
        self.assertIn('environment_name', data)

    def test_pathway_patch_environment_fk(self):
        """PATCH /api/v2/neuralpathways/{id}/ can set environment FK."""
        if not self.environment:
            self.skipTest('No ProjectEnvironment available in fixtures')

        response = self.client.patch(
            f'/api/v2/neuralpathways/{self.pathway.id}/',
            data={'environment': str(self.environment.id)},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.pathway.refresh_from_db()
        self.assertEqual(self.pathway.environment_id, self.environment.id)

    def test_pathway_patch_environment_null(self):
        """PATCH /api/v2/neuralpathways/{id}/ can clear environment FK (set to null)."""
        self.pathway.environment = self.environment
        self.pathway.save()

        response = self.client.patch(
            f'/api/v2/neuralpathways/{self.pathway.id}/',
            data={'environment': None},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.pathway.refresh_from_db()
        self.assertIsNone(self.pathway.environment_id)
