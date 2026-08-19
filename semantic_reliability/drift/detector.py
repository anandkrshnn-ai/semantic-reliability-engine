from typing import List, Optional, Tuple, Dict, Any
import sqlglot
from sqlglot import exp

from semantic_reliability.drift.rules import SemanticDrift, DriftSeverity, DriftType
from semantic_reliability.drift.normalizer import ASTNormalizer


class SemanticDriftDetector:
    """Analyzes AST-level structural and semantic changes between baseline and candidate SQL."""

    @classmethod
    def analyze(
        cls,
        original_sql: str,
        candidate_sql: str,
        dialect: Optional[str] = None,
    ) -> List[SemanticDrift]:
        """Perform comprehensive semantic drift inspection across relational algebra components."""
        orig_ast = sqlglot.parse_one(original_sql, read=dialect)
        cand_ast = sqlglot.parse_one(candidate_sql, read=dialect)

        drifts: List[SemanticDrift] = []

        # 1. Population Logic Analysis (WHERE Clause)
        drifts.extend(cls._analyze_where_clause(orig_ast, cand_ast))

        # 2. Mathematical Aggregations (SELECT Clause)
        drifts.extend(cls._analyze_aggregations(orig_ast, cand_ast))

        # 3. Join Topology & Predicates (JOIN Clauses)
        drifts.extend(cls._analyze_joins(orig_ast, cand_ast))

        # 4. Grouping & Reporting Grain (GROUP BY Clause)
        drifts.extend(cls._analyze_group_by(orig_ast, cand_ast))

        # 5. Null-Handling & Coalesce Defaults
        drifts.extend(cls._analyze_null_handling(orig_ast, cand_ast))

        # 6. Post-Aggregation Filters (HAVING Clause)
        drifts.extend(cls._analyze_having_clause(orig_ast, cand_ast))

        # 7. Source Tables
        drifts.extend(cls._analyze_tables(orig_ast, cand_ast))

        return drifts

    @classmethod
    def _analyze_where_clause(cls, orig: exp.Expression, cand: exp.Expression) -> List[SemanticDrift]:
        drifts = []
        orig_where = orig.find(exp.Where)
        cand_where = cand.find(exp.Where)

        if orig_where and not cand_where:
            drifts.append(SemanticDrift(
                severity=DriftSeverity.FATAL,
                drift_type=DriftType.FILTER_REMOVAL,
                component="WHERE Clause (Population Definition)",
                summary="All filter constraints were dropped.",
                details="Baseline had WHERE constraints which were completely removed in candidate SQL.",
                business_impact="Unfiltered data is being aggregated. Massive metric inflation expected.",
                original_snippet=orig_where.sql(pretty=True),
                candidate_snippet="[NONE]",
                remediation="Restore population constraints or create a dedicated unfiltered model.",
            ))
        elif not orig_where and cand_where:
            drifts.append(SemanticDrift(
                severity=DriftSeverity.HIGH,
                drift_type=DriftType.FILTER_ADDITION,
                component="WHERE Clause (Population Definition)",
                summary="New filter constraints introduced to previously unfiltered model.",
                details=f"New filters added:\n  {cand_where.sql(pretty=True)}",
                business_impact="Population restricted. Downstream metrics will reflect lower volumes than baseline.",
                original_snippet="[NONE]",
                candidate_snippet=cand_where.sql(pretty=True),
                remediation="Confirm if filtering is intentional and aligned with business definition.",
            ))
        elif orig_where and cand_where:
            if not ASTNormalizer.are_predicates_equivalent(orig_where.this, cand_where.this):
                drifts.append(SemanticDrift(
                    severity=DriftSeverity.CRITICAL,
                    drift_type=DriftType.SEMANTIC_LOGIC_SHIFT,
                    component="WHERE Clause (Population Definition)",
                    summary="Filter conditions modified.",
                    details=f"Baseline filter:\n  {orig_where.sql()}\nCandidate filter:\n  {cand_where.sql()}",
                    business_impact="The population criteria has changed. Dashboards will silently include/exclude different entities.",
                    original_snippet=orig_where.sql(pretty=True),
                    candidate_snippet=cand_where.sql(pretty=True),
                    remediation="Verify whether logical criteria change is an approved business metric update.",
                ))
        return drifts

    @classmethod
    def _analyze_aggregations(cls, orig: exp.Expression, cand: exp.Expression) -> List[SemanticDrift]:
        drifts = []
        orig_aggs = list(orig.find_all(exp.AggFunc))
        cand_aggs = list(cand.find_all(exp.AggFunc))

        orig_agg_types = [type(f).__name__ for f in orig_aggs]
        cand_agg_types = [type(f).__name__ for f in cand_aggs]

        if sorted(orig_agg_types) != sorted(cand_agg_types):
            drifts.append(SemanticDrift(
                severity=DriftSeverity.HIGH,
                drift_type=DriftType.AGGREGATION_FUNCTION_SHIFT,
                component="SELECT Clause (Mathematical Aggregation)",
                summary="Aggregation functions altered (e.g. SUM vs AVG vs COUNT).",
                details=f"Baseline functions: {orig_agg_types}\nCandidate functions: {cand_agg_types}",
                business_impact="The mathematical computation of the metric has changed.",
                original_snippet=", ".join([f.sql() for f in orig_aggs]),
                candidate_snippet=", ".join([f.sql() for f in cand_aggs]),
                remediation="Ensure mathematical formula conforms to the canonical business metric definition.",
            ))

        # Check expressions inside aggregations
        orig_agg_sqls = sorted([f.sql() for f in orig_aggs])
        cand_agg_sqls = sorted([f.sql() for f in cand_aggs])
        if sorted(orig_agg_types) == sorted(cand_agg_types) and orig_agg_sqls != cand_agg_sqls:
            drifts.append(SemanticDrift(
                severity=DriftSeverity.HIGH,
                drift_type=DriftType.AGGREGATION_EXPRESSION_SHIFT,
                component="SELECT Clause (Mathematical Aggregation Payload)",
                summary="Expression evaluated inside aggregation function has shifted.",
                details=f"Baseline agg expressions:\n  {orig_agg_sqls}\nCandidate agg expressions:\n  {cand_agg_sqls}",
                business_impact="Underlying calculation components modified (e.g., CASE statements or amounts).",
                original_snippet="\n".join(orig_agg_sqls),
                candidate_snippet="\n".join(cand_agg_sqls),
                remediation="Review arithmetic operands and case conditions inside aggregation.",
            ))

        return drifts

    @classmethod
    def _analyze_joins(cls, orig: exp.Expression, cand: exp.Expression) -> List[SemanticDrift]:
        drifts = []
        orig_joins = list(orig.find_all(exp.Join))
        cand_joins = list(cand.find_all(exp.Join))

        if len(orig_joins) != len(cand_joins):
            drifts.append(SemanticDrift(
                severity=DriftSeverity.HIGH,
                drift_type=DriftType.JOIN_TYPE_SHIFT,
                component="JOIN Topology",
                summary="Join count altered.",
                details=f"Baseline has {len(orig_joins)} joins; candidate has {len(cand_joins)} joins.",
                business_impact="Table relationships changed; potential fan-out or record loss.",
                remediation="Verify join cardinality.",
            ))

        # Check for missing ON conditions (Cartesian explosions)
        for cj in cand_joins:
            if not cj.args.get("on") and not cj.args.get("using") and not cj.kind == "CROSS":
                drifts.append(SemanticDrift(
                    severity=DriftSeverity.FATAL,
                    drift_type=DriftType.JOIN_PREDICATE_MUTATION,
                    component="JOIN Predicate",
                    summary="Join predicate missing on non-cross join.",
                    details=f"Join without ON/USING clause: {cj.sql()}",
                    business_impact="Cartesian product explosion resulting in duplicate metric counting.",
                    candidate_snippet=cj.sql(),
                    remediation="Add explicit ON clause to join.",
                ))

        return drifts

    @classmethod
    def _analyze_group_by(cls, orig: exp.Expression, cand: exp.Expression) -> List[SemanticDrift]:
        drifts = []
        orig_group = orig.find(exp.Group)
        cand_group = cand.find(exp.Group)

        orig_exprs = [e.sql() for e in orig_group.expressions] if orig_group else []
        cand_exprs = [e.sql() for e in cand_group.expressions] if cand_group else []

        if sorted(orig_exprs) != sorted(cand_exprs):
            drifts.append(SemanticDrift(
                severity=DriftSeverity.CRITICAL,
                drift_type=DriftType.GRAIN_DRIFT,
                component="GROUP BY (Reporting Grain)",
                summary="Aggregation grain dimensions shifted.",
                details=f"Baseline grain: {orig_exprs}\nCandidate grain: {cand_exprs}",
                business_impact="Output dataset grain changed. Downstream dimensional models and BI will break.",
                original_snippet=", ".join(orig_exprs) if orig_exprs else "[NONE]",
                candidate_snippet=", ".join(cand_exprs) if cand_exprs else "[NONE]",
                remediation="Restore required grouping dimensions.",
            ))
        return drifts

    @classmethod
    def _analyze_null_handling(cls, orig: exp.Expression, cand: exp.Expression) -> List[SemanticDrift]:
        drifts = []
        orig_coalesce = list(orig.find_all(exp.Coalesce))
        cand_coalesce = list(cand.find_all(exp.Coalesce))

        if len(orig_coalesce) > len(cand_coalesce):
            drifts.append(SemanticDrift(
                severity=DriftSeverity.MEDIUM,
                drift_type=DriftType.NULL_HANDLING_DRIFT,
                component="COALESCE / Null Handling",
                summary="COALESCE default values removed.",
                details=f"Baseline contained {len(orig_coalesce)} COALESCE calls; candidate has {len(cand_coalesce)}.",
                business_impact="NULL values may propagate to calculations and result in unexpected NULL aggregates.",
                remediation="Ensure NULL-safe fallbacks are retained.",
            ))
        return drifts

    @classmethod
    def _analyze_having_clause(cls, orig: exp.Expression, cand: exp.Expression) -> List[SemanticDrift]:
        drifts = []
        orig_having = orig.find(exp.Having)
        cand_having = cand.find(exp.Having)

        if (orig_having and not cand_having) or (not orig_having and cand_having) or (
            orig_having and cand_having and orig_having.sql() != cand_having.sql()
        ):
            drifts.append(SemanticDrift(
                severity=DriftSeverity.HIGH,
                drift_type=DriftType.HAVING_FILTER_SHIFT,
                component="HAVING Clause",
                summary="Post-aggregation filter altered.",
                details=f"Baseline: {orig_having.sql() if orig_having else '[NONE]'}\nCandidate: {cand_having.sql() if cand_having else '[NONE]'}",
                business_impact="Post-aggregation group retention altered.",
                remediation="Confirm post-aggregation business thresholds.",
            ))
        return drifts

    @classmethod
    def _analyze_tables(cls, orig: exp.Expression, cand: exp.Expression) -> List[SemanticDrift]:
        drifts = []
        orig_tables = sorted(list(set(t.name for t in orig.find_all(exp.Table))))
        cand_tables = sorted(list(set(t.name for t in cand.find_all(exp.Table))))

        if orig_tables != cand_tables:
            drifts.append(SemanticDrift(
                severity=DriftSeverity.HIGH,
                drift_type=DriftType.TABLE_TARGET_SHIFT,
                component="Source Tables (FROM / JOIN)",
                summary="Source table lineage has changed.",
                details=f"Baseline sources: {orig_tables}\nCandidate sources: {cand_tables}",
                business_impact="Upstream dependency shifts; metric may read from staging or deprecated tables.",
                original_snippet=", ".join(orig_tables),
                candidate_snippet=", ".join(cand_tables),
                remediation="Verify upstream model lineage and table sources.",
            ))
        return drifts
