import asyncio
import json
import logging
from typing import List, NamedTuple, Optional, Tuple

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from peripheral_nervous_system.models import NerveTerminalRegistry, NerveTerminalStatus

logger = logging.getLogger(__name__)

# Single scan-in-progress lock. Guards against the view-triggered scan
# stampede where post_save acetylcholine from the first scan causes the
# frontend to re-list which would re-kick the scan. Held for the duration
# of a single _run_async_scan call.
_SCAN_LOCK = asyncio.Lock()


# --- 1. CONSTANTS & TYPES ---


class DiscoveryConstants:
    """Centralized constants for the discovery protocol."""

    DEFAULT_SUBNET_PREFIX = getattr(settings, 'ARE_SELF_SUBNET', '192.168.1.')
    DEFAULT_PORT = getattr(settings, 'ARE_SELF_PORT', 5005)
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
    subnet_prefix: str = DiscoveryConstants.DEFAULT_SUBNET_PREFIX,
    port: int = DiscoveryConstants.DEFAULT_PORT,
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
    Orchestrator: Scans the subnet and reconciles NerveTerminalRegistry.

    Flow:
        1. Launch all probes in parallel.
        2. As each PONG arrives, upsert that agent to ONLINE. The
           registrar is compare-then-save so a no-op scan does not
           fire acetylcholine.
        3. After all probes finish, any currently non-OFFLINE row that
           was NOT seen this round is flipped to OFFLINE (per-row
           .save() so each dying card gets its own neurotransmitter).

    There is no CHECKING transient write: those per-row saves turned
    every scan into a broadcast storm that made the UI churn. Only real
    state transitions are written to the DB.

    Re-entry is guarded by _SCAN_LOCK: if a scan is already running, this
    call returns immediately with an empty list.
    """
    if _SCAN_LOCK.locked():
        logger.info('Scan already in progress; skipping re-entrant scan.')
        return []

    async with _SCAN_LOCK:
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

        # 3. Register ONLINE (Serial DB Writes, no-op save when unchanged)
        registered_names = []
        registered_ids = set()
        for identity in found_identities:
            name = await _register_agent_in_db(identity)
            registered_names.append(name)
            registered_ids.add(identity.unique_id)

        # 4. Anything non-OFFLINE that we did not see this round is
        #    unreachable -> OFFLINE.
        await _mark_unreachable_offline(registered_ids)

        return registered_names


@sync_to_async
def _mark_unreachable_offline(found_ids: set) -> int:
    """Flip live NerveTerminalRegistry rows that did not PONG to OFFLINE.

    "Live" means any row whose status is not already OFFLINE. Rows whose
    unique id was registered this round are excluded (they were just
    upserted to ONLINE).

    Iterates and .save()s individually so each row's post_save fires its
    own acetylcholine -- these are real state transitions and the UI
    should see them.

    Returns the number of rows transitioned, for logging/tests.
    """
    count = 0
    with transaction.atomic():
        stale_qs = NerveTerminalRegistry.objects.exclude(
            status_id=NerveTerminalStatus.OFFLINE
        ).exclude(id__in=found_ids)
        for terminal in stale_qs:
            terminal.status_id = NerveTerminalStatus.OFFLINE
            terminal.save(update_fields=['status', 'modified'])
            count += 1
    if count:
        logger.info(f'Marked {count} unreachable nerve terminals OFFLINE.')
    return count


async def _probe_agent(ip: str, port: int) -> Optional[AgentIdentity]:
    """Single-step handshake: Connect -> PING -> Read UUID from PONG."""
    reader, writer = None, None

    # --- BLOCK 1: ESTABLISH CONNECTION ---
    # We expect timeouts and connection refusals here during a subnet scan.
    # These should be handled silently or with debug logs only.
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=DiscoveryConstants.SCAN_TIMEOUT,
        )
    except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
        # Host is likely offline or port is closed.
        return None

    # --- BLOCK 2: PROTOCOL EXECUTION ---
    try:
        # 1. Send PING
        ping_req = {
            DiscoveryConstants.K_CMD: DiscoveryConstants.CMD_PING
        }
        writer.write(
            (json.dumps(ping_req) + '\n').encode(
                DiscoveryConstants.ENCODING
            )
        )
        await writer.drain()

        # 2. Read Response
        raw_data = await asyncio.wait_for(
            reader.read(4096), timeout=DiscoveryConstants.SCAN_TIMEOUT
        )

        if not raw_data:
            logger.debug(f'[{ip}] Socket closed remotely during handshake.')
            return None

        # 3. Parse & Validate
        decoded_data = raw_data.decode(DiscoveryConstants.ENCODING)
        data = json.loads(decoded_data)

        if (
            data.get(DiscoveryConstants.K_STATUS)
            != DiscoveryConstants.VAL_PONG
        ):
            logger.warning(
                f'[{ip}] Protocol Mismatch: Expected PONG, got {data.get(DiscoveryConstants.K_STATUS)}'
            )
            return None

        agent_uuid = data.get(DiscoveryConstants.K_UUID)
        if not agent_uuid:
            logger.error(f'[{ip}] Agent handshake failed: Missing UUID field.')
            return None

        # 4. Success DTO
        return AgentIdentity(
            unique_id=agent_uuid,
            ip_address=ip,
            hostname=data.get(
                DiscoveryConstants.K_HOSTNAME,
                DiscoveryConstants.VAL_UNKNOWN,
            ),
            version=data.get(
                DiscoveryConstants.K_VERSION,
                DiscoveryConstants.VAL_VER_ZERO,
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
    """Upsert RemoteTarget based on Hardware UUID and Status ID.

    Compare-then-save: if the row already exists and (status, ip, version)
    already match the discovered identity, this function does NOT touch
    the database. That no-op is the whole point -- it prevents a stable
    agent from firing an acetylcholine broadcast on every scan and
    triggering a frontend refetch storm. last_seen is intentionally left
    stale in the no-op path; it is advisory, not load-bearing.
    """

    # Validation: Ensure we have the NamedTuple before accessing unique_id
    if not hasattr(identity, 'unique_id'):
        logger.error(f'Invalid identity object: {identity}')
        return 'Unknown'

    normalized_hostname = identity.hostname.upper().split('.')[0]

    try:
        existing = NerveTerminalRegistry.objects.get(id=identity.unique_id)
    except NerveTerminalRegistry.DoesNotExist:
        existing = None

    if existing is not None:
        unchanged = (
            existing.status_id == NerveTerminalStatus.ONLINE
            and existing.ip_address == identity.ip_address
            and existing.version == identity.version
        )
        if unchanged:
            logger.debug(
                '[Unchanged] %s (%s) -- skipping no-op save',
                existing.hostname,
                existing.ip_address,
            )
            return existing.hostname

        existing.hostname = normalized_hostname
        existing.ip_address = identity.ip_address
        existing.version = identity.version
        existing.last_seen = timezone.now()
        existing.status_id = NerveTerminalStatus.ONLINE
        existing.save(update_fields=[
            'hostname',
            'ip_address',
            'version',
            'last_seen',
            'status',
            'modified',
        ])
        logger.info(f'[Updated] {existing.hostname} ({existing.ip_address})')
        return existing.hostname

    target = NerveTerminalRegistry.objects.create(
        id=identity.unique_id,
        hostname=normalized_hostname,
        ip_address=identity.ip_address,
        version=identity.version,
        last_seen=timezone.now(),
        status_id=NerveTerminalStatus.ONLINE,
    )
    logger.info(f'[Registered] {target.hostname} ({target.ip_address})')
    return target.hostname
