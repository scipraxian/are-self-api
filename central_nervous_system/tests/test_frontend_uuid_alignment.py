"""
Tests that frontend UUID constants (nodeConstants.ts) stay in sync with
backend model constants and fixture data.

If a test here fails, the frontend nodeConstants.ts needs updating to match.
"""

import json
import re
from pathlib import Path
from uuid import UUID

from django.test import TestCase
from rest_framework.test import APIClient

from central_nervous_system.models import (
    Effector,
    NeuralPathway,
    Neuron,
    Axon,
    Spike,
    SpikeTrain,
    EffectorContext,
)
from common.tests.common_test_case import CommonFixturesAPITestCase


# ── The canonical UUID map from the backend model ──────────────────────

BACKEND_EFFECTOR_UUIDS = {
    'BEGIN_PLAY': Effector.BEGIN_PLAY,
    'LOGIC_GATE': Effector.LOGIC_GATE,
    'LOGIC_RETRY': Effector.LOGIC_RETRY,
    'LOGIC_DELAY': Effector.LOGIC_DELAY,
    'FRONTAL_LOBE': Effector.FRONTAL_LOBE,
    'DEBUG': Effector.DEBUG,
}

# ── The same map as declared in the frontend ───────────────────────────

FRONTEND_EFFECTOR_UUIDS = {
    'BEGIN_PLAY': UUID('a74a9b1a-7326-4dff-9013-d640433b3bf7'),
    'LOGIC_GATE': UUID('3aa7a066-232a-4710-b387-a9033771e8dd'),
    'LOGIC_RETRY': UUID('644c234f-c810-494b-8339-7829a143e099'),
    'LOGIC_DELAY': UUID('0094c230-0784-4522-8e87-9c25dcab5a7f'),
    'FRONTAL_LOBE': UUID('64c0995a-cbd2-47d3-a452-e36ea4d46154'),
    'DEBUG': UUID('8eb0d85b-35f5-4095-9b10-37a2e6fefbef'),
}


class EffectorUUIDAlignmentTest(TestCase):
    """Backend model constants match the hardcoded frontend constants."""

    def test_all_backend_effector_constants_have_frontend_counterparts(self):
        """Every EFFECTOR constant on the model has a frontend entry."""
        for name, backend_uuid in BACKEND_EFFECTOR_UUIDS.items():
            self.assertIn(
                name,
                FRONTEND_EFFECTOR_UUIDS,
                f'Backend constant Effector.{name} has no frontend counterpart',
            )

    def test_frontend_uuids_match_backend(self):
        """Each frontend UUID exactly matches the backend model constant."""
        for name in BACKEND_EFFECTOR_UUIDS:
            backend = BACKEND_EFFECTOR_UUIDS[name]
            frontend = FRONTEND_EFFECTOR_UUIDS.get(name)
            self.assertEqual(
                backend,
                frontend,
                f'Effector.{name}: backend={backend} != frontend={frontend}',
            )

    def test_no_extra_frontend_constants(self):
        """Frontend doesn't declare constants the backend doesn't know about."""
        for name in FRONTEND_EFFECTOR_UUIDS:
            self.assertIn(
                name,
                BACKEND_EFFECTOR_UUIDS,
                f'Frontend constant {name} has no backend counterpart',
            )


class EffectorUUIDFixtureTest(CommonFixturesAPITestCase):
    """Fixture-loaded effectors match the model constants."""

    def test_canonical_effectors_exist_in_database(self):
        """Every canonical effector UUID actually exists after fixtures load."""
        for name, expected_uuid in BACKEND_EFFECTOR_UUIDS.items():
            exists = Effector.objects.filter(pk=expected_uuid).exists()
            self.assertTrue(
                exists,
                f'Effector.{name} ({expected_uuid}) not found in DB — '
                f'fixture data is out of sync with model constants.',
            )

    def test_begin_play_effector_name(self):
        """BEGIN_PLAY effector has a recognizable name."""
        eff = Effector.objects.get(pk=Effector.BEGIN_PLAY)
        self.assertIn('begin', eff.name.lower())

    def test_debug_effector_name(self):
        """DEBUG effector has a recognizable name."""
        eff = Effector.objects.get(pk=Effector.DEBUG)
        self.assertIn('debug', eff.name.lower())


class APIV2UUIDSerializationTest(CommonFixturesAPITestCase):
    """V2 API endpoints return UUID strings, not integers."""

    def setUp(self):
        super().setUp()
        self.client = self.test_client

    def test_effector_list_returns_uuid_ids(self):
        """GET /api/v2/effectors/ returns UUID string IDs."""
        response = self.client.get('/api/v2/effectors/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertTrue(len(results) > 0, 'No effectors returned')

        for item in results:
            # ID should be a valid UUID string, not an integer
            self.assertIsInstance(item['id'], str)
            try:
                UUID(item['id'])
            except ValueError:
                self.fail(f"Effector id '{item['id']}' is not a valid UUID")

    def test_effector_detail_returns_uuid_executable(self):
        """GET /api/v2/effectors/{uuid}/ returns UUID executable FK."""
        effector = Effector.objects.first()
        response = self.client.get(f'/api/v2/effectors/{effector.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # executable should be a UUID string
        self.assertIsInstance(data['executable'], str)
        UUID(data['executable'])  # raises if invalid

    def test_neuron_serializer_returns_uuid_effector(self):
        """Neurons in a pathway detail have UUID effector references."""
        pathway = NeuralPathway.objects.filter(neurons__isnull=False).first()
        if not pathway:
            self.skipTest('No pathways with neurons in fixtures')

        response = self.client.get(f'/api/v2/neuralpathways/{pathway.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        for neuron in data.get('neurons', []):
            self.assertIsInstance(neuron['id'], str)
            UUID(neuron['id'])

            # effector FK should be a UUID string
            if neuron.get('effector'):
                self.assertIsInstance(neuron['effector'], str)
                UUID(neuron['effector'])

    def test_axon_serializer_returns_uuid_source_target(self):
        """Axons in a pathway detail have UUID source/target references."""
        pathway = NeuralPathway.objects.filter(axons__isnull=False).first()
        if not pathway:
            self.skipTest('No pathways with axons in fixtures')

        response = self.client.get(f'/api/v2/neuralpathways/{pathway.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        for axon in data.get('axons', []):
            self.assertIsInstance(axon['id'], str)
            UUID(axon['id'])
            self.assertIsInstance(axon['source'], str)
            UUID(axon['source'])
            self.assertIsInstance(axon['target'], str)
            UUID(axon['target'])
            # type remains an integer FK
            self.assertIsInstance(axon['type'], int)

    def test_canonical_effector_accessible_by_uuid(self):
        """Each canonical effector UUID resolves via the API."""
        for name, expected_uuid in BACKEND_EFFECTOR_UUIDS.items():
            response = self.client.get(f'/api/v2/effectors/{expected_uuid}/')
            self.assertEqual(
                response.status_code,
                200,
                f'Effector.{name} ({expected_uuid}) returned {response.status_code}',
            )
            data = response.json()
            self.assertEqual(str(data['id']), str(expected_uuid))


class NodeConstantsFileParseTest(TestCase):
    """
    Parse the actual nodeConstants.ts file and verify its UUIDs match
    the backend. This catches drift even if someone edits the TS file
    without updating the Python test constants above.
    """

    NODE_CONSTANTS_PATH = (
        Path(__file__).resolve().parents[3]
        / 'are-self-ui'
        / 'src'
        / 'components'
        / 'nodeConstants.ts'
    )

    def test_node_constants_file_exists(self):
        """The frontend constants file exists at the expected path."""
        if not self.NODE_CONSTANTS_PATH.exists():
            self.skipTest(
                f'nodeConstants.ts not found at {self.NODE_CONSTANTS_PATH} '
                f'(are-self-ui repo not adjacent to are-self-api)'
            )

    def test_parsed_uuids_match_backend(self):
        """UUIDs extracted from the TS file match the backend model."""
        if not self.NODE_CONSTANTS_PATH.exists():
            self.skipTest('nodeConstants.ts not found')

        content = self.NODE_CONSTANTS_PATH.read_text()

        # Extract lines like: BEGIN_PLAY: 'a74a9b1a-...',
        pattern = re.compile(
            r"(\w+):\s*'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'"
        )
        parsed = {m.group(1): UUID(m.group(2)) for m in pattern.finditer(content)}

        self.assertTrue(len(parsed) > 0, 'No UUIDs found in nodeConstants.ts')

        for name, backend_uuid in BACKEND_EFFECTOR_UUIDS.items():
            self.assertIn(
                name,
                parsed,
                f'Effector.{name} not found in nodeConstants.ts',
            )
            self.assertEqual(
                parsed[name],
                backend_uuid,
                f'nodeConstants.ts {name}: {parsed[name]} != backend {backend_uuid}',
            )
