from typing import Dict, Any
from semantic_reliability.gym.models import GymEvidenceItem


def format_to_dpo(item: GymEvidenceItem, include_metadata: bool = True) -> Dict[str, Any]:
    """Formats GymEvidenceItem into standard HuggingFace TRL / Anthropic DPO JSONL format."""
    record = {
        "prompt": item.prompt,
        "chosen": item.chosen_sql,
        "rejected": item.rejected_sql,
    }
    if include_metadata:
        record["metadata"] = {
            "example_id": item.example_id,
            "metric_id": item.contract_id,
            "domain": item.domain,
            "split": item.split,
            "mutation_type": item.mutation_type,
            "difficulty": item.difficulty,
            "variance_pct": item.rejected_evidence.variance_pct,
            "violations": item.rejected_evidence.violations,
            "evidence_hash": item.evidence_hash,
            "policy_version": item.policy_version,
        }
    return record
