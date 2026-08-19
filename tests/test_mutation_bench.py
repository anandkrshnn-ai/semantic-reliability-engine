import pytest
from semantic_reliability.harness.duckdb_runner import DuckDBFixtureRunner, MutationClassification
from semantic_reliability.assertions.registry import AssertionSuite
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


def test_standard_dbt_suite_leaves_surviving_defects():
    runner = DuckDBFixtureRunner()
    mutator = MutationEngine(BASE_SQL)
    mutations = mutator.generate_all_mutations()

    dbt_suite = AssertionSuite.get_standard_structural_suite()
    report = runner.run_assertion_benchmark(BASE_SQL, mutations, dbt_suite)

    # Standard dbt checks (not_null + unique + row_count) pass on filter removal and math invert!
    assert report.surviving_defects_count > 0
    assert report.effective_catch_score_pct < 100.0

    # Ensure surviving defects are captured
    surviving_types = [
        e.mutation_type for e in report.evaluations
        if e.classification == MutationClassification.VALID_DEFECT_SURVIVED
    ]
    assert len(surviving_types) > 0


def test_semantic_suite_catches_surviving_defects():
    runner = DuckDBFixtureRunner()
    mutator = MutationEngine(BASE_SQL)
    mutations = mutator.generate_all_mutations()

    semantic_suite = AssertionSuite.get_semantic_assertion_suite()
    report = runner.run_assertion_benchmark(BASE_SQL, mutations, semantic_suite)

    # Semantic suite achieves higher catch score by enforcing population & metric value
    dbt_suite = AssertionSuite.get_standard_structural_suite()
    dbt_report = runner.run_assertion_benchmark(BASE_SQL, mutations, dbt_suite)

    assert report.effective_catch_score_pct >= dbt_report.effective_catch_score_pct
    assert report.detected_by_assertions_count >= dbt_report.detected_by_assertions_count
