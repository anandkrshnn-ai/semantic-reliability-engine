from typing import Dict, Any
from semantic_reliability.gym.models import GymEvidenceItem


def format_to_rlhf(item: GymEvidenceItem) -> Dict[str, Any]:
    """Formats GymEvidenceItem into RLHF reward modeling pair."""
    return {
        "prompt": item.prompt,
        "completions": [
            {
                "response": item.chosen_sql,
                "reward": 1.0,
                "compliant": True,
                "evidence": item.chosen_evidence.model_dump(),
            },
            {
                "response": item.rejected_sql,
                "reward": 0.0,
                "compliant": False,
                "evidence": item.rejected_evidence.model_dump(),
            }
        ],
        "metadata": {
            "example_id": item.example_id,
            "metric_id": item.contract_id,
            "difficulty": item.difficulty,
            "evidence_hash": item.evidence_hash,
        }
    }
