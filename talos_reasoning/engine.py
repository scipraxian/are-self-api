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
    """

    def tick(self, session_id):
        logger.info(f"[ReasoningEngine] 🧠 Ticking Session: {session_id}")

        try:
            session = ReasoningSession.objects.get(id=session_id)
        except ReasoningSession.DoesNotExist:
            logger.error(f"[ReasoningEngine] Session {session_id} not found.")
            return

        # 1. State Check
        if session.status_id not in [ReasoningStatusID.PENDING, ReasoningStatusID.ACTIVE]:
            logger.warning(f"[ReasoningEngine] Session {session_id} inactive. Aborting.")
            return

        if session.status_id == ReasoningStatusID.PENDING:
            session.status_id = ReasoningStatusID.ACTIVE
            session.save()

        # 2. Turn Count Check
        if session.turns.count() >= session.max_turns:
            session.status_id = ReasoningStatusID.MAXED_OUT
            session.save()
            return

        # 3. GOAL SELECTION (THE FIX: INTERRUPT PRIORITY)
        # Check for NEW commands (Pending) which supersede current work.
        new_goal = session.goals.filter(
            status_id=ReasoningStatusID.PENDING
        ).order_by('created').first()

        if new_goal:
            # Retire any currently active goal
            active_goals = session.goals.filter(
                status_id=ReasoningStatusID.ACTIVE
            ).exclude(id=new_goal.id)

            if active_goals.exists():
                logger.info(f"[ReasoningEngine] ⚡ Interrupting {active_goals.count()} goals for New Goal {new_goal.id}")
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

        # 4. Context Construction

        tools = ToolDefinition.objects.all()
        tool_docs = "\n".join([f"- {t.name}: {t.system_prompt_context}" for t in tools])

        # B. System Prompt (FIXED: REMOVED "arg=" INSTRUCTION)
        system_prompt = (
            "SYSTEM: You are the Talos Build Engineer.\n"
            "ROLE: Execute the user's specific command.\n"
            "CONTEXT: You are attached to the Project Root.\n\n"
            "INSTRUCTIONS:\n"
            "1. Syntax: :::tool_name(path=\"file\") :::\n"
            "2. Use RELATIVE paths (e.g. 'manage.py').\n"
            "3. STOP immediately after issuing a command.\n\n"
            "AVAILABLE TOOLS:\n"
            f"{tool_docs}"
        )

        # C. HISTORY FILTERING (FIXED: ISOLATION)
        # Only show history related to the CURRENT Goal.
        history_turns = session.turns.filter(active_goal=active_goal).order_by('-turn_number')[:3][::-1]

        history_text = ""
        if history_turns:
            history_text = "HISTORY (Current Task):\n"
            for t in history_turns:
                history_text += f"TURN {t.turn_number} THOUGHT:\n{t.thought_process}\n"
                for c in t.tool_calls.all():
                    history_text += f"SYSTEM (TOOL RESULTS): {c.tool.name} -> {c.result_payload[:500]}...\n"
        else:
            history_text = "(No history for this specific task. Start fresh.)"

        user_content = (
            f"### CURRENT COMMAND ###\n"
            f"{goal_text}\n"
            f"#######################\n\n"
            f"{history_text}\n\n"
            "Execute the Current Command now."
        )

        # 5. Inference
        model_name = ModelRegistry.get_model('scout_light')
        client = OllamaClient(model=model_name)

        try:
            logger.info(f"[ReasoningEngine] Querying Model: {model_name}")
            result = client.chat(system_prompt, user_content, options={"temperature": 0.1})
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
            turn_number=session.turns.count() + 1,
            input_context_snapshot=user_content,
            thought_process=ai_thought,
            status_id=ReasoningStatusID.COMPLETED
        )

        # 7. Tool Dispatch
        actions = parse_ai_actions(ai_thought)
        if actions:
            logger.info(f"[ReasoningEngine] 🛠️ Dispatching {len(actions)} actions.")

            real_project_root = None

            for action in actions:
                tool_name = action.get('tool')
                args = action.get('args', {})

                if tool_name in ['ai_read_file', 'ai_search_file', 'ai_list_files']:
                    if not real_project_root:
                        real_project_root = str(settings.BASE_DIR)
                        if session.spawn_link and session.spawn_link.environment:
                            real_project_root = session.spawn_link.environment.project_environment.project_root

                    args['root_path'] = real_project_root

                try:
                    tool_def = ToolDefinition.objects.get(name=tool_name)
                    call = ToolCall.objects.create(
                        turn=turn,
                        tool=tool_def,
                        arguments=json.dumps(args),
                        status_id=ReasoningStatusID.ACTIVE
                    )

                    tool_func = getattr(parietal_tools, tool_name, None)
                    if tool_func:
                        if tool_name == 'ai_read_file':
                            if 'max_lines' not in args: args['max_lines'] = 50
                            args['max_lines'] = min(int(args['max_lines']), 150)

                        res = tool_func(**args)
                        call.result_payload = str(res)
                        call.status_id = ReasoningStatusID.COMPLETED
                    else:
                        call.result_payload = f"Error: Tool '{tool_name}' implementation not found."
                        call.status_id = ReasoningStatusID.ERROR

                except ToolDefinition.DoesNotExist:
                    logger.warning(f"AI requested unknown tool: {tool_name}")
                    continue
                except Exception as e:
                    logger.error(f"[ReasoningEngine] Tool Crash: {tool_name} -> {e}")
                    call.result_payload = f"CRASH: {str(e)}"
                    call.traceback = traceback.format_exc()
                    call.status_id = ReasoningStatusID.ERROR
                    session.status_id = ReasoningStatusID.ATTENTION_REQUIRED

                call.save()
        else:
            logger.info("[ReasoningEngine] No tool actions found.")

        logger.info(f"[ReasoningEngine] ✅ Turn {turn.turn_number} finished.")