import importlib
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
            return (f"Error: Tool '{tool_name}' violates nomenclature. Must "
                    f"start with 'mcp_'.")

        try:
            # Dynamically import the module:
            # talos_parietal.parietal_mcp.mcp_read_file
            module_path = f"talos_parietal.parietal_mcp.{tool_name}"
            tool_module = importlib.import_module(module_path)

            # We expect the module to have a main function sharing the exact
            # tool name
            tool_func = getattr(tool_module, tool_name, None)

            if not tool_func:
                return (f"Error: Function '{tool_name}' not found inside "
                        f"module '{module_path}'.")

            # Await the execution
            result = await tool_func(**args)
            return str(result)

        except ImportError:
            return (f"Error: Tool module '{tool_name}' does not exist in "
                    f"parietal_mcp.")
        except Exception as e:
            logger.exception(f"[ParietalMCP] Execution crash in {tool_name}")
            return f"Tool Execution Crash: {str(e)}"
