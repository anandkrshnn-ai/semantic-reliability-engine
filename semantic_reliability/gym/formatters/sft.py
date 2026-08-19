from typing import Dict, Any
from semantic_reliability.gym.models import GymEvidenceItem


def format_to_sft(item: GymEvidenceItem) -> Dict[str, Any]:
    """Formats GymEvidenceItem into SFT instruction-tuning format with reasoning traces."""
    rationale = (
        f"The query must satisfy business contract '{item.contract_id}'. "
        f"A flawed formulation might introduce '{item.mutation_description}' resulting in a {item.rejected_evidence.variance_pct:.1f}% metric variance."
    )
    return {
        "instruction": item.prompt,
        "input": f"Contract ID: {item.contract_id}\nDomain: {item.domain}",
        "output": item.chosen_sql,
        "negative_example": item.rejected_sql,
        "semantic_rationale": rationale,
        "metadata": {
            "example_id": item.example_id,
            "metric_id": item.contract_id,
            "difficulty": item.difficulty,
            "evidence_hash": item.evidence_hash,
        }
    }
