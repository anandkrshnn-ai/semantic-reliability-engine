"""Trajectory Replay and Regression Testing Engine for Phase 12.2."""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import duckdb

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.firewall.engine import ContractRegistry
from .protocol import AgentTrajectory, BenchmarkScenario, NetGovernancePolicy
from .oracle import OracleValidator
from .evaluator import BenchmarkEvaluator

logger = logging.getLogger("sre.benchmark.replay")


def export_trajectories(trajectories: List[AgentTrajectory], path: str | Path) -> None:
    """Exports agent trajectories to JSONL with privacy redaction applied."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for t in trajectories:
            f.write(json.dumps(t.redact_for_export()) + "\n")


def load_trajectories(path: str | Path) -> List[AgentTrajectory]:
    """Loads agent trajectories from JSONL file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Trajectory file not found: {path}")

    trajectories = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                trajectories.append(AgentTrajectory(**data))
    return trajectories


class TrajectoryReplayEngine:
    """Replays recorded trajectories against updated SCOS contracts to detect regressions."""

    def __init__(self, registry: ContractRegistry, conn: Optional[duckdb.DuckDBPyConnection] = None):
        self.registry = registry
        self.conn = conn or duckdb.connect(":memory:")
        self.oracle = OracleValidator(conn=self.conn, registry=self.registry)

    def replay_trajectories(
        self,
        trajectories: List[AgentTrajectory],
        scenarios: List[BenchmarkScenario],
        policy: Optional[NetGovernancePolicy] = None,
    ) -> Dict[str, Any]:
        """Re-evaluates trajectories against the active contract registry."""
        scen_map = {s.scenario_id: s for s in scenarios}
        gov_policy = policy or NetGovernancePolicy()
        evaluator = BenchmarkEvaluator(gov_policy)

        blind_trajs: List[AgentTrajectory] = []
        gov_trajs: List[AgentTrajectory] = []
        replayed_trajs: List[AgentTrajectory] = []

        for traj in trajectories:
            scenario = scen_map.get(traj.scenario_id)
            if not scenario:
                continue

            # If raw SQL is available (e.g. in-memory test run), re-evaluate against current contracts
            if traj.final_sql_raw:
                eval_res = self.oracle.evaluate_agent_sql(traj.final_sql_raw, scenario)
                replayed_t = traj.model_copy(update={
                    "execution_success": eval_res["execution_success"],
                    "contract_compliant": eval_res["contract_compliant"],
                    "result_correct": eval_res["result_correct"],
                })
            else:
                replayed_t = traj

            replayed_trajs.append(replayed_t)
            if replayed_t.agent_type == "blind":
                blind_trajs.append(replayed_t)
            else:
                gov_trajs.append(replayed_t)

        scorecard = evaluator.compute_scorecard(blind_trajs, gov_trajs) if (blind_trajs or gov_trajs) else {}
        return {
            "total_replayed": len(replayed_trajs),
            "scorecard": scorecard,
            "trajectories": [t.redact_for_export() for t in replayed_trajs],
        }
