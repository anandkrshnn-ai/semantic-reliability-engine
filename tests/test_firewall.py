import pytest
from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant, GrainInvariant, AggregationInvariant
from semantic_reliability.firewall.models import EvaluateRequest, Decision, RiskLevel
from semantic_reliability.firewall.policy import PolicyEngine
from semantic_reliability.firewall.engine import ContractRegistry, SemanticEvaluator


@pytest.fixture
def firewall_setup():
    registry = ContractRegistry()
    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id",
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"]),
            grain=GrainInvariant(required_dimensions=["customer_id"]),
            aggregation=AggregationInvariant(required_function="SUM"),
        )
    )
    registry.register(metric_def, version="1.0.0")
    policy = PolicyEngine(strict_mode=True)
    evaluator = SemanticEvaluator(registry, policy)
    return evaluator


def test_firewall_allows_compliant_sql(firewall_setup):
    req = EvaluateRequest(
        request_id="req-001",
        metric_id="net_revenue",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id",
        agent_id="langchain-analyst-1",
    )
    res = firewall_setup.evaluate(req)
    assert res.decision == Decision.ALLOW
    assert res.execution_allowed is True
    assert res.contract_compliant is True
    assert res.risk == RiskLevel.LOW
    assert len(res.violations) == 0


def test_firewall_denies_missing_population_filter(firewall_setup):
    # Missing status = 'active'
    req = EvaluateRequest(
        request_id="req-002",
        metric_id="net_revenue",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY customer_id",
        agent_id="text2sql-agent-9",
    )
    res = firewall_setup.evaluate(req)
    assert res.decision == Decision.DENY
    assert res.execution_allowed is False
    assert res.contract_compliant is False
    assert res.risk == RiskLevel.CRITICAL
    assert len(res.violations) > 0
    assert any(v.mutation_equivalent == "FILTER_DROP" for v in res.violations)


def test_firewall_non_strict_requires_review(firewall_setup):
    firewall_setup.policy.strict_mode = False
    req = EvaluateRequest(
        request_id="req-003",
        metric_id="net_revenue",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY customer_id",
        agent_id="text2sql-agent-9",
    )
    res = firewall_setup.evaluate(req)
    assert res.decision == Decision.REQUIRE_REVIEW
    assert res.execution_allowed is False
    assert res.risk == RiskLevel.CRITICAL


def test_firewall_denies_unparseable_sql(firewall_setup):
    req = EvaluateRequest(
        request_id="req-004",
        metric_id="net_revenue",
        sql="SELECT FROM WHERE broken SQL ;;;",
        agent_id="unstable-agent",
    )
    res = firewall_setup.evaluate(req)
    assert res.decision == Decision.DENY
    assert res.execution_allowed is False
    assert "Parse Error" in res.message


def test_firewall_records_audit_trail(firewall_setup):
    req = EvaluateRequest(
        request_id="req-005",
        metric_id="net_revenue",
        sql="SELECT customer_id, SUM(amount) FROM transactions WHERE status = 'active' GROUP BY customer_id",
        agent_id="cfo-agent",
    )
    res = firewall_setup.evaluate(req)
    assert len(firewall_setup.audit_log) > 0
    last_trace = firewall_setup.audit_log[-1]
    assert last_trace["trace_id"] == res.trace_id
    assert last_trace["agent_id"] == "cfo-agent"
    assert "sql_hash" in last_trace
