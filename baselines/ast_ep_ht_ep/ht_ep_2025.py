# -*- coding: utf-8 -*-
"""Reconstruction of HT-EP from JSS 2025 (112354).

Paper: "Hierarchical tree-based algorithms for efficient expression parsing and
       test sequence generation in software models"

The implementation follows Algorithms 1-3, Eqs. (38)-(41), and Fig. 5.
Where the printed pseudocode is inconsistent with the equations/figures, the
resolution is documented in README.md and paper_reconstruction_notes.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from common import (
    AlgebraEngine,
    CHOICE,
    CONCAT,
    INTERLEAVE,
    PARALLEL,
    STAR,
    HierarchyNode,
    TraceStep,
    Value,
    atom_value,
    insert_implicit_concat,
    is_constraint_token,
    is_integer_token,
    is_operand_token,
    language_to_strings,
    matching_parentheses,
    tokenize,
    tokens_to_text,
)


@dataclass
class LayerTable:
    tokens: List[str]
    initial_depths: List[int]
    final_depths: List[int]


@dataclass
class HTEPResult:
    value: Value
    sequences: List[str]
    trace: List[TraceStep]
    tree: HierarchyNode
    layer_table: LayerTable
    operation_count: int
    tree_nodes: int
    tree_height: int


def build_layer_table_from_tokens(tokens: Sequence[str]) -> LayerTable:
    """Implement the intended effect of Eqs. (38)-(40).

    Eqs. (38)-(39) are implemented directly. Eq. (40) has boundary/index
    ambiguities in print. We resolve them using Table 2 and the four hierarchy
    shapes in Fig. 5:
      * a postfix constraint on the *entire* expression does not create a new
        proper child layer;
      * a postfix constraint on a proper atom/group raises the constrained span
        by one layer.
    This reproduces Table 2 for (a|(b||k)2)c(d|e) exactly.
    """
    n = len(tokens)
    if n == 0:
        return LayerTable([], [], [])
    open_to_close, close_to_open = matching_parentheses(tokens)

    # Eq. (38): bracket mark v(i), represented as depth before/after tokens.
    current = 0
    initial: List[int] = []
    for tok in tokens:
        if tok == "(":
            initial.append(current)  # Eq. (39): v(k-1)
            current += 1
        elif tok == ")":
            current -= 1
            if current < 0:
                raise ValueError("Unbalanced parentheses")
            initial.append(current)  # Eq. (39): v(k)
        else:
            initial.append(current)  # Eq. (39): v(k-1), numerically current
    if current != 0:
        raise ValueError("Unbalanced parentheses")

    final = list(initial)

    # Eq. (40), interpreted by constrained-span boundaries (Fig. 5).
    for j, tok in enumerate(tokens):
        if not (tok == STAR or is_integer_token(tok) or is_constraint_token(tok)):
            continue
        if j == 0:
            continue
        if tokens[j - 1] == ")":
            close_idx = j - 1
            open_idx = close_to_open.get(close_idx)
            if open_idx is None:
                raise ValueError("No matching '(' for postfix operator")
            span_start, span_end = open_idx, j
        else:
            span_start, span_end = j - 1, j

        whole_expression = (span_start == 0 and span_end == n - 1)
        if whole_expression:
            # Fig. 5(a),(c): root remains root; only already-present inner
            # parenthesis layers survive.
            continue
        for k in range(span_start, span_end + 1):
            final[k] += 1

    return LayerTable(list(tokens), initial, final)


def build_layer_table(expression: str) -> LayerTable:
    return build_layer_table_from_tokens(tokenize(expression))


def _child_spans_from_depths(depths: Sequence[int]) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    i = 0
    while i < len(depths):
        if depths[i] >= 1:
            start = i
            i += 1
            while i < len(depths) and depths[i] >= 1:
                i += 1
            spans.append((start, i - 1))
        else:
            i += 1
    return spans


def construct_hierarchy_tree_tokens(tokens: Sequence[str], depth: int = 0) -> HierarchyNode:
    table = build_layer_table_from_tokens(tokens)
    spans = _child_spans_from_depths(table.final_depths)
    # Only proper subexpressions may be children.
    spans = [sp for sp in spans if not (sp[0] == 0 and sp[1] == len(tokens) - 1)]
    node = HierarchyNode(tokens=list(tokens), depth=depth, child_spans=spans, children=[])
    for start, end in spans:
        child_tokens = list(tokens[start:end + 1])
        node.children.append(construct_hierarchy_tree_tokens(child_tokens, depth + 1))
    return node


def construct_hierarchy_tree(expression: str) -> HierarchyNode:
    return construct_hierarchy_tree_tokens(tokenize(expression), 0)


def hierarchy_node_count(node: HierarchyNode) -> int:
    return 1 + sum(hierarchy_node_count(c) for c in node.children)


def hierarchy_height(node: HierarchyNode) -> int:
    if not node.children:
        return 1
    return 1 + max(hierarchy_height(c) for c in node.children)


class HTEP2025(object):
    """Executable HT-EP baseline reconstructed from Algorithms 1-3."""

    def __init__(self, max_sequences: int = 100000, constraint_handler=None):
        self.engine = AlgebraEngine(max_sequences=max_sequences,
                                    constraint_handler=constraint_handler)
        self.trace: List[TraceStep] = []
        self._step_no = 0

    def run(self, expression: str, separator: str = "") -> HTEPResult:
        self.trace = []
        self._step_no = 0
        tokens = tokenize(expression)
        layer_table = build_layer_table_from_tokens(tokens)
        tree = construct_hierarchy_tree_tokens(tokens)
        value = self._evaluate_tree(tree)
        return HTEPResult(
            value=value,
            sequences=language_to_strings(value.language, separator=separator),
            trace=list(self.trace),
            tree=tree,
            layer_table=layer_table,
            operation_count=len(self.trace),
            tree_nodes=hierarchy_node_count(tree),
            tree_height=hierarchy_height(tree),
        )

    def _evaluate_tree(self, node: HierarchyNode) -> Value:
        # Algorithm 1 / Parsing rules 1-2: children first, then bring results
        # into the father node.
        child_values: List[Value] = []
        for child in node.children:
            child_values.append(self._evaluate_tree(child))

        local: List[Union[str, Value]] = []
        child_by_start: Dict[int, Tuple[int, Value]] = {}
        for span, val in zip(node.child_spans, child_values):
            child_by_start[span[0]] = (span[1], val)

        i = 0
        while i < len(node.tokens):
            if i in child_by_start:
                end, val = child_by_start[i]
                local.append(val)
                i = end + 1
            else:
                local.append(node.tokens[i])
                i += 1

        value = self._algebraic_operation(local, scope="layer-%d:%s" % (node.depth, node.expression_text()))
        node.result = value
        return value

    def _record(self, scope: str, operator: str, rule: str,
                before_tokens: Sequence[Union[str, Value]],
                after_tokens: Sequence[Union[str, Value]], value: Value) -> None:
        self._step_no += 1
        self.trace.append(TraceStep(
            step=self._step_no,
            algorithm="HT-EP-2025",
            scope=scope,
            operator=operator,
            rule=rule,
            before=tokens_to_text(before_tokens),
            after=tokens_to_text(after_tokens),
            result_count=len(value.language),
        ))

    def _algebraic_operation(self, tokens: Sequence[Union[str, Value]], scope: str) -> Value:
        """Executable form of Algorithm 3 + Parsing rules 3-4.

        Priority high -> low (Definition 10):
          constraint symbols; concatenation; concurrent/alternate; choice.
        Postfix star/repeat/constraint is therefore reduced first.
        Equal-priority binary operators are reduced left-to-right.
        """
        work = self._prepare_values(list(tokens))
        work = self._reduce_parentheses(work, scope)

        # Constraint symbols / postfix repetition and closure, left to right.
        i = 0
        while i < len(work):
            tok = work[i]
            if isinstance(tok, str) and (tok == STAR or is_integer_token(tok) or is_constraint_token(tok)):
                if i == 0 or not isinstance(work[i - 1], Value):
                    raise ValueError("Postfix operator %r has no operand in %s" % (tok, tokens_to_text(work)))
                operand = work[i - 1]
                before = list(work)
                if tok == STAR:
                    # Eq. (41) and Fig. 5(e) use powers 0,1,2,3.
                    value, _ = self.engine.postfix(STAR, operand, star_bound=3)
                    rule = "Eq.(41): *=0,1,2,3"
                else:
                    value, semantic_rule = self.engine.postfix(tok, operand, star_bound=3)
                    rule = "Algorithm 3: %s" % semantic_rule
                work[i - 1:i + 1] = [value]
                self._record(scope, tok, rule, before, work, value)
                i = max(0, i - 1)
            else:
                i += 1

        # Definition 10 priority, equal priority left-to-right.
        for ops, label in [
            ((CONCAT,), "concatenation priority"),
            ((INTERLEAVE, PARALLEL), "concurrent/alternate priority"),
            ((CHOICE,), "choice priority"),
        ]:
            while True:
                idx = self._find_operator(work, ops)
                if idx is None:
                    break
                if idx == 0 or idx + 1 >= len(work):
                    raise ValueError("Binary operator without two operands in %s" % tokens_to_text(work))
                left = work[idx - 1]
                right = work[idx + 1]
                if not isinstance(left, Value) or not isinstance(right, Value):
                    raise ValueError("Operator %s does not have reduced operands in %s" % (work[idx], tokens_to_text(work)))
                op = str(work[idx])
                before = list(work)
                value, semantic_rule = self.engine.binary(op, left, right)
                work[idx - 1:idx + 2] = [value]
                self._record(scope, op, "%s / %s" % (label, semantic_rule), before, work, value)

        if len(work) != 1 or not isinstance(work[0], Value):
            raise ValueError("AlgebraicOperation did not reduce %s; remaining=%r" % (tokens_to_text(tokens), work))
        return work[0]

    def _prepare_values(self, tokens: List[Union[str, Value]]) -> List[Union[str, Value]]:
        # Insert implicit concat first, then convert atomic operands to Values.
        explicit = insert_implicit_concat(tokens)
        out: List[Union[str, Value]] = []
        for tok in explicit:
            if isinstance(tok, Value):
                out.append(tok)
            elif is_operand_token(tok):
                out.append(atom_value(str(tok)))
            else:
                out.append(tok)
        return out

    def _reduce_parentheses(self, work: List[Union[str, Value]], scope: str) -> List[Union[str, Value]]:
        """Reduce any residual parentheses.

        Normally their contents correspond to already-evaluated child nodes. This
        fallback also makes the reconstruction tolerant of redundant parentheses,
        while not counting parentheses as algebraic operations.
        """
        while "(" in work or ")" in work:
            stack: List[int] = []
            reduced = False
            for i, tok in enumerate(work):
                if tok == "(":
                    stack.append(i)
                elif tok == ")":
                    if not stack:
                        raise ValueError("Unmatched ')' in %s" % tokens_to_text(work))
                    start = stack.pop()
                    inner = work[start + 1:i]
                    if len(inner) == 1 and isinstance(inner[0], Value):
                        value = inner[0]
                    else:
                        value = self._algebraic_operation(inner, scope + "/paren")
                    work[start:i + 1] = [value]
                    reduced = True
                    break
            if not reduced:
                if stack:
                    raise ValueError("Unmatched '(' in %s" % tokens_to_text(work))
                break
        return work

    @staticmethod
    def _find_operator(work: Sequence[Union[str, Value]], operators: Tuple[str, ...]) -> Optional[int]:
        for i, tok in enumerate(work):
            if isinstance(tok, str) and tok in operators:
                return i
        return None


def format_hierarchy(node: HierarchyNode, indent: str = "") -> str:
    lines = ["%s%s" % (indent, node.expression_text())]
    for child in node.children:
        lines.append(format_hierarchy(child, indent + "  "))
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Reconstructed HT-EP (JSS 2025)")
    parser.add_argument("expression")
    parser.add_argument("--separator", default="", help="Join multi-token actions with this separator")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()

    result = HTEP2025().run(args.expression, separator=args.separator)
    print("layer table tokens:", result.layer_table.tokens)
    print("initial depths    :", result.layer_table.initial_depths)
    print("final depths      :", result.layer_table.final_depths)
    print("hierarchy tree:\n" + format_hierarchy(result.tree))
    print("tree nodes:", result.tree_nodes, "height:", result.tree_height)
    print("algebraic operations:", result.operation_count)
    print("sequences (%d):" % len(result.sequences))
    for s in result.sequences:
        print(s)
    if args.trace:
        print("\nTRACE")
        for step in result.trace:
            print("%02d scope=%s op=%s rule=%s" % (step.step, step.scope, step.operator, step.rule))
            print("  before:", step.before)
            print("  after :", step.after)


if __name__ == "__main__":
    main()
