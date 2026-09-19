import hashlib
from pathlib import Path

from semantic_reliability.firewall.engine import ContractRegistry, SemanticEvaluator
from semantic_reliability.firewall.models import EvaluateRequest
from semantic_reliability.guardrail import SemanticGuardrail
from semantic_reliability.testing.drift.distance import ast_node_signatures, semantic_drift_distance

CONTRACT_PATH = Path("benchmark_corpus/dev/net_revenue/contract.yaml")

REWRITTEN_EQUIVALENT_SQL = """
SELECT
    customer_id,
    DATE_TRUNC('month', transaction_date) AS reporting_month,
    SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
    SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
FROM transactions
WHERE status = 'active' AND region = 'NA'
GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
"""

DROPPED_FILTER_SQL = """
SELECT
    customer_id,
    DATE_TRUNC('month', transaction_date) AS reporting_month,
    SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
    SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
FROM transactions
WHERE region = 'NA'
GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
"""


def _contract_sql() -> str:
    guard = SemanticGuardrail.from_contract(CONTRACT_PATH)
    definition, _version = guard.registry.get("net_revenue")
    return definition.sql


def test_identical_sql_has_zero_drift():
    contract_sql = _contract_sql()
    assert semantic_drift_distance(contract_sql, contract_sql, "postgres", "postgres") == 0.0


def test_commutative_and_formatting_rewrite_has_zero_drift():
    contract_sql = _contract_sql()
    assert semantic_drift_distance(REWRITTEN_EQUIVALENT_SQL, contract_sql, "duckdb", "postgres") == 0.0


def test_dropped_filter_produces_positive_drift():
    assert semantic_drift_distance(DROPPED_FILTER_SQL, _contract_sql(), "duckdb", "postgres") > 0.0


def test_aggregation_swap_produces_positive_drift():
    candidate = REWRITTEN_EQUIVALENT_SQL.replace(
        "SUM(CASE WHEN type = 'refund'", "AVG(CASE WHEN type = 'refund'"
    )
    assert semantic_drift_distance(candidate, _contract_sql(), "duckdb", "postgres") > 0.0


def test_unrelated_query_has_high_drift():
    assert semantic_drift_distance("SELECT 1", _contract_sql(), "duckdb", "postgres") > 0.8


def test_alias_and_qualifier_differences_are_cosmetic():
    sig_a = ast_node_signatures("SELECT t.amount AS total FROM transactions AS t", "duckdb")
    sig_b = ast_node_signatures("SELECT amount AS revenue FROM transactions", "duckdb")
    assert sig_a == sig_b


def test_guardrail_reports_jaccard_drift_and_allows_equivalent_rewrite():
    guard = SemanticGuardrail.from_contract(CONTRACT_PATH)

    equivalent = guard.verify(REWRITTEN_EQUIVALENT_SQL)
    assert equivalent.is_valid is True
    assert equivalent.drift_score == 0.0

    drifted = guard.verify("SELECT SUM(amount) FROM transactions WHERE status = 'active'")
    assert drifted.is_valid is False
    assert drifted.drift_score > 0.0


def test_audit_trace_sql_hash_is_stable_sha256():
    registry = ContractRegistry(Path("benchmark_corpus/dev/net_revenue"))
    evaluator = SemanticEvaluator(registry)
    sql = "SELECT SUM(amount) FROM transactions"

    evaluator.evaluate(EvaluateRequest(
        request_id="req-drift-test",
        metric_id="net_revenue",
        sql=sql,
        dialect="duckdb",
        agent_id="test-agent",
    ))

    last_trace = evaluator.audit_log[-1]
    assert last_trace["sql_hash"] == hashlib.sha256(sql.encode("utf-8")).hexdigest()
