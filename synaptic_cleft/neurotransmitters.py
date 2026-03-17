from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from .constants import RELEASE_METHOD, LogChannel, NeurotransmitterEvent


def get_current_utc_time() -> datetime:
    """Module-level callable to prevent nested lambda functions."""
    return datetime.now(timezone.utc)


class Neurotransmitter(BaseModel):
    """The base envelope for all synaptic websocket messages."""

    event: NeurotransmitterEvent
    spike_id: UUID
    timestamp: datetime = Field(default_factory=get_current_utc_time)

    def to_synapse_dict(self) -> dict:
        """Formats the neurotransmitter for Django Channels."""
        return {
            'type': RELEASE_METHOD,
            'payload': self.model_dump(mode='json'),
        }


class Glutamate(Neurotransmitter):
    """Fast, excitatory log streaming."""

    event: NeurotransmitterEvent = NeurotransmitterEvent.LOG
    channel: LogChannel
    message: str


class Dopamine(Neurotransmitter):
    """Positive State changes and terminal conditions."""

    event: NeurotransmitterEvent = NeurotransmitterEvent.STATUS
    status_id: int


class Cortisol(Neurotransmitter):
    """Negative State changes and terminal conditions."""

    event: NeurotransmitterEvent = NeurotransmitterEvent.STATUS
    status_id: int


class Acetylcholine(Neurotransmitter):
    """Memory, variables, and blackboard updates."""

    event: NeurotransmitterEvent = NeurotransmitterEvent.BLACKBOARD
    key: str
    value: Any
