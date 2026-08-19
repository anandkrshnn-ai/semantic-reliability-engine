from enum import Enum
from typing import Optional, Tuple, List, Callable
import sqlglot
from sqlglot import exp
from pydantic import BaseModel


class MutationType(str, Enum):
    FILTER_DROP = "FILTER_DROP"
    BOUNDARY_SHIFT = "BOUNDARY_SHIFT"
    AGGREGATION_SWAP = "AGGREGATION_SWAP"
    JOIN_PREDICATE_DROP = "JOIN_PREDICATE_DROP"
    GRAIN_DROP = "GRAIN_DROP"
    COALESCE_BYPASS = "COALESCE_BYPASS"
    MATH_OPERATOR_INVERT = "MATH_OPERATOR_INVERT"
    DISTINCT_DROP = "DISTINCT_DROP"


class MutationResult(BaseModel):
    """Represents an applied SQL AST mutation."""
    mutation_type: MutationType
    description: str
    original_sql: str
    mutated_sql: str
    target_node: str
    mutation_category: str
