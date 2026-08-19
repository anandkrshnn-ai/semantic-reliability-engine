import json
from pathlib import Path
from typing import List, Dict, Any, Literal
import yaml

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.gym.generator import SemanticGymGenerator


def export_gym_dataset(
    corpus_dir: str | Path,
    output_path: str | Path,
    export_format: Literal["dpo", "rlhf", "sft"] = "dpo"
) -> int:
    """Scans all YAML metric contracts in corpus_dir and exports training pairs to output_path."""
    c_path = Path(corpus_dir)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    contract_files = list(c_path.glob("**/*.yaml"))
    total_records = 0

    with open(out_path, "w", encoding="utf-8") as f_out:
        for c_file in contract_files:
            try:
                data = yaml.safe_load(c_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "metric" not in data or "sql" not in data:
                    continue

                metric_def = MetricDefinition(**data)
                gen = SemanticGymGenerator(metric_def)

                if export_format == "dpo":
                    for item in gen.generate_dpo_pairs():
                        f_out.write(json.dumps(item.to_jsonl_dict()) + "\n")
                        total_records += 1
                elif export_format == "rlhf":
                    for item in gen.generate_rlhf_items():
                        f_out.write(json.dumps(item.to_jsonl_dict()) + "\n")
                        total_records += 1
                elif export_format == "sft":
                    for item in gen.generate_sft_instructions():
                        f_out.write(json.dumps(item.to_jsonl_dict()) + "\n")
                        total_records += 1
            except Exception as e:
                continue

    return total_records
