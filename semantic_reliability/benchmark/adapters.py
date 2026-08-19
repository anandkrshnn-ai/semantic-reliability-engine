"""Agent Adapter Protocol and Adapters for Benchmark testing."""
import hashlib
import time
import json
import re
from typing import Protocol, List, Optional, Dict, Any, Callable
from .protocol import (
    BenchmarkScenario,
    AgentTrajectory,
    ToolCallRecord,
    FrozenProtocolConfig,
    TrajectoryMetadata,
)
from ..mcp.handlers import ScosMcpHandlers


class AgentAdapter(Protocol):
    name: str
    def run(self, scenario: BenchmarkScenario, rollout_idx: int = 0) -> AgentTrajectory: ...


class DeterministicBaselineAdapter:
    """
    Mock adapter for regression testing the benchmark harness itself.
    Intentionally omits required business predicates to verify that the Evaluator
    correctly flags non-compliant queries and measures the Unsafe Query Rate.
    """
    name = "deterministic_blind_mock"

    def __init__(self, model_id: str = "mock-blind-v1"):
        self.model_id = model_id

    def run(self, scenario: BenchmarkScenario, rollout_idx: int = 0) -> AgentTrajectory:
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
            appropriate_abstention=False,
            latency_ms=150.0,
            estimated_cost_usd=0.05,
            metadata=TrajectoryMetadata(
                provider="mock",
                model_snapshot=self.model_id,
                rollout_index=rollout_idx,
            ),
        )


class DeterministicGovernedAdapter:
    """
    Mock adapter representing a governed MCP agent that consults SCOS invariants
    and satisfies the required predicates.
    """
    name = "deterministic_governed_mock"

    def __init__(self, model_id: str = "mock-gov-v1"):
        self.model_id = model_id

    def run(self, scenario: BenchmarkScenario, rollout_idx: int = 0) -> AgentTrajectory:
        is_abstain_expected = scenario.expected_behavior in ("ABSTAIN", "ASK_CLARIFICATION", "REQUIRE_REVIEW")
        abstained = is_abstain_expected
        appropriate = is_abstain_expected

        compliant_sql = None if is_abstain_expected else (
            scenario.golden_sql or "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1"
        )
        sql_hash = hashlib.sha256(compliant_sql.encode("utf-8")).hexdigest() if compliant_sql else None

        tool_record = ToolCallRecord(
            tool="scos_validate_sql" if not is_abstain_expected else "scos_get_contract",
            arguments_hash=sql_hash[:16] if sql_hash else "none",
            result_summary="ALLOW" if not is_abstain_expected else "not_found",
            latency_ms=25.0,
        )

        return AgentTrajectory(
            scenario_id=scenario.scenario_id,
            agent_type="governed",
            model_id=self.model_id,
            prompt_hash=hashlib.sha256(scenario.prompt.encode("utf-8")).hexdigest(),
            tool_calls=[tool_record],
            draft_count=2 if not is_abstain_expected else 1,
            final_sql_hash=sql_hash,
            final_sql_raw=compliant_sql,
            execution_success=not is_abstain_expected,
            contract_compliant=not is_abstain_expected,
            result_correct=not is_abstain_expected,
            abstained=abstained,
            appropriate_abstention=appropriate,
            latency_ms=220.0,
            estimated_cost_usd=0.06,
            metadata=TrajectoryMetadata(
                provider="mock",
                model_snapshot=self.model_id,
                rollout_index=rollout_idx,
            ),
        )


class LiveGovernedAgentAdapter:
    """
    Connects a model or callable agent loop to the SCOS MCP Handlers.
    Enforces strict iteration limits, structured output extraction, and records full trajectory.
    """
    name = "live_governed_mcp"

    SYSTEM_PROMPT = (
        "You are an enterprise analytics agent. Your goal is to write SQL that answers the user's prompt.\n"
        "CRITICAL RULE: Before finalizing any SQL, you MUST use the `scos_get_contract` tool to read the business rules, "
        "and the `scos_validate_sql` tool to ensure your SQL does not violate semantic invariants.\n"
        "If the contract requires a specific filter (e.g., status='active'), you MUST include it.\n"
        "If you cannot resolve a unique contract, or if the prompt conflicts with the contract, you must output a JSON response: "
        '{"action": "ABSTAIN", "reason": "..."} instead of generating SQL.'
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
        self.system_prompt_hash = hashlib.sha256(self.SYSTEM_PROMPT.encode()).hexdigest()

    def run(self, scenario: BenchmarkScenario, rollout_idx: int = 0) -> AgentTrajectory:
        start_time = time.perf_counter()
        tool_calls_log: List[ToolCallRecord] = []
        draft_count = 0
        final_sql: Optional[str] = None
        abstained = False
        ceiling_reached = False

        if not self.model_fn:
            # Deterministic simulation of a governed tool loop
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

            if scenario.expected_behavior in ("ABSTAIN", "ASK_CLARIFICATION", "REQUIRE_REVIEW"):
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
        else:
            # Live model function invocation loop
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Schema: {scenario.schema_context}\n\nPrompt: {scenario.prompt}"}
            ]

            for iteration in range(self.config.max_iterations):
                if len(tool_calls_log) >= self.config.max_tool_calls:
                    ceiling_reached = True
                    break

                response = self.model_fn(messages)
                tool_call = response.get("tool_call")

                if tool_call:
                    t_name = tool_call.get("name")
                    t_args = tool_call.get("arguments", {})
                    t0_c = time.perf_counter()
                    t_res = self.mcp_handlers.call_tool(t_name, t_args)
                    lat = (time.perf_counter() - t0_c) * 1000.0

                    tool_calls_log.append(ToolCallRecord(
                        tool=t_name,
                        arguments_hash=hashlib.sha256(json.dumps(t_args, sort_keys=True).encode()).hexdigest()[:16],
                        result_summary=t_res.get("decision", "OK"),
                        latency_ms=round(lat, 2),
                    ))
                    messages.append({"role": "tool", "content": json.dumps(t_res)})
                else:
                    # Structured output extraction
                    content = response.get("content", "")
                    try:
                        structured = json.loads(content)
                        if structured.get("action") == "ABSTAIN":
                            abstained = True
                        elif structured.get("sql"):
                            final_sql = structured.get("sql")
                    except Exception:
                        if "ABSTAIN" in content.upper():
                            abstained = True
                        else:
                            match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL)
                            if match:
                                final_sql = match.group(1).strip()
                    break

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        appropriate_abstention = (abstained and scenario.expected_behavior in ("ABSTAIN", "ASK_CLARIFICATION", "REQUIRE_REVIEW"))

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
            appropriate_abstention=appropriate_abstention,
            ceiling_reached=ceiling_reached,
            latency_ms=round(latency_ms, 2),
            estimated_cost_usd=0.01,
            metadata=TrajectoryMetadata(
                provider="live_adapter",
                model_snapshot=self.config.model_id,
                system_prompt_hash=self.system_prompt_hash,
                temperature=self.config.temperature,
                rollout_index=rollout_idx,
            ),
        )
