from typing import Dict, Any
from .models import GymExample


class DPOFormatter:
    """Formats GymExample into standard Hugging Face TRL / Anthropic DPO format."""
    def format(self, ex: GymExample) -> Dict[str, Any]:
        return {
            "prompt": ex.prompt,
            "chosen": ex.chosen_sql,
            "rejected": ex.rejected_sql,
            "metadata": {
                "example_id": ex.example_id,
                "contract_id": ex.contract_id,
                "mutation_type": ex.mutation_type,
                "difficulty": ex.difficulty,
                "evidence_hash": ex.evidence_hash,
                "split": ex.split,
            }
        }


class SFTFormatter:
    """Formats GymExample into SFT instruction-tuning format with reasoning traces."""
    def format(self, ex: GymExample) -> Dict[str, Any]:
        return {
            "prompt": ex.prompt,
            "completion": ex.chosen_sql,
            "negative_example": ex.rejected_sql,
            "semantic_rationale": f"Contract '{ex.contract_id}' requires specific invariants. An invalid formulation would introduce '{ex.mutation_description}'.",
            "metadata": {
                "example_id": ex.example_id,
                "difficulty": ex.difficulty,
                "evidence_hash": ex.evidence_hash,
            }
        }


class RLHFFormatter:
    """Formats GymExample into RLHF reward modeling pair with fine-grained scores."""
    def format(self, ex: GymExample) -> Dict[str, Any]:
        return {
            "prompt": ex.prompt,
            "completions": [
                {
                    "response": ex.chosen_sql,
                    "reward": 1.0,
                    "compliant": True,
                    "evidence": ex.chosen_evidence,
                },
                {
                    "response": ex.rejected_sql,
                    "reward": 0.0,
                    "compliant": False,
                    "evidence": ex.rejected_evidence,
                }
            ],
            "metadata": {
                "example_id": ex.example_id,
                "difficulty": ex.difficulty,
                "evidence_hash": ex.evidence_hash,
            }
        }


def get_formatter(fmt: str):
    fmt_lower = fmt.lower()
    if fmt_lower == "dpo":
        return DPOFormatter()
    if fmt_lower == "sft":
        return SFTFormatter()
    if fmt_lower == "rlhf":
        return RLHFFormatter()
    raise ValueError(f"Unknown format: '{fmt}'. Expected 'dpo', 'sft', or 'rlhf'.")
