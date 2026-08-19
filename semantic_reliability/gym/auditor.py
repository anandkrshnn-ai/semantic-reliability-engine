import json
from pathlib import Path
from collections import Counter
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

from .models import SPLIT_RULES


class GymAuditReport(BaseModel):
    """Audit report validating integrity, leakage absence, and distribution balance of a Gym dataset."""
    total_records: int = 0
    duplicate_example_ids: int = 0
    duplicate_evidence_hashes: int = 0
    conflicting_preference_labels: int = 0
    chosen_rejected_identical: int = 0
    missing_evidence: int = 0
    missing_contract_versions: int = 0
    missing_fixture_ids: int = 0
    mutation_family_leakage: int = 0
    metric_family_leakage: int = 0
    domain_leakage: int = 0
    mutation_distribution: Dict[str, float] = Field(default_factory=dict)
    difficulty_distribution: Dict[str, float] = Field(default_factory=dict)
    split_distribution: Dict[str, float] = Field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return (
            self.duplicate_example_ids == 0
            and self.duplicate_evidence_hashes == 0
            and self.conflicting_preference_labels == 0
            and self.chosen_rejected_identical == 0
            and self.missing_evidence == 0
            and self.mutation_family_leakage == 0
            and self.metric_family_leakage == 0
            and self.domain_leakage == 0
        )


def audit_gym_dataset(dataset_path: str | Path, target_split: Optional[str] = None) -> GymAuditReport:
    """
    Performs comprehensive static and statistical audit on exported dataset file:
    - Integrity: duplicate hashes, missing metadata, identical chosen/rejected.
    - Leakage: verifies no holdout mutation types or forbidden domains appear in train split.
    - Distribution: percentages per mutation operator and difficulty level.
    """
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = GymAuditReport(total_records=len(lines))

    if not lines:
        return report

    seen_example_ids = set()
    seen_evidence_hashes = set()
    prompt_pairs: Dict[str, str] = {}  # prompt -> chosen_sql

    mutation_counts = Counter()
    difficulty_counts = Counter()
    split_counts = Counter()

    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            report.missing_evidence += 1
            continue

        prompt = rec.get("prompt", rec.get("instruction", ""))
        chosen = rec.get("chosen", rec.get("output", rec.get("completion", ""))).strip()
        rejected = rec.get("rejected", rec.get("negative_example", "")).strip()

        meta = rec.get("metadata", {})

        # Check 1: Identical chosen & rejected
        if chosen and rejected and chosen == rejected:
            report.chosen_rejected_identical += 1

        # Check 2: Conflicting preference labels
        if prompt in prompt_pairs:
            if prompt_pairs[prompt] != chosen:
                report.conflicting_preference_labels += 1
        else:
            prompt_pairs[prompt] = chosen

        # Check 3: Metadata presence & Hashes
        ex_id = meta.get("example_id")
        ev_hash = meta.get("evidence_hash")
        split = meta.get("split", target_split or "train")
        mut_type = meta.get("mutation_type", "UNKNOWN")
        diff = meta.get("difficulty", "medium").upper()

        if not ex_id:
            report.missing_evidence += 1
        elif ex_id in seen_example_ids:
            report.duplicate_example_ids += 1
        else:
            seen_example_ids.add(ex_id)

        if not ev_hash:
            report.missing_evidence += 1
        elif ev_hash in seen_evidence_hashes:
            report.duplicate_evidence_hashes += 1
        else:
            seen_evidence_hashes.add(ev_hash)

        # Check 4: Leakage validation
        if split == "train":
            # Train split must not contain holdout mutations
            if mut_type in ("GRAIN_DROP", "MATH_OPERATOR_INVERT", "JOIN_PREDICATE_DROP"):
                report.mutation_family_leakage += 1
            # Train split must not contain holdout domains
            if meta.get("domain", "").lower() in ("healthcare", "infrastructure", "risk"):
                report.domain_leakage += 1

        # Distribution tracking
        mutation_counts[mut_type] += 1
        difficulty_counts[diff] += 1
        split_counts[split] += 1

    # Compute percentages
    total = len(lines)
    report.mutation_distribution = {
        k: round((v / total) * 100.0, 1) for k, v in mutation_counts.items()
    }
    report.difficulty_distribution = {
        k: round((v / total) * 100.0, 1) for k, v in difficulty_counts.items()
    }
    report.split_distribution = {
        k: round((v / total) * 100.0, 1) for k, v in split_counts.items()
    }

    return report
