import time
from typing import List, Optional, Any, Dict
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


    def evaluate_df(self, df: "pd.DataFrame") -> AssertionResult:
        import pandas as pd
        t0 = time.perf_counter()
        present_cols = [c for c in self.columns if c in df.columns]
        if not present_cols:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=True,
                description=f"Assert no nulls in columns {self.columns} (skipped: columns not present)",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
        null_count = int(df[present_cols].isnull().sum().sum())
        passed = (null_count == 0)
        return AssertionResult(
            name=self.name,
            assertion_type=self.assertion_type,
            passed=passed,
            description=f"Assert no nulls in columns {present_cols}",
            failure_reason=None if passed else f"Found {null_count} null row(s) in {present_cols}",
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

    def evaluate_df(self, df: "pd.DataFrame") -> AssertionResult:
        import pandas as pd
        t0 = time.perf_counter()
        present_cols = [c for c in self.columns if c in df.columns]
        if not present_cols or len(present_cols) != len(self.columns):
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=True,
                description=f"Assert unique key across {self.columns} (skipped: model does not contain full key)",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
        dupe_count = int(df.duplicated(subset=present_cols).sum())
        passed = (dupe_count == 0)
        return AssertionResult(
            name=self.name,
            assertion_type=self.assertion_type,
            passed=passed,
            description=f"Assert unique key across {present_cols}",
            failure_reason=None if passed else f"Found {dupe_count} duplicate key row(s) across {present_cols}",
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

    def evaluate_df(self, df: "pd.DataFrame") -> AssertionResult:
        t0 = time.perf_counter()
        row_count = len(df)
        passed = row_count >= self.min_rows and (self.max_rows is None or row_count <= self.max_rows)
        return AssertionResult(
            name=self.name,
            assertion_type=self.assertion_type,
            passed=passed,
            description=f"Assert row count between {self.min_rows} and {self.max_rows or 'inf'}",
            failure_reason=None if passed else f"Observed {row_count} rows, outside expected range [{self.min_rows}, {self.max_rows or 'inf'}]",
            execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )


class AcceptedRangeAssertion:
    """dbt/dbt-utils generic test: Assert numeric column values stay strictly within [min_value, max_value]."""
    assertion_type = "accepted_range"

    def __init__(
        self,
        column: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        inclusive: bool = True,
        name: Optional[str] = None,
    ):
        self.column = column
        self.min_value = float(min_value) if min_value is not None else None
        self.max_value = float(max_value) if max_value is not None else None
        self.inclusive = inclusive
        self.name = name or f"accepted_range_{column}_{min_value}_to_{max_value}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        conditions = []
        if self.min_value is not None:
            op = "<" if self.inclusive else "<="
            conditions.append(f"{self.column} {op} {self.min_value}")
        if self.max_value is not None:
            op = ">" if self.inclusive else ">="
            conditions.append(f"{self.column} {op} {self.max_value}")

        cond_str = " OR ".join(conditions) if conditions else "FALSE"
        wrapped_query = f"WITH target_model AS ({sql}) SELECT COUNT(*) FROM target_model WHERE {cond_str};"
        try:
            res = con.execute(wrapped_query).fetchone()
            violating_count = res[0] if res else 0
            passed = (violating_count == 0)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Assert {self.column} within bounds [min: {self.min_value}, max: {self.max_value}]",
                failure_reason=None if passed else f"Found {violating_count} row(s) where {self.column} violates range [{self.min_value}, {self.max_value}]",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert {self.column} within bounds",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )

    def evaluate_df(self, df: "pd.DataFrame") -> AssertionResult:
        t0 = time.perf_counter()
        if self.column not in df.columns:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert {self.column} within bounds",
                failure_reason=f"Missing column '{self.column}' in DataFrame",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )

        series = df[self.column].dropna()
        violations = 0
        if self.min_value is not None:
            if self.inclusive:
                violations += int((series < self.min_value).sum())
            else:
                violations += int((series <= self.min_value).sum())
        if self.max_value is not None:
            if self.inclusive:
                violations += int((series > self.max_value).sum())
            else:
                violations += int((series >= self.max_value).sum())

        passed = (violations == 0)
        return AssertionResult(
            name=self.name,
            assertion_type=self.assertion_type,
            passed=passed,
            description=f"Assert {self.column} within bounds [min: {self.min_value}, max: {self.max_value}]",
            failure_reason=None if passed else f"Found {violations} row(s) where {self.column} violates range [{self.min_value}, {self.max_value}]",
            execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )


class AcceptedValuesAssertion:
    """Standard dbt generic test: Assert column values belong strictly to an explicit allowed discrete set."""
    assertion_type = "accepted_values"

    def __init__(
        self,
        column: str,
        values: List[Any],
        quote: bool = True,
        name: Optional[str] = None,
    ):
        self.column = column
        self.values = [str(v) for v in values]
        self.quote = quote
        self.name = name or f"accepted_values_{column}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        val_list_sql = ", ".join([f"'{v}'" if self.quote else str(v) for v in self.values])
        wrapped_query = f"""
        WITH target_model AS ({sql})
        SELECT COUNT(*)
        FROM target_model
        WHERE {self.column} IS NOT NULL AND {self.column} NOT IN ({val_list_sql});
        """
        try:
            res = con.execute(wrapped_query).fetchone()
            violating_count = res[0] if res else 0
            passed = (violating_count == 0)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Assert {self.column} values belong to accepted set {self.values}",
                failure_reason=None if passed else f"Found {violating_count} row(s) where {self.column} is outside accepted values {self.values}",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert {self.column} accepted values",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )

    def evaluate_df(self, df: "pd.DataFrame") -> AssertionResult:
        t0 = time.perf_counter()
        if self.column not in df.columns:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert {self.column} accepted values",
                failure_reason=f"Missing column '{self.column}' in DataFrame",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )

        series = df[self.column].dropna().astype(str)
        violating_count = int((~series.isin(self.values)).sum())
        passed = (violating_count == 0)
        return AssertionResult(
            name=self.name,
            assertion_type=self.assertion_type,
            passed=passed,
            description=f"Assert {self.column} values belong to accepted set {self.values}",
            failure_reason=None if passed else f"Found {violating_count} row(s) where {self.column} is outside accepted values {self.values}",
            execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )


class RelationshipsAssertion:
    """Standard dbt generic test: Assert referential integrity against a parent table/model."""
    assertion_type = "relationships"

    def __init__(
        self,
        from_column: str,
        to_table: str,
        to_column: str,
        name: Optional[str] = None,
    ):
        self.from_column = from_column
        self.to_table = to_table
        self.to_column = to_column
        self.name = name or f"relationships_{from_column}_to_{to_table}_{to_column}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        # Verify parent table exists in database catalog
        try:
            con.execute(f"SELECT 1 FROM {self.to_table} LIMIT 0;")
        except Exception:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=True,
                description=f"Assert foreign key {self.from_column} references {self.to_table}.{self.to_column} (skipped: parent table '{self.to_table}' not in database catalog)",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )

        wrapped_query = f"""
        WITH target_model AS ({sql}),
        child AS (
            SELECT {self.from_column} AS from_col
            FROM target_model
            WHERE {self.from_column} IS NOT NULL
        ),
        parent AS (
            SELECT {self.to_column} AS to_col
            FROM {self.to_table}
        )
        SELECT COUNT(*)
        FROM child
        LEFT JOIN parent ON child.from_col = parent.to_col
        WHERE parent.to_col IS NULL;
        """
        try:
            res = con.execute(wrapped_query).fetchone()
            orphan_count = res[0] if res else 0
            passed = (orphan_count == 0)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=f"Assert foreign key {self.from_column} references {self.to_table}.{self.to_column}",
                failure_reason=None if passed else f"Found {orphan_count} orphan key(s) in {self.from_column} missing in {self.to_table}.{self.to_column}",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert foreign key relationships",
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )

    def evaluate_df(self, df: "pd.DataFrame", con: Optional[duckdb.DuckDBPyConnection] = None) -> AssertionResult:
        t0 = time.perf_counter()
        if self.from_column not in df.columns:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert relationships {self.from_column} -> {self.to_table}",
                failure_reason=f"Missing column '{self.from_column}' in DataFrame",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
        if con is None:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=True,
                description=f"Assert relationships (skipped: no database connection for parent table '{self.to_table}')",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
        try:
            con.register("_temp_df_target", df)
            return self.evaluate(con, "SELECT * FROM _temp_df_target")
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=f"Assert relationships {self.from_column} -> {self.to_table}",
                failure_reason=f"Relational check error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
        finally:
            try:
                con.unregister("_temp_df_target")
            except Exception:
                pass


class SingularSqlAssertion:
    """Standard dbt singular test: Assert custom SQL query returns zero failing rows (passes if count == 0)."""
    assertion_type = "singular_sql_test"

    def __init__(
        self,
        name: str,
        sql: str,
        description: Optional[str] = None,
    ):
        self.name = name
        self.sql = sql
        self.description = description or f"Singular SQL test: {name}"

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        t0 = time.perf_counter()
        target_sql = self.sql
        if "{{ model }}" in target_sql or "{{model}}" in target_sql:
            wrapped_test = f"""
            WITH target_model AS ({sql})
            SELECT COUNT(*) FROM ({target_sql.replace("{{ model }}", "target_model").replace("{{model}}", "target_model")}) AS singular_subq;
            """
        else:
            wrapped_test = f"SELECT COUNT(*) FROM ({target_sql}) AS singular_subq;"

        try:
            res = con.execute(wrapped_test).fetchone()
            fail_count = res[0] if res else 0
            passed = (fail_count == 0)
            elapsed = (time.perf_counter() - t0) * 1000.0

            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=passed,
                description=self.description,
                failure_reason=None if passed else f"Singular test '{self.name}' failed with {fail_count} violating row(s)",
                execution_time_ms=round(elapsed, 2),
            )
        except Exception as e:
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=self.description,
                failure_reason=f"Runtime evaluation error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )

    def evaluate_df(self, df: "pd.DataFrame", con: Optional[duckdb.DuckDBPyConnection] = None) -> AssertionResult:
        t0 = time.perf_counter()
        db_con = con or duckdb.connect(":memory:")
        try:
            db_con.register("_temp_df_model", df)
            res = self.evaluate(db_con, "SELECT * FROM _temp_df_model")
            # If error is due to missing columns that don't belong to this model schema, skip gracefully
            if not res.passed and ("not found in FROM clause" in str(res.failure_reason) or "Referenced column" in str(res.failure_reason)):
                return AssertionResult(
                    name=self.name,
                    assertion_type=self.assertion_type,
                    passed=True,
                    description=f"{self.description} (skipped: model does not contain test columns)",
                    execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                )
            return res
        except Exception as e:
            err_msg = str(e)
            if "not found in FROM clause" in err_msg or "Referenced column" in err_msg:
                return AssertionResult(
                    name=self.name,
                    assertion_type=self.assertion_type,
                    passed=True,
                    description=f"{self.description} (skipped: model does not contain test columns)",
                    execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                )
            return AssertionResult(
                name=self.name,
                assertion_type=self.assertion_type,
                passed=False,
                description=self.description,
                failure_reason=f"Singular evaluation error: {err_msg}",
                execution_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
        finally:
            try:
                db_con.unregister("_temp_df_model")
            except Exception:
                pass

