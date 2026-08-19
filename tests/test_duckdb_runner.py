import pytest
from semantic_reliability.harness.duckdb_runner import DuckDBFixtureRunner, MutationClassification
from semantic_reliability.mutations.engine import MutationEngine

BASE_SQL = """
SELECT
  customer_id,
  DATE_TRUNC('month', transaction_date) AS reporting_month,
  SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
  SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
FROM transactions
WHERE region = 'NA' AND status = 'active'
GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
"""


def test_duckdb_runner_execution():
    runner = DuckDBFixtureRunner()
    df, err = runner.execute_query("SELECT COUNT(*) AS cnt FROM transactions")
    assert err is None
    assert len(df) == 1
    assert df["cnt"].iloc[0] > 0


def test_duckdb_compare_identical_query():
    runner = DuckDBFixtureRunner()
    diff = runner.compare_execution_with_assertions(
        baseline_sql=BASE_SQL,
        mutated_sql=BASE_SQL,
        mutation_id="MUT_00",
        mutation_type="IDENTITY",
        description="Identical query execution",
    )
    assert diff.is_equivalent_on_fixture is True
    assert diff.row_count_delta == 0
    assert diff.empirical_variance_pct == 0.0
    assert diff.classification == MutationClassification.EQUIVALENT_ON_FIXTURE


def test_duckdb_compare_filter_drop_variance():
    runner = DuckDBFixtureRunner()
    mutated_sql = """
    SELECT
      customer_id,
      DATE_TRUNC('month', transaction_date) AS reporting_month,
      SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
      SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
    FROM transactions
    GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
    """
    diff = runner.compare_execution_with_assertions(
        baseline_sql=BASE_SQL,
        mutated_sql=mutated_sql,
        mutation_id="MUT_01",
        mutation_type="FILTER_DROP",
        description="Filter drop variance check",
    )
    assert diff.is_equivalent_on_fixture is False
    assert diff.empirical_variance_pct > 0.0 or diff.row_count_delta != 0


def test_duckdb_run_empirical_benchmark():
    runner = DuckDBFixtureRunner()
    mutator = MutationEngine(BASE_SQL)
    mutations = mutator.generate_all_mutations()

    res = runner.run_assertion_benchmark(BASE_SQL, mutations)
    assert res.total_mutations_generated > 0
    assert res.valid_defects_count <= res.total_mutations_generated
    assert 0.0 <= res.effective_catch_score_pct <= 100.0
    assert len(res.evaluations) == res.total_mutations_generated
