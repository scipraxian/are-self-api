import sys
import os

from asgiref.sync import sync_to_async
from hydra.models import HydraHead

sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Legacy')))
from log_grokker import parse_log_section


@sync_to_async
def _parse_head_log(head_id: str) -> str:
    try:
        head = HydraHead.objects.get(id=head_id)
        content = head.application_log or ""

        events = parse_log_section(content, 'HOST')

        errors = [e for e in events if 'Error' in e['message']]
        warnings = [e for e in events if 'Warning' in e['message']]

        if not errors and not warnings:
            return "Parser found 0 Errors and 0 Warnings."

        error_lines = [str(e.get('line_number', '?')) for e in errors]
        warning_lines = [str(e.get('line_number', '?')) for e in warnings]

        err_line_str = f" on lines {', '.join(error_lines[:5])}" if errors else ""
        if len(errors) > 5:
            err_line_str += f"... (and {len(errors)-5} more)"

        warn_line_str = f" on lines {', '.join(warning_lines[:5])}" if warnings else ""
        if len(warnings) > 5:
            warn_line_str += f"... (and {len(warnings)-5} more)"

        summary = f"Parser found {len(errors)} Critical Errors{err_line_str}. Found {len(warnings)} Warnings{warn_line_str}."

        return summary
    except Exception as e:
        return f"Failed to parse log: {str(e)}"


async def mcp_run_unreal_diagnostic_parser(head_id: str) -> str:
    """MCP Tool: Parse Unreal Engine logs for a specific HydraHead and return a structural summary."""
    return await _parse_head_log(head_id)
