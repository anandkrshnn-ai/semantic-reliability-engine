import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple


class RejectionReason(str, Enum):
    EQUIVALENT_ON_FIXTURE = "equivalent_on_fixture"
    UNEXECUTABLE = "unexecutable"
    CHOSEN_CONTRACT_FAILURE = "chosen_contract_failure"
    INSUFFICIENT_FIXTURE_CONTRAST = "insufficient_fixture_contrast"
    INCOMPLETE_CONTRACT = "incomplete_contract"
    REJECTED_NOT_SEMANTICALLY_DIVERGENT = "rejected_not_semantically_divergent"


SPLIT_RULES: Dict[str, List[str]] = {
    "train": ["FILTER_DROP", "AGGREGATION_SWAP", "COALESCE_BYPASS"],
    "validation": ["BOUNDARY_SHIFT", "DISTINCT_DROP"],
    "holdout": ["GRAIN_DROP", "MATH_OPERATOR_INVERT", "JOIN_PREDICATE_DROP"]
}


def assign_split(metric_id: str, family: str) -> str:
    """Deterministic, leakage-resistant split assignment based on metric family."""
    h = hashlib.md5(family.encode()).hexdigest()
    val = int(h[:8], 16) % 100
    if val < 70:
        return "train"
    if val < 85:
        return "validation"
    return "holdout"


def assign_difficulty(mutation_type: str, contract: Any) -> Tuple[str, List[str]]:
    """Deterministic multi-factor difficulty heuristic."""
    reasons: List[str] = []
    m_upper = mutation_type.upper()
    if m_upper in ["FILTER_DROP", "AGGREGATION_SWAP", "COALESCE_BYPASS"]:
        level = "easy"
        reasons.append("direct_ast_mutation")
    elif m_upper in ["BOUNDARY_SHIFT", "DISTINCT_DROP", "GRAIN_DROP"]:
        level = "medium"
        reasons.append("subtle_boundary_or_grain_shift")
    else:
        level = "hard"
        reasons.append("relational_or_deduction_inversion")

    if hasattr(contract, "invariants") and contract.invariants and contract.invariants.population:
        req_filters = getattr(contract.invariants.population, "required_filters", [])
        if len(req_filters) > 2:
            reasons.append("multi_component_metric")

    return level, reasons


def compute_evidence_hash(evidence: Dict[str, Any]) -> str:
    """Generates deterministic full 64-character SHA256 hash from canonical JSON payload."""
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class GymExample:
    example_id: str
    prompt: str
    contract_id: str
    contract_version: str
    chosen_sql: str
    rejected_sql: str
    mutation_type: str
    mutation_description: str
    chosen_evidence: Dict[str, Any]
    rejected_evidence: Dict[str, Any]
    difficulty: str
    difficulty_reasons: List[str]
    fixture_id: str
    policy_version: str
    evidence_hash: str
    split: str
    metric_family: str

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}
