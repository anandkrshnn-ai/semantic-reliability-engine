from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import duckdb


class ContrastCheckResult(BaseModel):
    check_name: str
    status: str  # "PASS", "WARN", "FAIL"
    details: str
    impact: str


class FixtureAdequacyReport(BaseModel):
    table_name: str
    total_rows: int
    adequacy_score_pct: float
    checks: List[ContrastCheckResult]

    @property
    def is_adequate(self) -> bool:
        return self.adequacy_score_pct >= 70.0


class FixtureAdequacyChecker:
    """Audits fixture datasets to verify whether they contain the conditions necessary to expose mutations."""

    @classmethod
    def audit_fixture(cls, con: duckdb.DuckDBPyConnection, table_name: str = "transactions") -> FixtureAdequacyReport:
        checks: List[ContrastCheckResult] = []

        # 1. Total row count check
        try:
            res = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            row_count = res[0] if res else 0
        except Exception as e:
            return FixtureAdequacyReport(
                table_name=table_name,
                total_rows=0,
                adequacy_score_pct=0.0,
                checks=[ContrastCheckResult(
                    check_name="Table Exists",
                    status="FAIL",
                    details=f"Table `{table_name}` not accessible: {str(e)}",
                    impact="Cannot evaluate fixture adequacy.",
                )],
            )

        if row_count < 3:
            checks.append(ContrastCheckResult(
                check_name="Dataset Volume",
                status="WARN",
                details=f"Fixture has only {row_count} rows. High risk of accidental equivalence.",
                impact="Small sample size may mask valid mutation differences.",
            ))
        else:
            checks.append(ContrastCheckResult(
                check_name="Dataset Volume",
                status="PASS",
                details=f"Fixture has {row_count} representative rows.",
                impact="Sufficient volume for standard relational evaluation.",
            ))

        # Inspect table columns
        cols_info = con.execute(f"DESCRIBE {table_name}").fetchall()
        cols = [c[0].lower() for c in cols_info]

        # 2. Status/Active contrast check
        if "status" in cols:
            distinct_statuses = [r[0] for r in con.execute(f"SELECT DISTINCT status FROM {table_name}").fetchall()]
            if len(distinct_statuses) > 1 and any(s.lower() != "active" for s in distinct_statuses if s):
                checks.append(ContrastCheckResult(
                    check_name="Active/Inactive Status Contrast",
                    status="PASS",
                    details=f"Contains diverse status values: {distinct_statuses}",
                    impact="Filter drops on `status = 'active'` will be exposed.",
                ))
            else:
                checks.append(ContrastCheckResult(
                    check_name="Active/Inactive Status Contrast",
                    status="FAIL",
                    details=f"Only single status value found: {distinct_statuses}",
                    impact="Filter drops on status will be mistakenly classified as equivalent!",
                ))

        # 3. Categorical Boundary Contrast
        cat_cols = [c for c in ["region", "type", "category", "channel"] if c in cols]
        for c in cat_cols:
            distinct_vals = [r[0] for r in con.execute(f"SELECT DISTINCT {c} FROM {table_name}").fetchall()]
            if len(distinct_vals) > 1:
                checks.append(ContrastCheckResult(
                    check_name=f"Categorical Boundary Contrast (`{c}`)",
                    status="PASS",
                    details=f"Contains {len(distinct_vals)} distinct values: {distinct_vals}",
                    impact=f"Mutations modifying `{c}` boundary filters will be exposed.",
                ))
            else:
                checks.append(ContrastCheckResult(
                    check_name=f"Categorical Boundary Contrast (`{c}`)",
                    status="WARN",
                    details=f"Column `{c}` has only 1 distinct value: {distinct_vals}",
                    impact=f"Boundary mutations on `{c}` may produce false equivalent outcomes.",
                ))

        # 4. Numerical Aggregation Component Contrast
        num_cols = [c for c in ["amount", "revenue", "price", "cost", "quantity"] if c in cols]
        if num_cols:
            n_col = num_cols[0]
            val_stats = con.execute(f"SELECT MIN({n_col}), MAX({n_col}), AVG({n_col}) FROM {table_name}").fetchone()
            if val_stats and val_stats[0] is not None and val_stats[1] is not None and val_stats[0] != val_stats[1]:
                checks.append(ContrastCheckResult(
                    check_name=f"Numerical Distribution Contrast (`{n_col}`)",
                    status="PASS",
                    details=f"Range: [{val_stats[0]}, {val_stats[1]}], Mean: {val_stats[2]:.2f}",
                    impact="SUM vs AVG vs COUNT aggregation swaps will produce distinct non-zero variance.",
                ))
            else:
                checks.append(ContrastCheckResult(
                    check_name=f"Numerical Distribution Contrast (`{n_col}`)",
                    status="WARN",
                    details="Uniform or null values detected in numerical column.",
                    impact="Aggregation swaps may yield zero numerical divergence.",
                ))

        # 5. Multi-dimensional Grain Contrast
        grain_cols = [c for c in ["customer_id", "user_id", "order_id", "account_id"] if c in cols]
        if grain_cols:
            g_col = grain_cols[0]
            dupe_groups = con.execute(f"SELECT {g_col}, COUNT(*) FROM {table_name} GROUP BY {g_col} HAVING COUNT(*) > 1").fetchall()
            if len(dupe_groups) > 0:
                checks.append(ContrastCheckResult(
                    check_name="Multi-row Grain Multiplicity",
                    status="PASS",
                    details=f"Multiple records exist per `{g_col}` entity.",
                    impact="Grouping key omissions (Grain Drop) will trigger detectable row count shifts.",
                ))
            else:
                checks.append(ContrastCheckResult(
                    check_name="Multi-row Grain Multiplicity",
                    status="WARN",
                    details=f"Each `{g_col}` appears at most once in fixture.",
                    impact="Grain reductions may preserve 1:1 row cardinalities on this fixture.",
                ))

        pass_count = sum(1 for c in checks if c.status == "PASS")
        score = (pass_count / len(checks) * 100.0) if checks else 0.0

        return FixtureAdequacyReport(
            table_name=table_name,
            total_rows=row_count,
            adequacy_score_pct=round(score, 1),
            checks=checks,
        )
