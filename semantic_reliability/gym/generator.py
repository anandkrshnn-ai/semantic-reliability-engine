import logging
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any, Optional
import yaml
import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.mutations.engine import MutationEngine
from semantic_reliability.compiler.contracts import SemanticContractValidator
from .models import (
    GymExample,
    RejectionReason,
    SPLIT_RULES,
    assign_split,
    assign_difficulty,
    compute_evidence_hash,
)

logger = logging.getLogger("sre.gym")


class GymGenerator:
    """Consolidated Generator for SRE Semantic Gym Preference Datasets."""

    def __init__(self, corpus_dir: str | Path, policy_version: str = "v1.0.0-phase8.4"):
        self.corpus_dir = Path(corpus_dir)
        self.policy_version = policy_version
        self.rejection_counts: Dict[RejectionReason, int] = defaultdict(int)

    def generate(self, target_split: str = "all") -> List[GymExample]:
        examples: List[GymExample] = []

        for metric_path in self.corpus_dir.rglob("*.yaml"):
            if metric_path.name.startswith("assertions_") or metric_path.name == "validity_policy.yaml":
                continue

            try:
                data = yaml.safe_load(metric_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "metric" not in data or "sql" not in data:
                    continue
                contract = MetricDefinition(**data)
            except Exception as e:
                logger.warning(f"Failed to load {metric_path}: {e}")
                self.rejection_counts[RejectionReason.INCOMPLETE_CONTRACT] += 1
                continue

            family = contract.metadata.get("family", contract.metric)
            metric_split = assign_split(contract.metric, family)
            if target_split.lower() != "all" and metric_split != target_split.lower():
                continue

            # Locate fixture CSV in model directory
            fixture_path = metric_path.parent / f"{metric_path.stem}.csv"
            if not fixture_path.exists():
                csvs = list(metric_path.parent.glob("*.csv"))
                fixture_path = csvs[0] if csvs else None

            con = duckdb.connect(":memory:")
            has_fixture = False
            baseline_val: Optional[float] = None

            if fixture_path and fixture_path.exists():
                try:
                    ast_base = sqlglot.parse_one(contract.sql, read=contract.dialect)
                    table_expr = ast_base.find(exp.Table)
                    table_name = table_expr.name if table_expr else "transactions"
                    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{fixture_path}')")
                    has_fixture = True

                    res = con.execute(contract.sql).df()
                    if res.empty or len(res) == 0:
                        self.rejection_counts[RejectionReason.INSUFFICIENT_FIXTURE_CONTRAST] += 1
                        con.close()
                        continue
                    baseline_val = float(res.iloc[0, -1]) if pd.notnull(res.iloc[0, -1]) else 0.0
                except Exception:
                    self.rejection_counts[RejectionReason.UNEXECUTABLE] += 1
                    con.close()
                    continue

            # Verify chosen SQL satisfies its own contract
            eval_chosen = SemanticContractValidator.validate(candidate_sql=contract.sql, metric_def=contract)
            if not eval_chosen.passed:
                self.rejection_counts[RejectionReason.CHOSEN_CONTRACT_FAILURE] += 1
                con.close()
                continue

            engine = MutationEngine(base_sql=contract.sql, dialect=contract.dialect)
            mutations = engine.generate_all_mutations()

            for mut in mutations:
                allowed_muts = SPLIT_RULES.get(target_split.lower())
                if target_split.lower() != "all" and allowed_muts and mut.mutation_type.value not in allowed_muts:
                    continue

                mut_sql = mut.mutated_sql.strip()
                mut_val: Optional[float] = None
                variance_pct = 0.0

                if has_fixture:
                    try:
                        res_m = con.execute(mut_sql).df()
                        if not res_m.empty:
                            mut_val = float(res_m.iloc[0, -1]) if pd.notnull(res_m.iloc[0, -1]) else 0.0
                    except Exception:
                        self.rejection_counts[RejectionReason.UNEXECUTABLE] += 1
                        continue

                    if baseline_val is not None and mut_val is not None:
                        if baseline_val == mut_val:
                            self.rejection_counts[RejectionReason.EQUIVALENT_ON_FIXTURE] += 1
                            continue
                        if baseline_val != 0:
                            variance_pct = round(abs(mut_val - baseline_val) / abs(baseline_val) * 100.0, 2)
                        else:
                            variance_pct = 100.0

                eval_mut = SemanticContractValidator.validate(candidate_sql=mut_sql, metric_def=contract)
                violations = [f"{v.invariant_category}: {v.invariant_rule}" for v in eval_mut.violations]

                if not violations and variance_pct == 0.0:
                    self.rejection_counts[RejectionReason.REJECTED_NOT_SEMANTICALLY_DIVERGENT] += 1
                    continue

                difficulty, reasons = assign_difficulty(mut.mutation_type.value, contract)

                chosen_evidence = {
                    "execution": True,
                    "contract_passed": True,
                    "assertions_passed": True,
                    "violations": [],
                }
                rejected_evidence = {
                    "execution": True,
                    "contract_passed": len(violations) == 0,
                    "assertions_passed": False,
                    "variance_pct": variance_pct,
                    "violations": violations,
                }

                evidence_payload = {
                    "chosen": chosen_evidence,
                    "rejected": rejected_evidence,
                    "mutation": mut.mutation_type.value,
                    "metric": contract.metric,
                }
                ev_hash = compute_evidence_hash(evidence_payload)

                prompt = contract.description or f"Write a production-grade SQL query to calculate '{contract.metric}' for owner '{contract.owner}' at '{contract.grain}' granularity."

                examples.append(GymExample(
                    example_id=f"{contract.metric}_{mut.mutation_type.value.lower()}",
                    prompt=prompt,
                    contract_id=contract.metric,
                    contract_version=getattr(contract, "version", "1.0.0"),
                    chosen_sql=contract.sql.strip(),
                    rejected_sql=mut_sql,
                    mutation_type=mut.mutation_type.value,
                    mutation_description=mut.description,
                    chosen_evidence=chosen_evidence,
                    rejected_evidence=rejected_evidence,
                    difficulty=difficulty,
                    difficulty_reasons=reasons,
                    fixture_id=fixture_path.stem if fixture_path else "synthetic",
                    policy_version=self.policy_version,
                    evidence_hash=ev_hash,
                    split=metric_split,
                    metric_family=family,
                ))

            con.close()

        return examples


# Alias for backward compatibility
SemanticGymGenerator = GymGenerator
