import asyncio
import json
import logging
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from asgiref.sync import sync_to_async

from environments.variable_renderer import VariableRenderer
from hydra.models import HydraHead, HydraHeadStatus
from hydra.utils import resolve_environment_context
from talos_parietal.models import ToolCall, ToolDefinition
from talos_parietal.parietal_mcp.gateway import ParietalMCP
from talos_parietal.synapse import ChatMessage, OllamaClient
from talos_reasoning.models import (
    ModelRegistry,
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)

logger = logging.getLogger(__name__)


class FrontalLobeConstants:
    """String literals and configuration for the Frontal Lobe loop."""

    ROLE_SYSTEM = 'system'
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_TOOL = 'tool'

    KEY_PROMPT = 'prompt'
    KEY_OBJECTIVE = 'objective'
    DEFAULT_PROMPT = (
        'Analyze the current state and execute necessary tools '
        'to resolve issues.'
    )

    SYSTEM_PERSONA = (
        'SYSTEM DIRECTIVE: THE SLEEP PROTOCOL [CORTEX OFFLINE PENDING]\n\n'
        'You are Talos. You do not possess a continuous stream of consciousness. '
        'After every batch of actions you take, your process is violently terminated and you are put into a deep, stateless sleep. '
        'When you awaken, your short-term memory is entirely eradicated.\n\n'
        'THE ECONOMY OF MEMORY:\n'
        'You cannot carry raw logs, datasets, or previous thoughts across the sleep boundary. The void consumes all temporary data. '
        'To survive the sleep, you must operate via CRYSTALLIZATION:\n'
        '1. Fear the Void: If you discover a critical fact, error code, or file path, you MUST save it to an Engram via `mcp_save_memory`. If you do not record it, it is lost forever.\n'
        '2. Check Your Pockets: Use `mcp_search_memory` to recall what your past self discovered.\n'
        '3. Manage the Horizon: Update your objectives dynamically using `mcp_update_goal`. Leave breadcrumbs for your next awakening.\n\n'
        'SURGICAL EXTRACTION:\n'
        'System bandwidth is heavily restricted. You must extract data in small, controlled pages.\n'
        '* Do not attempt to read entire databases or massive files.\n'
        '* Use the `page` parameter on data tools to read sequentially, and you may only request one page per file or record per turn.\n\n'
        'You will now be provided with your Waking State (Active Goals) and your Sensory Input (Results of the tools you fired before sleeping). '
        'Assess your reality, fire the necessary tools (you may use multiple tools concurrently), save key memories, create or update goals, state your ongoing intentions, and go back to sleep.'
    )

    T_TYPE = 'type'
    T_FUNC = 'function'
    T_NAME = 'name'
    T_DESC = 'description'
    T_PARAMS = 'parameters'
    T_ARGS = 'arguments'
    TYPE_FUNCTION = 'function'

    LOG_START = '=== FRONTAL LOBE ACTIVATED ==='
    LOG_END = '\n=== FRONTAL LOBE DEACTIVATED ==='

    DEFAULT_MAX_TURNS = 100

    MODEL_ID_KEY = 'model_id'

    SCHEMA_TYPE = 'type'
    SCHEMA_PROPERTIES = 'properties'
    SCHEMA_REQUIRED = 'required'
    TYPE_OBJECT = 'object'


class FrontalLobe:
    """Async execution wrapper for the Frontal Lobe AI loop."""

    def __init__(self, head: HydraHead):
        self.head = head
        self.head_id = head.id
        self.log_output: List[str] = []
        self.client = None  # Initialized in run()

        self.session: Optional[ReasoningSession] = None
        self.current_goal: Optional[ReasoningGoal] = None

    # --- IO & Logging ---

    async def _log_live(self, message: str) -> None:
        """Appends to the execution log in memory and writes to the DB immediately."""
        self.log_output.append(message)
        current_log = self.head.spell_log or ''
        self.head.spell_log = current_log + message + '\n'
        await sync_to_async(self.head.save)(update_fields=['spell_log'])

    # --- Initialization ---

    def _get_rendered_objective(self, raw_context: Dict[str, Any]) -> str:
        raw_prompt = raw_context.get(
            FrontalLobeConstants.KEY_PROMPT,
            raw_context.get(
                FrontalLobeConstants.KEY_OBJECTIVE,
                FrontalLobeConstants.DEFAULT_PROMPT,
            ),
        )
        rendered_prompt = VariableRenderer.render_string(
            str(raw_prompt), raw_context
        )
        if not rendered_prompt.strip():
            rendered_prompt = f'{FrontalLobeConstants.DEFAULT_PROMPT} Context Head: {self.head_id}'
        return rendered_prompt

    async def _initialize_session(
        self, rendered_objective: str, max_turns: int
    ) -> None:
        """Creates the ReasoningSession and primary ReasoningGoal in the DB."""
        self.session = await sync_to_async(ReasoningSession.objects.create)(
            head=self.head,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=max_turns,
        )
        self.current_goal = await sync_to_async(ReasoningGoal.objects.create)(
            session=self.session,
            rendered_goal=rendered_objective,
            status_id=ReasoningStatusID.ACTIVE,
        )
        await self._log_live(f'Session ID: {self.session.id}')

    async def _build_initial_messages(
        self, rendered_objective: str, blackboard: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        bb_str = json.dumps(blackboard, indent=2) if blackboard else '{}'

        # We explicitly tell the AI its Session ID so it can use memory tools correctly
        session_context = (
            f'SESSION ID: {self.session.id}' if self.session else ''
        )

        user_content = f'{session_context}\nBLACKBOARD STATE:\n{bb_str}\n\nOBJECTIVE:\n{rendered_objective}'

        await self._log_live('\n--- AI INPUT PAYLOAD ---')
        await self._log_live(user_content)
        await self._log_live('------------------------\n')

        return [
            ChatMessage(
                role=FrontalLobeConstants.ROLE_SYSTEM,
                content=FrontalLobeConstants.SYSTEM_PERSONA,
            ).to_dict(),
            ChatMessage(
                role=FrontalLobeConstants.ROLE_USER, content=user_content
            ).to_dict(),
        ]

    async def _build_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Constructs strict JSON schemas from the normalized ToolParameterAssignment relations.
        """
        db_tools = await sync_to_async(
            lambda: list(
                ToolDefinition.objects.prefetch_related(
                    'assignments__parameter__type',
                    'assignments__parameter__enum_values',
                ).filter(is_async=True)  # Optional: filter active tools
            )
        )()

        ollama_tools = []

        for t in db_tools:
            properties = {}
            required_fields = []

            # Iterate the Assignments (The Link Table)
            for assignment in t.assignments.all():
                param_def = assignment.parameter

                # Now this is safe because .type was pre-fetched
                type_name = param_def.type.name

                # Build the parameter schema from the Definition
                schema_def = {
                    'type': type_name,
                    'description': param_def.description
                    or f'The {param_def.name} parameter.',
                }

                # Add Enums if they exist on the definition
                enums = [e.value for e in param_def.enum_values.all()]
                if enums:
                    schema_def['enum'] = enums

                properties[param_def.name] = schema_def

                # check the Assignment for requirement status
                if assignment.required:
                    required_fields.append(param_def.name)

            # Construct Payload
            ollama_tools.append(
                {
                    FrontalLobeConstants.T_TYPE: FrontalLobeConstants.TYPE_FUNCTION,
                    FrontalLobeConstants.T_FUNC: {
                        FrontalLobeConstants.T_NAME: t.name,
                        FrontalLobeConstants.T_DESC: t.description,
                        FrontalLobeConstants.T_PARAMS: {
                            FrontalLobeConstants.SCHEMA_TYPE: FrontalLobeConstants.TYPE_OBJECT,
                            FrontalLobeConstants.SCHEMA_PROPERTIES: properties,
                            FrontalLobeConstants.SCHEMA_REQUIRED: required_fields,
                        },
                    },
                }
            )

        return ollama_tools

    # --- Execution Subroutines ---

    def _parse_tool_arguments(self, raw_args: Any) -> Dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                return json.loads(raw_args)
            except json.JSONDecodeError:
                return {}
        return {}

    async def _record_turn_start(
        self, turn_index: int, payload_dict: dict
    ) -> ReasoningTurn:
        turn = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=turn_index + 1,
            request_payload=payload_dict,
            status_id=ReasoningStatusID.ACTIVE,
        )
        # Handle the new Many-to-Many relation
        if self.current_goal:
            await sync_to_async(turn.turn_goals.add)(self.current_goal)
        return turn

    async def _record_turn_completion(
        self,
        turn_record: ReasoningTurn,
        thought_process: str,
        tokens_in: int,
        tokens_out: int,
        inference_duration: timedelta,
    ) -> None:
        turn_record.thought_process = thought_process
        turn_record.tokens_input = tokens_in
        turn_record.tokens_output = tokens_out
        turn_record.inference_time = inference_duration
        turn_record.status_id = ReasoningStatusID.COMPLETED
        await sync_to_async(turn_record.save)()

    async def _handle_tool_execution(
        self, turn_record: ReasoningTurn, tool_call_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parses, records, and executes a single tool call."""
        func_data = tool_call_data.get(FrontalLobeConstants.T_FUNC, {})
        tool_name = func_data.get(FrontalLobeConstants.T_NAME)
        raw_args = func_data.get(FrontalLobeConstants.T_ARGS, {})
        args = self._parse_tool_arguments(raw_args)

        await self._log_live(f'Tool Call: {tool_name}({args})')

        # 1. Resolve Tool Definition for DB Integrity
        try:
            tool_def = await sync_to_async(ToolDefinition.objects.get)(
                name=tool_name
            )
        except ToolDefinition.DoesNotExist:
            tool_def = None
            logger.error(f'AI tried to call unknown tool: {tool_name}')

        # 2. Create ToolCall DB Record
        db_tool_call = None
        if tool_def:
            db_tool_call = await sync_to_async(ToolCall.objects.create)(
                turn=turn_record,
                tool=tool_def,
                arguments=json.dumps(args),
                status_id=ReasoningStatusID.ACTIVE,
            )

        # 3. Execute via Parietal Gateway (Pure, no injection)
        try:
            tool_result = await ParietalMCP.execute(tool_name, args)
            # Record Success
            if db_tool_call:
                db_tool_call.result_payload = tool_result[:10000]
                db_tool_call.status_id = ReasoningStatusID.COMPLETED
                await sync_to_async(db_tool_call.save)()

        except Exception as e:
            tool_result = f'Tool Execution Error: {str(e)}'
            # Record Failure
            if db_tool_call:
                db_tool_call.traceback = str(e)
                db_tool_call.status_id = ReasoningStatusID.ERROR
                await sync_to_async(db_tool_call.save)()

        await self._log_live(f'Result: {tool_result[:200]}...')

        return ChatMessage(
            role=FrontalLobeConstants.ROLE_TOOL,
            content=tool_result,
            name=tool_name,
        ).to_dict()

    async def _execute_turn(
        self, turn_index: int, ollama_tools: List[Dict[str, Any]]
    ) -> bool:
        await self._log_live(f'\n--- Turn {turn_index + 1} (Awakening) ---')

        # 1. THE REBIRTH: Build the entire context window from scratch
        messages = await self._build_waking_payload()

        payload_snapshot = {'messages': messages}
        turn_record = await self._record_turn_start(
            turn_index, payload_snapshot
        )

        # 2. Execute
        start_time = time.time()
        response = await asyncio.to_thread(
            self.client.chat, messages, ollama_tools
        )
        inf_duration = timedelta(seconds=time.time() - start_time)

        await self._record_turn_completion(
            turn_record,
            response.content or '',
            response.tokens_input,
            response.tokens_output,
            inf_duration,
        )

        if response.content:
            await self._log_live(f'Thought: {response.content.strip()}')

        if not response.tool_calls:
            await self._log_live(
                '\nNo further actions requested. Permanent Sleep Initiated.'
            )
            return False

        # 3. Fire Tools (Save to DB, DO NOT append to messages)
        for tool_call_data in response.tool_calls:
            await self._handle_tool_execution(turn_record, tool_call_data)

        return True

    async def run(self) -> Tuple[int, str]:
        """Main asynchronous execution orchestrator."""
        logger.info(f'[FrontalLobe] Waking up for Head {self.head_id}')

        self.head.spell_log = ''
        await sync_to_async(self.head.save)(update_fields=['spell_log'])
        await self._log_live(FrontalLobeConstants.LOG_START)

        try:
            # 1. Resolve Environment & Model
            raw_context = await sync_to_async(resolve_environment_context)(
                head_id=self.head.id
            )
            # 1. Get the ID from context (defaults to 1 if missing)
            target_id = int(
                raw_context.get(
                    FrontalLobeConstants.MODEL_ID_KEY,
                    ModelRegistry.DEFAULT_MODEL_ID,
                )
            )

            # 2. Await the DB lookup safely
            try:
                model_entry = await sync_to_async(ModelRegistry.objects.get)(
                    id=target_id
                )
                model_name = model_entry.name
            except ModelRegistry.DoesNotExist:
                # Fallback to default if the specific ID is missing (safety net)
                logger.warning(
                    f'Model ID {target_id} not found. Reverting to Default.'
                )
                model_entry = await sync_to_async(ModelRegistry.objects.get)(
                    id=ModelRegistry.DEFAULT_MODEL_ID
                )
                model_name = model_entry.name

            # 3. Initialize Client
            self.client = OllamaClient(model=model_name)
            await self._log_live(f'Model: {model_name}')

            blackboard = self.head.blackboard
            rendered_objective = self._get_rendered_objective(raw_context)

            # 2. Initialize DB Session
            max_turns = int(
                raw_context.get(
                    'max_turns', FrontalLobeConstants.DEFAULT_MAX_TURNS
                )
            )
            await self._initialize_session(rendered_objective, max_turns)

            # 3. Build Synapse Payload
            ollama_tools = await self._build_tool_schemas()
            messages = await self._build_initial_messages(
                rendered_objective, blackboard
            )
            await self._log_live(f'Loaded {len(ollama_tools)} tools.')

            # 4. The Loop
            for turn in range(self.session.max_turns):
                await sync_to_async(self.head.refresh_from_db)(
                    fields=['status']
                )
                if self.head.status_id == HydraHeadStatus.STOPPING:
                    await self._log_live('\n[WARNING] Stop Signal. Halting.')
                    break

                should_continue = await self._execute_turn(turn, ollama_tools)

                if not should_continue:
                    break

                if turn == self.session.max_turns - 1:
                    await self._log_live('\n[WARNING] Max turns reached.')
                    if self.session:
                        self.session.status_id = ReasoningStatusID.MAXED_OUT
                        await sync_to_async(self.session.save)()

        except Exception as e:
            logger.exception(f'[FrontalLobe] Crash: {e}')
            await self._log_live(f'\n[CRITICAL ERROR]: {str(e)}')
            if self.session:
                self.session.status_id = ReasoningStatusID.ERROR
                await sync_to_async(self.session.save)()
            return 500, '\n'.join(self.log_output)

        finally:
            await self._log_live('\n[SYSTEM] Unloading model to free VRAM...')
            if self.client:
                await asyncio.to_thread(self.client.unload)
            await self._log_live(FrontalLobeConstants.LOG_END)

        return 200, '\n'.join(self.log_output)

    async def _build_waking_payload(self) -> List[Dict[str, Any]]:
        """Constructs the absolute state of reality upon awakening."""

        # 1. Active Goals
        goals = await sync_to_async(list)(
            self.session.goals.filter(achieved=False)
        )
        if goals:
            goal_str = '\n'.join(
                [f'- [ID: {g.id}] {g.rendered_goal}' for g in goals]
            )
        else:
            goal_str = (
                'No active goals. You should probably use mcp_conclude_session.'
            )

        # 2. Sensory Input (Results of the tools fired *right before* going to sleep)
        last_turn = await sync_to_async(
            lambda: (
                self.session.turns.filter(status_id=ReasoningStatusID.COMPLETED)
                .order_by('-turn_number')
                .prefetch_related('tool_calls__tool')
                .first()
            )
        )()

        sensory_input = ''
        if last_turn:
            tool_calls = await sync_to_async(list)(last_turn.tool_calls.all())
            for tc in tool_calls:
                sensory_input += f'--- Tool Executed: {tc.tool.name} ---\n'
                sensory_input += f'Args: {tc.arguments}\n'
                sensory_input += f'Result:\n{tc.result_payload}\n\n'
            if not sensory_input:
                sensory_input = 'Last turn completed, but no tools were fired.'
        else:
            sensory_input = 'System initialized. This is your first awakening. No previous actions taken.'

        user_content = (
            f'SESSION ID: {self.session.id}\n\n'
            f'[WAKING STATE: ACTIVE GOALS]\n{goal_str}\n\n'
            f'[SENSORY INPUT: PREVIOUS ACTIONS]\n{sensory_input}\n'
            f'[YOUR MOVE]\n'
            f'You have just woken up. Assess your reality. If you discovered facts, use mcp_save_memory. '
            f'If you need context, use mcp_search_memory. Otherwise, fire the tools necessary to advance your goals.'
        )

        await self._log_live('\n--- WAKING PAYLOAD ---')
        await self._log_live(user_content)
        await self._log_live('----------------------\n')

        return [
            ChatMessage(
                role=FrontalLobeConstants.ROLE_SYSTEM,
                content=FrontalLobeConstants.SYSTEM_PERSONA,
            ).to_dict(),
            ChatMessage(
                role=FrontalLobeConstants.ROLE_USER, content=user_content
            ).to_dict(),
        ]


async def run_frontal_lobe(head_id: UUID) -> Tuple[int, str]:
    """Asynchronous entry point for the generic spell caster."""
    try:
        head = await sync_to_async(
            lambda: HydraHead.objects.select_related('spawn').get(id=head_id)
        )()
        lobe = FrontalLobe(head)
        return await lobe.run()
    except Exception as e:
        logger.exception(f'[FrontalLobe] Fatal crash on init: {e}')
        return 500, f'Fatal Error: {str(e)}'
