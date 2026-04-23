import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from asgiref.sync import sync_to_async
from django.db.models import Q

from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from frontal_lobe.synapse_client import SynapseClient, SynapseResponse
from hypothalamus.serializers import ModelSelection
from identity.addons._handler_registry import (
    dispatch_tool_post,
    dispatch_tool_pre,
)
from neuroplasticity.models import NeuralModifierStatus
from parietal_lobe.models import ToolCall, ToolDefinition
from parietal_lobe.parietal_mcp.gateway import ParietalMCP

logger = logging.getLogger(__name__)


def _sync_chat_execution(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model_selection: ModelSelection,
) -> SynapseResponse:
    """Runs completely synchronously inside the thread to allow DB resolution."""
    client = SynapseClient(model_selection)
    return client.chat(messages, tools)


def _sync_unload_execution(model_selection: ModelSelection):
    """Runs synchronously to send the VRAM drop signal."""
    client = SynapseClient(model_selection)
    client.unload()


def _json_str_to_dict(raw_args: Any) -> Dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
    return {}


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

    SESSION_ID = 'session_id'
    TURN_ID = 'turn_id'

    def __init__(self, session: ReasoningSession, log_callback: Callable):
        self.session = session
        self.log_callback = log_callback
        self._last_used_model_selection: Optional[ModelSelection] = None

        self.enabled_tools = (
            self.session.identity_disc.enabled_tools
            if self.session.identity_disc
            else None
        )

    async def _log_live(self, message: str) -> None:
        if self.log_callback:
            if asyncio.iscoroutinefunction(self.log_callback):
                await self.log_callback(message)
            else:
                self.log_callback(message)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model_selection: ModelSelection,
    ) -> SynapseResponse:
        """Acts as a pure conduit, passing the dynamic model choice directly to the Synapse."""

        # Track for VRAM unloading later
        self._last_used_model_selection = model_selection

        # Hand the execution over to the async thread
        return await asyncio.to_thread(
            _sync_chat_execution, messages, tools, model_selection
        )

    async def unload_client(self) -> None:
        """Sends the VRAM unload signal to the last used model."""
        if (
            hasattr(self, '_last_used_model_selection')
            and self._last_used_model_selection
        ):
            await asyncio.to_thread(
                _sync_unload_execution, self._last_used_model_selection
            )

    def _fetch_tools(self, identity_disc):
        """Return the ToolDefinitions the session's IdentityDisc enables.

        Tools owned by a NeuralModifier (``genome`` FK non-null) are
        excluded unless their owning modifier is ENABLED. Core tools
        (``genome IS NULL``) are always included. This is the gating
        codepath that makes bundle enable / disable take effect on the
        next reasoning session.
        """
        return list(
            identity_disc.enabled_tools.prefetch_related(
                'assignments__parameter__type',
                'assignments__parameter__enum_values',
            )
            .select_related('use_type')
            .filter(is_async=True)
            .filter(
                Q(genome__isnull=True)
                | Q(genome__status_id=NeuralModifierStatus.ENABLED)
            )
        )

    async def build_tool_schemas(self) -> List[Dict[str, Any]]:
        """Constructs strict JSON schemas from the normalized ToolParameterAssignment relations."""
        if not self.session.identity_disc:
            return []

        db_tools = await sync_to_async(self._fetch_tools)(
            self.session.identity_disc
        )

        ollama_tools = []

        for t in db_tools:
            properties = {}
            required_fields = []

            for assignment in t.assignments.all():
                param_def = assignment.parameter
                type_name = param_def.type.name
                schema_def: Dict[str, Any] = {
                    self.SCHEMA_TYPE: type_name,
                    self.T_DESC: param_def.description
                    or f'The {param_def.name} parameter.',
                }
                enums = [e.value for e in param_def.enum_values.all()]
                if enums:
                    schema_def['enum'] = enums
                properties[param_def.name] = schema_def
                if assignment.required:
                    required_fields.append(param_def.name)

            mechanics = t.use_type
            if mechanics is not None:
                cost_str = f'[COST: {mechanics.focus_modifier} Focus | REWARD: +{mechanics.xp_reward} XP] '
            else:
                cost_str = ''

            full_description = f'{cost_str}{t.description}'

            ollama_tools.append(
                {
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
                }
            )

        return ollama_tools

    async def handle_tool_execution(
        self, turn_record: ReasoningTurn, tool_call_data: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """Parses, records, and executes a single tool call."""
        func_data = tool_call_data.get(self.T_FUNC, {})
        tool_name = func_data.get(self.T_NAME)
        raw_args = func_data.get(self.T_ARGS, {})
        args = _json_str_to_dict(raw_args)
        args[self.SESSION_ID] = str(self.session.id)
        args[self.TURN_ID] = str(turn_record.id)
        await self._log_live(f'Tool Call: {tool_name}({args})')

        try:
            tool_def = await sync_to_async(
                lambda: ToolDefinition.objects.select_related('use_type').get(
                    name=tool_name
                )
            )()
        except ToolDefinition.DoesNotExist:
            tool_def = None
            logger.error(f'AI tried to call unknown tool: {tool_name}')

            error_msg = f"Error: Unknown tool '{tool_name}'"
            await self._log_live(f'Result: {error_msg}')
            return {
                'role': 'tool',
                'name': tool_name,
                'content': error_msg,
            }

        mechanics = tool_def.use_type if tool_def else None
        disc = self.session.identity_disc

        # --- TOOL PRE (handler first-veto) ---
        # Each IdentityAddonHandler attached to the disc gets a pre-veto.
        # Focus fizzles on insufficient focus; other handlers can add their
        # own gates (rate-limit, quota, etc.). A disc with no handlers sees
        # no veto — same as the old function-based "addon not installed".
        fizzle_msg = await sync_to_async(dispatch_tool_pre)(
            disc, self.session, mechanics
        )
        if fizzle_msg is not None:
            await self._log_live(f'Result: {fizzle_msg}')

            db_tool_call = await sync_to_async(ToolCall.objects.create)(
                turn=turn_record,
                tool=tool_def,
                arguments=json.dumps(args),
                status_id=ReasoningStatusID.ERROR,
                result_payload=fizzle_msg,
                traceback='Tool pre-check vetoed.',
            )
            return {
                'role': 'tool',
                'name': tool_name,
                'content': fizzle_msg,
            }

        # --- NORMAL EXECUTION ---
        db_tool_call = await sync_to_async(ToolCall.objects.create)(
            turn=turn_record,
            tool=tool_def,
            arguments=json.dumps(args),
            status_id=ReasoningStatusID.ACTIVE,
        )

        try:
            tool_result_obj = await ParietalMCP.execute(tool_name, args)
            tool_result = str(tool_result_obj)

            db_tool_call.result_payload = tool_result[:20000]
            db_tool_call.status_id = ReasoningStatusID.COMPLETED
            await sync_to_async(db_tool_call.save)()

            # --- TOOL POST (handler collect-all) ---
            # Focus owns the focus/XP ledger; any handler observing the raw
            # result (focus_yield / xp_yield / other metadata) gets its shot.
            # Passes the pre-stringification object so handlers can read attrs.
            await sync_to_async(dispatch_tool_post)(
                disc, self.session, mechanics, tool_result_obj
            )

        except Exception as e:
            tool_result = f'Tool Execution Error: {str(e)}'
            db_tool_call.traceback = str(e)
            db_tool_call.status_id = ReasoningStatusID.ERROR
            await sync_to_async(db_tool_call.save)()

        await self._log_live(f'Result: {tool_result[:200]}...')

        # --- NO MORE CHAT MESSAGE CREATION ---
        return {
            'role': 'tool',
            'name': tool_name,
            'content': tool_result,
        }

    async def process_tool_calls(
        self, turn_record: ReasoningTurn, tool_calls_data: List[Dict[str, Any]]
    ) -> None:
        """Sorts tool calls by focus_modifier and executes them."""
        tool_names = [
            tc.get(self.T_FUNC, {}).get(self.T_NAME) for tc in tool_calls_data
        ]
        tool_defs = await sync_to_async(
            lambda: list(
                ToolDefinition.objects.select_related('use_type').filter(
                    name__in=tool_names
                )
            )
        )()
        tool_def_map = {td.name: td for td in tool_defs}

        def get_focus_mod(tc):
            name = tc.get(self.T_FUNC, {}).get(self.T_NAME)
            td = tool_def_map.get(name)
            if td and td.use_type:
                return td.use_type.focus_modifier
            return 0

        sorted_tool_calls = sorted(
            tool_calls_data, key=get_focus_mod, reverse=True
        )

        for tool_call_data in sorted_tool_calls:
            await self.handle_tool_execution(turn_record, tool_call_data)
