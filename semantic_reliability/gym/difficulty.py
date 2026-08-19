from typing import Literal

def calibrate_difficulty(
    mutation_type: str,
    variance_pct: float = 0.0,
    has_subtle_predicate: bool = False
) -> Literal["easy", "medium", "hard", "expert"]:
    """
    Calibrates difficulty based on semantic detectability:
    - easy: explicit missing predicate, obvious aggregation swap with large variance
    - medium: standard boundary shift, coalesce bypass
    - hard: subtle variance (<5%), grain alteration, temporal attribution
    - expert: multi-component deduction omission, relational join drop
    """
    m_type = mutation_type.upper()

    if m_type in ("JOIN_PREDICATE_DROP", "MATH_OPERATOR_INVERT"):
        return "expert"

    if m_type in ("GRAIN_DROP", "BOUNDARY_SHIFT") or (0.0 < abs(variance_pct) <= 5.0) or has_subtle_predicate:
        return "hard"

    if m_type in ("FILTER_DROP", "COALESCE_BYPASS"):
        return "medium"

    return "easy"
