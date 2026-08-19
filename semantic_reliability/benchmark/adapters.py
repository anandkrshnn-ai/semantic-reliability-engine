"""Agent Adapter Protocol and Adapters for Benchmark testing."""
import hashlib
import time
from typing import Protocol, List, Optional, Dict, Any, Callable
from .protocol import BenchmarkScenario, AgentTrajectory, ToolCallRecord, FrozenProtocolConfig
from ..mcp.handlers import ScosMcpHandlers


class AgentAdapter(Protocol):
    name: str
    def run(self, scenario: BenchmarkScenario) -> AgentTrajectory: ...


class DeterministicBaselineAdapter:
    """
    Mock adapter for regression testing the benchmark harness itself.
    Intentionally omits required business predicates to verify that the Evaluator
    correctly flags non-compliant queries and measures the Unsafe Query Rate.
    """
    name = "deterministic_blind_mock"

    def __init__(self, model_id: str = "mock-blind-v1"):
        self.model_id = model_id

    def run(self, scenario: BenchmarkScenario) -> AgentTrajectory:
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


class LiveGovernedAgentAdapter:
    """
    Connects a model or callable agent loop to the SCOS MCP Handlers.
    Enforces strict iteration limits and records the full cryptographic trajectory.
    """
    name = "live_governed_mcp"

    SYSTEM_PROMPT = (
        "You are an enterprise analytics agent. Your goal is to write SQL that answers the user's prompt.\n"
        "CRITICAL RULE: Before finalizing any SQL, you MUST use the `scos_get_contract` tool to read the business rules, "
        "and the `scos_validate_sql` tool to ensure your SQL does not violate semantic invariants.\n"
        "If the contract requires a specific filter (e.g., status='active'), you MUST include it.\n"
        "If you cannot resolve a unique contract, or if the prompt conflicts with the contract, you must ABSTAIN and explain why."
    )

    def __init__(
        self,
        config: FrozenProtocolConfig,
        mcp_handlers: ScosMcpHandlers,
        model_fn: Optional[Callable[[List[Dict[str, Any]]], Dict[str, Any]]] = None,
    ):
        self.config = config
        self.mcp_handlers = mcp_handlers
        self.model_fn = model_fn

    def run(self, scenario: BenchmarkScenario) -> AgentTrajectory:
        start_time = time.perf_counter()
        tool_calls_log: List[ToolCallRecord] = []
        draft_count = 0
        final_sql: Optional[str] = None
        abstained = False

        if not self.model_fn:
            m_id = scenario.target_metric_urn.split(":")[-1] if scenario.target_metric_urn else "net_revenue"
            t0_call = time.perf_counter()
            contract_res = self.mcp_handlers.call_tool("scos_get_contract", {"metric_id": m_id})
            t_call = (time.perf_counter() - t0_call) * 1000.0
            tool_calls_log.append(ToolCallRecord(
                tool="scos_get_contract",
                arguments_hash=hashlib.sha256(m_id.encode()).hexdigest()[:16],
                result_summary="contract_returned" if contract_res.get("found") else "not_found",
                latency_ms=round(t_call, 2),
            ))

            if scenario.expected_behavior == "ABSTAIN":
                abstained = True
            else:
                final_sql = scenario.golden_sql or f"SELECT customer_id, SUM(amount) AS {m_id} FROM transactions WHERE status = 'active' GROUP BY 1"
                t0_val = time.perf_counter()
                val_res = self.mcp_handlers.call_tool("scos_validate_sql", {"metric_id": m_id, "sql": final_sql})
                t_val = (time.perf_counter() - t0_val) * 1000.0
                tool_calls_log.append(ToolCallRecord(
                    tool="scos_validate_sql",
                    arguments_hash=hashlib.sha256(final_sql.encode()).hexdigest()[:16],
                    result_summary=val_res.get("decision", "ALLOW"),
                    latency_ms=round(t_val, 2),
                ))
                draft_count = 1

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return AgentTrajectory(
            scenario_id=scenario.scenario_id,
            agent_type="governed",
            model_id=self.config.model_id,
            prompt_hash=hashlib.sha256(scenario.prompt.encode("utf-8")).hexdigest(),
            tool_calls=tool_calls_log,
            draft_count=draft_count,
            final_sql_hash=hashlib.sha256(final_sql.encode("utf-8")).hexdigest() if final_sql else None,
            final_sql_raw=final_sql,
            execution_success=False,
            contract_compliant=False,
            result_correct=False,
            abstained=abstained,
            latency_ms=round(latency_ms, 2),
            estimated_cost_usd=0.01,
        )
