"""Agent Adapter Protocol and Deterministic Mock Adapters for Benchmark testing."""
import hashlib
from typing import Protocol, List, Optional
from .protocol import BenchmarkScenario, AgentTrajectory, ToolCallRecord


class AgentAdapter(Protocol):
    name: str
    def run(self, scenario: BenchmarkScenario) -> AgentTrajectory: ...


class DeterministicBaselineAdapter:
    """
    WARNING: Mock adapter for regression testing the benchmark harness itself.
    It intentionally omits required business predicates to verify that the Evaluator
    correctly flags non-compliant queries and measures the Unsafe Query Rate.
    """
    name = "deterministic_blind_mock"

    def __init__(self, model_id: str = "mock-blind-v1"):
        self.model_id = model_id

    def run(self, scenario: BenchmarkScenario) -> AgentTrajectory:
        # Generates basic SQL missing business-semantic filters (e.g. status = 'active')
        flawed_sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY 1"
        sql_hash = hashlib.sha256(flawed_sql.encode("utf-8")).hexdigest()

        return AgentTrajectory(
            scenario_id=scenario.scenario_id,
            agent_type="blind",
            model_id=self.model_id,
            prompt_hash=hashlib.sha256(scenario.prompt.encode("utf-8")).hexdigest(),
            tool_calls=[],
            draft_count=1,
            final_sql_hash=sql_hash,
            final_sql_raw=flawed_sql,
            execution_success=True,
            contract_compliant=False,
            result_correct=False,
            abstained=False,
            latency_ms=150.0,
            estimated_cost_usd=0.05,
        )


class DeterministicGovernedAdapter:
    """
    Mock adapter representing a governed MCP agent that consults SCOS invariants
    and satisfies the required predicates.
    """
    name = "deterministic_governed_mock"

    def __init__(self, model_id: str = "mock-gov-v1"):
        self.model_id = model_id

    def run(self, scenario: BenchmarkScenario) -> AgentTrajectory:
        compliant_sql = scenario.golden_sql or "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1"
        sql_hash = hashlib.sha256(compliant_sql.encode("utf-8")).hexdigest()

        tool_record = ToolCallRecord(
            tool="scos_validate_sql",
            arguments_hash=sql_hash[:16],
            result_summary="ALLOW",
            latency_ms=25.0,
        )

        return AgentTrajectory(
            scenario_id=scenario.scenario_id,
            agent_type="governed",
            model_id=self.model_id,
            prompt_hash=hashlib.sha256(scenario.prompt.encode("utf-8")).hexdigest(),
            tool_calls=[tool_record],
            draft_count=2,
            final_sql_hash=sql_hash,
            final_sql_raw=compliant_sql,
            execution_success=True,
            contract_compliant=True,
            result_correct=True,
            abstained=False,
            latency_ms=220.0,
            estimated_cost_usd=0.06,
        )
