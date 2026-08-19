import pytest
from semantic_reliability.harness.validity import BenchmarkValidityEvaluator, BenchmarkConfidence, BenchmarkValidity


def test_validity_policy_loading():
    policy = BenchmarkValidityEvaluator.load_policy()
    assert policy.get("policy_version") == "1.0"
    assert "thresholds" in policy
    assert "conclusive" in policy["thresholds"]
    assert policy["thresholds"]["conclusive"]["min_fixture_adequacy"] == 80.0


def test_validity_evaluation_with_absolute_counts():
    val = BenchmarkValidityEvaluator.evaluate(
        model_id="b2b_saas_arr",
        standard_catch_pct=25.0,
        semantic_catch_pct=100.0,
        fixture_adequacy_pct=100.0,
        contract_coverage_pct=80.0,
        total_mutations_generated=4,
        valid_defects_count=4,
        standard_detected_count=1,
        standard_surviving_count=3,
        semantic_detected_count=4,
        semantic_surviving_count=0,
    )

    assert val.confidence == BenchmarkConfidence.HIGH
    assert val.validity == BenchmarkValidity.CONCLUSIVE
    assert val.incremental_gain_pct == 75.0
    assert val.standard_surviving_count == 3
    assert val.semantic_surviving_count == 0
