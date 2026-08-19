from typing import List, Optional, Tuple, Dict, Any
import sqlglot
from sqlglot import exp

from semantic_reliability.mutations.mutators import MutationType, MutationResult


class MutationEngine:
    """Injects precise AST-level logical mutations into SQL models (Chaos Engineering for Data)."""

    def __init__(self, base_sql: str, dialect: Optional[str] = None):
        self.base_sql = base_sql
        self.dialect = dialect
        self.ast = sqlglot.parse_one(base_sql, read=dialect)

    def generate_all_mutations(self) -> List[MutationResult]:
        """Run all mutation generators and return list of valid mutated ASTs."""
        mutations: List[MutationResult] = []

        m_filter = self.inject_filter_drop()
        if m_filter:
            mutations.append(m_filter)

        m_bound = self.inject_boundary_shift()
        if m_bound:
            mutations.append(m_bound)

        m_agg = self.inject_aggregation_swap()
        if m_agg:
            mutations.append(m_agg)

        m_dist = self.inject_distinct_drop()
        if m_dist:
            mutations.append(m_dist)

        m_join = self.inject_join_predicate_drop()
        if m_join:
            mutations.append(m_join)

        m_grain = self.inject_grain_drop()
        if m_grain:
            mutations.append(m_grain)

        m_coalesce = self.inject_coalesce_bypass()
        if m_coalesce:
            mutations.append(m_coalesce)

        m_math = self.inject_math_operator_invert()
        if m_math:
            mutations.append(m_math)

        return mutations

    def inject_filter_drop(self) -> Optional[MutationResult]:
        """Simulate accidental deletion of an AND filter conjunct in WHERE."""
        ast_copy = self.ast.copy()
        where = ast_copy.find(exp.Where)
        if not where:
            return None

        and_expr = where.find(exp.And)
        if and_expr:
            # Replace AND node with its left expression, dropping right condition
            and_expr.replace(and_expr.this)
            return MutationResult(
                mutation_type=MutationType.FILTER_DROP,
                description="Dropped right conjunct of AND condition in WHERE clause.",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="WHERE AND Conjunct",
                mutation_category="Population Filtering",
            )
        else:
            # Drop entire WHERE clause
            where.pop()
            return MutationResult(
                mutation_type=MutationType.FILTER_DROP,
                description="Completely removed WHERE clause filter.",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="WHERE Clause",
                mutation_category="Population Filtering",
            )

    def inject_boundary_shift(self) -> Optional[MutationResult]:
        """Mutate inequality operators (> to >=, < to <=, = to !=)."""
        ast_copy = self.ast.copy()

        gt = ast_copy.find(exp.GT)
        if gt:
            gte = exp.GTE(this=gt.this, expression=gt.expression)
            gt.replace(gte)
            return MutationResult(
                mutation_type=MutationType.BOUNDARY_SHIFT,
                description="Mutated '>' boundary comparison to '>='.",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="GT Operator",
                mutation_category="Boundary Conditions",
            )

        lt = ast_copy.find(exp.LT)
        if lt:
            lte = exp.LTE(this=lt.this, expression=lt.expression)
            lt.replace(lte)
            return MutationResult(
                mutation_type=MutationType.BOUNDARY_SHIFT,
                description="Mutated '<' boundary comparison to '<='.",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="LT Operator",
                mutation_category="Boundary Conditions",
            )

        eq = ast_copy.find(exp.EQ)
        if eq:
            neq = exp.NEQ(this=eq.this, expression=eq.expression)
            eq.replace(neq)
            return MutationResult(
                mutation_type=MutationType.BOUNDARY_SHIFT,
                description="Mutated '=' equality comparison to '!='.",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="EQ Operator",
                mutation_category="Boundary Conditions",
            )

        return None

    def inject_aggregation_swap(self) -> Optional[MutationResult]:
        """Simulate mathematical calculation error (e.g. SUM -> AVG, or AVG -> SUM)."""
        ast_copy = self.ast.copy()

        sum_func = ast_copy.find(exp.Sum)
        if sum_func:
            avg_func = exp.Avg(this=sum_func.this)
            sum_func.replace(avg_func)
            return MutationResult(
                mutation_type=MutationType.AGGREGATION_SWAP,
                description="Swapped SUM() aggregation function to AVG().",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="SUM Aggregation",
                mutation_category="Mathematical Calculation",
            )

        avg_func = ast_copy.find(exp.Avg)
        if avg_func:
            sum_func = exp.Sum(this=avg_func.this)
            avg_func.replace(sum_func)
            return MutationResult(
                mutation_type=MutationType.AGGREGATION_SWAP,
                description="Swapped AVG() aggregation function to SUM().",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="AVG Aggregation",
                mutation_category="Mathematical Calculation",
            )

        count_func = ast_copy.find(exp.Count)
        if count_func:
            sum_func = exp.Sum(this=count_func.this)
            count_func.replace(sum_func)
            return MutationResult(
                mutation_type=MutationType.AGGREGATION_SWAP,
                description="Swapped COUNT() aggregation function to SUM().",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="COUNT Aggregation",
                mutation_category="Mathematical Calculation",
            )

        return None

    def inject_distinct_drop(self) -> Optional[MutationResult]:
        """Simulate dropping DISTINCT inside COUNT(DISTINCT col)."""
        ast_copy = self.ast.copy()
        for count_node in ast_copy.find_all(exp.Count):
            if count_node.args.get("distinct"):
                count_node.args["distinct"] = False
                return MutationResult(
                    mutation_type=MutationType.DISTINCT_DROP,
                    description="Removed DISTINCT modifier from COUNT(DISTINCT) calculation.",
                    original_sql=self.base_sql,
                    mutated_sql=ast_copy.sql(pretty=True),
                    target_node="COUNT DISTINCT Modifier",
                    mutation_category="Mathematical Calculation",
                )
        return None

    def inject_join_predicate_drop(self) -> Optional[MutationResult]:
        """Simulate accidental Cartesian explosion by dropping ON condition in a JOIN."""
        ast_copy = self.ast.copy()
        for join in ast_copy.find_all(exp.Join):
            if join.args.get("on"):
                join.args["on"] = None
                return MutationResult(
                    mutation_type=MutationType.JOIN_PREDICATE_DROP,
                    description="Stripped ON predicate from JOIN clause (Cartesian product risk).",
                    original_sql=self.base_sql,
                    mutated_sql=ast_copy.sql(pretty=True),
                    target_node="JOIN ON Predicate",
                    mutation_category="Join Cardinality",
                )
        return None

    def inject_grain_drop(self) -> Optional[MutationResult]:
        """Simulate grain over-aggregation by dropping a column from GROUP BY."""
        ast_copy = self.ast.copy()
        group = ast_copy.find(exp.Group)
        if group and len(group.expressions) > 1:
            dropped = group.expressions.pop()
            return MutationResult(
                mutation_type=MutationType.GRAIN_DROP,
                description=f"Dropped column '{dropped.sql()}' from GROUP BY clause.",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="GROUP BY Expressions",
                mutation_category="Reporting Grain",
            )
        return None

    def inject_coalesce_bypass(self) -> Optional[MutationResult]:
        """Simulate NULL propagation bug by removing COALESCE default fallback."""
        ast_copy = self.ast.copy()
        coalesce = ast_copy.find(exp.Coalesce)
        if coalesce and len(coalesce.expressions) > 0:
            # Replace COALESCE(col, 0) with just col (the first expression)
            coalesce.replace(coalesce.expressions[0])
            return MutationResult(
                mutation_type=MutationType.COALESCE_BYPASS,
                description="Bypassed COALESCE default value, exposing query to NULL propagation.",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="COALESCE Node",
                mutation_category="Null Safety",
            )
        return None

    def inject_math_operator_invert(self) -> Optional[MutationResult]:
        """Invert arithmetic operator (+ to -, or - to +)."""
        ast_copy = self.ast.copy()
        sub = ast_copy.find(exp.Sub)
        if sub:
            add = exp.Add(this=sub.this, expression=sub.expression)
            sub.replace(add)
            return MutationResult(
                mutation_type=MutationType.MATH_OPERATOR_INVERT,
                description="Inverted subtraction (-) operand to addition (+).",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="Subtraction Operator",
                mutation_category="Arithmetic Logic",
            )

        add = ast_copy.find(exp.Add)
        if add:
            sub = exp.Sub(this=add.this, expression=add.expression)
            add.replace(sub)
            return MutationResult(
                mutation_type=MutationType.MATH_OPERATOR_INVERT,
                description="Inverted addition (+) operand to subtraction (-).",
                original_sql=self.base_sql,
                mutated_sql=ast_copy.sql(pretty=True),
                target_node="Addition Operator",
                mutation_category="Arithmetic Logic",
            )
        return None
