from typing import Dict, Any, List
from pydantic import BaseModel


class SFTInstructionItem(BaseModel):
    """Supervised Fine-Tuning instruction format with chain-of-thought semantic contract rationale."""
    instruction: str
    input: str
    output: str
    negative_example: str
    semantic_rationale: str
    metric_id: str

    def to_jsonl_dict(self) -> Dict[str, Any]:
        return {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output,
            "negative_example": self.negative_example,
            "semantic_rationale": self.semantic_rationale,
            "metadata": {
                "metric_id": self.metric_id,
            }
        }
