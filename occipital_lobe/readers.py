import re
from central_nervous_system.models import SpikeTrain, Spike, SpikeStatus

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
    r"LogProperty:\s+Error:",  # Explicit Property Errors
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


def extract_error_blocks(full_log_content):
    """Refactored helper to extract error patterns with context."""
    cleaned_lines = full_log_content.splitlines()

    def is_concern(line):
        for pattern in CONCERN_PATTERNS:
            if re.search(pattern, line):
                for ignore in IGNORE_PATTERNS:
                    if re.search(ignore, line):
                        return False
                return True
        return False

    error_blocks = []
    i = 0
    while i < len(cleaned_lines):
        line = cleaned_lines[i]
        if is_concern(line):
            start = max(0, i - 5)
            end = min(len(cleaned_lines), i + 10)
            block = "\n".join(cleaned_lines[start:end])
            error_blocks.append(f"... {block} ...")
            i = end
        else:
            i += 1
    return "\n".join(error_blocks[:5])


def read_build_log(run_id, max_token_budget=128000):
    """
    Retrieves and sanitizes log data for a specific CNS Spawn.
    Implements dynamic truncation based on the provided token budget.
    """
    try:
        spike_train = SpikeTrain.objects.get(id=run_id)
    except SpikeTrain.DoesNotExist:
        return "SpikeTrain not found."

    # Find the failed spike(s) first, or just the last run spike
    spikes = spike_train.spikes.filter(status_id=SpikeStatus.FAILED)
    if not spikes.exists():
        spikes = spike_train.spikes.all()

    if not spikes.exists():
        return "No execution spikes found for this spike_train."

    # Join logs from failed spikes
    full_log_content = ""
    for spike in spikes:
        full_log_content += f"\n--- HEAD {spike.id} ({spike.effector.name}) ---\n"
        full_log_content += spike.application_log or ""

    # Reserve tokens for Prompt + Overheads. 1 Token ~= 4 Chars.
    safe_token_limit = max_token_budget - 2000
    max_char_limit = safe_token_limit * 4

    # 1. Error Extraction (Vital Context)
    error_summary = extract_error_blocks(full_log_content)

    current_chars = len(error_summary)
    remaining_chars = max_char_limit - current_chars

    if remaining_chars <= 0:
        return f"ERROR SUMMARY ONLY (Log too huge):\n{error_summary}"

    # 2. Dynamic Tail
    if len(full_log_content) < remaining_chars:
        tail = full_log_content
    else:
        # Take the last N chars
        tail = full_log_content[-remaining_chars:]
        # Snap to nearest line break
        first_newline = tail.find('\n')
        if first_newline != -1:
            tail = tail[first_newline + 1:]
        tail = f"... [TRUNCATED {len(full_log_content) - len(tail)} chars] ...\n{tail}"

    if error_summary:
        return f"ERROR SUMMARY:\n{error_summary}\n\nLOG CONTEXT:\n{tail}"
    else:
        return f"LOG CONTEXT:\n{tail}"
