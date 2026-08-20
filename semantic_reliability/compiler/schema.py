from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class PopulationInvariant(BaseModel):
    required_filters: List[str] = Field(default_factory=list, description="Filters that must always be present in WHERE clause")
    forbidden_filters: List[str] = Field(default_factory=list, description="Filters that must never appear")


class GrainInvariant(BaseModel):
    required_dimensions: List[str] = Field(default_factory=list, description="Grouping dimensions that define the reporting grain")
    allow_over_aggregation: bool = Field(False, description="Whether higher-level aggregations are permitted")


class AggregationInvariant(BaseModel):
    required_function: Optional[str] = Field(None, description="Expected top-level aggregate function (SUM, AVG, COUNT)")
    positive_components: List[str] = Field(default_factory=list, description="Values that must be added (e.g. invoice)")
    negative_components: List[str] = Field(default_factory=list, description="Values that must be subtracted (e.g. refund)")


class UnitInvariant(BaseModel):
    currency: Optional[str] = Field(None, description="Expected currency (USD, EUR, INR)")
    scale: Optional[str] = Field("standard", description="Scale definition (e.g. dollars vs cents, units vs thousands)")


class TimeInvariant(BaseModel):
    timezone: Optional[str] = Field("UTC", description="Expected timestamp timezone")
    period_grain: Optional[str] = Field(None, description="Calendar vs Fiscal period definitions (e.g. calendar_month)")


class SemanticInvariants(BaseModel):
    population: Optional[PopulationInvariant] = Field(default_factory=PopulationInvariant)
    grain: Optional[GrainInvariant] = Field(default_factory=GrainInvariant)
    aggregation: Optional[AggregationInvariant] = Field(default_factory=AggregationInvariant)
    units: Optional[UnitInvariant] = Field(default_factory=UnitInvariant)
    time: Optional[TimeInvariant] = Field(default_factory=TimeInvariant)


class PopulationProbe(BaseModel):
    """Checks if a filter predicate selects the expected proportion of the population."""
    column: str
    target_value: Optional[Any] = None
    baseline_rate: float = Field(..., description="Expected ratio (0.0 to 1.0)")
    tolerance: float = Field(0.05, description="Absolute tolerance for rate deviation")


class ImplicationProbe(BaseModel):
    """Checks if Condition A implies Condition B (e.g., 'Active' implies 'Revenue > 0')."""
    condition_column: str
    condition_value: Any
    implication_column: str
    implication_operator: str = Field(default=">", description="Comparison operator: '>', '<', '=', '!=', 'IS NOT NULL'")
    implication_value: Optional[Any] = None
    baseline_confidence: float = Field(..., description="Expected P(B|A) (0.0 to 1.0)")
    tolerance_drop: float = Field(0.10, description="Alert if confidence drops by > X")


class NullDriftProbe(BaseModel):
    """Monitors the null rate of critical semantic columns."""
    column: str
    baseline_null_rate: float = Field(default=0.0, description="Expected null percentage (0.0 to 1.0)")
    tolerance: float = Field(0.02, description="Max acceptable absolute null rate deviation")


class MetricProbes(BaseModel):
    """Declarative statistical observability expectations."""
    population: List[PopulationProbe] = Field(default_factory=list)
    implications: List[ImplicationProbe] = Field(default_factory=list)
    null_drift: List[NullDriftProbe] = Field(default_factory=list)


class ContractProvenance(BaseModel):
    """Verifiable upstream sourcing and provenance metadata for metric contracts."""
    repository: Optional[str] = Field(None, description="Canonical source repository URL (e.g. https://github.com/dbt-labs/jaffle_shop)")
    organization: Optional[str] = Field(None, description="Authoring or publishing organization")
    reference_path: Optional[str] = Field(None, description="Path within upstream repository")
    commit_sha: Optional[str] = Field(None, description="Verified upstream commit hash")
    verified_at: Optional[str] = Field(None, description="ISO timestamp of last mechanical verification")
    verified_symbols: List[str] = Field(default_factory=list, description="Verified column, model, and test symbols")
    license: Optional[str] = Field("Apache-2.0", description="Contract or upstream license")


class MetricDefinition(BaseModel):
    """Schema for ground-truth business metric definitions with policy-driven invariants and statistical probes."""
    metric: str = Field(..., description="Unique metric identifier (e.g. net_revenue)")
    description: Optional[str] = Field(None, description="Human-readable description of the metric")
    owner: str = Field(..., description="Business or team owner of the metric (e.g. finance, revops)")
    grain: str = Field(..., description="Reporting grain/granularity (e.g. customer_month, daily, transaction)")
    sql: str = Field(..., description="Canonical ground-truth SQL query definition")
    dialect: Optional[str] = Field("postgres", description="SQL dialect of canonical query (e.g. snowflake, bigquery, postgres, duckdb)")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    dimensions: List[str] = Field(default_factory=list, description="Allowed slice/dice dimensions")
    invariants: Optional[SemanticInvariants] = Field(default_factory=SemanticInvariants, description="Declarative semantic contract invariants")
    probes: Optional[MetricProbes] = Field(default_factory=MetricProbes, description="Declarative statistical probes for runtime semantic observability")
    provenance: Optional[ContractProvenance] = Field(None, description="Verifiable external provenance metadata")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary custom metadata")

