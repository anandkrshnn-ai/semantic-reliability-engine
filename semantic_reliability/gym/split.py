from typing import Literal

# Structured splits mapping mutation families and domains to prevent leakage
# Train on core filter and aggregation changes; validate on boundaries and nulls; hold out multi-relational and domain-specific models.
TRAIN_MUTATION_TYPES = {"FILTER_DROP", "AGGREGATION_SWAP", "COALESCE_BYPASS"}
VAL_MUTATION_TYPES = {"BOUNDARY_SHIFT", "DISTINCT_DROP"}
HOLDOUT_MUTATION_TYPES = {"GRAIN_DROP", "MATH_OPERATOR_INVERT", "JOIN_PREDICATE_DROP"}

HOLDOUT_DOMAINS = {"healthcare", "infrastructure", "risk"}


def assign_dataset_split(metric_id: str, domain: str, mutation_type: str) -> Literal["train", "val", "holdout"]:
    """Determines whether a preference pair belongs to train, validation, or holdout split."""
    if domain.lower() in HOLDOUT_DOMAINS:
        return "holdout"
    if mutation_type.upper() in HOLDOUT_MUTATION_TYPES:
        return "holdout"
    if mutation_type.upper() in VAL_MUTATION_TYPES:
        return "val"
    return "train"
