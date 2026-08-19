from typing import List, Tuple
from .models import Decision, RiskLevel, Violation

MUTATION_ORACLE_MAP = {
    "required_filters": "FILTER_DROP",
    "forbidden_filters": "FILTER_DROP",
    "required_dimensions": "GRAIN_DROP",
    "required_function": "AGGREGATION_SWAP",
    "negative_components": "MATH_OPERATOR_INVERT",
    "coalesce_required": "NULL_COALESCE_DROP",
    "population": "FILTER_DROP",
    "grain": "GRAIN_DROP",
    "aggregation": "AGGREGATION_SWAP",
}


def map_violation_to_mutation_oracle(rule: str, invariant_type: str) -> str:
    text = f"{rule} {invariant_type}".lower()
    if "population" in text or "filter" in text:
        return "FILTER_DROP"
    if "grain" in text or "group" in text or "dimension" in text:
        return "GRAIN_DROP"
    if "negative" in text or "deduction" in text or "subtraction" in text:
        return "MATH_OPERATOR_INVERT"
    if "aggregation" in text or "function" in text or "component" in text:
        return "AGGREGATION_SWAP"
    if "coalesce" in text or "null" in text:
        return "NULL_COALESCE_DROP"
    return "UNKNOWN"


class PolicyEngine:
    """Evaluates semantic violations and computes a runtime governance decision (ALLOW, AUDIT, REQUIRE_REVIEW, DENY)."""

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode

    def evaluate(self, violations: List[Violation]) -> Tuple[Decision, RiskLevel, str]:
        if not violations:
            return Decision.ALLOW, RiskLevel.LOW, "Contract compliant. Execution allowed."

        # Enrich violations with mutation oracle data
        for v in violations:
            v.mutation_equivalent = map_violation_to_mutation_oracle(v.rule, v.invariant_type)

        # Determine max severity (ERROR/CRITICAL vs WARNING)
        has_error = any(v.severity.upper() in ("ERROR", "CRITICAL", "FATAL") for v in violations)
        
        if has_error:
            if self.strict_mode:
                return (
                    Decision.DENY, 
                    RiskLevel.CRITICAL, 
                    "Critical semantic defect detected. Execution blocked by policy."
                )
            else:
                return (
                    Decision.REQUIRE_REVIEW, 
                    RiskLevel.CRITICAL, 
                    "Critical semantic defect detected. Manual review required before execution."
                )
        else:
            return (
                Decision.AUDIT, 
                RiskLevel.HIGH, 
                "Semantic anomaly detected. Execution allowed but logged for audit."
            )
