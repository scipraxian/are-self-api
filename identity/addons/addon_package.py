from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class AddonPackage:
    iteration: Optional[int]
    identity: UUID
    identity_disc: Optional[UUID]
    turn_number: int
