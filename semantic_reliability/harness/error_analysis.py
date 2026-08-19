from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class RootCauseCategory(str, Enum):
    MISSING_CONTRACT = "MISSING_CONTRACT"
    WEAK_FIXTURE = "WEAK_FIXTURE"
    UNSUPPORTED_DIALECT = "UNSUPPORTED_DIALECT"
    ASSERTION_GAP = "ASSERTION_GAP"
    MUTATION_ORACLE_GAP = "MUTATION_ORACLE_GAP"
    RESULT_COMPARISON_GAP = "RESULT_COMPARISON_GAP"


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SurvivingDefectRecord(BaseModel):
    mutation_id: str
    model: str
    operator: str
    classification: str = "UNDETECTED_DEFECT"
    root_cause_category: RootCauseCategory
    root_cause_code: str
    description: str
    missing_contract_dimension: Optional[str] = None
    recommended_assertion: str
    severity: SeverityLevel = SeverityLevel.HIGH
    fixture_sensitive: bool = True
    reproduced: bool = True


class SurvivingDefectTaxonomy:
    """Standardized error analysis taxonomy for classifying surviving defects in the benchmark corpus."""

    KNOWN_HOLDOUT_SURVIVING_DEFECTS: List[SurvivingDefectRecord] = [
        SurvivingDefectRecord(
            mutation_id="ROAS_002",
            model="ad_campaign_roas",
            operator="BOUNDARY_SHIFT",
            root_cause_category=RootCauseCategory.MISSING_CONTRACT,
            root_cause_code="ATTRIBUTION_WINDOW_UNDECLARED",
            description="Campaign status or attribution cutoff shift survived because no exposure-to-conversion window contract was declared.",
            missing_contract_dimension="temporal_attribution_window",
            recommended_assertion="temporal_bounds_assertion(max_attribution_days=30)",
            severity=SeverityLevel.HIGH,
        ),
        SurvivingDefectRecord(
            mutation_id="READMISSION_001",
            model="hospital_readmission_rate",
            operator="FILTER_DROP",
            root_cause_category=RootCauseCategory.MISSING_CONTRACT,
            root_cause_code="INDEX_ADMISSION_DENOMINATOR_UNCONSTRAINED",
            description="Deceased/planned patient exclusion filter drop survived standard not-null checks without a denominator eligibility contract.",
            missing_contract_dimension="cohort_eligibility",
            recommended_assertion="required_population(source_table='hospital_discharges', required_filter='is_planned_readmission = false')",
            severity=SeverityLevel.HIGH,
        ),
        SurvivingDefectRecord(
            mutation_id="TAKE_RATE_002",
            model="marketplace_take_rate",
            operator="AGGREGATION_SWAP",
            root_cause_category=RootCauseCategory.ASSERTION_GAP,
            root_cause_code="NUMERATOR_DENOMINATOR_LINKAGE_MISSING",
            description="Commission fee aggregation swap produced valid float bounded within (0, 1) without a strict tolerance check.",
            missing_contract_dimension="aggregation_tolerance",
            recommended_assertion="metric_value(column='take_rate', tolerance_pct=1.0)",
            severity=SeverityLevel.MEDIUM,
        ),
        SurvivingDefectRecord(
            mutation_id="CHARGEBACK_001",
            model="fintech_chargeback_rate",
            operator="COALESCE_BYPASS",
            root_cause_category=RootCauseCategory.MUTATION_ORACLE_GAP,
            root_cause_code="EQUIVALENT_ON_FIXTURE_DENOMINATOR",
            description="Coalesce unwrap generated equivalent result because fixture dataset lacked explicit NULL chargeback flags.",
            missing_contract_dimension="null_policy",
            recommended_assertion="fixture_contrast(column='is_disputed', require_nulls=True)",
            severity=SeverityLevel.LOW,
        ),
    ]

    @classmethod
    def get_defect_analysis(cls, model_id: Optional[str] = None) -> List[SurvivingDefectRecord]:
        if model_id:
            return [d for d in cls.KNOWN_HOLDOUT_SURVIVING_DEFECTS if d.model == model_id]
        return cls.KNOWN_HOLDOUT_SURVIVING_DEFECTS
