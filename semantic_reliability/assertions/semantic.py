import time
from typing import List, Optional
import duckdb

from semantic_reliability.assertions.base import DataAssertion, AssertionResult


class RequiredPopulationAssertion:
    """Semantic assertion: Verifies that no source records violating business filters leak into output."""
    assertion_type = "required_population"

    def __init__(self, source_table: str, required_filter: str, join_key: str = "customer_id", name: Optional[str] = None):
        self.source_table = source_table
        self.required_filter = required_filter
        self.join_key = join_key
        clean_filter = required_filter.replace(" ", "_").replace("=", "eq").replace("'", "")
        self.name = name or f"population_filter_{clean_filter}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        # Find if any entity in output violates the required business filter in the raw table
        wrapped_query = f"""
        WITH target_model AS ({sql}),
        invalid_entities AS (
            SELECT src.{self.join_key}
            FROM target_model tm
            JOIN {self.source_table} src ON tm.{self.join_key} = src.{self.join_key}
            WHERE NOT ({self.required_filter})
        )
        SELECT COUNT(*) FROM invalid_entities;
        """
        try:
            res = con.execute(wrapped_query).fetchone()
            leaked_count = res[0] if res else 0
            passed = (leaked_count == 0)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Ensure population strictly conforms to `{self.required_filter}` on `{self.source_table}`",
                failure_reason=None if passed else f"Found {leaked_count} record(s) in output violating required filter `{self.required_filter}`",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Ensure population filter `{self.required_filter}`",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )


class MetricValueAssertion:
    """Semantic assertion: Verifies the aggregate scalar output of a metric against expected ground-truth."""
    assertion_type = "metric_value"

    def __init__(
        self,
        column: str,
        expected_value: Optional[float] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        tolerance_pct: float = 0.01,
        name: Optional[str] = None
    ):
        self.column = column
        self.expected_value = expected_value
        self.min_value = min_value
        self.max_value = max_value
        self.tolerance_pct = tolerance_pct
        self.name = name or f"metric_value_{column}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        wrapped_query = f"WITH target_model AS ({sql}) SELECT SUM({self.column}) AS total_val FROM target_model;"
        try:
            res = con.execute(wrapped_query).fetchone()
            total_val = float(res[0]) if res and res[0] is not None else 0.0

            passed = True
            failure_reason = None

            if self.expected_value is not None:
                delta = abs(total_val - self.expected_value)
                max_allowed_delta = abs(self.expected_value * self.tolerance_pct / 100.0) if self.expected_value != 0 else 0.001
                if delta > max_allowed_delta:
                    passed = False
                    failure_reason = f"Observed sum({self.column}) = {total_val:.2f}, expected {self.expected_value:.2f} (Δ: {delta:.2f})"

            if self.min_value is not None and total_val < self.min_value:
                passed = False
                failure_reason = f"Observed sum({self.column}) = {total_val:.2f} < minimum {self.min_value:.2f}"

            if self.max_value is not None and total_val > self.max_value:
                passed = False
                failure_reason = f"Observed sum({self.column}) = {total_val:.2f} > maximum {self.max_value:.2f}"

            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Assert aggregated {self.column} value conforms to business expectation",
                failure_reason=failure_reason,
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert {self.column} value",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )


class ExpectedGrainAssertion:
    """Semantic assertion: Verifies that output table maintains declared dimensional grain without duplication."""
    assertion_type = "expected_grain"

    def __init__(self, grain_columns: List[str], name: Optional[str] = None):
        self.grain_columns = grain_columns
        self.name = name or f"grain_{'_'.join(grain_columns)}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        cols_str = ", ".join(self.grain_columns)
        wrapped_query = f"""
        WITH target_model AS ({sql}),
        grain_check AS (
            SELECT {cols_str}, COUNT(*) AS row_cnt
            FROM target_model
            GROUP BY {cols_str}
            HAVING COUNT(*) > 1
        )
        SELECT COUNT(*) FROM grain_check;
        """
        try:
            res = con.execute(wrapped_query).fetchone()
            dupe_grain_count = res[0] if res else 0
            passed = (dupe_grain_count == 0)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Assert strict reporting grain across {self.grain_columns}",
                failure_reason=None if passed else f"Found {dupe_grain_count} multi-row collisions violating grain {self.grain_columns}",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert reporting grain across {self.grain_columns}",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
