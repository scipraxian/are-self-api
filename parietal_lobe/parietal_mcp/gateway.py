import importlib
import inspect
import json
import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


_PARIETAL_TOOL_REGISTRY: Dict[str, Callable] = {}


def register_parietal_tool(tool_name: str, handler: Callable) -> None:
    """Register a bundle-contributed parietal MCP tool.

    Args:
        tool_name: Must start with 'mcp_' (enforced).
        handler: The async callable that implements the tool. Its
            signature is inspected at dispatch time the same way core
            tools are — drop hallucinated args, enforce required args,
            etc.

    Raises:
        ValueError: if `tool_name` does not start with 'mcp_'.
        RuntimeError: if `tool_name` is already registered (by any
            source — core dynamic-import collision detection is left
            to dispatch time; this guard only covers registry
            collisions between bundles).
    """
    if not tool_name.startswith('mcp_'):
        raise ValueError(
            f"Parietal tool name '{tool_name}' must start with 'mcp_'."
        )
    if tool_name in _PARIETAL_TOOL_REGISTRY:
        raise RuntimeError(
            f"Parietal tool '{tool_name}' is already registered."
        )
    _PARIETAL_TOOL_REGISTRY[tool_name] = handler
    logger.debug('[ParietalMCP] Registered bundle tool %s.', tool_name)


def unregister_parietal_tool(tool_name: str) -> None:
    """Remove a registered tool. No-op if absent.

    Used by the NeuralModifier uninstall path to clean up. Never
    raises on missing keys — uninstall must be idempotent.
    """
    if _PARIETAL_TOOL_REGISTRY.pop(tool_name, None) is not None:
        logger.debug(
            '[ParietalMCP] Unregistered bundle tool %s.', tool_name
        )


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
            tool_func = _PARIETAL_TOOL_REGISTRY.get(tool_name)

            if tool_func is None:
                module_path = f'parietal_lobe.parietal_mcp.{tool_name}'
                tool_module = importlib.import_module(module_path)
                tool_func = getattr(tool_module, tool_name, None)

                if not tool_func:
                    return (
                        f"Error: Function '{tool_name}' not found inside "
                        f"module '{module_path}'."
                    )

            # --- ARMOR: Hallucination Defense ---
            # Inspect the target function's signature and drop any invented arguments.
            sig = inspect.signature(tool_func)
            safe_args = {k: v for k, v in args.items() if k in sig.parameters}

            # extra_args = set(args.keys()) - set(safe_args.keys())
            # if extra_args:
            #     logger.warning(
            #         f'[ParietalMCP] Stripped extra arguments from {tool_name}: {extra_args}'
            #     )

            # --- ARMOR: Required argument validation ---
            # If the LLM forgot to include required args, fail fast with a clear message
            required = [
                name
                for name, param in sig.parameters.items()
                if param.default is inspect._empty
                and param.kind
                in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            ]
            missing = [name for name in required if name not in safe_args]
            if missing:
                return (
                    f"Tool '{tool_name}' missing required arguments: "
                    f'{", ".join(sorted(missing))}.'
                )

            # Await the execution safely
            result = await tool_func(**safe_args)
            if isinstance(result, (dict, list)):
                return json.dumps(result, default=str)
            return str(result)

        except ImportError:
            return (
                f"Error: Tool module '{tool_name}' does not exist in "
                f'parietal_mcp.'
            )
        except Exception as e:
            logger.exception(f'[ParietalMCP] Execution crash in {tool_name}')
            return f'Tool Execution Crash: {str(e)}'
