from pydantic import BaseModel, Field
from typing import Optional, List, Any
from enum import Enum


class Decision(str, Enum):
    ALLOW = "ALLOW"
    AUDIT = "AUDIT"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    DENY = "DENY"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvaluateRequest(BaseModel):
    request_id: str
    metric_id: str
    sql: str
    dialect: str = "duckdb"
    agent_id: str
    question: Optional[str] = None


class Violation(BaseModel):
    rule: str
    expected: str
    found: str
    severity: str
    invariant_type: str
    mutation_equivalent: Optional[str] = Field(
        default=None, 
        description="The mutation operator that maps to this semantic contract failure"
    )


class EvaluateResponse(BaseModel):
    request_id: str
    trace_id: str
    decision: Decision
    execution_allowed: bool
    contract_compliant: bool
    risk: RiskLevel
    violations: List[Violation]
    contract_version: str
    message: Optional[str] = None
