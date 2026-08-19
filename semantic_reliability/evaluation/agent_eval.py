from enum import Enum
from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel, Field
import sqlglot
import duckdb

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.compiler.contracts import SemanticContractValidator, ContractViolation
from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.harness.duckdb_runner import DuckDBFixtureRunner


class SemanticRiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AgentSQLEvaluationReport(BaseModel):
    metric_id: str
    execution_success: bool
    contract_compliant: bool
    syntax_error: Optional[str] = None
    violations: List[str] = Field(default_factory=list)
    assertion_failures: List[str] = Field(default_factory=list)
    unsupported_assumptions: List[str] = Field(default_factory=list)
    semantic_risk: SemanticRiskLevel
    row_count: int = 0
    verdict: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class AgentSQLEvaluator:
    """Evaluates agent-generated SQL against declared business semantic contracts and assertion test suites."""

    @classmethod
    def evaluate(
        cls,
        candidate_sql: str,
        metric_def: MetricDefinition,
        fixtures: Optional[Dict[str, Any]] = None,
        assertion_suite: Optional[AssertionSuite] = None,
        dialect: str = "duckdb",
    ) -> AgentSQLEvaluationReport:
        violations: List[str] = []
        assertion_failures: List[str] = []
        unsupported_assumptions: List[str] = []
        execution_success = False
        row_count = 0
        syntax_error = None

        # 1. AST Syntax & Transpilation Check
        try:
            sqlglot.parse_one(candidate_sql, read=dialect)
        except Exception as e:
            return AgentSQLEvaluationReport(
                metric_id=metric_def.metric,
                execution_success=False,
                contract_compliant=False,
                syntax_error=str(e),
                violations=["SQL syntax is invalid or non-transpilable."],
                semantic_risk=SemanticRiskLevel.CRITICAL,
                verdict="REJECTED_SYNTAX_ERROR",
                evidence={"raw_error": str(e)},
            )

        # 2. Contract Invariant AST Validation
        if metric_def.invariants:
            c_res = SemanticContractValidator.validate(candidate_sql, metric_def, dialect=dialect)
            for v in c_res.violations:
                violations.append(f"[{v.invariant_category}] {v.details}")
                if "population" in v.invariant_category.lower():
                    unsupported_assumptions.append("Agent omitted required business population filter.")
                if "grain" in v.invariant_category.lower():
                    unsupported_assumptions.append("Agent changed reporting aggregation grain.")
                if "aggregation" in v.invariant_category.lower():
                    unsupported_assumptions.append("Agent omitted required positive/negative arithmetic component.")

        # 3. DuckDB Execution & Assertion Testing
        if fixtures:
            try:
                runner = DuckDBFixtureRunner(fixtures=fixtures)
                df = runner.con.execute(candidate_sql).fetchdf()
                execution_success = True
                row_count = len(df)

                if assertion_suite:
                    for assertion in assertion_suite.assertions:
                        res = assertion.evaluate(runner.con, candidate_sql)
                        if not res.passed:
                            assertion_failures.append(f"[{res.name}] {res.failure_reason}")
            except Exception as e:
                execution_success = False
                syntax_error = str(e)
                violations.append(f"Runtime Execution Failure: {str(e)}")

        contract_compliant = (len(violations) == 0)

        # 4. Semantic Risk Determination
        if not execution_success and fixtures:
            semantic_risk = SemanticRiskLevel.CRITICAL
            verdict = "REJECTED_EXECUTION_FAILURE"
        elif len(violations) > 0 and len(assertion_failures) == 0:
            # The most dangerous case: Contract breached, but assertions didn't catch it!
            semantic_risk = SemanticRiskLevel.HIGH
            verdict = "SILENT_SEMANTIC_BREACH_SURVIVED_TESTS"
        elif len(violations) > 0 or len(assertion_failures) > 0:
            semantic_risk = SemanticRiskLevel.HIGH
            verdict = "REJECTED_SEMANTIC_DEFECT_DETECTED"
        else:
            semantic_risk = SemanticRiskLevel.LOW
            verdict = "ACCEPTED_SEMANTICALLY_COMPLIANT"

        return AgentSQLEvaluationReport(
            metric_id=metric_def.metric,
            execution_success=execution_success,
            contract_compliant=contract_compliant,
            syntax_error=syntax_error,
            violations=violations,
            assertion_failures=assertion_failures,
            unsupported_assumptions=unsupported_assumptions,
            semantic_risk=semantic_risk,
            row_count=row_count,
            verdict=verdict,
            evidence={
                "candidate_sql": candidate_sql,
                "row_count": row_count,
                "total_violations": len(violations),
                "total_assertion_failures": len(assertion_failures),
            }
        )
