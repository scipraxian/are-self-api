import asyncio
import json
import logging
from typing import List, Optional

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from talos_agent.models import TalosAgentRegistry, TalosAgentStatus

logger = logging.getLogger(__name__)


# --- 1. CONSTANTS ---


class TalosDiscoveryConstants:
    """Centralized constants to eliminate string literals."""

    # Config Defaults
    DEFAULT_SUBNET_PREFIX = getattr(settings, 'TALOS_SUBNET', '192.168.1.')
    DEFAULT_PORT = getattr(settings, 'TALOS_PORT', 5005)
    SCAN_TIMEOUT = 1.0
    ENCODING = 'utf-8'

    # Protocol Keys
    K_CMD = 'cmd'
    K_STATUS = 'status'
    K_HOSTNAME = 'hostname'
    K_VERSION = 'version'

    # Protocol Values
    CMD_PING = 'PING'
    VAL_PONG = 'PONG'
    VAL_UNKNOWN = 'Unknown'
    VAL_VER_ZERO = '0.0.0'


# --- 2. CORE FUNCTIONS ---


def scan_and_register(
    subnet_prefix: str = TalosDiscoveryConstants.DEFAULT_SUBNET_PREFIX,
    port: int = TalosDiscoveryConstants.DEFAULT_PORT,
) -> List[str]:
    """
    Main Entry Point (Synchronous).
    Orchestrates the async scan and synchronous DB registration.
    """
    return asyncio.run(_run_async_scan(subnet_prefix, port))


async def _run_async_scan(subnet_prefix: str, port: int) -> List[str]:
    """
    Orchestrator: Generates IPs, awaits probes, and triggers registration.
    """
    tasks = []
    # Generate IPs 1..254
    for i in range(1, 255):
        ip = f'{subnet_prefix}{i}'
        tasks.append(_probe_agent_address(ip, port))

    logger.info(f'Scanning {len(tasks)} IPs on {subnet_prefix}x:{port}...')

    # Concurrent Execution
    results = await asyncio.gather(*tasks)

    # Filter Failures (None) - We now have a list of unsaved TalosAgentRegistry objects
    found_agents: List[TalosAgentRegistry] = [
        res for res in results if res is not None
    ]

    # Register Successes
    registered_names = []
    for agent_dto in found_agents:
        # Pass the DTO (Data Transfer Object) to the DB handler
        name = await _register_agent_in_db(agent_dto)
        registered_names.append(name)

    return registered_names


async def _probe_agent_address(
    ip: str, port: int
) -> Optional[TalosAgentRegistry]:
    """
    Network I/O: Attempts a TCP handshake and PING/PONG.
    Returns an UNSAVED TalosAgentRegistry instance as a DTO.
    """
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=TalosDiscoveryConstants.SCAN_TIMEOUT,
        )

        # 1. Send PING
        request = {
            TalosDiscoveryConstants.K_CMD: TalosDiscoveryConstants.CMD_PING
        }
        payload = json.dumps(request) + '\n'

        writer.write(payload.encode(TalosDiscoveryConstants.ENCODING))
        await writer.drain()

        # 2. Read Response
        data = await asyncio.wait_for(
            reader.read(4096), timeout=TalosDiscoveryConstants.SCAN_TIMEOUT
        )

        if not data:
            return None

        response = json.loads(data.decode(TalosDiscoveryConstants.ENCODING))

        # 3. Validate PONG and Populate DTO
        if (
            response.get(TalosDiscoveryConstants.K_STATUS)
            == TalosDiscoveryConstants.VAL_PONG
        ):
            # DRY: We instantiate the model directly.
            # We explicitly set status_id to ONLINE (integer) to avoid DB lookup.
            return TalosAgentRegistry(
                ip_address=ip,
                hostname=response.get(
                    TalosDiscoveryConstants.K_HOSTNAME,
                    TalosDiscoveryConstants.VAL_UNKNOWN,
                ),
                version=response.get(
                    TalosDiscoveryConstants.K_VERSION,
                    TalosDiscoveryConstants.VAL_VER_ZERO,
                ),
                status_id=TalosAgentStatus.ONLINE,
            )

    except (OSError, asyncio.TimeoutError, json.JSONDecodeError):
        pass
    except Exception as e:
        logger.debug(f'Probe error for {ip}: {e}')
    finally:
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    return None


@sync_to_async
def _register_agent_in_db(dto: TalosAgentRegistry) -> str:
    """
    Database I/O: Merges the DTO into the persistent database record.
    """
    # Clean Hostname (remove domain)
    raw_hostname = dto.hostname.upper()
    if '.' in raw_hostname:
        clean_hostname = raw_hostname.split('.')[0]
    else:
        clean_hostname = raw_hostname

    # 1. Get or Create (Identifier Only)
    # We use the clean hostname as the unique key
    agent, created = TalosAgentRegistry.objects.get_or_create(
        hostname=clean_hostname, defaults={'status_id': TalosAgentStatus.ONLINE}
    )

    # 2. Update Mutable Fields from DTO
    agent.ip_address = dto.ip_address
    agent.version = dto.version
    agent.last_seen = timezone.now()

    # Always mark online if we just heard from it
    agent.status_id = TalosAgentStatus.ONLINE

    agent.save()

    log_action = 'Created' if created else 'Updated'
    logger.info(f'[{log_action}] Agent {clean_hostname} at {agent.ip_address}')

    return clean_hostname
