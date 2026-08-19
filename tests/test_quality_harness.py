import pytest
from semantic_reliability.harness.quality_harness import QualityHarness
from semantic_reliability.harness.reporter import Reporter
from semantic_reliability.drift.detector import SemanticDriftDetector

BASE_SQL = """
SELECT
  customer_id,
  SUM(amount) AS total_revenue
FROM transactions
WHERE region = 'NA' AND amount > 0
GROUP BY customer_id
"""

CAND_SQL = """
SELECT
  customer_id,
  AVG(amount) AS total_revenue
FROM transactions
WHERE region = 'EU'
GROUP BY customer_id
"""


def test_quality_harness_evaluation():
    benchmark = QualityHarness.evaluate_model(BASE_SQL)
    assert benchmark.total_mutations > 0
    assert 0.0 <= benchmark.mutation_score_pct <= 100.0
    assert len(benchmark.evaluations) == benchmark.total_mutations


def test_pr_comment_markdown_generation():
    drifts = SemanticDriftDetector.analyze(BASE_SQL, CAND_SQL)
    md = Reporter.generate_pr_comment_markdown(drifts, model_name="fct_revenue.sql", metric_name="net_revenue")
    assert "Semantic Drift Alert" in md
    assert "WHERE Clause" in md or "SELECT Clause" in md


def test_benchmark_report_markdown():
    benchmark = QualityHarness.evaluate_model(BASE_SQL)
    md = Reporter.generate_benchmark_report_markdown(benchmark, model_name="fct_revenue.sql")
    assert "Semantic Mutation Benchmark Report" in md
    assert "Mutation Score" in md
