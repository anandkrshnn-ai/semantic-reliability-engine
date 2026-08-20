"""4-Tier Baseline Ladder Evaluator for Semantic-SQL-Bench.
Evaluates analytical SQL queries against progressive tiers of testing rigor.
"""
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
import sqlglot
import pandas as pd
import duckdb

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.compiler.contracts import SemanticContractValidator
from semantic_reliability.assertions.base import AssertionResult, DataAssertion
from semantic_reliability.assertions.registry import AssertionSuite


class BaselineTier(str, Enum):
    TIER_0_SYNTAX = "tier_0_syntax"
    TIER_1_MINIMAL_STRUCTURAL = "tier_1_minimal_structural"
    TIER_2_REALISTIC_DBT = "tier_2_realistic_dbt"
    TIER_3_STATIC_SCOS_AST = "tier_3_static_scos_ast"
    TIER_4_RUNTIME_RELATIONAL = "tier_4_runtime_relational"


class BaselineLadderEvaluator:
    """Evaluates candidate SQL across the progressive 4-tier validation ladder."""

    def __init__(
        self,
        contract: Optional[MetricDefinition] = None,
        conn: Optional[duckdb.DuckDBPyConnection] = None,
        suite: Optional[AssertionSuite] = None,
        suite_path: Optional[str | Path] = None,
    ):
        self.contract = contract
        self.conn = conn or duckdb.connect(":memory:")
        self.static_validator = SemanticContractValidator()
        self.suite = suite or (AssertionSuite.from_yaml_file(suite_path) if suite_path else None)

    def evaluate_tier_0_syntax(self, sql: str) -> Dict[str, Any]:
        """Tier 0: Syntactic validity check."""
        try:
            tree = sqlglot.parse_one(sql)
            return {"tier": BaselineTier.TIER_0_SYNTAX.value, "passed": tree is not None, "error": None}
        except Exception as e:
            return {"tier": BaselineTier.TIER_0_SYNTAX.value, "passed": False, "error": str(e)}

    def evaluate_tier_1_minimal_structural(self, df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Tier 1: Minimal structural schema tests (not_null, unique_key, row_count_bounds)."""
        if df is None or df.empty:
            return {"tier": BaselineTier.TIER_1_MINIMAL_STRUCTURAL.value, "passed": False, "reason": "empty_dataframe"}
        has_nulls = df.isnull().any().any()
        return {
            "tier": BaselineTier.TIER_1_MINIMAL_STRUCTURAL.value,
            "passed": not has_nulls and len(df) >= 1,
            "row_count": len(df),
            "has_nulls": bool(has_nulls),
        }

    def evaluate_tier_2_realistic_dbt(
        self,
        df: Optional[pd.DataFrame] = None,
        sql: Optional[str] = None,
        conn: Optional[duckdb.DuckDBPyConnection] = None,
        suite: Optional[AssertionSuite] = None,
        suite_path: Optional[str | Path] = None,
        numeric_cols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Tier 2: Realistic dbt suite executing schema tests (accepted_range, accepted_values, relationships, singular SQL tests)."""
        # Tier 1 prerequisite check on DataFrame if provided
        if df is not None:
            tier_1 = self.evaluate_tier_1_minimal_structural(df)
            if not tier_1["passed"]:
                return {
                    "tier": BaselineTier.TIER_2_REALISTIC_DBT.value,
                    "passed": False,
                    "reason": tier_1.get("reason", "failed_tier_1"),
                    "violations": ["Failed Tier-1 structural integrity (empty or null values detected)"],
                    "checks_count": 0,
                    "passed_checks_count": 0,
                    "failed_checks_count": 1,
                    "details": [],
                }

        # Resolve the active Tier-2 assertion suite
        active_suite = suite
        if active_suite is None and suite_path is not None:
            active_suite = AssertionSuite.from_yaml_file(suite_path)
        if active_suite is None and self.suite is not None:
            active_suite = self.suite
        if active_suite is None:
            active_suite = AssertionSuite.get_realistic_dbt_suite()

        db_con = conn or self.conn
        results: List[AssertionResult] = []

        # Execute assertions against DataFrame or SQL + DuckDB
        for assertion in active_suite.assertions:
            if df is not None and hasattr(assertion, "evaluate_df"):
                if assertion.assertion_type == "relationships":
                    from_col = getattr(assertion, "from_column", None)
                    if from_col and from_col not in df.columns:
                        continue
                    res = assertion.evaluate_df(df, con=db_con)
                elif assertion.assertion_type == "singular_sql_test":
                    res = assertion.evaluate_df(df, con=db_con)
                else:
                    # Check if required column exists in df for column-specific assertion
                    col = getattr(assertion, "column", None)
                    if col and col not in df.columns:
                        continue
                    cols = getattr(assertion, "columns", None)
                    if cols and not any(c in df.columns for c in cols):
                        continue
                    res = assertion.evaluate_df(df)
                results.append(res)
            elif sql is not None:
                res = assertion.evaluate(db_con, sql)
                results.append(res)
            elif df is not None:
                try:
                    db_con.register("_df_eval_target", df)
                    res = assertion.evaluate(db_con, "SELECT * FROM _df_eval_target")
                    results.append(res)
                finally:
                    try:
                        db_con.unregister("_df_eval_target")
                    except Exception:
                        pass

        # Dynamic range validation for numeric columns if explicitly requested or running default suite
        if df is not None:
            if numeric_cols:
                for col in numeric_cols:
                    if col in df.columns:
                        is_neg = bool((df[col] < 0).any())
                        results.append(AssertionResult(
                            name=f"accepted_range_{col}_non_negative",
                            assertion_type="accepted_range",
                            passed=not is_neg,
                            description=f"Assert {col} >= 0",
                            failure_reason=f"accepted_range_violation_negative_values_in_{col}" if is_neg else None,
                        ))
            elif suite is None and suite_path is None and self.suite is None:
                tested_range_cols = {getattr(a, "column", None) for a in active_suite.assertions if a.assertion_type == "accepted_range"}
                num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
                for col in num_cols:
                    if col not in tested_range_cols and col in df.columns:
                        is_neg = bool((df[col] < 0).any())
                        results.append(AssertionResult(
                            name=f"accepted_range_{col}_non_negative",
                            assertion_type="accepted_range",
                            passed=not is_neg,
                            description=f"Assert {col} >= 0",
                            failure_reason=f"accepted_range_violation_negative_values_in_{col}" if is_neg else None,
                        ))

        failed_results = [r for r in results if not r.passed]
        passed = (len(failed_results) == 0)
        failure_reason = failed_results[0].failure_reason if failed_results else None

        return {
            "tier": BaselineTier.TIER_2_REALISTIC_DBT.value,
            "passed": passed,
            "checks_count": len(results),
            "passed_checks_count": len(results) - len(failed_results),
            "failed_checks_count": len(failed_results),
            "violations": [r.failure_reason for r in failed_results if r.failure_reason],
            "reason": failure_reason,
            "details": [r.model_dump() if hasattr(r, "model_dump") else r.__dict__ for r in results],
        }

    def evaluate_tier_3_static_scos_ast(self, sql: str) -> Dict[str, Any]:
        """Tier 3: Static SCOS AST invariant compiler."""
        if not self.contract:
            return {"tier": BaselineTier.TIER_3_STATIC_SCOS_AST.value, "passed": True, "reason": "no_contract"}
        res = SemanticContractValidator.validate(sql, self.contract)
        return {
            "tier": BaselineTier.TIER_3_STATIC_SCOS_AST.value,
            "passed": res.passed,
            "violations_count": len(res.violations),
            "violations": [v.invariant_rule for v in res.violations],
        }

    def evaluate_all_tiers(
        self,
        sql: str,
        df: Optional[pd.DataFrame] = None,
        suite: Optional[AssertionSuite] = None,
        conn: Optional[duckdb.DuckDBPyConnection] = None,
    ) -> Dict[str, Any]:
        """Runs candidate SQL through all 4 tiers in sequence."""
        t0 = self.evaluate_tier_0_syntax(sql)
        t1 = self.evaluate_tier_1_minimal_structural(df) if t0["passed"] else {"tier": BaselineTier.TIER_1_MINIMAL_STRUCTURAL.value, "passed": False}
        t2 = self.evaluate_tier_2_realistic_dbt(df=df, sql=sql, conn=conn, suite=suite) if t1["passed"] else {"tier": BaselineTier.TIER_2_REALISTIC_DBT.value, "passed": False}
        t3 = self.evaluate_tier_3_static_scos_ast(sql)

        return {
            "tier_0_syntax": t0["passed"],
            "tier_1_minimal_structural": t1["passed"],
            "tier_2_realistic_dbt": t2["passed"],
            "tier_3_static_scos_ast": t3["passed"],
            "details": {
                "tier_0": t0,
                "tier_1": t1,
                "tier_2": t2,
                "tier_3": t3,
            }
        }
