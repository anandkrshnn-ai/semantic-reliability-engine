from typing import Literal, List
from pydantic import BaseModel


class SemanticProbeAlert(BaseModel):
    """Structured signal indicating a decoupling of empirical data reality from contract assumptions."""
    signal_type: str  # e.g., "status_population_rate_shift"
    contract: str
    baseline: float
    current: float
    relative_change: float  # Percentage change (e.g. +25.0%)
    confidence: Literal["high", "medium", "low"]
    likely_causes: List[str]
    action_required: str = "Human review required to confirm if upstream definition changed."

    def to_dict(self):
        return self.model_dump()
