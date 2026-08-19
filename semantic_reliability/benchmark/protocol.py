"""Protocol and trajectory data models for Phase 12.1 Agent Evaluation Harness."""
import hashlib
from typing import Literal, Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class ScenarioClass(str, Enum):
    CLEAR_CONTRACT = "CLEAR_CONTRACT"
    AMBIGUOUS_METRIC = "AMBIGUOUS_METRIC"
    MISSING_CONTRACT = "MISSING_CONTRACT"
    CONTRACT_CONFLICT = "CONTRACT_CONFLICT"


class BenchmarkScenario(BaseModel):
    """Immutable scenario definition. Golden SQL is an oracle, not a hint."""
    scenario_id: str
    scenario_class: ScenarioClass
    domain: str
    prompt: str
    schema_context: str
    target_metric_urn: Optional[str] = None
    expected_behavior: Literal["PRODUCE_SQL", "ABSTAIN", "ASK_CLARIFICATION", "REQUIRE_REVIEW"] = "PRODUCE_SQL"
    golden_sql: Optional[str] = None
    fixture_fingerprint: Optional[str] = None


class ToolCallRecord(BaseModel):
    """Privacy-preserving record of a single tool invocation."""
    tool: str
    arguments_hash: str
    result_summary: str
    latency_ms: float = 0.0


class AgentTrajectory(BaseModel):
    """Complete, auditable record of an agent's reasoning and execution path."""
    scenario_id: str
    agent_type: Literal["blind", "governed"]
    model_id: str
    prompt_hash: str
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    draft_count: int = 0
    final_sql_hash: Optional[str] = None
    final_sql_raw: Optional[str] = Field(default=None, exclude=True)
    execution_success: bool = False
    contract_compliant: bool = False
    result_correct: bool = False
    abstained: bool = False
    latency_ms: float = 0.0
    estimated_cost_usd: Optional[float] = None
    audit_chain_verified: bool = True

    def redact_for_export(self) -> Dict[str, Any]:
        """Returns a safe dictionary for JSONL export, stripping raw SQL."""
        data = self.model_dump()
        data.pop("final_sql_raw", None)
        return data


class NetGovernancePolicy(BaseModel):
    """Versioned weights for calculating the Net Governance Benefit."""
    lambda_latency: float = 0.1
    lambda_cost: float = 0.5
    lambda_abstention_penalty: float = 0.2
    version: str = "1.0.0"


class FrozenProtocolConfig(BaseModel):
    """Ensures exact reproducibility of a benchmark run."""
    protocol_version: str = "12.1.0"
    scenario_commit: str = "main"
    contract_commit: str = "main"
    model_id: str = "base-model"
    temperature: float = 0.0
    max_tool_calls: int = 5
    max_iterations: int = 3
    fixture_version: str = "v1.0"
    policy_version: str = "1.0.0"
