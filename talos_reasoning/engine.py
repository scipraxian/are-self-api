import logging
import traceback
import json
from typing import Optional, Dict, Any, List

from django.conf import settings
from talos_parietal.synapse import OllamaClient
from talos_parietal.registry import ModelRegistry
from talos_parietal import tools as parietal_tools
from talos_frontal.utils import parse_command_string
from .models import (ReasoningSession, ReasoningGoal, ReasoningTurn,
                     ToolDefinition, ToolCall, ReasoningStatusID)

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """The Executive Driver for Reasoning Sessions.

  Refactored to be a Linear Command Console: No recursion, modular methods,
  and integer-based model constants.
  """

    def tick(self, session_id: int) -> None:
        """Performs one step of the reasoning process.

    Args:
      session_id: The ID of the session to tick.
    """
        logger.info(f"[ReasoningEngine] 🧠 Ticking Session: {session_id}")

        # 1. Load Session
        session = self._load_session(session_id)
        if not session:
            return

        # 2. Handle Goal Preemption
        self._handle_goal_preemption(session)

        # 3. Build Context
        context = self._build_context(session)
        if not context:
            return

        # 4. Query Brain
        response_text = self._query_brain(context)
        if not response_text:
            session.status_id = ReasoningStatusID.ERROR
            session.save()
            return

        # 5. Parse Action
        action = self._parse_action(response_text)

        # 6. Execute Tool (if any)
        tool_result = None
        if action:
            tool_result = self._execute_tool(action, session)

        # 7. Commit Turn
        self._commit_turn(session, response_text, context['user'], tool_result,
                          action)

        # NO RECURSION HERE.
        logger.info(
            f"[ReasoningEngine] Turn completed for session {session_id}")

    def _load_session(self, session_id: int) -> Optional[ReasoningSession]:
        """Loads and validates the session for a tick.

    Args:
      session_id: The ID of the session.

    Returns:
      The ReasoningSession object if valid, else None.
    """
        try:
            session = ReasoningSession.objects.get(id=session_id)
        except ReasoningSession.DoesNotExist:
            logger.error(f"[ReasoningEngine] Session {session_id} not found.")
            return None

        if session.status_id not in [
                ReasoningStatusID.PENDING, ReasoningStatusID.ACTIVE
        ]:
            logger.warning(
                f"[ReasoningEngine] Session {session_id} inactive. Aborting.")
            return None

        if session.turns.count() >= session.max_turns:
            logger.warning(
                f"[ReasoningEngine] Max turns reached for {session_id}")
            session.status_id = ReasoningStatusID.MAXED_OUT
            session.save()
            return None

        if session.status_id == ReasoningStatusID.PENDING:
            session.status_id = ReasoningStatusID.ACTIVE
            session.save()

        return session

    def _handle_goal_preemption(self, session: ReasoningSession) -> None:
        """Handles switching to a new PENDING goal and completing the old one.

    Args:
      session: The current reasoning session.
    """
        new_goal = session.goals.filter(
            status_id=ReasoningStatusID.PENDING).order_by('created').first()
        active_goal = session.goals.filter(
            status_id=ReasoningStatusID.ACTIVE).order_by('created').first()

        if new_goal:
            if active_goal:
                logger.info(
                    f"[ReasoningEngine] ⚡ Goal Transition: {active_goal.id} -> {new_goal.id}"
                )
                self._update_rolling_summary(session, active_goal)
                active_goal.status_id = ReasoningStatusID.COMPLETED
                active_goal.save()

            new_goal.status_id = ReasoningStatusID.ACTIVE
            new_goal.save()

    def _build_context(self, session: ReasoningSession) -> Dict[str, str]:
        """Constructs the system and user prompts for the LLM.

    Args:
      session: The current reasoning session.

    Returns:
      A dictionary with 'system' and 'user' content.
    """
        # Find active goal
        active_goal = session.goals.filter(
            status_id=ReasoningStatusID.ACTIVE).order_by('created').first()
        if not active_goal:
            # If no active goal, create one from session goal
            active_goal = ReasoningGoal.objects.create(
                session=session,
                reasoning_prompt=session.goal,
                status_id=ReasoningStatusID.ACTIVE)

        # --- MEMORY FIX: LOAD FULL SESSION HISTORY ---
        # Previously filtered by active_goal, causing amnesia.
        # Now fetches the last 15 turns of the ENTIRE session to provide context.
        history_turns = session.turns.all().order_by('-turn_number')[:15][::-1]

        history_text = ""
        if history_turns:
            history_text = "### SESSION HISTORY ###\n"
            for t in history_turns:
                # Add a marker if this turn belonged to a previous goal
                goal_context = f" (Goal: {t.active_goal.reasoning_prompt})" if t.active_goal else ""

                history_text += f"THOUGHT{goal_context}: {t.thought_process}\n"
                for call in t.tool_calls.all():
                    res_snippet = (call.result_payload[:800] + "...") if len(
                        call.result_payload) > 800 else call.result_payload
                    history_text += f"SYSTEM (Result {call.tool.name}): {res_snippet}\n"

        # Memory/Summary (Long term)
        memory_text = (
            f"### SHORT-TERM MEMORY (Summarized) ###\n"
            f"{session.rolling_context_summary or 'No summary yet.'}")

        # Tools Documentation
        tools = ToolDefinition.objects.all()
        tool_docs = "\n".join(
            [f"- {t.name}: {t.system_prompt_context}" for t in tools])

        system_prompt = (
            "SYSTEM: You are the Talos Build Engineer.\n"
            "MISSION: Fulfill the current objective using the Session History as context.\n"
            "LINEAR COMMAND MODE: You MUST use the following CLI syntax for actions.\n"
            "COMMANDS:\n"
            "1. READ_FILE: <path> [start_line]\n"
            "2. SEARCH_FILE: <path> \"<pattern>\"\n"
            "3. LIST_DIR: <path>\n\n"
            "RULES:\n"
            "- Output exactly one command per turn if an action is needed.\n"
            "- If you have the answer based on HISTORY, state it and do not use a tool.\n\n"
            "AVAILABLE TOOLS:\n"
            f"{tool_docs}")

        user_content = (
            f"{memory_text}\n\n"
            f"### CURRENT OBJECTIVE ###\n{active_goal.reasoning_prompt}\n\n"
            f"{history_text}\n\n"
            "Next action?")

        return {"system": system_prompt, "user": user_content}

    def _query_brain(self, context: Dict[str, str]) -> Optional[str]:
        """Queries the Ollama LLM.

    Args:
      context: Dictionary with 'system' and 'user' prompts.

    Returns:
      The text response from the model or None if it fails.
    """
        model_name = ModelRegistry.get_model(ModelRegistry.COMMANDER)
        client = OllamaClient(model=model_name)

        try:
            result = client.chat(context['system'],
                                 context['user'],
                                 options={"temperature": 0.1})
            return result.get('content', '')
        except Exception as e:
            logger.error(f"[ReasoningEngine] Inference Failed: {e}")
            return None

    def _parse_action(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parses the response for a command.

    Args:
      response_text: The raw response from the LLM.

    Returns:
      A dictionary with 'tool' and 'args' or None.
    """
        return parse_command_string(response_text)

    def _execute_tool(self, action: Dict[str, Any],
                      session: ReasoningSession) -> str:
        """Executes the tool and returns the result.

    Args:
      action: The tool action to perform.
      session: The current session.

    Returns:
      The tool result as a string.
    """
        tool_name = action.get('tool')
        args = action.get('args', {})

        # Project Root Resolution
        project_root = str(settings.BASE_DIR)
        if (session.spawn_link and session.spawn_link.environment and
                session.spawn_link.environment.project_environment):
            project_root = session.spawn_link.environment.project_environment.project_root

        if tool_name in ['ai_read_file', 'ai_search_file', 'ai_list_files']:
            args['root_path'] = project_root

        try:
            tool_func = getattr(parietal_tools, tool_name, None)
            if tool_func:
                if tool_name == 'ai_read_file':
                    args['max_lines'] = min(int(args.get('max_lines', 50)), 150)

                res = tool_func(**args)
                return str(res)
            else:
                return f"Error: '{tool_name}' implementation not found."
        except Exception as e:
            logger.error(f"[ReasoningEngine] Tool Crash: {tool_name} -> {e}")
            return f"CRASH: {str(e)}"

    def _commit_turn(self,
                     session: ReasoningSession,
                     thought: str,
                     context_snapshot: str,
                     tool_result: Optional[str] = None,
                     action: Optional[Dict[str, Any]] = None) -> None:
        """Saves the turn and tool call results to the database.

    Args:
      session: The active session.
      thought: The AI's thought process.
      context_snapshot: The user context snapshot.
      tool_result: The result of the tool execution (if any).
      action: The action dictionary (if any).
    """
        active_goal = session.goals.filter(
            status_id=ReasoningStatusID.ACTIVE).order_by('created').first()
        turn_number = session.turns.count() + 1

        turn = ReasoningTurn.objects.create(
            session=session,
            active_goal=active_goal,
            turn_number=turn_number,
            input_context_snapshot=context_snapshot,
            thought_process=thought,
            status_id=ReasoningStatusID.COMPLETED)

        if action and tool_result is not None:
            try:
                tool_def = ToolDefinition.objects.get(name=action['tool'])
                ToolCall.objects.create(turn=turn,
                                        tool=tool_def,
                                        arguments=json.dumps(action['args']),
                                        result_payload=tool_result,
                                        status_id=ReasoningStatusID.COMPLETED)
            except ToolDefinition.DoesNotExist:
                pass

        # Self-Summarization logic if no tool was called (Final thought)
        if not action and active_goal:
            active_goal.status_id = ReasoningStatusID.COMPLETED
            active_goal.save()
            self._update_rolling_summary(session, active_goal)

    def _update_rolling_summary(self, session: ReasoningSession,
                                goal: ReasoningGoal) -> None:
        """Asks the AI to summarize the goal's results and updates memory."""
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

        model_name = ModelRegistry.get_model(ModelRegistry.SCOUT_LIGHT)
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

    def run_to_completion(self, session_id: int) -> None:
        """Backward compatibility helper (deprecated)."""
        self.tick(session_id)
