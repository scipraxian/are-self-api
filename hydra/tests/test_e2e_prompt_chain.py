import os

from django.core.management import call_command
from django.test import TestCase

from environments.models import ProjectEnvironment
from hydra.hydra import Hydra
from hydra.management.commands.generate_prompt_payload import (
    BLACKBOARD_RESULT_KEY,
)
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraSpellBookNodeContext,
    HydraWireType,
)


class E2EPromptChainTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # 1. Base Environment
        self.env = ProjectEnvironment.objects.get(selected=True)
        self.spell_dummy = HydraSpell.objects.get(
            pk=1
        )  # Reusing existing spells for speed

        # 2. Build the Graph
        self.book = HydraSpellbook.objects.create(
            name='E2E Prompt Chain', environment=self.env
        )

        # Node 1: The spell that says "Hello" (Simulating a build or test)
        self.node_1 = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell_dummy, is_root=True
        )

        # Node 2: The AI Prompt Builder
        self.node_2 = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell_dummy
        )

        # Connect them with a standard Flow Wire
        HydraSpellbookConnectionWire.objects.create(
            spellbook=self.book,
            source=self.node_1,
            target=self.node_2,
            type_id=HydraWireType.TYPE_FLOW,
        )

        # 3. Inject the UI Prompt Configuration into Node 2
        HydraSpellBookNodeContext.objects.create(
            node=self.node_2,
            key='prompt',
            value='AI, please analyze this output:\n{{ provenance.application_log }}',
        )

        # 4. Prepare the Execution Instance
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            status_id=HydraSpawnStatus.RUNNING,
            environment=self.env,
        )
        self.generated_file_path = None

    def tearDown(self):
        # Cleanup the physical temp file so we don't pollute the dev environment
        if self.generated_file_path and os.path.exists(
            self.generated_file_path
        ):
            os.remove(self.generated_file_path)

    def test_end_to_end_prompt_chain(self):
        """
        Validates the entire pipeline:
        Log Generation -> Provenance Linking -> Variable Resolution -> File Generation
        """

        # STEP 1: Simulate Node 1 finishing its work and capturing a log
        head_1 = HydraHead.objects.create(
            spawn=self.spawn,
            node=self.node_1,
            spell=self.spell_dummy,
            status_id=HydraHeadStatus.SUCCESS,
            application_log='HELLO AI. THE SYSTEM HAS DETECTED A FATAL EXCEPTION.',
        )

        # STEP 2: Trigger the Hydra Graph Engine to walk the wire
        engine = Hydra(spawn_id=self.spawn.id)
        engine._process_graph_triggers(head_1)

        # STEP 3: Verify the engine created Node 2 and correctly assigned the Provenance Link
        head_2 = HydraHead.objects.get(spawn=self.spawn, node=self.node_2)
        self.assertEqual(
            head_2.provenance_id, head_1.id, 'Provenance link failed!'
        )

        # STEP 4: Execute the Payload Generator (Simulating the Caster running the DJANGO executable)
        with self.assertLogs(level='INFO') as log_capture:
            call_command('generate_prompt_payload', head_id=str(head_2.id))

            # extract the path from the logs
            found_path = None
            for record in log_capture.output:
                if (
                    '::blackboard_set' in record
                    and BLACKBOARD_RESULT_KEY in record
                ):
                    parts = record.split('::')
                    if len(parts) >= 3:
                        found_path = parts[2].strip()
                        break

            self.assertIsNotNone(
                found_path, 'Did not find blackboard instruction in logs'
            )
            self.generated_file_path = found_path

        # STEP 5: Verify the Blackboard Exhale (Simulated via log check)
        # We cannot check head_2.blackboard because the log parser isn't running.
        # head_2.refresh_from_db()
        # self.assertIn(BLACKBOARD_RESULT_KEY, head_2.blackboard)
        # self.generated_file_path = head_2.blackboard[BLACKBOARD_RESULT_KEY]

        self.assertTrue(
            os.path.exists(self.generated_file_path),
            'Payload file was not created!',
        )

        # STEP 6: Verify Context Resolution (The Inception Render)
        with open(self.generated_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Did the literal prompt text come through?
        self.assertIn('AI, please analyze this output:', content)

        # Did the nested {{ provenance.application_log }} resolve correctly from Head 1?
        self.assertIn(
            'HELLO AI. THE SYSTEM HAS DETECTED A FATAL EXCEPTION.', content
        )
