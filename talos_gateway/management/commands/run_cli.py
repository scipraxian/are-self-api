"""Django management command for the Are-Self CLI REPL."""

import asyncio
import logging
import sys
import random
from typing import Optional

from django.core.management.base import BaseCommand

from talos_gateway.cli.client import CliClient, DisplayCallbacks
from talos_gateway.cli.display import (
    format_error,
    format_response_complete,
    format_session_info,
    format_session_list,
    format_token_delta,
    parse_cli_input,
    print_welcome,
)

logger = logging.getLogger('talos_gateway.management.run_cli')


def _write_flush(text: str) -> None:
    """Write to stdout and flush immediately for streaming."""
    sys.stdout.write(text)
    sys.stdout.flush()


def _cli_listen_on_token(token: str) -> None:
    _write_flush(format_token_delta(token))


def _cli_listen_on_complete(content: str, session_status: str) -> None:
    _write_flush(format_response_complete(content, session_status) + '\n')


def _cli_listen_on_status(status: str) -> None:
    _write_flush('[status] %s\n' % status)


def _cli_listen_on_error(code: str, message: str) -> None:
    _write_flush(format_error(code, message) + '\n')


async def run_cli_main_async(
    host: str,
    port: int,
    channel: str,
    session: Optional[str],
) -> None:
    """Connect to the gateway WebSocket and run the interactive REPL."""
    ws_url = 'ws://%s:%s/ws/gateway/stream/' % (host, port)
    client = CliClient(ws_url, channel)
    callbacks = DisplayCallbacks(
        on_token=_cli_listen_on_token,
        on_complete=_cli_listen_on_complete,
        on_status=_cli_listen_on_status,
        on_error=_cli_listen_on_error,
    )

    await client.start(callbacks)
    try:
        if session:
            result = await client.send_join_session(session)
            session_id = result.get('session_id', session)
            sys.stdout.write(
                format_session_info(session_id, 'joined', '') + '\n'
            )
        else:
            result = await client.send_create_session()
            session_id = result.get('session_id', '')
            sys.stdout.write(
                format_session_info(
                    session_id, 'new', result.get('channel_id', channel)
                ) + '\n'
            )

        sys.stdout.write(print_welcome() + '\n')
        sys.stdout.flush()

        voice_enabled = False
        pending_attachment: Optional[str] = None

        while True:
            line = await asyncio.get_event_loop().run_in_executor(
                None, sys.stdin.readline
            )
            if not line:
                break

            cmd, args = parse_cli_input(line)

            if cmd == 'quit':
                break
            elif cmd == 'new':
                r = await client.send_create_session()
                session_id = r.get('session_id', '')
                sys.stdout.write(
                    format_session_info(
                        session_id, 'new', r.get('channel_id', '')
                    ) + '\n'
                )
            elif cmd == 'sessions':
                sessions = await client.send_list_sessions()
                sys.stdout.write(format_session_list(sessions) + '\n')
            elif cmd == 'select':
                r = await client.send_join_session(args)
                sys.stdout.write(
                    format_session_info(
                        r.get('session_id', args), 'joined', ''
                    ) + '\n'
                )
            elif cmd == 'interrupt':
                r = await client.send_interrupt()
                sys.stdout.write('[interrupt] %s\n' % r)
            elif cmd == 'attach':
                pending_attachment = args
                sys.stdout.write(
                    '[attach] Queued: %s (sent with next message)\n' % args
                )
            elif cmd == 'voice':
                voice_enabled = not voice_enabled
                sys.stdout.write(
                    '[voice] %s\n'
                    % ('enabled' if voice_enabled else 'disabled')
                )
            elif cmd == 'status':
                sys.stdout.write(
                    format_session_info(session_id, 'active', channel)
                    + '\n'
                )
            elif cmd == 'message':
                await client.send_message(args)
                if pending_attachment:
                    pending_attachment = None

            sys.stdout.flush()
    finally:
        await client.stop()


class Command(BaseCommand):
    """``python manage.py run_cli`` — interactive CLI agent REPL."""

    help = (
        'Connect to the Are-Self gateway WebSocket and start an interactive '
        'CLI session (blocks until /quit or Ctrl+C).'
    )

    def add_arguments(self, parser):
        rand_float = random.random()
        parser.add_argument(
            '--host',
            default='127.0.0.1',
            help='Gateway WebSocket host (default: 127.0.0.1)',
        )
        parser.add_argument(
            '--port',
            type=int,
            default=8001,
            help='Gateway WebSocket port (default: 8001)',
        )
        parser.add_argument(
            '--channel',
            default=f'cli-{rand_float:0.4f}',
            help='Channel ID for session mapping (default: cli-default)',
        )
        parser.add_argument(
            '--session',
            default=None,
            help='UUID of an existing session to resume',
        )

    def handle(self, *args, **options):
        try:
            asyncio.run(
                run_cli_main_async(
                    host=options['host'],
                    port=options['port'],
                    channel=options['channel'],
                    session=options.get('session'),
                )
            )
        except KeyboardInterrupt:
            self.stdout.write('\nGoodbye.\n')
