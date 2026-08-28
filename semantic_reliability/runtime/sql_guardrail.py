from typing import List, Tuple
from semantic_reliability.firewall.models import Decision, RiskLevel, Violation
import sqlglot
from sqlglot import exp

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

class SQLGuardrail:
    """AST-based structural guardrail to block destructive queries and enforce limits."""
    
    def __init__(self, max_limit: int = 1000):
        self.max_limit = max_limit
    
    def enforce(self, sql: str, dialect: str = "duckdb") -> str:
        """Parses SQL and blocks DDL/mutations. Enforces LIMIT if absent."""
        try:
            ast = sqlglot.parse_one(sql, read=dialect)
        except Exception as e:
            raise ValueError(f"Guardrail Blocked: Unparseable SQL. {str(e)}")
            
        # Block DDL and destructive statements
        if not isinstance(ast, exp.Select):
            raise ValueError("Guardrail Blocked: Only SELECT statements are permitted.")
            
        # Enforce LIMIT
        limit_clause = ast.args.get("limit")
        if not limit_clause:
            ast.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))
        else:
            try:
                requested_limit = int(limit_clause.expression.this)
                if requested_limit > self.max_limit:
                    ast.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))
            except (ValueError, TypeError):
                # If limit is an expression, overwrite it for safety
                ast.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))
                
        return ast.sql(dialect=dialect)
