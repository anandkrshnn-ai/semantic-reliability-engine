import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.mutations.engine import MutationEngine
from semantic_reliability.gym.difficulty import calibrate_difficulty
from semantic_reliability.gym.formatters.dpo import DPOPreferenceItem
from semantic_reliability.gym.formatters.rlhf import RLHFRewardItem
from semantic_reliability.gym.formatters.sft import SFTInstructionItem


class SemanticGymGenerator:
    """Generates contract-grounded preference and alignment datasets from metric contracts and AST mutations."""

    def __init__(self, metric_def: MetricDefinition):
        self.metric_def = metric_def

    def generate_dpo_pairs(self) -> List[DPOPreferenceItem]:
        pairs: List[DPOPreferenceItem] = []
        prompt = self._build_prompt()

        engine = MutationEngine(base_sql=self.metric_def.sql, dialect=self.metric_def.dialect)
        mutations = engine.generate_all_mutations()

        for m in mutations:
            diff = calibrate_difficulty(m.mutation_type.value)
            pairs.append(DPOPreferenceItem(
                prompt=prompt,
                chosen=self.metric_def.sql.strip(),
                rejected=m.mutated_sql.strip(),
                metric_id=self.metric_def.metric,
                mutation_type=m.mutation_type.value,
                difficulty=diff.value,
                violation_reason=m.description,
            ))

        return pairs

    def generate_rlhf_items(self) -> List[RLHFRewardItem]:
        items: List[RLHFRewardItem] = []
        prompt = self._build_prompt()

        engine = MutationEngine(base_sql=self.metric_def.sql, dialect=self.metric_def.dialect)
        mutations = engine.generate_all_mutations()

        for m in mutations:
            diff = calibrate_difficulty(m.mutation_type.value)
            items.append(RLHFRewardItem(
                prompt=prompt,
                completions=[
                    {"sql": self.metric_def.sql.strip(), "reward": 1.0, "compliant": True},
                    {"sql": m.mutated_sql.strip(), "reward": 0.0, "compliant": False, "flaw": m.description},
                ],
                metric_id=self.metric_def.metric,
                difficulty=diff.value,
            ))

        return items

    def generate_sft_instructions(self) -> List[SFTInstructionItem]:
        instructions: List[SFTInstructionItem] = []
        engine = MutationEngine(base_sql=self.metric_def.sql, dialect=self.metric_def.dialect)
        mutations = engine.generate_all_mutations()

        for m in mutations:
            rationale = (
                f"The correct SQL must satisfy the '{self.metric_def.metric}' business definition. "
                f"An incorrect formulation might inadvertently introduce '{m.description}', which corrupts reporting."
            )
            instructions.append(SFTInstructionItem(
                instruction=f"Write a canonical SQL query to compute '{self.metric_def.metric}' for owner '{self.metric_def.owner}' at grain '{self.metric_def.grain}'.",
                input=f"Metric: {self.metric_def.metric}\nGrain: {self.metric_def.grain}",
                output=self.metric_def.sql.strip(),
                negative_example=m.mutated_sql.strip(),
                semantic_rationale=rationale,
                metric_id=self.metric_def.metric,
            ))

        return instructions

    def _build_prompt(self) -> str:
        desc = self.metric_def.description or f"Compute ground-truth {self.metric_def.metric}"
        return (
            f"You are an enterprise data engineer. Write a production-grade SQL query to calculate '{self.metric_def.metric}' "
            f"for the '{self.metric_def.owner}' team at '{self.metric_def.grain}' granularity. {desc}."
        )
