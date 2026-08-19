import pytest
from semantic_reliability.drift.detector import SemanticDriftDetector
from semantic_reliability.drift.rules import DriftSeverity, DriftType

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


def test_drift_filter_removal():
    cand_sql = """
    SELECT
      customer_id,
      DATE_TRUNC('month', transaction_date) AS reporting_month,
      SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
      SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
    FROM transactions
    GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
    """
    drifts = SemanticDriftDetector.analyze(BASE_SQL, cand_sql)
    assert any(d.drift_type == DriftType.FILTER_REMOVAL and d.severity == DriftSeverity.FATAL for d in drifts)


def test_drift_filter_logic_shift():
    cand_sql = """
    SELECT
      customer_id,
      DATE_TRUNC('month', transaction_date) AS reporting_month,
      SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
      SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
    FROM transactions
    WHERE region = 'NA' AND status = 'pending'
    GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
    """
    drifts = SemanticDriftDetector.analyze(BASE_SQL, cand_sql)
    assert any(d.drift_type == DriftType.SEMANTIC_LOGIC_SHIFT and d.severity == DriftSeverity.CRITICAL for d in drifts)


def test_drift_aggregation_function_shift():
    cand_sql = """
    SELECT
      customer_id,
      DATE_TRUNC('month', transaction_date) AS reporting_month,
      AVG(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) AS net_revenue
    FROM transactions
    WHERE region = 'NA' AND status = 'active'
    GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
    """
    drifts = SemanticDriftDetector.analyze(BASE_SQL, cand_sql)
    assert any(d.drift_type == DriftType.AGGREGATION_FUNCTION_SHIFT for d in drifts)


def test_drift_grain_shift():
    cand_sql = """
    SELECT
      customer_id,
      SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
      SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
    FROM transactions
    WHERE region = 'NA' AND status = 'active'
    GROUP BY customer_id
    """
    drifts = SemanticDriftDetector.analyze(BASE_SQL, cand_sql)
    assert any(d.drift_type == DriftType.GRAIN_DRIFT for d in drifts)


def test_drift_join_predicate_drop():
    base_join = "SELECT * FROM orders o JOIN customers c ON o.cust_id = c.id WHERE o.active = true"
    cand_join = "SELECT * FROM orders o JOIN customers c WHERE o.active = true"
    drifts = SemanticDriftDetector.analyze(base_join, cand_join)
    assert any(d.drift_type == DriftType.JOIN_PREDICATE_MUTATION and d.severity == DriftSeverity.FATAL for d in drifts)


def test_no_drift_on_identical_sql():
    drifts = SemanticDriftDetector.analyze(BASE_SQL, BASE_SQL)
    assert len(drifts) == 0
