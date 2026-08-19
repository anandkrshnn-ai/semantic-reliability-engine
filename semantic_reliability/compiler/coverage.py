from typing import Dict, List, Set, Optional, Any
from pydantic import BaseModel, Field

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants


class MetricSemanticRequirement(BaseModel):
    metric_category: str
    required_dimensions: List[str]
    description: str


class ContractCoverageReport(BaseModel):
    metric_name: str
    metric_category: str
    declared_dimensions: List[str]
    missing_dimensions: List[str]
    coverage_score_pct: float

    @property
    def is_comprehensive(self) -> bool:
        return self.coverage_score_pct >= 75.0


class SemanticCoverageCalculator:
    """Calculates semantic contract completeness based on domain requirements for each metric class."""

    METRIC_DOMAIN_RULES: Dict[str, MetricSemanticRequirement] = {
        "net_revenue": MetricSemanticRequirement(
            metric_category="financial_revenue",
            required_dimensions=["population", "grain", "aggregation", "currency", "time"],
            description="Net financial metric requiring population filtering, grain, deduction mapping, currency, and period alignment."
        ),
        "monthly_active_users": MetricSemanticRequirement(
            metric_category="engagement_funnel",
            required_dimensions=["population", "grain", "time", "deduplication"],
            description="User engagement volume requiring active status filter, calendar period, and entity deduplication."
        ),
        "customer_churn_rate": MetricSemanticRequirement(
            metric_category="cohort_retention",
            required_dimensions=["population", "grain", "churn_definition", "denominator_eligibility"],
            description="Proportional lifecycle metric requiring cohort definition and denominator eligibility."
        ),
        "average_order_value": MetricSemanticRequirement(
            metric_category="ecommerce_ratio",
            required_dimensions=["population", "grain", "numerator_amount", "denominator_order_count"],
            description="Transaction ratio requiring completed order filter and distinct order count denominator."
        ),
        "inventory_turnover": MetricSemanticRequirement(
            metric_category="supply_chain_ratio",
            required_dimensions=["population", "grain", "cogs_component", "average_inventory"],
            description="Supply chain efficiency ratio requiring cost of goods sold and active stock valuation."
        ),
        "sla_compliance_rate": MetricSemanticRequirement(
            metric_category="operational_sla",
            required_dimensions=["population", "grain", "clock_start", "clock_stop", "exclusion_filter"],
            description="Operational SLA compliance requiring response window definition and spam/test exclusions."
        ),
        "checkout_conversion_rate": MetricSemanticRequirement(
            metric_category="funnel_conversion",
            required_dimensions=["population", "grain", "funnel_start_event", "funnel_complete_event"],
            description="Multi-step funnel requiring start event and terminal success event definitions."
        ),
        "customer_retention_rate": MetricSemanticRequirement(
            metric_category="cohort_retention",
            required_dimensions=["population", "grain", "cohort_period", "returning_window", "eligibility"],
            description="Cohort retention rate requiring baseline cohort definition and return time window."
        ),
    }

    @classmethod
    def evaluate_contract(cls, metric_def: MetricDefinition) -> ContractCoverageReport:
        metric_id = metric_def.metric.lower()
        req = cls.METRIC_DOMAIN_RULES.get(metric_id)

        if not req:
            # Default generic requirement
            req = MetricSemanticRequirement(
                metric_category="generic_metric",
                required_dimensions=["population", "grain", "aggregation"],
                description="Standard generic business metric."
            )

        declared_dims: List[str] = []
        invariants = metric_def.invariants or SemanticInvariants()

        # Check declared invariants
        if invariants.population and (invariants.population.required_filters or invariants.population.forbidden_filters):
            declared_dims.append("population")
            declared_dims.append("exclusion_filter")

        if invariants.grain and invariants.grain.required_dimensions:
            declared_dims.append("grain")

        if invariants.aggregation:
            if invariants.aggregation.required_function:
                declared_dims.append("aggregation")
            if invariants.aggregation.positive_components or invariants.aggregation.negative_components:
                declared_dims.append("aggregation")
                declared_dims.append("churn_definition")
                declared_dims.append("cogs_component")
                declared_dims.append("funnel_complete_event")

        if invariants.units and invariants.units.currency:
            declared_dims.append("currency")

        if invariants.time and (invariants.time.timezone or invariants.time.period_grain):
            declared_dims.append("time")
            declared_dims.append("cohort_period")
            declared_dims.append("clock_start")

        # Normalize unique set
        declared_set = set(declared_dims)
        required_set = set(req.required_dimensions)

        satisfied = declared_set.intersection(required_set)
        missing = required_set - declared_set

        score = (len(satisfied) / len(required_set) * 100.0) if required_set else 100.0

        return ContractCoverageReport(
            metric_name=metric_def.metric,
            metric_category=req.metric_category,
            declared_dimensions=sorted(list(satisfied)),
            missing_dimensions=sorted(list(missing)),
            coverage_score_pct=round(score, 1),
        )
