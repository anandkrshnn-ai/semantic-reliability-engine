import json
from pathlib import Path
from collections import Counter
from typing import Dict, Any


def inspect_dataset(dataset_path: str | Path, show_evidence: bool = False):
    path = Path(dataset_path)
    if not path.exists():
        print(f"File not found: {path}")
        return

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"\n🔍 Total records in {path.name}: {len(records)}")
    if not records:
        return

    diffs = Counter(r.get("metadata", {}).get("difficulty", "unknown") for r in records)
    muts = Counter(r.get("metadata", {}).get("mutation_type", "unknown") for r in records)

    print("\nDifficulty Distribution:")
    for k, v in diffs.items():
        print(f"  {k}: {v}")

    print("\nMutation Types:")
    for k, v in muts.items():
        print(f"  {k}: {v}")

    if show_evidence and records:
        print("\nSample Record Metadata:")
        print(json.dumps(records[0].get("metadata", {}), indent=2))
