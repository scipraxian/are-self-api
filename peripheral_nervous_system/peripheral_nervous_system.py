import asyncio
import json
import logging
from typing import List, NamedTuple, Optional, Tuple

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from peripheral_nervous_system.models import NerveTerminalRegistry, NerveTerminalStatus

logger = logging.getLogger(__name__)


# --- 1. CONSTANTS & TYPES ---


class TalosDiscoveryConstants:
    """Centralized constants for the discovery protocol."""

    DEFAULT_SUBNET_PREFIX = getattr(settings, 'TALOS_SUBNET', '192.168.1.')
    DEFAULT_PORT = getattr(settings, 'TALOS_PORT', 5005)
    SCAN_TIMEOUT = 1.5  # Fast timeout for ping-only
    ENCODING = 'utf-8'

    # Protocol Keys
    K_CMD = 'cmd'
    K_STATUS = 'status'
    K_HOSTNAME = 'hostname'
    K_VERSION = 'version'
    K_UUID = 'uuid'

    # Values
    CMD_PING = 'PING'
    VAL_PONG = 'PONG'
    VAL_UNKNOWN = 'Unknown'
    VAL_VER_ZERO = '0.0.0'


class AgentIdentity(NamedTuple):
    """Immutable DTO for a discovered agent."""

    unique_id: str
    ip_address: str
    hostname: str
    version: str


# --- 2. CORE FUNCTIONS ---
async def scan_and_register(
    spike_id: str,
    subnet_prefix: str = TalosDiscoveryConstants.DEFAULT_SUBNET_PREFIX,
    port: int = TalosDiscoveryConstants.DEFAULT_PORT,
) -> Tuple[int, str]:
    """Asynchronous entry point for agent discovery."""

    # _run_async_scan already probes and saves to DB, returning List[str]
    registered_names = await _run_async_scan(subnet_prefix, port)

    log_output = f'Scan complete. Found {len(registered_names)} agents.'
    if registered_names:
        log_output += f' Registered/Updated: {", ".join(registered_names)}'

    # Return (Success Code 200, Log String) for NeuroMuscularJunction
    return 200, log_output


async def _run_async_scan(subnet_prefix: str, port: int) -> List[str]:
    """
    Orchestrator: Scans subnet asynchronously and registers found agents.
    """
    # 1. Launch Probes (Parallel)
    tasks = []
    # Scan 1-254
    for i in range(1, 255):
        ip = f'{subnet_prefix}{i}'
        tasks.append(_probe_agent(ip, port))

    logger.info(f'Scanning subnet {subnet_prefix}x on port {port}...')

    # 2. Gather Results
    results = await asyncio.gather(*tasks)
    found_identities = [res for res in results if res is not None]

    logger.info(f'Scan complete. Found {len(found_identities)} agents.')

    # 3. Register (Serial DB Writes)
    registered_names = []
    for identity in found_identities:
        name = await _register_agent_in_db(identity)
        registered_names.append(name)

    return registered_names


async def _probe_agent(ip: str, port: int) -> Optional[AgentIdentity]:
    """Single-step handshake: Connect -> PING -> Read UUID from PONG."""
    reader, writer = None, None

    # --- BLOCK 1: ESTABLISH CONNECTION ---
    # We expect timeouts and connection refusals here during a subnet scan.
    # These should be handled silently or with debug logs only.
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=TalosDiscoveryConstants.SCAN_TIMEOUT,
        )
    except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
        # Host is likely offline or port is closed.
        return None

    # --- BLOCK 2: PROTOCOL EXECUTION ---
    try:
        # 1. Send PING
        ping_req = {
            TalosDiscoveryConstants.K_CMD: TalosDiscoveryConstants.CMD_PING
        }
        writer.write(
            (json.dumps(ping_req) + '\n').encode(
                TalosDiscoveryConstants.ENCODING
            )
        )
        await writer.drain()

        # 2. Read Response
        raw_data = await asyncio.wait_for(
            reader.read(4096), timeout=TalosDiscoveryConstants.SCAN_TIMEOUT
        )

        if not raw_data:
            logger.debug(f'[{ip}] Socket closed remotely during handshake.')
            return None

        # 3. Parse & Validate
        decoded_data = raw_data.decode(TalosDiscoveryConstants.ENCODING)
        data = json.loads(decoded_data)

        if (
            data.get(TalosDiscoveryConstants.K_STATUS)
            != TalosDiscoveryConstants.VAL_PONG
        ):
            logger.warning(
                f'[{ip}] Protocol Mismatch: Expected PONG, got {data.get(TalosDiscoveryConstants.K_STATUS)}'
            )
            return None

        agent_uuid = data.get(TalosDiscoveryConstants.K_UUID)
        if not agent_uuid:
            logger.error(f'[{ip}] Agent handshake failed: Missing UUID field.')
            return None

        # 4. Success DTO
        return AgentIdentity(
            unique_id=agent_uuid,
            ip_address=ip,
            hostname=data.get(
                TalosDiscoveryConstants.K_HOSTNAME,
                TalosDiscoveryConstants.VAL_UNKNOWN,
            ),
            version=data.get(
                TalosDiscoveryConstants.K_VERSION,
                TalosDiscoveryConstants.VAL_VER_ZERO,
            ),
        )

    except json.JSONDecodeError as e:
        logger.error(f'[{ip}] Handshake failed: Malformed JSON response. {e}')
        return None
    except (asyncio.TimeoutError, OSError) as e:
        logger.warning(f'[{ip}] Handshake interrupted (I/O Error): {e}')
        return None
    finally:
        # Robust Cleanup
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


@sync_to_async
def _register_agent_in_db(identity: AgentIdentity) -> str:
    """Upsert RemoteTarget based on Hardware UUID and Status ID."""

    # Validation: Ensure we have the NamedTuple before accessing unique_id
    if not hasattr(identity, 'unique_id'):
        logger.error(f'Invalid identity object: {identity}')
        return 'Unknown'

    target, created = NerveTerminalRegistry.objects.update_or_create(
        id=identity.unique_id,
        defaults=dict(
            hostname=identity.hostname.upper().split('.')[0],
            ip_address=identity.ip_address,
            version=identity.version,
            last_seen=timezone.now(),
            status_id=NerveTerminalStatus.ONLINE,
        ),
    )

    action = 'Registered' if created else 'Updated'
    logger.info(f'[{action}] {target.hostname} ({target.ip_address})')
    return target.hostname
