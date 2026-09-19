import duckdb
from semantic_reliability.testing.mutations.engine import MutationEngine
from semantic_reliability.harness.equivalence import EquivalenceOracle

sql = open('benchmark_corpus/holdout/fintech_chargeback_rate/model_fintech_chargeback_rate.sql').read()
con = duckdb.connect(':memory:')
con.execute("CREATE TABLE settled_payments AS SELECT * FROM read_csv_auto('benchmark_corpus/holdout/fintech_chargeback_rate/settled_payments.csv')")
base_df = con.execute(sql).df()
print('Base DF:')
print(base_df)

muts = MutationEngine(sql).generate_all_mutations()
for m in muts:
    if m.mutation_type.name == 'COALESCE_BYPASS':
        print('Mutated SQL:', m.mutated_sql)
        mut_df = con.execute(m.mutated_sql).df()
        print('Mut DF:')
        print(mut_df)
