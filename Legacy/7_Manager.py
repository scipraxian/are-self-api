"""Engineering Console and workflow manager for the UE Builder.

This module provides a command-line interface to manage the build pipeline,
monitor remote agents, and execute various build steps.
"""

import datetime
import glob
import json
import logging
import os
import subprocess
import sys

import PipelineConfig as config

# Configure logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
WORKFLOW_LOG = os.path.join(config.LOG_DIR, 'Manager_Workflow.log')

# --- WINDOWS FLAGS (The Magic Sauce) ---
# SW_SHOWNOACTIVATE (4): Displays a window in its most recent size and position.
# The active window remains active.
SW_SHOWNOACTIVATE = 4
SW_SHOWMINNOACTIVE = 7
STARTF_USESHOWWINDOW = 1


def get_startup_info(mode='inactive'):
    """Creates Windows-specific startup info to prevent focus stealing.

    Args:
        mode (str): The window mode ('minimized' or 'inactive').

    Returns:
        subprocess.STARTUPINFO or None: The startup info object if on Windows.
    """
    if sys.platform != 'win32':
        return None

    si = subprocess.STARTUPINFO()
    si.dwFlags |= STARTF_USESHOWWINDOW

    if mode == 'minimized':
        si.wShowWindow = SW_SHOWMINNOACTIVE
    else:
        si.wShowWindow = SW_SHOWNOACTIVATE

    return si


class EngineeringConsole:
    """Main console interface for managing the build pipeline."""

    def __init__(self):
        """Initializes the EngineeringConsole."""
        self._monitor_process = None

    def _clear_screen(self):
        """Clears the console screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _log_workflow(self, message: str):
        """Logs a message to both the console and the workflow log file.

        Args:
            message (str): The message to log.
        """
        timestamp = datetime.datetime.now().strftime('[%H:%M:%S]')
        line = f'{timestamp} {message}'
        print(line)
        try:
            if not os.path.exists(config.LOG_DIR):
                os.makedirs(config.LOG_DIR)
            with open(WORKFLOW_LOG, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:  # pylint: disable=broad-except
            pass

    def start_monitor(self):
        """Starts the background status daemon minimized."""
        script_path = os.path.join(config.BUILDER_DIR, 'AgentMonitor.py')
        if os.path.exists(script_path):
            self._monitor_process = subprocess.Popen(
                [sys.executable, script_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=get_startup_info('minimized')
            )

    def stop_monitor(self):
        """Stops the background status daemon."""
        if self._monitor_process:
            self._monitor_process.terminate()

    def _get_status_display(self):
        """Gets the status lines for display in the console.

        Returns:
            list: A list of strings representing the status of remote targets.
        """
        if not os.path.exists(config.STATUS_FILE):
            return ['   (Initializing Monitor...)']
        try:
            with open(config.STATUS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            lines = []
            for target in config.REMOTE_TARGETS:
                name = target['name']
                info = data.get(name, {})
                share_str = 'SHARE:OK' if info.get('share_ok') else 'SHARE:--'
                agent_str = 'AGENT:OK' if info.get('agent_ok') else 'AGENT:--'
                lines.append(f'   [{name:<15}]  {share_str}  |  {agent_str}')
            return lines
        except Exception:  # pylint: disable=broad-except
            return ['   (Reading Status...)']

    def _find_script(self, script_name):
        """Finds the absolute path of a script.

        Args:
            script_name (str): The name of the script file.

        Returns:
            str or None: The absolute path if found, None otherwise.
        """
        path = os.path.join(config.BUILDER_DIR, script_name)
        return path if os.path.exists(path) else None

    def _launch_step_new_window(self, step_name, script_name, args=None):
        """Launches a build step in a new console window.

        Args:
            step_name (str): Human-readable name of the step.
            script_name (str): Filename of the script to run.
            args (list, optional): List of command-line arguments.

        Returns:
            bool: True if the step launched and finished successfully.
        """
        if args is None:
            args = []
        script_path = self._find_script(script_name)
        if not script_path:
            self._log_workflow(f'[ERROR] Script not found: {script_name}')
            return False

        self._log_workflow(f'>>> STARTING: {step_name} ({script_name})')
        python_exe = sys.executable
        arg_string = ' '.join(args)
        inner_cmd = f'"{python_exe}" "{script_path}" {arg_string}'
        wrapper_cmd = f'cmd /c "{inner_cmd} || pause"'

        try:
            # Launch with NO ACTIVATE flag
            process = subprocess.Popen(
                wrapper_cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=config.BUILDER_DIR,
                startupinfo=get_startup_info('inactive')
            )
            process.wait()
            self._log_workflow(f'    Finished: {step_name}')
            return True
        except Exception as e:
            self._log_workflow(f'!!! EXCEPTION in {step_name}: {e}')
            return False

    def _aggregate_logs(self):
        """Aggregates local and remote logs into a single session log file."""
        self._log_workflow('Aggregating Local and Remote logs...')
        timestamp = datetime.datetime.now().strftime('%H%M%S')
        combined_filename = f'Local_And_Remote_Logs_{timestamp}.log'
        combined_path = os.path.join(config.LOG_DIR, combined_filename)
        local_log_src = os.path.join(config.LOG_DIR, 'UATApp.log')

        with open(combined_path, 'w', encoding='utf-8') as outfile:
            outfile.write('=' * 51 + '\n')
            outfile.write(f'   AGGREGATED SESSION LOG - {timestamp}\n')
            outfile.write('=' * 51 + '\n\n')

            if os.path.exists(local_log_src):
                outfile.write('=== LOCAL CLIENT LOG (Host) ===\n')
                try:
                    with open(
                        local_log_src, 'r', encoding='utf-8', errors='replace'
                    ) as f:
                        outfile.write(f.read())
                except Exception:  # pylint: disable=broad-except
                    pass
                outfile.write('\n\n')

            remote_logs = glob.glob(os.path.join(config.LOG_DIR, '*_Agent.log'))
            for remote_log in remote_logs:
                agent_name = os.path.basename(
                    remote_log
                ).replace('_Agent.log', '')
                outfile.write(f'=== REMOTE AGENT LOG ({agent_name}) ===\n')
                try:
                    with open(
                        remote_log, 'r', encoding='utf-8', errors='replace'
                    ) as f:
                        outfile.write(f.read())
                except Exception:  # pylint: disable=broad-except
                    pass
                outfile.write('\n\n')

        self._log_workflow(f'Combined log created: {combined_filename}')

    def run_smart_workflow(self):
        """Executes the smart build and distribution workflow."""
        print('\n--- STEP 1: UAT BUILD ---')
        if not self._launch_step_new_window('UAT Build', '4_UAT_Build.py'):
            return

        print('\n--- STEP 2: SMOKE TEST (Local) ---')
        self._launch_step_new_window('Smoke Test', '5_UAT_Run.py', ['-AutoClose'])

        print('\n--- STEP 3: PARALLEL DISTRIBUTION ---')
        self._launch_step_new_window(
            'Parallel Distribute', '6_Parallel_Distribute.py'
        )

        print('\n>>> LAUNCHING LOCAL HOST. PLAY THE GAME NOW. <<<')
        self._launch_step_new_window('Host Session', '5_UAT_Run.py')

        print('\n>>> HOST CLOSED. TERMINATING REMOTES... <<<')
        self._launch_step_new_window(
            'Stop Remotes', '9_AgentConsole.py', ['--kill-all']
        )

        print('\n>>> FETCHING REMOTE LOGS... <<<')
        script_path = self._find_script('9_AgentConsole.py')
        if script_path:
            subprocess.run(
                [sys.executable, script_path, '--fetch-only'],
                cwd=config.BUILDER_DIR,
                check=False
            )

        self._aggregate_logs()
        input('\n[DONE] Workflow Complete. Press Enter...')

    def main_loop(self):
        """Main interaction loop for the engineering console."""
        self.start_monitor()
        try:
            while True:
                self._clear_screen()
                print('=' * 55)
                print(f'   {config.PROJECT_NAME} - ENGINEERING CONSOLE 5.5')
                print('=' * 55)

                status_lines = self._get_status_display()
                for line in status_lines:
                    print(line)

                print('-' * 55)
                print(' 1.  FULL PIPELINE')
                print(' 2.  SMART WORKFLOW (Async Distribute)')
                print(' ' + '-' * 54)
                print(' 2B. Smoke Test Only (-AutoClose)')
                print(' 3.  UAT: Build Only')
                print(' 4.  UAT: Run Only (Local)')
                print(' 5.  Distribute Only (Parallel)')
                print(' ' + '-' * 54)
                print(' 20. Maintenance: Clean Logs')
                print(' 21. Maintenance: Generate AI Context')
                print(' 22. Maintenance: Deep Clean')
                print(' 23. REMOTE: Agent Console')
                print(' 24. REMOTE: Update Agent Scripts')
                print(' Q.  Quit')
                print('=' * 55)

                choice = input('\nSelect Option: ').strip().upper()
                if choice == '1':
                    self._launch_step_new_window(
                        'Full Pipeline', '0_Unattended.py',
                        ['--clean-logs', '--start-at', '0.5']
                    )
                elif choice == '2':
                    self.run_smart_workflow()
                elif choice == '2B':
                    self._launch_step_new_window(
                        'Smoke Test', '5_UAT_Run.py', ['-AutoClose']
                    )
                elif choice == '3':
                    self._launch_step_new_window('UAT Build', '4_UAT_Build.py')
                elif choice == '4':
                    self._launch_step_new_window('UAT Run', '5_UAT_Run.py')
                elif choice == '5':
                    self._launch_step_new_window(
                        'Parallel Distribute', '6_Parallel_Distribute.py'
                    )
                elif choice == '20':
                    self._launch_step_new_window(
                        'Clean Logs', '0_Unattended.py',
                        ['--clean-logs', '--start-at', '100']
                    )
                elif choice == '21':
                    self._launch_step_new_window('Gen Context', '6_5_FeedTheAI.py')
                elif choice == '22':
                    self._launch_step_new_window(
                        'Deep Clean', '8_CleanArtifacts.py'
                    )
                elif choice == '23':
                    subprocess.Popen(
                        [sys.executable, os.path.join(
                            config.BUILDER_DIR, '9_AgentConsole.py'
                        )],
                        creationflags=0x00000010,
                        cwd=config.BUILDER_DIR
                    )
                elif choice == '24':
                    self._launch_step_new_window(
                        'Update Agents', '10_UpdateRemoteAgents.py'
                    )
                elif choice == 'Q':
                    break
        finally:
            self.stop_monitor()
            sys.exit(0)


if __name__ == '__main__':
    console = EngineeringConsole()
    console.main_loop()