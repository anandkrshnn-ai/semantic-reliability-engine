from enum import Enum
from typing import Optional, Dict, Any, List
from pathlib import Path
from pydantic import BaseModel, Field
import yaml


class BenchmarkConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class BenchmarkValidity(str, Enum):
    CONCLUSIVE = "CONCLUSIVE"
    QUALIFIED = "QUALIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ModelBenchmarkValidation(BaseModel):
    model_id: str
    total_mutations_generated: int = 0
    executable_mutations_count: int = 0
    equivalent_mutations_count: int = 0
    valid_defects_count: int = 0
    standard_detected_count: int = 0
    standard_surviving_count: int = 0
    semantic_detected_count: int = 0
    semantic_surviving_count: int = 0
    standard_catch_pct: float
    semantic_catch_pct: float
    incremental_gain_pct: float
    fixture_adequacy_pct: float
    contract_coverage_pct: float
    confidence: BenchmarkConfidence
    validity: BenchmarkValidity
    validity_notes: str
    policy_version: str = "1.0"


class BenchmarkValidityEvaluator:
    """Evaluates the scientific validity, confidence, and absolute defect counts of a benchmark run using a versioned policy."""

    POLICY_FILE = Path(__file__).resolve().parent / "validity_policy.yaml"

    @classmethod
    def load_policy(cls) -> Dict[str, Any]:
        if cls.POLICY_FILE.exists():
            try:
                return yaml.safe_load(cls.POLICY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "policy_version": "1.0",
            "thresholds": {
                "conclusive": {"min_fixture_adequacy": 80.0, "min_contract_coverage": 60.0},
                "qualified": {"min_fixture_adequacy": 60.0, "min_contract_coverage": 40.0},
            }
        }

    @classmethod
    def evaluate(
        cls,
        model_id: str,
        standard_catch_pct: float,
        semantic_catch_pct: float,
        fixture_adequacy_pct: float,
        contract_coverage_pct: float,
        total_mutations_generated: int = 0,
        executable_mutations_count: int = 0,
        equivalent_mutations_count: int = 0,
        valid_defects_count: int = 0,
        standard_detected_count: int = 0,
        standard_surviving_count: int = 0,
        semantic_detected_count: int = 0,
        semantic_surviving_count: int = 0,
    ) -> ModelBenchmarkValidation:
        policy = cls.load_policy()
        thresh = policy.get("thresholds", {})
        concl_t = thresh.get("conclusive", {"min_fixture_adequacy": 80.0, "min_contract_coverage": 60.0})
        qual_t = thresh.get("qualified", {"min_fixture_adequacy": 60.0, "min_contract_coverage": 40.0})

        incremental_gain = round(semantic_catch_pct - standard_catch_pct, 1)

        # Confidence & validity calculation based on versioned policy
        if (fixture_adequacy_pct >= concl_t["min_fixture_adequacy"] and
            contract_coverage_pct >= concl_t["min_contract_coverage"]):
            confidence = BenchmarkConfidence.HIGH
            validity = BenchmarkValidity.CONCLUSIVE
            validity_notes = "Fixture contrast and contract completeness meet strict conclusive standards."
        elif (fixture_adequacy_pct >= qual_t["min_fixture_adequacy"] and
              contract_coverage_pct >= qual_t["min_contract_coverage"]):
            confidence = BenchmarkConfidence.MEDIUM
            validity = BenchmarkValidity.QUALIFIED
            validity_notes = "Acceptable fixture contrast with partial contract coverage."
        else:
            confidence = BenchmarkConfidence.LOW
            validity = BenchmarkValidity.INCONCLUSIVE
            validity_notes = f"Fixture adequacy ({fixture_adequacy_pct:.0f}%) or contract coverage ({contract_coverage_pct:.0f}%) is below validity thresholds."

        return ModelBenchmarkValidation(
            model_id=model_id,
            total_mutations_generated=total_mutations_generated,
            executable_mutations_count=executable_mutations_count,
            equivalent_mutations_count=equivalent_mutations_count,
            valid_defects_count=valid_defects_count,
            standard_detected_count=standard_detected_count,
            standard_surviving_count=standard_surviving_count,
            semantic_detected_count=semantic_detected_count,
            semantic_surviving_count=semantic_surviving_count,
            standard_catch_pct=standard_catch_pct,
            semantic_catch_pct=semantic_catch_pct,
            incremental_gain_pct=incremental_gain,
            fixture_adequacy_pct=fixture_adequacy_pct,
            contract_coverage_pct=contract_coverage_pct,
            confidence=confidence,
            validity=validity,
            validity_notes=validity_notes,
            policy_version=policy.get("policy_version", "1.0"),
        )
