import pytest
from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import ReasoningSession, ReasoningTurn, ReasoningStatus, ReasoningStatusID
from hypothalamus.models import AIModel, LLMProvider, AIModelProvider, AIModelProviderUsageRecord

class FrontalLobeTest(CommonFixturesAPITestCase):

    def setUp(self):
        # Initializing objects for test coverage
        self.session = ReasoningSession.objects.create(total_xp=250)

    def test_reasoning_session_level_property(self):
        # Test current_level property logically
        self.assertEqual(self.session.current_level, 3)
        self.assertEqual(self.session.max_focus, 11)

    def test_reasoning_turn_efficiency_bonus(self):
        model = AIModel.objects.create(name='test-model', context_length=4096)
        provider = LLMProvider.objects.create(key='test-provider', base_url='http://test.com')
        ai_model_provider = AIModelProvider.objects.create(
            ai_model=model,
            provider=provider,
            provider_unique_model_id='test-model-id'
        )

        usage_1 = AIModelProviderUsageRecord.objects.create(
            ai_model_provider=ai_model_provider,
            ai_model=model,
            response_payload={'content': "Short thought"}
        )
        usage_2 = AIModelProviderUsageRecord.objects.create(
            ai_model_provider=ai_model_provider,
            ai_model=model,
            response_payload={'content': "Currently thinking"}
        )

        # Create a past turn to test logic
        turn_1 = ReasoningTurn.objects.create(session=self.session,
                                              turn_number=1,
                                              model_usage_record=usage_1)
        turn_2 = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=2,
            last_turn=turn_1,
            model_usage_record=usage_2)

        # Apply efficiency bonus based on previous turn's output string len compared to capacity
        # turn_1 thought length is 13, target_capacity = level 3 * 1000 = 3000 -> efficient
        was_efficient, status = turn_2.apply_efficiency_bonus()

        self.assertTrue(was_efficient)
        self.assertIn('SUCCESS', status)
        self.assertEqual(self.session.total_xp, 255)  # 250 + 5 XP bonus

    def test_efficiency_bonus_no_last_turn(self):
        """Assert efficiency bonus returns early when there is no previous turn."""
        model = AIModel.objects.create(name='test-model-2', context_length=4096)
        provider = LLMProvider.objects.first()
        ai_model_provider = AIModelProvider.objects.create(
            ai_model=model,
            provider=provider,
            provider_unique_model_id='test-model-2-id'
        )
        usage = AIModelProviderUsageRecord.objects.create(
            ai_model_provider=ai_model_provider,
            ai_model=model,
            response_payload={'content': 'Hello'}
        )
        turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            model_usage_record=usage
        )

        was_efficient, status = turn.apply_efficiency_bonus()

        self.assertFalse(was_efficient)
        self.assertEqual(status, '')

    def test_efficiency_bonus_verbose_output_fails(self):
        """Assert efficiency bonus fails when previous turn output exceeds capacity."""
        model = AIModel.objects.create(name='test-model-3', context_length=4096)
        provider = LLMProvider.objects.first()
        ai_model_provider = AIModelProvider.objects.create(
            ai_model=model,
            provider=provider,
            provider_unique_model_id='test-model-3-id'
        )
        # Level 3 = 3000 char capacity. Make a verbose response exceeding it.
        verbose_content = 'x' * 3500
        usage_1 = AIModelProviderUsageRecord.objects.create(
            ai_model_provider=ai_model_provider,
            ai_model=model,
            response_payload={'content': verbose_content}
        )
        usage_2 = AIModelProviderUsageRecord.objects.create(
            ai_model_provider=ai_model_provider,
            ai_model=model,
            response_payload={'content': 'Short'}
        )

        turn_1 = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            model_usage_record=usage_1
        )
        turn_2 = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=2,
            last_turn=turn_1,
            model_usage_record=usage_2
        )

        was_efficient, status = turn_2.apply_efficiency_bonus()

        self.assertFalse(was_efficient)
        self.assertIn('FAILED', status)
        self.assertEqual(self.session.total_xp, 250)  # unchanged
