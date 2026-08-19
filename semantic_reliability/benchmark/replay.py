"""Trajectory Replay and Regression Testing Engine for Phase 12.2 & 12.4."""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import duckdb

from semantic_reliability.firewall.engine import ContractRegistry
from .protocol import AgentTrajectory, BenchmarkScenario, NetGovernancePolicy
from .oracle import OracleValidator
from .evaluator import BenchmarkEvaluator

logger = logging.getLogger("sre.benchmark.replay")


def export_trajectories(
    trajectories: List[AgentTrajectory],
    export_path: str | Path,
    raw_artifacts_dir: Optional[str | Path] = None,
) -> None:
    """
    Exports agent trajectories to JSONL with privacy redaction applied.
    Optionally saves raw SQL into a local protected artifacts directory.
    """
    p = Path(export_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if raw_artifacts_dir:
        art_p = Path(raw_artifacts_dir)
        art_p.mkdir(parents=True, exist_ok=True)
        for t in trajectories:
            if t.final_sql_raw and t.final_sql_hash:
                (art_p / f"{t.final_sql_hash}.sql").write_text(t.final_sql_raw, encoding="utf-8")

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

    def __init__(
        self,
        registry: ContractRegistry,
        conn: Optional[duckdb.DuckDBPyConnection] = None,
        raw_artifacts_dir: Optional[str | Path] = None,
    ):
        self.registry = registry
        self.conn = conn or duckdb.connect(":memory:")
        self.oracle = OracleValidator(conn=self.conn, registry=self.registry)
        self.raw_artifacts_dir = Path(raw_artifacts_dir) if raw_artifacts_dir else None

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
        unreplayable_count = 0

        for traj in trajectories:
            scenario = scen_map.get(traj.scenario_id)
            if not scenario:
                continue

            sql_to_eval = traj.final_sql_raw

            # Attempt to resolve raw SQL from local protected artifacts directory
            if not sql_to_eval and traj.final_sql_hash and self.raw_artifacts_dir:
                art_file = self.raw_artifacts_dir / f"{traj.final_sql_hash}.sql"
                if art_file.exists():
                    sql_to_eval = art_file.read_text(encoding="utf-8")

            if sql_to_eval:
                eval_res = self.oracle.evaluate_agent_sql(sql_to_eval, scenario)
                replayed_t = traj.model_copy(update={
                    "execution_success": eval_res["execution_success"],
                    "contract_compliant": eval_res["contract_compliant"],
                    "result_correct": eval_res["result_correct"],
                })
            elif traj.final_sql_hash:
                # Missing SQL artifact makes detailed re-evaluation UNREPLAYABLE
                unreplayable_count += 1
                replayed_t = traj
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
            "unreplayable_artifacts_count": unreplayable_count,
            "scorecard": scorecard,
            "trajectories": [t.redact_for_export() for t in replayed_trajs],
        }
