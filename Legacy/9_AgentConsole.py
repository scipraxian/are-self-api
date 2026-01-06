"""Interactive and command-line console for managing remote agents.

This script allows users to send commands to remote agents, fetch logs from
network shares, and generate AI context summaries. It supports both
interactive menu mode and headless command-line operation.
"""

import json
import logging
import os
import subprocess
import sys
import time

import AgentUtils
import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)


def clear_screen():
    """Clears the console screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_status_map():
    """Reads the latest agent status from the status JSON file.

    Returns:
        dict: The loaded status mapping.
    """
    if not os.path.exists(config.STATUS_FILE):
        return {}
    try:
        with open(config.STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:  # pylint: disable=broad-except
        return {}


def run_ai_summary():
    """Executes the AI context packer script (Step 6.5)."""
    print('\n' + '-' * 41)
    print('   GENERATING AI CONTEXT SUMMARY')
    print('-' * 41)
    script_path = os.path.join(config.BUILDER_DIR, '6_5_FeedTheAI.py')
    if os.path.exists(script_path):
        try:
            subprocess.run([sys.executable, script_path], check=True)
            logger.info('   [SUCCESS] Context Generated.')
        except Exception as e:  # pylint: disable=broad-except
            logger.error('   [ERROR] Summary generation failed: %s', e)
    else:
        logger.error('   [ERROR] Script missing: %s', script_path)


def headless_fetch():
    """Fetches logs from all active remote shares without interaction."""
    print('--- HEADLESS LOG FETCH ---')
    status_map = get_status_map()

    for t in AgentUtils.TARGETS:
        name = t['name']
        t_status = status_map.get(name, {})

        if t_status.get('share_ok', False):
            AgentUtils.rescue_remote_log(t)
        else:
            logger.info('   [%s] SKIP (Share/Host Offline)', name)

    print('--- FETCH COMPLETE ---')


def headless_kill():
    """Sends labels KILL command to all active agents without interaction."""
    print('--- HEADLESS KILL SEQUENCE ---')
    status_map = get_status_map()

    kill_count = 0
    for t in AgentUtils.TARGETS:
        name = t['name']
        t_status = status_map.get(name, {})

        if t_status.get('agent_ok', False):
            logger.info('   [%s] Sending KILL...', name)
            if AgentUtils.send_agent_command(name, 'KILL', timeout=3):
                logger.info('      OK')
                kill_count += 1
            else:
                logger.warning('      FAIL')
        else:
            logger.info('   [%s] SKIP (Agent Offline)', name)

    if kill_count > 0:
        logger.info('Waiting 2s for file locks...')
        time.sleep(2)
    print('--- KILL SEQUENCE COMPLETE ---')


def main():
    """Main execution point for the agent console."""
    # --- HEADLESS MODES ---
    if len(sys.argv) > 1:
        if '--fetch-only' in sys.argv:
            headless_fetch()
            return
        if '--kill-all' in sys.argv:
            headless_kill()
            return

    # --- INTERACTIVE MODE ---
    while True:
        clear_screen()
        print('=' * 41)
        print('   REMOTE AGENT CONSOLE v5.5 (Decoupled)')
        print('=' * 41)

        status_map = get_status_map()

        for i, t in enumerate(AgentUtils.TARGETS):
            name = t['name']
            s = status_map.get(name, {})

            # Simple status indicator
            if s.get('agent_ok'):
                status_str = 'ONLINE'
            elif s.get('share_ok'):
                status_str = 'SHARE_ONLY'
            else:
                status_str = 'OFFLINE'

            print(f'   Target {i + 1}: {name:<15} [{status_str}]')

        print('-' * 41)
        print(' 1. KILL All Remotes (+ Logs + Summary)')
        print(' 2. LAUNCH All Remotes')
        print(' 3. PING All Remotes')
        print(' ' + '-' * 40)
        print(' 4. FETCH LOGS ONLY (Active Shares)')
        print(' 5. FETCH & SUMMARIZE (Manual Run)')
        print(' ' + '-' * 40)
        print(' Q. Return to Manager')
        print('=' * 41)

        choice = input('\nCommand: ').strip().upper()
        if choice == 'Q':
            break

        target_list = AgentUtils.TARGETS
        cmd = ''
        run_summary = False
        fetch_logs = False

        if choice == '1':
            cmd = 'KILL'
            fetch_logs = True
            run_summary = True
        elif choice == '2':
            cmd = 'LAUNCH'
        elif choice == '3':
            cmd = 'PING'
        elif choice == '4':
            headless_fetch()
            input('\nPress Enter...')
            continue
        elif choice == '5':
            headless_fetch()
            run_ai_summary()
            input('\nPress Enter...')
            continue

        if cmd:
            logger.info('\n--- EXECUTING: %s ---', cmd)
            current_status = get_status_map()

            for t in target_list:
                name = t['name']
                t_stat = current_status.get(name, {})

                # 1. Execute Command (If Agent Online)
                if t_stat.get('agent_ok', False):
                    AgentUtils.send_agent_command(name, cmd)
                else:
                    logger.info('   [%s] SKIP CMD (Agent Offline)', name)

                # 2. Fetch Log (If Share Online AND Requested)
                if fetch_logs:
                    if cmd == 'KILL' and t_stat.get('agent_ok', False):
                        # Give it a moment if we just killed it
                        time.sleep(0.5)

                    if t_stat.get('share_ok', False):
                        AgentUtils.rescue_remote_log(t)
                    else:
                        logger.warning('   [%s] SKIP LOG (Share Offline)', name)

            if run_summary:
                run_ai_summary()
            input('\nDone. Press Enter...')


if __name__ == '__main__':
    main()