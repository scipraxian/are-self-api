from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.conf import settings
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from talos_reasoning.engine import ReasoningEngine
import logging

logger = logging.getLogger(__name__)


class ChatOverrideView(View):
    """
    MANUAL OVERRIDE: Directly chat with the Reasoning Engine.
    Uses a persistent 'Manual Sandbox' session.
    """

    def post(self, request, *args, **kwargs):
        message = request.POST.get('message', '')
        if not message:
            return JsonResponse({'error': 'No message provided'}, status=400)

        try:
            # 1. FIND OR CREATE SANDBOX SESSION
            # We look for a specific session for manual testing
            session = ReasoningSession.objects.filter(
                goal="Manual Sandbox",
                status_id__in=[ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING]
            ).order_by('-created').first()

            if not session:
                session = ReasoningSession.objects.create(
                    goal="Manual Sandbox",
                    status_id=ReasoningStatusID.ACTIVE,
                    max_turns=100
                )

            # 2. INJECT GOAL (User Input)
            # This tells the engine what to do on this tick
            ReasoningGoal.objects.create(
                session=session,
                reasoning_prompt=message,
                status_id=ReasoningStatusID.PENDING
            )

            # 3. TICK THE ENGINE
            engine = ReasoningEngine()
            engine.tick(session.id)

            # 4. FETCH RESULT
            # Get the turn that was just created (the latest one)
            latest_turn = session.turns.order_by('-turn_number').last()

            response_text = ""
            model_name = "System"

            if latest_turn:
                # Basic thought
                response_text = latest_turn.thought_process

                # Append tool outputs for visibility
                tools = latest_turn.tool_calls.all()
                if tools.exists():
                    response_text += "\n\n--- TOOLS EXECUTED ---\n"
                    for t in tools:
                        status_icon = "✅" if t.status.name == 'Completed' else "❌"
                        # Show command and snippet of result
                        response_text += f"{status_icon} {t.tool.name}\n"
                        if t.result_payload:
                            snippet = t.result_payload[:200] + "..." if len(
                                t.result_payload) > 200 else t.result_payload
                            response_text += f"   > {snippet}\n"

                model_name = "ReasoningEngine"
            else:
                response_text = "Engine ticked but produced no new turn (Check logs)."

            return JsonResponse({
                'response': response_text,
                'tokens_input': 0,
                'tokens_output': 0,
                'model': model_name
            })

        except Exception as e:
            logger.error(f"Chat Override Crash: {e}")
            return JsonResponse({'error': str(e)}, status=500)

    def get(self, request, *args, **kwargs):
        return render(request, 'dashboard/partials/chat_window.html')