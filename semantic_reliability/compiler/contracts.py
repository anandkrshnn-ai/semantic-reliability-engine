from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import sqlglot
from sqlglot import exp

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants
from semantic_reliability.drift.rules import SemanticDrift, DriftSeverity, DriftType


class ContractViolation(BaseModel):
    """Represents a violation of a declared semantic invariant contract."""
    invariant_category: str
    invariant_rule: str
    severity: str
    details: str
    remediation: str


class ContractEvaluationResult(BaseModel):
    """Result of checking a candidate SQL model against declared semantic invariants."""
    passed: bool
    metric_name: str
    violations: List[ContractViolation]
    evaluated_invariants_count: int


class SemanticContractValidator:
    """Validates candidate SQL models against policy-driven semantic invariant contracts."""

    @classmethod
    def validate(
        cls,
        candidate_sql: str,
        metric_def: MetricDefinition,
        dialect: Optional[str] = None,
    ) -> ContractEvaluationResult:
        cand_ast = sqlglot.parse_one(candidate_sql, read=dialect or metric_def.dialect)
        invariants = metric_def.invariants or SemanticInvariants()

        violations: List[ContractViolation] = []
        rules_checked = 0

        read_dialect = dialect or metric_def.dialect

        # 1. Population Invariant Check
        if invariants.population:
            rules_checked += 1
            for req_filter in invariants.population.required_filters:
                req_ast = sqlglot.parse_one(f"SELECT * FROM t WHERE {req_filter}", read=read_dialect).find(exp.Where)
                cand_where = cand_ast.find(exp.Where)

                is_present = False
                if cand_where and req_ast:
                    req_norm = req_ast.this.sql().strip()
                    cand_norm = cand_where.this.sql().strip()
                    if req_norm in cand_norm:
                        is_present = True

                if not is_present:
                    violations.append(ContractViolation(
                        invariant_category="Population Invariant",
                        invariant_rule=f"Required filter: `{req_filter}`",
                        severity="CRITICAL",
                        details=f"Candidate SQL does not include required business filter `{req_filter}` in WHERE clause.",
                        remediation=f"Add `AND {req_filter}` to candidate SQL query.",
                    ))

        # 2. Grain Invariant Check
        if invariants.grain and invariants.grain.required_dimensions:
            rules_checked += 1
            cand_group = cand_ast.find(exp.Group)
            cand_dims = [
                e.sql().lower().replace(" ", "").replace("'", "").replace('"', "")
                for e in cand_group.expressions
            ] if cand_group else []

            for req_dim in invariants.grain.required_dimensions:
                try:
                    req_parsed = sqlglot.parse_one(req_dim, read=read_dialect).sql().lower().replace(" ", "").replace("'", "").replace('"', "")
                except Exception:
                    req_parsed = req_dim.lower().replace(" ", "").replace("'", "").replace('"', "")

                dim_present = any(req_parsed in d or d in req_parsed or req_dim.lower().replace(" ", "") in d for d in cand_dims)
                if not dim_present:
                    violations.append(ContractViolation(
                        invariant_category="Reporting Grain Invariant",
                        invariant_rule=f"Required grouping dimension: `{req_dim}`",
                        severity="CRITICAL",
                        details=f"Candidate query does not group by required dimension `{req_dim}`.",
                        remediation=f"Include `{req_dim}` in candidate GROUP BY clause.",
                    ))

        # 3. Aggregation Net Component Check
        if invariants.aggregation:
            rules_checked += 1
            cand_sql_text = candidate_sql.lower()
            for pos in invariants.aggregation.positive_components:
                if pos.lower() not in cand_sql_text:
                    violations.append(ContractViolation(
                        invariant_category="Aggregation Invariant",
                        invariant_rule=f"Positive component `{pos}`",
                        severity="HIGH",
                        details=f"Candidate calculation omits positive component condition for `{pos}`.",
                        remediation=f"Ensure positive component `{pos}` is included in net aggregation.",
                    ))
            for neg in invariants.aggregation.negative_components:
                if neg.lower() not in cand_sql_text:
                    violations.append(ContractViolation(
                        invariant_category="Aggregation Invariant",
                        invariant_rule=f"Negative component `{neg}`",
                        severity="HIGH",
                        details=f"Candidate calculation omits negative deduction condition for `{neg}`.",
                        remediation=f"Ensure negative component `{neg}` is subtracted in net aggregation.",
                    ))

        # 4. Timezone Invariant Check
        if invariants.time and invariants.time.timezone:
            rules_checked += 1
            # If UTC is required, check if non-UTC timezone keywords appear
            if invariants.time.timezone.upper() == "UTC" and "time zone" in candidate_sql.lower():
                if "utc" not in candidate_sql.lower():
                    violations.append(ContractViolation(
                        invariant_category="Timezone Invariant",
                        invariant_rule="Timezone must be UTC",
                        severity="HIGH",
                        details="Candidate query contains non-UTC timezone conversion.",
                        remediation="Convert timestamps using UTC timezone alignment.",
                    ))

        return ContractEvaluationResult(
            passed=len(violations) == 0,
            metric_name=metric_def.metric,
            violations=violations,
            evaluated_invariants_count=rules_checked,
        )
