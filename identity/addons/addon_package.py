from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class AddonPackage:
    iteration: Optional[int]
    identity_disc: Optional[UUID]

    # --- Turn Context ---
    turn_number: int
    reasoning_turn_id: Optional[id]
    session_id: Optional[UUID] = None
    spike_id: Optional[UUID] = None

    # --- Agile Context ---
    environment_id: Optional[UUID] = None
    shift_id: Optional[int] = None
