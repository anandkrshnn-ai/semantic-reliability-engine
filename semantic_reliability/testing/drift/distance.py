from typing import Optional, Set

import sqlglot
from sqlglot import exp

from semantic_reliability.testing.drift.normalizer import ASTNormalizer

_COSMETIC_NODES = (exp.Identifier, exp.Alias, exp.TableAlias, exp.Paren)


def _node_signature(node: exp.Expression) -> Optional[str]:
    if isinstance(node, _COSMETIC_NODES):
        return None
    if isinstance(node, exp.Star):
        return "star"
    if isinstance(node, exp.Column):
        if isinstance(node.this, exp.Star):
            return "star"
        return f"column:{node.name.lower()}"
    if isinstance(node, exp.Table):
        return f"table:{node.name.lower()}"
    if isinstance(node, exp.Literal):
        if node.is_string:
            return f"literal:str:{node.this}"
        return f"literal:num:{str(node.this).strip().lower()}"
    if isinstance(node, exp.Boolean):
        return f"boolean:{bool(node.this)}"
    if isinstance(node, exp.Null):
        return "null"
    return f"node:{type(node).__name__}"


def ast_node_signatures(sql: str, dialect: Optional[str] = "duckdb") -> Set[str]:
    """Extract the normalized AST node set N(sql) used by the D_sem formula."""
    ast = sqlglot.parse_one(sql, read=dialect)
    normalized = ASTNormalizer.normalize(ast)
    signatures: Set[str] = set()
    for node in normalized.walk():
        sig = _node_signature(node)
        if sig is not None:
            signatures.add(sig)
    return signatures


def semantic_drift_distance(
    candidate_sql: str,
    contract_sql: str,
    candidate_dialect: Optional[str] = "duckdb",
    contract_dialect: Optional[str] = "duckdb",
) -> float:
    """
    D_sem = 1 - |N_agent & N_contract| / |N_agent | N_contract|

    Deterministic AST-set Jaccard distance in [0, 1] between a candidate query
    and the canonical metric contract query.
    """
    candidate_nodes = ast_node_signatures(candidate_sql, candidate_dialect)
    contract_nodes = ast_node_signatures(contract_sql, contract_dialect)
    union = candidate_nodes | contract_nodes
    if not union:
        return 0.0
    intersection = candidate_nodes & contract_nodes
    return round(1.0 - (len(intersection) / len(union)), 6)
