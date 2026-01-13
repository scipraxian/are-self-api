# FILE: C:\talos\talos_frontal\views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from talos_reasoning.models import ReasoningSession, ReasoningStatusID
from talos_reasoning.engine import ReasoningEngine
import logging

logger = logging.getLogger(__name__)


class ChatOverrideView(View):
    """
    MANUAL OVERRIDE: Directly chat with the Reasoning Engine.
    Uses a persistent 'Manual Sandbox' session.
    """

    def _get_active_session(self):
        """Helper to find the sticky manual session."""
        session = ReasoningSession.objects.filter(
            spawn_link__isnull=True
        ).order_by('-created').first()
        return session

    def post(self, request, *args, **kwargs):
        message = request.POST.get('message', '')
        session_id = request.POST.get('session_id', '')

        if not message:
            return JsonResponse({'error': 'No message provided'}, status=400)

        try:
            # 1. Resolve Session
            session = None
            if session_id:
                try:
                    session = ReasoningSession.objects.get(id=session_id)
                except ReasoningSession.DoesNotExist:
                    pass

            if not session:
                session = self._get_active_session()

            if not session:
                session = ReasoningSession.objects.create(
                    goal="Manual Sandbox",
                    status_id=ReasoningStatusID.ACTIVE,
                    max_turns=100
                )

            # Ensure session is awake
            if session.status_id in [ReasoningStatusID.COMPLETED, ReasoningStatusID.MAXED_OUT, ReasoningStatusID.ERROR]:
                session.status_id = ReasoningStatusID.ACTIVE
                session.save()

            # 2. Add Goal
            from talos_reasoning.models import ReasoningGoal

            # Retire old active goals
            session.goals.filter(
                status_id__in=[ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING]
            ).update(status_id=ReasoningStatusID.COMPLETED)

            ReasoningGoal.objects.create(
                session=session,
                reasoning_prompt=message,
                status_id=ReasoningStatusID.PENDING
            )

            # 3. Tick
            engine = ReasoningEngine()
            engine.tick(session.id)

            # 4. Response
            latest_turn = session.turns.order_by('-turn_number').first()
            response_text = ""
            model_name = "System"

            if latest_turn:
                response_text = latest_turn.thought_process
                tools = latest_turn.tool_calls.all()
                if tools.exists():
                    response_text += "\n\n--- TOOLS EXECUTED ---\n"
                    for t in tools:
                        status_icon = "✅" if t.status.name == 'Completed' else "❌"
                        response_text += f"{status_icon} {t.tool.name}\n"
                        if t.result_payload:
                            snippet = t.result_payload[:200] + "..." if len(
                                t.result_payload) > 200 else t.result_payload
                            response_text += f"   > {snippet}\n"
                model_name = "ReasoningEngine"
            else:
                response_text = "Engine ticked but produced no new turn."

            return JsonResponse({
                'response': response_text,
                'tokens_input': 0,
                'tokens_output': 0,
                'model': model_name,
                'session_id': str(session.id)
            })

        except Exception as e:
            logger.error(f"Chat Override Crash: {e}")
            return JsonResponse({'error': str(e)}, status=500)

    def get(self, request, *args, **kwargs):
        """Renders the chat window, pre-filling history from the active session."""
        session = self._get_active_session()
        history = []

        if session:
            # Reconstruct chat history from turns
            # We want chronological order (Oldest -> Newest)
            turns = session.turns.order_by('turn_number')
            for turn in turns:
                # 1. User Input (The Goal)
                if turn.active_goal:
                    history.append({
                        'type': 'user',
                        'text': turn.active_goal.reasoning_prompt
                    })

                # 2. AI Output (The Thought + Tools)
                ai_text = turn.thought_process
                tools = turn.tool_calls.all()
                if tools.exists():
                    ai_text += "\n\n--- TOOLS EXECUTED ---\n"
                    for t in tools:
                        status_icon = "✅" if t.status.name == 'Completed' else "❌"
                        ai_text += f"{status_icon} {t.tool.name}\n"
                        if t.result_payload:
                            snippet = t.result_payload[:200] + "..." if len(
                                t.result_payload) > 200 else t.result_payload
                            ai_text += f"   > {snippet}\n"

                history.append({
                    'type': 'ai',
                    'text': ai_text,
                    'model': 'ReasoningEngine'
                })

        return render(request, 'dashboard/partials/chat_window.html', {
            'session': session,
            'history': history
        })