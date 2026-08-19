import pytest
from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant, GrainInvariant, AggregationInvariant, UnitInvariant, TimeInvariant
from semantic_reliability.compiler.coverage import SemanticCoverageCalculator


def test_contract_coverage_full_revenue():
    m = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT 1",
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"]),
            grain=GrainInvariant(required_dimensions=["customer_id"]),
            aggregation=AggregationInvariant(required_function="SUM", positive_components=["type = 'invoice'"], negative_components=["type = 'refund'"]),
            units=UnitInvariant(currency="USD"),
            time=TimeInvariant(timezone="UTC"),
        )
    )

    report = SemanticCoverageCalculator.evaluate_contract(m)
    assert report.coverage_score_pct == 100.0
    assert report.is_comprehensive is True
    assert len(report.missing_dimensions) == 0


def test_contract_coverage_partial():
    m = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT 1",
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"]),
        )
    )

    report = SemanticCoverageCalculator.evaluate_contract(m)
    assert report.coverage_score_pct < 100.0
    assert "currency" in report.missing_dimensions
    assert "grain" in report.missing_dimensions
    assert "aggregation" in report.missing_dimensions
