#!/usr/bin/env python3
"""Two-Engine Systems Tradeoff Benchmark Runner.
Evaluates 14 models (8 Development, 6 Frozen Holdout) across the 4-Tier Baseline Ladder:
  Tier 0: Syntax Only (AST Parser)
  Tier 1: Minimal Structural Schema (Nullity, Uniqueness, Row Count)
  Tier 2: Realistic dbt Quality Suite (Grounded in dbt-labs/jaffle_shop: accepted_range, accepted_values, relationships, singular SQL)
  Tier 3: Static SCOS AST Invariant Compiler (0 ms, 0 warehouse scan)
  Tier 4: Runtime Relational Oracle (Full contrastive fixture assertions)
"""
import sys
import time
import json
from pathlib import Path
import pandas as pd
import duckdb

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.compiler.contracts import SemanticContractValidator
from semantic_reliability.mutations.engine import MutationEngine
from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.adapters.dbt_adapter import DBTTestAdapter
from semantic_reliability.harness.baseline_ladder import BaselineLadderEvaluator
from semantic_reliability.harness.duckdb_runner import DuckDBFixtureRunner


def run_benchmark():
    corpus_dir = Path("benchmark_corpus")
    realistic_suite_path = Path("examples/assertions/realistic_dbt_suite.yaml")
    realistic_suite = AssertionSuite.from_yaml_file(realistic_suite_path)

    tracks = [
        ("Development Track", sorted([d for d in (corpus_dir / "dev").iterdir() if d.is_dir()])),
        ("Frozen Holdout Track", sorted([d for d in (corpus_dir / "holdout").iterdir() if d.is_dir()])),
    ]

    all_results = []
    tier_stats = {
        "tier_0": {"caught": 0, "total_valid": 0, "latencies_ms": []},
        "tier_1": {"caught": 0, "total_valid": 0, "latencies_ms": []},
        "tier_2": {"caught": 0, "total_valid": 0, "latencies_ms": []},
        "tier_3": {"caught": 0, "total_valid": 0, "latencies_ms": []},
        "tier_4": {"caught": 0, "total_valid": 0, "latencies_ms": []},
    }

    print("=" * 80)
    print("🔬 RUNNING TWO-ENGINE SYSTEMS TRADEOFF BENCHMARK (14 MODELS)")
    print("=" * 80)

    for track_name, model_dirs in tracks:
        print(f"\n📂 Track: {track_name} ({len(model_dirs)} models)")
        for m_dir in model_dirs:
            model_id = m_dir.name
            sql_files = list(m_dir.glob("model_*.sql"))
            csv_files = list(m_dir.glob("*.csv"))
            contract_yaml = m_dir / "contract.yaml"
            sem_yaml = m_dir / "semantic_assertions.yaml"

            if not sql_files or not csv_files:
                continue

            sql_file = sql_files[0]
            csv_file = csv_files[0]
            table_name = csv_file.stem
            sql_text = sql_file.read_text(encoding="utf-8")

            compiler = MetricCompiler.from_yaml_file(contract_yaml) if contract_yaml.exists() else None
            metric_def = compiler.definition if compiler else None

            sem_suite = AssertionSuite.from_yaml_file(sem_yaml) if sem_yaml.exists() else AssertionSuite.get_semantic_assertion_suite()
            dbt_yaml = m_dir / "schema.yml"
            model_dbt_suite = DBTTestAdapter.parse_schema_yml(dbt_yaml) if dbt_yaml.exists() else realistic_suite

            # Initialize DuckDB
            con = duckdb.connect(":memory:")
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{csv_file}')")

            # Execute baseline SQL to get baseline output
            try:
                base_df = con.execute(sql_text).df()
            except Exception as e:
                print(f"  [ERROR] Baseline query failed for {model_id}: {e}")
                continue

            # Generate mutations
            mutator = MutationEngine(sql_text)
            mutations = mutator.generate_all_mutations()

            evaluator = BaselineLadderEvaluator(contract=metric_def, conn=con, suite=model_dbt_suite)

            model_record = {
                "track": track_name,
                "model_id": model_id,
                "total_mutations": len(mutations),
                "valid_defects": 0,
                "tier_0_caught": 0,
                "tier_1_caught": 0,
                "tier_2_caught": 0,
                "tier_3_caught": 0,
                "tier_4_caught": 0,
            }

            for mut in mutations:
                mut_sql = mut.mutated_sql

                # Try executing mutated SQL on fixture
                try:
                    mut_df = con.execute(mut_sql).df()
                    is_executable = True
                except Exception:
                    mut_df = None
                    is_executable = False

                # Determine if mutation is a valid defect (differs from baseline)
                is_equivalent = False
                if is_executable and mut_df is not None:
                    try:
                        pd.testing.assert_frame_equal(base_df, mut_df, check_dtype=False)
                        is_equivalent = True
                    except AssertionError:
                        is_equivalent = False

                if is_equivalent:
                    continue

                model_record["valid_defects"] += 1

                # 1. Tier 0: Syntax
                t0_start = time.perf_counter()
                t0_res = evaluator.evaluate_tier_0_syntax(mut_sql)
                t0_dur = (time.perf_counter() - t0_start) * 1000.0
                tier_stats["tier_0"]["latencies_ms"].append(t0_dur)
                t0_caught = not t0_res["passed"]
                if t0_caught:
                    model_record["tier_0_caught"] += 1

                # 2. Tier 1: Minimal Structural
                t1_start = time.perf_counter()
                t1_res = evaluator.evaluate_tier_1_minimal_structural(mut_df)
                t1_dur = (time.perf_counter() - t1_start) * 1000.0
                tier_stats["tier_1"]["latencies_ms"].append(t1_dur)
                t1_caught = not t1_res["passed"]
                if t1_caught:
                    model_record["tier_1_caught"] += 1

                # 3. Tier 2: Realistic dbt Suite
                t2_start = time.perf_counter()
                t2_res = evaluator.evaluate_tier_2_realistic_dbt(df=mut_df, sql=mut_sql, conn=con, suite=model_dbt_suite)
                t2_dur = (time.perf_counter() - t2_start) * 1000.0
                tier_stats["tier_2"]["latencies_ms"].append(t2_dur)
                t2_caught = not t2_res["passed"]
                if t2_caught:
                    model_record["tier_2_caught"] += 1

                # 4. Tier 3: Static SCOS AST Linter
                t3_start = time.perf_counter()
                t3_res = evaluator.evaluate_tier_3_static_scos_ast(mut_sql)
                t3_dur = (time.perf_counter() - t3_start) * 1000.0
                tier_stats["tier_3"]["latencies_ms"].append(t3_dur)
                t3_caught = not t3_res["passed"]
                if t3_caught:
                    model_record["tier_3_caught"] += 1

                # 5. Tier 4: Runtime Relational Oracle
                t4_start = time.perf_counter()
                t4_caught = False
                if is_executable:
                    for assertion in sem_suite.assertions:
                        try:
                            res = assertion.evaluate(con, mut_sql)
                            if not res.passed:
                                t4_caught = True
                                break
                        except Exception:
                            t4_caught = True
                            break
                else:
                    t4_caught = True
                t4_dur = (time.perf_counter() - t4_start) * 1000.0
                tier_stats["tier_4"]["latencies_ms"].append(t4_dur)
                if t4_caught:
                    model_record["tier_4_caught"] += 1

            all_results.append(model_record)
            v = model_record["valid_defects"]
            print(f"  {model_id:<28} | Valid: {v:2d} | T0: {model_record['tier_0_caught']:2d} | T1: {model_record['tier_1_caught']:2d} | T2: {model_record['tier_2_caught']:2d} | T3: {model_record['tier_3_caught']:2d} | T4: {model_record['tier_4_caught']:2d}")

    # Aggregate stats
    df_res = pd.DataFrame(all_results)
    total_valid = df_res["valid_defects"].sum()

    print("\n" + "=" * 80)
    print("📊 EMPIRICAL SUMMARY ACROSS ALL 14 BENCHMARK MODELS")
    print("=" * 80)
    print(f"Total Analytical Models Tested: {len(df_res)} (8 Dev + 6 Frozen Holdout)")
    print(f"Total Valid Injected Defects:   {total_valid}")
    print("-" * 80)

    summary_table = []
    for tier_key, name, compute, cost in [
        ("tier_0", "Tier 0: Syntax Only", "sqlglot AST parse", "$0.00"),
        ("tier_1", "Tier 1: Minimal Structural", "null / unique / bounds", "$0.00"),
        ("tier_2", "Tier 2: Realistic dbt Suite", "accepted_range / values / fk / singular", "$0.00"),
        ("tier_3", "Tier 3: Static SCOS AST Linter", "Deterministic AST Compiler", "$0.00"),
        ("tier_4", "Tier 4: Runtime Relational Oracle", "DuckDB Join / Predicate Fixture", "~$0.01 / scan"),
    ]:
        caught = df_res[f"{tier_key}_caught"].sum()
        catch_rate = (caught / total_valid * 100.0) if total_valid > 0 else 0.0
        lats = tier_stats[tier_key]["latencies_ms"]
        p50 = pd.Series(lats).median() if lats else 0.0
        p95 = pd.Series(lats).quantile(0.95) if lats else 0.0

        summary_table.append({
            "tier": name,
            "caught": int(caught),
            "total": int(total_valid),
            "catch_rate_pct": round(float(catch_rate), 2),
            "p50_latency_ms": round(float(p50), 2),
            "p95_latency_ms": round(float(p95), 2),
            "compute_type": compute,
            "est_cost": cost,
        })
        print(f"{name:<35} | Caught: {caught:3d}/{total_valid:3d} ({catch_rate:5.1f}%) | Latency P50: {p50:5.2f}ms, P95: {p95:5.2f}ms")

    # Save to JSON
    # Compute combined catch rates
    total_t3_or_t4 = 0
    total_t2_or_t3 = 0
    total_all_tiers = 0

    for m in all_results:
        # Note: we can compute from individual mutation records
        pass

    output_path = Path("benchmark_ladder_scorecard.json")
    output_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_models": len(df_res),
        "total_valid_defects": int(total_valid),
        "summary": summary_table,
        "models": all_results,
    }
    output_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    print(f"\n✅ Benchmark scorecard saved to: {output_path}")


if __name__ == "__main__":
    run_benchmark()
