"""
Frontal Lobe signals.

Hosts the ReasoningTurn post_save receiver that materializes the
ReasoningTurnDigest side-car and broadcasts it to the frontend as an
Acetylcholine neurotransmitter.

The digest is discardable and recomputable, and the neurotransmitter is
a best-effort push — neither must ever break the save path for a
ReasoningTurn. Both failure modes are guarded and logged independently.
"""

import logging

from asgiref.sync import async_to_sync
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from frontal_lobe.digest_builder import (
    build_and_save_digest,
    digest_to_vesicle,
)
from frontal_lobe.models import (
    ReasoningStatusID,
    ReasoningTurn,
    ReasoningTurnDigest,
    SessionConclusion,
)
from hippocampus.models import Engram
from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Acetylcholine

logger = logging.getLogger(__name__)

# Status IDs that mean "the turn hasn't produced an LLM response yet".
# We broadcast a ghost vesicle for these so the UI can render a
# placeholder node before the real digest lands.
TURN_IN_FLIGHT_STATUS_IDS = (
    ReasoningStatusID.PENDING,
    ReasoningStatusID.ACTIVE,
    ReasoningStatusID.PAUSED,
    ReasoningStatusID.ATTENTION_REQUIRED,
)


@receiver(post_save, sender=ReasoningTurn)
def write_reasoning_turn_digest(sender, instance, **kwargs):
    """Upsert the digest and broadcast it when a turn has a usage record.

    Triggered on every save of ReasoningTurn. Skips the write if:
      - the save is a fixture load (raw=True), or
      - model_usage_record has not been attached yet (the turn hasn't
        finished its LLM round-trip, so there's nothing to digest).

    Successful build -> fire Acetylcholine with receptor_class
    'ReasoningTurnDigest' and the full digest as the vesicle, so the
    UI can append a node on the reasoning-session graph without a
    round-trip fetch.

    Build failures abort the broadcast (nothing to send). Broadcast
    failures do not roll back the digest (it's already saved). Both
    are logged with bracketed tags per the style guide.
    """
    if kwargs.get('raw', False):
        return
    if instance.model_usage_record_id is None:
        return

    try:
        digest = build_and_save_digest(instance)
    except Exception:
        logger.exception(
            '[FrontalLobe] Failed to build digest for turn %s',
            instance.id,
        )
        return

    broadcast_digest(digest)


@receiver(post_save, sender=ReasoningTurn)
def broadcast_turn_started(sender, instance, **kwargs):
    """Push a ghost vesicle while a turn is still in flight.

    Fires on every save of a ReasoningTurn, and emits an Acetylcholine
    only when the turn has no ``model_usage_record`` yet AND its status
    is in the in-flight set (PENDING/ACTIVE/PAUSED/ATTENTION_REQUIRED).
    Once the turn completes, ``write_reasoning_turn_digest`` takes over
    and the frontend prunes the ghost in favor of the real digest node
    (both carry the same ``turn_id``).

    receptor_class='ReasoningTurn' with dendrite_id=str(session_id) so
    a per-session dendrite subscription can filter efficiently —
    unrelated Dopamine/Cortisol signals on the same receptor class use
    dendrite_id=turn.id and will be ignored by the client filter.

    Failures are logged under ``[FrontalLobe]`` and swallowed; a dead
    broadcast must never roll back a turn save.
    """
    if kwargs.get('raw', False):
        return
    if instance.model_usage_record_id is not None:
        return
    if instance.status_id not in TURN_IN_FLIGHT_STATUS_IDS:
        return

    status_name = ''
    try:
        status_name = instance.status.name or ''
    except AttributeError:
        pass

    vesicle = {
        'turn_id': str(instance.id),
        'session_id': str(instance.session_id),
        'turn_number': instance.turn_number,
        'status_name': status_name,
        'created': (
            instance.created.isoformat() if instance.created else None
        ),
    }

    try:
        transmitter = Acetylcholine(
            receptor_class='ReasoningTurn',
            dendrite_id=str(instance.session_id),
            activity='started',
            vesicle=vesicle,
        )
        async_to_sync(fire_neurotransmitter)(transmitter)
    except Exception:
        logger.exception(
            '[FrontalLobe] Turn-started neurotransmitter failed for turn %s',
            instance.id,
        )


@receiver(m2m_changed, sender=Engram.source_turns.through)
def refresh_digest_on_engram_link_change(
    sender, instance, action, reverse, model, pk_set, **kwargs
):
    """Rebuild digests for turns whose engram links changed.

    Fires on ``post_add``/``post_remove``. For ``post_clear`` ``pk_set``
    is ``None`` — clears are rare and the next explicit add will repaint,
    so we skip them.

    Forward direction (``engram.source_turns.add(turn)``): ``instance``
    is the Engram and ``pk_set`` is the turn ids. Reverse direction
    (``turn.engrams.add(engram)``): ``instance`` is the ReasoningTurn
    and ``pk_set`` is the engram ids.

    Turns without a ``model_usage_record`` are still digest-ineligible
    (same gate as the post_save receiver), so we filter them out
    rather than silently creating stub digests. Per-turn try/except
    isolates builder failures so one bad turn does not abort the
    rest.
    """
    if action not in ('post_add', 'post_remove'):
        return
    if not pk_set:
        return

    if reverse:
        turn_ids = [instance.id]
    else:
        turn_ids = list(pk_set)

    for turn in ReasoningTurn.objects.filter(
        id__in=turn_ids, model_usage_record__isnull=False
    ):
        try:
            digest = build_and_save_digest(turn)
        except Exception:
            logger.exception(
                '[FrontalLobe] Engram M2M digest refresh failed for turn %s',
                turn.id,
            )
            continue
        broadcast_digest(digest)


@receiver(post_save, sender=SessionConclusion)
def broadcast_session_conclusion(sender, instance, **kwargs):
    """Push the conclusion as an Acetylcholine vesicle on save.

    SessionConclusion is only written from ``mcp_done``'s
    ``update_or_create``; any save is a real conclusion event, so
    there's no ``model_usage_record``-style emptiness gate to apply
    here. Fixture loads still get skipped via the standard
    ``raw`` guard, and the broadcast itself is wrapped so a failure
    in the synaptic cleft never rolls back the conclusion write.
    """
    if kwargs.get('raw', False):
        return
    broadcast_conclusion(instance)


def conclusion_to_vesicle(conclusion: SessionConclusion) -> dict:
    """Serialize a SessionConclusion to the Acetylcholine vesicle dict.

    Kept key-identical to ``SessionConclusionSerializer`` so the push
    transport (vesicle) and the pull transport
    (``/api/v2/reasoning_sessions/{id}/conclusion/``) stay byte-identical
    — a symmetry test in ``test_conclusion.py`` enforces this.
    """
    status_name = ''
    try:
        status_name = conclusion.status.name or ''
    except AttributeError:
        pass
    return {
        'id': conclusion.id,
        'session_id': str(conclusion.session_id),
        'status_name': status_name,
        'summary': conclusion.summary,
        'reasoning_trace': conclusion.reasoning_trace,
        'outcome_status': conclusion.outcome_status,
        'recommended_action': conclusion.recommended_action,
        'next_goal_suggestion': conclusion.next_goal_suggestion,
        'system_persona_and_prompt_feedback': (
            conclusion.system_persona_and_prompt_feedback
        ),
        'created': (
            conclusion.created.isoformat() if conclusion.created else None
        ),
        'modified': (
            conclusion.modified.isoformat() if conclusion.modified else None
        ),
    }


def broadcast_conclusion(conclusion: SessionConclusion) -> None:
    """Fire an Acetylcholine with the full conclusion as the vesicle.

    receptor_class is the domain entity ('SessionConclusion'),
    dendrite_id is the session UUID so per-session subscriptions work
    without a shape change. Failures are logged with the
    ``[FrontalLobe]`` tag and swallowed — the conclusion is already
    saved; a dead broadcast should not bubble up.
    """
    try:
        transmitter = Acetylcholine(
            receptor_class='SessionConclusion',
            dendrite_id=str(conclusion.session_id),
            activity='saved',
            vesicle=conclusion_to_vesicle(conclusion),
        )
        async_to_sync(fire_neurotransmitter)(transmitter)
    except Exception:
        logger.exception(
            '[FrontalLobe] Conclusion neurotransmitter failed for session %s',
            conclusion.session_id,
        )


def broadcast_digest(digest: ReasoningTurnDigest) -> None:
    """Fire an Acetylcholine with the full digest as the vesicle.

    receptor_class is the digest itself ('ReasoningTurnDigest'), per
    the convention in CLAUDE.md — channels group synapse_{class}
    must be a domain entity, and the digest is one. The frontend
    subscribes via useDendrite('ReasoningTurnDigest', null) and
    filters vesicles by vesicle.session_id client-side.

    dendrite_id is the digest's PK (which is the turn's UUID), so any
    future per-turn targeted subscriptions work without a shape
    change.
    """
    try:
        transmitter = Acetylcholine(
            receptor_class='ReasoningTurnDigest',
            dendrite_id=str(digest.turn_id),
            activity='saved',
            vesicle=digest_to_vesicle(digest),
        )
        async_to_sync(fire_neurotransmitter)(transmitter)
    except Exception:
        logger.exception(
            '[FrontalLobe] Digest neurotransmitter failed for turn %s',
            digest.turn_id,
        )
