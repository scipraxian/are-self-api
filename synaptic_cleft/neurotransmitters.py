from datetime import datetime, timezone
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from common.constants import TYPE

from .constants import RELEASE_METHOD, LogChannel


def get_current_utc_time() -> datetime:
    """Module-level callable to prevent nested lambda functions."""
    return datetime.now(timezone.utc)


PAYLOAD_KEY = 'payload'
JSON_KEY = 'json'


class Neurotransmitter(BaseModel):
    """
    Base envelope for WebSocket routing (receptor, dendrite, molecule, activity).

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

    # receptor_class: Django Channels group / domain (e.g. "IdentityDisc")
    receptor_class: str

    # dendrite_id: Scoped subscription key (e.g. PK, uuid, or None for collections)
    dendrite_id: str | None

    # molecule: Packet type; subclass name is set in __init__
    molecule: str = 'Neurotransmitter'

    # activity: Action verb (e.g. "created", "updated", "streaming", "attention_required")
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
            PAYLOAD_KEY: self.model_dump(mode=JSON_KEY),
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


class Norepinephrine(Neurotransmitter):
    """Worker monitoring, alertness, and fleet awareness."""

    activity: str = 'event'
    # vesicle holds structured Celery event data or worker log lines
