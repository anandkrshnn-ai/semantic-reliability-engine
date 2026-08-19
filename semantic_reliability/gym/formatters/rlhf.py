from typing import Dict, Any, List
from pydantic import BaseModel


class RLHFRewardItem(BaseModel):
    """Reward Model training format with paired completions and ground-truth preference score."""
    prompt: str
    completions: List[Dict[str, Any]]
    metric_id: str
    difficulty: str

    def to_jsonl_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "completions": self.completions,
            "metric_id": self.metric_id,
            "difficulty": self.difficulty,
        }
