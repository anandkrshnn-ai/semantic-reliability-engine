from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class DriftSeverity(str, Enum):
    FATAL = "FATAL"
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class DriftType(str, Enum):
    FILTER_REMOVAL = "FILTER_REMOVAL"
    FILTER_ADDITION = "FILTER_ADDITION"
    SEMANTIC_LOGIC_SHIFT = "SEMANTIC_LOGIC_SHIFT"
    AGGREGATION_FUNCTION_SHIFT = "AGGREGATION_FUNCTION_SHIFT"
    AGGREGATION_EXPRESSION_SHIFT = "AGGREGATION_EXPRESSION_SHIFT"
    MATHEMATICAL_OPERATOR_SHIFT = "MATHEMATICAL_OPERATOR_SHIFT"
    JOIN_PREDICATE_MUTATION = "JOIN_PREDICATE_MUTATION"
    JOIN_TYPE_SHIFT = "JOIN_TYPE_SHIFT"
    GRAIN_DRIFT = "GRAIN_DRIFT"
    NULL_HANDLING_DRIFT = "NULL_HANDLING_DRIFT"
    HAVING_FILTER_SHIFT = "HAVING_FILTER_SHIFT"
    TABLE_TARGET_SHIFT = "TABLE_TARGET_SHIFT"


class SemanticDrift(BaseModel):
    """Represents an identified semantic difference between baseline and candidate SQL."""
    severity: DriftSeverity
    drift_type: DriftType
    component: str
    summary: str
    details: str
    business_impact: str
    original_snippet: Optional[str] = None
    candidate_snippet: Optional[str] = None
    remediation: Optional[str] = None
