from __future__ import annotations

from typing import Optional

from ._segment import ArgMaxLeftmostSegmentTree, NEG_INF
from .model import AstNode, NTable
from .spec import Fixity, OperatorSpec, default_operator_spec


class AstBuilder:
    """O(n log n) MRC reconstruction with leftmost-maximum tie-breaking."""

    __slots__ = ("spec",)

    def __init__(self, spec: Optional[OperatorSpec] = None) -> None:
        self.spec = spec or default_operator_spec()

    def build(self, table: NTable) -> AstNode:
        if not table.tokens:
            raise ValueError("Cannot reconstruct an empty N-Table")
        rmq = ArgMaxLeftmostSegmentTree(table.values)
        return self._build_segment(table, rmq, 0, len(table.tokens) - 1)

    def _build_segment(
        self,
        table: NTable,
        rmq: ArgMaxLeftmostSegmentTree,
        lo: int,
        hi: int,
    ) -> AstNode:
        if lo > hi:
            raise ValueError("Malformed expression: empty operand region")

        if lo == hi:
            if table.values[lo] is not None:
                raise ValueError("Malformed expression: operator without operand")
            return AstNode(table.tokens[lo])

        max_value, p = rmq.query(lo, hi)
        if max_value == NEG_INF:
            # The paper's normalization contract requires this region to be one atomic operand.
            if lo != hi:
                raise ValueError(
                    "Operand region contains multiple tokens but no operator; "
                    "normalization should insert explicit concatenation"
                )
            return AstNode(table.tokens[lo])

        op = table.tokens[p]
        if op not in self.spec:
            raise ValueError(f"Numeric entry at non-operator token {op!r}")

        meta = self.spec[op]

        if meta.arity == 2:
            if p == lo or p == hi:
                raise ValueError(f"Binary operator {op!r} lacks an operand")
            left = self._build_segment(table, rmq, lo, p - 1)
            right = self._build_segment(table, rmq, p + 1, hi)
            return AstNode(op, left, right)

        if meta.fixity is Fixity.POSTFIX:
            if p == lo:
                raise ValueError(f"Postfix operator {op!r} lacks a left operand")
            if p != hi:
                raise ValueError(
                    f"Postfix unary operator {op!r} must terminate its recursive segment"
                )
            left = self._build_segment(table, rmq, lo, p - 1)
            return AstNode(op, left, None)

        if meta.fixity is Fixity.PREFIX:
            if p == hi:
                raise ValueError(f"Prefix operator {op!r} lacks a right operand")
            if p != lo:
                raise ValueError(
                    f"Prefix unary operator {op!r} must begin its recursive segment"
                )
            right = self._build_segment(table, rmq, p + 1, hi)
            # Unary operand is stored in left for a uniform one-child AstNode.
            return AstNode(op, right, None)

        raise ValueError(f"Unsupported unary fixity for {op!r}")
