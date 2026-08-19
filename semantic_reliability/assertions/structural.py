import time
from typing import List, Optional
import duckdb
from pydantic import BaseModel, Field

from semantic_reliability.assertions.base import DataAssertion, AssertionResult


class NonNullOutputAssertion:
    """Standard dbt-style check: Assert specific columns contain zero NULL values."""
    assertion_type = "not_null"

    def __init__(self, columns: List[str], name: Optional[str] = None):
        self.columns = columns
        self.name = name or f"not_null_{'_'.join(columns)}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        null_predicates = " OR ".join([f"{col} IS NULL" for col in self.columns])
        wrapped_query = f"""
        WITH target_model AS ({sql})
        SELECT COUNT(*) AS null_count
        FROM target_model
        WHERE {null_predicates};
        """
        try:
            res = con.execute(wrapped_query).fetchone()
            null_count = res[0] if res else 0
            passed = (null_count == 0)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Assert no nulls in columns {self.columns}",
                failure_reason=None if passed else f"Found {null_count} null row(s) in {self.columns}",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert no nulls in columns {self.columns}",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )


class UniqueKeyAssertion:
    """Standard dbt-style check: Assert composite/single key uniqueness (no duplicates)."""
    assertion_type = "unique_key"

    def __init__(self, columns: List[str], name: Optional[str] = None):
        self.columns = columns
        self.name = name or f"unique_{'_'.join(columns)}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        cols_str = ", ".join(self.columns)
        wrapped_query = f"""
        WITH target_model AS ({sql}),
        dupes AS (
            SELECT {cols_str}, COUNT(*) AS cnt
            FROM target_model
            GROUP BY {cols_str}
            HAVING COUNT(*) > 1
        )
        SELECT COUNT(*) FROM dupes;
        """
        try:
            res = con.execute(wrapped_query).fetchone()
            dupe_count = res[0] if res else 0
            passed = (dupe_count == 0)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Assert unique key across {self.columns}",
                failure_reason=None if passed else f"Found {dupe_count} duplicate key group(s) across {self.columns}",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert unique key across {self.columns}",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )


class RowCountBoundsAssertion:
    """Standard volumetric check: Assert row count is non-zero and within expected volume bounds."""
    assertion_type = "row_count_bounds"

    def __init__(self, min_rows: int = 1, max_rows: Optional[int] = None, name: Optional[str] = None):
        self.min_rows = min_rows
        self.max_rows = max_rows
        self.name = name or f"row_count_bounds_{min_rows}_to_{max_rows or 'inf'}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        wrapped_query = f"WITH target_model AS ({sql}) SELECT COUNT(*) FROM target_model;"
        try:
            res = con.execute(wrapped_query).fetchone()
            row_count = res[0] if res else 0
            passed = row_count >= self.min_rows and (self.max_rows is None or row_count <= self.max_rows)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Assert row count between {self.min_rows} and {self.max_rows or 'inf'}",
                failure_reason=None if passed else f"Observed {row_count} rows, outside expected range [{self.min_rows}, {self.max_rows or 'inf'}]",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description="Assert row count bounds",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
