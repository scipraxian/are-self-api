import logging
import traceback
import json
from django.utils import timezone
from talos_parietal.synapse import OllamaClient
from talos_parietal.registry import ModelRegistry
from talos_parietal import tools as parietal_tools
from talos_frontal.utils import parse_ai_actions
from .models import (ReasoningSession, ReasoningGoal, ReasoningTurn,
                     ToolDefinition, ToolCall, ReasoningStatusID)

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """
    The Executive Driver for Reasoning Sessions.
    Moves a session forward by one cognitive turn.
    """

    def tick(self, session_id):
        """
        Executes a single turn of reasoning.
        """
        logger.info(f"[ReasoningEngine] 🧠 Ticking Session: {session_id}")

        try:
            session = ReasoningSession.objects.get(id=session_id)
        except ReasoningSession.DoesNotExist:
            logger.error(f"[ReasoningEngine] Session {session_id} not found.")
            return

        # 1. State Check
        if session.status_id not in [
                ReasoningStatusID.PENDING, ReasoningStatusID.ACTIVE
        ]:
            logger.warning(
                f"[ReasoningEngine] Session {session_id} is in terminal or inactive state: {session.status.name}. Aborting tick."
            )
            return

        if session.status_id == ReasoningStatusID.PENDING:
            session.status_id = ReasoningStatusID.ACTIVE
            session.save()

        # 2. Turn Count Check
        current_turn_count = session.turns.count()
        if current_turn_count >= session.max_turns:
            logger.warning(
                f"[ReasoningEngine] Session {session_id} reached max turns ({session.max_turns})."
            )
            session.status_id = ReasoningStatusID.MAXED_OUT
            session.save()
            return

        # 3. Goal Selection
        active_goal = session.goals.filter(
            status_id__in=[ReasoningStatusID.PENDING, ReasoningStatusID.ACTIVE
                          ]).order_by('created').first()

        goal_text = active_goal.reasoning_prompt if active_goal else session.goal
        if not active_goal:
            # Create a proxy goal if none exists to keep relations clean
            active_goal = ReasoningGoal.objects.create(
                session=session,
                reasoning_prompt=session.goal,
                status_id=ReasoningStatusID.ACTIVE)
        elif active_goal.status_id == ReasoningStatusID.PENDING:
            active_goal.status_id = ReasoningStatusID.ACTIVE
            active_goal.save()

        # 4. Context Construction
        # A. Tool Definitions
        tools = ToolDefinition.objects.all()
        tool_docs = "\n".join(
            [f"- {t.name}: {t.system_prompt_context}" for t in tools])

        system_prompt = (
            "SYSTEM: You are the Talos Build Engineer (Senior Lobe).\n"
            f"MISSION GOAL: {session.goal}\n\n"
            "INSTRUCTIONS:\n"
            "1. Analyze the context and issue commands if needed.\n"
            "2. Command Syntax: :::tool_name(arg=\"value\") :::\n"
            "3. STOP immediately after issuing a command.\n\n"
            "AVAILABLE TOOLS:\n"
            f"{tool_docs}\n\n"
            "FORMAT:\n"
            "THOUGHT: [Your reasoning]\n"
            ":::ai_tool_name(...) :::")

        # B. Recent History (Last 3 turns)
        history_turns = session.turns.order_by('-turn_number')[:3][::-1]
        history_text = ""
        for t in history_turns:
            history_text += f"\n\nTURN {t.turn_number} THOUGHT:\n{t.thought_process}"
            # Include tool results if any
            calls = t.tool_calls.all()
            if calls.exists():
                history_text += "\nSYSTEM (TOOL RESULTS):"
                for c in calls:
                    history_text += f"\nResult ({c.tool.name}): {c.result_payload}"

        # C. Project Root
        project_root = "Unknown"
        if session.spawn_link and session.spawn_link.environment and session.spawn_link.environment.project_environment:
            project_root = session.spawn_link.environment.project_environment.project_root

        user_content = (f"CURRENT TASK: {goal_text}\n"
                        f"PROJECT ROOT: {project_root}\n"
                        f"{history_text}\n\n"
                        "Waiting for next thought or command...")

        # 5. Inference
        model_name = ModelRegistry.get_model('scout_light')
        client = OllamaClient(model=model_name)

        options = {
            "num_predict": 1024,
            "temperature": 0.1,
        }

        try:
            logger.info(f"[ReasoningEngine] Querying Model: {model_name}")
            result = client.chat(system_prompt, user_content, options=options)
            ai_thought = result.get('content', '')
        except Exception as e:
            logger.error(f"[ReasoningEngine] Inference Failed: {e}")
            session.status_id = ReasoningStatusID.ERROR
            session.save()
            return

        # 6. Turn Record
        turn = ReasoningTurn.objects.create(
            session=session,
            active_goal=active_goal,
            turn_number=current_turn_count + 1,
            input_context_snapshot=user_content,
            thought_process=ai_thought,
            status_id=ReasoningStatusID.COMPLETED)

        # 7. Tool Dispatch
        actions = parse_ai_actions(ai_thought)
        if actions:
            logger.info(
                f"[ReasoningEngine] 🛠️ Dispatching {len(actions)} actions.")
            for action in actions:
                tool_name = action.get('tool')
                args = action.get('args', {})

                # Auto-inject project root for filesystem tools
                if tool_name in ['ai_read_file', 'ai_search_file'
                                ] and 'root_path' not in args:
                    args['root_path'] = project_root

                # Record ToolCall
                try:
                    tool_def = ToolDefinition.objects.get(name=tool_name)
                    call = ToolCall.objects.create(
                        turn=turn,
                        tool=tool_def,
                        arguments=json.dumps(args),
                        status_id=ReasoningStatusID.ACTIVE)
                except ToolDefinition.DoesNotExist:
                    logger.warning(
                        f"[ReasoningEngine] ❌ Unknown tool requested: {tool_name}"
                    )
                    continue

                # Execution
                try:
                    # Look up function in parietal_tools
                    tool_func = getattr(parietal_tools, tool_name, None)
                    if tool_func:
                        res = tool_func(**args)
                        call.result_payload = str(res)
                        call.status_id = ReasoningStatusID.COMPLETED
                    else:
                        call.result_payload = f"Error: Tool implementation '{tool_name}' not found in registry."
                        call.status_id = ReasoningStatusID.ERROR
                except Exception as e:
                    logger.error(
                        f"[ReasoningEngine] 💥 Tool Crash: {tool_name} -> {e}")
                    call.result_payload = f"CRASH: {str(e)}"
                    call.traceback = traceback.format_exc()
                    call.status_id = ReasoningStatusID.ERROR
                    session.status_id = ReasoningStatusID.ATTENTION_REQUIRED

                call.save()
        else:
            logger.info("[ReasoningEngine] No tool actions found in response.")

        # Update Session Metrics (Optional, if we want to bubble up tokens)
        session.save()

        logger.info(
            f"[ReasoningEngine] ✅ Tick Complete for Session {session_id}. Turn {turn.turn_number} finished."
        )

    def run_to_completion(self, session_id):
        """
        Helper to keep ticking until terminal state.
        """
        while True:
            session = ReasoningSession.objects.get(id=session_id)
            if session.status_id not in [
                    ReasoningStatusID.PENDING, ReasoningStatusID.ACTIVE
            ]:
                break

            self.tick(session_id)

            # Re-fetch to check if max turns or other error stopped it
            session.refresh_from_db()
            if session.status_id in [
                    ReasoningStatusID.MAXED_OUT, ReasoningStatusID.ERROR,
                    ReasoningStatusID.COMPLETED
            ]:
                break
