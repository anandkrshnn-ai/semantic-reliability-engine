from typing import Dict, Any
from pydantic import BaseModel


class DPOPreferenceItem(BaseModel):
    """Direct Preference Optimization training pair (HuggingFace / Anthropic standard format)."""
    prompt: str
    chosen: str
    rejected: str
    metric_id: str
    mutation_type: str
    difficulty: str
    violation_reason: str
    policy_version: str = "1.0"

    def to_jsonl_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "chosen": self.chosen,
            "rejected": self.rejected,
            "metadata": {
                "metric_id": self.metric_id,
                "mutation_type": self.mutation_type,
                "difficulty": self.difficulty,
                "violation_reason": self.violation_reason,
                "policy_version": self.policy_version,
            }
        }
