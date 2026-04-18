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
from frontal_lobe.models import ReasoningTurn, ReasoningTurnDigest
from hippocampus.models import Engram
from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Acetylcholine

logger = logging.getLogger(__name__)


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
