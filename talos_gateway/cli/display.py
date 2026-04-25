"""Terminal rendering and input parsing for the CLI client (pure functions)."""

from typing import Tuple

_COMMANDS = frozenset({
    'new', 'sessions', 'select', 'interrupt',
    'attach', 'voice', 'status', 'quit',
})


def parse_cli_input(raw: str) -> Tuple[str, str]:
    """Split raw terminal input into (command, args).

    Slash-prefixed tokens matching a known command are extracted.
    Everything else is treated as a plain message.

    Returns:
        Tuple of (command_name, argument_string).
    """
    stripped = raw.strip()
    if stripped.startswith('/'):
        parts = stripped[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ''
        if cmd in _COMMANDS:
            args = parts[1] if len(parts) > 1 else ''
            return cmd, args
    return 'message', stripped


def format_token_delta(token: str) -> str:
    """Format a single streamed token for terminal display."""
    return token


def format_response_complete(content: str, status: str) -> str:
    """Format the final response with a status indicator."""
    return '\n[%s] %s' % (status, content)


def format_session_list(sessions: list[dict]) -> str:
    """Format a list of sessions as a readable table."""
    if not sessions:
        return 'No active sessions.'

    lines = ['  %-36s  %-16s  %s' % ('SESSION ID', 'CHANNEL', 'IDENTITY')]
    lines.append('  ' + '-' * 70)
    for s in sessions:
        lines.append(
            '  %-36s  %-16s  %s' % (
                s.get('session_id', ''),
                s.get('channel_id', ''),
                s.get('identity_disc_name', ''),
            )
        )
    return '\n'.join(lines)


def format_session_info(session_id: str, status: str, identity: str) -> str:
    """Format a single-session summary line."""
    return 'Session: %s | Status: %s | Identity: %s' % (
        session_id, status, identity,
    )


def format_error(code: str, message: str) -> str:
    """Format an error for terminal display."""
    return '[ERROR %s] %s' % (code, message)


def format_identity_disc_list(discs: list[dict]) -> str:
    """Format a list of available IdentityDiscs as a readable table.

    Each ``dict`` is expected to expose ``name``, ``id`` and
    ``identity_type`` keys; missing values render as empty strings.
    """
    if not discs:
        return 'No available IdentityDiscs.'

    lines = ['  %-24s  %-36s  %s' % ('NAME', 'ID', 'TYPE')]
    lines.append('  ' + '-' * 70)
    for d in discs:
        lines.append(
            '  %-24s  %-36s  %s' % (
                d.get('name', ''),
                d.get('id', ''),
                d.get('identity_type', ''),
            )
        )
    return '\n'.join(lines)


def print_welcome() -> str:
    """Return a welcome banner with available commands."""
    return (
        'Are-Self CLI\n'
        '============\n'
        'Commands:\n'
        '  /new             Create a new session\n'
        '  /sessions        List active sessions\n'
        '  /select <id>     Switch to a session\n'
        '  /interrupt       Interrupt current reasoning\n'
        '  /attach <path>   Attach a file to next message\n'
        '  /voice           Toggle voice mode\n'
        '  /status          Show current session info\n'
        '  /quit            Exit the CLI\n'
    )
