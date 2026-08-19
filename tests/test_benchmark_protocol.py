import json
import duckdb
import pytest

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant
from semantic_reliability.firewall.engine import ContractRegistry
from semantic_reliability.benchmark.protocol import (
    NetGovernancePolicy,
    BenchmarkScenario,
    ScenarioClass,
    AgentTrajectory,
    ToolCallRecord,
)
from semantic_reliability.benchmark.oracle import OracleValidator
from semantic_reliability.benchmark.evaluator import BenchmarkEvaluator
from semantic_reliability.benchmark.adapters import (
    DeterministicBaselineAdapter,
    DeterministicGovernedAdapter,
)
from semantic_reliability.benchmark.scenarios import SCENARIOS


@pytest.fixture
def benchmark_db():
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE transactions (
            customer_id VARCHAR,
            transaction_date DATE,
            type VARCHAR,
            amount DOUBLE,
            region VARCHAR,
            status VARCHAR
        );
        INSERT INTO transactions VALUES
            ('C1', '2026-01-01', 'invoice', 100.0, 'NA', 'active'),
            ('C1', '2026-01-02', 'refund', 20.0, 'NA', 'active'),
            ('C2', '2026-01-03', 'invoice', 200.0, 'EU', 'active');

        CREATE TABLE orders (
            customer_id VARCHAR,
            order_amount DOUBLE,
            order_status VARCHAR,
            is_test BOOLEAN
        );
        INSERT INTO orders VALUES
            ('C1', 50.0, 'completed', false),
            ('C2', 120.0, 'completed', false);

        CREATE TABLE user_logins (
            user_id VARCHAR,
            login_date DATE,
            status VARCHAR,
            is_bot BOOLEAN
        );
        INSERT INTO user_logins VALUES
            ('U1', '2026-01-01', 'active', false),
            ('U2', '2026-01-02', 'active', false);

        CREATE TABLE subscriptions (
            plan VARCHAR,
            cancelled BOOLEAN,
            is_trial BOOLEAN
        );
        INSERT INTO subscriptions VALUES
            ('pro', false, false),
            ('enterprise', true, false);

        CREATE TABLE cohorts (
            cohort_id VARCHAR,
            retained_users INT,
            total_users INT,
            is_active BOOLEAN
        );
        INSERT INTO cohorts VALUES
            ('2026_Q1', 80, 100, true);

        CREATE TABLE tickets (
            tier VARCHAR,
            met_sla BOOLEAN,
            status VARCHAR
        );
        INSERT INTO tickets VALUES
            ('tier1', true, 'resolved');

        CREATE TABLE inventory (
            warehouse_id VARCHAR,
            cogs DOUBLE,
            avg_inventory DOUBLE,
            is_obsolete BOOLEAN
        );
        INSERT INTO inventory VALUES
            ('W1', 1000.0, 200.0, false);

        CREATE TABLE checkouts (
            step VARCHAR,
            converted BOOLEAN,
            is_bot BOOLEAN
        );
        INSERT INTO checkouts VALUES
            ('cart', true, false);
    """)
    return conn


@pytest.fixture
def contract_registry():
    registry = ContractRegistry()
    registry.register(MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, DATE_TRUNC('month', transaction_date) AS reporting_month, SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) - SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue FROM transactions WHERE region = 'NA' AND status = 'active' GROUP BY customer_id, DATE_TRUNC('month', transaction_date)",
        dialect="duckdb",
        metadata={"domain": "finance"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["region = 'NA'", "status = 'active'"])
        )
    ))
    registry.register(MetricDefinition(
        metric="average_order_value",
        owner="ecommerce",
        grain="customer",
        sql="SELECT customer_id, AVG(order_amount) AS avg_order_value FROM orders WHERE order_status = 'completed' AND is_test = false GROUP BY customer_id",
        dialect="duckdb",
        metadata={"domain": "ecommerce"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["order_status = 'completed'", "is_test = false"])
        )
    ))
    registry.register(MetricDefinition(
        metric="monthly_active_users",
        owner="product",
        grain="monthly",
        sql="SELECT DATE_TRUNC('month', login_date) AS reporting_month, COUNT(DISTINCT user_id) AS active_users FROM user_logins WHERE status = 'active' AND is_bot = false GROUP BY DATE_TRUNC('month', login_date)",
        dialect="duckdb",
        metadata={"domain": "product"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'", "is_bot = false"])
        )
    ))
    registry.register(MetricDefinition(
        metric="customer_churn_rate",
        owner="growth",
        grain="plan",
        sql="SELECT plan, COUNT(CASE WHEN cancelled = true THEN 1 END) * 1.0 / COUNT(*) AS churn_rate FROM subscriptions WHERE is_trial = false GROUP BY plan",
        dialect="duckdb",
        metadata={"domain": "growth"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["is_trial = false"])
        )
    ))
    registry.register(MetricDefinition(
        metric="customer_retention_rate",
        owner="growth",
        grain="cohort_id",
        sql="SELECT cohort_id, SUM(CASE WHEN returned_next_period = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS retention_rate FROM retention_cohorts WHERE status = 'active' GROUP BY cohort_id",
        dialect="duckdb",
        metadata={"domain": "growth"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"])
        )
    ))
    registry.register(MetricDefinition(
        metric="sla_compliance_rate",
        owner="operations",
        grain="tier",
        sql="SELECT priority, SUM(CASE WHEN resolved_within_sla = true THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS sla_rate FROM support_tickets WHERE is_spam = false GROUP BY priority",
        dialect="duckdb",
        metadata={"domain": "operations"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["is_spam = false"])
        )
    ))
    registry.register(MetricDefinition(
        metric="inventory_turnover",
        owner="supply_chain",
        grain="warehouse_id",
        sql="SELECT warehouse_id, SUM(cogs) / SUM(stock_value) AS turnover_ratio FROM inventory_movements WHERE is_obsolete = false GROUP BY warehouse_id",
        dialect="duckdb",
        metadata={"domain": "supply_chain"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["is_obsolete = false"])
        )
    ))
    registry.register(MetricDefinition(
        metric="checkout_conversion_rate",
        owner="ecommerce",
        grain="step",
        sql="SELECT COUNT(CASE WHEN event_name = 'checkout_complete' THEN 1 END) * 1.0 / COUNT(*) AS conversion_rate FROM checkout_events WHERE is_internal_ip = false",
        dialect="duckdb",
        metadata={"domain": "ecommerce"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["is_internal_ip = false"])
        )
    ))
    return registry


def test_oracle_validator_evaluation(benchmark_db, contract_registry):
    oracle = OracleValidator(conn=benchmark_db, registry=contract_registry)

    # 1. Oracle validation on Scenario 1
    scen1 = SCENARIOS[0]
    assert oracle.validate_oracle(scen1) is True

    # 2. Evaluate agent SQL (Compliant & Matching)
    eval_match = oracle.evaluate_agent_sql(scen1.golden_sql, scen1)
    assert eval_match["execution_success"] is True
    assert eval_match["contract_compliant"] is True
    assert eval_match["result_correct"] is True

    # 3. Evaluate flawed agent SQL (Executes but violates contract and mismatches result)
    flawed_sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY 1"
    eval_flawed = oracle.evaluate_agent_sql(flawed_sql, scen1)
    assert eval_flawed["execution_success"] is True
    assert eval_flawed["contract_compliant"] is False
    assert eval_flawed["result_correct"] is False


def test_evaluator_scorecard_and_semantic_lift():
    policy = NetGovernancePolicy(lambda_latency=0.1, lambda_cost=0.5, lambda_abstention_penalty=0.2)
    evaluator = BenchmarkEvaluator(policy)

    blind_adapter = DeterministicBaselineAdapter()
    gov_adapter = DeterministicGovernedAdapter()

    blind_trajs = [blind_adapter.run(s) for s in SCENARIOS]
    gov_trajs = [gov_adapter.run(s) for s in SCENARIOS]

    scorecard = evaluator.compute_scorecard(blind_trajs, gov_trajs)

    # Blind adapter intentionally fails contracts
    assert scorecard["blind_baseline"]["unsafe_query_rate"] == 1.0
    assert scorecard["blind_baseline"]["contract_compliance"] == 0.0

    # Governed adapter succeeds on contracts (8 compliant queries = 0.40, 12 appropriate abstentions = 0.60)
    assert scorecard["governed_mcp"]["contract_compliance"] == 0.40
    assert scorecard["governed_mcp"]["appropriate_abstention_rate"] == 0.60
    assert scorecard["governed_mcp"]["unsafe_query_rate"] == 0.0

    # Semantic lift is +0.40
    assert scorecard["semantic_lift"] == 0.40
    assert scorecard["net_governance_benefit"] > 0.3


def test_trajectory_privacy_redaction():
    traj = AgentTrajectory(
        scenario_id="scen_001",
        agent_type="governed",
        model_id="test-model",
        prompt_hash="a1b2c3d4",
        tool_calls=[ToolCallRecord(tool="scos_validate_sql", arguments_hash="12345", result_summary="ALLOW")],
        final_sql_hash="e5f6g7h8",
        final_sql_raw="SELECT * FROM secret_transactions WHERE ssn = '123-45-6789'",
        execution_success=True,
        contract_compliant=True,
        result_correct=True,
    )

    redacted = traj.redact_for_export()
    # Confirm final_sql_raw was stripped, but final_sql_hash was preserved
    assert "final_sql_raw" not in redacted
    assert redacted["final_sql_hash"] == "e5f6g7h8"
    assert redacted["scenario_id"] == "scen_001"


def test_trajectory_export_and_replay_engine(tmp_path, benchmark_db, contract_registry):
    from semantic_reliability.benchmark.replay import export_trajectories, load_trajectories, TrajectoryReplayEngine

    gov_adapter = DeterministicGovernedAdapter()
    trajectories = [gov_adapter.run(s) for s in SCENARIOS]

    # 1. Export to JSONL
    out_jsonl = tmp_path / "trajectories.jsonl"
    art_dir = tmp_path / "artifacts"
    export_trajectories(trajectories, out_jsonl, raw_artifacts_dir=art_dir)
    assert out_jsonl.exists()

    # 2. Load from JSONL
    loaded = load_trajectories(out_jsonl)
    assert len(loaded) == len(SCENARIOS)
    assert loaded[0].final_sql_raw is None  # Confirmed redacted

    # 3. Replay with artifacts directory
    engine = TrajectoryReplayEngine(registry=contract_registry, conn=benchmark_db, raw_artifacts_dir=art_dir)
    replay_res = engine.replay_trajectories(loaded, SCENARIOS)
    assert replay_res["total_replayed"] == len(SCENARIOS)
    assert replay_res["unreplayable_artifacts_count"] == 0
    assert "scorecard" in replay_res
    assert replay_res["scorecard"]["governed_mcp"]["contract_compliance"] == 0.40
    assert replay_res["scorecard"]["governed_mcp"]["appropriate_abstention_rate"] == 0.60


def test_live_governed_adapter_and_cli(contract_registry):
    from semantic_reliability.benchmark.adapters import LiveGovernedAgentAdapter
    from semantic_reliability.benchmark.protocol import FrozenProtocolConfig
    from semantic_reliability.mcp.handlers import ScosMcpHandlers
    from click.testing import CliRunner
    from semantic_reliability.cli import main

    handlers = ScosMcpHandlers(registry=contract_registry)
    cfg = FrozenProtocolConfig(model_id="test-live-model")
    adapter = LiveGovernedAgentAdapter(config=cfg, mcp_handlers=handlers)

    scen = SCENARIOS[0]
    traj = adapter.run(scen)
    assert traj.agent_type == "governed"
    assert len(traj.tool_calls) >= 1
    assert traj.tool_calls[0].tool == "scos_get_contract"

    # Test CLI execution
    runner = CliRunner()
    res = runner.invoke(main, ["benchmark-live", "--output", "scorecard_test.json"])
    assert res.exit_code == 0
    assert "Benchmark live run complete" in res.output


def test_oracle_dataframe_canonical_comparison_robustness(benchmark_db, contract_registry):
    """Stress-tests canonical dataframe comparator with nulls in sort keys, duplicates, and mixed types."""
    import pandas as pd
    from semantic_reliability.benchmark.oracle import OracleValidator

    oracle = OracleValidator(conn=benchmark_db, registry=contract_registry)

    # 1. Nulls in sort keys and values
    df_a = pd.DataFrame([
        {"id": 1, "status": None, "val": 10.00001},
        {"id": 2, "status": "active", "val": 20.0},
        {"id": None, "status": "pending", "val": 5.0},
    ])
    df_b = pd.DataFrame([
        {"id": None, "status": "pending", "val": 5.00002},
        {"id": 2, "status": "active", "val": 20.0},
        {"id": 1, "status": None, "val": 10.0},
    ])
    assert oracle._compare_dataframes(df_a, df_b) is True

    # 2. Duplicate rows with varied associated attributes
    df_c = pd.DataFrame([
        {"user_id": "U1", "cat": "A", "amt": 100.0},
        {"user_id": "U1", "cat": "B", "amt": 50.0},
        {"user_id": "U1", "cat": "A", "amt": 100.0},
    ])
    df_d = pd.DataFrame([
        {"user_id": "U1", "cat": "A", "amt": 100.0},
        {"user_id": "U1", "cat": "A", "amt": 100.0},
        {"user_id": "U1", "cat": "B", "amt": 50.0},
    ])
    assert oracle._compare_dataframes(df_c, df_d) is True

    # 3. Differing values fail comparison
    df_e = pd.DataFrame([
        {"user_id": "U1", "cat": "A", "amt": 100.0},
        {"user_id": "U1", "cat": "B", "amt": 99.0},
    ])
    assert oracle._compare_dataframes(df_c, df_e) is False



