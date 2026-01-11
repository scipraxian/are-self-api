import re
from hydra.models import HydraSpawn, HydraHead, HydraHeadStatus

# Regex Patterns for Error Detection
# The "Killers" (High Priority)
CONCERN_PATTERNS = [
    r"Log\w+:\s+Error:",  # Catch generic "LogProperty: Error:"
    r"Log\w+:\s+Fatal:",  # Catch "LogWindows: Fatal:"
    r"Log\w+:\s+Critical:",  # Catch Critical errors
    r"LogScript:\s+Error:",  # Catch Blueprint Runtime Errors
    r"Exception:",  # Python/C# Exceptions
    r"error C\d+:",  # C++ Compiler Errors (C2065)
    r"error LNK\d+:",  # Linker Errors
    r"BEWARE:",  # Memory Warnings (Special Case)
    r"Ensure condition failed:",  # Logic Breaks
]

# The "Noise" (Ignore these even if they match above)
IGNORE_PATTERNS = [
    r"0 Error\(s\)",  # "Success - 0 Error(s)"
    r"0 error\(s\)",
    r"Success -",
    r"LogInit: Display:",  # Summary lines
    r"LogAutomationController:",  # Test noise
    r"LogAudioCaptureCore:",  # "No Audio Capture" spam
]


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

    def is_concern(line):
        for pattern in CONCERN_PATTERNS:
            if re.search(pattern, line):
                # Check ignores
                for ignore in IGNORE_PATTERNS:
                    if re.search(ignore, line):
                        return False
                return True
        return False

    # 1. Capture Error Blocks (Context: 5 before, 10 after)
    error_blocks = []
    i = 0
    while i < len(cleaned_lines):
        line = cleaned_lines[i]
        if is_concern(line):
            start = max(0, i - 5)
            end = min(len(cleaned_lines), i + 10)
            block = "\n".join(cleaned_lines[start:end])
            error_blocks.append(f"... {block} ...")
            # Skip forward to avoid overlapping blocks for same error cluster
            i = end
        else:
            i += 1

    # Limit error blocks to avoid huge dumps
    error_summary = "\n".join(error_blocks[:5])

    # 2. Last 200 lines
    tail = "\n".join(cleaned_lines[-200:])

    return f"ERROR SUMMARY:\n{error_summary}\n\nLAST 200 LINES:\n{tail}"
