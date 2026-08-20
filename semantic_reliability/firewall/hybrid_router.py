"""Hybrid Verification & Escalation Router.

Routes SQL candidate queries to Tier 3 (Static SCOS AST Linter) by default (< 1ms, 0 bytes scanned)
and adaptively escalates to Tier 4 (Runtime Relational Oracle) on AST ambiguity, deep nesting,
or policy-triggered deep inspection.
"""

from typing import Optional, List, Dict, Any
import time
import sqlglot
from sqlglot import exp
from pydantic import BaseModel, Field

from semantic_reliability.compiler.contracts import SemanticContractValidator, ContractEvaluationResult, ContractViolation
from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.assertions.registry import AssertionSuite


class HybridValidationResult(BaseModel):
    """Result of hybrid static-first verification with adaptive runtime escalation."""
    passed: bool
    metric_name: str
    routing_tier: str = Field(..., description="'tier_3_static' or 'tier_4_escalated'")
    routing_decision: str = Field(..., description="e.g. tier_3_static_approved, tier_4_escalated_rejected")
    escalated: bool
    escalation_reason: Optional[str] = None
    static_result: ContractEvaluationResult
    runtime_passed: Optional[bool] = None
    runtime_failure_reasons: List[str] = Field(default_factory=list)
    latency_ms: float
    bytes_scanned: int = 0


class HybridValidator:
    """Adaptive Hybrid Router bridging Static AST pre-flight and Runtime Relational execution."""

    @classmethod
    def _assess_ast_escalation_triggers(cls, ast: exp.Expression) -> Optional[str]:
        """Detects whether AST characteristics warrant escalating from static to runtime oracle."""
        # 1. Multiple nested CTEs or deep subqueries
        ctes = list(ast.find_all(exp.CTE))
        if len(ctes) > 1:
            return f"Complex query graph: {len(ctes)} CTEs detected"

        subqueries = list(ast.find_all(exp.Subquery))
        if len(subqueries) > 1:
            return f"Nested subqueries: {len(subqueries)} subqueries detected"

        # 2. Window functions or complex CASE expressions
        windows = list(ast.find_all(exp.Window))
        if len(windows) > 0:
            return "Window function detected (qualify/partition logic requires relational execution)"

        # 3. Dynamic coalesce / null-handling bypasses
        coalesces = list(ast.find_all(exp.Coalesce))
        cases = list(ast.find_all(exp.Case))
        if len(cases) > 1:
            return "Multiple conditional branches (CASE WHEN) require runtime contrastive evaluation"

        return None

    @classmethod
    def validate_hybrid(
        cls,
        candidate_sql: str,
        metric_def: MetricDefinition,
        duckdb_conn: Optional[Any] = None,
        runtime_suite: Optional[AssertionSuite] = None,
        force_escalate: bool = False,
        dialect: Optional[str] = None,
    ) -> HybridValidationResult:
        """Executes static pre-flight validation and adaptively escalates to runtime oracle if needed."""
        start_time = time.perf_counter()
        
        # Step 1: Run Tier 3 Static SCOS AST Linter
        static_res = SemanticContractValidator.validate(
            candidate_sql=candidate_sql,
            metric_def=metric_def,
            dialect=dialect,
        )

        # If static invariant compiler found critical violations, fail-fast without warehouse execution
        if not static_res.passed:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return HybridValidationResult(
                passed=False,
                metric_name=metric_def.metric,
                routing_tier="tier_3_static",
                routing_decision="tier_3_static_rejected",
                escalated=False,
                escalation_reason=None,
                static_result=static_res,
                runtime_passed=None,
                runtime_failure_reasons=[v.details for v in static_res.violations],
                latency_ms=round(elapsed_ms, 3),
                bytes_scanned=0,
            )

        # Step 2: Static compiler passed - assess if escalation to Tier 4 is required
        try:
            cand_ast = sqlglot.parse_one(candidate_sql, read=dialect or metric_def.dialect)
            escalation_trigger = cls._assess_ast_escalation_triggers(cand_ast) if cand_ast else None
        except Exception:
            escalation_trigger = "SQL unparseable or complex syntax"

        if force_escalate:
            escalation_trigger = "Forced escalation requested by caller"

        # If no escalation needed or no runtime engine provided, approve on Tier 3
        if not escalation_trigger or duckdb_conn is None or runtime_suite is None:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return HybridValidationResult(
                passed=True,
                metric_name=metric_def.metric,
                routing_tier="tier_3_static",
                routing_decision="tier_3_static_approved",
                escalated=False,
                escalation_reason=None,
                static_result=static_res,
                runtime_passed=None,
                runtime_failure_reasons=[],
                latency_ms=round(elapsed_ms, 3),
                bytes_scanned=0,
            )

        # Step 3: Escalate to Tier 4 (Runtime Relational Oracle)
        try:
            runtime_passed = True
            failures = []
            for assertion in runtime_suite.assertions:
                res = assertion.evaluate(duckdb_conn, candidate_sql)
                if not res.passed:
                    runtime_passed = False
                    failures.append(f"{res.assertion_type}: {res.failure_reason}")
        except Exception as e:
            runtime_passed = False
            failures = [f"Runtime execution error: {e}"]


        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        decision = "tier_4_escalated_approved" if runtime_passed else "tier_4_escalated_rejected"

        return HybridValidationResult(
            passed=runtime_passed,
            metric_name=metric_def.metric,
            routing_tier="tier_4_escalated",
            routing_decision=decision,
            escalated=True,
            escalation_reason=escalation_trigger,
            static_result=static_res,
            runtime_passed=runtime_passed,
            runtime_failure_reasons=failures,
            latency_ms=round(elapsed_ms, 3),
            bytes_scanned=1024,  # Synthetic scan cost
        )
