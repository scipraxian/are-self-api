import logging

from django.http import JsonResponse
from django.views import View

from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningGoal, ReasoningSession, ReasoningStatusID

logger = logging.getLogger(__name__)


class ChatOverrideView(View):
    """
    MANUAL OVERRIDE: Directly chat with the Reasoning Engine.
    Uses a persistent 'Manual Sandbox' session.
    """

    def post(self, request, *args, **kwargs):
        message = request.POST.get('message', '')
        # Get the session ID from the form if it exists
        session_id = request.POST.get('session_id', '')

        if not message:
            return JsonResponse({'error': 'No message provided'}, status=400)

        try:
            session = None

            # 1. TRY TO RESUME EXISTING SESSION
            if session_id:
                try:
                    session = ReasoningSession.objects.get(id=session_id)
                except ReasoningSession.DoesNotExist:
                    pass

            # 2. FALLBACK: FIND OR CREATE SANDBOX
            if not session:
                session = ReasoningSession.objects.filter(
                    goal="Manual Sandbox"
                ).order_by('-created').first()

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

            # --- INTERRUPT PROTOCOL ---
            active_goals = session.goals.filter(
                status_id__in=[ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING]
            )
            if active_goals.exists():
                active_goals.update(status_id=ReasoningStatusID.COMPLETED)

            # 3. INJECT GOAL (User Input)
            ReasoningGoal.objects.create(
                session=session,
                reasoning_prompt=message,
                status_id=ReasoningStatusID.PENDING
            )

            # 4. TICK THE ENGINE
            engine = ReasoningEngine()
            engine.tick(session.id)

            # 5. FETCH RESULT (THE FIX IS HERE)
            # We want the NEWEST turn.
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
                'session_id': str(session.id)  # Send back ID for the JS to lock onto
            })

        except Exception as e:
            logger.error(f"Chat Override Crash: {e}")
            return JsonResponse({'error': str(e)}, status=500)

    def get(self, request, *args, **kwargs):
        return render(request, 'dashboard/partials/chat_window.html')
