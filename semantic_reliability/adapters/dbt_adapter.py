from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel, Field
import yaml

from semantic_reliability.assertions.base import DataAssertion
from semantic_reliability.assertions.base import DataAssertion
from semantic_reliability.assertions.structural import (
    NonNullOutputAssertion,
    UniqueKeyAssertion,
    RowCountBoundsAssertion,
    AcceptedRangeAssertion,
    AcceptedValuesAssertion,
    RelationshipsAssertion,
    SingularSqlAssertion,
)
from semantic_reliability.assertions.registry import AssertionSuite


class DBTParsingAudit(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    suite: AssertionSuite
    declared_tests_count: int
    supported_tests_count: int
    skipped_tests_count: int
    skipped_test_names: List[str] = Field(default_factory=list)


class DBTTestAdapter:
    """Parses standard dbt schema.yml / models.yml test definitions with explicit tracking of skipped tests."""

    @classmethod
    def parse_schema_yml(cls, yml_path: str | Path, model_name: Optional[str] = None) -> AssertionSuite:
        audit = cls.parse_schema_yml_with_audit(yml_path, model_name=model_name)
        return audit.suite

    @classmethod
    def parse_schema_yml_with_audit(cls, yml_path: str | Path, model_name: Optional[str] = None) -> DBTParsingAudit:
        content = Path(yml_path).read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        models = data.get("models", [])
        if not models and "version" in data and "seeds" in data:
            models = data.get("seeds", [])

        suite = AssertionSuite(name=f"dbt_tests_{model_name or Path(yml_path).stem}")
        declared_count = 0
        supported_count = 0
        skipped_names: List[str] = []

        for m in models:
            m_name = m.get("name")
            if model_name and m_name != model_name:
                continue

            columns = m.get("columns", [])
            for col in columns:
                col_name = col.get("name")
                tests = col.get("tests", [])

                for t in tests:
                    declared_count += 1
                    if isinstance(t, str):
                        t_name = t.lower()
                        if t_name == "not_null":
                            suite.add(NonNullOutputAssertion(columns=[col_name], name=f"dbt_not_null_{col_name}"))
                            supported_count += 1
                        elif t_name == "unique":
                            suite.add(UniqueKeyAssertion(columns=[col_name], name=f"dbt_unique_{col_name}"))
                            supported_count += 1
                        else:
                            skipped_names.append(f"{col_name}.{t_name}")
                    elif isinstance(t, dict):
                        t_key = list(t.keys())[0]
                        t_cfg = t[t_key] or {}
                        t_key_lower = t_key.lower()

                        if t_key_lower == "not_null":
                            suite.add(NonNullOutputAssertion(columns=[col_name], name=f"dbt_not_null_{col_name}"))
                            supported_count += 1
                        elif t_key_lower == "unique":
                            suite.add(UniqueKeyAssertion(columns=[col_name], name=f"dbt_unique_{col_name}"))
                            supported_count += 1
                        elif t_key_lower == "accepted_values":
                            vals = t_cfg.get("values", []) if isinstance(t_cfg, dict) else t_cfg
                            suite.add(AcceptedValuesAssertion(column=col_name, values=vals, name=f"dbt_accepted_values_{col_name}"))
                            supported_count += 1
                        elif t_key_lower in ("accepted_range", "dbt_utils.accepted_range"):
                            min_val = t_cfg.get("min_value") if isinstance(t_cfg, dict) else None
                            max_val = t_cfg.get("max_value") if isinstance(t_cfg, dict) else None
                            suite.add(AcceptedRangeAssertion(column=col_name, min_value=min_val, max_value=max_val, name=f"dbt_accepted_range_{col_name}"))
                            supported_count += 1
                        elif t_key_lower == "relationships":
                            to_tbl = t_cfg.get("to", t_cfg.get("to_table")) if isinstance(t_cfg, dict) else ""
                            # clean ref('table') format if present
                            if to_tbl.startswith("ref(") and to_tbl.endswith(")"):
                                to_tbl = to_tbl[4:-1].strip("'\"")
                            to_col = t_cfg.get("field", t_cfg.get("to_column")) if isinstance(t_cfg, dict) else ""
                            suite.add(RelationshipsAssertion(from_column=col_name, to_table=to_tbl, to_column=to_col, name=f"dbt_relationships_{col_name}"))
                            supported_count += 1
                        else:
                            skipped_names.append(f"{col_name}.{t_key}")

            # Check model-level tests
            model_tests = m.get("tests", [])
            for mt in model_tests:
                declared_count += 1
                if isinstance(mt, dict):
                    mt_key = list(mt.keys())[0]
                    mt_cfg = mt[mt_key] or {}
                    if mt_key == "dbt_utils.unique_combination_of_columns":
                        comb_cols = mt_cfg.get("combination_of_columns", [])
                        suite.add(UniqueKeyAssertion(columns=comb_cols, name=f"dbt_unique_combo_{'_'.join(comb_cols)}"))
                        supported_count += 1
                    elif mt_key in ("row_count_bounds", "dbt_utils.row_count_bounds"):
                        min_r = mt_cfg.get("min_rows", 1)
                        max_r = mt_cfg.get("max_rows", None)
                        suite.add(RowCountBoundsAssertion(min_rows=min_r, max_rows=max_r, name=f"dbt_row_count_bounds_{m_name}"))
                        supported_count += 1
                    else:
                        skipped_names.append(f"model_test.{mt_key}")
                elif isinstance(mt, str):
                    skipped_names.append(f"model_test.{mt}")

        if not suite.assertions:
            suite.add(RowCountBoundsAssertion(min_rows=1, name="dbt_table_exists"))
            supported_count += 1

        return DBTParsingAudit(
            suite=suite,
            declared_tests_count=declared_count,
            supported_tests_count=supported_count,
            skipped_tests_count=len(skipped_names),
            skipped_test_names=skipped_names,
        )
