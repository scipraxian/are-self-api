import asyncio
import json
import logging
from typing import Any, Callable, Dict, List

from asgiref.sync import sync_to_async

from talos_parietal.models import ToolCall, ToolDefinition
from talos_parietal.parietal_mcp.gateway import ParietalMCP
from frontal_lobe.synapse import ChatMessage, OllamaClient
from frontal_lobe.models import ReasoningSession, ReasoningStatusID, ReasoningTurn

logger = logging.getLogger(__name__)


class ParietalLobe:
    """Handles sensory input, tool execution (motor output), and model inference."""

    T_TYPE = 'type'
    T_FUNC = 'function'
    T_NAME = 'name'
    T_DESC = 'description'
    T_PARAMS = 'parameters'
    T_ARGS = 'arguments'
    TYPE_FUNCTION = 'function'

    SCHEMA_TYPE = 'type'
    SCHEMA_PROPERTIES = 'properties'
    SCHEMA_REQUIRED = 'required'
    TYPE_OBJECT = 'object'
    ROLE_TOOL = 'tool'

    def __init__(self, session: ReasoningSession, log_callback: Callable):
        self.session = session
        self.log_callback = log_callback
        self.client = None

    async def _log_live(self, message: str) -> None:
        if self.log_callback:
            if asyncio.iscoroutinefunction(self.log_callback):
                await self.log_callback(message)
            else:
                self.log_callback(message)

    async def initialize_client(self, model_name: str) -> None:
        self.client = OllamaClient(model=model_name)

    async def chat(self, messages: List[Dict[str, Any]],
                   tools: List[Dict[str, Any]]) -> Any:
        return await asyncio.to_thread(self.client.chat, messages, tools)

    async def unload_client(self) -> None:
        if self.client:
            await asyncio.to_thread(self.client.unload)

    async def build_tool_schemas(self) -> List[Dict[str, Any]]:
        """Constructs strict JSON schemas from the normalized ToolParameterAssignment relations."""
        db_tools = await sync_to_async(lambda: list(
            ToolDefinition.objects.prefetch_related(
                'assignments__parameter__type',
                'assignments__parameter__enum_values',
            ).select_related('use_type').filter(is_async=True)))()

        ollama_tools = []

        for t in db_tools:
            properties = {}
            required_fields = []

            for assignment in t.assignments.all():
                param_def = assignment.parameter
                type_name = param_def.type.name
                schema_def: Dict[str, Any] = {
                    self.SCHEMA_TYPE:
                        type_name,
                    self.T_DESC:
                        param_def.description
                        or f'The {param_def.name} parameter.',
                }
                enums = [e.value for e in param_def.enum_values.all()]
                if enums:
                    schema_def['enum'] = enums
                properties[param_def.name] = schema_def
                if assignment.required:
                    required_fields.append(param_def.name)

            mechanics = t.use_type
            if mechanics:
                cost_str = f'[COST: {mechanics.focus_modifier} Focus | REWARD: +{mechanics.xp_reward} XP] '
            else:
                cost_str = '[COST: 0 Focus | REWARD: +0 XP] '

            full_description = f'{cost_str}{t.description}'

            ollama_tools.append({
                self.T_TYPE: self.TYPE_FUNCTION,
                self.T_FUNC: {
                    self.T_NAME: t.name,
                    self.T_DESC: full_description,
                    self.T_PARAMS: {
                        self.SCHEMA_TYPE: self.TYPE_OBJECT,
                        self.SCHEMA_PROPERTIES: properties,
                        self.SCHEMA_REQUIRED: required_fields,
                    },
                },
            })

        return ollama_tools

    def _parse_tool_arguments(self, raw_args: Any) -> Dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                return json.loads(raw_args)
            except json.JSONDecodeError:
                return {}
        return {}

    async def handle_tool_execution(
            self, turn_record: ReasoningTurn,
            tool_call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parses, records, and executes a single tool call, enforcing the Focus Economy."""
        func_data = tool_call_data.get(self.T_FUNC, {})
        tool_name = func_data.get(self.T_NAME)
        raw_args = func_data.get(self.T_ARGS, {})
        args = self._parse_tool_arguments(raw_args)

        # Safe Injection: Pass the exact turn ID to memory tools
        if tool_name in ['mcp_engram_save', 'mcp_engram_update']:
            args['turn_id'] = turn_record.id

        await self._log_live(f'Tool Call: {tool_name}({args})')

        try:
            tool_def = await sync_to_async(
                lambda: ToolDefinition.objects.select_related('use_type').get(
                    name=tool_name))()
        except ToolDefinition.DoesNotExist:
            tool_def = None
            logger.error(f'AI tried to call unknown tool: {tool_name}')

        mechanics = tool_def.use_type if tool_def else None
        focus_mod = mechanics.focus_modifier if mechanics else 0
        xp_gain = mechanics.xp_reward if mechanics else 0

        if focus_mod < 0 and self.session.current_focus + focus_mod < 0:
            fizzle_msg = (
                f'SYSTEM OVERRIDE: Spell Fizzled! Insufficient Focus. '
                f'(Requires {-focus_mod}, but you only have {self.session.current_focus}). '
                f'You must use Synthesis tools (like mcp_save_memory) to restore Focus.'
            )
            await self._log_live(f'Result: {fizzle_msg}')

            if tool_def:
                await sync_to_async(ToolCall.objects.create)(
                    turn=turn_record,
                    tool=tool_def,
                    arguments=json.dumps(args),
                    status_id=ReasoningStatusID.ERROR,
                    result_payload=fizzle_msg,
                    traceback='Insufficient Focus.',
                )

            return ChatMessage(
                role=self.ROLE_TOOL,
                content=fizzle_msg,
                name=tool_name,
            ).to_dict()

        db_tool_call = None
        if tool_def:
            db_tool_call = await sync_to_async(ToolCall.objects.create)(
                turn=turn_record,
                tool=tool_def,
                arguments=json.dumps(args),
                status_id=ReasoningStatusID.ACTIVE,
            )

        try:
            tool_result = await ParietalMCP.execute(tool_name, args)

            if db_tool_call:
                db_tool_call.result_payload = tool_result[:10000]
                db_tool_call.status_id = ReasoningStatusID.COMPLETED
                await sync_to_async(db_tool_call.save)()

                self.session.current_focus = min(
                    self.session.max_focus,
                    self.session.current_focus + focus_mod,
                )
                self.session.total_xp += xp_gain
                await sync_to_async(
                    self.session.save
                )(update_fields=['current_focus', 'total_xp'])

        except Exception as e:
            tool_result = f'Tool Execution Error: {str(e)}'
            if db_tool_call:
                db_tool_call.traceback = str(e)
                db_tool_call.status_id = ReasoningStatusID.ERROR
                await sync_to_async(db_tool_call.save)()

        await self._log_live(f'Result: {tool_result[:200]}...')

        return ChatMessage(
            role=self.ROLE_TOOL,
            content=tool_result,
            name=tool_name,
        ).to_dict()

    async def process_tool_calls(self, turn_record: ReasoningTurn,
                                 tool_calls_data: List[Dict[str, Any]]) -> None:
        """Sorts tool calls by focus_modifier and executes them."""
        tool_names = [
            tc.get(self.T_FUNC, {}).get(self.T_NAME) for tc in tool_calls_data
        ]
        tool_defs = await sync_to_async(lambda: list(
            ToolDefinition.objects.select_related('use_type').filter(
                name__in=tool_names)))()
        tool_def_map = {td.name: td for td in tool_defs}

        def get_focus_mod(tc):
            name = tc.get(self.T_FUNC, {}).get(self.T_NAME)
            td = tool_def_map.get(name)
            if td and td.use_type:
                return td.use_type.focus_modifier
            return 0

        sorted_tool_calls = sorted(tool_calls_data,
                                   key=get_focus_mod,
                                   reverse=True)

        for tool_call_data in sorted_tool_calls:
            await self.handle_tool_execution(turn_record, tool_call_data)
