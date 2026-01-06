"""Remote agent diagnostic tool to verify connectivity and protocol.

This script performs ICMP pings, TCP port checks, and a protocol handshake
(PING/PONG) with remote agents to ensure they are reachable and responsive.
"""

import logging
import socket
import subprocess
import sys

# Configure logging
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
AGENT_PORT = 5005
TARGETS = [
    'DREWDESK01',
    'MIKE-DESKTOP-1'
]


def print_header(text):
    """Prints a formatted header to the console.

    Args:
        text (str): The header text to display.
    """
    print('\n' + '=' * 60)
    print(f'   {text}')
    print('=' * 60)


def check_icmp_ping(host):
    """Checks if a host responds to ICMP pings.

    Args:
        host (str): The hostname or IP to ping.

    Returns:
        bool: True if the host is reachable, False otherwise.
    """
    logger.info('[1/3] ICMP Ping (%s)... ', host)
    try:
        # -n 1 = 1 packet, -w 1000 = 1000ms timeout
        cmd = ['ping', '-n', '1', '-w', '1000', host]
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False
        )
        if result.returncode == 0:
            logger.info('PASS (Host is Online)')
            return True

        logger.warning('FAIL (Host Unreachable or Blocking Ping)')
        return False
    except Exception as e:  # pylint: disable=broad-except
        logger.error('ERROR (%s)', e)
        return False


def check_tcp_port(host):
    """Checks if the agent's TCP port is open on the host.

    Args:
        host (str): The hostname or IP to check.

    Returns:
        bool: True if the port is open, False otherwise.
    """
    logger.info('[2/3] TCP Port Test (%s:%d)... ', host, AGENT_PORT)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)  # 2 second timeout
    try:
        result = sock.connect_ex((host, AGENT_PORT))
        if result == 0:
            logger.info('PASS (Port Open)')
            sock.close()
            return True

        logger.warning('FAIL (Error Code: %s)', result)
        logger.info(
            '      > Hint: The Agent might not be running, or Firewall '
            'is blocking.'
        )
        sock.close()
        return False
    except Exception as e:  # pylint: disable=broad-except
        logger.error('ERROR (%s)', e)
        return False


def check_agent_protocol(host):
    """Performs a PING/PONG protocol handshake with the remote agent.

    Args:
        host (str): The hostname or IP of the agent.

    Returns:
        bool: True if the protocol handshake succeeds, False otherwise.
    """
    logger.info('[3/3] Agent Protocol Handshake...')
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect((host, AGENT_PORT))

            # Send PING
            s.sendall(b'PING')

            # Wait for PONG
            data = s.recv(1024).decode('utf-8').strip()

            if data == 'PONG':
                logger.info(' PASS (Received \'PONG\')')
                return True

            logger.warning(' FAIL (Received \'%s\', expected \'PONG\')', data)
            return False
    except Exception as e:  # pylint: disable=broad-except
        logger.error('\n      > Protocol Failed: %s', e)
        return False


def main():
    """Main diagnostic loop for all configured targets."""
    print_header('REMOTE AGENT DIAGNOSTIC TOOL')

    for host in TARGETS:
        print(f'\n--- TARGET: {host} ---')

        # Step 1: Ping
        if not check_icmp_ping(host):
            logger.info('   [STOP] Host offline. Cannot proceed.')
            continue

        # Step 2: Port
        if not check_tcp_port(host):
            print('\n   !!! FIREWALL ACTION REQUIRED !!!')
            print(f'   Run this command on {host} (Admin CMD):')
            print(
                f'   netsh advfirewall firewall add rule name="HSH Agent" '
                f'dir=in action=allow protocol=TCP localport={AGENT_PORT}'
            )
            continue

        # Step 3: Protocol
        if check_agent_protocol(host):
            logger.info('\n   [SUCCESS] %s is fully operational.', host)
        else:
            logger.warning('\n   [WARNING] Connection made, but Agent logic failed.')

    print('\n[DONE] Test Complete.')
    input('\nPress Enter to exit...')


if __name__ == '__main__':
    main()