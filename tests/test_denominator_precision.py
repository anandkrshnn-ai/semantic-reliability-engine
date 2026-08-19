import pytest
from semantic_reliability.harness.duckdb_runner import DuckDBFixtureRunner, AssertionBenchmarkReport, MutationClassification


def test_denominator_accounting_identity():
    # Enforce: G = E + U + V and V = D + S
    rep = AssertionBenchmarkReport(
        suite_name="test_suite",
        total_mutations_generated=10,
        executable_mutations_count=8,
        equivalent_mutations_count=2,
        valid_defects_count=6,
        detected_by_assertions_count=4,
        surviving_defects_count=2,
        effective_catch_score_pct=66.7,
        evaluations=[]
    )

    G = rep.total_mutations_generated
    E = rep.equivalent_mutations_count
    U = rep.unexecutable_mutations_count
    V = rep.valid_defects_count
    D = rep.detected_by_assertions_count
    S = rep.surviving_defects_count

    assert G == E + U + V
    assert V == D + S
    assert rep.effective_catch_score_pct == round((D / V) * 100.0, 1)


def test_zero_valid_defects_does_not_claim_100_pct():
    rep = AssertionBenchmarkReport(
        suite_name="test_suite",
        total_mutations_generated=2,
        executable_mutations_count=2,
        equivalent_mutations_count=2,
        valid_defects_count=0,
        detected_by_assertions_count=0,
        surviving_defects_count=0,
        effective_catch_score_pct=0.0,
        evaluations=[]
    )
    assert rep.valid_defects_count == 0
    # Zero valid defects should never be reported as 100%
    assert rep.effective_catch_score_pct == 0.0
