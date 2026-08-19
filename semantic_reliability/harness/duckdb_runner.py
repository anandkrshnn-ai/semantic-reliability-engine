import io
import duckdb
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from enum import Enum
from pydantic import BaseModel, Field

from semantic_reliability.mutations.mutators import MutationResult, MutationType
from semantic_reliability.assertions.base import AssertionResult, DataAssertion
from semantic_reliability.assertions.registry import AssertionSuite


class MutationClassification(str, Enum):
    EQUIVALENT_ON_FIXTURE = "EQUIVALENT_ON_FIXTURE"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    VALID_DEFECT_DETECTED = "VALID_DEFECT_DETECTED"
    VALID_DEFECT_SURVIVED = "VALID_DEFECT_SURVIVED"
    CONTRACT_ONLY_DETECTION = "CONTRACT_ONLY_DETECTION"


class AssertionAwareExecutionDiff(BaseModel):
    """Detailed evaluation of an injected mutation under fixture data and test assertions."""
    mutation_id: str
    mutation_type: str
    description: str
    baseline_row_count: int
    mutated_row_count: int
    row_count_delta: int
    is_equivalent_on_fixture: bool
    empirical_variance_pct: float
    result_changed: bool
    assertions_failed: List[str] = Field(default_factory=list)
    classification: MutationClassification
    summary: str


class AssertionBenchmarkReport(BaseModel):
    """Comprehensive mutation catch benchmark results evaluated against an AssertionSuite."""
    suite_name: str
    total_mutations_generated: int
    executable_mutations_count: int
    equivalent_mutations_count: int
    valid_defects_count: int
    detected_by_assertions_count: int
    surviving_defects_count: int
    effective_catch_score_pct: float
    surviving_defect_summaries: List[str] = Field(default_factory=list)
    evaluations: List[AssertionAwareExecutionDiff]

    @property
    def unexecutable_mutations_count(self) -> int:
        return self.total_mutations_generated - self.executable_mutations_count


class DuckDBFixtureRunner:
    """Executes baseline vs mutated SQL queries inside in-memory DuckDB and evaluates assertion suites."""

    def __init__(self, fixtures: Optional[Dict[str, pd.DataFrame | str | Path]] = None):
        self.con = duckdb.connect(":memory:")
        self._load_fixtures(fixtures)

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:
            pass

    def _load_fixtures(self, fixtures: Optional[Dict[str, Any]] = None) -> None:
        if fixtures:
            for table_name, data in fixtures.items():
                if isinstance(data, (str, Path)):
                    path_str = str(data)
                    if path_str.endswith(".csv"):
                        self.con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{path_str}')")
                elif isinstance(data, pd.DataFrame):
                    self.con.register(table_name, data)
        else:
            default_csv = Path(__file__).resolve().parent.parent.parent / "examples" / "fixtures" / "transactions.csv"
            if default_csv.exists():
                self.con.execute(f"CREATE TABLE transactions AS SELECT * FROM read_csv_auto('{default_csv}')")
            else:
                self.con.execute("""
                    CREATE TABLE transactions (
                        transaction_id VARCHAR,
                        customer_id VARCHAR,
                        transaction_date TIMESTAMP,
                        amount DOUBLE,
                        type VARCHAR,
                        status VARCHAR,
                        region VARCHAR,
                        last_login TIMESTAMP
                    );
                    INSERT INTO transactions VALUES
                    ('T1', 'C1', '2026-01-05 10:00:00', 1000.0, 'invoice', 'active', 'NA', '2026-08-01'),
                    ('T2', 'C1', '2026-01-12 11:30:00', 200.0, 'refund', 'active', 'NA', '2026-08-01'),
                    ('T3', 'C2', '2026-01-15 09:15:00', 2500.0, 'invoice', 'active', 'NA', '2026-08-10'),
                    ('T4', 'C2', '2026-01-20 14:00:00', 500.0, 'refund', 'active', 'NA', '2026-08-10'),
                    ('T5', 'C3', '2026-01-18 16:45:00', 3000.0, 'invoice', 'pending', 'NA', '2026-05-01');
                """)

    def execute_query(self, sql: str) -> Tuple[pd.DataFrame, Optional[str]]:
        try:
            df = self.con.execute(sql).df()
            return df, None
        except Exception as e:
            return pd.DataFrame(), str(e)

    def evaluate_assertions(self, sql: str, suite: AssertionSuite) -> List[AssertionResult]:
        results = []
        for assertion in suite.assertions:
            res = assertion.evaluate(self.con, sql)
            results.append(res)
        return results

    def compare_execution_with_assertions(
        self,
        baseline_sql: str,
        mutated_sql: str,
        mutation_id: str,
        mutation_type: str,
        description: str,
        assertion_suite: Optional[AssertionSuite] = None,
    ) -> AssertionAwareExecutionDiff:
        base_df, base_err = self.execute_query(baseline_sql)
        mut_df, mut_err = self.execute_query(mutated_sql)

        # 1. Check for runtime syntax / execution error
        if base_err or mut_err:
            failed_checks = ["RuntimeExecutionError"]
            return AssertionAwareExecutionDiff(
                mutation_id=mutation_id,
                mutation_type=mutation_type,
                description=description,
                baseline_row_count=len(base_df),
                mutated_row_count=0,
                row_count_delta=-len(base_df),
                is_equivalent_on_fixture=False,
                empirical_variance_pct=100.0,
                result_changed=True,
                assertions_failed=failed_checks,
                classification=MutationClassification.RUNTIME_ERROR,
                summary=f"Runtime error triggered in database: {mut_err or base_err}",
            )

        base_rows = len(base_df)
        mut_rows = len(mut_df)
        row_delta = mut_rows - base_rows

        # 2. Check for empirical output variance on fixture data
        is_equiv = False
        variance_pct = 0.0

        if base_rows == mut_rows and list(base_df.columns) == list(mut_df.columns):
            try:
                numeric_cols = base_df.select_dtypes(include=["number"]).columns
                if len(numeric_cols) > 0:
                    base_sum = float(base_df[numeric_cols].sum().sum())
                    mut_sum = float(mut_df[numeric_cols].sum().sum())
                    if base_sum != 0:
                        variance_pct = abs(mut_sum - base_sum) / abs(base_sum) * 100.0
                    else:
                        variance_pct = 100.0 if mut_sum != 0 else 0.0

                    if variance_pct < 0.001:
                        is_equiv = True
                else:
                    is_equiv = base_df.equals(mut_df)
            except Exception:
                is_equiv = False
        else:
            variance_pct = abs(row_delta) / (base_rows if base_rows > 0 else 1.0) * 100.0

        result_changed = not is_equiv

        # 3. Evaluate configured assertions on the mutated query
        failed_assertions = []
        if assertion_suite:
            assertion_results = self.evaluate_assertions(mutated_sql, assertion_suite)
            failed_assertions = [r.name for r in assertion_results if not r.passed]

        # 4. Classify outcome
        if is_equiv:
            classification = MutationClassification.EQUIVALENT_ON_FIXTURE
            summary = "Equivalent output on fixture (global semantic equivalence not established)"
        elif len(failed_assertions) > 0:
            classification = MutationClassification.VALID_DEFECT_DETECTED
            summary = f"Detected by assertion(s): {', '.join(failed_assertions)}"
        else:
            classification = MutationClassification.VALID_DEFECT_SURVIVED
            summary = f"SURVIVING DEFECT: Passed all tests despite row Δ={row_delta:+d}, variance={variance_pct:.1f}%"

        return AssertionAwareExecutionDiff(
            mutation_id=mutation_id,
            mutation_type=mutation_type,
            description=description,
            baseline_row_count=base_rows,
            mutated_row_count=mut_rows,
            row_count_delta=row_delta,
            is_equivalent_on_fixture=is_equiv,
            empirical_variance_pct=round(variance_pct, 1),
            result_changed=result_changed,
            assertions_failed=failed_assertions,
            classification=classification,
            summary=summary,
        )

    def run_assertion_benchmark(
        self,
        baseline_sql: str,
        mutations: List[MutationResult],
        assertion_suite: Optional[AssertionSuite] = None,
    ) -> AssertionBenchmarkReport:
        suite = assertion_suite or AssertionSuite.get_standard_structural_suite()
        evaluations: List[AssertionAwareExecutionDiff] = []
        equiv_count = 0
        detected_count = 0
        surviving_count = 0
        surviving_summaries: List[str] = []

        for idx, mut in enumerate(mutations, 1):
            diff = self.compare_execution_with_assertions(
                baseline_sql=baseline_sql,
                mutated_sql=mut.mutated_sql,
                mutation_id=f"MUT_{idx:02d}",
                mutation_type=mut.mutation_type.value,
                description=mut.description,
                assertion_suite=suite,
            )
            evaluations.append(diff)

            if diff.classification == MutationClassification.EQUIVALENT_ON_FIXTURE:
                equiv_count += 1
            elif diff.classification in (MutationClassification.VALID_DEFECT_DETECTED, MutationClassification.RUNTIME_ERROR):
                detected_count += 1
            elif diff.classification == MutationClassification.VALID_DEFECT_SURVIVED:
                surviving_count += 1
                surviving_summaries.append(f"[{diff.mutation_type}] {diff.description} -> {diff.summary}")

        total_gen = len(mutations)
        executable_valid = total_gen - equiv_count
        effective_catch_score = (detected_count / executable_valid * 100.0) if executable_valid > 0 else 100.0

        return AssertionBenchmarkReport(
            suite_name=suite.name,
            total_mutations_generated=total_gen,
            executable_mutations_count=total_gen,
            equivalent_mutations_count=equiv_count,
            valid_defects_count=executable_valid,
            detected_by_assertions_count=detected_count,
            surviving_defects_count=surviving_count,
            effective_catch_score_pct=round(effective_catch_score, 1),
            surviving_defect_summaries=surviving_summaries,
            evaluations=evaluations,
        )
