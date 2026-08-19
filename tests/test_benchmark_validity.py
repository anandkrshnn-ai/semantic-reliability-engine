import pytest
from semantic_reliability.harness.validity import BenchmarkValidityEvaluator, BenchmarkConfidence, BenchmarkValidity


def test_validity_evaluation_high_confidence():
    val = BenchmarkValidityEvaluator.evaluate(
        model_id="net_revenue",
        standard_catch_pct=20.0,
        semantic_catch_pct=100.0,
        fixture_adequacy_pct=100.0,
        contract_coverage_pct=100.0,
    )
    assert val.confidence == BenchmarkConfidence.HIGH
    assert val.validity == BenchmarkValidity.CONCLUSIVE
    assert val.incremental_gain_pct == 80.0


def test_validity_evaluation_low_confidence_inconclusive():
    val = BenchmarkValidityEvaluator.evaluate(
        model_id="customer_retention",
        standard_catch_pct=0.0,
        semantic_catch_pct=0.0,
        fixture_adequacy_pct=40.0,
        contract_coverage_pct=50.0,
    )
    assert val.confidence == BenchmarkConfidence.LOW
    assert val.validity == BenchmarkValidity.INCONCLUSIVE
    assert "below validity thresholds" in val.validity_notes
    assert val.incremental_gain_pct == 0.0
