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
            amount DOUBLE,
            status VARCHAR,
            trans_date DATE
        );
        INSERT INTO transactions VALUES
            ('C1', 100.0, 'active', '2026-01-01'),
            ('C1', 50.0, 'cancelled', '2026-01-02'),
            ('C2', 200.0, 'active', '2026-01-03');

        CREATE TABLE subscriptions (
            customer_id VARCHAR,
            base_fee DOUBLE,
            discount DOUBLE,
            status VARCHAR,
            renewal_date DATE
        );
        INSERT INTO subscriptions VALUES
            ('C1', 100.0, 10.0, 'active', '2026-01-01'),
            ('C2', 50.0, 0.0, 'cancelled', '2026-01-02');
    """)
    return conn


@pytest.fixture
def contract_registry():
    registry = ContractRegistry()
    registry.register(MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1",
        dialect="duckdb",
        metadata={"domain": "finance"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"])
        )
    ))
    registry.register(MetricDefinition(
        metric="mrr",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, SUM(base_fee - discount) AS mrr FROM subscriptions WHERE status = 'active' GROUP BY 1",
        dialect="duckdb",
        metadata={"domain": "finance"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"])
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

    # Governed adapter succeeds on contracts
    assert scorecard["governed_mcp"]["contract_compliance"] == 1.0
    assert scorecard["governed_mcp"]["result_correctness"] == 1.0

    # Semantic lift should be +1.0
    assert scorecard["semantic_lift"] == 1.0
    assert scorecard["net_governance_benefit"] > 0.9


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
    export_trajectories(trajectories, out_jsonl)
    assert out_jsonl.exists()

    # 2. Load from JSONL
    loaded = load_trajectories(out_jsonl)
    assert len(loaded) == len(SCENARIOS)
    assert loaded[0].final_sql_raw is None  # Confirmed redacted

    # 3. Replay with in-memory trajectories containing final_sql_raw
    engine = TrajectoryReplayEngine(registry=contract_registry, conn=benchmark_db)
    replay_res = engine.replay_trajectories(trajectories, SCENARIOS)
    assert replay_res["total_replayed"] == len(SCENARIOS)
    assert "scorecard" in replay_res
    assert replay_res["scorecard"]["governed_mcp"]["contract_compliance"] == 1.0

