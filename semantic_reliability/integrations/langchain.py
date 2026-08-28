"""LangChain and LangGraph Integration for Semantic Reliability Engine (SRE)."""

from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import logging

from semantic_reliability.guardrail import SemanticGuardrail, GuardrailResult, SemanticDriftException

logger = logging.getLogger("sre.integrations.langchain")


class SREGuardrailToolWrapper:
    """
    Wraps a LangChain Database / SQL Tool (e.g. QuerySQLDataBaseTool) with SRE AST verification.

    When an agent calls the SQL tool:
    1. Intercepts the generated SQL query.
    2. Validates semantic invariants against the metric contract.
    3. If compliant: proceeds to execute the base tool.
    4. If invariant drift is detected:
       - If `raise_on_drift=False` (default): Returns a formatted diagnostic error to the agent,
         prompting the LLM to inspect its scratchpad and regenerate compliant SQL without throwing an exception.
       - If `raise_on_drift=True`: Immediately raises `SemanticDriftException`.
    """

    def __init__(
        self,
        base_tool: Any,
        contract_path: Union[str, Path],
        metric_id: Optional[str] = None,
        dialect: str = "duckdb",
        raise_on_drift: bool = False,
    ):
        self.base_tool = base_tool
        self.guardrail = SemanticGuardrail.from_contract(contract_path)
        self.metric_id = metric_id
        self.dialect = dialect
        self.raise_on_drift = raise_on_drift

        # Forward tool metadata if available
        self.name = getattr(base_tool, "name", "sre_guarded_sql_tool")
        self.description = getattr(
            base_tool,
            "description",
            "Execute SQL queries with deterministic business semantic guardrails.",
        )

    def _extract_sql(self, query_input: Union[str, Dict[str, Any]]) -> str:
        if isinstance(query_input, str):
            return query_input.strip()
        if isinstance(query_input, dict):
            return (
                query_input.get("query")
                or query_input.get("sql")
                or query_input.get("input")
                or str(query_input)
            )
        return str(query_input)

    def run(self, tool_input: Union[str, Dict[str, Any]], **kwargs: Any) -> Any:
        """Synchronous execution wrapper."""
        sql = self._extract_sql(tool_input)
        result = self.guardrail.verify(sql, metric_id=self.metric_id, dialect=self.dialect)

        if not result.is_valid:
            error_msg = self._format_agent_feedback(result)
            logger.warning(f"SRE Guardrail Intercepted Query: {error_msg}")
            if self.raise_on_drift:
                raise SemanticDriftException(result)
            return error_msg

        # Forward to underlying tool
        if hasattr(self.base_tool, "run"):
            return self.base_tool.run(tool_input, **kwargs)
        if callable(self.base_tool):
            return self.base_tool(tool_input, **kwargs)
        raise TypeError(f"Underlying base_tool {type(self.base_tool)} is not callable or runnable.")

    async def arun(self, tool_input: Union[str, Dict[str, Any]], **kwargs: Any) -> Any:
        """Asynchronous execution wrapper."""
        sql = self._extract_sql(tool_input)
        result = self.guardrail.verify(sql, metric_id=self.metric_id, dialect=self.dialect)

        if not result.is_valid:
            error_msg = self._format_agent_feedback(result)
            logger.warning(f"SRE Guardrail Intercepted Query (Async): {error_msg}")
            if self.raise_on_drift:
                raise SemanticDriftException(result)
            return error_msg

        if hasattr(self.base_tool, "arun"):
            return await self.base_tool.arun(tool_input, **kwargs)
        if hasattr(self.base_tool, "run"):
            return self.base_tool.run(tool_input, **kwargs)
        if callable(self.base_tool):
            return self.base_tool(tool_input, **kwargs)
        raise TypeError(f"Underlying base_tool {type(self.base_tool)} is not callable or runnable.")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        tool_input = args[0] if args else kwargs.get("tool_input", "")
        return self.run(tool_input, **kwargs)

    def _format_agent_feedback(self, result: GuardrailResult) -> str:
        violations = "\n  - ".join(result.violations) if result.violations else "Semantic contract violated."
        feedback = (
            f"ERROR [SEMANTIC_GUARDRAIL_BLOCKED]: The generated SQL violates business metric contract '{result.metric_id}'.\n"
            f"Drift Score: {result.drift_score:.2f}\n"
            f"Violations Detected:\n  - {violations}\n"
            f"Please revise your SQL query to satisfy these required filters/invariants before executing."
        )
        return feedback


class SREGuardrailCallback:
    """
    LangChain BaseCallbackHandler compatible callback hook for observing semantic drift.
    """

    def __init__(
        self,
        contract_path: Union[str, Path],
        metric_id: Optional[str] = None,
        dialect: str = "duckdb",
        block_on_drift: bool = True,
    ):
        self.guardrail = SemanticGuardrail.from_contract(contract_path)
        self.metric_id = metric_id
        self.dialect = dialect
        self.block_on_drift = block_on_drift
        self.traces: List[Dict[str, Any]] = []

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Intercepts tool start event if it looks like an SQL query."""
        if any(keyword in input_str.upper() for keyword in ["SELECT", "FROM", "WHERE", "JOIN"]):
            result = self.guardrail.verify(input_str, metric_id=self.metric_id, dialect=self.dialect)
            self.traces.append({
                "sql": input_str,
                "is_valid": result.is_valid,
                "drift_score": result.drift_score,
                "violations": result.violations,
            })
            if not result.is_valid and self.block_on_drift:
                raise SemanticDriftException(result)
