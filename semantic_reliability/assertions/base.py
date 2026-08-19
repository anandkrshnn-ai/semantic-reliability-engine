from typing import Protocol, Optional, List, Dict, Any, runtime_checkable
from pydantic import BaseModel, Field
import duckdb


class AssertionResult(BaseModel):
    """Result of running a single data quality or semantic assertion."""
    name: str
    assertion_type: str
    passed: bool
    description: str
    failure_reason: Optional[str] = None
    execution_time_ms: float = 0.0


@runtime_checkable
class DataAssertion(Protocol):
    """Protocol for data quality and semantic assertions executed in DuckDB/Warehouse."""
    name: str
    assertion_type: str

    def evaluate(self, con: duckdb.DuckDBPyConnection, sql: str) -> AssertionResult:
        """Evaluate assertion against a candidate/mutated SQL query within the database connection."""
        ...
