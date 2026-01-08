import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.utils.html import escape
from hydra.models import (
    HydraHead, HydraSpell, HydraExecutable, HydraSpellbook, 
    HydraSpawn, HydraHeadStatus, HydraSpawnStatus
)
from environments.models import ProjectEnvironment

class LogUITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.env = ProjectEnvironment.objects.create(name="LogEnv", is_active=True)
        status = HydraHeadStatus.objects.create(id=1, name="Created")
        spawn_status = HydraSpawnStatus.objects.create(id=1, name="Created")
        exe = HydraExecutable.objects.create(name="Tool", slug="tool")
        spell = HydraSpell.objects.create(name="Spell", executable=exe)
        book = HydraSpellbook.objects.create(name="Book")
        spawn = HydraSpawn.objects.create(spellbook=book, status=spawn_status)
        self.head = HydraHead.objects.create(
            spawn=spawn, 
            spell=spell, 
            status=status,
            spell_log=">>> TOOL LOG OUTPUT <<<",
            execution_log="[SYSTEM] Started process 1234"
        )

    def test_log_view_tool_stream(self):
        """Verify tool log tab renders content."""
        url = reverse('hydra_head_logs', args=[self.head.id])
        # Default request (no partial arg) should return full UI
        response = self.client.get(url + "?type=tool")
        
        self.assertEqual(response.status_code, 200)
        
        # Expect escaped content
        expected = escape(">>> TOOL LOG OUTPUT <<<")
        self.assertContains(response, expected)
        
        # Expect UI structure
        self.assertContains(response, 'log-tab active') 

    def test_log_view_system_stream(self):
        url = reverse('hydra_head_logs', args=[self.head.id])
        response = self.client.get(url + "?type=system")
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "[SYSTEM] Started process 1234")