"""Unit tests for Hybrid static-first validation and adaptive escalation."""

import pytest
import duckdb
import pandas as pd
from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant, GrainInvariant
from semantic_reliability.firewall.hybrid_router import HybridValidator
from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.assertions.structural import NonNullOutputAssertion



@pytest.fixture
def sample_metric():
    return MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, reporting_month, sum(amount) as net_revenue FROM payments WHERE is_refund = false GROUP BY 1, 2",
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["is_refund = false"]),
            grain=GrainInvariant(required_dimensions=["customer_id", "reporting_month"]),
        ),
    )


@pytest.fixture
def duckdb_con():
    con = duckdb.connect(":memory:")
    df = pd.DataFrame({
        "customer_id": [1, 2],
        "reporting_month": ["2026-01-01", "2026-01-01"],
        "amount": [100.0, 200.0],
        "net_revenue": [100.0, 200.0],
        "is_refund": [False, False],
    })
    con.register("payments", df)
    return con


def test_hybrid_validator_fast_path_rejection(sample_metric):
    # Missing required filter is_refund = false -> Fast-path rejection (< 1ms, 0 queries)
    bad_sql = "SELECT customer_id, reporting_month, sum(amount) as net_revenue FROM payments GROUP BY customer_id, reporting_month"
    res = HybridValidator.validate_hybrid(candidate_sql=bad_sql, metric_def=sample_metric)

    assert res.passed is False
    assert res.routing_tier == "tier_3_static"
    assert res.routing_decision == "tier_3_static_rejected"
    assert res.escalated is False
    assert res.bytes_scanned == 0


def test_hybrid_validator_fast_path_approval(sample_metric):
    # Compliant, simple query -> Tier 3 static approved immediately
    good_sql = "SELECT customer_id, reporting_month, sum(amount) as net_revenue FROM payments WHERE is_refund = false GROUP BY customer_id, reporting_month"
    res = HybridValidator.validate_hybrid(candidate_sql=good_sql, metric_def=sample_metric)

    assert res.passed is True
    assert res.routing_tier == "tier_3_static"
    assert res.routing_decision == "tier_3_static_approved"
    assert res.escalated is False


def test_hybrid_validator_adaptive_escalation(sample_metric, duckdb_con):
    # Query with multiple CTEs / complex graph triggers escalation to Tier 4
    complex_sql = """
    WITH raw_payments AS (
        SELECT * FROM payments WHERE is_refund = false
    ),
    filtered_payments AS (
        SELECT * FROM raw_payments
    )
    SELECT customer_id, reporting_month, sum(amount) as net_revenue
    FROM filtered_payments
    GROUP BY customer_id, reporting_month
    """
    suite = AssertionSuite(name="net_revenue_suite", assertions=[
        NonNullOutputAssertion(columns=["net_revenue"]),
    ])

    res = HybridValidator.validate_hybrid(
        candidate_sql=complex_sql,
        metric_def=sample_metric,
        duckdb_conn=duckdb_con,
        runtime_suite=suite,
    )

    assert res.passed is True
    assert res.routing_tier == "tier_4_escalated"
    assert res.routing_decision == "tier_4_escalated_approved"
    assert res.escalated is True
    assert "CTEs detected" in res.escalation_reason

