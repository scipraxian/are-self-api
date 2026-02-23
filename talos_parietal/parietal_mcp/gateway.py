import importlib
import inspect
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ParietalMCP:
    """
    Gateway for executing MCP-compliant tools asynchronously.
    Maps a tool name string directly to its corresponding module file.
    """

    @classmethod
    async def execute(cls, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Dynamically loads and awaits the requested mcp tool.
        """
        if not tool_name.startswith('mcp_'):
            return (
                f"Error: Tool '{tool_name}' violates nomenclature. Must "
                f"start with 'mcp_'."
            )

        try:
            module_path = f'talos_parietal.parietal_mcp.{tool_name}'
            tool_module = importlib.import_module(module_path)

            tool_func = getattr(tool_module, tool_name, None)

            if not tool_func:
                return (
                    f"Error: Function '{tool_name}' not found inside "
                    f"module '{module_path}'."
                )

            # --- ARMOR: Hallucination Defense ---
            # Inspect the target function's signature and drop any invented arguments
            sig = inspect.signature(tool_func)
            safe_args = {k: v for k, v in args.items() if k in sig.parameters}

            hallucinated = set(args.keys()) - set(safe_args.keys())
            if hallucinated:
                logger.warning(
                    f'[ParietalMCP] Stripped hallucinated arguments from {tool_name}: {hallucinated}'
                )

            # Await the execution safely
            result = await tool_func(**safe_args)
            return str(result)

        except ImportError:
            return (
                f"Error: Tool module '{tool_name}' does not exist in "
                f'parietal_mcp.'
            )
        except Exception as e:
            logger.exception(f'[ParietalMCP] Execution crash in {tool_name}')
            return f'Tool Execution Crash: {str(e)}'
