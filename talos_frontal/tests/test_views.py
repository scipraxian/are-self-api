from django.test import TestCase, Client
from django.urls import reverse
from talos_reasoning.models import (
    ReasoningSession, ReasoningGoal, ReasoningTurn, ReasoningStatusID
)


class ChatViewTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.client = Client()
        self.url = reverse('talos_frontal:chat_override')

        # Setup a session with history
        self.session = ReasoningSession.objects.create(
            goal="Manual Sandbox",
            status_id=ReasoningStatusID.ACTIVE
        )

        # 1. User Input (Goal)
        self.goal = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="READ_FILE: test.txt",
            status_id=ReasoningStatusID.COMPLETED
        )

        # 2. AI Output (Turn)
        ReasoningTurn.objects.create(
            session=self.session,
            active_goal=self.goal,
            turn_number=1,
            thought_process="Reading file...",
            status_id=ReasoningStatusID.COMPLETED
        )

    def test_view_returns_history(self):
        """
        Verify the view reconstructs the chat history from the DB
        and renders it into the template.
        """
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/partials/chat_window.html')

        # Verify context data
        history = response.context['history']
        self.assertEqual(len(history), 2)  # 1 User msg, 1 AI msg

        # Verify User Message
        self.assertEqual(history[0]['type'], 'user')
        self.assertEqual(history[0]['text'], 'READ_FILE: test.txt')

        # Verify AI Message
        self.assertEqual(history[1]['type'], 'ai')
        self.assertIn('Reading file...', history[1]['text'])

        # Verify HTML content (Integration check)
        self.assertContains(response, 'READ_FILE: test.txt')
        self.assertContains(response, 'Reading file...')