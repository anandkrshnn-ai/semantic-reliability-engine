import duckdb
from semantic_reliability.testing.mutations.engine import MutationEngine
from semantic_reliability.harness.equivalence import EquivalenceOracle

sql = open('benchmark_corpus/holdout/fintech_chargeback_rate/model_fintech_chargeback_rate.sql').read()
con = duckdb.connect(':memory:')
con.execute("CREATE TABLE settled_payments AS SELECT * FROM read_csv_auto('benchmark_corpus/holdout/fintech_chargeback_rate/settled_payments.csv')")
base_df = con.execute(sql).df()

muts = MutationEngine(sql).generate_all_mutations()
for m in muts:
    try:
        mut_df = con.execute(m.mutated_sql).df()
        is_equiv, _ = EquivalenceOracle.check_equivalence(mut_df, base_df)
    except Exception as e:
        is_equiv = False
    print(m.mutation_type, 'equiv:', is_equiv)
