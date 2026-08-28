from typing import List, Set, Optional, Tuple, Dict, Any
import sqlglot
from sqlglot import exp


class ASTNormalizer:
    """Canonicalizes SQL AST expressions to eliminate false positives from commutative or cosmetic variations."""

    @classmethod
    def normalize(cls, expression: exp.Expression) -> exp.Expression:
        """Create a deep normalized copy of an AST node."""
        node = expression.copy()
        cls._normalize_node(node)
        return node

    @classmethod
    def _normalize_node(cls, node: exp.Expression) -> None:
        """Recursively normalize node and children."""
        # 1. Unwrap redundant parentheses
        if isinstance(node, exp.Paren):
            unwrapped = cls._unwrap_parens(node)
            if unwrapped is not node:
                node.replace(unwrapped)
                cls._normalize_node(unwrapped)
                return

        # 2. Flatten and sort AND / OR commutative chains
        if isinstance(node, (exp.And, exp.Or)):
            cls._sort_boolean_chain(node)

        # 3. Canonicalize aliases
        if isinstance(node, exp.Alias):
            if isinstance(node.args.get("alias"), exp.Identifier):
                node.args["alias"].set("this", node.args["alias"].this.lower())

        # Recursively process children
        for child in list(node.iter_expressions()):
            cls._normalize_node(child)

    @classmethod
    def _unwrap_parens(cls, node: exp.Expression) -> exp.Expression:
        curr = node
        while isinstance(curr, exp.Paren) and curr.this:
            curr = curr.this
        return curr

    @classmethod
    def _sort_boolean_chain(cls, node: exp.Expression) -> None:
        """Extract all conjuncts/disjuncts in a binary boolean chain, sort them by SQL string, and rebuild."""
        is_and = isinstance(node, exp.And)
        is_or = isinstance(node, exp.Or)
        if not (is_and or is_or):
            return

        leaf_nodes: List[exp.Expression] = []

        def collect_leaves(curr: exp.Expression, target_type: type):
            curr_unwrapped = cls._unwrap_parens(curr)
            if isinstance(curr_unwrapped, target_type):
                collect_leaves(curr_unwrapped.this, target_type)
                collect_leaves(curr_unwrapped.expression, target_type)
            else:
                leaf_nodes.append(curr_unwrapped)

        target_type = exp.And if is_and else exp.Or
        collect_leaves(node, target_type)

        if len(leaf_nodes) > 1:
            sorted_leaves = sorted(leaf_nodes, key=lambda n: n.sql().strip().lower())
            combined = sorted_leaves[0]
            for next_leaf in sorted_leaves[1:]:
                combined = exp.And(this=combined, expression=next_leaf) if is_and else exp.Or(this=combined, expression=next_leaf)

            node.set("this", combined.this)
            node.set("expression", combined.expression)

    @classmethod
    def are_predicates_equivalent(cls, pred_a: Optional[exp.Expression], pred_b: Optional[exp.Expression]) -> bool:
        """Check if two WHERE/HAVING/ON predicates are logically equivalent after commutative normalization."""
        if pred_a is None and pred_b is None:
            return True
        if pred_a is None or pred_b is None:
            return False

        norm_a = cls.normalize(pred_a)
        norm_b = cls.normalize(pred_b)

        # Normalize SQL comparison by stripping outer whitespace/parens
        sql_a = norm_a.sql().strip().lower()
        sql_b = norm_b.sql().strip().lower()

        return sql_a == sql_b
