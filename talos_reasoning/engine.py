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
    STABILIZED VERSION (V1.2) - Recursive Execution & Context Hygiene.
    """

    def tick(self, session_id):
        """
        Executes a single turn of reasoning with recursion and context isolation.
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

        # 2. Safety: Max Turns Check
        turn_count = session.turns.count()
        if turn_count >= session.max_turns:
            return

        is_cleanup = False
        if (turn_count + 1) >= session.max_turns:
            logger.warning(
                f"[ReasoningEngine] Max turns reached. Final cleanup.")
            session.status_id = ReasoningStatusID.MAXED_OUT
            session.save()
            is_cleanup = True

        if session.status_id == ReasoningStatusID.PENDING:
            session.status_id = ReasoningStatusID.ACTIVE
            session.save()

        # 3. GOAL SELECTION & SUMMARIZATION LOGIC
        new_goal = session.goals.filter(
            status_id=ReasoningStatusID.PENDING).order_by('created').first()

        active_goal = session.goals.filter(
            status_id=ReasoningStatusID.ACTIVE).order_by('created').first()

        if new_goal:
            # INTERRUPT: Summarize what we have so far if active_goal exists
            if active_goal:
                logger.info(
                    f"[ReasoningEngine] ⚡ Goal Transition: {active_goal.id} -> {new_goal.id}"
                )
                self._update_rolling_summary(session, active_goal)
                active_goal.status_id = ReasoningStatusID.COMPLETED
                active_goal.save()

            active_goal = new_goal
            active_goal.status_id = ReasoningStatusID.ACTIVE
            active_goal.save()

        # Fallback to Session Goal if nothing active
        if not active_goal:
            active_goal = ReasoningGoal.objects.create(
                session=session,
                reasoning_prompt=session.goal,
                status_id=ReasoningStatusID.ACTIVE)

        # 4. CONTEXT BUILDING (The Lobotomy Check)
        # History is ISOLATED to the current goal.
        history_turns = session.turns.filter(
            active_goal=active_goal).order_by('-turn_number')[:3][::-1]

        history_text = ""
        if history_turns:
            history_text = "### RAW HISTORY (Current Goal Only) ###\n"
            for t in history_turns:
                history_text += f"THOUGHT: {t.thought_process}\n"
                for call in t.tool_calls.all():
                    res_snippet = (call.result_payload[:500] + "...") if len(
                        call.result_payload) > 500 else call.result_payload
                    history_text += f"SYSTEM (Result {call.tool.name}): {res_snippet}\n"
        else:
            history_text = "(New Goal focus. No raw history yet for this objective.)"

        # Long Term Memory
        memory_text = f"### SHORT-TERM MEMORY (Session Summary) ###\n{session.rolling_context_summary or 'No summary yet.'}"

        # Fetch Tools
        tools = ToolDefinition.objects.all()
        tool_docs = "\n".join(
            [f"- {t.name}: {t.system_prompt_context}" for t in tools])

        system_prompt = (
            "SYSTEM: You are the Talos Build Engineer.\n"
            "MISSION: Fulfill the current objective. You are in AUTO-DRIVE mode.\n"
            "RULES:\n"
            "1. Tool calls trigger another tick. Pure thoughts (synthesis) stop the engine.\n"
            "2. Use RELATIVE paths.\n"
            "3. Output ONLY the tool command: :::tool_name(path=\"...\") :::\n"
            "4. If finished with the goal, provide a final synthesis thought with NO tool call.\n\n"
            "AVAILABLE TOOLS:\n"
            f"{tool_docs}")

        user_content = (
            f"{memory_text}\n\n"
            f"### CURRENT OBJECTIVE ###\n{active_goal.reasoning_prompt}\n\n"
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
            turn_number=turn_count + 1,
            input_context_snapshot=user_content,
            thought_process=ai_thought,
            status_id=ReasoningStatusID.COMPLETED)

        # 7. TOOL DISPATCH & RECURSION
        actions = parse_ai_actions(ai_thought)

        # LOOP GUARD: Deduplication (Anti-Loop)
        prev_turn = session.turns.filter(
            id__lt=turn.id).order_by('-turn_number').first()
        if actions and prev_turn:
            prev_calls = prev_turn.tool_calls.all()
            if prev_calls.exists():
                pc = prev_calls.first()
                curr_action = actions[0]
                curr_tool = curr_action.get('tool')
                curr_args = json.dumps(curr_action.get('args', {}))

                if curr_tool == pc.tool.name and curr_args == pc.arguments:
                    logger.warning(
                        f"[ReasoningEngine] Loop detected! Repeating {curr_tool}. Stopping."
                    )
                    turn.thought_process = "SYSTEM: You just ran this command. Do not repeat it. Check the history."
                    turn.save()
                    session.status_id = ReasoningStatusID.ATTENTION_REQUIRED
                    session.save()
                    return

        if actions and session.status_id != ReasoningStatusID.MAXED_OUT:
            logger.info(
                f"[ReasoningEngine] 🛠️ Dispatching {len(actions)} actions. Recursing."
            )

            project_root = str(settings.BASE_DIR)
            if session.spawn_link and session.spawn_link.environment and session.spawn_link.environment.project_environment:
                project_root = session.spawn_link.environment.project_environment.project_root

            for action in actions:
                tool_name = action.get('tool')
                args = action.get('args', {})

                try:
                    tool_def = ToolDefinition.objects.get(name=tool_name)
                    call = ToolCall.objects.create(
                        turn=turn,
                        tool=tool_def,
                        arguments=json.dumps(args),
                        status_id=ReasoningStatusID.ACTIVE)
                except ToolDefinition.DoesNotExist:
                    continue

                if tool_name in [
                        'ai_read_file', 'ai_search_file', 'ai_list_files'
                ]:
                    args['root_path'] = project_root

                try:
                    tool_func = getattr(parietal_tools, tool_name, None)
                    if tool_func:
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
                        call.result_payload = f"Error: '{tool_name}' implementation not found."
                        call.status_id = ReasoningStatusID.ERROR
                except Exception as e:
                    logger.error(
                        f"[ReasoningEngine] Tool Crash: {tool_name} -> {e}")
                    call.result_payload = f"CRASH: {str(e)}"
                    call.traceback = traceback.format_exc()
                    call.status_id = ReasoningStatusID.ERROR

                call.save()

            # RECURSE IMMEDIATELY
            self.tick(session_id)
        else:
            # SYNTHESIS (NO TOOLS)
            logger.info(
                f"[ReasoningEngine] ✅ Goal Synthesis detected. Stopping.")
            active_goal.status_id = ReasoningStatusID.COMPLETED
            active_goal.save()
            self._update_rolling_summary(session, active_goal)

    def _update_rolling_summary(self, session, goal):
        """Asks the AI to summarize the goal's results and updates memory."""
        logger.info(
            f"[ReasoningEngine] 📝 Updating rolling summary for session {session.id}"
        )

        # Fetch relevant turns for this goal
        turns = session.turns.filter(active_goal=goal).order_by('turn_number')
        if not turns.exists():
            return

        events = []
        for t in turns:
            events.append(f"Thought: {t.thought_process}")
            for call in t.tool_calls.all():
                snippet = call.result_payload[:200]
                events.append(f"Action {call.tool.name} Result: {snippet}...")

        summary_prompt = (
            "Summarize the progress and outcome of the following work in 2-3 concise sentences.\n"
            "Focus on what was discovered or performed.\n\n"
            f"WORK LOG:\n" + "\n".join(events))

        model_name = ModelRegistry.get_model('scout_light')
        client = OllamaClient(model=model_name)

        try:
            res = client.chat("SYSTEM: You are a technical summarizer.",
                              summary_prompt)
            summary = res.get('content', '').strip()

            existing = session.rolling_context_summary
            new_summary = f"{existing}\n- {summary}" if existing else f"- {summary}"
            session.rolling_context_summary = new_summary
            session.save()
        except Exception as e:
            logger.error(f"[ReasoningEngine] Summary generation failed: {e}")

    def run_to_completion(self, session_id):
        """Helper to loop ticks (now redundant but kept for compatibility)."""
        self.tick(session_id)
