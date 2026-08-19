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
                "rejection_basis": ex.rejected_evidence.get("rejection_basis", []),
            }
        }


class SFTFormatter:
    """Formats GymExample into SFT instruction-tuning format with structured reason codes."""
    def format(self, ex: GymExample) -> Dict[str, Any]:
        reason_codes = []
        if ex.chosen_evidence.get("contract_compliant"):
            reason_codes.append("CONTRACT_COMPLIANT")
        if ex.chosen_evidence.get("assertions_passed"):
            reason_codes.append("ASSERTIONS_PASSED")

        return {
            "prompt": ex.prompt,
            "completion": ex.chosen_sql,
            "reason_codes": reason_codes,
            "metadata": {
                "example_id": ex.example_id,
                "contract_id": ex.contract_id,
                "difficulty": ex.difficulty,
                "evidence_hash": ex.evidence_hash,
            }
        }


class RLHFFormatter:
    """Formats GymExample into RLHF reward modeling pair with multi-component reward breakdowns."""
    def format(self, ex: GymExample) -> Dict[str, Any]:
        return {
            "prompt": ex.prompt,
            "response": ex.chosen_sql,
            "reward_components": {
                "execution": 1.0,
                "contract": 1.0,
                "assertions": 1.0,
                "fixture_divergence": 0.0,
                "cost": None,
            },
            "reward_policy_version": "sre-reward-v1",
            "metadata": {
                "example_id": ex.example_id,
                "contract_id": ex.contract_id,
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
