import os
import uuid

from django.core.management import call_command
from django.test import TestCase

from central_nervous_system.management.commands.generate_prompt_payload import (
    BLACKBOARD_RESULT_KEY,
)
from central_nervous_system.models import (
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
    NeuralPathway,
)


class GeneratePromptPayloadTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Setup minimal relational infrastructure
        self.book = NeuralPathway.objects.create(name='Payload Test Protocol')
        self.spike_train = SpikeTrain.objects.create(
            pathway=self.book, status_id=SpikeTrainStatus.CREATED
        )

        # 2. Pre-load the blackboard with a raw template and a variable to resolve
        initial_blackboard = {
            'prompt': 'Analyze this error log: {{ error_msg }}',
            'error_msg': 'Fatal Exception in PlayerController.cpp',
        }

        self.spike = Spike.objects.create(
            spike_train=self.spike_train,
            status_id=SpikeStatus.CREATED,
            blackboard=initial_blackboard,
        )
        self.generated_file_path = None

    def tearDown(self):
        # Prevent test suite from leaving physical temp files on the OS
        if self.generated_file_path and os.path.exists(
            self.generated_file_path
        ):
            os.remove(self.generated_file_path)

    def test_generate_prompt_payload_command(self):
        """
        Verify the command resolves the context, renders the string,
        logs the instruction, and creates the file.
        """
        # ACT: Execute the management command exactly as the Caster would
        with self.assertLogs(level='INFO') as log_capture:
            call_command('generate_prompt_payload', spike_id=str(self.spike.id))

            # extract the path from the logs
            found_path = None
            for record in log_capture.output:
                if (
                    '::blackboard_set' in record
                    and BLACKBOARD_RESULT_KEY in record
                ):
                    # Format: ::blackboard_set local_prompt_path::/tmp/path
                    parts = record.split('::')
                    if len(parts) >= 3:
                        found_path = parts[2].strip()
                        break

            self.assertIsNotNone(
                found_path, 'Did not find blackboard instruction in logs'
            )
            self.generated_file_path = found_path

        # Refresh is irrelevant now since command is read-only
        self.spike.refresh_from_db()

        # ASSERT 2: The physical file exists
        self.assertTrue(os.path.exists(self.generated_file_path))

        # ASSERT 3: The template was correctly rendered before saving
        with open(self.generated_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertEqual(
            content,
            'Analyze this error log: Fatal Exception in PlayerController.cpp',
        )

    def test_missing_head_graceful_exit(self):
        """Verify the command doesn't crash the worker if given a bad UUID."""
        call_command('generate_prompt_payload', spike_id=str(uuid.uuid4()))
