"""
CLI / Cron entry point for running the Replay Worker loop.
"""
import sys
from pathlib import Path
from typing import Optional, List
from .worker import ReplayWorker, LocalFixtureSnapshotProvider, ReplayResult
from .patcher import ContractPatcher


def run_replay_cycle(
    audit_log_path: str | Path,
    contract_dir: str | Path,
    fixture_dir: Optional[str | Path] = None,
) -> List[ReplayResult]:
    log_p = Path(audit_log_path)
    if not log_p.exists():
        print(f"Error: Audit log file '{audit_log_path}' not found.")
        return []

    snapshot_provider = LocalFixtureSnapshotProvider(fixture_dir=fixture_dir)
    worker = ReplayWorker(contract_dir=contract_dir, snapshot_provider=snapshot_provider)
    patcher = ContractPatcher()

    results: List[ReplayResult] = []

    with open(log_p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                res = worker.process_trace(line)
                if res:
                    results.append(res)
                    if res.contract_underspecified:
                        print(f"\n🚨 UNDERSPECIFIED CONTRACT DETECTED: metric='{res.metric_id}' (trace: {res.trace_id})")
                        print(f"   Catch Score: {res.catch_score:.1f}% | Surviving Valid Defects: {res.undetected_defects}")
                        suggestions = patcher.suggest_invariants(res.blind_spots)
                        pr_body = patcher.generate_pr_body(res.metric_id, suggestions, trace_id=res.trace_id)
                        print("\n--- GENERATED PULL REQUEST BODY ---")
                        print(pr_body)
                        print("------------------------------------\n")
            except Exception as e:
                print(f"Error processing trace line: {str(e)}", file=sys.stderr)

    return results
