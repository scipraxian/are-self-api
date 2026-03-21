from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from common.constants import TYPE

from .constants import RELEASE_METHOD, LogChannel


def get_current_utc_time() -> datetime:
    """Module-level callable to prevent nested lambda functions."""
    return datetime.now(timezone.utc)


class Neurotransmitter(BaseModel):
    """
    The base envelope for the synaptic 2-layer routing matrix.

    e.g.
    {
        "receptor_class": "IdentityDisc",
        "dendrite_id": "12345678-1234-1234-1234-1234567890ab",
        "molecule": "Acetylcholine",
        "activity": "updated",
        "vesicle": {
            "its": "springtime",
            "in": "topeka"
        },
        "timestamp": "2023-07-01T12:00:00Z"
    }
    """

    PAYLOAD_KEY = 'payload'
    JSON_KEY = 'json'

    # Layer 1 Router (The Django Channels Group) -> e.g., "IdentityDisc"
    receptor_class: str

    # Layer 2 Router (The Frontend Cache Key) -> e.g., "2873", "uuid", or None for Collections
    dendrite_id: str | None

    # Layer 3 Router (The Neurotransmitter Type) -> Auto-populates via __init__
    molecule: str = 'Neurotransmitter'

    # Layer 4 Router (The Action Verb) -> e.g., "created", "updated", "streaming", "attention_required"
    activity: str = 'transmitting'

    # The Payload
    vesicle: dict | None = None

    timestamp: datetime = Field(default_factory=get_current_utc_time)

    def __init__(self, **data: Any):
        super().__init__(**data)
        # Auto-reflection: subclasses label their own packets
        self.molecule = self.__class__.__name__

    def to_synapse_dict(self) -> dict:
        """Formats the neurotransmitter for Django Channels."""
        return {
            TYPE: RELEASE_METHOD,
            self.PAYLOAD_KEY: self.model_dump(mode=self.JSON_KEY),
        }


# ==========================================
# BIOLOGICAL MOLECULE SUBCLASSES
# These act as semantic wrappers and default state enforcers.
# ==========================================


class Glutamate(Neurotransmitter):
    """Fast, excitatory log streaming."""

    activity: str = 'streaming'
    # vesicle typically holds: {"channel": LogChannel.EXECUTION, "message": "..."}


class Dopamine(Neurotransmitter):
    """Positive state changes, progression, and terminal success conditions."""

    new_status: str
    activity: str = 'status_changed'
    # vesicle optional: {"related_id": 99, "error": "Bobs your uncle."}


class Cortisol(Neurotransmitter):
    """Negative state changes, halt conditions, and errors."""

    new_status: str
    activity: str = 'status_changed'
    # vesicle optional: {"related_id": 99, "error": "Bobs your uncle."}


class Acetylcholine(Neurotransmitter):
    """Memory, variables, and full entity data synchronization."""

    activity: str = (
        'updated'  # Can be overridden with 'created', 'deleted', etc.
    )
    # vesicle holds the serialized model data
