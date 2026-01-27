import asyncio
import json
import logging
import socket
from typing import List, Optional, Tuple

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from talos_agent.models import TalosAgentRegistry, TalosAgentStatus

logger = logging.getLogger(__name__)

# Default configuration if not in settings
DEFAULT_SUBNET = getattr(settings, 'TALOS_SUBNET', '192.168.1.')
DEFAULT_PORT = getattr(settings, 'TALOS_PORT', 5005)
SCAN_TIMEOUT = 1.0  # Seconds per IP (fast fail)


class TalosAgentFinder:
    """
    Async Hunter-Seeker for Talos Agents.
    Scans a subnet for Port 5005, verifies the protocol, and registers the agent.
    """

    def __init__(
        self, subnet_prefix: str = DEFAULT_SUBNET, port: int = DEFAULT_PORT
    ):
        self.subnet_prefix = subnet_prefix
        self.port = port

    def scan_and_register(self) -> List[str]:
        """
        Synchronous entry point for Celery tasks.
        Returns a list of hostnames found/updated.
        """
        return asyncio.run(self._async_scan())

    async def _async_scan(self) -> List[str]:
        """
        Scans 1..254 concurrently.
        """
        tasks = []
        # Create a task for every IP in the subnet
        for i in range(1, 255):
            ip = f'{self.subnet_prefix}{i}'
            tasks.append(self._check_agent(ip))

        logger.info(
            f'Scanning {len(tasks)} IPs on {self.subnet_prefix}x:{self.port}...'
        )

        # Run all probes in parallel
        results = await asyncio.gather(*tasks)

        # Filter out None results (failed probes)
        found_agents = [res for res in results if res is not None]

        # Register them in the DB
        registered_names = []
        for agent_data in found_agents:
            name = await self._register_agent_in_db(agent_data)
            registered_names.append(name)

        return registered_names

    async def _check_agent(self, ip: str) -> Optional[dict]:
        """
        Attempts a TCP handshake with a potential agent.
        Sends: {"cmd": "PING"}
        Expects: {"status": "PONG", "hostname": "...", "version": "..."}
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, self.port), timeout=SCAN_TIMEOUT
            )
        except (OSError, asyncio.TimeoutError):
            return None

        try:
            # 1. Send PING
            payload = json.dumps({'cmd': 'PING'}) + '\n'
            writer.write(payload.encode('utf-8'))
            await writer.drain()

            # 2. Read PONG
            data = await asyncio.wait_for(
                reader.read(4096), timeout=SCAN_TIMEOUT
            )
            response = json.loads(data.decode('utf-8'))

            if response.get('status') == 'PONG':
                # Success!
                return {
                    'ip': ip,
                    'hostname': response.get('hostname', 'Unknown'),
                    'version': response.get('version', '0.0.0'),
                }
        except Exception as e:
            logger.debug(f'Handshake failed for {ip}: {e}')
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        return None

    @sync_to_async
    def _register_agent_in_db(self, data: dict) -> str:
        """
        Updates or Creates the Agent Registry record.
        """
        hostname = data['hostname'].upper()
        # Strip domain if present (e.g., "WORKSTATION.LOCAL" -> "WORKSTATION")
        if '.' in hostname:
            hostname = hostname.split('.')[0]

        agent, created = TalosAgentRegistry.objects.update_or_create(
            hostname=hostname,
            defaults={
                'ip_address': data['ip'],
                'version': data['version'],
                'status_id': TalosAgentStatus.ONLINE,
                'last_seen': timezone.now(),
            },
        )

        action = 'Created' if created else 'Updated'
        logger.info(
            f'[{action}] Agent {hostname} at {data["ip"]} (v{data["version"]})'
        )
        return hostname
