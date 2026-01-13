import logging
import traceback
import json
import os
from django.conf import settings
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
    STABILIZED VERSION (V1.1).
    """

    def tick(self, session_id):
        """
        Executes a single turn of reasoning with goal priority and context isolation.
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
                f"[ReasoningEngine] Session {session_id} inactive. Aborting.")
            return

        if session.status_id == ReasoningStatusID.PENDING:
            session.status_id = ReasoningStatusID.ACTIVE
            session.save()

        # 2. Turn Count Check
        if session.turns.count() >= session.max_turns:
            logger.warning(f"[ReasoningEngine] Max turns reached.")
            session.status_id = ReasoningStatusID.MAXED_OUT
            session.save()
            return

        # 3. GOAL SELECTION (THE FIX: INTERRUPT PRIORITY)
        # Check for NEW commands (Pending) which supersede current work.
        new_goal = session.goals.filter(
            status_id=ReasoningStatusID.PENDING
        ).order_by('created').first()

        if new_goal:
            # INTERRUPT: Retire the currently active goal
            active_goals = session.goals.filter(
                status_id=ReasoningStatusID.ACTIVE
            ).exclude(id=new_goal.id)

            if active_goals.exists():
                logger.info(
                    f"[ReasoningEngine] ⚡ Interrupting {active_goals.count()} goals for New Goal {new_goal.id}")
                active_goals.update(status_id=ReasoningStatusID.COMPLETED)

            # Activate the new goal
            active_goal = new_goal
            active_goal.status_id = ReasoningStatusID.ACTIVE
            active_goal.save()
        else:
            # Continue working on existing active goal
            active_goal = session.goals.filter(
                status_id=ReasoningStatusID.ACTIVE
            ).order_by('created').first()

        # Fallback
        if not active_goal:
            goal_text = session.goal
            active_goal = ReasoningGoal.objects.create(
                session=session,
                reasoning_prompt=goal_text,
                status_id=ReasoningStatusID.ACTIVE)
        else:
            goal_text = active_goal.reasoning_prompt

        # 4. CONTEXT ISOLATION
        # Only fetch history for the CURRENT goal to prevent loop stuckness
        history_turns = session.turns.filter(active_goal=active_goal).order_by('-turn_number')[:3][::-1]

        history_text = ""
        if history_turns:
            history_text = "### RECENT HISTORY (This Goal) ###\n"
            for t in history_turns:
                history_text += f"THOUGHT: {t.thought_process}\n"
                for call in t.tool_calls.all():
                    res_snippet = (call.result_payload[:500] + "...") if len(
                        call.result_payload) > 500 else call.result_payload
                    history_text += f"SYSTEM (Result {call.tool.name}): {res_snippet}\n"
        else:
            history_text = "(New Goal. No previous context for this specific task.)"

        # Fetch Tools
        tools = ToolDefinition.objects.all()
        tool_docs = "\n".join(
            [f"- {t.name}: {t.system_prompt_context}" for t in tools])

        system_prompt = (
            "SYSTEM: You are the Talos Build Engineer.\n"
            "MISSION: Fulfill the user's specific command IMMEDIATELY.\n"
            "RULES:\n"
            "1. Execute ONE tool call that directly addresses the CURRENT GOAL.\n"
            "2. Use RELATIVE paths (e.g. 'manage.py'). Do NOT use absolute paths.\n"
            "3. Do NOT explore or list files unless explicitly asked or you don't know the file path.\n"
            "4. Output ONLY the tool command: :::tool_name(path=\"...\") :::\n"
            "5. Do NOT chat or explain yourself.\n\n"
            "AVAILABLE TOOLS:\n"
            f"{tool_docs}\n\n"
            "THOUGHT FORMAT:\n"
            "THOUGHT: I will fulfill the request.\n"
            ":::tool_name(...) :::")
        user_content = (
            f"### CURRENT GOAL ###\n{active_goal.reasoning_prompt}\n\n"
            f"{history_text}\n\n"
            "Next action?")

        # 5. INFERENCE
        model_name = ModelRegistry.get_model('scout_light')
        client = OllamaClient(model=model_name)

        try:
            logger.info(
                f"[ReasoningEngine] Inference for Goal: {active_goal.id}")
            result = client.chat(system_prompt,
                                 user_content,
                                 options={"temperature": 0.1})
            ai_thought = result.get('content', '')
        except Exception as e:
            logger.error(f"[ReasoningEngine] Inference Failed: {e}")
            session.status_id = ReasoningStatusID.ERROR
            session.save()
            return

        # 6. TURN RECORD
        turn = ReasoningTurn.objects.create(
            session=session,
            active_goal=active_goal,
            turn_number=session.turns.count() + 1,
            input_context_snapshot=user_content,
            thought_process=ai_thought,
            status_id=ReasoningStatusID.COMPLETED)

        # 7. TOOL DISPATCH (IMPLICIT CONTEXT)
        actions = parse_ai_actions(ai_thought)

        if actions:
            logger.info(
                f"[ReasoningEngine] 🛠️ Dispatching {len(actions)} actions.")

            # Resolve Root Path once
            project_root = str(settings.BASE_DIR)
            if session.spawn_link and session.spawn_link.environment and session.spawn_link.environment.project_environment:
                project_root = session.spawn_link.environment.project_environment.project_root

            for action in actions:
                tool_name = action.get('tool')
                args = action.get('args', {})

                # Record ToolCall
                try:
                    tool_def = ToolDefinition.objects.get(name=tool_name)
                    call = ToolCall.objects.create(
                        turn=turn,
                        tool=tool_def,
                        arguments=json.dumps(args),
                        status_id=ReasoningStatusID.ACTIVE)
                except ToolDefinition.DoesNotExist:
                    logger.warning(f"AI requested unknown tool: {tool_name}")
                    continue

                # SILENT ROOT INJECTION
                if tool_name in [
                        'ai_read_file', 'ai_search_file', 'ai_list_files'
                ]:
                    args['root_path'] = project_root

                # Execution
                try:
                    tool_func = getattr(parietal_tools, tool_name, None)
                    if tool_func:
                        # Safety: Clamp max_lines for AI reads
                        if tool_name == 'ai_read_file':
                            try:
                                args['max_lines'] = min(
                                    int(args.get('max_lines', 50)), 150)
                            except (ValueError, TypeError):
                                args['max_lines'] = 50

                        res = tool_func(**args)
                        call.result_payload = str(res)
                        call.status_id = ReasoningStatusID.COMPLETED
                    else:
                        call.result_payload = f"Error: Implementation for '{tool_name}' not found."
                        call.status_id = ReasoningStatusID.ERROR
                except Exception as e:
                    logger.error(
                        f"[ReasoningEngine] Tool Crash: {tool_name} -> {e}")
                    call.result_payload = f"CRASH: {str(e)}"
                    call.traceback = traceback.format_exc()
                    call.status_id = ReasoningStatusID.ERROR
                    session.status_id = ReasoningStatusID.ATTENTION_REQUIRED

                call.save()
        else:
            logger.info("[ReasoningEngine] No tool actions found.")

        logger.info(f"[ReasoningEngine] ✅ Turn {turn.turn_number} finished.")

    def run_to_completion(self, session_id):
        """Helper to loop ticks."""
        while True:
            session = ReasoningSession.objects.get(id=session_id)
            if session.status_id not in [
                    ReasoningStatusID.PENDING, ReasoningStatusID.ACTIVE
            ]:
                break
            self.tick(session_id)
            session.refresh_from_db()
            if session.status_id in [
                    ReasoningStatusID.MAXED_OUT, ReasoningStatusID.ERROR,
                    ReasoningStatusID.COMPLETED,
                    ReasoningStatusID.ATTENTION_REQUIRED
            ]:
                break
