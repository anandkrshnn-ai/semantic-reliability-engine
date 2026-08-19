from typing import Optional, List, Dict, Any
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


class MetricDefinition(BaseModel):
    """Schema for ground-truth business metric definitions with policy-driven invariants."""
    metric: str = Field(..., description="Unique metric identifier (e.g. net_revenue)")
    description: Optional[str] = Field(None, description="Human-readable description of the metric")
    owner: str = Field(..., description="Business or team owner of the metric (e.g. finance, revops)")
    grain: str = Field(..., description="Reporting grain/granularity (e.g. customer_month, daily, transaction)")
    sql: str = Field(..., description="Canonical ground-truth SQL query definition")
    dialect: Optional[str] = Field("postgres", description="SQL dialect of canonical query (e.g. snowflake, bigquery, postgres, duckdb)")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    dimensions: List[str] = Field(default_factory=list, description="Allowed slice/dice dimensions")
    invariants: Optional[SemanticInvariants] = Field(default_factory=SemanticInvariants, description="Declarative semantic contract invariants")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary custom metadata")
