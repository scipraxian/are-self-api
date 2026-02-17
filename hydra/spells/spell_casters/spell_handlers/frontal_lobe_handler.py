import json
import logging
from typing import Any, Dict, List, Tuple
from uuid import UUID

from django.conf import settings

from hydra.models import HydraHead
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
    DEFAULT_PROMPT = 'Analyze the current state and execute necessary tools to resolve issues.'
    SYSTEM_PERSONA = (
        'You are Talos, a Senior Build Engineer and autonomous AI agent. '
        'Your job is to investigate logs, navigate the filesystem, and write '
        'fixes to the Blackboard to orchestrate the build pipeline.'
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


def _build_tool_schemas() -> List[Dict[str, Any]]:
    """Fetches active tools from the database and maps them to the Ollama schema."""
    db_tools = ToolDefinition.objects.all()
    ollama_tools = []

    for t in db_tools:
        schema = (
            t.parameters_schema
            if isinstance(t.parameters_schema, dict)
            else json.loads(t.parameters_schema)
        )
        ollama_tools.append(
            {
                FrontalLobeConstants.T_TYPE: FrontalLobeConstants.TYPE_FUNCTION,
                FrontalLobeConstants.T_FUNC: {
                    FrontalLobeConstants.T_NAME: t.name,
                    FrontalLobeConstants.T_DESC: t.description,
                    FrontalLobeConstants.T_PARAMS: schema,
                },
            }
        )
    return ollama_tools


def _execute_tool(tool_name: str, args: Dict[str, Any]) -> str:
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


def _parse_tool_arguments(raw_args: Any) -> Dict[str, Any]:
    """Ensures tool arguments are a valid dictionary, handling LLM quirks."""
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
    return {}


def _get_objective(context: Dict[str, Any], head_id: UUID) -> str:
    """Extracts the primary objective from the execution context."""
    prompt = context.get(
        FrontalLobeConstants.KEY_PROMPT,
        context.get(FrontalLobeConstants.KEY_OBJECTIVE, ''),
    )

    if prompt:
        return prompt

    return f'{FrontalLobeConstants.DEFAULT_PROMPT} Context Head: {head_id}'


def run_frontal_lobe(head_id: UUID) -> Tuple[int, str]:
    """
    The Native AI Handler for the Talos AGI loop.
    """
    logger.info(f'[FrontalLobe] Waking up for Head {head_id}')
    log_output = [FrontalLobeConstants.LOG_START]

    try:
        head = HydraHead.objects.get(id=head_id)
    except HydraHead.DoesNotExist:
        return 500, f'Error: Head {head_id} not found.'

    context = resolve_environment_context(head_id=head.id)
    objective = _get_objective(context, head_id)
    ollama_tools = _build_tool_schemas()

    model_name = ModelRegistry.get_model(ModelRegistry.COMMANDER)
    client = OllamaClient(model=model_name)

    messages = [
        ChatMessage(
            role=FrontalLobeConstants.ROLE_SYSTEM,
            content=FrontalLobeConstants.SYSTEM_PERSONA,
        ).to_dict(),
        ChatMessage(
            role=FrontalLobeConstants.ROLE_USER,
            content=f'CONTEXT DATA:\n{json.dumps(context, indent=2)}\n\nOBJECTIVE:\n{objective}',
        ).to_dict(),
    ]

    log_output.append(f'Model: {model_name}')
    log_output.append(f'Loaded {len(ollama_tools)} tools.')
    log_output.append(f'Objective: {objective}')

    # The Autonomous ReAct Loop
    for turn in range(FrontalLobeConstants.MAX_TURNS):
        log_output.append(f'\n--- Turn {turn + 1} ---')
        logger.info(f'[FrontalLobe] Turn {turn + 1} tick...')

        response = client.chat(messages=messages, tools=ollama_tools)

        # 1. Record Assistant State (Using DTO)
        assistant_msg = ChatMessage(
            role=FrontalLobeConstants.ROLE_ASSISTANT,
            content=response.content,
            tool_calls=response.tool_calls if response.tool_calls else None,
        )
        messages.append(assistant_msg.to_dict())

        if response.content:
            log_output.append(f'Thought: {response.content.strip()}')

        # 2. Check for Loop Termination
        if not response.tool_calls:
            log_output.append(
                'No further actions requested. Objective Complete.'
            )
            break

        # 3. Process Tools
        for tool_call in response.tool_calls:
            func_data = tool_call.get(FrontalLobeConstants.T_FUNC, {})
            tool_name = func_data.get(FrontalLobeConstants.T_NAME)

            raw_args = func_data.get(FrontalLobeConstants.T_ARGS, {})
            args = _parse_tool_arguments(raw_args)

            log_output.append(f'Tool Call: {tool_name}({args})')

            tool_result = _execute_tool(tool_name, args)
            log_output.append(f'Result: {tool_result[:200]}...')

            # 4. Record Tool Result (Using DTO)
            tool_msg = ChatMessage(
                role=FrontalLobeConstants.ROLE_TOOL,
                content=tool_result,
                name=tool_name,
            )
            messages.append(tool_msg.to_dict())

        if turn == FrontalLobeConstants.MAX_TURNS - 1:
            log_output.append(
                '\n[WARNING] Max cognitive turns reached. Halting.'
            )

    log_output.append(FrontalLobeConstants.LOG_END)
    return 200, '\n'.join(log_output)
