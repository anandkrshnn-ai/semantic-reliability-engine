import json
from pathlib import Path
from typing import List, Tuple, Literal, Optional
import yaml

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.gym.models import GymEvidenceItem, CandidateRejectionStats
from semantic_reliability.gym.generator import SemanticGymGenerator
from semantic_reliability.gym.formatters.dpo import format_to_dpo
from semantic_reliability.gym.formatters.sft import format_to_sft
from semantic_reliability.gym.formatters.rlhf import format_to_rlhf


def export_gym_dataset(
    corpus_dir: str | Path,
    output_path: str | Path,
    export_format: Literal["dpo", "sft", "rlhf", "evidence"] = "dpo",
    split_filter: Optional[str] = None,
) -> Tuple[int, CandidateRejectionStats]:
    """
    Scans metric contracts and fixtures across corpus_dir, applies scientific validity gates,
    and exports formatted preference datasets.
    """
    c_path = Path(corpus_dir)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stats = CandidateRejectionStats()
    all_items: List[GymEvidenceItem] = []

    # Find all contract YAMLs
    contract_files = list(c_path.glob("**/*.yaml"))

    for c_file in contract_files:
        if c_file.name.startswith("assertions_") or c_file.name == "validity_policy.yaml":
            continue
        try:
            data = yaml.safe_load(c_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "metric" not in data or "sql" not in data:
                continue

            metric_def = MetricDefinition(**data)

            # Discover matching CSV fixture in model directory
            fixture_csv = c_file.parent / f"{c_file.stem}.csv"
            if not fixture_csv.exists():
                csvs = list(c_file.parent.glob("*.csv"))
                fixture_csv = csvs[0] if csvs else None

            gen = SemanticGymGenerator(
                metric_def=metric_def,
                fixture_path=fixture_csv,
            )

            items = gen.generate_evidence_pairs(stats=stats)
            for item in items:
                if split_filter and split_filter.lower() != "all" and item.split != split_filter.lower():
                    continue
                all_items.append(item)

        except Exception:
            continue

    with open(out_path, "w", encoding="utf-8") as f_out:
        for item in all_items:
            if export_format == "dpo":
                f_out.write(json.dumps(format_to_dpo(item)) + "\n")
            elif export_format == "sft":
                f_out.write(json.dumps(format_to_sft(item)) + "\n")
            elif export_format == "rlhf":
                f_out.write(json.dumps(format_to_rlhf(item)) + "\n")
            elif export_format == "evidence":
                f_out.write(json.dumps(item.model_dump()) + "\n")

    return len(all_items), stats
