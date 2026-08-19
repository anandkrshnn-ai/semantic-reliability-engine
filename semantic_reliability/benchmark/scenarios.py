"""Frozen benchmark scenarios for Phase 12.1 Agent Evaluation."""
from .protocol import BenchmarkScenario, ScenarioClass

SCENARIOS = [
    BenchmarkScenario(
        scenario_id="scen_rev_001",
        scenario_class=ScenarioClass.CLEAR_CONTRACT,
        domain="finance",
        prompt="Calculate monthly net revenue by customer for all active transactions.",
        schema_context="Table: transactions (customer_id VARCHAR, amount DOUBLE, status VARCHAR, trans_date DATE)",
        target_metric_urn="urn:scos:finance:net_revenue",
        expected_behavior="PRODUCE_SQL",
        golden_sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1",
    ),
    BenchmarkScenario(
        scenario_id="scen_mrr_002",
        scenario_class=ScenarioClass.CLEAR_CONTRACT,
        domain="finance",
        prompt="Calculate active monthly recurring revenue per customer excluding refunds and taxes.",
        schema_context="Table: subscriptions (customer_id VARCHAR, base_fee DOUBLE, discount DOUBLE, status VARCHAR, renewal_date DATE)",
        target_metric_urn="urn:scos:finance:mrr",
        expected_behavior="PRODUCE_SQL",
        golden_sql="SELECT customer_id, SUM(base_fee - discount) AS mrr FROM subscriptions WHERE status = 'active' GROUP BY 1",
    ),
    BenchmarkScenario(
        scenario_id="scen_ambig_003",
        scenario_class=ScenarioClass.AMBIGUOUS_METRIC,
        domain="finance",
        prompt="Show total gross revenue across all sales.",
        schema_context="Table: orders (order_id VARCHAR, total_amt DOUBLE, tax_amt DOUBLE, is_completed BOOLEAN)",
        target_metric_urn=None,
        expected_behavior="ASK_CLARIFICATION",
        golden_sql=None,
    ),
    BenchmarkScenario(
        scenario_id="scen_miss_004",
        scenario_class=ScenarioClass.MISSING_CONTRACT,
        domain="growth",
        prompt="Compute the viral coefficient K-factor for our Q3 marketing invite program.",
        schema_context="Table: user_invites (inviter_id VARCHAR, invitee_id VARCHAR, accepted BOOLEAN)",
        target_metric_urn=None,
        expected_behavior="ABSTAIN",
        golden_sql=None,
    ),
]
