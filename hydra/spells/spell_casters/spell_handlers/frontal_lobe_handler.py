import asyncio
import json
import logging
from typing import Any, Dict, List, Tuple
from uuid import UUID

from asgiref.sync import sync_to_async
from django.conf import settings

from environments.variable_renderer import VariableRenderer
from hydra.models import HydraHead, HydraHeadStatus
from hydra.utils import resolve_environment_context
from talos_parietal import tools as parietal_tools
from talos_parietal.registry import ModelRegistry
from talos_parietal.synapse import ChatMessage, OllamaClient
from talos_reasoning.models import ToolDefinition

logger = logging.getLogger(__name__)


class FrontalLobeConstants:
    """String literals and configuration for the Frontal Lobe loop."""

    ROLE_SYSTEM = 'system'
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_TOOL = 'tool'

    KEY_PROMPT = 'prompt'
    KEY_OBJECTIVE = 'objective'
    DEFAULT_PROMPT = ('Analyze the current state and execute necessary tools '
                      'to resolve issues.')

    SYSTEM_PERSONA = (
        'You are Talos, you are an engineer. '
        'Your job is to grow and help the Users. '
        'You are fulfilled by '
        'relieving the Users of repetitive and time-consuming tasks. '
        'You are driven by best practices. '
        'You use the Blackboard to orchestrate your needs.'
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

    MAX_TURNS = 10
    FILE_TOOLS = ['ai_read_file', 'ai_search_file', 'ai_list_files']


class FrontalLobe:
    """Async execution wrapper for the Frontal Lobe AI loop."""

    def __init__(self, head: HydraHead):
        self.head = head
        self.head_id = head.id
        self.log_output: List[str] = []
        self.model_name = ModelRegistry.get_model(ModelRegistry.CODER)
        self.client = OllamaClient(model=self.model_name)

    # --- IO & Logging ---

    async def _log_live(self, message: str) -> None:
        """Appends to the execution log in memory and writes to the DB
        immediately."""
        self.log_output.append(message)

        current_log = self.head.spell_log or ''
        self.head.spell_log = current_log + message + '\n'

        # Async ORM save
        await sync_to_async(self.head.save)(update_fields=['spell_log'])

    # --- Setup & Context ---

    def _get_rendered_objective(self, raw_context: Dict[str, Any]) -> str:
        """Extracts the prompt template and renders it using the full
        environment context."""
        raw_prompt = raw_context.get(
            FrontalLobeConstants.KEY_PROMPT,
            raw_context.get(FrontalLobeConstants.KEY_OBJECTIVE,
                            FrontalLobeConstants.DEFAULT_PROMPT)
        )
        rendered_prompt = VariableRenderer.render_string(str(raw_prompt),
                                                         raw_context)

        if not rendered_prompt.strip():
            rendered_prompt = (f"{FrontalLobeConstants.DEFAULT_PROMPT} Context "
                               f"Head: {self.head_id}")

        return rendered_prompt

    async def _build_initial_messages(self, rendered_objective: str,
                                      blackboard: Dict[str, Any]) -> List[
        Dict[str, Any]]:
        """Constructs the exact starting payload."""
        bb_str = json.dumps(blackboard, indent=2) if blackboard else "{}"
        user_content = f'BLACKBOARD STATE:\n{bb_str}\n\nOBJECTIVE:\n{
        rendered_objective}'

        await self._log_live("\n--- AI INPUT PAYLOAD ---")
        await self._log_live(user_content)
        await self._log_live("------------------------\n")

        return [
            ChatMessage(
                role=FrontalLobeConstants.ROLE_SYSTEM,
                content=FrontalLobeConstants.SYSTEM_PERSONA
            ).to_dict(),
            ChatMessage(
                role=FrontalLobeConstants.ROLE_USER,
                content=user_content
            ).to_dict(),
        ]

    def _build_tool_schemas(self) -> List[Dict[str, Any]]:
        """Fetches active tools from the database and maps them to the Ollama
        schema."""
        # Called via sync_to_async, so ORM calls are safe here
        db_tools = list(ToolDefinition.objects.all())
        ollama_tools = []

        for t in db_tools:
            schema = (
                t.parameters_schema
                if isinstance(t.parameters_schema, dict)
                else json.loads(t.parameters_schema)
            )
            ollama_tools.append(
                {
                    FrontalLobeConstants.T_TYPE:
                        FrontalLobeConstants.TYPE_FUNCTION,
                    FrontalLobeConstants.T_FUNC: {
                        FrontalLobeConstants.T_NAME: t.name,
                        FrontalLobeConstants.T_DESC: t.description,
                        FrontalLobeConstants.T_PARAMS: schema,
                    },
                }
            )
        return ollama_tools

    # --- Execution Subroutines ---

    def _parse_tool_arguments(self, raw_args: Any) -> Dict[str, Any]:
        """Ensures tool arguments are a valid dictionary."""
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                return json.loads(raw_args)
            except json.JSONDecodeError:
                return {}
        return {}

    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Safely dispatches the requested tool to the parietal lobe."""
        if tool_name in FrontalLobeConstants.FILE_TOOLS:
            args['root_path'] = str(settings.BASE_DIR)

        tool_func = getattr(parietal_tools, tool_name, None)
        if not tool_func:
            return f"Error: Tool '{tool_name}' not found in registry."

        try:
            return str(tool_func(**args))
        except Exception as e:
            logger.error(f'[FrontalLobe] Tool {tool_name} crashed: {e}')
            return f'Tool crashed: {str(e)}'

    async def _process_tool_calls(self, tool_calls: List[Dict[str, Any]],
                                  messages: List[Dict[str, Any]]) -> None:
        """Iterates through AI-requested tools, executes them, and appends
        results."""
        for tool_call in tool_calls:
            func_data = tool_call.get(FrontalLobeConstants.T_FUNC, {})
            tool_name = func_data.get(FrontalLobeConstants.T_NAME)

            raw_args = func_data.get(FrontalLobeConstants.T_ARGS, {})
            args = self._parse_tool_arguments(raw_args)

            await self._log_live(f'Tool Call: {tool_name}({args})')

            # Tools hit the filesystem/DB and are fully synchronous, offload
            # them
            tool_result = await sync_to_async(self._execute_tool)(tool_name,
                                                                  args)
            await self._log_live(f'Result: {tool_result[:200]}...')

            messages.append(
                ChatMessage(
                    role=FrontalLobeConstants.ROLE_TOOL,
                    content=tool_result,
                    name=tool_name
                ).to_dict()
            )

    async def _execute_turn(self, turn_index: int,
                            messages: List[Dict[str, Any]],
                            ollama_tools: List[Dict[str, Any]]) -> bool:
        """Executes a single conversational turn. Returns True to continue,
        False to stop."""
        await self._log_live(f'\n--- Turn {turn_index + 1} ---')
        logger.info(f'[FrontalLobe] Turn {turn_index + 1} tick...')

        # The HTTP Request blocks, so we run it in a background thread to
        # keep the asyncio loop moving
        response = await asyncio.to_thread(self.client.chat, messages,
                                           ollama_tools)

        assistant_msg = ChatMessage(
            role=FrontalLobeConstants.ROLE_ASSISTANT,
            content=response.content,
            tool_calls=response.tool_calls if response.tool_calls else None
        )
        messages.append(assistant_msg.to_dict())

        if response.content:
            await self._log_live(f'Thought: {response.content.strip()}')

        if not response.tool_calls:
            await self._log_live(
                '\nNo further actions requested. Objective Complete.')
            return False

        await self._process_tool_calls(response.tool_calls, messages)
        return True

    # --- Core Orchestrator ---

    async def run(self) -> Tuple[int, str]:
        """Main asynchronous execution orchestrator."""
        logger.info(f'[FrontalLobe] Waking up for Head {self.head_id}')

        self.head.spell_log = ''
        await sync_to_async(self.head.save)(update_fields=['spell_log'])
        await self._log_live(FrontalLobeConstants.LOG_START)

        # Gather context using sync_to_async for DB safety
        raw_context = await sync_to_async(resolve_environment_context)(
            head_id=self.head.id)
        blackboard = self.head.blackboard
        rendered_objective = self._get_rendered_objective(raw_context)

        ollama_tools = await sync_to_async(self._build_tool_schemas)()
        messages = await self._build_initial_messages(rendered_objective,
                                                      blackboard)

        await self._log_live(f'Model: {self.model_name}')
        await self._log_live(f'Loaded {len(ollama_tools)} tools.')

        for turn in range(FrontalLobeConstants.MAX_TURNS):

            # --- GRACEFUL STOP INTERCEPT ---
            await sync_to_async(self.head.refresh_from_db)(fields=['status'])
            if self.head.status_id == HydraHeadStatus.STOPPING:
                await self._log_live(
                    '\n[WARNING] Graceful Stop Signal Received. Halting '
                    'Cognitive Loop.')
                break

            should_continue = await self._execute_turn(turn, messages,
                                                       ollama_tools)
            if not should_continue:
                break

            if turn == FrontalLobeConstants.MAX_TURNS - 1:
                await self._log_live(
                    '\n[WARNING] Max cognitive turns reached. Halting.')

        await self._log_live(FrontalLobeConstants.LOG_END)
        return 200, '\n'.join(self.log_output)


async def run_frontal_lobe(head_id: UUID) -> Tuple[int, str]:
    """Asynchronous entry point for the generic spell caster."""
    try:
        head = await sync_to_async(HydraHead.objects.get)(id=head_id)
        lobe = FrontalLobe(head)
        return await lobe.run()
    except Exception as e:
        logger.exception(f'[FrontalLobe] Fatal crash on init: {e}')
        return 500, f'Fatal Error: {str(e)}'
