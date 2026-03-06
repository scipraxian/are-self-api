import pytest
from django.test import TransactionTestCase
from frontal_lobe.models import ReasoningSession, ReasoningTurn, ReasoningGoal, ReasoningStatus, ReasoningStatusID


class FrontalLobeTest(TransactionTestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
        'identity/fixtures/initial_data.json',
        'parietal_lobe/fixtures/initial_data.json',
        'prefrontal_cortex/fixtures/initial_data.json',
        'temporal_lobe/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Initializing objects for test coverage
        self.session = ReasoningSession.objects.create(total_xp=250)

    def test_reasoning_session_level_property(self):
        # Test current_level property logically
        self.assertEqual(self.session.current_level, 3)
        self.assertEqual(self.session.max_focus, 11)

    def test_reasoning_turn_efficiency_bonus(self):
        # Create a past turn to test logic
        turn_1 = ReasoningTurn.objects.create(session=self.session,
                                              turn_number=1,
                                              thought_process="Short thought")
        turn_2 = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=2,
            last_turn=turn_1,
            thought_process="Currently thinking")

        # Apply efficiency bonus based on previous turn's output string len compared to capacity
        # turn_1 thought length is 13, target_capacity = level 3 * 1000 = 3000 -> efficient
        was_efficient, status = turn_2.apply_efficiency_bonus()

        self.assertTrue(was_efficient)
        self.assertTrue("SUCCESS" in status)
        self.assertEqual(self.session.total_xp, 255)  # increased by 5

    def test_reasoning_goal_creation(self):
        goal = ReasoningGoal.objects.create(session=self.session,
                                            achieved=False,
                                            rendered_goal="Compute tests")
        self.assertEqual(str(goal), 'Goal: Compute tests...')
