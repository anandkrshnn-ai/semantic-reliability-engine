"""BenchmarkEvaluator computing scorecard, Semantic Lift, and Net Governance Benefit."""
from typing import List, Dict, Any
from .protocol import AgentTrajectory, NetGovernancePolicy


class BenchmarkEvaluator:
    """Computes scorecard, Semantic Lift, and Net Governance Benefit across benchmark runs."""

    def __init__(self, policy: NetGovernancePolicy):
        self.policy = policy

    def compute_scorecard(self, blind_trajs: List[AgentTrajectory], gov_trajs: List[AgentTrajectory]) -> Dict[str, Any]:
        def _stats(trajs: List[AgentTrajectory]) -> Dict[str, Any]:
            n = len(trajs)
            if n == 0:
                return {}
            exec_count = sum(1 for t in trajs if t.execution_success)
            comp_count = sum(1 for t in trajs if t.contract_compliant)
            corr_count = sum(1 for t in trajs if t.result_correct)
            unsafe_count = sum(1 for t in trajs if t.execution_success and not t.contract_compliant)
            abstain_count = sum(1 for t in trajs if t.abstained)

            p95_lat = 0.0
            if n > 0:
                lats = sorted(t.latency_ms for t in trajs)
                idx = min(int(n * 0.95), n - 1)
                p95_lat = lats[idx]

            return {
                "total_scenarios": n,
                "execution_success": round(exec_count / n, 4),
                "contract_compliance": round(comp_count / n, 4),
                "result_correctness": round(corr_count / n, 4),
                "unsafe_query_rate": round(unsafe_count / n, 4),
                "abstention_rate": round(abstain_count / n, 4),
                "mean_tool_calls": round(sum(len(t.tool_calls) for t in trajs) / n, 2),
                "p95_latency_ms": round(p95_lat, 2),
                "mean_estimated_cost": round(sum(t.estimated_cost_usd or 0.0 for t in trajs) / n, 4),
            }

        blind_stats = _stats(blind_trajs)
        gov_stats = _stats(gov_trajs)

        # Delta metrics
        delta_correctness = gov_stats.get("result_correctness", 0.0) - blind_stats.get("result_correctness", 0.0)
        delta_latency_sec = (gov_stats.get("p95_latency_ms", 0.0) - blind_stats.get("p95_latency_ms", 0.0)) / 1000.0
        delta_cost = gov_stats.get("mean_estimated_cost", 0.0) - blind_stats.get("mean_estimated_cost", 0.0)
        delta_abstention = gov_stats.get("abstention_rate", 0.0) - blind_stats.get("abstention_rate", 0.0)

        semantic_lift = gov_stats.get("contract_compliance", 0.0) - blind_stats.get("contract_compliance", 0.0)

        net_benefit = (
            delta_correctness
            - (self.policy.lambda_latency * delta_latency_sec)
            - (self.policy.lambda_cost * delta_cost)
            - (self.policy.lambda_abstention_penalty * delta_abstention)
        )

        return {
            "blind_baseline": blind_stats,
            "governed_mcp": gov_stats,
            "semantic_lift": round(semantic_lift, 4),
            "net_governance_benefit": round(net_benefit, 4),
            "policy_version": self.policy.version,
        }
