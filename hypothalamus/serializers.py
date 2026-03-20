from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

FALLBACK_MODEL_ID = 'ollama/qwen2.5-coder:8b'


@dataclass(frozen=True)
class ModelSelection:
    """The result of a Hypothalamus routing decision."""

    provider_model_id: str
    ai_model_name: str
    distance: float
    input_cost_per_token: Decimal
    is_fallback: bool = False

    @classmethod
    def fallback(cls) -> 'ModelSelection':
        return cls(
            provider_model_id=FALLBACK_MODEL_ID,
            ai_model_name=FALLBACK_MODEL_ID,
            distance=1.0,
            input_cost_per_token=Decimal('0'),
            is_fallback=True,
        )


@dataclass(frozen=True)
class SyncResult:
    """Summary of a catalog sync run."""

    models_added: int
    providers_added: int
    prices_updated: int
    models_deactivated: int
    status: str
    error: Optional[str] = None
