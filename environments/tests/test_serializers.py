import pytest
from django.test import TestCase

from environments.models import (
    Executable,
    ExecutableSwitch,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
    ProjectEnvironmentStatus,
)
from environments.serializers import (
    ContextVariableSerializer,
    ExecutableSerializer,
)


@pytest.mark.django_db
class EnvironmentSerializersTest(TestCase):
    # Loads CANONICAL + INCUBATOR NeuralModifier rows so any
    # ProjectEnvironment.objects.create() call defaulting genome to
    # NeuralModifier.INCUBATOR has the FK target present in the test DB.
    fixtures = ['neuroplasticity/fixtures/genetic_immutables.json']

    def setUp(self):
        # Setup basic types
        self.status_active = ProjectEnvironmentStatus.objects.create(
            name='Active'
        )

        # Setup Environment
        self.env = ProjectEnvironment.objects.create(
            name='Test Env', status=self.status_active
        )

        # Setup Context Keys
        self.key_root = ProjectEnvironmentContextKey.objects.create(
            name='project_root'
        )

    def test_context_variable_writable(self):
        """Verify ContextVariableSerializer allows creating/updating variables."""
        data = {
            'environment': self.env.id,
            'key': self.key_root.id,
            'value': 'C:/Test/Root',
        }

        # Create
        serializer = ContextVariableSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        var = serializer.save()

        self.assertEqual(var.value, 'C:/Test/Root')
        self.assertEqual(var.key.name, 'project_root')

        # Update
        update_data = {'value': 'D:/New/Root'}
        serializer = ContextVariableSerializer(
            var, data=update_data, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_var = serializer.save()

        self.assertEqual(updated_var.value, 'D:/New/Root')

    def test_executable_serialization(self):
        """Verify ExecutableSerializer handles nested details and updates."""
        switch = ExecutableSwitch.objects.create(name='Silent', flag='-silent')
        exe = Executable.objects.create(
            name='Editor', executable='UnrealEditor.exe', log='editor.log'
        )
        exe.switches.add(switch)

        # 1. Read Check (Nested Fields)
        serializer = ExecutableSerializer(exe)
        data = serializer.data

        self.assertIn('switches_detail', data)
        self.assertEqual(len(data['switches_detail']), 1)
        self.assertEqual(data['switches_detail'][0]['flag'], '-silent')

        # 2. Write Check (Core Fields)
        update_payload = {
            'name': 'Editor (Patched)',
            'executable': 'UnrealEditor_Patched.exe',
        }

        write_serializer = ExecutableSerializer(
            exe, data=update_payload, partial=True
        )
        self.assertTrue(write_serializer.is_valid(), write_serializer.errors)
        updated_exe = write_serializer.save()

        self.assertEqual(updated_exe.name, 'Editor (Patched)')
        self.assertEqual(updated_exe.executable, 'UnrealEditor_Patched.exe')
        # Ensure switches weren't wiped
        self.assertEqual(updated_exe.switches.count(), 1)
