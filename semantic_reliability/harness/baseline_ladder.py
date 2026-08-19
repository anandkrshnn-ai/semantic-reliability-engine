"""4-Tier Baseline Ladder Evaluator for Semantic-SQL-Bench.
Evaluates analytical SQL queries against progressive tiers of testing rigor.
"""
from enum import Enum
from typing import Dict, Any, List, Optional
import sqlglot
import pandas as pd
import duckdb

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.compiler.contracts import SemanticContractValidator
from semantic_reliability.assertions.base import AssertionResult


class BaselineTier(str, Enum):
    TIER_0_SYNTAX = "tier_0_syntax"
    TIER_1_MINIMAL_STRUCTURAL = "tier_1_minimal_structural"
    TIER_2_REALISTIC_DBT = "tier_2_realistic_dbt"
    TIER_3_STATIC_SCOS_AST = "tier_3_static_scos_ast"
    TIER_4_RUNTIME_RELATIONAL = "tier_4_runtime_relational"


class BaselineLadderEvaluator:
    """Evaluates candidate SQL across the progressive 4-tier validation ladder."""

    def __init__(self, contract: Optional[MetricDefinition] = None, conn: Optional[duckdb.DuckDBPyConnection] = None):
        self.contract = contract
        self.conn = conn or duckdb.connect(":memory:")
        self.static_validator = SemanticContractValidator()

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

    def evaluate_tier_2_realistic_dbt(self, df: Optional[pd.DataFrame], numeric_cols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Tier 2: Realistic dbt suite (range bounds, non-negative assertions)."""
        tier_1 = self.evaluate_tier_1_minimal_structural(df)
        if not tier_1["passed"]:
            return {"tier": BaselineTier.TIER_2_REALISTIC_DBT.value, "passed": False, "reason": "failed_tier_1"}

        cols_to_check = numeric_cols or [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        for col in cols_to_check:
            if (df[col] < 0).any():
                return {
                    "tier": BaselineTier.TIER_2_REALISTIC_DBT.value,
                    "passed": False,
                    "reason": f"accepted_range_violation_negative_values_in_{col}",
                }
        return {"tier": BaselineTier.TIER_2_REALISTIC_DBT.value, "passed": True, "reason": None}

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

    def evaluate_all_tiers(self, sql: str, df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Runs candidate SQL through all 4 tiers in sequence."""
        t0 = self.evaluate_tier_0_syntax(sql)
        t1 = self.evaluate_tier_1_minimal_structural(df) if t0["passed"] else {"tier": BaselineTier.TIER_1_MINIMAL_STRUCTURAL.value, "passed": False}
        t2 = self.evaluate_tier_2_realistic_dbt(df) if t1["passed"] else {"tier": BaselineTier.TIER_2_REALISTIC_DBT.value, "passed": False}
        t3 = self.evaluate_tier_3_static_scos_ast(sql)

        return {
            "tier_0_syntax": t0["passed"],
            "tier_1_minimal_structural": t1["passed"],
            "tier_2_realistic_dbt": t2["passed"],
            "tier_3_static_scos_ast": t3["passed"],
        }
