import hashlib
import json
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class ExecutionEvidence(BaseModel):
    execution_success: bool = True
    contract_compliant: bool = True
    assertions_passed: bool = True
    result_changed: bool = False
    variance_pct: float = 0.0
    violations: List[str] = Field(default_factory=list)


class GymEvidenceItem(BaseModel):
    """Rich internal audit-grade record for a contract-grounded preference pair."""
    example_id: str
    prompt: str
    contract_id: str
    contract_version: str = "1.0"
    domain: str = "general"
    split: str = "train"
    chosen_sql: str
    rejected_sql: str
    mutation_type: str
    mutation_description: str
    chosen_evidence: ExecutionEvidence
    rejected_evidence: ExecutionEvidence
    difficulty: Literal["easy", "medium", "hard", "expert"] = "medium"
    fixture_id: str
    policy_version: str = "1.0"
    evidence_hash: str = ""

    def compute_hash(self) -> str:
        payload = {
            "prompt": self.prompt,
            "chosen_sql": self.chosen_sql,
            "rejected_sql": self.rejected_sql,
            "mutation_type": self.mutation_type,
            "contract_id": self.contract_id,
            "variance_pct": self.rejected_evidence.variance_pct,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    def model_post_init(self, __context: Any) -> None:
        if not self.evidence_hash:
            self.evidence_hash = self.compute_hash()


class CandidateRejectionStats(BaseModel):
    """Tracks why candidate pairs were rejected to prevent noisy training data."""
    candidates_generated: int = 0
    accepted_pairs: int = 0
    rejected_equivalent: int = 0
    rejected_invalid_chosen: int = 0
    rejected_insufficient_contrast: int = 0
    rejected_incomplete_contract: int = 0
    rejected_not_divergent: int = 0
