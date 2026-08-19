import json
import pytest
from pathlib import Path
from semantic_reliability.replay.worker import ReplayWorker, LocalFixtureSnapshotProvider, ReplayResult
from semantic_reliability.replay.patcher import ContractPatcher
from semantic_reliability.replay.main import run_replay_cycle


@pytest.fixture
def replay_setup(tmp_path):
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    
    # Contract with population filter, but lacking grain dimension assertion
    net_revenue_contract = contracts_dir / "net_revenue.yaml"
    net_revenue_contract.write_text("""
metric: net_revenue
owner: finance
grain: customer_month
dialect: duckdb
sql: "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id"
invariants:
  population:
    required_filters:
      - "status = 'active'"
""", encoding="utf-8")

    return contracts_dir


def test_replay_ignores_denied_traces(replay_setup):
    worker = ReplayWorker(contract_dir=replay_setup)
    denied_trace = {
        "trace_id": "trace-denied-1",
        "metric_id": "net_revenue",
        "decision": "DENY",
        "sql": "SELECT * FROM transactions",
    }
    res = worker.process_trace(denied_trace)
    assert res is None


def test_replay_detects_blind_spots_on_allowed_trace(replay_setup):
    worker = ReplayWorker(contract_dir=replay_setup)
    allowed_trace = {
        "trace_id": "trace-allow-101",
        "metric_id": "net_revenue",
        "decision": "ALLOW",
        "sql": "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id",
    }
    res = worker.process_trace(allowed_trace)
    assert res is not None
    assert res.trace_id == "trace-allow-101"
    assert res.metric_id == "net_revenue"
    assert isinstance(res.catch_score, float)
    assert res.total_valid_defects > 0


def test_contract_patcher_extracts_suggestions():
    blind_spots = [
        {
            "mutation_type": "FILTER_DROP",
            "description": "Drop WHERE clause predicate: status = 'active'",
        },
        {
            "mutation_type": "GRAIN_DROP",
            "description": "Drop GROUP BY dimension: customer_id",
        },
        {
            "mutation_type": "AGGREGATION_SWAP",
            "description": "Swapped SUM(amount) with AVG(amount)",
        }
    ]
    suggestions = ContractPatcher.suggest_invariants(blind_spots)
    assert "status = 'active'" in suggestions["population_required"]
    assert "customer_id" in suggestions["grain_dimensions"]
    assert len(suggestions["aggregation_review_needed"]) > 0

    pr_body = ContractPatcher.generate_pr_body("net_revenue", suggestions, trace_id="trace-xyz")
    assert "Automated Contract Patch for `net_revenue`" in pr_body
    assert "status = 'active'" in pr_body
    assert "customer_id" in pr_body


def test_run_replay_cycle_end_to_end(replay_setup, tmp_path):
    log_file = tmp_path / "audit_test.log"
    log_file.write_text(json.dumps({
        "trace_id": "trace-cycle-1",
        "metric_id": "net_revenue",
        "decision": "ALLOW",
        "sql": "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id",
    }) + "\n", encoding="utf-8")

    results = run_replay_cycle(audit_log_path=log_file, contract_dir=replay_setup)
    assert len(results) == 1
    assert results[0].trace_id == "trace-cycle-1"
