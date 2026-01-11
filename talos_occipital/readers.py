import re
from hydra.models import HydraSpawn, HydraHead, HydraHeadStatus


def strip_timestamps(text):
    """
    Removes standard timestamp patterns from log lines.
    """
    # Regex for [2026-01-11 10:00:00] or similar
    # Adjust based on likely log format in tasks.py (get_timestamp())
    # task.py uses get_timestamp(), let's assume it's like [YYYY-MM-DD HH:MM:SS]
    return re.sub(r'^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ',
                  '',
                  text,
                  flags=re.MULTILINE)


def read_build_log(run_id):
    """
    Retrieves and sanitizes log data for a specific Hydra Spawn.
    Returns the last 200 lines + any Error blocks.
    """
    try:
        spawn = HydraSpawn.objects.get(id=run_id)
    except HydraSpawn.DoesNotExist:
        return "Spawn not found."

    # Find the failed head(s) first, or just the last run head
    heads = spawn.heads.filter(status_id=HydraHeadStatus.FAILED)
    if not heads.exists():
        heads = spawn.heads.all()

    if not heads.exists():
        return "No execution heads found for this spawn."

    # Join logs from failed heads
    full_log_content = ""
    for head in heads:
        full_log_content += f"\n--- HEAD {head.id} ({head.spell.name}) ---\n"
        full_log_content += head.spell_log

    # Processing
    lines = full_log_content.splitlines()
    cleaned_lines = [strip_timestamps(line) for line in lines]

    # 1. Capture Error Blocks (Context around "Error" or "Exception")
    error_blocks = []
    for i, line in enumerate(cleaned_lines):
        if "error" in line.lower() or "exception" in line.lower():
            start = max(0, i - 5)
            end = min(len(cleaned_lines), i + 5)
            block = "\n".join(cleaned_lines[start:end])
            error_blocks.append(f"... {block} ...")

    # Limit error blocks to avoid huge dumps
    error_summary = "\n".join(error_blocks[:5])

    # 2. Last 200 lines
    tail = "\n".join(cleaned_lines[-200:])

    return f"ERROR SUMMARY:\n{error_summary}\n\nLAST 200 LINES:\n{tail}"
