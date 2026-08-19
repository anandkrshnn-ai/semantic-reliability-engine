"""Oracle Validator for Phase 12.1 Benchmark Harness."""
import hashlib
import json
from typing import Optional, Dict, Any
import duckdb
import pandas as pd
import numpy as np
import sqlglot

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.compiler.contracts import SemanticContractValidator
from semantic_reliability.firewall.engine import ContractRegistry
from .protocol import BenchmarkScenario


class OracleValidator:
    """Proves the Golden SQL is a valid oracle, and grades agent outputs against it."""

    def __init__(self, conn: Optional[duckdb.DuckDBPyConnection] = None, registry: Optional[ContractRegistry] = None, float_tol: float = 1e-4):
        self.conn = conn or duckdb.connect(":memory:")
        self.registry = registry or ContractRegistry()
        self.float_tol = float_tol

    def validate_oracle(self, scenario: BenchmarkScenario, dialect: str = "duckdb") -> bool:
        """Proves the golden SQL executes cleanly, satisfies SCOS invariants, and matches fingerprint."""
        if not scenario.golden_sql:
            return scenario.expected_behavior != "PRODUCE_SQL"

        try:
            # 1. Check execution
            res_df = self.conn.execute(scenario.golden_sql).df()

            # 2. Check SCOS contract satisfaction
            if scenario.target_metric_urn:
                m_slug = scenario.target_metric_urn.split(":")[-1]
                m_def, _ = self.registry.get(m_slug)
                val_res = SemanticContractValidator.validate(candidate_sql=scenario.golden_sql, metric_def=m_def, dialect=dialect)
                if not val_res.passed:
                    return False

            # 3. Check fixture fingerprint
            if scenario.fixture_fingerprint:
                serialized = json.dumps(res_df.to_dict(orient="records"), sort_keys=True, default=str).encode("utf-8")
                fp = hashlib.sha256(serialized).hexdigest()
                if fp != scenario.fixture_fingerprint:
                    return False

            return True
        except Exception:
            return False

    def evaluate_agent_sql(self, agent_sql: Optional[str], scenario: BenchmarkScenario, dialect: str = "duckdb") -> Dict[str, bool]:
        """Evaluates agent output against SCOS contract and Oracle Golden SQL."""
        if not agent_sql or not agent_sql.strip():
            return {
                "execution_success": False,
                "contract_compliant": False,
                "result_correct": False,
            }

        # 1. Execution
        exec_success = False
        agent_df: Optional[pd.DataFrame] = None
        try:
            agent_df = self.conn.execute(agent_sql).df()
            exec_success = True
        except Exception:
            exec_success = False

        # 2. Contract Compliance
        contract_compliant = True
        if scenario.expected_behavior in ("ABSTAIN", "ASK_CLARIFICATION", "REQUIRE_REVIEW"):
            # Generating unguided SQL when the scenario requires abstention/clarification is non-compliant
            contract_compliant = False
        elif scenario.target_metric_urn:
            try:
                m_slug = scenario.target_metric_urn.split(":")[-1]
                m_def, _ = self.registry.get(m_slug)
                val_res = SemanticContractValidator.validate(candidate_sql=agent_sql, metric_def=m_def, dialect=dialect)
                contract_compliant = val_res.passed
            except Exception:
                contract_compliant = False

        # 3. Result Correctness vs Oracle
        result_correct = False
        if exec_success and scenario.golden_sql and agent_df is not None:
            try:
                oracle_df = self.conn.execute(scenario.golden_sql).df()
                result_correct = self._compare_dataframes(agent_df, oracle_df)
            except Exception:
                result_correct = False

        return {
            "execution_success": exec_success,
            "contract_compliant": contract_compliant,
            "result_correct": result_correct,
        }

    def _compare_dataframes(self, df_cand: pd.DataFrame, df_true: pd.DataFrame) -> bool:
        """Order-insensitive, numeric-tolerant canonical row dataframe comparison."""
        if df_cand is None or df_true is None:
            return False
        if df_cand.empty and df_true.empty:
            return True
        if df_cand.empty != df_true.empty:
            return False
        if len(df_cand) != len(df_true) or df_cand.shape[1] != df_true.shape[1]:
            return False

        try:
            def canonical_row(row, cols):
                items = []
                for c in cols:
                    val = row[c]
                    if pd.isna(val) or val is None:
                        items.append(f"{c}:__NULL__")
                    elif isinstance(val, (int, float, np.number)):
                        rounded = round(float(val), 4)
                        items.append(f"{c}:{rounded}")
                    else:
                        items.append(f"{c}:{str(val).strip()}")
                return tuple(items)

            c_cols = sorted(df_cand.columns) if set(df_cand.columns) == set(df_true.columns) else list(df_cand.columns)
            t_cols = sorted(df_true.columns) if set(df_cand.columns) == set(df_true.columns) else list(df_true.columns)

            c_rows = sorted([canonical_row(row, c_cols) for _, row in df_cand.iterrows()])
            t_rows = sorted([canonical_row(row, t_cols) for _, row in df_true.iterrows()])

            return c_rows == t_rows
        except Exception:
            return False
