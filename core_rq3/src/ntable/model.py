from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple, List


@dataclass(frozen=True)
class NTable:
    tokens: Tuple[str, ...]
    values: Tuple[Optional[int], ...]

    def __post_init__(self) -> None:
        if len(self.tokens) != len(self.values):
            raise ValueError("tokens and values must have equal length")

    def has_operator(self) -> bool:
        return any(v is not None for v in self.values)

    def operator_max(self) -> int:
        vals = [v for v in self.values if v is not None]
        if not vals:
            raise ValueError("N-Table contains no operator")
        return max(vals)

    def shifted(self, delta: int) -> "NTable":
        return NTable(
            self.tokens,
            tuple(None if v is None else v + delta for v in self.values),
        )

    def pretty(self) -> str:
        widths = [
            max(len(tok), 4 if val is None else len(str(val)))
            for tok, val in zip(self.tokens, self.values)
        ]
        s = "S: " + " ".join(tok.rjust(w) for tok, w in zip(self.tokens, widths))
        d = "D: " + " ".join(
            ("null" if val is None else str(val)).rjust(w)
            for val, w in zip(self.values, widths)
        )
        return s + "\n" + d


@dataclass
class AstNode:
    label: str
    left: Optional["AstNode"] = None
    right: Optional["AstNode"] = None

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None

    def prefix(self) -> str:
        if self.is_leaf:
            return self.label
        if self.right is None:
            return f"({self.label} {self.left.prefix() if self.left else '∅'})"
        return (
            f"({self.label} "
            f"{self.left.prefix() if self.left else '∅'} "
            f"{self.right.prefix() if self.right else '∅'})"
        )

    def pretty(self) -> str:
        lines: List[str] = []

        def rec(node: "AstNode", prefix: str, is_tail: bool) -> None:
            lines.append(prefix + ("└── " if is_tail else "├── ") + node.label)
            children = [c for c in (node.left, node.right) if c is not None]
            for idx, child in enumerate(children):
                rec(
                    child,
                    prefix + ("    " if is_tail else "│   "),
                    idx == len(children) - 1,
                )

        lines.append(self.label)
        children = [c for c in (self.left, self.right) if c is not None]
        for idx, child in enumerate(children):
            rec(child, "", idx == len(children) - 1)
        return "\n".join(lines)
