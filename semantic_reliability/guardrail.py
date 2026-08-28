from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union, Dict, Any
import uuid
import yaml

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.firewall.engine import ContractRegistry, SemanticEvaluator
from semantic_reliability.firewall.models import EvaluateRequest, EvaluateResponse, Decision, RiskLevel
from semantic_reliability.testing.drift.detector import SemanticDriftDetector


class SemanticDriftException(Exception):
    """Raised when an SQL query violates business semantic contract invariants."""

    def __init__(self, result: "GuardrailResult"):
        self.result = result
        violations_str = "\n  - ".join(result.violations) if result.violations else "Unspecified semantic violation"
        message = (
            f"Semantic Guardrail Blocked Execution (Drift Score: {result.drift_score:.2f}, Decision: {result.decision}):\n"
            f"  - {violations_str}"
        )
        if result.remediation_hint:
            message += f"\nRemediation Suggestion:\n  {result.remediation_hint}"
        super().__init__(message)


@dataclass
class GuardrailResult:
    """Evaluation result from SemanticGuardrail."""
    is_valid: bool
    drift_score: float
    violations: List[str]
    decision: str
    risk: str
    metric_id: str
    sql: str
    remediation_hint: Optional[str] = None
    raw_response: Optional[EvaluateResponse] = None

    def __bool__(self) -> bool:
        return self.is_valid


class SemanticGuardrail:
    """
    High-level, deterministic semantic guardrail for text-to-SQL AI agents.

    Guarantees that generated queries strictly adhere to business logic definitions (SCOS contracts),
    preventing silent metric corruption and un-filtered mutations prior to warehouse execution.
    """

    def __init__(self, contract_source: Union[str, Path, MetricDefinition, Dict[str, Any]]):
        self.registry = ContractRegistry()

        if isinstance(contract_source, MetricDefinition):
            self.registry.register(contract_source)
            self.primary_metric = contract_source.metric
        elif isinstance(contract_source, dict):
            metric_def = MetricDefinition(**contract_source)
            self.registry.register(metric_def)
            self.primary_metric = metric_def.metric
        else:
            path = Path(contract_source)
            if path.is_file():
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                metric_def = MetricDefinition(**data)
                version = data.get("version", "1.0.0")
                self.registry.register(metric_def, version=version)
                self.primary_metric = metric_def.metric
            elif path.is_dir():
                self.registry = ContractRegistry(path)
                if not self.registry.contracts:
                    raise ValueError(f"No valid SCOS contract YAMLs found in directory: {path}")
                self.primary_metric = list(self.registry.contracts.keys())[0]
            else:
                raise FileNotFoundError(f"Contract file or directory not found: {contract_source}")

        self.evaluator = SemanticEvaluator(self.registry)

    @classmethod
    def from_contract(cls, contract_path: Union[str, Path]) -> "SemanticGuardrail":
        """Initialize guardrail from a contract YAML file or directory."""
        return cls(contract_path)

    @classmethod
    def from_definition(cls, definition: MetricDefinition) -> "SemanticGuardrail":
        """Initialize guardrail directly from a MetricDefinition object."""
        return cls(definition)

    def verify(
        self,
        sql: str,
        metric_id: Optional[str] = None,
        dialect: str = "duckdb",
        agent_id: str = "agent-guardrail",
    ) -> GuardrailResult:
        """
        Evaluate a candidate SQL query against the metric contract.

        Returns GuardrailResult with validation status, drift score, and detailed violation breakdown.
        """
        target_metric = metric_id or self.primary_metric
        req = EvaluateRequest(
            request_id=f"req-{uuid.uuid4()}",
            metric_id=target_metric,
            sql=sql,
            dialect=dialect,
            agent_id=agent_id,
        )

        resp = self.evaluator.evaluate(req)

        # Calculate mathematical drift score D_sem in [0, 1]
        violations_formatted = [f"[{v.invariant_type}] {v.found}" for v in resp.violations]
        if not resp.contract_compliant and not violations_formatted:
            violations_formatted = [resp.message or "Query violates semantic contract."]

        if resp.contract_compliant and resp.decision == Decision.ALLOW:
            drift_score = 0.0
        else:
            # Scaled penalty based on severity and number of invariant violations
            num_violations = len(resp.violations)
            drift_score = min(1.0, 0.4 + (0.2 * num_violations)) if num_violations > 0 else 1.0

        return GuardrailResult(
            is_valid=(resp.decision == Decision.ALLOW),
            drift_score=drift_score,
            violations=violations_formatted,
            decision=resp.decision.value,
            risk=resp.risk.value,
            metric_id=target_metric,
            sql=sql,
            remediation_hint=resp.message,
            raw_response=resp,
        )

    def intercept(
        self,
        sql: str,
        metric_id: Optional[str] = None,
        dialect: str = "duckdb",
        agent_id: str = "agent-guardrail",
    ) -> str:
        """
        Intercept candidate SQL. If valid, returns the SQL unaltered.
        If invariant violation is detected, raises SemanticDriftException.
        """
        result = self.verify(sql, metric_id=metric_id, dialect=dialect, agent_id=agent_id)
        if not result.is_valid:
            raise SemanticDriftException(result)
        return sql
