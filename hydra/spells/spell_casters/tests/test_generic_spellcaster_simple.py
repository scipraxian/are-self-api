import pytest
from django.test import TestCase

from hydra.models import HydraExecutableType, HydraHead
from hydra.spells.spell_casters.generic_spell_caster import GenericSpellCaster


class NativeDistributorTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]

    def test_generic_spellcaster_instantiates(self):
        """Asserts that the GenericSpellCaster can be instantiated."""
        head = HydraHead.objects.create(spell_id=1)

        try:
            test_generic_spellcaster = GenericSpellCaster(head.id, None, None)
        except Exception:
            self.fail("Failed to instantiate GenericSpellCaster.")


    def test_generic_spellcaster_cast_spell(self):
        """Assert popen is called with the correct arguments.

        TODO: Mock popen and mock open

        """
        pass

    @pytest.mark.live
    def test_generic_spellcaster_live_cast(self):
        """Assert actual call uses popen and open correctly."""
        pass

    def test_generic_spellcaster_executable_router(self):
        """Assert executable router selects the correct executable."""
        head = HydraHead.objects.create(spell_id=1)
        test_generic_spellcaster = GenericSpellCaster(head.id, None, None)
        test_generic_spellcaster.executable_type = HydraExecutableType.LOCAL_PYTHON
        test_generic_spellcaster._executable_router()
        assert test_generic_spellcaster._execute_local_python == test_generic_spellcaster._executable_router

    def test_generic_spellcaster_execute_local_python(self):
        """Assert local python is called with the correct arguments."""
        pass

    def test_generic_spellcaster_post_log(self):
        """Assert post log is called with the correct arguments."""
        pass

    def test_generic_spellcaster_stream_log_with_mock(self):
        """Assert stream log is called with the correct arguments."""
        pass
    def test_generic_spellcaster_stream_log_with_live(self):
        """Assert stream log is called correctly with an actual test log file."""
        pass
    def test_generic_spellcaster_block_for_log(self):
        """Assert block for log is called with the correct arguments."""
        pass
    def test_generic_spellcaster_get_command_returns_correct_command(self):
        """Assert get command returns the correct command."""
        head = HydraHead.objects.create(spell_id=1)
        test_generic_spellcaster = GenericSpellCaster(head.id, None, None)
        test_generic_spellcaster.executable_type = HydraExecutableType.LOCAL_PYTHON
        assert test_generic_spellcaster._get_command() == ['python', 'test.py']

    def test_generic_spellcaster_resolve_switches_returns_well_formed_stripped_result(self):
        """Assert resolve switches returns a well formed list of switches."""
        head = HydraHead.objects.create(spell_id=1)
        test_generic_spellcaster = GenericSpellCaster(head.id, None, None)
        test_generic_spellcaster.executable_type = HydraExecutableType.LOCAL_PYTHON
        assert test_generic_spellcaster._resolve_switches('--test --test2') == ['--test', '--test2']

    def test_generic_spellcaster_resolve_switches_returns_empty_list_for_empty_string(self):
        """Assert resolve switches returns an empty list for an empty string."""
        head = HydraHead.objects.create(spell_id=1)
        test_generic_spellcaster = GenericSpellCaster(head.id, None, None)
        test_generic_spellcaster.executable_type = HydraExecutableType.LOCAL_PYTHON
        assert test_generic_spellcaster._resolve_switches('') == []

    def test_generic_spellcaster_process_is_killed_on_cancel(self):
        """Assert process is killed on cancel."""
        pass

    def test_generic_spellcaster_log_router_routes_to_correct_logging_type(self):
        """Assert log router routes to correct logging type, e.g. local python."""
        pass

    def test_generic_spellcaster_blocks_and_streams_local_popen_log(self):
        """Assert LOCAL_POPEN streams logs."""
        pass

