import pytest
from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant, GrainInvariant, AggregationInvariant
from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.assertions.structural import NonNullOutputAssertion
from semantic_reliability.evaluation.agent_eval import AgentSQLEvaluator, SemanticRiskLevel


@pytest.fixture
def sample_metric_def():
    return MetricDefinition(
        metric="b2b_arr",
        owner="finance",
        grain="customer",
        sql="SELECT customer_id, SUM(mrr * 12) AS arr FROM saas_contracts WHERE status = 'active' GROUP BY customer_id",
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"]),
            grain=GrainInvariant(required_dimensions=["customer_id"]),
            aggregation=AggregationInvariant(required_function="SUM"),
        )
    )


def test_agent_eval_catches_missing_business_predicate(sample_metric_def):
    # Agent generated SQL that runs fine but dropped status = 'active'
    agent_sql = "SELECT customer_id, SUM(mrr * 12) AS arr FROM saas_contracts GROUP BY customer_id"

    report = AgentSQLEvaluator.evaluate(
        candidate_sql=agent_sql,
        metric_def=sample_metric_def,
    )

    assert report.execution_success is False or report.contract_compliant is False
    assert report.contract_compliant is False
    assert any("population" in v.lower() or "status" in v.lower() for v in report.violations)
    assert report.semantic_risk in (SemanticRiskLevel.HIGH, SemanticRiskLevel.CRITICAL)


def test_agent_eval_execution_success_is_not_semantic_correctness(sample_metric_def):
    # Agent query succeeds syntactically on duckdb, but has wrong grain
    agent_sql = "SELECT SUM(mrr * 12) AS arr FROM saas_contracts WHERE status = 'active'"

    report = AgentSQLEvaluator.evaluate(
        candidate_sql=agent_sql,
        metric_def=sample_metric_def,
    )

    assert report.contract_compliant is False
    assert any("grain" in v.lower() for v in report.violations)
    assert report.verdict != "ACCEPTED_SEMANTICALLY_COMPLIANT"


def test_agent_eval_accepts_compliant_sql(sample_metric_def):
    compliant_sql = "SELECT customer_id, SUM(mrr * 12.0) AS arr FROM saas_contracts WHERE status = 'active' GROUP BY customer_id"

    report = AgentSQLEvaluator.evaluate(
        candidate_sql=compliant_sql,
        metric_def=sample_metric_def,
    )

    assert report.contract_compliant is True
    assert len(report.violations) == 0
    assert report.semantic_risk == SemanticRiskLevel.LOW
    assert report.verdict == "ACCEPTED_SEMANTICALLY_COMPLIANT"
