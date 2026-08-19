import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import sqlglot
from sqlglot import exp

from semantic_reliability.compiler.schema import MetricDefinition


class MetricCompiler:
    """Compiles and validates canonical business metrics into AST representations."""

    def __init__(self, definition: MetricDefinition):
        self.definition = definition
        self._ast: Optional[exp.Expression] = None
        self._compile_ast()

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> "MetricCompiler":
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        definition = MetricDefinition(**raw)
        return cls(definition)

    @classmethod
    def from_yaml_str(cls, text: str) -> "MetricCompiler":
        raw = yaml.safe_load(text)
        definition = MetricDefinition(**raw)
        return cls(definition)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricCompiler":
        definition = MetricDefinition(**data)
        return cls(definition)

    def _compile_ast(self) -> None:
        try:
            self._ast = sqlglot.parse_one(self.definition.sql, read=self.definition.dialect)
        except Exception as e:
            raise ValueError(f"Failed to parse ground-truth SQL for metric '{self.definition.metric}': {e}") from e

    def get_ground_truth_sql(self, target_dialect: Optional[str] = None) -> str:
        """Return formatted canonical SQL query, optionally transpiled to target dialect."""
        if target_dialect and target_dialect != self.definition.dialect:
            return self._ast.sql(dialect=target_dialect, pretty=True)
        return self._ast.sql(pretty=True)

    def get_ast(self) -> exp.Expression:
        """Return the root AST node."""
        return self._ast.copy()

    def get_where_ast(self) -> Optional[exp.Where]:
        """Return the WHERE filter AST node if present."""
        return self._ast.find(exp.Where)

    def get_select_expressions(self) -> List[exp.Expression]:
        """Return list of selected columns/aggregations."""
        return list(self._ast.find_all(exp.Select))

    def get_aggregation_nodes(self) -> List[exp.Func]:
        """Return list of all aggregation functions (SUM, AVG, COUNT, etc.)."""
        return list(self._ast.find_all(exp.AggFunc))

    def get_tables(self) -> List[str]:
        """Return list of table names referenced in FROM and JOIN clauses."""
        return [t.name for t in self._ast.find_all(exp.Table)]

    def get_metadata(self) -> Dict[str, Any]:
        """Return non-SQL metadata."""
        return self.definition.model_dump(exclude={"sql"})
