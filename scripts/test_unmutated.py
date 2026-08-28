import duckdb
from pathlib import Path
import pandas as pd
from semantic_reliability.harness.baseline_ladder import BaselineLadderEvaluator
from semantic_reliability.assertions.registry import AssertionSuite

corpus = Path("benchmark_corpus")
suite = AssertionSuite.from_yaml_file("examples/assertions/realistic_dbt_suite.yaml")

print("EVALUATING UNMUTATED GROUND-TRUTH MODELS ON TIER 2:")
all_passed = True
for track in ["dev", "holdout"]:
    for m_dir in sorted((corpus / track).iterdir()):
        if not m_dir.is_dir():
            continue
        sql_file = list(m_dir.glob("model_*.sql"))[0]
        csv_file = list(m_dir.glob("*.csv"))[0]
        con = duckdb.connect(":memory:")
        con.execute(f"CREATE TABLE {csv_file.stem} AS SELECT * FROM read_csv_auto('{csv_file}')")
        sql = sql_file.read_text(encoding="utf-8")
        df = con.execute(sql).df()
        evaluator = BaselineLadderEvaluator(conn=con, suite=suite)
        res = evaluator.evaluate_tier_2_realistic_dbt(df=df, sql=sql, conn=con, suite=suite)
        print(f"{m_dir.name:<30} -> unmutated passed: {res['passed']} (checks: {res['checks_count']}, failed: {res['failed_checks_count']})")
        if not res["passed"]:
            all_passed = False
            print(f"   Reason: {res['reason']}")
            print(f"   Violations: {res['violations']}")

print(f"\nALL 14 UNMUTATED MODELS PASSED TIER 2: {all_passed}")
