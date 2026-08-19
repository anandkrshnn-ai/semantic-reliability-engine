from enum import Enum
from typing import Dict, Any


class MutationDifficulty(str, Enum):
    EASY = "EASY"        # Aggregation swap or distinct drop (often alters scalar shape/scale)
    MEDIUM = "MEDIUM"    # Missing basic WHERE predicate
    HARD = "HARD"        # Boundary shift (>= vs >) or subtle temporal attribution window
    EXPERT = "EXPERT"    # Multi-component deduction omission or relational join predicate drop


# Difficulty mapping for mutation operators
DIFFICULTY_MAP = {
    "AGGREGATION_SWAP": MutationDifficulty.EASY,
    "DISTINCT_DROP": MutationDifficulty.EASY,
    "FILTER_DROP": MutationDifficulty.MEDIUM,
    "COALESCE_BYPASS": MutationDifficulty.MEDIUM,
    "BOUNDARY_SHIFT": MutationDifficulty.HARD,
    "GRAIN_DROP": MutationDifficulty.HARD,
    "MATH_OPERATOR_INVERT": MutationDifficulty.EXPERT,
    "JOIN_PREDICATE_DROP": MutationDifficulty.EXPERT,
}


def calibrate_difficulty(mutation_type: str, empirical_variance_pct: float = 0.0) -> MutationDifficulty:
    base = DIFFICULTY_MAP.get(mutation_type.upper(), MutationDifficulty.MEDIUM)
    # If variance is very subtle (< 5%), elevate difficulty to HARD/EXPERT
    if 0.0 < empirical_variance_pct < 5.0 and base in (MutationDifficulty.EASY, MutationDifficulty.MEDIUM):
        return MutationDifficulty.HARD
    return base
