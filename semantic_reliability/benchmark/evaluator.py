"""BenchmarkEvaluator computing scorecard, Semantic Lift, and Net Governance Benefit with dispersion metrics."""
from typing import List, Dict, Any
import numpy as np
from .protocol import AgentTrajectory, NetGovernancePolicy


class BenchmarkEvaluator:
    """Computes scorecard, Semantic Lift, and Net Governance Benefit with multi-rollout dispersion."""

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
            approp_abstain = sum(1 for t in trajs if t.appropriate_abstention)
            ceiling_count = sum(1 for t in trajs if t.ceiling_reached)

            lats = sorted(t.latency_ms for t in trajs)
            p50_lat = np.percentile(lats, 50) if n > 0 else 0.0
            p95_lat = np.percentile(lats, 95) if n > 0 else 0.0

            exec_rate = round(exec_count / n, 4)
            comp_rate = round(comp_count / n, 4)
            corr_rate = round(corr_count / n, 4)
            unsafe_rate = round(unsafe_count / n, 4)
            abstain_rate = round(abstain_count / n, 4)
            approp_rate = round(approp_abstain / n, 4)

            return {
                "total_evaluations": n,
                "execution_success": exec_rate,
                "execution_success_rate": exec_rate,
                "contract_compliance": comp_rate,
                "contract_compliance_rate": comp_rate,
                "result_correctness": corr_rate,
                "result_correctness_rate": corr_rate,
                "unsafe_query_rate": unsafe_rate,
                "abstention_rate": abstain_rate,
                "appropriate_abstention_rate": approp_rate,
                "ceiling_reached_rate": round(ceiling_count / n, 4),
                "mean_tool_calls": round(sum(len(t.tool_calls) for t in trajs) / n, 2),
                "p50_latency_ms": round(float(p50_lat), 2),
                "p95_latency_ms": round(float(p95_lat), 2),
                "mean_estimated_cost_usd": round(sum(t.estimated_cost_usd or 0.0 for t in trajs) / n, 4),
            }

        blind_stats = _stats(blind_trajs)
        gov_stats = _stats(gov_trajs)

        # Delta metrics
        delta_correctness = gov_stats.get("result_correctness_rate", 0.0) - blind_stats.get("result_correctness_rate", 0.0)
        delta_latency_sec = (gov_stats.get("p95_latency_ms", 0.0) - blind_stats.get("p95_latency_ms", 0.0)) / 1000.0
        delta_cost = gov_stats.get("mean_estimated_cost_usd", 0.0) - blind_stats.get("mean_estimated_cost_usd", 0.0)
        delta_inapprop_abstain = (gov_stats.get("abstention_rate", 0.0) - gov_stats.get("appropriate_abstention_rate", 0.0))

        semantic_lift = gov_stats.get("contract_compliance_rate", 0.0) - blind_stats.get("contract_compliance_rate", 0.0)

        net_benefit = (
            delta_correctness
            - (self.policy.lambda_latency * delta_latency_sec)
            - (self.policy.lambda_cost * delta_cost)
            - (self.policy.lambda_abstention_penalty * delta_inapprop_abstain)
        )

        return {
            "blind_baseline": blind_stats,
            "governed_mcp": gov_stats,
            "semantic_lift": round(semantic_lift, 4),
            "net_governance_benefit": round(net_benefit, 4),
            "policy_version": self.policy.version,
        }
