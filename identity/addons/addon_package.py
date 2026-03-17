from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class AddonPackage:
    iteration: Optional[int]
    identity: UUID
    identity_disc: Optional[UUID]
    turn_number: int
    reasoning_turn_id: Optional[int]
    environment_id: Optional[UUID]
    shift_id: Optional[int]
