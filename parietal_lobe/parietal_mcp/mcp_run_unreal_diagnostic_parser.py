import sys
import os
import math

from asgiref.sync import sync_to_async
from central_nervous_system.models import Spike

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from ue_tools.log_parser import LogParserFactory, LogConstants


@sync_to_async
def _parse_head_log(head_id: str, page: int = 1) -> str:
    try:
        spike = Spike.objects.get(id=head_id)
        content = spike.application_log or ""

        import io
        parser = LogParserFactory.create(LogConstants.TYPE_RUN, 'HOST')
        with io.StringIO(content) as stream:
            entries = parser.parse_chunk(stream)
        entries.extend(parser.flush())

        error_indices = [
            i for i, e in enumerate(entries)
            if LogConstants.LVL_ERROR in e.level or
            getattr(e, 'message', '').find('Error') != -1
        ]
        warning_indices = [
            i for i, e in enumerate(entries)
            if LogConstants.LVL_WARNING in e.level or
            getattr(e, 'message', '').find('Warning') != -1
        ]

        if not error_indices and not warning_indices:
            return "Parser found 0 Errors and 0 Warnings."

        err_lines = [str(entries[i].line_num) for i in error_indices]
        warn_lines = [str(entries[i].line_num) for i in warning_indices]

        err_line_str = f" on lines {', '.join(err_lines[:5])}" if err_lines else ""
        if len(err_lines) > 5:
            err_line_str += f"... (and {len(err_lines)-5} more)"

        warn_line_str = f" on lines {', '.join(warn_lines[:5])}" if warn_lines else ""
        if len(warn_lines) > 5:
            warn_line_str += f"... (and {len(warn_lines)-5} more)"

        summary_header = f"Parser found {len(error_indices)} Critical Errors{err_line_str}. Found {len(warning_indices)} Warnings{warn_line_str}.\n"

        if not error_indices:
            return summary_header

        errors_per_page = 5
        total_pages = math.ceil(len(error_indices) /
                                errors_per_page) if error_indices else 1
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * errors_per_page
        end_idx = start_idx + errors_per_page

        current_page_errors = error_indices[start_idx:end_idx]

        summary = summary_header + f"\n[DIAGNOSTIC RESULTS: Page {page} of {total_pages} | Total Errors: {len(error_indices)}]\n"

        for i in current_page_errors:
            err_entry = entries[i]
            # Grab context lines: up to 5 lines before and 5 lines after
            start_i = max(0, i - 5)
            end_i = min(len(entries), i + 6)

            summary += f"\n--- ERROR AT LINE {err_entry.line_num} ---\n"
            for j in range(start_i, end_i):
                ctx_entry = entries[j]
                prefix = ">> " if j == i else "   "
                summary += f"{prefix}{ctx_entry.line_num}: {ctx_entry.raw}\n"

        # Hard cap size fallback
        if len(summary) > 20000:
            summary = summary[:20000] + "\n... [Truncated]"

        return summary
    except Exception as e:
        return f"Failed to parse log: {str(e)}"


async def mcp_run_unreal_diagnostic_parser(head_id: str, page: int = 1) -> str:
    """MCP Tool: Parse Unreal Engine logs for a specific Spike and return a structural summary."""
    return await _parse_head_log(head_id, page)
