# -*- coding: utf-8 -*-
"""Reconstruction of AST-EP from JSS 2023 (111798).

Paper: "Using expression parsing and algebraic operations to generate test sequences"

The reconstruction follows the paper's core algorithm:
- construct an AST;
- obtain the post-order list;
- repeatedly locate the first operator;
- reduce binary Op1 using its two preceding values;
- reduce postfix Op2 using its preceding value;
- use the special ParsingClosure heuristic for '*'.

The original paper used a modified RE2 for AST construction. That modified source is
not supplied in the paper, so this reconstruction uses the shared deterministic parser
in common.py under the operator-priority contract documented in README.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from common import (
    AlgebraEngine,
    ASTNode,
    CONCAT,
    CHOICE,
    INTERLEAVE,
    PARALLEL,
    STAR,
    TraceStep,
    Value,
    atom_value,
    ast_height,
    ast_node_count,
    build_ast,
    is_binary_operator,
    is_constraint_token,
    is_integer_token,
    language_to_strings,
    postorder_tokens,
)


@dataclass
class ASTEPResult:
    value: Value
    sequences: List[str]
    trace: List[TraceStep]
    ast: ASTNode
    postorder: List[str]
    operation_count: int
    ast_nodes: int
    ast_height: int


class ASTEP2023(object):
    """Executable AST-EP baseline reconstructed from Fig. 3 and Fig. 5."""

    def __init__(self, max_sequences: int = 100000, constraint_handler=None):
        self.engine = AlgebraEngine(max_sequences=max_sequences,
                                    constraint_handler=constraint_handler)
        # Python equivalent of the paper's T/V lookup organization.
        # T maps an operator to an interval in V. The generalized semantic rules
        # are functions rather than textual equations, but lookup is preserved.
        self.V = [
            "choice", "concatenation", "interleaving", "parallel",
            "star", "numeric_repetition", "constraint"
        ]
        self.T: Dict[str, Tuple[int, int]] = {
            CHOICE: (0, 0),
            CONCAT: (1, 1),
            INTERLEAVE: (2, 2),
            PARALLEL: (3, 3),
            STAR: (4, 4),
            "<N>": (5, 5),
            "/Γ": (6, 6),
        }

    @staticmethod
    def _is_operator(token: object) -> bool:
        return (isinstance(token, str) and
                (is_binary_operator(token) or token == STAR or
                 is_integer_token(token) or is_constraint_token(token)))

    @staticmethod
    def _is_op1(token: object) -> bool:
        return isinstance(token, str) and is_binary_operator(token)

    @staticmethod
    def _is_op2(token: object) -> bool:
        return (isinstance(token, str) and
                (token == STAR or is_integer_token(token) or is_constraint_token(token)))

    @staticmethod
    def _first_operator_index(seq: List[Union[str, Value]]) -> Optional[int]:
        for i, item in enumerate(seq):
            if ASTEP2023._is_operator(item):
                return i
        return None

    def _parsing_closure(self, operand: Value, op: str) -> Tuple[Value, str]:
        """Fig. 5 / Eqs. (16)-(18).

        For '*':
          - if the reduced operand is a top-level choice a1|...|an, k=n;
          - otherwise k=3.
        Other postfix operators are delegated to the operation set.
        """
        if op == STAR:
            if operand.top_choice_arity is not None:
                k = operand.top_choice_arity
                rule = "Eq.(17)+(18): choice closure, k=n=%d" % k
            else:
                k = 3
                rule = "Eq.(16)+(18): non-choice closure, k=3"
            value, _ = self.engine.postfix(STAR, operand, star_bound=k)
            return value, rule
        if is_integer_token(op):
            value, _ = self.engine.postfix(op, operand, star_bound=3)
            return value, "algebraic operation set: numeric repetition"
        if is_constraint_token(op):
            value, _ = self.engine.postfix(op, operand, star_bound=3)
            return value, "algebraic operation set: constraint"
        raise ValueError("Unsupported Op2: %s" % op)

    def run(self, expression: str, separator: str = "") -> ASTEPResult:
        ast = build_ast(expression)
        po = postorder_tokens(ast)
        seq: List[Union[str, Value]] = []
        for tok in po:
            if self._is_operator(tok):
                seq.append(tok)
            else:
                seq.append(atom_value(tok))

        trace: List[TraceStep] = []
        step_no = 0
        while True:
            i = self._first_operator_index(seq)
            if i is None:
                break
            op = seq[i]
            before = self._seq_text(seq)
            if self._is_op1(op):
                if i < 2 or not isinstance(seq[i - 2], Value) or not isinstance(seq[i - 1], Value):
                    raise ValueError("Malformed AST-EP postorder around binary operator %r" % op)
                left = seq[i - 2]
                right = seq[i - 1]
                value, rule_name = self.engine.binary(str(op), left, right)
                seq[i - 2:i + 1] = [value]
                paper_rule = "Theorem 3(1) / %s" % rule_name
            else:
                if i < 1 or not isinstance(seq[i - 1], Value):
                    raise ValueError("Malformed AST-EP postorder around unary operator %r" % op)
                operand = seq[i - 1]
                value, paper_rule = self._parsing_closure(operand, str(op))
                seq[i - 1:i + 1] = [value]
            step_no += 1
            trace.append(TraceStep(
                step=step_no,
                algorithm="AST-EP-2023",
                scope="postorder",
                operator=str(op),
                rule=paper_rule,
                before=before,
                after=self._seq_text(seq),
                result_count=len(value.language),
            ))

        if len(seq) != 1 or not isinstance(seq[0], Value):
            raise ValueError("AST-EP did not reduce to one value: %r" % seq)
        value = seq[0]
        return ASTEPResult(
            value=value,
            sequences=language_to_strings(value.language, separator=separator),
            trace=trace,
            ast=ast,
            postorder=po,
            operation_count=len(trace),
            ast_nodes=ast_node_count(ast),
            ast_height=ast_height(ast),
        )

    @staticmethod
    def _seq_text(seq: List[Union[str, Value]]) -> str:
        parts: List[str] = []
        for item in seq:
            if isinstance(item, Value):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "<" + ", ".join(parts) + ">"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Reconstructed AST-EP (JSS 2023)")
    parser.add_argument("expression")
    parser.add_argument("--separator", default="", help="Join multi-token actions with this separator")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()

    result = ASTEP2023().run(args.expression, separator=args.separator)
    print("postorder:", result.postorder)
    print("AST nodes:", result.ast_nodes, "height:", result.ast_height)
    print("algebraic operations:", result.operation_count)
    print("sequences (%d):" % len(result.sequences))
    for s in result.sequences:
        print(s)
    if args.trace:
        print("\nTRACE")
        for step in result.trace:
            print("%02d op=%s rule=%s" % (step.step, step.operator, step.rule))
            print("  before:", step.before)
            print("  after :", step.after)


if __name__ == "__main__":
    main()
