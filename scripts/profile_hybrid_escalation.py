#!/usr/bin/env python3
"""Empirical Profiling Script for Hybrid Adaptive Validation Router.

Evaluates the HybridValidator (Tier 3 Static Pre-flight + Tier 4 Adaptive Runtime Escalation)
across all 14 benchmark models and 45 valid executable semantic mutations.
Measures:
  1. Fast-Path Static Rejection Rate (pre-flight rejection with 0 database scan)
  2. Fast-Path Static Approval Rate (pre-flight approval without database execution)
  3. Adaptive Escalation Frequency & Decision Distribution
  4. Latency and Compute Savings compared to Full Runtime Database Execution
"""

import sys
import time
import json
from pathlib import Path
import duckdb
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(force_terminal=True, legacy_windows=False)

from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.firewall.hybrid_router import HybridValidator, HybridValidationResult
from semantic_reliability.mutations.engine import MutationEngine
from semantic_reliability.assertions.registry import AssertionSuite


def profile_hybrid_router():
    corpus_dir = Path("benchmark_corpus")
    tracks = [
        ("Development Track", sorted([d for d in (corpus_dir / "dev").iterdir() if d.is_dir()])),
        ("Frozen Holdout Track", sorted([d for d in (corpus_dir / "holdout").iterdir() if d.is_dir()])),
    ]

    results_by_model = []
    total_unmutated_evaluated = 0
    total_mutations_evaluated = 0

    stats = {
        "fast_path_static_rejections": 0,
        "fast_path_static_approvals": 0,
        "escalated_to_runtime_approved": 0,
        "escalated_to_runtime_rejected": 0,
        "tier_3_latencies": [],
        "tier_4_latencies": [],
        "hybrid_latencies": [],
        "pure_runtime_latencies": [],
    }

    console.print(Panel(
        "[bold cyan]Benchmarking Adaptive Hybrid Validation Router across 14 Metric Models[/bold cyan]\n"
        "[dim]Measuring Fast-Path Static Approvals/Rejections vs. Adaptive Runtime Escalations...[/dim]",
        title="[bold green]🔬 Hybrid Router Systems Profiler[/bold green]",
        border_style="cyan"
    ))

    table = Table(title="Model-by-Model Hybrid Routing Breakdown", show_header=True, header_style="bold magenta")
    table.add_column("Track", width=12)
    table.add_column("Model ID", width=26)
    table.add_column("Valid Mut.", justify="right", width=10)
    table.add_column("Fast Static Rej", justify="right", width=15)
    table.add_column("Escalated Rej", justify="right", width=14)
    table.add_column("Hybrid Caught", justify="right", width=14)
    table.add_column("Hybrid Lat. P50", justify="right", width=15)

    for track_name, model_dirs in tracks:
        for m_dir in model_dirs:
            model_id = m_dir.name
            sql_files = list(m_dir.glob("model_*.sql"))
            csv_files = list(m_dir.glob("*.csv"))
            contract_yaml = m_dir / "contract.yaml"
            sem_yaml = m_dir / "semantic_assertions.yaml"

            if not sql_files or not csv_files or not contract_yaml.exists():
                continue

            sql_file = sql_files[0]
            csv_file = csv_files[0]
            table_name = csv_file.stem
            sql_text = sql_file.read_text(encoding="utf-8")

            compiler = MetricCompiler.from_yaml_file(contract_yaml)
            metric_def = compiler.definition
            runtime_suite = AssertionSuite.from_yaml_file(sem_yaml) if sem_yaml.exists() else AssertionSuite.get_semantic_assertion_suite()

            # Initialize DuckDB
            con = duckdb.connect(":memory:")
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{csv_file}')")

            # 1. Profile Unmutated Clean Query
            t0 = time.perf_counter()
            unmutated_res = HybridValidator.validate_hybrid(
                candidate_sql=sql_text,
                metric_def=metric_def,
                duckdb_conn=con,
                runtime_suite=runtime_suite,
            )
            stats["hybrid_latencies"].append(unmutated_res.latency_ms)
            total_unmutated_evaluated += 1

            if unmutated_res.routing_decision == "tier_3_static_approved":
                stats["fast_path_static_approvals"] += 1
            elif unmutated_res.routing_decision == "tier_4_escalated_approved":
                stats["escalated_to_runtime_approved"] += 1

            # 2. Profile Mutations
            mutator = MutationEngine(sql_text)
            mutations = mutator.generate_all_mutations()

            model_valid_count = 0
            model_fast_rej = 0
            model_esc_rej = 0
            model_latencies = []

            for mut in mutations:
                try:
                    mut_df = con.execute(mut.mutated_sql).df()
                except Exception:
                    continue  # Unexecutable mutation

                # Check if genuinely defective
                is_defective = False
                for a in runtime_suite.assertions:
                    ar = a.evaluate(con, mut.mutated_sql)
                    if not ar.passed:
                        is_defective = True
                        break

                if not is_defective:
                    continue

                model_valid_count += 1
                total_mutations_evaluated += 1

                # Pure Runtime Baseline Latency
                rt_t0 = time.perf_counter()
                for a in runtime_suite.assertions:
                    a.evaluate(con, mut.mutated_sql)
                rt_elapsed = (time.perf_counter() - rt_t0) * 1000.0
                stats["pure_runtime_latencies"].append(rt_elapsed)

                # Hybrid Router
                h_res = HybridValidator.validate_hybrid(
                    candidate_sql=mut.mutated_sql,
                    metric_def=metric_def,
                    duckdb_conn=con,
                    runtime_suite=runtime_suite,
                )
                stats["hybrid_latencies"].append(h_res.latency_ms)
                model_latencies.append(h_res.latency_ms)

                if h_res.routing_decision == "tier_3_static_rejected":
                    stats["fast_path_static_rejections"] += 1
                    model_fast_rej += 1
                elif h_res.routing_decision == "tier_4_escalated_rejected":
                    stats["escalated_to_runtime_rejected"] += 1
                    model_esc_rej += 1

            model_latencies_sorted = sorted(model_latencies)
            p50 = model_latencies_sorted[len(model_latencies_sorted)//2] if model_latencies_sorted else 0.0
            total_caught = model_fast_rej + model_esc_rej

            table.add_row(
                "Dev" if "Dev" in track_name else "Holdout",
                model_id,
                str(model_valid_count),
                str(model_fast_rej),
                str(model_esc_rej),
                f"{total_caught}/{model_valid_count}",
                f"{p50:.2f} ms",
            )

            results_by_model.append({
                "track": track_name,
                "model_id": model_id,
                "valid_mutations": model_valid_count,
                "fast_path_rejections": model_fast_rej,
                "escalated_rejections": model_esc_rej,
                "total_caught": total_caught,
                "p50_latency_ms": p50,
            })

    console.print(table)

    # Compute overall statistics
    total_evals = total_unmutated_evaluated + total_mutations_evaluated
    fast_path_total = stats["fast_path_static_approvals"] + stats["fast_path_static_rejections"]
    escalated_total = stats["escalated_to_runtime_approved"] + stats["escalated_to_runtime_rejected"]
    fast_path_rate = (fast_path_total / total_evals * 100.0) if total_evals else 0.0

    hybrid_lats = sorted(stats["hybrid_latencies"])
    pure_lats = sorted(stats["pure_runtime_latencies"])

    hybrid_p50 = hybrid_lats[len(hybrid_lats)//2] if hybrid_lats else 0.0
    pure_p50 = pure_lats[len(pure_lats)//2] if pure_lats else 0.0
    latency_reduction = ((pure_p50 - hybrid_p50) / pure_p50 * 100.0) if pure_p50 > 0 else 0.0

    summary_panel = (
        f"[bold]Total Query Evaluations Profiled:[/bold] {total_evals} (14 clean queries + {total_mutations_evaluated} valid semantic mutations)\n"
        f"--------------------------------------------------------------------------------\n"
        f"⚡ [bold green]Fast-Path Static Processing (0 DB queries, 0 bytes):[/bold green] {fast_path_total} / {total_evals} ([bold]{fast_path_rate:.1f}%[/bold])\n"
        f"   • Fast Static Approvals (Clean Queries):  {stats['fast_path_static_approvals']} / {total_unmutated_evaluated} ({stats['fast_path_static_approvals']/total_unmutated_evaluated*100.0:.1f}%)\n"
        f"   • Fast Static Rejections (Defects):       {stats['fast_path_static_rejections']} / {total_mutations_evaluated} ({stats['fast_path_static_rejections']/total_mutations_evaluated*100.0:.1f}%)\n"
        f"🔄 [bold yellow]Adaptive Runtime Escalation (Tier 4):[/bold yellow]       {escalated_total} / {total_evals} ([bold]{100.0 - fast_path_rate:.1f}%[/bold])\n"
        f"--------------------------------------------------------------------------------\n"
        f"⏱️ [bold]Latency Profile (P50):[/bold]\n"
        f"   • Pure Runtime Database Execution: [yellow]{pure_p50:.2f} ms[/yellow]\n"
        f"   • Hybrid Adaptive Router:          [bold green]{hybrid_p50:.2f} ms[/bold green] ([bold cyan]{latency_reduction:.1f}% speedup[/bold cyan])\n"
        f"💰 [bold]Database Workload Offload:[/bold]             [bold green]{fast_path_rate:.1f}%[/bold green] of queries handled with 0 warehouse compute"
    )

    console.print(Panel(summary_panel, title="[bold green]📊 Systems Tradeoff Summary[/bold green]", border_style="green"))

    # Export results
    scorecard = {
        "total_evaluations": total_evals,
        "unmutated_clean_queries": total_unmutated_evaluated,
        "valid_semantic_mutations": total_mutations_evaluated,
        "fast_path_static_total": fast_path_total,
        "fast_path_static_rate_pct": round(fast_path_rate, 2),
        "fast_path_static_approvals": stats["fast_path_static_approvals"],
        "fast_path_static_rejections": stats["fast_path_static_rejections"],
        "escalated_total": escalated_total,
        "escalated_rate_pct": round(100.0 - fast_path_rate, 2),
        "hybrid_latency_p50_ms": round(hybrid_p50, 3),
        "pure_runtime_latency_p50_ms": round(pure_p50, 3),
        "speedup_pct": round(latency_reduction, 2),
        "models": results_by_model,
    }

    out_file = Path("hybrid_escalation_scorecard.json")
    out_file.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    console.print(f"\n[green]✓ Hybrid router profiling scorecard exported to:[/green] {out_file}\n")


if __name__ == "__main__":
    profile_hybrid_router()
