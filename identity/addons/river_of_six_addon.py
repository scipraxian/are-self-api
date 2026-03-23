from typing import List

from frontal_lobe.models import ChatMessage, ChatMessageRole
from identity.addons.addon_package import AddonPackage


def river_of_six_addon(package: AddonPackage) -> List[ChatMessage]:
    """
    Identity Addon (Phase: HISTORY):
    A highly constrained memory window. Retains 6 turns of history,
    gradually decaying tool data to simulate cognitive load and enforce Engram usage.
    """
    if not package.session_id:
        return []

    current_turn_num = package.turn_number

    # Exclude Age 7+ completely (only fetch turns greater than current - 6)
    cutoff_turn = max(1, current_turn_num - 6)

    history_qs = list(
        ChatMessage.objects.filter(
            session_id=package.session_id,
            turn__turn_number__gte=cutoff_turn,
            turn__turn_number__lt=current_turn_num,
            is_volatile=False,
        )
        .select_related('role', 'turn')
        .order_by('created')
    )

    for msg in history_qs:
        # Calculate how many turns ago this happened
        age = current_turn_num - msg.turn.turn_number

        if msg.role_id == ChatMessageRole.TOOL:
            if age >= 4:
                # Age 4, 5, 6: Tool data completely removed
                msg.content = (
                    '[DATA EVICTED FROM L1 CACHE. REQUIRES ENGRAM RETRIEVAL.]'
                )
            elif age == 3:
                # Age 3: Extra warning
                msg.content += '\n\n[SYSTEM CRITICAL: L1 EVICTION IMMINENT ON NEXT TURN. FINAL CHANCE TO SAVE TO ENGRAMS.]'
            elif age == 2:
                # Age 2: Standard warning
                msg.content += '\n\n[SYSTEM WARNING: L1 Cache decay beginning.]'
            # Age 1: Remains untouched

    return history_qs
