from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Mapping, Tuple


class Fixity(str, Enum):
    INFIX = "infix"
    PREFIX = "prefix"
    POSTFIX = "postfix"


@dataclass(frozen=True)
class Operator:
    symbol: str
    rank: int
    arity: int
    fixity: Fixity

    def __post_init__(self) -> None:
        if self.arity not in (1, 2):
            raise ValueError(f"Unsupported arity {self.arity} for {self.symbol!r}")
        if self.arity == 2 and self.fixity is not Fixity.INFIX:
            raise ValueError(f"Binary operator {self.symbol!r} must be infix")
        if self.arity == 1 and self.fixity is Fixity.INFIX:
            raise ValueError(f"Unary operator {self.symbol!r} cannot be infix")


class OperatorSpec:
    """Immutable operator-rank / arity / fixity contract."""

    __slots__ = ("_ops", "_symbols_longest")

    def __init__(self, operators: Iterable[Operator]) -> None:
        ops: Dict[str, Operator] = {}
        for op in operators:
            if op.symbol in ops:
                raise ValueError(f"Duplicate operator: {op.symbol}")
            if op.symbol in {"(", ")"}:
                raise ValueError("Parentheses are structural tokens, not operators in OperatorSpec")
            ops[op.symbol] = op
        if not ops:
            raise ValueError("OperatorSpec must contain at least one operator")
        self._ops = ops
        self._symbols_longest = tuple(sorted(ops, key=len, reverse=True))

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._ops

    def __getitem__(self, symbol: str) -> Operator:
        try:
            return self._ops[symbol]
        except KeyError:
            raise ValueError(f"Unknown operator {symbol!r}") from None

    @property
    def symbols_longest_first(self) -> Tuple[str, ...]:
        return self._symbols_longest

    @property
    def ranks(self) -> Tuple[int, ...]:
        return tuple(sorted({op.rank for op in self._ops.values()}))

    def rank(self, symbol: str) -> int:
        return self[symbol].rank

    def arity(self, symbol: str) -> int:
        return self[symbol].arity

    def fixity(self, symbol: str) -> Fixity:
        return self[symbol].fixity

    def as_mapping(self) -> Mapping[str, Operator]:
        return dict(self._ops)


def default_operator_spec() -> OperatorSpec:
    # /Γ is treated as postfix here because the current paper's reconstruction
    # pseudocode describes unary operators through postfix operand selection.
    # Change its fixity in a custom OperatorSpec if the experiment uses prefix /Γ.
    return OperatorSpec(
        [
            Operator("|", 0, 2, Fixity.INFIX),
            Operator("||", 1, 2, Fixity.INFIX),
            Operator("[]", 1, 2, Fixity.INFIX),
            Operator(".", 2, 2, Fixity.INFIX),
            Operator("*", 3, 1, Fixity.POSTFIX),
            Operator("/Γ", 3, 1, Fixity.POSTFIX),
        ]
    )
