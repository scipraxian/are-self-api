"""Canonical gateway-to-reasoning bridge.

This module is the single entrypoint for wiring gateway transport into the
Are-Self reasoning engine.  It reuses the Thalamus ``inject_swarm_chatter``
pattern so that adapter-driven personal-agent messages and Thalamus chat
messages follow the same canonical runtime path.

Key Functions
=============
``wake_reasoning``
    Queue a user message and, when necessary, create a Spike and fire it so
    that ``FrontalLobe.run()`` picks up the message.
``handle_interrupt``
    Set the active Spike to STOPPING so the reasoning loop exits gracefully.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from central_nervous_system.models import (
    NeuralPathway,
    Neuron,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from talos_gateway.models import GatewaySession
from thalamus.thalamus import inject_swarm_chatter

logger = logging.getLogger('talos_gateway.runtime')

# Statuses where the session already has a viable spike and just needs a
# message queued (and possibly a wake-up via inject_swarm_chatter).
_INJECTABLE_STATUSES = frozenset({
    ReasoningStatusID.ACTIVE,
    ReasoningStatusID.PENDING,
    ReasoningStatusID.ATTENTION_REQUIRED,
})


def wake_reasoning(
    gateway_session: GatewaySession,
    reasoning_session: ReasoningSession,
    content: str,
    role: str = 'user',
) -> dict[str, Any]:
    """Queue a user message and wake reasoning if needed.

    This is the canonical gateway entrypoint.  It delegates to
    ``inject_swarm_chatter`` for queue+wake semantics and creates a fresh
    Spike when the session has none or has already terminated.

    Args:
        gateway_session: The platform-level session row.
        reasoning_session: The reasoning session to target.
        content: The user message text.
        role: Message role (default ``'user'``).

    Returns:
        Dict with ``success``, ``action`` (``'queued'``, ``'woken'``, or
        ``'spawned'``), and ``session_id``.
    """
    has_spike = reasoning_session.spike_id is not None
    status = reasoning_session.status_id

    if has_spike and status in _INJECTABLE_STATUSES:
        was_waiting = status == ReasoningStatusID.ATTENTION_REQUIRED
        inject_swarm_chatter(reasoning_session, role=role, text=content)
        action = 'woken' if was_waiting else 'queued'
        logger.info(
            '[Gateway] %s message on session %s (action=%s).',
            role,
            reasoning_session.pk,
            action,
        )
        return {
            'success': True,
            'action': action,
            'session_id': str(reasoning_session.pk),
        }

    # Session has no spike or has reached a terminal status — genesis path.
    _ensure_spike(reasoning_session)
    inject_swarm_chatter(reasoning_session, role=role, text=content)
    logger.info(
        '[Gateway] Spawned spike for session %s.',
        reasoning_session.pk,
    )
    return {
        'success': True,
        'action': 'spawned',
        'session_id': str(reasoning_session.pk),
    }


def _ensure_spike(reasoning_session: ReasoningSession) -> Spike:
    """Create a Spike and SpikeTrain so reasoning can execute.

    Mirrors the Thalamus ``interact`` genesis pattern exactly:
    find/create standing SpikeTrain → create Spike on the ``run_frontal_lobe``
    Neuron → link to session → create initial ReasoningTurn.
    """
    pathway_id = NeuralPathway.THALAMUS

    # 1. Find or create the standing SpikeTrain.
    standing_train = (
        SpikeTrain.objects.filter(pathway_id=pathway_id)
        .order_by('-created')
        .first()
    )
    if not standing_train:
        pathway = NeuralPathway.objects.get(id=pathway_id)
        standing_train = SpikeTrain.objects.create(
            pathway=pathway,
            environment_id=pathway.environment_id,
            status_id=SpikeTrainStatus.RUNNING,
        )
    elif standing_train.status_id != SpikeTrainStatus.RUNNING:
        standing_train.status_id = SpikeTrainStatus.RUNNING
        standing_train.save(update_fields=['status_id'])

    # 2. Locate the Frontal Lobe neuron (non-root on the THALAMUS pathway).
    neuron = Neuron.objects.filter(
        pathway_id=pathway_id, is_root=False,
    ).first()

    # 3. Create the Spike.
    spike = Spike.objects.create(
        spike_train=standing_train,
        neuron=neuron,
        effector_id=neuron.effector_id,
        status_id=SpikeStatus.PENDING,
        axoplasm={},
    )

    # 4. Link spike to the session and set it ready for injection.
    reasoning_session.spike = spike
    reasoning_session.status_id = ReasoningStatusID.ATTENTION_REQUIRED
    reasoning_session.save(update_fields=['spike', 'status_id'])

    # 5. Ensure an initial turn exists.
    if not ReasoningTurn.objects.filter(session=reasoning_session).exists():
        ReasoningTurn.objects.create(
            session=reasoning_session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )

    return spike


def handle_interrupt(reasoning_session_id: UUID) -> dict[str, Any]:
    """Set the active Spike to STOPPING for a reasoning session.

    The FrontalLobe reasoning loop polls ``spike_is_stopping()`` and will
    exit gracefully once the status is STOPPING.

    Args:
        reasoning_session_id: UUID of the reasoning session.

    Returns:
        Dict with ``success`` and either ``spike_id`` or ``error``.
    """
    try:
        session = ReasoningSession.objects.select_related('spike').get(
            pk=reasoning_session_id,
        )
    except ReasoningSession.DoesNotExist:
        return {'success': False, 'error': 'session_not_found'}

    spike = session.spike
    if spike is None:
        return {'success': False, 'error': 'no_active_spike'}

    if spike.status_id not in (SpikeStatus.RUNNING, SpikeStatus.PENDING):
        return {'success': False, 'error': 'spike_not_active'}

    spike.status_id = SpikeStatus.STOPPING
    spike.save(update_fields=['status_id'])

    logger.info(
        '[Gateway] Interrupt requested for session %s, spike %s.',
        reasoning_session_id,
        spike.id,
    )
    return {'success': True, 'spike_id': str(spike.id)}
